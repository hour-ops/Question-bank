#!/usr/bin/env python
"""写路径冒烟：POST /api/submit → judge_queue(pending) → POST /api/sync(mock) → 回写校验。

等价于阶段 -1 的核心链路（提交→入队→判分→回写），不联网（判分走 mock）。
用法: python tests/smoke_submit_sync.py [--port 5000]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=int((ROOT / "app" / "port.txt").read_text().strip() or 5000))
    args = ap.parse_args()
    base = f"http://127.0.0.1:{args.port}"

    conn = sqlite3.connect(str(DATA / "english.sqlite"))
    row = conn.execute(
        "SELECT question_uid, stem, answer FROM questions WHERE question_type='translation_fill' ORDER BY id LIMIT 1"
    ).fetchone()
    conn.close()
    if not row:
        print("FAIL: english 库里没有 translation_fill 题目")
        return 1
    uid, stem, answer = row
    print(f"[1] 选题 {uid} :: {stem[:40]!r}")

    before = {}
    a = sqlite3.connect(str(DATA / "attempts.sqlite"))
    before["queue"] = a.execute("SELECT count(*) FROM judge_queue").fetchone()[0]
    before["attempts"] = a.execute("SELECT count(*) FROM attempts").fetchone()[0]
    a.close()
    e = sqlite3.connect(str(DATA / "english.sqlite"))
    before["review_log"] = e.execute("SELECT count(*) FROM review_log").fetchone()[0]
    before["wrong_book"] = e.execute("SELECT count(*) FROM wrong_book").fetchone()[0]
    e.close()
    print(f"[2] 提交前: {before}")

    r = requests.post(f"{base}/api/submit", json={
        "question_uid": uid, "subject": "english",
        "user_answer": "我过去常每天练两个小时钢琴。", "elapsed_ms": 1234,
    }, timeout=20)
    print(f"[3] POST /api/submit → {r.status_code} {r.text[:200]}")
    if r.status_code not in (200, 201):  # 201 Created 是正确语义
        return 1
    attempt_id = (r.json() or {}).get("attempt_id")

    a = sqlite3.connect(str(DATA / "attempts.sqlite"))
    pend = a.execute("SELECT count(*) FROM judge_queue WHERE judge_status='pending'").fetchone()[0]
    a.close()
    print(f"[4] judge_queue pending = {pend}（应 >=1）")

    r2 = requests.post(f"{base}/api/sync?mock=1", timeout=180)
    res = (r2.json() or {}).get("result") or {}
    print(f"[5] POST /api/sync(mock) → {r2.status_code} synced={res.get('synced')} failed={res.get('failed')}")

    a = sqlite3.connect(str(DATA / "attempts.sqlite"))
    after = {
        "queue": a.execute("SELECT count(*) FROM judge_queue").fetchone()[0],
        "synced": a.execute("SELECT count(*) FROM judge_queue WHERE judge_status='synced'").fetchone()[0],
        "attempts": a.execute("SELECT count(*) FROM attempts").fetchone()[0],
        "attempt_synced": a.execute("SELECT count(*) FROM attempts WHERE synced=1").fetchone()[0],
        "row": a.execute("SELECT judge_score, judge_model FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone(),
    }
    a.close()
    e = sqlite3.connect(str(DATA / "english.sqlite"))
    after["review_log"] = e.execute("SELECT count(*) FROM review_log").fetchone()[0]
    after["wrong_book"] = e.execute("SELECT count(*) FROM wrong_book").fetchone()[0]
    e.close()
    print(f"[6] 提交后: {after}")

    ok = (
        after["queue"] >= before["queue"] + 1
        and after["synced"] >= 1
        and after["attempts"] >= before["attempts"] + 1
        and after["review_log"] >= before["review_log"] + 1  # 历史遗留 pending 可能一并同步，用 >=
    )
    print("[7] " + ("PASS 写路径全链路打通（attempts + judge_queue + review_log 均已回写）" if ok else "FAIL 回写不完整"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
