#!/usr/bin/env python
"""update_review_status.py 离线测试 —— **不联网、零 API 花费**。

覆盖：
  ① 通过 → approved           ② 拒绝 → rejected + logs/review_rejects.jsonl
  ③ 快照冲突 → 跳过 + conflicts ④ uid 不存在 → missing
  ⑤ 畸形行 → invalid           ⑥ --dry-run 不落库

⚠️ 不使用 tempfile.TemporaryDirectory()：本机沙箱拒绝对系统临时目录做删除（WinError 5），
   临时文件统一放工作区内的 tests/.tmp/（见决策记录第 10 节）。

运行: python tests/test_update_review_status.py
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import init_db  # noqa: E402
import update_review_status as urs  # noqa: E402

PY = sys.executable
TMPROOT = ROOT / "tests" / ".tmp"


# --------------------------------------------------------------------------- 夹具


def fresh_dir(name: str) -> Path:
    d = TMPROOT / name
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True, exist_ok=True)
    return d


def cleanup(d: Path) -> None:
    shutil.rmtree(d, ignore_errors=True)


HEADER = "| question_uid | subject | status_snapshot | decision | reason |\n| --- | --- | --- | --- | --- |\n"


def make_root(name: str, subjects: tuple[str, ...] = ("english",), questions: dict | None = None) -> Path:
    """临时项目根：data/{subject}.sqlite（含 questions/review_log）+ logs/ + config/distractors.json。"""
    root = fresh_dir(name)
    (root / "data").mkdir(parents=True, exist_ok=True)
    (root / "logs").mkdir(parents=True, exist_ok=True)
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "config" / "distractors.json").write_text("{}\n", encoding="utf-8")
    for subj in subjects:
        conn = sqlite3.connect(str(root / "data" / f"{subj}.sqlite"))
        conn.executescript(init_db.SUBJECT_SCHEMA)
        for uid, status, version in (questions or {}).get(subj, []):
            conn.execute(
                "INSERT INTO questions(question_uid, subject, status, version, stem) VALUES(?,?,?,?,?)",
                (uid, subj, status, version, f"题干 {uid}"),
            )
        conn.commit()
        conn.close()
    return root


def write_queue(root: Path, body: str, name: str = "review_queue.md") -> Path:
    p = root / "output" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(HEADER + body, encoding="utf-8")
    return p


def q_status(root: Path, subject: str, uid: str):
    conn = sqlite3.connect(str(root / "data" / f"{subject}.sqlite"))
    row = conn.execute("SELECT status, version, reviewed_by FROM questions WHERE question_uid=?", (uid,)).fetchone()
    conn.close()
    return row


def review_log(root: Path, subject: str) -> list:
    conn = sqlite3.connect(str(root / "data" / f"{subject}.sqlite"))
    rows = conn.execute("SELECT question_uid, reviewed_at, result FROM review_log ORDER BY id").fetchall()
    conn.close()
    return rows


def reject_log(root: Path) -> list:
    p = root / "logs" / "review_rejects.jsonl"
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


# --------------------------------------------------------------------------- ① 通过


def test_approve_sets_approved_and_writes_review_log() -> None:
    root = make_root("approve", questions={"english": [("uid-ok", "pending_review", 1)]})
    try:
        q = write_queue(root, "| uid-ok | english | pending_review | 通过 | |\n")
        res = urs.run(q, dry_run=False, root=root)
        assert res["updated"] == 1, f"应更新 1 行，实际 {res['updated']}"
        assert (res["conflicts"], res["missing"], res["invalid"]) == (0, 0, 0), res
        status, version, reviewed_by = q_status(root, "english", "uid-ok")
        assert status == "approved", f"状态应为 approved，实际 {status}"
        assert version == 2, f"version 应 +1 → 2，实际 {version}"
        assert reviewed_by == "human", f"reviewed_by 应为 human，实际 {reviewed_by}"
        logs = review_log(root, "english")
        assert len(logs) == 1 and logs[0][0] == "uid-ok" and logs[0][2] == "approved", logs
        assert logs[0][1], "reviewed_at 不应为空"
        assert not (root / "logs" / "review_rejects.jsonl").exists(), "通过不应写拒绝日志"
    finally:
        cleanup(root)


def test_version_null_is_created() -> None:
    """version 为 NULL 时应写成 1（COALESCE），不能崩在 NOT NULL / TypeError 上。"""
    root = make_root("version_null", questions={"english": [("uid-null", "pending_review", None)]})
    try:
        q = write_queue(root, "| uid-null | english | pending_review | approve | |\n")
        res = urs.run(q, dry_run=False, root=root)
        assert res["updated"] == 1, res
        assert q_status(root, "english", "uid-null")[1] == 1
    finally:
        cleanup(root)


# --------------------------------------------------------------------------- ② 拒绝


def test_reject_sets_rejected_and_writes_reject_log_only() -> None:
    root = make_root("reject", questions={"english": [("uid-bad", "pending_review", 1)]})
    try:
        dist = root / "config" / "distractors.json"
        before_content = dist.read_text(encoding="utf-8")
        before_mtime = dist.stat().st_mtime_ns
        q = write_queue(root, "| uid-bad | english | pending_review | 拒绝 | 答案错误 |\n")
        res = urs.run(q, dry_run=False, root=root)
        assert res["updated"] == 1 and res["conflicts"] == 0, res
        assert q_status(root, "english", "uid-bad")[0] == "rejected"
        assert review_log(root, "english")[0][2] == "rejected"

        logs = reject_log(root)
        assert len(logs) == 1, f"review_rejects.jsonl 应有 1 行，实际 {logs}"
        rec = logs[0]
        assert set(rec) == {"ts", "question_uid", "subject", "reason"}, f"字段应为 ts/question_uid/subject/reason，实际 {set(rec)}"
        assert rec["question_uid"] == "uid-bad" and rec["subject"] == "english" and rec["reason"] == "答案错误"

        # ⚠️ 硬要求：拒绝原因绝不能混写进干扰项库 config/distractors.json
        assert dist.read_text(encoding="utf-8") == before_content, "distractors.json 内容被改动了！"
        assert dist.stat().st_mtime_ns == before_mtime, "distractors.json 的 mtime 变了（被写过）！"
    finally:
        cleanup(root)


def test_reject_reason_enumerated_and_prefixed() -> None:
    """原因必须在 7 个下拉值内；`其他：xxx` 带补充说明也接受，但垃圾原因 → invalid。"""
    root = make_root("reject_reason", questions={"english": [
        ("uid-r1", "pending_review", 1), ("uid-r2", "pending_review", 1), ("uid-r3", "pending_review", 1)]})
    try:
        q = write_queue(root, (
            "| uid-r1 | english | pending_review | 拒绝 | 其他：题干抄错 |\n"
            "| uid-r2 | english | pending_review | 拒绝 | 我觉得不好 |\n"
            "| uid-r3 | english | pending_review | 拒绝 | |\n"
        ))
        res = urs.run(q, dry_run=False, root=root)
        assert res["updated"] == 1, f"只有 uid-r1 应更新，实际 updated={res['updated']}"
        assert res["invalid"] == 2, f"应 2 行 invalid，实际 {res['invalid']}: {res['invalid_rows']}"
        assert q_status(root, "english", "uid-r2")[0] == "pending_review", "非法原因的行不得落库"
        assert reject_log(root)[0]["reason"] == "其他：题干抄错", "日志应保留人工填写的原文"
    finally:
        cleanup(root)


# --------------------------------------------------------------------------- ③ 快照冲突


def test_snapshot_conflict_is_skipped() -> None:
    root = make_root("conflict", questions={"english": [
        ("uid-c", "approved", 3), ("uid-fine", "pending_review", 1)]})
    try:
        q = write_queue(root, (
            "| uid-c | english | pending_review | 通过 | |\n"
            "| uid-fine | english | pending_review | 通过 | |\n"
        ))
        res = urs.run(q, dry_run=False, root=root)
        assert res["conflicts"] == 1 and res["updated"] == 1, res
        row = q_status(root, "english", "uid-c")
        assert row[0] == "approved" and row[1] == 3, f"冲突行不得改动（status/version）: {row}"
        assert q_status(root, "english", "uid-fine")[0] == "approved"
        conflicts = res["conflict_rows"]
        assert conflicts[0]["question_uid"] == "uid-c"
        assert conflicts[0]["snapshot"] == "pending_review" and conflicts[0]["actual"] == "approved"
        assert all(r[0] != "uid-c" for r in review_log(root, "english")), "冲突行不应写 review_log"
    finally:
        cleanup(root)


# --------------------------------------------------------------------------- ④ 缺失


def test_missing_uid_is_counted_not_fatal() -> None:
    root = make_root("missing", questions={"english": [("uid-here", "pending_review", 1)]})
    try:
        q = write_queue(root, (
            "| uid-ghost | english | pending_review | 通过 | |\n"
            "| uid-here | english | pending_review | 通过 | |\n"
        ))
        res = urs.run(q, dry_run=False, root=root)
        assert res["missing"] == 1 and res["updated"] == 1, res
        assert res["missing_rows"][0]["question_uid"] == "uid-ghost"
        assert q_status(root, "english", "uid-here")[0] == "approved", "缺 uid 不应中断后续行"
    finally:
        cleanup(root)


# --------------------------------------------------------------------------- ⑤ 畸形行


def test_malformed_rows_are_invalid_and_tolerated() -> None:
    root = make_root("invalid", questions={"english": [("uid-x", "pending_review", 1)]})
    try:
        q = root / "output" / "review_queue.md"
        q.parent.mkdir(parents=True, exist_ok=True)
        q.write_text(
            "# 人工审核队列\n"
            "\n"
            "说明：把 decision 填成 通过/拒绝/修改。\n"
            "\n" + HEADER +
            "\n"
            "| uid-x | english | pending_review | 通过 | |\n"
            "| uid-bad-decision | english | pending_review | 也许 | |\n"
            "| uid-bad-subject | 数学 | pending_review | 通过 | |\n"
            "| uid-x | english |  | 通过 | |\n"
            "行内杂讯不是表格\n"
            "| uid-short | english |\n"
            "|  | english | pending_review | 通过 | |\n",
            encoding="utf-8",
        )
        res = urs.run(q, dry_run=False, root=root)
        assert res["updated"] == 1, f"只有 uid-x 应成功，实际 {res}（valid 行={res['parsed_rows']}）"
        assert res["invalid"] == 5, f"应有 5 行 invalid，实际 {res['invalid']}: {[r['error'] for r in res['invalid_rows']]}"
        errs = " | ".join(r["error"] for r in res["invalid_rows"])
        for expect in ("decision", "subject", "status_snapshot", "列数不足", "question_uid 为空"):
            assert expect in errs, f"invalid 原因应包含「{expect}」，实际: {errs}"
    finally:
        cleanup(root)


def test_header_aliases_and_extra_columns() -> None:
    """表头列序可变、中英别名与反引号装饰都要能吃。"""
    root = make_root("aliases", questions={"english": [("uid-alias", "pending_review", 1)]})
    try:
        q = root / "output" / "review_queue.md"
        q.parent.mkdir(parents=True, exist_ok=True)
        q.write_text(
            "| `uid` | 科目 | 状态 | decision | 原因 | 备注 |\n"
            "| :--- | :---: | --- | --- | --- | --- |\n"
            "| uid-alias | English | `pending_review` | **approve** |  | 人工核对过 |\n",
            encoding="utf-8",
        )
        res = urs.run(q, dry_run=False, root=root)
        assert res["updated"] == 1, res
        assert q_status(root, "english", "uid-alias")[0] == "approved"
    finally:
        cleanup(root)


# --------------------------------------------------------------------------- 修改 → 保持待审


def test_edit_keeps_pending_review() -> None:
    root = make_root("edit", questions={"english": [("uid-e", "pending_review", 2)]})
    try:
        q = write_queue(root, "| uid-e | english | pending_review | 修改 | 答案错误 |\n")
        res = urs.run(q, dry_run=False, root=root)
        assert res["updated"] == 1, res
        status, version, reviewed_by = q_status(root, "english", "uid-e")
        assert status == "pending_review", f"修改后应保持 pending_review，实际 {status}"
        assert version == 3 and reviewed_by == "human"
        assert review_log(root, "english")[0][2] == "pending_review"
        assert not reject_log(root), "「修改」不是拒绝，不应写 review_rejects.jsonl"
    finally:
        cleanup(root)


# --------------------------------------------------------------------------- ⑥ dry-run


def test_dry_run_writes_nothing() -> None:
    root = make_root("dry", questions={"english": [
        ("uid-a", "pending_review", 1), ("uid-b", "pending_review", 1)]})
    try:
        q = write_queue(root, (
            "| uid-a | english | pending_review | 通过 | |\n"
            "| uid-b | english | pending_review | 拒绝 | 格式问题 |\n"
            "| uid-ghost | english | pending_review | 通过 | |\n"
        ))
        res = urs.run(q, dry_run=True, root=root)
        assert res["dry_run"] is True
        assert res["updated"] == 2 and res["missing"] == 1, res
        for uid in ("uid-a", "uid-b"):
            row = q_status(root, "english", uid)
            assert row[0] == "pending_review" and row[1] == 1, f"dry-run 不得改动库: {uid} {row}"
        assert review_log(root, "english") == [], "dry-run 不得写 review_log"
        assert not (root / "logs" / "review_rejects.jsonl").exists(), "dry-run 不得写拒绝日志"
        assert [a["to"] for a in res["applied"]] == ["approved", "rejected"], res["applied"]
    finally:
        cleanup(root)


def test_cli_dry_run_subprocess_no_write() -> None:
    root = make_root("cli_dry", questions={"english": [("uid-cli", "pending_review", 1)]})
    try:
        q = write_queue(root, "| uid-cli | english | pending_review | 通过 | |\n")
        proc = subprocess.run(
            [PY, str(ROOT / "scripts" / "update_review_status.py"), str(q), "--dry-run", "--root", str(root)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120, cwd=str(ROOT),
        )
        assert proc.returncode == 0, f"退出码 {proc.returncode}\n{proc.stdout[-800:]}\n{proc.stderr[-800:]}"
        assert '"dry_run": true' in proc.stdout, proc.stdout[-500:]
        assert "[dry-run]" in proc.stdout, "dry-run 应打印将执行的动作"
        assert q_status(root, "english", "uid-cli")[0] == "pending_review", "CLI dry-run 不得落库"
        assert review_log(root, "english") == []
    finally:
        cleanup(root)


def test_cli_missing_queue_exit_2() -> None:
    root = make_root("cli_missing")
    try:
        proc = subprocess.run(
            [PY, str(ROOT / "scripts" / "update_review_status.py"), str(root / "output" / "nope.md")],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120, cwd=str(ROOT),
        )
        assert proc.returncode == 2, f"文件不存在应退出 2，实际 {proc.returncode}: {proc.stdout[-300:]}"
        assert "不存在" in proc.stdout
    finally:
        cleanup(root)


def test_compile() -> None:
    import py_compile

    py_compile.compile(str(ROOT / "scripts" / "update_review_status.py"), doraise=True)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS {fn.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"  FAIL {fn.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  ERROR {fn.__name__}: {type(exc).__name__}: {exc}")
    shutil.rmtree(TMPROOT, ignore_errors=True)
    print(f"{len(fns) - failed}/{len(fns)} passed")
    raise SystemExit(1 if failed else 0)
