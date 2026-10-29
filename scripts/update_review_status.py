#!/usr/bin/env python
"""阶段 5b · 人工审核回写：把 output/review_queue.md 的人工决策落回科目库。

用法:
    python scripts/update_review_status.py output/review_queue.md [--dry-run] [--root <项目根>]

输入（由 validate_and_fill.py 生成的 Markdown 表格）:
    | question_uid | subject | status_snapshot | decision | reason |
    - decision: 通过 / 拒绝 / 修改（也接受 approve / reject / edit）
    - reason:   仅「拒绝」时必填，取值 ∈ 答案错误 / 来源不可信 / 表述歧义 / 重复题 / 超纲 / 格式问题 / 其他

规则（见 DESIGN.md 第 8 / 15 节、决策记录第 6 节第 11 条）:
  1. 通过 → `status='approved'`；拒绝 → `'rejected'`；修改 → 保持 `'pending_review'`（人工改完再审）。
  2. **快照校验（硬要求）**：`status_snapshot` 必须等于库中当前 `status`，否则**拒绝更新该行**
     → 计入 `conflicts` 并在报告中列出（防人工误改 uid / 状态竞争）。写库时 WHERE 再带一次快照，
     行数 ≠1 同样按冲突处理。
  3. 每次成功动作（同一事务）：写 `review_log(question_uid, reviewed_at, result)` +
     `questions.reviewed_by='human'` + `version = version + 1`。
     `result` = 审核后的 status（`approved` / `rejected` / `pending_review`）。
  4. 拒绝原因写 `logs/review_rejects.jsonl`（JSONL，一行一条：ts/question_uid/subject/reason）。
     ⚠️ **绝对不写 `config/distractors.json`** —— 那是干扰项库，与拒绝原因语义不同，混写即错误。
  5. `question_uid` 不在库中 → `missing`；表格畸形行 → `invalid`；两者都**不中断**执行。
  6. 所有 sqlite 连接：`PRAGMA journal_mode=WAL` + `busy_timeout=30000`。
  7. `--dry-run`：只报告将执行的动作，**不写任何库 / 日志**。

输出：JSON 汇总 `{updated, conflicts, missing, invalid, dry_run}`（明细以中文报告打印）。
退出码：0 正常；2 用法 / 文件 / 表头错误。
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

SUBJECTS = ("english", "c_wuhan", "c_hbpu", "aca_llm")
CANONICAL_COLUMNS = ("question_uid", "subject", "status_snapshot", "decision", "reason")

# 决策：中文 / 英文别名 → 归一化
DECISION_ALIASES = {
    "通过": "approve", "批准": "approve", "同意": "approve",
    "approve": "approve", "approved": "approve", "pass": "approve", "ok": "approve",
    "拒绝": "reject", "驳回": "reject",
    "reject": "reject", "rejected": "reject", "deny": "reject",
    "修改": "edit", "编辑": "edit", "待改": "edit",
    "edit": "edit", "edited": "edit", "revise": "edit",
}
DECISION_TO_STATUS = {"approve": "approved", "reject": "rejected", "edit": "pending_review"}

# 拒绝原因（下拉枚举）
REJECT_REASONS = ("答案错误", "来源不可信", "表述歧义", "重复题", "超纲", "格式问题", "其他")
_REASON_SEPS = ("：", ":", "，", ",", "、", "/", "-", "—", " ", "（", "(", "；", ";")

_SEP_RE = re.compile(r"^:?-+:?$")

COLUMN_ALIASES = {
    "question_uid": ("questionuid", "uid", "questionid", "qid", "题号", "题目id", "题目编号"),
    "subject": ("subject", "科目", "学科"),
    "status_snapshot": ("statussnapshot", "snapshot", "status", "状态", "状态快照", "快照"),
    "decision": ("decision", "决策", "审核结论", "审核结果", "结论", "决定"),
    "reason": ("reason", "原因", "拒绝原因", "理由"),
}

REVIEW_LOG_DDL = (
    "CREATE TABLE IF NOT EXISTS review_log ("
    "id INTEGER PRIMARY KEY, question_uid TEXT, reviewed_at TEXT, result TEXT)"
)


# --------------------------------------------------------------------------- 工具


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def force_utf8_stdout() -> None:
    """Windows 管道下默认是 GBK，会让报告里的中文/JSON 崩掉或乱码。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):  # pragma: no cover
            pass


