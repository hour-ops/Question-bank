#!/usr/bin/env python
"""在两个科目库之间按 `question_uid` 对齐 `options`（只补"目标库缺、源库有"的题）。

用途：
  - 便携版与源码根是两套 `data/`，同一道题的 `id` 不同但 `question_uid` 相同
    （uid 由 `(subject, source_url, stem)` 决定，全项目同一套规则）。
  - 所以"源码根已经修好、便携版还没修"的题，可以直接按 uid 搬过去，零成本。

只写 `questions.options` / `reviewed_by` / `version`；不动 `wrong_book` / `review_log`。

用法:
    python scripts/sync_options_by_uid.py --src-data data --dst-data "D:\\便携版\\data" --subject aca_llm
    python scripts/sync_options_by_uid.py --src-data ... --dst-data ... --subject aca_llm --apply
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def opt_count(raw) -> int:
    try:
        arr = json.loads(raw) if isinstance(raw, str) else raw
        return len(arr) if isinstance(arr, list) else 0
    except (TypeError, ValueError):
        return 0


def backup_db(path: Path) -> Path:
    dst_dir = path.parent / "backup"
    dst_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = dst_dir / f"{path.stem}-{stamp}{path.suffix}"
    src = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    dst = sqlite3.connect(str(target))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return target


def main() -> int:
    ap = argparse.ArgumentParser(description="按 question_uid 把 options 从源库搬到目标库（默认 dry-run）")
    ap.add_argument("--src-data", required=True)
    ap.add_argument("--dst-data", required=True)
    ap.add_argument("--subject", default="aca_llm")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    src_db = Path(args.src_data) / f"{args.subject}.sqlite"
    dst_db = Path(args.dst_data) / f"{args.subject}.sqlite"
    for p in (src_db, dst_db):
        if not p.exists():
            print(f"缺库: {p}")
            return 2

    s = sqlite3.connect(f"file:{src_db}?mode=ro", uri=True)
    have = {}
    for uid, opts in s.execute("SELECT question_uid, options FROM questions WHERE status<>'archived'"):
        if opt_count(opts) >= 2:
            have[uid] = opts
    s.close()
    print(f"[src] {src_db} 有选项的题: {len(have)}")

    d = sqlite3.connect(f"file:{dst_db}?mode=ro", uri=True)
    need = [(i, uid) for i, uid in d.execute(
        "SELECT id, question_uid FROM questions "
        "WHERE status<>'archived' AND question_type IN ('single_choice','multiple_choice') "
        "AND (options IS NULL OR options='' OR options='[]')")]
    d.close()
    payload = [(i, have[uid]) for i, uid in need if uid in have]
    print(f"[dst] {dst_db} 缺选项 {len(need)} 条，其中 {len(payload)} 条能在源库按 uid 找到")

    if not args.apply or not payload:
        print("（dry-run：未改库）" if not args.apply else "无可用数据")
        return 0

    bak = backup_db(dst_db)
    print(f"[备份] {bak.name}")
    conn = sqlite3.connect(str(dst_db))
    conn.execute("PRAGMA busy_timeout=30000")
    try:
        ts = now_iso()
        for qid, opts in payload:
            conn.execute("UPDATE questions SET options=?, reviewed_by=?, "
                         "version=COALESCE(version,1)+1 WHERE id=?",
                         (opts, f"auto:sync_options_by_uid@{ts}", qid))
        conn.commit()
    finally:
        conn.close()
    print(f"[已改库] 补选项 {len(payload)} 题")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
