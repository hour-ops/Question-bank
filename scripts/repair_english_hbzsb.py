#!/usr/bin/env python
"""从**本地保存的 hbzsb 网页**恢复「只抽到选项串、段落丢了」的英语阅读填空/语法填空。

现场证据（`inbox/english/0140b7d01657.html`）：
    段落里是  `Most of us develop poor reading __4__ at an early age ...`
    选项在下面 `1.A.applying B.doing C.offering D.getting`
说明段落**一直都在本地**，只是当年导入时只抓了选项行、把段落漏了。

本脚本：
1. 扫描所有保存的 html，建两张索引：
   - 选项串（去空白小写）→ (文件, 题号)
   - 文件 → 含 `__N__` 的段落正文
2. 拿 DB 里 stem 形如 `A.applying B.doing C.offering D.getting` 的行去索引里查：
   命中就回填 `material_text`（带 `【N】________` 空位）、`stem`（第 N 空）、`options`。

用法:
    python scripts/repair_english_hbzsb.py             # dry-run
    python scripts/repair_english_hbzsb.py --apply
"""

from __future__ import annotations

import argparse
import html as htmlmod
import json
import re
import shutil
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
PAGES = ROOT / "inbox" / "english"

OPT_LINE = re.compile(r"^\s*(\d{1,2})\s*[.、]\s*([A-D])\s*[.．]")
BLANK = re.compile(r"_{1,4}\s?(\d{1,2})\s?_{0,4}")


def norm_key(s: str) -> str:
    return re.sub(r"[\s.．、]+", "", (s or "").lower())


def paras(text: str) -> list[str]:
    """把 html 拆成 <p> 块的纯文本（保留顺序）。"""
    out = []
    for m in re.finditer(r"<p[^>]*>(.*?)</p>", text, re.S):
        t = re.sub(r"<[^>]+>", "", m.group(1))
        t = htmlmod.unescape(t).replace("\u00a0", " ").strip()
        if t:
            out.append(t)
    return out


def build_index() -> tuple[dict, dict]:
    opt_index: dict[str, tuple[str, int]] = {}
    passages: dict[str, str] = {}
    for p in PAGES.glob("*.html"):
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        blocks = paras(text)
        if not blocks:
            continue
        blank_blocks = [b for b in blocks if BLANK.search(b) and re.search(r"[A-Za-z]", b)]
        if blank_blocks:
            passages[p.name] = "\n\n".join(blank_blocks)
        cur = None
        for b in blocks:
            m = OPT_LINE.match(b)
            if m:
                cur = (b, int(m.group(1)))
                key = re.sub(r"^\s*\d{1,2}\s*[.、]\s*", "", b)   # 去掉行首题号再当键
                opt_index.setdefault(norm_key(key), (p.name, cur[1]))
            elif cur and len(b) < 80 and b.lower().startswith(("a.", "a．")):
                opt_index.setdefault(norm_key(b), (p.name, cur[1]))
    return opt_index, passages


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    opt_index, passages = build_index()
    print(f"索引：选项串 {len(opt_index)} 条｜含空位的段落 {len(passages)} 篇")

    db = DATA / "english.sqlite"
    con = sqlite3.connect(str(db))
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT id, question_type, source_url, stem, material_text, options, answer FROM questions "
        "WHERE status<>'archived' AND question_type IN ('reading_fill','grammar_fill','cloze','word_fill') "
        "AND COALESCE(material_text,'')='' AND stem LIKE 'A.%' ORDER BY id").fetchall()
    print(f"待修：{len(rows)} 行（stem 只有选项串、段落为空）")

    upd = []
    miss = []
    for r in rows:
        hit = opt_index.get(norm_key(r["stem"]))
        if not hit:
            miss.append(r)
            continue
        fname, no = hit
        passage = passages.get(fname) or ""
        if not passage:
            miss.append(r)
            continue
        # 段落里的 __4__ → 【4】________
        passage = BLANK.sub(lambda m: "【%s】________" % m.group(1), passage)
        # 选项从自己的 stem 解析（A.applying B.doing …）
        parts = re.split(r"\s*(?=[A-D][.．])", r["stem"].strip())
        opts = []
        for p in parts:
            m = re.match(r"([A-D])[.．]\s*(.+)", p.strip(), re.S)
            if m:
                opts.append({"key": m.group(1), "text": m.group(2).strip()})
        if len(opts) != 4:
            parts2 = re.split(r"\s+(?=[A-D][.．])", r["stem"].strip())
            opts = []
            for p in parts2:
                m = re.match(r"([A-D])[.．]\s*(.+)", p.strip(), re.S)
                if m:
                    opts.append({"key": m.group(1), "text": m.group(2).strip()})
        if len(opts) != 4:
            miss.append(r)
            continue
        upd.append((r["id"], {
            "material_text": passage,
            "stem": f"第 {no} 空：从 A/B/C/D 中选出最适合填在文中 【{no}】 处的词",
            "options": json.dumps(opts, ensure_ascii=False),
        }, r["question_type"], fname, no))

    print(f"可修 {len(upd)} 行｜查不到 {len(miss)} 行")
    print("  命中来源文件数：", len({u[3] for u in upd}))
    for rid, d, qt, fn, no in upd[:3]:
        print(f"\n--- 预览 id={rid} ({qt}) ← {fn} 第 {no} 空 ---")
        print("  stem:", d["stem"])
        print("  mat:", d["material_text"][:220].replace("\n", " ⏎ "))
        print("  opts:", d["options"][:160])

    if not args.apply:
        print("\ndry-run：未写库")
        con.close()
        return 0
    if not upd:
        print("没有可修的，退出")
        con.close()
        return 1

    bak = DATA / "backup" / f"english.sqlite.bak-{datetime.now().strftime('%Y%m%d-%H%M%S')}-prehbzsb"
    bak.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(db, bak)
    print(f"\n已备份 → {bak}")
    try:
        for rid, d, *_ in upd:
            con.execute("UPDATE questions SET material_text=?, stem=?, options=? WHERE id=?",
                        (d["material_text"], d["stem"], d["options"], rid))
        con.commit()
    finally:
        con.close()
    print(f"已回填 {len(upd)} 行段落/空位/选项")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
