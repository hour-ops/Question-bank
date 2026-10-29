#!/usr/bin/env python
"""sm2_scheduler.py 离线测试 —— **不联网**（纯函数 + 工作区临时 sqlite/临时 config + 子进程 dry-run）。

覆盖：①答对升级 ②中途再错只回退一档（不是重置） ③最高档保持 ④aca_exit_streak 移出
      ⑤--dry-run 不改库 ⑥水位防重放 ⑦questions 表零写入（硬约束）

⚠️ 不使用 tempfile.TemporaryDirectory()：本机沙箱拒绝对系统临时目录做删除（WinError 5），
   因此临时文件统一放在工作区内的 tests/.tmp/ 下。

运行: python tests/test_sm2_scheduler.py
"""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import init_db  # noqa: E402
import sm2_scheduler as sm2  # noqa: E402

PY = sys.executable
TMPROOT = ROOT / "tests" / ".tmp"

NOW = datetime(2026, 10, 11, 12, 0, 0, tzinfo=timezone.utc)
NOW_S = sm2.fmt_ts(NOW)
EVENT_TS = (NOW - timedelta(hours=1)).isoformat(timespec="seconds")  # 2026-10-11T11:00:00+00:00
CFG = sm2.load_config()  # 项目真实 config/sm2_config.json
TIERS = CFG["intervals_days"]


def fresh_dir(name: str) -> Path:
    """在工作区内创建干净的临时目录（可被沙箱删除）。"""
    d = TMPROOT / name
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True, exist_ok=True)
    return d


def cleanup(d: Path) -> None:
    shutil.rmtree(d, ignore_errors=True)


# --------------------------------------------------------------------- 夹具


def make_db(d: Path, subject: str) -> Path:
    """用 init_db 的真实 schema 建一个科目库（WAL + busy_timeout 一并生效）。"""
    p = d / f"{subject}.sqlite"
    conn = init_db.connect(p)
    conn.executescript(init_db.SUBJECT_SCHEMA)
    conn.commit()
    conn.close()
    return p


def write_cfg(d: Path, **over: object) -> Path:
    cfg = {"version": "test", "intervals_days": list(TIERS), "aca_exit_streak": 2,
           "downgrade_policy": "step_back_one"}
    cfg.update(over)
    p = d / "sm2_config.json"
    p.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    return p


def open_db(d: Path, subject: str):
    return sm2.connect(d / f"{subject}.sqlite")


def seed_wrong(conn, uid: str, **cols: object) -> None:
    base = {"wrong_count": 1, "correct_streak": 0, "last_wrong_at": None,
            "next_review_at": None, "mastery": 0, "notes": None, "updated_at": None}
    base.update(cols)
    conn.execute(
        "INSERT INTO wrong_book(question_uid,wrong_count,correct_streak,last_wrong_at,"
        "next_review_at,mastery,notes,updated_at) VALUES(?,?,?,?,?,?,?,?)",
        (uid, base["wrong_count"], base["correct_streak"], base["last_wrong_at"],
         base["next_review_at"], base["mastery"], base["notes"], base["updated_at"]),
    )
    conn.commit()


def seed_review(conn, uid: str, result: str, ts: str = EVENT_TS) -> None:
    conn.execute("INSERT INTO review_log(question_uid, reviewed_at, result) VALUES(?,?,?)",
                 (uid, ts, result))
    conn.commit()


def dump(conn, table: str) -> list[tuple]:
    return [tuple(r) for r in conn.execute(f"SELECT * FROM {table} ORDER BY rowid")]


def run_capture(*args: object, **kwargs: object) -> tuple[dict, str]:
    """跑 run() 并捕获 stdout（run 内部只 print，不写日志文件）。"""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        stats = sm2.run(*args, **kwargs)  # type: ignore[arg-type]
    return stats, buf.getvalue()


# --------------------------------------------------------------------- 纯函数


def test_load_config_real_file() -> None:
    cfg = sm2.load_config()
    assert cfg["intervals_days"] == [1, 3, 7, 14, 30], f"档位应为 1/3/7/14/30，实际 {cfg['intervals_days']}"
    assert cfg["aca_exit_streak"] == 2
    assert cfg["downgrade_policy"] == "step_back_one"


