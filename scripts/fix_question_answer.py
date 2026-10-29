"""改判一条题的答案（人工复核用）。

背景：考试宝 37563622 的答案锁在 APP，库里这 89 道题的答案是模型推断的，
其中「多模态协同学习」一题模型给了 B，但题干要求"理解语音和图像的上下文"，
四个选项里只有 A「音频转视频」同时涉及音频与画面；B 视觉定位通常是"图像＋文本指令"。
用户反馈多个 AI 也选 A —— 以题干证据为准改判为 A，并把复核标记写进库。

用法:
    python scripts/fix_question_answer.py --stem-like "%多模态协同学习%" --answer A --reviewed "manual-fix:multimodal"
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SUBJECT = "aca_llm"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stem-like", required=True)
    ap.add_argument("--answer", required=True)
    ap.add_argument("--explanation", default="")
    ap.add_argument("--reviewed", default="manual-fix")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    db = DATA / f"{SUBJECT}.sqlite"
    con = sqlite3.connect(str(db))
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT id, exam_title, answer, explanation FROM questions WHERE stem LIKE ?",
        (args.stem_like,)).fetchall()
    if not rows:
        print("没找到题目")
        return 1
    for r in rows:
        print(f"id={r['id']} 《{r['exam_title']}》 {r['answer']} → {args.answer.upper()}")
        print("  旧解析:", (r["explanation"] or "")[:120])
    if not args.apply:
        print("\ndry-run：未写库")
        con.close()
        return 0
    try:
        for r in rows:
            con.execute(
                "UPDATE questions SET answer=?, explanation=COALESCE(NULLIF(?,''), explanation), "
                "reviewed_by=? WHERE id=?",
                (args.answer.upper(), args.explanation, args.reviewed, r["id"]))
        con.commit()
    finally:
        con.close()
    print(f"\n已改判 {len(rows)} 条 → 答案 {args.answer.upper()}，复核标记 {args.reviewed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
