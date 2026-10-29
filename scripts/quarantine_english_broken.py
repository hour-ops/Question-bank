#!/usr/bin/env python
"""把「题干段落丢了、根本没法作答」的英语填空题隔离出去（status=archived），并留修复清单。

为什么先隔离而不是硬修
--------------------
这些题来自 hbzsb.com 的文章页，当年只抽到了「A.xx B.yy C.zz D.ww」这种选项串，
**段落正文没抽到**（页面里段落可能在表格/图片里）。没有段落就没有空位，任何前端改动都救不了，
用户点进去只能干瞪眼。先隔离，等按 HTML 重抽一次段落再放回来。

清单写到 `inbox/english/_quarantined.json`，修好后可以原样回滚（status 改回 approved）。

用法:
    python scripts/quarantine_english_broken.py            # dry-run
    python scripts/quarantine_english_broken.py --apply
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
MANIFEST = ROOT / "inbox" / "english" / "_quarantined.json"

FILL_TYPES = ("cloze", "word_fill", "dialogue", "reading_fill", "grammar_fill",
              "outline_fill", "sentence_completion", "translation_fill")
HAS_BLANK = re.compile(r"_{2,}|【\d")
HAS_INLINE = re.compile(r"[（(][^）)]{1,24}[/／][^）)]{1,24}[）)]")


def unanswerable(stem: str, material: str) -> bool:
    text = (stem or "") + "\n" + (material or "")
    if HAS_BLANK.search(text):
        return False
    # 题干自带「(in/to)」这种内联选项：位置有了，手打能答，不算坏
    if HAS_INLINE.search(stem or ""):
        return False
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    db = DATA / "english.sqlite"
    con = sqlite3.connect(str(db))
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT id, question_type, source_url, stem, material_text, options, answer, status "
        "FROM questions WHERE status<>'archived' AND question_type IN (%s) "
        "ORDER BY id" % ",".join("?" * len(FILL_TYPES)), FILL_TYPES).fetchall()

    hit = [r for r in rows if unanswerable(r["stem"], r["material_text"])]
    print(f"填空题 {len(rows)} 条 → 判定不可作答 {len(hit)} 条")
    print("  按题型：", dict(Counter(r["question_type"] for r in hit)))
    print("  按来源：", dict(Counter(re.sub(r"/article/.*$", "", r["source_url"] or "") for r in hit).most_common(6)))
    for r in hit[:8]:
        print(f"  id={r['id']:<5}{r['question_type']:<14}stem={(r['stem'] or '')[:56]!r}")
    if len(hit) > 8:
        print(f"  … 其余 {len(hit) - 8} 条同型")

    if not hit:
        print("没有需要隔离的题")
        con.close()
        return 0

    if not args.apply:
        print("\ndry-run：未写库（加 --apply 才隔离）")
        con.close()
        return 0

    conv = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "reason": "源页面只抽到选项串、段落正文缺失 → 无空位不可作答；修好后把 status 改回 approved 即可恢复",
        "count": len(hit),
        "ids": [r["id"] for r in hit],
        "items": [{"id": r["id"], "type": r["question_type"], "source_url": r["source_url"],
                   "stem": (r["stem"] or "")[:120], "answer": (r["answer"] or "")[:60]} for r in hit],
    }
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(conv, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n清单 → {MANIFEST}")

    try:
        con.executemany("UPDATE questions SET status='archived', reviewed_by='quarantine-missing-stem' "
                        "WHERE id=?", [(r["id"],) for r in hit])
        con.commit()
    finally:
        con.close()
    print(f"已隔离 {len(hit)} 条（status=archived, reviewed_by=quarantine-missing-stem）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