def normalize_cell(raw: str) -> str:
    """去空白 / 反引号 / 粗体标记 / 首尾引号（md 表格里常见的装饰）。"""
    s = (raw or "").strip()
    s = s.strip("`").strip()
    if len(s) > 4 and s.startswith("**") and s.endswith("**"):
        s = s[2:-2].strip()
    s = s.strip("`").strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'“”‘’":
        s = s[1:-1].strip()
    return s


def _key(s: str) -> str:
    return re.sub(r"[\s`*_\-]+", "", (s or "").lower())


def split_row(line: str) -> list[str]:
    """按 `|` 切分表格行；`\\|` 视为单元格内的字面竖线。"""
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|") and not body.endswith("\\|"):
        body = body[:-1]
    cells: list[str] = []
    buf: list[str] = []
    i = 0
    while i < len(body):
        ch = body[i]
        if ch == "\\" and i + 1 < len(body) and body[i + 1] == "|":
            buf.append("|")
            i += 2
            continue
        if ch == "|":
            cells.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    cells.append("".join(buf))
    return [c.strip() for c in cells]


def is_separator_row(cells: list[str]) -> bool:
    return bool(cells) and all(_SEP_RE.match(c or "") for c in cells)


def is_table_row(line: str) -> bool:
    return line.lstrip().startswith("|")


def normalize_decision(raw: str) -> str | None:
    return DECISION_ALIASES.get(_key(raw).replace("（", "").replace("）", ""))


def match_reject_reason(raw: str) -> str | None:
    """返回命中的规范原因；`其他：xxx` 这类带补充说明的写法也接受（保留原文入日志）。"""
    s = normalize_cell(raw)
    if not s:
        return None
    for r in REJECT_REASONS:
        if s == r:
            return r
    for r in REJECT_REASONS:
        if s.startswith(r) and len(s) > len(r) and s[len(r)] in _REASON_SEPS:
            return r
    return None


def resolve_queue_path(queue_path: str | Path, root: Path) -> Path:
    p = Path(queue_path)
    if not p.is_absolute():
        cand = Path.cwd() / p
        if not cand.exists() and (root / p).exists():
            cand = root / p
        p = cand
    return p


# --------------------------------------------------------------------------- 解析


def resolve_columns(header_cells: list[str]) -> dict[str, int]:
    """表头 → {列名: 索引}；识别不了（无表头）时返回固定列序。"""
    idx: dict[str, int] = {}
    for i, cell in enumerate(header_cells):
        k = _key(cell)
        for col, aliases in COLUMN_ALIASES.items():
            if col in idx:
                continue
            if k in (_key(a) for a in aliases):
                idx[col] = i
                break
    if "question_uid" not in idx:
        return {}  # 视为无表头 → 固定列序
    missing = [c for c in ("subject", "status_snapshot", "decision") if c not in idx]
    if missing:
        raise ValueError(f"表头缺列: {', '.join(missing)}（表头: {' | '.join(header_cells)}）")
    return idx


def parse_queue(path: Path) -> tuple[list[dict], list[dict]]:
    """解析审核队列 → (有效行, 无效行)。容错：忽略表头 / 分隔行 / 空行 / 非表格行。"""
    text = Path(path).read_text(encoding="utf-8-sig")
    rows: list[dict] = []
    invalid: list[dict] = []
    columns: dict[str, int] = {}

    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or not is_table_row(line):
            continue  # 空行 / 非表格行（标题、说明文字）→ 直接忽略
        cells = split_row(line)
        if is_separator_row(cells):
            continue  # |---|---| 分隔行
        stripped = [normalize_cell(c) for c in cells]

        if not columns:
            keys = [_key(c) for c in stripped]
            if any(k in ("questionuid", "uid", "questionid", "qid", "题号") for k in keys):
                columns = resolve_columns(stripped)  # 表头行本身不产出数据
                continue
            columns = {c: i for i, c in enumerate(CANONICAL_COLUMNS)}  # 无表头 → 固定列序

        row: dict = {"line": lineno}
        for col in CANONICAL_COLUMNS:
            i = columns.get(col, -1)
            row[col] = stripped[i] if 0 <= i < len(stripped) else ""
        row["raw"] = line[:160]

        # --- 列数不足（连 4 个必填列都凑不齐）→ invalid
        if len(stripped) < 4:
            invalid.append({**row, "error": f"列数不足（{len(stripped)} 列，至少需 4 列）"})
            continue
        if not row["question_uid"]:
            invalid.append({**row, "error": "question_uid 为空"})
            continue
        subject = row["subject"].lower()
        if subject not in SUBJECTS:
            invalid.append({**row, "error": f"未知 subject: {row['subject'] or '(空)'}"})
            continue
        row["subject"] = subject
        if not row["status_snapshot"]:
            invalid.append({**row, "error": "status_snapshot 为空（无法做快照校验）"})
            continue

        # 未填写 decision = 人工**尚未审核**该行 → 跳过，**不计入 invalid**
        # （invalid 应只表示"行本身有问题"；把 292 行未审的全叫 invalid 会误导审核者）
        if not (row["decision"] or "").strip():
            row["decision"] = "skip"
            row["reason_key"] = ""
            rows.append(row)
            continue

        decision = normalize_decision(row["decision"])
        if decision is None:
            invalid.append({**row, "error": f"未知 decision: {row['decision'] or '(空)'}"})
            continue
        row["decision"] = decision

        if decision == "reject":
            if not row["reason"]:
                invalid.append({**row, "error": "拒绝必须填 reason"})
                continue
            reason = match_reject_reason(row["reason"])
            if reason is None:
                invalid.append({**row, "error": f"拒绝原因不在枚举内: {row['reason']}"})
                continue
            row["reason_key"] = reason
        else:
            row["reason_key"] = ""
        rows.append(row)

    if not columns and not rows and not invalid:
        raise ValueError("未找到任何 Markdown 表格行")
    return rows, invalid


