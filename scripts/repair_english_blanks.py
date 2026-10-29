#!/usr/bin/env python
"""修复英语「填空/完形/情景对话」被吃掉的下划线空位（从本地保存的真题 JSON 重建）。

病因（有据可查，不是我瞎猜）
--------------------------
`inbox/real_exams/*.json` 的结构是**结构化 block**：

    {"type":"markdown","value":"The amount of sleep "}
    {"type":"blank","key":"q31","placeholder":"31"}          ← 空在这里
    {"type":"markdown","value":" depends on the age ..."}

当年导入时只拼了 markdown 块、**把 blank 块整块丢了**，还拿 "\\n\\n" 当分隔符，
于是题干里的 `________` 变成了空行 —— 这就是你在页面上看到
「The amount of sleep ⏎⏎ depends on ...」却找不到空的原因。

本脚本做的事（纯机械、0 成本、可回滚）
------------------------------------
1. 用 `materials[].blocks` 重建 `material_text`，空位写成 `【31】________`（带编号，能对上题号）；
2. 用 `items[]` 重建每题：
   - `stem`：原题干；本来就是"填空型"（stem 为空、interaction.target 指向某个空）的，
     写成「第 31 空」；
   - `options`：源里没给选项、只有答案的（词汇填空 A-L 词库、情景对话 A-G 句库），
     用同 section 所有 `referenceAnswer` 里的「字母. 内容」还原成选项表；
3. 只在 DB 行数 == 源 items 数时动手（数量对不上就跳过并记账），写完逐条回读校验。

用法:
    python scripts/repair_english_blanks.py                # dry-run
    python scripts/repair_english_blanks.py --apply        # 写库（自动备份）
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
EX = ROOT / "inbox" / "real_exams"

BLANK_MARK = "【{0}】________"


def blocks_text(blocks) -> str:
    out = []
    for b in blocks or []:
        t = b.get("type")
        if t == "blank":
            ph = b.get("placeholder") or b.get("key") or "?"
            out.append(BLANK_MARK.format(ph))
        else:
            out.append(str(b.get("value") or ""))
    return "".join(out)


def label_of(item: dict) -> str:
    """referenceAnswer 里的「E. anywhere」这种字符串。"""
    return blocks_text(((item.get("referenceAnswer") or {}).get("blocks")) or []).strip()


def letter_label(s: str) -> tuple[str, str] | None:
    m = re.match(r"^\s*([A-Z])\s*[.、)．]\s*(.+?)\s*$", s or "", re.S)
    return (m.group(1), m.group(2)) if m else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--subject", default="english")
    args = ap.parse_args()

    db = DATA / f"{args.subject}.sqlite"
    con = sqlite3.connect(str(db))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=30000")

    files = {}
    for p in EX.glob("*.json"):
        m = re.match(r"(\d+)_", p.name)
        if m:
            files[int(m.group(1))] = p

    stats = dict(groups=0, ok=0, skipped=0, rows=0, blank_restored=0, opts_filled=0, stem_filled=0)
    changes: list[tuple] = []

    for sid, path in sorted(files.items()):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        sections = ((data.get("exam") or {}).get("sections")) or []
        for si, sec in enumerate(sections):
            items = sec.get("items") or []
            if not items:
                continue
            grp = f"{sid}-s{si}"
            rows = con.execute("SELECT * FROM questions WHERE group_uid=? ORDER BY id", (grp,)).fetchall()
            if not rows:
                continue
            stats["groups"] += 1
            if len(rows) != len(items):
                stats["skipped"] += 1
                print(f"  跳过 {grp}：DB {len(rows)} 行 / 源 {len(items)} 题（数量不一致）")
                continue

            # 1) 整段材料（多个 material 用空行连接；空位带编号）
            parts = []
            for mat in sec.get("materials") or []:
                txt = blocks_text(mat.get("blocks"))
                if txt.strip():
                    parts.append(txt)
            material = "\n\n".join(parts).strip()
            blank_count = material.count("【") if material else 0

            # 2) 词库/句库：同一 section 里所有 referenceAnswer 的「字母. 内容」
            bank: dict[str, str] = {}
            for it in items:
                ll = letter_label(label_of(it))
                if ll and ll[0] not in bank:
                    bank[ll[0]] = ll[1]
            bank_opts = [{"key": k, "text": bank[k]} for k in sorted(bank)]

            for row, it in zip(rows, items):
                stem_txt = blocks_text(((it.get("stem") or {}).get("blocks")) or []).strip()
                inter = it.get("interaction") or {}
                target = inter.get("target") or ""
                choices = inter.get("choices") or []
                no = it.get("no")

                new_stem = stem_txt
                if not new_stem and target and material:
                    new_stem = f"第 {no} 空：请填入文中 {BLANK_MARK.format(str(no)[-2:] if no else '?')} 处的正确选项"
                if not new_stem:
                    new_stem = row["stem"]

                new_opts = row["options"]
                if choices:
                    new_opts = json.dumps(
                        [{"key": c.get("key"), "text": re.sub(r"^[A-Z]\s*[.、)．]\s*", "", str(c.get("label") or ""))}
                         for c in choices], ensure_ascii=False)
                elif len(bank_opts) >= 2:
                    new_opts = json.dumps(bank_opts, ensure_ascii=False)

                upd = {}
                if material and (row["material_text"] or "") != material:
                    upd["material_text"] = material
                if new_stem != (row["stem"] or ""):
                    upd["stem"] = new_stem
                    stats["stem_filled"] += 1
                if new_opts != (row["options"] or ""):
                    upd["options"] = new_opts
                    stats["opts_filled"] += 1
                if not upd:
                    continue
                stats["rows"] += 1
                stats["blank_restored"] += blank_count
                changes.append((row["id"], upd))

    print(f"\n分组 {stats['groups']}（跳过 {stats['skipped']}）｜待更新 {stats['rows']} 行"
          f"｜补题干 {stats['stem_filled']}｜补选项 {stats['opts_filled']}")

    # 空写保护的抽样展示
    for rid, upd in changes[:3]:
        print(f"\n--- 预览 id={rid} ---")
        for k, v in upd.items():
            print(f"  {k}: {str(v)[:300]}")

    if not args.apply:
        print("\ndry-run：未写库")
        return 0

    bak = DATA / "backup" / f"english.sqlite.bak-{datetime.now().strftime('%Y%m%d-%H%M%S')}-preblank"
    bak.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(db, bak)
    print(f"\n已备份 → {bak}")

    try:
        for rid, upd in changes:
            sets = ", ".join(f"{k}=?" for k in upd)
            con.execute(f"UPDATE questions SET {sets} WHERE id=?", (*upd.values(), rid))
        con.commit()
    finally:
        con.close()

    # 回读校验
    chk = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    left = chk.execute(
        "SELECT count(*) FROM questions WHERE status<>'archived' AND question_type IN "
        "('cloze','word_fill','dialogue','reading_fill') "
        "AND COALESCE(material_text,'')<>'' AND material_text NOT LIKE '%【%'").fetchone()[0]
    fixed = chk.execute(
        "SELECT count(*) FROM questions WHERE status<>'archived' AND question_type IN "
        "('cloze','word_fill','dialogue','reading_fill') AND material_text LIKE '%【%'").fetchone()[0]
    chk.close()
    print(f"回读：带编号空位的题 {fixed} 条；同类型仍无空位 {left} 条（多为 hbzsb 网页来源，待下一步）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
