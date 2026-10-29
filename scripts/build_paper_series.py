#!/usr/bin/env python
"""一次生成**四套** 50 题真题仿真卷（200 题不重复），按考纲分数分布组卷。

卷面规格（每套都一样，与官方一致）：
    单选 35 = 概念6 + 提示词7 + 增强8 + 微调4 + Agent6 + 安全4
    多选 15 = 概念3 + 提示词3 + 增强3 + 微调2 + Agent2 + 安全2
    合计 50 题 / 100 分（每题 2 分）

题源优先级：**考试宝真题 > 其它真题 > AI 生成**（AI 只补真题不够的格子，
卷内 `source_url`/`trust_level` 原样保留，所以套卷页的来源徽标是准的）。

四套之间**零复用**：每题只出现一次。

用法:
    python scripts/build_paper_series.py --series 4            # dry-run
    python scripts/build_paper_series.py --series 4 --apply
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SUBJECT = "aca_llm"
PREFIX = "真题仿真卷·ACA-50题"

MODULES = ["考点·大模型概念", "考点·提示词工程", "考点·增强大模型应用的能力",
           "考点·大模型微调", "考点·大模型 Agent", "考点·安全合规"]
NEED_S = [6, 7, 8, 4, 6, 4]
NEED_M = [3, 3, 3, 2, 2, 2]
CN = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十", "十一", "十二"]

sys.path.insert(0, str(ROOT / "scripts"))
try:
    from lib.uid import generate_uid  # noqa: E402
except Exception:  # noqa: BLE001
    generate_uid = None


def module_of(kp: str) -> str | None:
    kp = (kp or "").strip()
    if not kp:
        return None
    if kp in MODULES:
        return kp
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
    return bool(a and b) and len(a & b) / max(1, len(a | b)) >= thr


def pref(r: sqlite3.Row) -> int:
    url = str(r["source_url"] or "")
    tl = str(r["trust_level"] or "")
    if "kaoshibao" in url:
        return 0          # 考试宝真题最优先
    if tl == "ai_generated":
        return 2          # AI 最后
    return 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--series", type=int, default=4, help="一共出几套（从 --start 开始编号）")
    ap.add_argument("--start", type=int, default=1, help="起始卷号（1=第一套）")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    db = DATA / f"{SUBJECT}.sqlite"
    con = sqlite3.connect(str(db))
    con.row_factory = sqlite3.Row

    # 只清掉**本次要写的那几套**（append 模式不动已有卷子）
    titles = [f"{PREFIX}（{CN[args.start - 1 + i]}）" for i in range(args.series)]
    old = con.execute(
        "SELECT count(*) FROM questions WHERE exam_title IN (%s)" % ",".join("?" * len(titles)),
        titles).fetchone()[0]
    print(f"本次目标 {len(titles)} 套；同名的旧副本 {old} 题（--apply 时删除重建）")

    rows = con.execute(
        "SELECT * FROM questions WHERE status='approved' "
        "AND COALESCE(reviewed_by,'')<>'paper-assembly' "
        "AND COALESCE(reviewed_by,'')<>'paper-series' "
        "AND COALESCE(trust_level,'')<>'acp' "
        "AND stem NOT IN (SELECT stem FROM questions WHERE reviewed_by IN ('paper-assembly','paper-series')) "
        "ORDER BY id").fetchall()
    pool: dict[tuple[str, str], list] = defaultdict(list)
    for r in rows:
        mod = module_of(r["chapter"]) or module_of(r["knowledge_point"])
        if mod and r["question_type"] in ("single_choice", "multiple_choice"):
            pool[(mod, r["question_type"])].append(r)
    for k in pool:
        pool[k].sort(key=pref)

    need = [(m, "single_choice", NEED_S[i]) for i, m in enumerate(MODULES)] + \
           [(m, "multiple_choice", NEED_M[i]) for i, m in enumerate(MODULES)]
    need_map = {(m, t): n for m, t, n in need}
    P = args.series

    # ① 每个格子按「考试宝 > 其它真题 > AI」排序，取够 P×n 道（整卷系列池）
    cells: dict[tuple[str, str], list] = {}
    for mod, qtype, n in need:
        want = n * P
        seen = set()
        picked = []
        for cand in pool[(mod, qtype)]:
            if cand["stem"] in seen:
                continue
            seen.add(cand["stem"])
            picked.append(cand)
            if len(picked) == want:
                break
        if len(picked) < want:
            print(f"  ❌ {mod}/{qtype} 只有 {len(picked)}/{want} 题可用")
            return 1
        cells[(mod, qtype)] = picked

    # ② 轮转发牌：把每格均匀摊到 P 套里（避免"前三套全真题、第四套全是 AI"）
    papers: list[list[sqlite3.Row]] = [[] for _ in range(P)]
    for (mod, qtype), lst in cells.items():
        for i in range(P):
            papers[i].extend(lst[i::P])

    # ③ 卷内排序：先按题型（单选在前）、再按模块顺序
    order_mod = {m: i for i, m in enumerate(MODULES)}
    order_type = {"single_choice": 0, "multiple_choice": 1}
    for i in range(P):
        papers[i].sort(key=lambda r: (order_type.get(r["question_type"], 9),
                                      order_mod.get(module_of(r["chapter"]) or
                                                    module_of(r["knowledge_point"]) or "", 9)))

    # ④ 卷内近似重复检查：撞了就换成同格子还没用的题
    used: set[int] = {r["id"] for pr in papers for r in pr}
    for i, pr in enumerate(papers):
        grams_list = [grams(r["stem"]) for r in pr]
        for j in range(len(pr)):
            for k in range(j):
                if not similar(grams_list[j], grams_list[k]):
                    continue
                mod = module_of(pr[j]["chapter"]) or module_of(pr[j]["knowledge_point"]) or ""
                spare = [c for c in pool.get((mod, pr[j]["question_type"]), [])
                         if c["id"] not in used]
                for c in spare:
                    g = grams(c["stem"])
                    if all(not similar(g, gk) for gi, gk in enumerate(grams_list) if gi != j):
                        used.discard(pr[j]["id"])
                        used.add(c["id"])
                        pr[j] = c
                        grams_list[j] = g
                        break

    for p, picked in enumerate(papers):
        kinds = Counter(r["question_type"] for r in picked)
        src = Counter(("考试宝" if "kaoshibao" in (r["source_url"] or "") else
                       ("AI" if r["trust_level"] == "ai_generated" else "其它真题")) for r in picked)
        print(f"第{CN[p]}套：{len(picked)} 题｜单选 {kinds['single_choice']} 多选 {kinds['multiple_choice']}"
              f"｜来源 {dict(src)}")

    if not args.apply:
        print("\ndry-run：未写库")
        con.close()
        return 0

    cols = [c[1] for c in con.execute("PRAGMA table_info(questions)")]
    inserted = 0
    try:
        con.execute("DELETE FROM questions WHERE exam_title IN (%s)" % ",".join("?" * len(titles)),
                    titles)
        for p, picked in enumerate(papers):
            title = f"{PREFIX}（{CN[args.start - 1 + p]}）"
            for r in picked:
                stem = r["stem"]
                # ⚠ generate_uid 只取 stem 前 50 字，把 id 塞进 source_url 才能保证唯一
                uid = (generate_uid(SUBJECT, f"paper-series:{title}:{r['id']}", stem) if generate_uid
                       else None) or f"ps-{uuid.uuid4().hex[:12]}"
                is_kb = "kaoshibao" in (r["source_url"] or "")
                label = "考试宝真题" if is_kb else ("AI补题" if r["trust_level"] == "ai_generated" else "其它真题")
                row = dict(r)
                row.update({
                    "question_uid": uid,
                    "exam_title": title,
                    "source_credit": f"{title}（取自：{r['exam_title'] or '题库'}）",
                    "chapter": f"{module_of(r['chapter']) or module_of(r['knowledge_point']) or ''}"
                               .replace("考点·", "") + f"·{label}",
                    "status": "approved",
                    "reviewed_by": "paper-series",
                    "version": 1,
                })
                row = {k: v for k, v in row.items() if k in cols and k != "id"}
                con.execute(f"INSERT INTO questions ({','.join(row)}) VALUES ({','.join('?' * len(row))})",
                            tuple(row.values()))
                inserted += 1
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
    print(f"\n已写入 {inserted} 题，共 {args.series} 套 → {PREFIX}（一…{CN[args.series - 1]}）")

    chk = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    chk.row_factory = sqlite3.Row
    for p in range(args.series):
        t = f"{PREFIX}（{CN[p]}）"
        qs = chk.execute("SELECT question_type, chapter FROM questions WHERE exam_title=? ORDER BY id", (t,)).fetchall()
        kinds = [q["question_type"] for q in qs]
        fm = next((i for i, k in enumerate(kinds) if k == "multiple_choice"), len(kinds))
        mods = Counter((q["chapter"] or "·").split("·")[0] for q in qs)
        srcs = Counter((q["chapter"] or "·").split("·")[-1] for q in qs)
        print(f"\n{t}：{len(qs)} 题，第1–{fm} 单选 / 其余多选"
              f"{'✓' if not any(k == 'single_choice' for k in kinds[fm:]) else '❌'}")
        print("   考点：" + "｜".join(f"{m.replace('考点·', '')}{mods.get(m.replace('考点·', ''), 0)}"
                                    for m in MODULES))
        print("   来源：" + "｜".join(f"{k}{v}" for k, v in srcs.items()))
    chk.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
