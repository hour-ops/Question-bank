#!/usr/bin/env python
"""用**真实题目**按 ACA 考纲配比组一张 50 题卷子（不再让大模型写题）。

背景：用户反馈 AI 生成的题"雷同，都是一类问题"。真实题库（考试宝 82 题 + 用户提供的
ACA/ACP 题）已经按六个考点打好标（scripts/classify_kaoshibao.py），配比够用，
所以这张卷子**全部取真题**：

    单选 35 = 概念6 + 提示词7 + 增强8 + 微调4 + Agent6 + 安全4
    多选 15 = 概念3 + 提示词3 + 增强3 + 微调2 + Agent2 + 安全2
    合计 50 题 / 100 分（每题 2 分）

顺序：先插 35 道单选、再插 15 道多选 → id 顺序 = 卷面顺序。
⚠️ 会把原题**复制**一份到新卷名下（原题库保留不动），因此同一道题会出现在两个卷子里。

用法:
    python scripts/build_paper_from_bank.py --paper "真题仿真卷·ACA-50题"            # dry-run
    python scripts/build_paper_from_bank.py --paper "..." --apply --replace
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sqlite3
import sys
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SUBJECT = "aca_llm"
sys.path.insert(0, str(ROOT / "scripts"))
try:
    from lib.uid import generate_uid  # noqa: E402
except Exception:  # noqa: BLE001
    generate_uid = None

MODULES = ["考点·大模型概念", "考点·提示词工程", "考点·增强大模型应用的能力",
           "考点·大模型微调", "考点·大模型 Agent", "考点·安全合规"]
NEED_SINGLE = [6, 7, 8, 4, 6, 4]
NEED_MULTI = [3, 3, 3, 2, 2, 2]


def module_of(kp: str) -> str | None:
    kp = (kp or "").strip()
    if not kp:
        return None
    if kp in MODULES:
        return kp
    # 兼容三种写法：「大模型微调」/「大模型概念·1.1」（chapter）/「考点·大模型微调」
    s = kp[3:] if kp.startswith("考点·") else kp
    s = s.split("·")[0].strip()
    for m in MODULES:
        if m.replace("考点·", "") == s:
            return m
    m = re.match(r"^KP-(\d)", kp)
    if m:
        i = int(m.group(1)) - 1
        return MODULES[i] if 0 <= i < 6 else None
    return None


def grams(s: str, n: int = 4) -> set[str]:
    t = re.sub(r"[\s\u3000，。、；：？！“”‘’（）()【】\[\]《》,.;:?!\"'*]+", "", s or "")
    return {t[i:i + n] for i in range(max(0, len(t) - n + 1))}


def similar(a: set[str], b: set[str], thr: float = 0.55) -> bool:
    if not a or not b:
        return False
    return len(a & b) / max(1, len(a | b)) >= thr


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--paper", required=True)
    ap.add_argument("--seed", type=int, default=20261024)
    ap.add_argument("--replace", action="store_true")
    ap.add_argument("--allow-ai-fill", action="store_true",
                    help="真题不够的格子允许从 AI 生成题里补（卷内会如实保留 trust_level）")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    db = DATA / f"{SUBJECT}.sqlite"
    con = sqlite3.connect(str(db))
    con.row_factory = sqlite3.Row
    if args.replace and args.apply:
        # ⚠ 必须先删同名旧卷，再挑选候选：否则本卷上一版的 50 条会把题源挡掉（少 50 题）
        old = con.execute("SELECT count(*) FROM questions WHERE exam_title=?", (args.paper,)).fetchone()[0]
        if old:
            con.execute("DELETE FROM questions WHERE exam_title=?", (args.paper,))
            con.commit()
            print(f"--replace：已删除同名旧卷 {old} 题")
    rows = con.execute(
        "SELECT * FROM questions WHERE status='approved' "
        "AND COALESCE(trust_level,'')<>'acp' AND COALESCE(trust_level,'')<>'ai_generated' "
        "AND COALESCE(reviewed_by,'')<>'paper-assembly' "     # 卷内复制出来的副本不算题源
        "AND stem NOT IN (SELECT stem FROM questions WHERE reviewed_by='paper-assembly') "  # 已被别的卷用过
        "AND (knowledge_point LIKE '考点·%' OR knowledge_point LIKE 'KP-%') "
        "ORDER BY id").fetchall()
    print(f"候选真题 {len(rows)} 题（考试宝 + 用户提供 + 散题，均已打考点标）")

    pool: dict[tuple[str, str], list] = defaultdict(list)
    for r in rows:
        mod = module_of(r["knowledge_point"])
        if not mod:
            continue
        pool[(mod, r["question_type"])].append(r)

    # AI 补题池（只在 --allow-ai-fill 且真题不够时用；不动卷内真题的 trust_level）
    ai_pool: dict[tuple[str, str], list] = defaultdict(list)
    if args.allow_ai_fill:
        ai_rows = con.execute(
            "SELECT * FROM questions WHERE status='approved' AND trust_level='ai_generated' "
            "AND COALESCE(reviewed_by,'')<>'paper-assembly' ORDER BY id").fetchall()
        for r in ai_rows:
            mod = module_of(r["chapter"]) or module_of(r["knowledge_point"])
            if mod:
                ai_pool[(mod, r["question_type"])].append(r)
        print(f"AI 补题池 {len(ai_rows)} 题（仅补真题不足的格子）")

    rnd = random.Random(args.seed)
    picked: list[sqlite3.Row] = []
    plan: list[tuple[str, str]] = []
    # 先排完所有单选、再排所有多选 —— 这样 id 顺序就是「1–35 单选、36–50 多选」
    for i, mod in enumerate(MODULES):
        plan += [(mod, "single_choice")] * NEED_SINGLE[i]
    for i, mod in enumerate(MODULES):
        plan += [(mod, "multiple_choice")] * NEED_MULTI[i]

    print("\n考点配比检查：")
    print(f"  {'考点':<20}{'单选(需/有)':>12}{'多选(需/有)':>12}")
    short = False
    for i, mod in enumerate(MODULES):
        s = len(pool[(mod, "single_choice")])
        m = len(pool[(mod, "multiple_choice")])
        miss = "  ← 不足" if (s < NEED_SINGLE[i] or m < NEED_MULTI[i]) else ""
        short = short or bool(miss)
        print(f"  {mod:<20}{f'{NEED_SINGLE[i]}/{s}':>12}{f'{NEED_MULTI[i]}/{m}':>12}{miss}")
    if short and not args.allow_ai_fill:
        print("配比不够，先补题库（或加 --allow-ai-fill 用 AI 补缺口）")
        return 1
    if short:
        print("⚠ 上面标 ← 不足 的格子会用 AI 补题")

    used_stems: set[str] = set()
    picked_grams: list[set[str]] = []
    ai_used = 0

    def choose(cands: list) -> sqlite3.Row | None:
        rnd.shuffle(cands)
        cands.sort(key=lambda r: 0 if "考试宝" in (r["exam_title"] or "") else 1)
        for cand in cands:
            g = grams(cand["stem"])
            if any(similar(g, e) for e in picked_grams):
                continue
            return cand
        return None

    for mod, qtype in plan:
        pick = choose([r for r in pool[(mod, qtype)] if r["stem"] not in used_stems])
        if pick is None and args.allow_ai_fill:
            pick = choose([r for r in ai_pool[(mod, qtype)] if r["stem"] not in used_stems])
            if pick is not None:
                ai_used += 1
        if pick is None:
            print(f"  ⚠ {mod}/{qtype} 可用题不足（真题与 AI 补题都用完了）")
            return 1
        used_stems.add(pick["stem"])
        picked_grams.append(grams(pick["stem"]))
        picked.append(pick)
    if ai_used:
        print(f"⚠ 其中 {ai_used} 题来自 AI 生成题（真题不足的格子），入库后 trust_level 仍是 ai_generated")

    singles = sum(1 for r in picked if r["question_type"] == "single_choice")
    print(f"\n组卷：{len(picked)} 题（单选 {singles} / 多选 {len(picked) - singles}）")

    if not args.apply:
        for i, r in enumerate(picked[:3], 1):
            print(f"  {i}. [{r['knowledge_point']}] {r['stem'][:60]}")
        print("\ndry-run：未写库")
        con.close()
        return 0

    cols = [c[1] for c in con.execute("PRAGMA table_info(questions)")]
    inserted = 0
    try:
        for seq, (r, (mod, qtype)) in enumerate(zip(picked, plan), 1):
            stem = r["stem"]
            uid = (generate_uid(SUBJECT, "paper-assembly", args.paper + stem) if generate_uid
                   else None) or f"pp-{uuid.uuid4().hex[:12]}"
            row = dict(r)
            src_label = "AI补题" if (r["trust_level"] == "ai_generated") else "真题"
            row.update({
                "question_uid": uid,
                "source_type": r["source_type"] or "real_exam",
                "source_credit": f"{args.paper}（取自：{r['exam_title'] or '题库'}）",
                "exam_title": args.paper,
                # 卷面「考点分布」条按 chapter 的『模块·来源』解析
                "chapter": f"{mod.replace('考点·', '')}·{src_label}",
                "status": "approved",
                "reviewed_by": "paper-assembly",
                "version": 1,
            })
            row = {k: v for k, v in row.items() if k in cols and k != "id"}
            con.execute(f"INSERT INTO questions ({','.join(row)}) VALUES ({','.join('?' * len(row))})",
                        tuple(row.values()))
            inserted += 1
        con.commit()
    finally:
        con.close()

    chk = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    chk.row_factory = sqlite3.Row
    out = chk.execute("SELECT question_type, knowledge_point, chapter FROM questions "
                      "WHERE exam_title=? ORDER BY id", (args.paper,)).fetchall()
    kinds = [r["question_type"] for r in out]
    fm = next((i for i, k in enumerate(kinds) if k == "multiple_choice"), len(kinds))
    from collections import Counter
    print(f"\n已入库 {inserted} 题 → '{args.paper}'")
    print(f"分段：第 1–{fm} 题单选，第 {fm + 1}–{len(kinds)} 题多选"
          f"{'✓' if not any(k == 'single_choice' for k in kinds[fm:]) else '❌'}")
    print("考点分布：")
    for mod in MODULES:
        n = sum(1 for r in out if module_of(r["chapter"]) == mod)
        print(f"  {mod:<20}{n:>3} 题（{n / len(out):.0%}）")
    ai_n = sum(1 for r in out if (r["chapter"] or "").endswith("AI补题"))
    if ai_n:
        print(f"  其中 AI 补题 {ai_n} 题 / 真题 {len(out) - ai_n} 题")
    chk.close()
    return 0 if inserted == len(plan) else 3


if __name__ == "__main__":
    raise SystemExit(main())
