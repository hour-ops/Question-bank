#!/usr/bin/env python
"""按考纲剔除英语选择题：英语考纲明令「无选择题/无判断题」，但源站把大量四选一
题目混在"阅读填空/阅读理解"栏目里，被我的题型推断错标成 `reading_fill`。

判定（任一命中即认为是选择题）：
  - `options` 字段非空（不是 `[]`/`null`）
  - 答案形如 `A` / `B.` / `AB` 等纯选项字母（≤4 个字母）
  - 题干里出现 ≥2 组 `A. B. C. D.` 形式的选项

动作：把命中的题置为 `rejected`（**不删除**，保留可追溯），原因写明"考纲禁止选择题"。

用法: python scripts/drop_english_choice.py --dry-run
      python scripts/drop_english_choice.py --apply
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "english.sqlite"
REJ = ROOT / "logs" / "review_rejects.jsonl"

# 题干里的选项：A. xxx  B. xxx  C. xxx  D. xxx（允许 A) A、 A．等变体）
OPT_RE = re.compile(r"(?:^|\s)[A-D]\s*[.、．)）]\s*\S")
ANS_LETTER_RE = re.compile(r"^\s*[A-D]{1,4}\s*[.、．]?\s*$")


def is_choice(stem: str, answer: str, options: str | None) -> bool:
    if options and str(options).strip() not in ("", "[]", "null"):
        return True
    if ANS_LETTER_RE.match(answer or ""):
        return True
    hits = OPT_RE.findall(stem or "")
    return len(hits) >= 2


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if not args.dry_run and not args.apply:
        print("请指定 --dry-run 或 --apply")
        return 2

    conn = sqlite3.connect(str(DB))
    conn.execute("PRAGMA busy_timeout=30000")
    rows = conn.execute(
        "SELECT question_uid, question_type, stem, answer, options, status FROM questions"
    ).fetchall()
    hits = [(u, t, s, a, o, st) for u, t, s, a, o, st in rows if is_choice(s, a, o)]
    print(f"英语共 {len(rows)} 题，判定为选择题 {len(hits)} 题")
    from collections import Counter
    print("  按题型:", dict(Counter(t for *_x, t, _s, _a, _o, _st in [(0, *h) for h in hits])))
    print("  按当前状态:", dict(Counter(h[5] for h in hits)))
    for h in hits[:5]:
        print(f"   - [{h[1]}] {str(h[2])[:70]} | 答案={str(h[3])[:12]}")

    if args.dry_run:
        print("\ndry-run：未写库。")
        return 0

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with REJ.open("a", encoding="utf-8") as fh:
        for uid, _t, _s, _a, _o, _st in hits:
            conn.execute("UPDATE questions SET status='rejected', reviewed_by='rule:no-choice', "
                         "version=COALESCE(version,0)+1 WHERE question_uid=?", (uid,))
            fh.write(json.dumps({"ts": now, "question_uid": uid, "subject": "english",
                                 "reason": "考纲禁止选择题：实测内容为四选一，题型标注错误"},
                                ensure_ascii=False) + "\n")
    conn.commit()
    n_appr = conn.execute("SELECT count(*) FROM questions WHERE status='approved'").fetchone()[0]
    conn.close()
    print(f"\n已剔除 {len(hits)} 题；英语 approved 仍为 {n_appr} 题")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
