#!/usr/bin/env python
"""校验一套生成卷是否真的符合考纲：题型分段 / 模块占比 / 答案分布 / 去重 / 分值。

用法:
    python scripts/verify_paper.py --paper "AI模拟卷·ACA全真50题"
    python scripts/verify_paper.py --paper "..." --expect 50 --expect-single 35 --expect-multi 15
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
sys.path.insert(0, str(ROOT / "scripts"))
import judge_local as jl  # noqa: E402

MODULES = [
    ("大模型概念", 0.18), ("提示词工程", 0.20), ("增强大模型应用的能力", 0.22),
    ("大模型微调", 0.12), ("大模型 Agent", 0.16), ("安全合规", 0.12),
]


def ngrams(s: str, n: int = 4) -> set[str]:
    t = re.sub(r"[\s\u3000，。、；：？！“”‘’（）()【】\[\]《》,.;:?!\"'*]+", "", s or "")
    return {t[i:i + n] for i in range(max(0, len(t) - n + 1))}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--paper", required=True)
    ap.add_argument("--subject", default="aca_llm")
    ap.add_argument("--expect", type=int, default=50)
    ap.add_argument("--expect-single", type=int, default=35)
    ap.add_argument("--expect-multi", type=int, default=15)
    args = ap.parse_args()

    con = sqlite3.connect(f"file:{DATA / f'{args.subject}.sqlite'}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT id, question_type, chapter, knowledge_point, stem, options, answer, explanation "
        "FROM questions WHERE exam_title=? AND status='approved' ORDER BY id", (args.paper,)).fetchall()
    con.close()

    ok = True
    print(f"卷名：{args.paper}")
    print(f"题数：{len(rows)}（期望 {args.expect}）{'✓' if len(rows) == args.expect else '❌'}")
    ok &= len(rows) == args.expect

    kinds = Counter(r["question_type"] for r in rows)
    s, m = kinds.get("single_choice", 0), kinds.get("multiple_choice", 0)
    print(f"题型：单选 {s} / 多选 {m}（期望 {args.expect_single}/{args.expect_multi}）"
          f"{'✓' if (s, m) == (args.expect_single, args.expect_multi) else '❌'}")
    ok &= (s, m) == (args.expect_single, args.expect_multi)

    print(f"满分：{sum(jl.full_score_for(args.subject, r['question_type']) for r in rows):.0f} 分"
          f"（每题 {jl.full_score_for(args.subject, 'single_choice'):.0f} 分）")

    # 分段：前 N 题必须全是单选，其后全是多选
    seq = [r["question_type"] for r in rows]
    first_multi = next((i for i, k in enumerate(seq) if k == "multiple_choice"), len(seq))
    mixed = any(k == "single_choice" for k in seq[first_multi:])
    print(f"分段：第 1–{first_multi} 题单选，第 {first_multi + 1}–{len(seq)} 题多选"
          f"{'✓ 未混杂' if not mixed else '❌ 单选混在多选之后'}")
    ok &= not mixed
    if mixed:
        bad = [i + 1 for i, k in enumerate(seq) if i >= first_multi and k == "single_choice"]
        print("  混杂题号：", bad[:20])

    # 模块占比：题目 chapter 形如「大模型概念·1.4」
    mod = Counter((r["chapter"] or "·").split("·")[0] for r in rows)
    print("\n模块分布（对照考纲权重）：")
    print(f"  {'模块':<12}{'考纲':>6}{'题数':>6}{'本卷占比':>9}   判定")
    for name, w in MODULES:
        n = mod.get(name, 0)
        exp = round(w * len(rows))
        mark = "✓" if n == exp else f"❌ 应 {exp}"
        print(f"  {name:<12}{w:>6.0%}{n:>6}{n / max(1, len(rows)):>9.0%}   {mark}")
        ok &= n == exp
    extra = set(mod) - {x[0] for x in MODULES}
    if extra:
        print("  ⚠ 未识别的模块名：", extra)

    # 单选题答案字母分布（防止全是 B）
    letters = Counter(re.sub(r"[^A-H]", "", str(r["answer"]).upper())
                      for r in rows if r["question_type"] == "single_choice")
    print("\n单选答案分布：", dict(sorted(letters.items())))
    if letters:
        top, cnt = letters.most_common(1)[0]
        ratio = cnt / max(1, s)
        print(f"  最多：{top} 占 {ratio:.0%}{'  ⚠ 偏集中' if ratio > 0.4 else '  ✓'}")

    # 多选答案个数
    multi_lens = Counter(len(re.sub(r"[^A-H]", "", str(r["answer"]).upper()))
                         for r in rows if r["question_type"] == "multiple_choice")
    print("多选答案个数分布：", dict(sorted(multi_lens.items())))

    # 每题结构
    bad_opts = [r["id"] for r in rows
                if len(json.loads(r["options"] or "[]")) != 4
                or len(set(re.sub(r"[^A-H]", "", str(r["answer"]).upper()))) == 0]
    print(f"四选项/答案结构：{'✓ 全部合格' if not bad_opts else f'❌ {bad_opts}'}")
    ok &= not bad_opts

    expl = [len(r["explanation"] or "") for r in rows]
    print(f"解析长度：平均 {sum(expl) / max(1, len(expl)):.0f} 字，最短 {min(expl) if expl else 0} 字")

    # 卷内去重（4-gram Jaccard）
    grams = [(r["id"], ngrams(r["stem"])) for r in rows]
    worst, pair = 0.0, None
    for i in range(len(grams)):
        for j in range(i + 1, len(grams)):
            a, b = grams[i][1], grams[j][1]
            if not a or not b:
                continue
            jac = len(a & b) / len(a | b)
            if jac > worst:
                worst, pair = jac, (grams[i][0], grams[j][0])
    print(f"卷内最大重复度：{worst:.2f}（{pair}）{'✓' if worst < 0.55 else '❌ 有近似重复题'}")
    ok &= worst < 0.55

    # 微调题占比（用户反馈"怎么全是微调"）
    fine = mod.get("大模型微调", 0)
    print(f"\n微调题：{fine} 题（{fine / max(1, len(rows)):.0%}，考纲 12%）"
          f"{'✓' if fine == round(0.12 * len(rows)) else '❌'}")

    print("\n结论：", "✅ 全部符合考纲配比" if ok else "❌ 有不符合项，见上")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