def test_load_config_rejects_bad_values() -> None:
    d = fresh_dir("cfg_bad")
    try:
        bad_policy = write_cfg(d, downgrade_policy="whatever")
        try:
            sm2.load_config(bad_policy)
        except ValueError:
            pass
        else:
            raise AssertionError("非法 downgrade_policy 应报错而不是静默回落")

        bad_intervals = write_cfg(d, intervals_days=[3, 1])
        try:
            sm2.load_config(bad_intervals)
        except ValueError:
            pass
        else:
            raise AssertionError("非递增 intervals_days 应报错")
    finally:
        cleanup(d)


def test_normalize_result() -> None:
    for v in ("correct", "RIGHT", "ok", 1, True, "正确", "答对"):
        assert sm2.normalize_result(v) is True, f"{v!r} 应判为答对"
    for v in ("wrong", "INCORRECT", "fail", 0, False, "错误", "答错"):
        assert sm2.normalize_result(v) is False, f"{v!r} 应判为答错"
    for v in (None, "", "maybe", "未知"):
        assert sm2.normalize_result(v) is None, f"{v!r} 应判为无法识别"


def test_tier_of_clamps() -> None:
    assert sm2.tier_of(0, 5) == 0
    assert sm2.tier_of(3, 5) == 3
    assert sm2.tier_of(99, 5) == 4, "档位应 clamp 到最高档"
    assert sm2.tier_of(None, 5) == 0
    assert sm2.tier_of(-2, 5) == 0


def test_current_tier_prefers_mastery_with_streak_fallback() -> None:
    """档位以 mastery 为准；mastery 为 0 时才用 correct_streak 兜底。"""
    assert sm2.current_tier({"mastery": 2, "correct_streak": 0}, 5) == 2, "降级后 streak=0 也必须记得档位"
    assert sm2.current_tier({"mastery": 0, "correct_streak": 3}, 5) == 3, "只写了 streak 的库应能兜底"
    assert sm2.current_tier({"mastery": 9, "correct_streak": 0}, 5) == 4
    assert sm2.current_tier(None, 5) == 0


# ① 答对升级


def test_plan_upgrade_on_correct() -> None:
    row = {"wrong_count": 1, "correct_streak": 0, "mastery": 0, "next_review_at": "old"}
    plan = sm2.plan_event(row, True, subject="english", cfg=CFG, now=NOW)
    assert plan["action"] == "upgrade", plan["action"]
    assert (plan["old_tier"], plan["new_tier"]) == (0, 1)
    assert plan["row"]["correct_streak"] == 1
    assert plan["row"]["mastery"] == 1
    assert plan["row"]["next_review_at"] == sm2.fmt_ts(NOW + timedelta(days=TIERS[1])), "0 档答对应进 3 天档"
    assert plan["row"]["updated_at"] == NOW_S


def test_plan_upgrade_from_middle_tier() -> None:
    """3 档（14 天）答对 → 4 档（30 天）。"""
    row = {"wrong_count": 1, "correct_streak": 3, "mastery": 3, "next_review_at": "old"}
    plan = sm2.plan_event(row, True, subject="english", cfg=CFG, now=NOW)
    assert plan["action"] == "upgrade" and plan["new_tier"] == 4
    assert plan["row"]["next_review_at"] == sm2.fmt_ts(NOW + timedelta(days=30))


# ② 中途再错 → 回退一档（不是重置到 1 天）


def test_plan_downgrade_steps_back_one() -> None:
    """7 天档（档位 2）再错 → 回到 3 天档（档位 1），**不是**重置到 1 天。"""
    row = {"wrong_count": 1, "correct_streak": 2, "mastery": 2, "next_review_at": "old"}
    plan = sm2.plan_event(row, False, subject="english", cfg=CFG, now=NOW, at=EVENT_TS)
    assert plan["action"] == "downgrade", plan["action"]
    assert (plan["old_tier"], plan["new_tier"]) == (2, 1), "7 天档应回退到 3 天档"
    assert plan["row"]["next_review_at"] == sm2.fmt_ts(NOW + timedelta(days=TIERS[1]))
    assert plan["row"]["next_review_at"] != sm2.fmt_ts(NOW + timedelta(days=TIERS[0])), "不应重置到 1 天"
    assert plan["row"]["correct_streak"] == 0
    assert plan["row"]["mastery"] == 1, "档位要落在 mastery 上，否则下次答对升不回 7 天档"
    assert plan["row"]["wrong_count"] == 2
    assert plan["row"]["last_wrong_at"] == EVENT_TS


