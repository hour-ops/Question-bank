#!/usr/bin/env python
"""update_daily_progress.py 离线测试（**不联网、不碰真实 data/**）。

覆盖：① 混合对错聚合 ② 幂等重跑 ③ ACA 满分判定 ④ 主观题 0.8 阈值 ⑤ --dry-run 不落库
      （另含：本地时区日期过滤、非法日期、questions 表不被改动、py_compile）

⚠️ 不使用 tempfile.TemporaryDirectory()：本机沙箱拒绝对系统临时目录做删除（WinError 5），
   因此临时文件统一放在工作区内的 tests/.tmp/ 下。

运行: python tests/test_update_daily_progress.py
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import init_db  # noqa: E402
import update_daily_progress as udp  # noqa: E402

PY = sys.executable
TMPROOT = ROOT / "tests" / ".tmp"
# ⚠️ tests/.tmp 是各测试文件**共享**的目录，且 test_fetch.py 收尾会 rmtree 整个 TMPROOT
#    → 并发跑多个测试文件时会互相删掉临时目录。本文件只在自己的子目录里造现场、只清自己。
TMPDIR = TMPROOT / "update_daily_progress"
SCRIPT = ROOT / "scripts" / "update_daily_progress.py"
DATE = "2026-10-11"

# 科目库 questions 的测试 fixture（题型决定 ACA 满分规则与 subjects 摘要）
QUESTIONS_FIXTURE = {
    "english": [("u-en-1", "grammar_fill"), ("u-en-2", "grammar_fill"),
                ("u-en-3", "writing"), ("u-en-4", "grammar_fill")],
    "c_wuhan": [("u-c-1", "code_correction"), ("u-c-2", "programming")],
    "aca_llm": [("u-aca-1", "single_choice"), ("u-aca-2", "multiple_choice"),
                ("u-aca-3", "single_choice")],
}

QUESTIONS_ONLY_DDL = (
    "CREATE TABLE IF NOT EXISTS questions ("
    "id INTEGER PRIMARY KEY, question_uid TEXT UNIQUE, question_type TEXT);"
)


# --------------------------------------------------------------------- 测试脚手架


def fresh_dir(name: str) -> Path:
    """在本文件专属的临时子目录里创建干净目录（可被沙箱删除）。"""
    d = TMPDIR / name
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True, exist_ok=True)
    return d


def cleanup(d: Path) -> None:
    shutil.rmtree(d, ignore_errors=True)


def att(attempt_id: str, subject: str, question_uid: str, judge_score, *,
        created_at: str = DATE + "T09:15:00", judge_model: str = "deepseek-flash",
        source_type: str = "fetch") -> dict:
    return {"attempt_id": attempt_id, "subject": subject, "question_uid": question_uid,
            "judge_score": judge_score, "created_at": created_at,
            "judge_model": judge_model, "source_type": source_type}


def make_env(root: Path, attempts: list[dict], *,
             subjects: dict[str, list[tuple[str, str]]] | None = None,
             with_daily_progress: bool = True) -> tuple[Path, Path]:
    """造临时 attempts 库 + 科目库（schema 复用 scripts/init_db.py，与真实库一致）。"""
    data = root / "data"
    data.mkdir(parents=True, exist_ok=True)

    a_db = data / "attempts.sqlite"
    conn = sqlite3.connect(str(a_db))
    conn.execute("PRAGMA journal_mode=WAL")           # 与 scripts/init_db.connect 一致
    conn.execute("PRAGMA busy_timeout=30000")
    conn.executescript(init_db.ATTEMPTS_SCHEMA)
    for rec in attempts:
        conn.execute(
            "INSERT INTO attempts(attempt_id, question_uid, subject, user_answer, judge_score,"
            " judge_model, judge_reason, judge_prompt_version, elapsed_ms, synced, source_type, created_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (rec["attempt_id"], rec["question_uid"], rec["subject"], rec.get("user_answer", ""),
             rec.get("judge_score"), rec.get("judge_model", "deepseek-flash"), "", "v0", 1000, 0,
             rec.get("source_type", "fetch"), rec["created_at"]),
        )
    conn.commit()
    conn.close()

    if subjects is None:
        subjects = {s: [] for s in sorted({a["subject"] for a in attempts})}
    for subj, qrows in subjects.items():
        s_db = data / f"{subj}.sqlite"
        s_conn = sqlite3.connect(str(s_db))
        s_conn.execute("PRAGMA journal_mode=WAL")     # 与 scripts/init_db.connect 一致
        s_conn.execute("PRAGMA busy_timeout=30000")
        if with_daily_progress:
            s_conn.executescript(init_db.SUBJECT_SCHEMA)
        else:
            s_conn.executescript(QUESTIONS_ONLY_DDL)
        for uid, qtype in qrows:
            s_conn.execute("INSERT INTO questions(question_uid, question_type) VALUES(?,?)", (uid, qtype))
        s_conn.commit()
        s_conn.close()
    return a_db, data


def run(a_db: Path, data: Path, *, date: str = DATE, dry: bool = False) -> int:
    """进程内跑 main()（不启子进程，便于断言返回值）。"""
    argv = ["--date", date, "--attempts-db", str(a_db), "--data-dir", str(data)]
    if dry:
        argv.append("--dry-run")
    return udp.main(argv)


def run_cli(a_db: Path, data: Path, *extra: str) -> subprocess.CompletedProcess:
    import os

    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(
        [PY, str(SCRIPT), "--attempts-db", str(a_db), "--data-dir", str(data), *extra],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=120, cwd=str(ROOT), env=env,
    )


def progress_row(db: Path, date_str: str = DATE) -> sqlite3.Row | None:
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(
            "SELECT date, total_done, correct_count, wrong_count, subjects FROM daily_progress WHERE date=?",
            (date_str,)).fetchone()
    finally:
        conn.close()


def has_table(db: Path, name: str) -> bool:
    conn = sqlite3.connect(str(db))
    try:
        return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None
    finally:
        conn.close()


def questions_snapshot(db: Path) -> list[tuple]:
    conn = sqlite3.connect(str(db))
    try:
        return conn.execute("SELECT question_uid, question_type FROM questions ORDER BY question_uid").fetchall()
    finally:
        conn.close()


def db_digest(db: Path) -> dict:
    """库内容快照（表清单 + 每表内容 + 存储的 journal_mode），用于证明 dry-run 零改动。"""
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        digest: dict = {"__journal_mode__": conn.execute("PRAGMA journal_mode").fetchone()[0]}
        names = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        for t in names:
            cols = [r[1] for r in conn.execute(f"PRAGMA table_info({t})")]
            rows = [tuple(r) for r in conn.execute(f"SELECT * FROM {t}")]
            digest[t] = (tuple(cols), tuple(sorted(str(r) for r in rows)))
        return digest
    finally:
        conn.close()


# --------------------------------------------------------------------- ① 混合聚合


def test_mixed_aggregation() -> None:
    """三个科目混合对错：正确/错误/未判分分别计数，subjects 摘要含题型与来源分布。"""
    d = fresh_dir("mixed")
    try:
        attempts = [
            att("a1", "english", "u-en-1", 1.0),                       # 0–1 分制 → 正确
            att("a2", "english", "u-en-2", 0.9, source_type="generate"),   # 正确
            att("a3", "english", "u-en-3", 0.5, source_type="generate"),   # 错误
            att("a4", "english", "u-en-4", 0.8),                       # 边界 0.8 → 正确
            att("a5", "c_wuhan", "u-c-1", 0.85),                       # 正确
            att("a6", "c_wuhan", "u-c-2", None, judge_model="deepseek-v4-pro"),  # 未判分
            att("a7", "aca_llm", "u-aca-1", 2.0, judge_model="local_rule"),      # ACA 满分 → 正确
            att("a8", "aca_llm", "u-aca-2", 1.5, judge_model="local_rule"),      # 多选 1.5 < 2 → 错误
            att("a9", "aca_llm", "u-aca-3", 0.0, judge_model="local_rule"),      # 错误
        ]
        a_db, data = make_env(d, attempts, subjects=QUESTIONS_FIXTURE)
        assert run(a_db, data) == 0

        en = progress_row(data / "english.sqlite")
        assert en is not None, "英语库应有 daily_progress 行"
        assert (en["total_done"], en["correct_count"], en["wrong_count"]) == (4, 3, 1), \
            f"english 应 4/3/1，实际 {(en['total_done'], en['correct_count'], en['wrong_count'])}"
        en_subj = json.loads(en["subjects"])
        assert en_subj["question_types"] == {"grammar_fill": 3, "writing": 1}, en_subj["question_types"]
        assert en_subj["source_types"] == {"fetch": 2, "generate": 2}, en_subj["source_types"]
        assert en_subj["correct"] == 3 and en_subj["wrong"] == 1 and en_subj["unjudged"] == 0

        cw = progress_row(data / "c_wuhan.sqlite")
        assert cw is not None and (cw["total_done"], cw["correct_count"], cw["wrong_count"]) == (2, 1, 0), \
            f"c_wuhan 应 2/1/0（1 条未判分），实际 {tuple(cw)}"
        assert json.loads(cw["subjects"])["unjudged"] == 1, "未判分应计入 unjudged，不计错误"

        aca = progress_row(data / "aca_llm.sqlite")
        assert aca is not None and (aca["total_done"], aca["correct_count"], aca["wrong_count"]) == (3, 1, 2), \
            f"aca_llm 应 3/1/2，实际 {tuple(aca)}"

        # 当天无 attempts 的科目不写行（c_hbpu 无库无数据）
        assert not (data / "c_hbpu.sqlite").exists()
    finally:
        cleanup(d)


# --------------------------------------------------------------------- ② 幂等


def test_idempotent_rerun() -> None:
    """同一天重复跑不累加；新增 attempts 后按全量重算覆盖；questions 表零改动。"""
    d = fresh_dir("idempotent")
    try:
        a_db, data = make_env(d, [att("a1", "english", "u-en-1", 1.0),
                                  att("a2", "english", "u-en-2", 1.0)],
                              subjects={"english": QUESTIONS_FIXTURE["english"]})
        en_db = data / "english.sqlite"
        q_before = questions_snapshot(en_db)

        assert run(a_db, data) == 0
        first = progress_row(en_db)
        assert (first["total_done"], first["correct_count"]) == (2, 2), tuple(first)

        assert run(a_db, data) == 0  # 幂等重跑
        again = progress_row(en_db)
        assert tuple(again) == tuple(first), f"重跑结果应完全一致：{tuple(first)} vs {tuple(again)}"
        assert again["total_done"] == 2, "重复跑不得累加（应为覆盖式写入）"

        # 追加一条错题 → 重算覆盖为 3/2/1，而不是 5
        conn = sqlite3.connect(str(a_db))
        conn.execute(
            "INSERT INTO attempts(attempt_id, question_uid, subject, judge_score, judge_model,"
            " source_type, created_at) VALUES('a3','u-en-3','english',0.3,'deepseek-flash','fetch',?)",
            (DATE + "T10:00:00",))
        conn.commit()
        conn.close()

        assert run(a_db, data) == 0
        third = progress_row(en_db)
        assert (third["total_done"], third["correct_count"], third["wrong_count"]) == (3, 2, 1), tuple(third)

        assert questions_snapshot(en_db) == q_before, "本脚本只能写 daily_progress，questions 表不得被改动"
    finally:
        cleanup(d)


# --------------------------------------------------------------------- ③ ACA 满分


def test_aca_full_score_rule() -> None:
    """ACA 满分 = config/aca_rules.json 的 correct / all_correct；judge_score >= 满分记正确。"""
    real = udp.load_aca_rules()
    assert udp.aca_full_score(real, "single_choice") == 2.0, "单选取 aca_rules.single_choice.correct"
    assert udp.aca_full_score(real, "multiple_choice") == 2.0, "多选取 aca_rules.multiple_choice.all_correct"

    assert udp.judge_correct("aca_llm", 2.0, question_type="single_choice", aca=real) is True
    assert udp.judge_correct("aca_llm", 1.99, question_type="single_choice", aca=real) is False
    assert udp.judge_correct("aca_llm", 0.0, question_type="single_choice", aca=real) is False
    assert udp.judge_correct("aca_llm", 2.0, question_type="multiple_choice", aca=real) is True
    assert udp.judge_correct("aca_llm", 1.0, question_type="multiple_choice", aca=real) is False
    assert udp.judge_correct("aca_llm", None, aca=real) is False, "未判分不得记正确"
    # 显式 full_score 优先（供未来题库改分值）
    assert udp.judge_correct("aca_llm", 2.0, full_score=5.0, aca=real) is False

    d = fresh_dir("aca_rules")
    try:
        cfg = d / "aca_rules.json"
        cfg.write_text(json.dumps({"single_choice": {"correct": 5.0},
                                   "multiple_choice": {"all_correct": 3.0}}), encoding="utf-8")
        rules = udp.load_aca_rules(cfg)
        assert udp.aca_full_score(rules, "single_choice") == 5.0
        assert udp.aca_full_score(rules, "multiple_choice") == 3.0
        assert udp.judge_correct("aca_llm", 5.0, question_type="single_choice", aca=rules) is True
        assert udp.judge_correct("aca_llm", 4.9, question_type="single_choice", aca=rules) is False
        assert udp.judge_correct("aca_llm", 3.0, question_type="multiple_choice", aca=rules) is True
        assert udp.judge_correct("aca_llm", 2.9, question_type="multiple_choice", aca=rules) is False
    finally:
        cleanup(d)

    # 配置读不到 → 回落到常量 ACA_QUESTION_FULL_SCORE
    assert udp.aca_full_score({}, None) == udp.ACA_QUESTION_FULL_SCORE == 2.0


# --------------------------------------------------------------------- ④ 主观题阈值


def test_subjective_threshold_and_scaling() -> None:
    """主观题：归一化到 0–1，>= 0.8 记正确；满分可由 taxonomy / 常量表 / 题目自带列配置。"""
    assert abs(udp.normalize_subjective(0.8) - 0.8) < 1e-12
    assert udp.judge_correct("english", 0.8) is True, "恰好 0.8 → 正确"
    assert udp.judge_correct("english", 0.79) is False
    assert udp.judge_correct("c_wuhan", 0.8) is True and udp.judge_correct("c_hbpu", 0.79) is False
    assert udp.judge_correct("english", None) is False

    # 满分制打分（judge_score > 1）→ 除以该题满分
    assert abs(udp.normalize_subjective(8.0, 10.0) - 0.8) < 1e-12
    assert udp.judge_correct("english", 8.0, full_score=10.0) is True
    assert udp.judge_correct("english", 7.9, full_score=10.0) is False
    assert udp.judge_correct("c_wuhan", 2.0, full_score=10.0) is False
    assert udp.normalize_subjective(12.0, 10.0) == 1.0, "超满分应裁剪到 1.0"
    assert udp.normalize_subjective(-3.0, 10.0) == 0.0

    # 满分解析顺序：① 题目自带 > ② taxonomy > ③ 脚本常量表 > ④ 默认 1.0
    assert udp.subjective_full_score("english", "grammar_fill") == udp.DEFAULT_SUBJECTIVE_FULL_SCORE
    taxonomy = {"subjects": {"english": {"question_types": {"writing": {"full_score": 10}}}}}
    assert udp.subjective_full_score("english", "writing", taxonomy=taxonomy) == 10.0
    assert udp.subjective_full_score("english", "writing", question_meta={"full_score": 5.0},
                                     taxonomy=taxonomy) == 5.0, "题目自带满分优先于 taxonomy"
    try:
        udp.SUBJECTIVE_FULL_SCORE[("c_wuhan", "*")] = 20.0
        assert udp.subjective_full_score("c_wuhan", "programming") == 20.0
        assert udp.subjective_full_score("c_hbpu", "programming") == udp.DEFAULT_SUBJECTIVE_FULL_SCORE
    finally:
        udp.SUBJECTIVE_FULL_SCORE.pop(("c_wuhan", "*"), None)


def test_taxonomy_full_score_end_to_end() -> None:
    """taxonomy 里配置题型满分后，落库统计按该刻度判对错（8/10 正确，7/10 错误）。"""
    d = fresh_dir("taxonomy_scale")
    orig_taxonomy = udp.TAXONOMY
    try:
        a_db, data = make_env(d, [att("a1", "english", "u-en-3", 8.0),
                                  att("a2", "english", "u-en-3", 7.0)],
                              subjects={"english": QUESTIONS_FIXTURE["english"]})
        cfg = d / "taxonomy.json"
        cfg.write_text(json.dumps({"subjects": {"english": {
            "question_types": {"writing": {"full_score": 10}}}}}), encoding="utf-8")
        udp.TAXONOMY = cfg
        assert run(a_db, data) == 0
        row = progress_row(data / "english.sqlite")
        assert (row["total_done"], row["correct_count"], row["wrong_count"]) == (2, 1, 1), tuple(row)
    finally:
        udp.TAXONOMY = orig_taxonomy
        cleanup(d)


# --------------------------------------------------------------------- ⑤ dry-run


def test_dry_run_does_not_write() -> None:
    """--dry-run：退出码 0、打印将写入的行、不建 daily_progress 表、不写行。"""
    d = fresh_dir("dry_run")
    try:
        a_db, data = make_env(d, [att("a1", "english", "u-en-1", 1.0),
                                  att("a2", "english", "u-en-2", 0.2),
                                  att("a3", "aca_llm", "u-aca-1", 2.0, judge_model="local_rule")],
                              subjects={"english": QUESTIONS_FIXTURE["english"],
                                        "aca_llm": QUESTIONS_FIXTURE["aca_llm"]},
                              with_daily_progress=False)

        before = {subj: db_digest(data / f"{subj}.sqlite") for subj in ("english", "aca_llm")}

        proc = run_cli(a_db, data, "--date", DATE, "--dry-run")
        assert proc.returncode == 0, f"dry-run 退出码 {proc.returncode}\n{proc.stderr[-800:]}"
        assert '"dry_run": true' in proc.stdout, proc.stdout[-500:]
        assert "[dry-run]" in proc.stdout
        assert "dry_run=True" in proc.stdout
        assert "total=2" in proc.stdout, "应打印将写入的行"
        assert '"grammar_fill": 2' in proc.stdout, "dry-run 仍应读出题型分布（只读打开 WAL 库）"

        for subj in ("english", "aca_llm"):
            db = data / f"{subj}.sqlite"
            assert not has_table(db, "daily_progress"), f"{subj}: dry-run 不得建 daily_progress 表"
            assert db_digest(db) == before[subj], f"{subj}: dry-run 不得改动库内容（含 journal_mode）"

        # 去掉 --dry-run 后应真正落库
        proc2 = run_cli(a_db, data, "--date", DATE)
        assert proc2.returncode == 0, proc2.stderr[-800:]
        assert '"dry_run": false' in proc2.stdout
        row = progress_row(data / "english.sqlite")
        assert row is not None and (row["total_done"], row["correct_count"], row["wrong_count"]) == (2, 1, 1), \
            f"english 应 2/1/1，实际 {tuple(row) if row else None}"
        assert progress_row(data / "aca_llm.sqlite")["correct_count"] == 1
    finally:
        cleanup(d)


# --------------------------------------------------------------------- ⑥ 日期 / 时区


def test_date_filter_uses_local_timezone() -> None:
    """只统计该本地自然日的 attempts：UTC 时间戳按本地换算，跨日/空格分隔格式都正确。"""
    d = fresh_dir("date_filter")
    try:
        tz = udp.local_tz()
        utc_same_day = datetime(2026, 10, 11, 12, 0, 0, tzinfo=tz).astimezone(timezone.utc) \
            .isoformat(timespec="seconds")                      # 本地正午 → 写成 UTC 串
        prev_day = "2026-10-10 23:00:00"                        # 本地前一天（空格分隔、无时区）
        next_day = "2026-10-12T00:30:00"                        # 本地次日
        space_same_day = "2026-10-11 08:00:00"                  # 本地当天（空格分隔）

        attempts = [
            att("a1", "english", "u-en-1", 1.0, created_at=utc_same_day),
            att("a2", "english", "u-en-2", 1.0, created_at=space_same_day),
            att("a3", "english", "u-en-3", 0.0, created_at=prev_day),
            att("a4", "english", "u-en-4", 0.0, created_at=next_day),
        ]
        a_db, data = make_env(d, attempts, subjects={"english": QUESTIONS_FIXTURE["english"]})

        assert run(a_db, data, date=DATE) == 0
        row = progress_row(data / "english.sqlite")
        assert row["total_done"] == 2, f"只应统计当天 2 条，实际 {row['total_done']}"

        # 前一天视角：应只看到 prev_day 那 1 条
        assert run(a_db, data, date="2026-10-10") == 0
        prev_row = progress_row(data / "english.sqlite", "2026-10-10")
        assert prev_row["total_done"] == 1, f"2026-10-10 应 1 条，实际 {prev_row['total_done']}"
        assert progress_row(data / "english.sqlite", DATE)["total_done"] == 2, "不同日期互不覆盖"

        # 本地日期换算自检（防测试自身写错时区预期）
        assert udp.local_date(utc_same_day) == DATE, f"{utc_same_day} 应换算为本地 {DATE}"
        assert udp.local_date(prev_day) == "2026-10-10" and udp.local_date("垃圾时间戳") is None
    finally:
        cleanup(d)


def test_bad_args_rejected() -> None:
    """非法日期 / 缺失 attempts 库 → 退出码 2（不写任何东西）。"""
    d = fresh_dir("bad_args")
    try:
        a_db, data = make_env(d, [att("a1", "english", "u-en-1", 1.0)],
                              subjects={"english": QUESTIONS_FIXTURE["english"]})
        assert run(a_db, data, date="2026-13-99") == 2, "非法日期应返回 2"
        assert progress_row(data / "english.sqlite") is None
        assert udp.main(["--date", DATE, "--attempts-db", str(d / "nope.sqlite"),
                         "--data-dir", str(data)]) == 2, "attempts 库缺失应返回 2"
    finally:
        cleanup(d)


def test_compile() -> None:
    import py_compile

    py_compile.compile(str(SCRIPT), doraise=True)


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
    shutil.rmtree(TMPDIR, ignore_errors=True)
    print(f"{len(fns) - failed}/{len(fns)} passed")
    raise SystemExit(1 if failed else 0)
