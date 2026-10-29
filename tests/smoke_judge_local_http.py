#!/usr/bin/env python
"""真实 HTTP 冒烟：起便携版服务 → 提交一题 → 校验规则判分/进度 → 清理并停服。

用法（在题库项目目录下）:
    python .tmp_smoke_http.py            # 默认打便携版目录
    python .tmp_smoke_http.py --target .  # 打当前目录

⚠️ 会在 attempts/科目库里留下本次的 attempt 与 review_log 行，脚本退出前**清理掉**
（只删自己造的那几行，绝不删历史数据）。
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

PY = r"C:\Users\win11_vmusers\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def post(url: str, payload: dict) -> tuple[int, dict]:
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8") or "{}")


def get(url: str) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(url, timeout=60) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8") or "{}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default=r"C:\Users\win11_vmusers\Desktop\题库项目_便携版")
    args = ap.parse_args()
    root = Path(args.target).resolve()
    print(f"[smoke] target = {root}")

    port = free_port()
    env = dict(os.environ, PYTHONIOENCODING="utf-8", DSH_SMOKE_PORT=str(port))
    log = root / ".tmp_smoke_server.log"
    with log.open("wb") as fh:
        proc = subprocess.Popen([PY, "-X", "utf8", "-B", "app/backend/app.py", "--port", str(port)],
                                cwd=str(root), env=env, stdout=fh, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    try:
        # 等服务就绪
        ready = False
        for _ in range(60):
            if proc.poll() is not None:
                break
            try:
                code, _body = get(base + "/api/progress?date=today")
                if code == 200:
                    ready = True
                    break
            except Exception:  # noqa: BLE001
                pass
            time.sleep(0.5)
        if not ready:
            print("[smoke] 服务未就绪，日志尾部：")
            print(log.read_text(encoding="utf-8", errors="replace")[-1500:])
            return 1
        print(f"[smoke] 服务已就绪 {base}")

        # 找一道规则可判的真题（c_wuhan 单选，答案 A-D 单字母）
        qdb = root / "data" / "c_wuhan.sqlite"
        conn = sqlite3.connect(qdb.resolve().as_uri() + "?mode=ro", uri=True)
        row = conn.execute("SELECT question_uid, answer, question_type FROM questions "
                           "WHERE question_type='single_choice' AND length(answer)=1 LIMIT 1").fetchone()
        conn.close()
        uid, answer, qtype = row
        print(f"[smoke] 取题 {uid} type={qtype} answer={answer!r}")
        c0 = sqlite3.connect(qdb)
        rl_before = c0.execute("SELECT COALESCE(MAX(id), 0) FROM review_log").fetchone()[0]
        c0.close()

        # ① 答对
        code, body = post(base + "/api/submit",
                          {"question_uid": uid, "subject": "c_wuhan", "user_answer": answer})
        print(f"[smoke] submit(对) -> {code} status={body.get('status')} judged_by={body.get('judged_by')} "
              f"score={body.get('judge_score')}/{body.get('full_score')} correct={body.get('correct')}")
        assert code == 201 and body.get("status") == "synced" and body.get("correct") is True, body
        att_ok = body["attempt_id"]

        # ② 答错
        wrong = next((c for c in "ABCD" if c != str(answer).upper()), "B")
        code, body2 = post(base + "/api/submit",
                           {"question_uid": uid, "subject": "c_wuhan", "user_answer": wrong})
        print(f"[smoke] submit(错) -> {code} status={body2.get('status')} correct={body2.get('correct')}")
        assert code == 201 and body2.get("status") == "synced" and body2.get("correct") is False, body2
        att_bad = body2["attempt_id"]

        # ③ 今日进度（需求 10：立即更新，不再等 AI）
        code, prog = get(base + "/api/progress?date=today")
        cw = (prog.get("subjects") or {}).get("c_wuhan") or {}
        print(f"[smoke] progress -> {code} c_wuhan total={cw.get('total_done')} "
              f"correct={cw.get('correct_count')} wrong={cw.get('wrong_count')} "
              f"accuracy={cw.get('accuracy')}")
        assert cw.get("total_done", 0) >= 2, prog
        assert cw.get("correct_count", 0) >= 1 and cw.get("wrong_count", 0) >= 1, prog

        # ④ /api/judge_local 单条重判（幂等）
        code, jl = post(base + "/api/judge_local", {"attempt_id": att_ok})
        item = (jl.get("results") or [{}])[0]
        print(f"[smoke] judge_local -> {code} gradeable={item.get('gradeable')} correct={item.get('correct')}")
        assert item.get("gradeable") and item.get("correct") is True, jl

        # ⑤ 队列里不应留 pending（规则判分已同步）
        adb = root / "data" / "attempts.sqlite"
        c2 = sqlite3.connect(adb)
        pend = c2.execute("SELECT count(*) FROM judge_queue WHERE judge_status='pending'").fetchone()[0]
        synced = c2.execute("SELECT count(*) FROM judge_queue WHERE judge_status='synced' "
                            "AND attempt_id IN (?,?)", (att_ok, att_bad)).fetchone()[0]
        c2.close()
        print(f"[smoke] queue pending={pend} synced(本次两条)={synced}")
        assert synced == 2, "本次两条应都是 synced"

        # ⑥ 清理：只删本次造的行（review_log 按 id 前后差值精确圈定，绝不碰历史）
        c4 = sqlite3.connect(qdb)
        new_ids = [r[0] for r in c4.execute("SELECT id FROM review_log WHERE id > ?", (rl_before,))]
        for rid in new_ids:
            c4.execute("DELETE FROM review_log WHERE id = ?", (rid,))
        c4.commit()
        c4.close()
        c3 = sqlite3.connect(adb)
        c3.execute("DELETE FROM attempts WHERE attempt_id IN (?,?)", (att_ok, att_bad))
        c3.execute("DELETE FROM judge_queue WHERE attempt_id IN (?,?)", (att_ok, att_bad))
        c3.commit()
        c3.close()
        print(f"[smoke] 已清理本次写入的 attempts / judge_queue / review_log（review_log 删了 {len(new_ids)} 行）")
        print("[smoke] ✅ 全部通过")
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        try:
            log.unlink()
        except OSError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