def test_downgrade_then_correct_returns_to_previous_tier() -> None:
    """7 天档 →（错）3 天档 →（对）回到 7 天档（档位连续性）。"""
    row = {"wrong_count": 1, "correct_streak": 2, "mastery": 2, "next_review_at": "old"}
    after_wrong = sm2.plan_event(row, False, subject="english", cfg=CFG, now=NOW)["row"]
    plan = sm2.plan_event(after_wrong, True, subject="english", cfg=CFG, now=NOW)
    assert plan["action"] == "upgrade" and plan["new_tier"] == 2
    assert plan["row"]["next_review_at"] == sm2.fmt_ts(NOW + timedelta(days=TIERS[2])), "应回到 7 天档"


def test_plan_downgrade_floor_is_first_tier() -> None:
    row = {"wrong_count": 2, "correct_streak": 0, "mastery": 0, "next_review_at": "old"}
    plan = sm2.plan_event(row, False, subject="english", cfg=CFG, now=NOW)
    assert plan["action"] == "downgrade" and plan["new_tier"] == 0
    assert plan["row"]["next_review_at"] == sm2.fmt_ts(NOW + timedelta(days=TIERS[0])), "最低档只能停在 1 天档"


def test_plan_first_wrong_enters_wrong_book() -> None:
    plan = sm2.plan_event(None, False, subject="english", cfg=CFG, now=NOW, at=EVENT_TS)
    assert plan["action"] == "first_wrong" and plan["is_new_row"] is True
    assert plan["row"]["wrong_count"] == 1 and plan["row"]["correct_streak"] == 0
    assert plan["row"]["mastery"] == 0
    assert plan["row"]["next_review_at"] == sm2.fmt_ts(NOW + timedelta(days=1)), "首次答错 → now + 1 天"


def test_plan_reset_policy_when_configured() -> None:
    """配置换成 reset_to_one 时按配置走（证明策略确实从 config 读）。"""
    d = fresh_dir("policy")
    try:
        cfg = sm2.load_config(write_cfg(d, downgrade_policy="reset_to_one"))
        row = {"wrong_count": 1, "correct_streak": 2, "mastery": 2, "next_review_at": "old"}
        plan = sm2.plan_event(row, False, subject="english", cfg=cfg, now=NOW)
        assert plan["new_tier"] == 0 and plan["row"]["mastery"] == 0
        assert plan["row"]["next_review_at"] == sm2.fmt_ts(NOW + timedelta(days=1))
    finally:
        cleanup(d)


# ③ 最高档保持


def test_plan_keep_max_tier() -> None:
    row = {"wrong_count": 1, "correct_streak": 4, "mastery": 4, "next_review_at": "old"}
    plan = sm2.plan_event(row, True, subject="english", cfg=CFG, now=NOW)
    assert plan["action"] == "keep_max", plan["action"]
    assert plan["new_tier"] == 4, "已到最高档不应越界"
    assert plan["row"]["next_review_at"] == sm2.fmt_ts(NOW + timedelta(days=30)), "最高档答对保持 30 天"
    assert plan["row"]["mastery"] == 5, "到达最长档且答对 → mastery+1"
    assert plan["row"]["correct_streak"] == 5


def test_plan_max_tier_repeat_keeps_30_days() -> None:
    row = {"wrong_count": 1, "correct_streak": 7, "mastery": 7, "next_review_at": "old"}
    plan = sm2.plan_event(row, True, subject="english", cfg=CFG, now=NOW)
    assert plan["action"] == "keep_max" and plan["new_tier"] == 4
    assert plan["row"]["next_review_at"] == sm2.fmt_ts(NOW + timedelta(days=30))
    assert plan["row"]["mastery"] == 8


# ④ aca_exit_streak 移出


def test_aca_exit_streak_out_of_due_queue() -> None:
    d = fresh_dir("aca_exit")
    try:
        cfg = sm2.load_config(write_cfg(d))
        make_db(d, "aca_llm")
        conn = open_db(d, "aca_llm")
        seed_wrong(conn, "aca1", mastery=1, correct_streak=1,
                   next_review_at="2026-10-11T00:00:00+00:00")
        seed_review(conn, "aca1", "correct")
        conn.close()

        stats, out = run_capture("aca_llm", False, data_dir=d, config_path=d / "sm2_config.json", now=NOW)
        s = stats["subjects"]["aca_llm"]
        assert s["exited"] == 1, f"ACA 连对 2 次应移出，实际 {s}"
        assert s["upgraded"] == 0, "ACA 达标时不应再走普通升级"
        assert s["processed"] == 1

        conn = open_db(d, "aca_llm")
        row = conn.execute("SELECT mastery, correct_streak, next_review_at, updated_at "
                           "FROM wrong_book WHERE question_uid='aca1'").fetchone()
        assert row is not None, "行应保留（删除会丢掉 updated_at 水位，导致事件重放）"
        assert row[0] == 2, f"移出应记 mastery+1，实际 {row[0]}"
        assert row[1] == 2, f"correct_streak 应记到 2，实际 {row[1]}"
        assert row[2] is None, "next_review_at 应为 NULL（移出到期队列）"
        assert row[3] == NOW_S
        due = conn.execute("SELECT count(*) FROM wrong_book WHERE next_review_at IS NOT NULL "
                           "AND next_review_at <= ?", (NOW_S,)).fetchone()[0]
        assert due == 0, "移出后不应再出现在到期队列"
        conn.close()
        assert "移出错题本" in out
    finally:
        cleanup(d)


