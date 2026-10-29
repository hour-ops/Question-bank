#!/usr/bin/env python
"""题库去重：同一科目库内「题干 + 题型 + 答案」完全相同的题只留一条，其余下架。

背景（实测，2026-10-13）：考试宝那套「阿里云大模型aca认证题库」标称 144 题，
但**题干规范化后只有 81 道不同题**（49 组重复、63 条冗余）；导入库内的 129 条里
唯一题干只有 70 条、冗余 59 条 —— 也就是刷题池里约 21% 是重复题。
重复组的 `answer` 全部一致（0 组冲突），所以按题干去重是安全的。

判重口径（**保守，宁可漏判不可错删**）：
  1. `stem` 去掉空白/中英文标点后**完全相同**；
  2. 且 `question_type` 相同；
  3. 且 `answer` 相同（字母排序后比较）；
  4. 且 `options` 归一化后**完全相同**（题干相同但选项不同的，是两个不同题）。
  任一不满足 → 视为不同题，不动。
  另外单独统计「题干+题型相同但答案不同」的组（`--json` 里 `answer_conflicts`），一律跳过。

保留策略（同组内排序，留第一个）：
  ① `status` 优先级 approved > pending_review > raw > rejected（别把已审核的换成待审核的）；
  ② 被引用次数多的（`wrong_book` + `review_log`，避免把有作答记录的题下架）；
  ③ `explanation` 更长的（信息更全）；
  ④ `options` 条数更多的；
  ⑤ `id` 更小的（稳定、可复现）。

写库契约（项目硬性约束，见 AGENTS/交接简报第 3 节）：
  - 本脚本**只写 `questions` 的 `status` / `reviewed_by` / `version`**；
  - `wrong_book` / `review_log` / `daily_progress` **一行都不碰**（只读来做引用计数）；
  - 默认 dry-run，`--apply` 才写；写前自动备份到 `data/backup/`，
    并写一份可回滚清单 `data/backup/dedupe-<时间戳>.json`。

用法:
    python scripts/dedupe_questions.py                          # dry-run，aca_llm
    python scripts/dedupe_questions.py --subject all            # dry-run，四个库都体检
    python scripts/dedupe_questions.py --apply                   # 真改库（aca_llm）
    python scripts/dedupe_questions.py --apply --subject all
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
BACKUP = DATA / "backup"
SUBJECTS = ("english", "c_wuhan", "c_hbpu", "aca_llm")

ARCHIVED = "archived"
STATUS_RANK = {"approved": 0, "pending_review": 1, "raw": 2, "rejected": 3}
_NORM_RE = re.compile(r"[\s\u3000，。、；：？！“”‘’（）()【】\[\]《》,.;:?!\"'*]+")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def norm_stem(text: str) -> str:
    return _NORM_RE.sub("", text or "")


def norm_answer(text: str) -> str:
    return "".join(sorted({ch for ch in re.sub(r"[^A-Za-z]", "", str(text or "")).upper()}))


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
    return bool(row)


def reference_counts(conn: sqlite3.Connection) -> dict[str, int]:
    """question_uid → 被引用次数（wrong_book + review_log）。只读。"""
    counts: dict[str, int] = {}
    for table in ("wrong_book", "review_log"):
        if not table_exists(conn, table):
            continue
        try:
            for uid, n in conn.execute(f"SELECT question_uid, COUNT(*) FROM {table} GROUP BY question_uid"):
                counts[uid] = counts.get(uid, 0) + int(n or 0)
        except sqlite3.Error:
            continue
    return counts


def load_rows(conn: sqlite3.Connection) -> list[dict]:
    rows = []
    for r in conn.execute(
        "SELECT id, question_uid, COALESCE(question_type,'') AS question_type, "
        "COALESCE(stem,'') AS stem, COALESCE(answer,'') AS answer, "
        "COALESCE(explanation,'') AS explanation, COALESCE(options,'') AS options, "
        "COALESCE(status,'') AS status, COALESCE(trust_level,'') AS trust_level, "
        "COALESCE(exam_title,'') AS exam_title "
        "FROM questions ORDER BY id"
    ):
        rows.append(dict(r))
    return rows


def option_count(raw) -> int:
    try:
        arr = json.loads(raw) if isinstance(raw, str) else raw
        return len(arr) if isinstance(arr, list) else 0
    except (TypeError, ValueError):
        return 0


def norm_options(raw) -> str:
    """选项归一化：`[{key,text}]` / `[{"Key","Value"}]` / 逗号串都压成同一种形式。

    只比较「字母 + 文本」，忽略字段名大小写与 JSON 序列化细节。
    """
    try:
        arr = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        arr = None
    if isinstance(arr, list) and arr:
        parts = []
        for item in arr:
            if isinstance(item, dict):
                key = str(item.get("key") or item.get("Key") or "").strip().upper()
                text = str(item.get("text") or item.get("Value") or item.get("value") or "").strip()
                parts.append(f"{key}={_NORM_RE.sub('', text)}")
            else:
                parts.append(_NORM_RE.sub("", str(item)))
        return "|".join(parts)
    return _NORM_RE.sub("", str(raw or ""))


def keeper_key(row: dict, refs: dict[str, int]):
    return (
        STATUS_RANK.get(row["status"], 9),
        -refs.get(row["question_uid"], 0),
        -len(row["explanation"] or ""),
        -option_count(row["options"]),
        int(row["id"]),
    )


def plan_subject(subj: str) -> tuple[dict, list[tuple[int, int]], list[dict]]:
    path = DATA / f"{subj}.sqlite"
    if not path.exists():
        return {"subject": subj, "skipped": "库不存在"}, [], []

    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = load_rows(conn)
        refs = reference_counts(conn)
    finally:
        conn.close()

    live = [r for r in rows if r["status"] != ARCHIVED]
    by_stem: dict[tuple, list[dict]] = {}
    for r in live:
        by_stem.setdefault((norm_stem(r["stem"]), r["question_type"]), []).append(r)

    groups: dict[tuple, list[dict]] = {}
    answer_conflicts: list[dict] = []
    option_splits = 0          # 题干相同、答案相同，但选项不同 → 不同题
    for (stem_norm, qtype), members in by_stem.items():
        # 题干相同但答案不同：说明是"同一段材料下的不同小题"或数据本身冲突 → 整组不动
        if len(members) > 1 and len({norm_answer(m["answer"]) for m in members}) > 1:
            answer_conflicts.append({
                "question_type": qtype,
                "stem": (members[0]["stem"] or "")[:60],
                "ids": [m["id"] for m in members],
                "answers": [m["answer"] for m in members],
            })
            continue
        for m in members:
            # 单题也要进 groups，否则 unique_questions 会少算（曾经踩过）
            groups.setdefault((stem_norm, qtype, norm_options(m["options"])), []).append(m)
        if len(members) > 1 and len({norm_options(m["options"]) for m in members}) > 1:
            option_splits += 1

    archive_plan: list[tuple[int, int]] = []   # (要下架的 id, 保留的 id)
    for (stem_norm, qtype, _opts), members in groups.items():
        if len(members) < 2:
            continue
        if all(m["status"] == "rejected" for m in members):
            continue                      # 整组都已下架，不用再清
        members_sorted = sorted(members, key=lambda m: keeper_key(m, refs))
        keep = members_sorted[0]
        for drop in members_sorted[1:]:
            archive_plan.append((int(drop["id"]), int(keep["id"])))

    stats = {
        "subject": subj,
        "total": len(rows),
        "live": len(live),
        "unique_questions": len(groups),
        "dup_groups": sum(1 for v in groups.values() if len(v) > 1),
        "redundant_rows": len(archive_plan),
        "answer_conflicts": len(answer_conflicts),
        "option_splits": option_splits,
    }
    return stats, archive_plan, answer_conflicts


def backup_db(path: Path) -> Path:
    BACKUP.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = BACKUP / f"{path.stem}-{stamp}{path.suffix}"
    src = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    dst = sqlite3.connect(str(target))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return target


def main() -> int:
    ap = argparse.ArgumentParser(description="同库内按题干去重，重复题下架为 archived（默认 dry-run）")
    ap.add_argument("--subject", default="aca_llm", help="科目名，或 all")
    ap.add_argument("--apply", action="store_true", help="真改库（先自动备份到 data/backup/）")
    ap.add_argument("--json", action="store_true", help="输出 JSON 报告")
    ap.add_argument("--data-dir", default="", help="只改这个数据目录下的库（默认 题库项目/data）")
    args = ap.parse_args()

    if args.data_dir:
        global DATA, BACKUP
        DATA = Path(args.data_dir)
        BACKUP = DATA / "backup"
        print(f"[data-dir] {DATA}")

    subjects = list(SUBJECTS) if args.subject == "all" else [args.subject]
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    report: dict = {"applied_at": None if not args.apply else now_iso(), "subjects": {}, "conflicts": {}}

    for subj in subjects:
        stats, plan, conflicts = plan_subject(subj)
        report["subjects"][subj] = stats
        if conflicts:
            report["conflicts"][subj] = conflicts
        print(f"===== {subj}")
        if stats.get("skipped"):
            print(f"  跳过：{stats['skipped']}")
            continue
        print(f"  总行数 {stats['total']}，未下架 {stats['live']}，唯一题（题干+题型+答案+选项）{stats['unique_questions']}")
        print(f"  重复组 {stats['dup_groups']}，可下架 {stats['redundant_rows']} 行"
              f"（剩余 {stats['live'] - stats['redundant_rows']} 行）")
        if stats["option_splits"]:
            print(f"  ℹ️ 题干+答案相同但选项不同、按不同题处理的：{stats['option_splits']} 组")
        if stats["answer_conflicts"]:
            print(f"  ⚠️ 答案冲突、已跳过的组：{stats['answer_conflicts']}（宁可留重复也不动）")
            for c in conflicts[:3]:
                print(f"      · ids={c['ids']} answers={c['answers']} {c['stem']!r}")

        if not args.apply or not plan:
            continue

        path = DATA / f"{subj}.sqlite"
        bak = backup_db(path)
        print(f"  [备份] {bak.name}")
        conn = sqlite3.connect(str(path))
        conn.execute("PRAGMA busy_timeout=30000")
        try:
            ts = now_iso()
            for drop_id, keep_id in plan:
                conn.execute(
                    "UPDATE questions SET status=?, reviewed_by=?, version=COALESCE(version,1)+1 "
                    "WHERE id=?",
                    (ARCHIVED, f"auto:dedupe_questions@{ts} | dup_of_id={keep_id}", drop_id),
                )
            conn.commit()
        finally:
            conn.close()
        undo = BACKUP / f"dedupe-{subj}-{stamp}.json"
        undo.write_text(json.dumps({
            "subject": subj, "applied_at": now_iso(), "archived": [
                {"id": d, "kept_id": k} for d, k in plan
            ],
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  [已改库] 下架 {len(plan)} 行；回滚清单 {undo.name}")

    if args.apply:
        log = BACKUP / f"dedupe-report-{stamp}.json"
        log.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n报告：{log}")
    else:
        print("\n（dry-run：未改任何库。加 --apply 才写入，写入前会自动备份到 data/backup/）")
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
