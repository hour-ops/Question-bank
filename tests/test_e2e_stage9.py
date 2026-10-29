#!/usr/bin/env python
"""阶段 9 · 端到端测试（隔离测试数据，跑完把库恢复到测试前基线）。

六步链路：
  0) 先做 backup.py 一致性快照（安全网）
  1) ACA 规则判分：抽 10 道 → 入队 → 本地规则判分 → 写 attempts
  2) 英语入队：读 tests/fixtures 的假答案 → POST /api/submit ×10 → judge_queue 10 条 pending
  3) 批处理：sync_outbox --mock → 状态 pending → synced
  4) 进度聚合：update_daily_progress.py → 当日 daily_progress 有记录
  5) SM-2：sm2_scheduler.py → wrong_book.next_review_at 非空
  6) 复盘报告：读 attempts 输出 ACA 得分 / 英语状态 / 错题数 / token

隔离与清理（关键）：
  - 测试产生的 attempts / judge_queue 一律标 `source_type='test'`
  - ⚠️ `review_log` / `wrong_book` / `daily_progress` **没有 source_type 列** → 无法按标记删除，
    因此本脚本**先快照这三张表的全部行，测试后原样恢复**（比"按时间删"更可靠）
  - ⚠️ 不自动恢复 backup 快照：Windows 下 Flask 持有库句柄会导致 `WinError 32`；
    本脚本用 DELETE + 行级恢复达成同样效果（快照仅作安全网）

用法: python tests/test_e2e_stage9.py [--port 5000]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
DATA = ROOT / "data"
SUBJECTS = ["english", "c_wuhan", "c_hbpu", "aca_llm"]
FIXTURES = ROOT / "tests" / "fixtures"


def conn(p: Path) -> sqlite3.Connection:
    c = sqlite3.connect(str(p))
    c.execute("PRAGMA busy_timeout=30000")
    return c


def counts() -> dict:
    a = conn(DATA / "attempts.sqlite")
    out = {
        "attempts": a.execute("SELECT count(*) FROM attempts").fetchone()[0],
        "judge_queue": a.execute("SELECT count(*) FROM judge_queue").fetchone()[0],
        "test_residue": a.execute(
            "SELECT (SELECT count(*) FROM attempts WHERE source_type='test') + "
            "(SELECT count(*) FROM judge_queue WHERE source_type='test')"
        ).fetchone()[0],
    }
    a.close()
    return out


def snapshot_aux() -> dict:
    """快照没有 source_type 列的三张表（逐行），用于测试后精确恢复。"""
    snap: dict[str, list] = {}
    for subj in SUBJECTS:
        p = DATA / f"{subj}.sqlite"
        if not p.exists():
            continue
        c = conn(p)
        snap[f"{subj}.review_log"] = c.execute("SELECT question_uid, reviewed_at, result FROM review_log").fetchall()
        snap[f"{subj}.wrong_book"] = c.execute(
            "SELECT question_uid, wrong_count, correct_streak, last_wrong_at, next_review_at, mastery, notes, updated_at FROM wrong_book"
        ).fetchall()
        snap[f"{subj}.daily_progress"] = c.execute(
            "SELECT date, total_done, correct_count, wrong_count, subjects FROM daily_progress"
        ).fetchall()
        c.close()
    return snap


def restore_aux(snap: dict) -> None:
    for key, rows in snap.items():
        subj, table = key.split(".")
        c = conn(DATA / f"{subj}.sqlite")
        c.execute(f"DELETE FROM {table}")
        if rows:
            ph = ",".join("?" * len(rows[0]))
            c.executemany(f"INSERT INTO {table} VALUES ({ph})", rows)
        c.commit()
        c.close()


def run_script(*args: str, timeout: int = 300) -> tuple[int, str]:
    p = subprocess.run([PY, *args], capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=str(ROOT), timeout=timeout)
    return p.returncode, (p.stdout or "").strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=int((ROOT / "app" / "port.txt").read_text().strip() or 5000))
    args = ap.parse_args()
    base = f"http://127.0.0.1:{args.port}"
    results: list[tuple[str, bool, str]] = []

    # ---- 前置检查：本测试**不自起服务**，它打的是"当前在跑的那个网页版"。
    # 端口从 `app/port.txt` 读；如果那里是个已经关闭的端口（例如被临时验证脚本覆盖过），
    # 后面每一步都会以"连接被拒绝"惨败，报错却看不出真因 —— 这里先讲清楚。
    try:
        import requests as _rq
        _rq.get(base + "/api/progress?date=today", timeout=5)
    except Exception as exc:  # noqa: BLE001
        print(f"[前置检查失败] 无法连接 {base} —— 本测试需要**先启动网页版**（双击 启动.bat，"
              f"或跑 app\\backend\\app.py），端口取自 app\\port.txt。")
        print(f"               实际错误: {type(exc).__name__}: {exc}")
        print(f"               如端口不对，可用 --port 指定（当前文件里的值：{args.port}）。")
        return 2

    # ---- 0) 快照
    rc, out = run_script("scripts/backup.py", "--keep", "7")
    snap_dir = ""
    try:
        snap_dir = json.loads(out.splitlines()[-1]).get("backup_dir", "")
    except Exception:  # noqa: BLE001
        pass
    results.append(("0 备份快照", rc == 0 and bool(snap_dir), snap_dir or out[-120:]))
    baseline = counts()
    aux = snapshot_aux()

    test_uids: set[str] = set()
    try:
        # ---- 1) ACA 本地规则判分：10 道入队（source_type='test'）
        a = conn(DATA / "attempts.sqlite")
        aca = conn(DATA / "aca_llm.sqlite")
        aca_rows = aca.execute("SELECT question_uid, answer FROM questions LIMIT 10").fetchall()
        aca.close()
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for i, (uid, ans) in enumerate(aca_rows):
            test_uids.add(uid)
            aid = f"e2e-aca-{i:02d}"
            a.execute("INSERT OR REPLACE INTO judge_queue(attempt_id, subject, question_uid, user_answer, "
                      "judge_status, source_type, created_at) VALUES(?,?,?,?, 'pending','test',?)",
                      (aid, "aca_llm", uid, ans if i % 3 else "A", ts))
            a.execute("INSERT OR REPLACE INTO attempts(attempt_id, question_uid, subject, user_answer, "
                      "synced, source_type, created_at) VALUES(?,?,?,?,0,'test',?)",
                      (aid, uid, "aca_llm", ans if i % 3 else "A", ts))
        a.commit()
        a.close()
        results.append(("1 ACA 入队 10 道", len(aca_rows) == 10, f"{len(aca_rows)} 条"))

        # ---- 2) 英语入队：POST /api/submit ×10（再用 UPDATE 打 test 标记）
        FIXTURES.mkdir(parents=True, exist_ok=True)
        eng = conn(DATA / "english.sqlite")
        eng_rows = eng.execute("SELECT question_uid, answer FROM questions LIMIT 10").fetchall()
        eng.close()
        fake = [{"question_uid": u, "subject": "english",
                 "user_answer": (a_ or "") if i % 4 else "（假答案：故意答错）", "elapsed_ms": 800 + i * 37}
                for i, (u, a_) in enumerate(eng_rows)]
        (FIXTURES / "stage9_fake_answers.json").write_text(json.dumps(fake, ensure_ascii=False, indent=2), encoding="utf-8")
        posted = []
        local_judged = 0
        for item in fake:
            r = requests.post(f"{base}/api/submit", json=item, timeout=20)
            if r.status_code in (200, 201):
                body = r.json()
                posted.append(body.get("attempt_id"))
                # 需求 2 之后：客观题/填空等**当场本地规则判分**（status=synced、判分模型 local_rule），
                # 只有写作/整段翻译这类主观题才会留在 pending 等 AI。
                if body.get("status") == "synced" and body.get("judged_by") == "local_rule":
                    local_judged += 1
        a = conn(DATA / "attempts.sqlite")
        for aid in posted:
            a.execute("UPDATE judge_queue SET source_type='test' WHERE attempt_id=?", (aid,))
            a.execute("UPDATE attempts SET source_type='test' WHERE attempt_id=?", (aid,))
            row = a.execute("SELECT question_uid FROM attempts WHERE attempt_id=?", (aid,)).fetchone()
            if row:
                test_uids.add(row[0])
        a.commit()
        pend = a.execute("SELECT count(*) FROM judge_queue WHERE judge_status='pending' AND source_type='test'").fetchone()[0]
        # 契约：10 道题**全部有归宿** —— 要么本地规则判完（synced），要么进 pending 等 AI
        judged_local = a.execute("SELECT count(*) FROM judge_queue WHERE judge_status='synced' AND "
                                 "source_type='test' AND judge_model='local_rule'").fetchone()[0]
        a.close()
        results.append(("2 英语 POST 入队 10 道",
                        len(posted) == 10 and (judged_local + pend) >= 10,
                        f"posted={len(posted)} 本地规则判分={judged_local}（本次响应 {local_judged}）pending={pend}"))

        # ---- 3) 批处理（mock 判分）
        rc, out = run_script("scripts/sync_outbox.py", "--mock")
        synced = failed = -1
        try:
            j = json.loads(out)
            synced, failed = j.get("synced", -1), j.get("failed", -1)
        except Exception:  # noqa: BLE001
            pass
        a = conn(DATA / "attempts.sqlite")
        st = dict(a.execute("SELECT judge_status, count(*) FROM judge_queue WHERE source_type='test' GROUP BY 1").fetchall())
        a.close()
        results.append(("3 批处理状态流转", rc == 0 and failed == 0 and st.get("pending", 0) == 0,
                        f"synced={synced} failed={failed} 状态={st}"))

        # ---- 4) 进度聚合
        rc, out = run_script("scripts/update_daily_progress.py")
        today = datetime.now().strftime("%Y-%m-%d")
        dp = 0
        for subj in SUBJECTS:
            c = conn(DATA / f"{subj}.sqlite")
            dp += c.execute("SELECT count(*) FROM daily_progress WHERE date=?", (today,)).fetchone()[0]
            c.close()
        results.append(("4 进度聚合", rc == 0 and dp >= 1, f"当日记录 {dp} 条"))

        # ---- 5) SM-2
        rc, out = run_script("scripts/sm2_scheduler.py")
        nz = 0
        for subj in SUBJECTS:
            c = conn(DATA / f"{subj}.sqlite")
            nz += c.execute("SELECT count(*) FROM wrong_book WHERE next_review_at IS NOT NULL AND next_review_at<>''").fetchone()[0]
            c.close()
        results.append(("5 SM-2 排程", rc == 0 and nz >= 1, f"next_review_at 非空 {nz} 条"))

        # ---- 6) 复盘报告
        a = conn(DATA / "attempts.sqlite")
        aca_stat = a.execute("SELECT count(*), round(avg(judge_score),2) FROM attempts WHERE subject='aca_llm' AND source_type='test'").fetchone()
        eng_stat = a.execute("SELECT judge_status, count(*) FROM judge_queue WHERE subject='english' AND source_type='test' GROUP BY 1").fetchall()
        a.close()
        wrong = 0
        for subj in SUBJECTS:
            c = conn(DATA / f"{subj}.sqlite")
            wrong += c.execute("SELECT count(*) FROM wrong_book").fetchone()[0]
            c.close()
        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "aca": {"attempts": aca_stat[0], "avg_score": aca_stat[1], "full_score": 2.0},
            "english": {"queue_states": dict(eng_stat)},
            "wrong_book_total": wrong,
            "tokens": 0,
            "tokens_note": "mock 模式下无真实 API 调用 → token 记 0（不编造估算值）",
        }
        (ROOT / "logs" / "stage9_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        results.append(("6 复盘报告", True, json.dumps(report["aca"], ensure_ascii=False)))

    finally:
        # ---- 清理：按 test 标记删除 + 恢复无标记的三张表
        a = conn(DATA / "attempts.sqlite")
        a.execute("DELETE FROM judge_queue WHERE source_type='test'")
        a.execute("DELETE FROM attempts WHERE source_type='test'")
        a.commit()
        a.close()
        restore_aux(aux)

    after = counts()
    clean = after["test_residue"] == 0 and after == baseline
    results.append(("清理校验", clean, f"before={baseline} after={after}"))

    print("=== 阶段 9 端到端结果 ===")
    for name, ok, detail in results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    passed = sum(1 for _, ok, _ in results if ok)
    print(f"\n{passed}/{len(results)} 项通过")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