def test_aca_exit_only_affects_aca_subject() -> None:
    """同样连对 2 次，非 ACA 科目只升级不移出。"""
    row = {"wrong_count": 1, "correct_streak": 1, "mastery": 1, "next_review_at": "old"}
    assert sm2.plan_event(row, True, subject="aca_llm", cfg=CFG, now=NOW)["action"] == "exit"
    for subj in ("english", "c_wuhan", "c_hbpu"):
        plan = sm2.plan_event(row, True, subject=subj, cfg=CFG, now=NOW)
        assert plan["action"] == "upgrade", f"{subj} 不应受 aca_exit_streak 影响"


# ⑤ / ⑥ / ⑦ 端到端（临时库）


def test_end_to_end_upgrade_writes_only_wrong_book() -> None:
    d = fresh_dir("e2e_upgrade")
    try:
        make_db(d, "english")
        conn = open_db(d, "english")
        seed_wrong(conn, "q1", wrong_count=2, correct_streak=0,
                   next_review_at="2026-10-11T00:00:00+00:00", notes="用户备注")
        conn.execute("INSERT INTO questions(question_uid, subject, stem, status, source_url) "
                     "VALUES('q1','english','题干','approved','https://x/1')")
        conn.commit()
        seed_review(conn, "q1", "correct")
        before_q = dump(conn, "questions")
        conn.close()

        stats, _ = run_capture("english", False, data_dir=d, config_path=d / "sm2_config.json", now=NOW)
        s = stats["subjects"]["english"]
        assert (s["processed"], s["upgraded"]) == (1, 1), s
        assert stats["totals"]["upgraded"] == 1
        assert stats["dry_run"] is False and stats["config"]["downgrade_policy"] == "step_back_one"

        conn = open_db(d, "english")
        row = conn.execute("SELECT wrong_count, correct_streak, next_review_at, mastery, notes, updated_at "
                           "FROM wrong_book WHERE question_uid='q1'").fetchone()
        assert row[0] == 2 and row[1] == 1 and row[3] == 1, f"答对升级后状态异常: {row}"
        assert row[2] == sm2.fmt_ts(NOW + timedelta(days=TIERS[1])), "next_review_at 应为 now+3 天"
        assert row[4] == "用户备注", "notes 不应被覆盖"
        assert row[5] == NOW_S, "必须写 updated_at（水位）"
        assert dump(conn, "questions") == before_q, "硬约束：绝不能写 questions 表"
        conn.close()
    finally:
        cleanup(d)


def test_first_wrong_event_inserts_row_in_db() -> None:
    d = fresh_dir("e2e_first_wrong")
    try:
        make_db(d, "c_wuhan")
        conn = open_db(d, "c_wuhan")
        seed_review(conn, "newq", "wrong")
        conn.close()

        stats, _ = run_capture("c_wuhan", False, data_dir=d, config_path=d / "sm2_config.json", now=NOW)
        assert stats["subjects"]["c_wuhan"]["added"] == 1
        conn = open_db(d, "c_wuhan")
        row = conn.execute("SELECT wrong_count, correct_streak, next_review_at, last_wrong_at "
                           "FROM wrong_book WHERE question_uid='newq'").fetchone()
        assert row is not None, "首次答错应新建 wrong_book 行"
        assert row[0] == 1 and row[1] == 0
        assert row[2] == sm2.fmt_ts(NOW + timedelta(days=1)), "首次答错 → now + 1 天"
        assert row[3] == EVENT_TS, "last_wrong_at 应为作答时间"
        conn.close()
    finally:
        cleanup(d)