# --------------------------------------------------------------------------- 落库


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def append_reject_log(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def apply_reviews(rows: list[dict], invalid: list[dict], dry_run: bool, root: Path) -> dict:
    data_dir = root / "data"
    rejects_log = root / "logs" / "review_rejects.jsonl"
    result: dict = {
        "updated": 0, "conflicts": 0, "missing": 0, "invalid": len(invalid), "dry_run": bool(dry_run),
        "applied": [], "conflict_rows": [], "missing_rows": [], "invalid_rows": invalid, "warnings": [],
    }

    conns: dict[str, sqlite3.Connection | None] = {}

    def conn_for(subject: str):
        if subject in conns:
            return conns[subject]
        db_path = data_dir / f"{subject}.sqlite"
        if not db_path.exists():
            conns[subject] = None
            return None
        try:
            c = connect(db_path)
            has_tbl = c.execute(
                "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='questions'"
            ).fetchone()[0]
        except sqlite3.Error as exc:  # 库损坏 / 打不开
            result["warnings"].append(f"{db_path.name}: {exc}")
            conns[subject] = None
            return None
        if not has_tbl:
            c.close()
            conns[subject] = None
            return None
        if not dry_run:
            c.execute(REVIEW_LOG_DDL)
            c.commit()
        conns[subject] = c
        return c

    try:
        for row in rows:
            subject = row["subject"]
            uid = row["question_uid"]
            snapshot = row["status_snapshot"]
            decision = row["decision"]
            if decision == "skip":
                # 人工尚未填写 decision → 跳过（独立计数，不进 invalid，也不进 5 键 JSON）
                result["skipped_unfilled"] = result.get("skipped_unfilled", 0) + 1
                continue
            new_status = DECISION_TO_STATUS[decision]

            conn = conn_for(subject)
            if conn is None:
                result["invalid"] += 1
                result["invalid_rows"].append(
                    {**row, "error": f"科目库不可用: data/{subject}.sqlite（不存在或缺 questions 表）"}
                )
                continue

            found = conn.execute(
                "SELECT status FROM questions WHERE question_uid=?", (uid,)
            ).fetchone()
            if found is None:
                result["missing"] += 1
                result["missing_rows"].append(
                    {"line": row["line"], "question_uid": uid, "subject": subject}
                )
                continue

            actual = found[0]
            if actual != snapshot:
                result["conflicts"] += 1
                result["conflict_rows"].append(
                    {"line": row["line"], "question_uid": uid, "subject": subject,
                     "snapshot": snapshot, "actual": actual, "decision": decision}
                )
                continue

            if dry_run:
                result["updated"] += 1
                result["applied"].append(
                    {"line": row["line"], "question_uid": uid, "subject": subject,
                     "decision": decision, "from": actual, "to": new_status,
                     "reason": row.get("reason_key") or "", "dry_run": True}
                )
                continue

            # 写库：WHERE 再带一次快照，防读-写之间被改动
            with conn:
                cur = conn.execute(
                    "UPDATE questions SET status=?, reviewed_by='human', "
                    "version=COALESCE(version,0)+1 WHERE question_uid=? AND status=?",
                    (new_status, uid, snapshot),
                )
                if cur.rowcount != 1:
                    changed = conn.execute(
                        "SELECT status FROM questions WHERE question_uid=?", (uid,)
                    ).fetchone()
                    result["conflicts"] += 1
                    result["conflict_rows"].append(
                        {"line": row["line"], "question_uid": uid, "subject": subject,
                         "snapshot": snapshot, "actual": (changed[0] if changed else None),
                         "decision": decision, "note": "写库时快照已变化"}
                    )
                    continue
                conn.execute(
                    "INSERT INTO review_log(question_uid, reviewed_at, result) VALUES(?,?,?)",
                    (uid, now_iso(), new_status),
                )

            result["updated"] += 1
            result["applied"].append(
                {"line": row["line"], "question_uid": uid, "subject": subject,
                 "decision": decision, "from": actual, "to": new_status,
                 "reason": row.get("reason_key") or "", "dry_run": False}
            )

            if decision == "reject":
                try:
                    append_reject_log(rejects_log, {
                        "ts": now_iso(), "question_uid": uid, "subject": subject,
                        "reason": row["reason"],
                    })
                except OSError as exc:  # 日志写失败不吞掉已完成的库更新
                    result["warnings"].append(f"review_rejects.jsonl 写入失败: {exc}")
    finally:
        for c in conns.values():
            if c is not None:
                c.close()

    return result


def run(queue_path: str | Path, dry_run: bool = False, root: str | Path | None = None) -> dict:
    root_path = Path(root) if root else ROOT
    qp = resolve_queue_path(queue_path, root_path)
    if not qp.exists():
        raise FileNotFoundError(f"审核队列文件不存在: {qp}")
    rows, invalid = parse_queue(qp)
    result = apply_reviews(rows, invalid, dry_run, root_path)
    result["queue_path"] = str(qp)
    result["parsed_rows"] = len(rows)
    return result


# --------------------------------------------------------------------------- CLI


def print_report(result: dict) -> None:
    flag = "  [DRY-RUN]" if result["dry_run"] else ""
    print(f"=== 人工审核回写报告{flag} ===")
    print(f"输入: {result.get('queue_path', '-')}")
    print(f"解析: 有效行 {result.get('parsed_rows', 0)}，无效行 {result['invalid']}")
    print(f"结果: updated={result['updated']} conflicts={result['conflicts']} "
          f"missing={result['missing']} invalid={result['invalid']}")

    if result["applied"]:
        print("\n-- 将执行 / 已执行 --" if result["dry_run"] else "\n-- 已执行 --")
        for a in result["applied"]:
            tail = f" 原因={a['reason']}" if a.get("reason") else ""
            prefix = "[dry-run] " if a.get("dry_run") else ""
            print(f"  {prefix}行{a['line']} {a['question_uid']} ({a['subject']}): "
                  f"{a['from']} → {a['to']}{tail}")
    if result["conflict_rows"]:
        print("\n-- 冲突（快照不符，已拒绝更新）--")
        for c in result["conflict_rows"]:
            print(f"  行{c['line']} {c['question_uid']} ({c['subject']}): "
                  f"快照 {c['snapshot']} ≠ 库中 {c['actual']}")
    if result["missing_rows"]:
        print("\n-- 缺失（uid 不在库中，已跳过）--")
        for m in result["missing_rows"]:
            print(f"  行{m['line']} {m['question_uid']} ({m['subject']})")
    if result["invalid_rows"]:
        print("\n-- 无效行（已跳过）--")
        for v in result["invalid_rows"]:
            print(f"  行{v['line']} {v.get('question_uid') or '-'}: {v['error']}")
    for w in result.get("warnings", []):
        print(f"  [warn] {w}")


def main(argv: list[str] | None = None) -> int:
    force_utf8_stdout()
    ap = argparse.ArgumentParser(
        description="把 output/review_queue.md 的人工审核决策回写到科目库（不触碰 config/distractors.json）"
    )
    ap.add_argument("queue", help="Markdown 审核队列，如 output/review_queue.md")
    ap.add_argument("--dry-run", action="store_true", help="只打印将执行的动作，不写库/日志")
    ap.add_argument("--root", default=None, help="项目根目录（默认脚本上级目录；测试用）")
    args = ap.parse_args(argv)

    try:
        result = run(args.queue, args.dry_run, args.root)
    except FileNotFoundError as exc:
        print(f"[错误] {exc}")
        return 2
    except ValueError as exc:
        print(f"[错误] 审核队列解析失败: {exc}")
        return 2

    print_report(result)
    summary = {k: result[k] for k in ("updated", "conflicts", "missing", "invalid", "dry_run")}
    print("\n=== 汇总 (JSON) ===")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
