#!/usr/bin/env python
"""**补回英语真题的选择题选项**（数据修复，零成本）。

## 问题（2026-10-13 实测）
英语真题里 **210 道单选/完形**的 `questions.options` 是空的，题干只有 `"It is essential that
every student \n\n a library card…"` 这样的空行 —— 也就是说**题面没有 A/B/C/D，用户没法选**。
根因：`scripts/import_real_exams.py:parse_v2()` 只从 `stem.blocks` + `answerSpec.values`
取题干与答案，**忽略了 `item.interaction.choices`**，而选项恰恰在那里：

    "interaction": {"type": "single_choice", "target": "b1",
                    "choices": [{"key": "A", "label": "A. has"}, {"key": "B", "label": "B. have"}, …]}

## 本脚本做什么
重读 `inbox/real_exams/*.json`，按 `group_uid`（= `f"{exam_id}-s{section_index}"`，与导入脚本同一规则）
定位数据库里那些**选项为空**的题，从 `interaction.choices` 生成
`options = [{"key":"A","text":"has"}, …]` 写回 `questions.options`。
`label` 里已含 `"A. "` 前缀 → 写库时剥掉（前端会自己拼 `key`）。

## 安全
- **只更新 `options` 为空的行**（已有的绝不覆盖）；只处理 `subject='english'`；
- 默认 dry-run，`--apply` 才写，写前自动备份到 `data/backup/`；
- 若一个 section 有多个 item（多空题），按 `no`/顺序对应到该 group 下的题；
  对不上的**跳过并计入 unmatched**（宁可少补也不乱补）。
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
BACKUP = DATA / "backup"
INBOX = ROOT / "inbox" / "real_exams"
DB = DATA / "english.sqlite"
LABEL_PREFIX = re.compile(r"^\s*[A-Ha-h]\s*[.、)．]\s*")


def choices_to_options(choices) -> list[dict]:
    """`interaction.choices` → `[{"key","text"}]`（剥掉 label 里的字母前缀）。"""
    out: list[dict] = []
    for c in choices or []:
        if not isinstance(c, dict):
            continue
        key = str(c.get("key") or "").strip().upper()
        label = str(c.get("label") or c.get("text") or c.get("value") or "").strip()
        text = LABEL_PREFIX.sub("", label).strip()
        if key and text:
            out.append({"key": key, "text": text})
    return out


def collect_from_exams() -> dict[str, list[dict]]:
    """{group_uid: [options…]} —— 一个 group 可能有多道题，按出现顺序排列。"""
    out: dict[str, list[list[dict]]] = {}
    for path in sorted(INBOX.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):     # 有的文件是裸数组（旧格式）→ 跳过
            continue
        exam = data.get("exam") or {}
        if not isinstance(exam, dict):
            continue
        sections = exam.get("sections")
        if not isinstance(sections, list):
            continue                      # 只有 v2（sections）结构有 interaction.choices
        for si, sec in enumerate(sections):
            if not isinstance(sec, dict):
                continue
            group = f"{data.get('id')}-s{si}"
            for item in sec.get("items") or []:
                if not isinstance(item, dict):
                    continue
                interaction = item.get("interaction") or {}
                opts = choices_to_options(interaction.get("choices"))
                if len(opts) >= 2:
                    out.setdefault(group, []).append(opts)
    return {k: v for k, v in out.items()}   # type: ignore[return-value]


def main() -> int:
    ap = argparse.ArgumentParser(description="补回英语真题选择题的选项（默认 dry-run）")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    found = collect_from_exams()
    total_groups = len(found)
    total_opts = sum(len(v) for v in found.values())
    print(f"原始真题里带 interaction.choices 的 section：{total_groups} 个，共 {total_opts} 道题有选项")

    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    rows = conn.execute(
        "SELECT question_uid, group_uid, COALESCE(options,'') AS options, question_type, "
        "COALESCE(stem,'') AS stem FROM questions WHERE subject='english' AND "
        "(options IS NULL OR options='' OR options='[]') ORDER BY group_uid, id").fetchall()
    empty = [dict(r) for r in rows]
    print(f"库内 english 选项为空的题：{len(empty)} 道")

    by_group: dict[str, list[dict]] = {}
    for r in empty:
        by_group.setdefault(str(r["group_uid"] or ""), []).append(r)

    plan, unmatched = [], []
    for group, qs in by_group.items():
        opts_list = found.get(group) or []
        if not opts_list:
            unmatched.append((group, len(qs), "原始 JSON 里没有该 group 的 choices"))
            continue
        if group == "":
            unmatched.append((group, len(qs), "库内 group_uid 为空，无法与原始 JSON 对齐"))
            continue
        # 按下标**前缀**匹配：一个 section 的 item 顺序与题目顺序一致。
        # 数量对不上时不整体放弃，能补几道补几道（剩下的照旧渲染成填空），
        # 但**绝不跨界**（多出来的题只报数，不乱套选项）。
        take = min(len(opts_list), len(qs))
        for q, opts in zip(qs[:take], opts_list[:take]):
            plan.append((q["question_uid"], opts, q["question_type"], q["stem"][:40]))
        if take < len(qs):
            unmatched.append((group, len(qs) - take,
                              f"库内比原始多 {len(qs) - take} 题（原始只有 {len(opts_list)} 组选项）"))
        elif take < len(opts_list):
            unmatched.append((group, len(opts_list) - take,
                              f"原始比库内多 {len(opts_list) - take} 组选项"))

    print(f"可补选项：{len(plan)} 道｜对不上而跳过：{len(unmatched)} 个 group")
    for group, n, why in unmatched[:6]:
        print(f"  [跳过] {group}（{n} 题）：{why}")

    if not args.apply:
        print("\n（dry-run：未写库）样例：")
        for uid, opts, qtype, stem in plan[:3]:
            print(f"  {uid} [{qtype}] {stem}… → " + " / ".join(f"{o['key']}.{o['text']}" for o in opts))
        conn.close()
        if args.json:
            print(json.dumps({"groups": total_groups, "planned": len(plan),
                              "unmatched": len(unmatched)}, ensure_ascii=False))
        return 0

    if plan:
        BACKUP.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        bak = BACKUP / f"english-{stamp}.sqlite"
        shutil.copy2(DB, bak)
        print(f"[备份] {bak.name}")
        for uid, opts, _qtype, _stem in plan:
            conn.execute("UPDATE questions SET options=? WHERE question_uid=?",
                         (json.dumps(opts, ensure_ascii=False), uid))
        conn.commit()
        print(f"[已改库] 补回 {len(plan)} 道题的选项")

    left = conn.execute(
        "SELECT count(*) FROM questions WHERE subject='english' AND status='approved' "
        "AND question_type IN ('single_choice','multiple_choice','cloze','word_fill',"
        "'phonetics','dialogue','translation_choice') AND "
        "(options IS NULL OR options='' OR options='[]')").fetchone()[0]
    conn.close()
    print(f"仍缺选项的客观题：{left} 道（含 interaction 里本来就没选项的题型）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