def test_correct_event_for_unknown_uid_skipped() -> None:
    """答对但不在错题本 → 不新建行、不排程。"""
    d = fresh_dir("e2e_unknown")
    try:
        make_db(d, "english")
        conn = open_db(d, "english")
        seed_review(conn, "never_wrong", "correct")
        conn.close()

        stats, out = run_capture("english", False, data_dir=d, config_path=d / "sm2_config.json", now=NOW)
        assert stats["subjects"]["english"]["processed"] == 0
        assert stats["subjects"]["english"]["skipped"] == 1
        conn = open_db(d, "english")
        assert conn.execute("SELECT count(*) FROM wrong_book").fetchone()[0] == 0
        conn.close()
        assert "不新建行" in out
    finally:
        cleanup(d)


def test_unknown_result_is_skipped() -> None:
    d = fresh_dir("e2e_unknown_result")
    try:
        make_db(d, "english")
        conn = open_db(d, "english")
        seed_wrong(conn, "q1", correct_streak=0, next_review_at="old")
        seed_review(conn, "q1", "半对半错")
        conn.close()

        stats, _ = run_capture("english", False, data_dir=d, config_path=d / "sm2_config.json", now=NOW)
        s = stats["subjects"]["english"]
        assert (s["processed"], s["skipped"]) == (0, 1), s
        conn = open_db(d, "english")
        assert conn.execute("SELECT next_review_at FROM wrong_book WHERE question_uid='q1'").fetchone()[0] == "old"
        conn.close()
    finally:
        cleanup(d)


def test_watermark_prevents_replay() -> None:
    """第二次运行不应重放同一批 review_log 事件。"""
    d = fresh_dir("watermark")
    try:
        make_db(d, "english")
        conn = open_db(d, "english")
        seed_wrong(conn, "q1", correct_streak=0, next_review_at="old")
        seed_review(conn, "q1", "correct")
        conn.close()
        kw = dict(data_dir=d, config_path=d / "sm2_config.json", now=NOW)

        first, _ = run_capture("english", False, **kw)  # type: ignore[arg-type]
        assert first["subjects"]["english"]["processed"] == 1
        conn = open_db(d, "english")
        after_first = dump(conn, "wrong_book")
        conn.close()

        second, _ = run_capture("english", False, **kw)  # type: ignore[arg-type]
        assert second["subjects"]["english"]["processed"] == 0, "水位失效 → 事件被重放"
        assert second["subjects"]["english"]["stale"] == 1
        conn = open_db(d, "english")
        assert dump(conn, "wrong_book") == after_first, "重放会重复升级"
        conn.close()
    finally:
        cleanup(d)


def test_events_after_run_start_are_deferred() -> None:
    """运行起点之后（未来时间戳）的事件留到下一轮，不会被提前应用。"""
    d = fresh_dir("deferred")
    try:
        make_db(d, "english")
        conn = open_db(d, "english")
        seed_wrong(conn, "q1", correct_streak=0, next_review_at="old")
        seed_review(conn, "q1", "correct", ts=(NOW + timedelta(minutes=5)).isoformat(timespec="seconds"))
        conn.close()

        stats, _ = run_capture("english", False, data_dir=d, config_path=d / "sm2_config.json", now=NOW)
        s = stats["subjects"]["english"]
        assert (s["processed"], s["deferred"]) == (0, 1), s
        conn = open_db(d, "english")
        assert conn.execute("SELECT next_review_at FROM wrong_book WHERE question_uid='q1'").fetchone()[0] == "old"
        conn.close()
    finally:
        cleanup(d)


def test_multiple_events_fold_in_order() -> None:
    """同一题的多个事件按时间折叠：7 天档 →（错）3 天档 →（对）回到 7 天档。"""
    d = fresh_dir("fold")
    try:
        make_db(d, "english")
        conn = open_db(d, "english")
        seed_wrong(conn, "q1", mastery=2, correct_streak=2, next_review_at="old")   # 7 天档
        seed_review(conn, "q1", "wrong", ts=(NOW - timedelta(hours=3)).isoformat(timespec="seconds"))
        seed_review(conn, "q1", "correct", ts=(NOW - timedelta(hours=2)).isoformat(timespec="seconds"))
        conn.close()

        stats, _ = run_capture("english", False, data_dir=d, config_path=d / "sm2_config.json", now=NOW)
        s = stats["subjects"]["english"]
        assert (s["processed"], s["downgraded"], s["upgraded"]) == (2, 1, 1), s
        conn = open_db(d, "english")
        row = conn.execute("SELECT wrong_count, correct_streak, mastery, next_review_at FROM wrong_book "
                           "WHERE question_uid='q1'").fetchone()
        # 档位 2 →(错) 1 →(对) 2 → now + 7 天（若档位错用 correct_streak 映射，这里会掉到 3 天档）
        assert row[0] == 2 and row[1] == 1 and row[2] == 2, f"折叠结果异常: {row}"
        assert row[3] == sm2.fmt_ts(NOW + timedelta(days=TIERS[2])), f"应回到 7 天档，实际 {row[3]}"
        conn.close()
    finally:
        cleanup(d)


# ⑤ --dry-run 不改库（含 CLI 路径）


def test_dry_run_does_not_write_db() -> None:
    d = fresh_dir("dry_run")
    try:
        make_db(d, "english")
        conn = open_db(d, "english")
        seed_wrong(conn, "q1", mastery=2, correct_streak=2,
                   next_review_at="2026-10-11T00:00:00+00:00")
        seed_review(conn, "q1", "wrong")
        conn.execute("INSERT INTO questions(question_uid, subject, stem) VALUES('q1','english','题干')")
        conn.commit()
        before = {t: dump(conn, t) for t in ("wrong_book", "review_log", "questions")}
        conn.close()
        kw = dict(data_dir=d, config_path=d / "sm2_config.json", now=NOW)

        stats, out = run_capture("english", True, **kw)  # type: ignore[arg-type]
        assert stats["dry_run"] is True
        assert stats["subjects"]["english"]["processed"] == 1, "dry-run 也应算出将要做的更新"
        assert stats["subjects"]["english"]["downgraded"] == 1
        assert "[dry-run]" in out and "next_review_at:" in out and " -> " in out, "必须打印 旧 → 新"
        assert "[apply]" not in out

        conn = open_db(d, "english")
        after = {t: dump(conn, t) for t in ("wrong_book", "review_log", "questions")}
        conn.close()
        assert after == before, "dry-run 绝不能改库"

        # 真正跑一次才应写入
        real, _ = run_capture("english", False, **kw)  # type: ignore[arg-type]
        assert real["subjects"]["english"]["processed"] == 1
        conn = open_db(d, "english")
        assert dump(conn, "wrong_book") != before["wrong_book"]
        conn.close()
    finally:
        cleanup(d)


def test_cli_dry_run_flag_via_main() -> None:
    """走 main() 的 --dry-run 分支（monkeypatch DATA/CONFIG 到临时目录，不碰真库）。"""
    d = fresh_dir("cli_main")
    cfg_path = write_cfg(d)
    make_db(d, "aca_llm")
    conn = open_db(d, "aca_llm")
    seed_wrong(conn, "aca1", correct_streak=1, next_review_at="old")
    seed_review(conn, "aca1", "correct")
    conn.commit()
    before = dump(conn, "wrong_book")
    conn.close()

    old_data, old_cfg = sm2.DATA, sm2.CONFIG
    sm2.DATA, sm2.CONFIG = d, cfg_path
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            rc = sm2.main(["--subject", "aca_llm", "--dry-run"])
    finally:
        sm2.DATA, sm2.CONFIG = old_data, old_cfg

    out = buf.getvalue()
    assert rc == 0, f"退出码 {rc}"
    assert '"dry_run": true' in out, "汇总 JSON 应含 dry_run"
    payload = json.loads(out.split("=== 汇总 ===", 1)[1])
    assert payload["totals"]["exited"] == 1
    conn = open_db(d, "aca_llm")
    assert dump(conn, "wrong_book") == before, "CLI dry-run 不得改库"
    conn.close()
    cleanup(d)


def test_subprocess_dry_run_on_real_data() -> None:
    """真实 CLI 对真项目库跑 --dry-run：退出码 0、打印汇总 JSON、不写库。"""
    proc = subprocess.run(
        [PY, str(ROOT / "scripts" / "sm2_scheduler.py"), "--subject", "english", "--dry-run"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120, cwd=str(ROOT),
    )
    assert proc.returncode == 0, f"退出码 {proc.returncode}\n{proc.stderr[-800:]}"
    assert "SM-2 排程 [dry-run] 不写库" in proc.stdout
    assert '"dry_run": true' in proc.stdout
    assert "[apply]" not in proc.stdout
    payload = json.loads(proc.stdout.split("=== 汇总 ===", 1)[1])
    assert payload["config"]["downgrade_policy"] == "step_back_one"


def test_compile() -> None:
    import py_compile

    py_compile.compile(str(ROOT / "scripts" / "sm2_scheduler.py"), doraise=True)


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
