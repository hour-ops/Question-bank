#!/usr/bin/env python
"""阶段 8 · Web UI 离线测试（`Flask.test_client()`，**不真起服务器、不占端口、不联网**）。

覆盖（对应阶段 8 提示词的 ①–⑦）：
  ① `/` 与 `/quiz`（乃至 7 个页面全部）返回 200
  ② `/api/questions` 返回 JSON 且条数受 `limit` 限制
  ③ `POST /api/submit` 后 `judge_queue` 多一条 `pending`，`attempts` 同步新增
  ④ `POST /review/action`：通过 → `approved`；拒绝 → `rejected` 且写 `review_rejects.jsonl`
     且 **`config/distractors.json` 字节未变**
  ⑤ `/api/progress` 形状正确
  ⑥ 队列页 HTML 含四态关键字（含 `failed`）且 failed 行有「手动重投」
  ⑦ 页面 HTML 不含 `http://` / `https://` 外链资源（防 CDN 回归）
外加（同一阶段的自检项）：
  ⑧ `failed` 可手动重投（`POST /api/requeue`）
  ⑨ 只读接口不写库（主库 mtime/size 与行数不变）
  ⑩ `POST /api/sync` 走 `--mock` 子进程（用路径重定向包装器跑真实的 `sync_outbox.main()`，
     避免测试污染项目真实 `data/`）

⚠️ 临时库/目录只放 `tests/.tmp/web_ui/`（`tests/.tmp` 是共享目录，只清自己的子目录）。
⚠️ 不用 `tempfile.TemporaryDirectory()`：本机沙箱拒绝对系统临时目录做删除（WinError 5）。

运行: python tests/test_web_ui.py
"""

from __future__ import annotations

import contextlib
import json
import shutil
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app" / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

import init_db  # noqa: E402
import app as webapp  # noqa: E402  ← app/backend/app.py（模块名就叫 app）

TMPROOT = ROOT / "tests" / ".tmp" / "web_ui"
SUBJECTS = ("english", "c_wuhan", "c_hbpu", "aca_llm")
DISTRACTORS = ROOT / "config" / "distractors.json"


# --------------------------------------------------------------------- 夹具


def _new_db(path: Path, schema: str) -> None:
    conn = init_db.connect(path)
    conn.executescript(schema)
    conn.commit()
    conn.close()


@contextlib.contextmanager
def web_env(name: str):
    """建一套隔离的 data/logs/output，并把 app 模块的目录全局指过去（“monkeypatch”）。"""
    base = TMPROOT / name
    shutil.rmtree(base, ignore_errors=True)
    data, logs, output = base / "data", base / "logs", base / "output"
    for d in (data, logs, output / "papers"):
        d.mkdir(parents=True, exist_ok=True)
    for subject in SUBJECTS:
        _new_db(data / f"{subject}.sqlite", init_db.SUBJECT_SCHEMA)
    _new_db(data / "attempts.sqlite", init_db.ATTEMPTS_SCHEMA)

    saved = (webapp.DATA_DIR, webapp.LOGS_DIR, webapp.OUTPUT_DIR, webapp.SYNC_SCRIPT)
    webapp.DATA_DIR, webapp.LOGS_DIR, webapp.OUTPUT_DIR = data, logs, output
    webapp.app.config["TESTING"] = True
    env = SimpleNamespace(base=base, data=data, logs=logs, output=output, client=webapp.app.test_client())
    try:
        yield env
    finally:
        webapp.DATA_DIR, webapp.LOGS_DIR, webapp.OUTPUT_DIR, webapp.SYNC_SCRIPT = saved
        webapp.app.config["TESTING"] = False


def add_question(data: Path, subject: str, uid: str, **kw) -> None:
    fields = {
        "question_uid": uid, "subject": subject, "question_type": "single_choice",
        "stem": f"题干 {uid}", "options": json.dumps([{"key": "A", "text": "甲"}, {"key": "B", "text": "乙"}]),
        "answer": "A", "explanation": "因为 A", "difficulty": "易", "status": "approved",
        "knowledge_point": "kp-1", "source_url": "local://demo", "fact_claim": "声明",
        "fact_source": "教材", "fact_verified": 0,
    }
    fields.update(kw)
    cols = ", ".join(fields)
    marks = ", ".join("?" for _ in fields)
    conn = sqlite3.connect(str(data / f"{subject}.sqlite"))
    conn.execute(f"INSERT INTO questions({cols}) VALUES({marks})", list(fields.values()))
    conn.commit()
    conn.close()


def add_queue_row(data: Path, attempt_id: str, subject: str, uid: str, status: str, **kw) -> None:
    conn = sqlite3.connect(str(data / "attempts.sqlite"))
    conn.execute(
        "INSERT INTO attempts(attempt_id, question_uid, subject, user_answer, elapsed_ms, synced, source_type, created_at)"
        " VALUES(?,?,?,?,?,0,'ui',?)",
        (attempt_id, uid, subject, kw.get("user_answer", "A"), 1200, "2026-01-01T00:00:00+00:00"),
    )
    conn.execute(
        "INSERT INTO judge_queue(attempt_id, subject, question_uid, user_answer, judge_status, judge_reason,"
        " source_type, created_at) VALUES(?,?,?,?,?,?,'ui',?)",
        (attempt_id, subject, uid, kw.get("user_answer", "A"), status,
         kw.get("judge_reason"), "2026-01-01T00:00:00+00:00"),
    )
    conn.commit()
    conn.close()


def scalar(path: Path, sql: str, params=()):
    conn = sqlite3.connect(str(path))
    try:
        row = conn.execute(sql, params).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def fetch(path: Path, sql: str, params=()):
    conn = sqlite3.connect(str(path))
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


# --------------------------------------------------------------------- ① 页面


def test_pages_return_200() -> None:
    with web_env("pages") as env:
        for path in ("/", "/quiz", "/analysis", "/compare", "/queue", "/settings", "/review"):
            resp = env.client.get(path)
            assert resp.status_code == 200, f"{path} → {resp.status_code}"
            assert b"<!DOCTYPE html>" in resp.data, f"{path} 未返回 HTML"
        assert env.client.get("/quiz").status_code == 200


def test_unknown_route_404() -> None:
    with web_env("pages404") as env:
        assert env.client.get("/nope").status_code == 404


# --------------------------------------------------------------------- ② questions


def test_api_questions_json_and_limit() -> None:
    with web_env("questions") as env:
        for i in range(5):
            add_question(env.data, "english", f"uid-{i}")
        add_question(env.data, "aca_llm", "uid-aca", question_type="single_choice")

        resp = env.client.get("/api/questions?subject=english")
        assert resp.status_code == 200
        assert resp.headers["Content-Type"].startswith("application/json")
        full = resp.get_json()
        assert full["count"] == 5, f"english 应有 5 题，实际 {full['count']}"

        lim = env.client.get("/api/questions?subject=english&limit=2").get_json()
        assert lim["count"] == 2 and len(lim["questions"]) == 2, "limit 未生效"

        zero = env.client.get("/api/questions?subject=english&limit=0").get_json()
        assert zero["count"] == 0, "limit=0 应返回 0 条"

        no_reveal = lim["questions"][0]
        assert "answer" not in no_reveal, "默认不应回传答案（reveal=0）"
        reveal = env.client.get("/api/questions?subject=english&limit=1&reveal=1").get_json()
        assert reveal["questions"][0]["answer"] == "A", "reveal=1 应回传答案"
        assert reveal["questions"][0]["options_parsed"][0]["key"] == "A"

        one = env.client.get("/api/questions?subject=aca_llm").get_json()
        assert one["count"] == 1
        bad = env.client.get("/api/questions?subject=nope")
        assert bad.status_code == 400, "未知科目应 400"


# --------------------------------------------------------------------- ③ submit


def test_submit_writes_attempt_and_pending_queue() -> None:
    """③ 提交后 `attempts` +1、`judge_queue` +1。

    ⚠️ 需求 2 之后行为分两支（细则见 `tests/test_judge_local.py`）：
      - **规则可判**的题（本题是 `single_choice` 答案 A）→ 当场 `synced` 并出分，不花钱；
      - **主观题**（写作/整段翻译）→ 仍是 `pending`，等 AI 判分（老行为）。
    本用例两支都覆盖，因为"队列页能看到 pending"是 UI 的硬需求。
    """
    with web_env("submit") as env:
        add_question(env.data, "english", "uid-s1")
        add_question(env.data, "english", "uid-w1", question_type="writing",
                     stem="Write an essay.", answer="Model essay.")
        attempts_db = env.data / "attempts.sqlite"
        before_a = scalar(attempts_db, "SELECT count(*) FROM attempts") or 0
        before_q = scalar(attempts_db, "SELECT count(*) FROM judge_queue") or 0

        resp = env.client.post("/api/submit", json={
            "question_uid": "uid-s1", "subject": "english", "user_answer": "A", "elapsed_ms": 3210,
        })
        assert resp.status_code in (200, 201), resp.data[:400]
        body = resp.get_json()
        assert body["attempt_id"], body
        assert body["status"] == "synced" and body["judged_by"] == "local_rule", body

        assert (scalar(attempts_db, "SELECT count(*) FROM attempts") or 0) == before_a + 1
        assert (scalar(attempts_db, "SELECT count(*) FROM judge_queue") or 0) == before_q + 1
        row = fetch(attempts_db, "SELECT judge_status, user_answer FROM judge_queue WHERE attempt_id=?",
                    (body["attempt_id"],))
        assert len(row) == 1 and row[0][0] == "synced", f"客观题应立即 synced: {row}"
        assert row[0][1] == "A"
        assert scalar(attempts_db, "SELECT elapsed_ms FROM attempts WHERE attempt_id=?",
                      (body["attempt_id"],)) == 3210
        assert scalar(attempts_db, "SELECT synced FROM attempts WHERE attempt_id=?",
                      (body["attempt_id"],)) == 1

        # 主观题：仍进 pending 队列（老行为，UI 队列页要能看到）
        resp_w = env.client.post("/api/submit", json={
            "question_uid": "uid-w1", "subject": "english", "user_answer": "my essay"})
        assert resp_w.status_code in (200, 201), resp_w.data[:400]
        body_w = resp_w.get_json()
        assert body_w["status"] == "pending", body_w
        row_w = fetch(attempts_db, "SELECT judge_status FROM judge_queue WHERE attempt_id=?",
                      (body_w["attempt_id"],))
        assert row_w[0][0] == "pending", f"主观题应保持 pending: {row_w}"
        assert scalar(attempts_db, "SELECT count(*) FROM judge_queue WHERE judge_status='pending'") == 1

        # /api/attempts 同步可见
        listed = env.client.get("/api/attempts?subject=english").get_json()
        assert listed["count"] == 2, listed["count"]

        # 参数校验
        assert env.client.post("/api/submit", json={"subject": "english"}).status_code == 400
        assert env.client.post("/api/submit", json={"question_uid": "x", "subject": "nope"}).status_code == 400


# --------------------------------------------------------------------- ④ review


def test_review_action_approve_reject_and_distractors_untouched() -> None:
    before_bytes = DISTRACTORS.read_bytes() if DISTRACTORS.exists() else b"<missing>"

    with web_env("review") as env:
        add_question(env.data, "english", "uid-a1", status="pending_review", version=0)
        add_question(env.data, "english", "uid-r1", status="pending_review", version=0)
        db = env.data / "english.sqlite"

        # 拒绝缺原因 → 400（不得写库）
        resp = env.client.post("/review/action", json={
            "question_uid": "uid-r1", "subject": "english", "decision": "拒绝"})
        assert resp.status_code == 400, resp.data[:300]
        assert "拒绝必须选择原因" in resp.get_json()["error"]
        assert scalar(db, "SELECT status FROM questions WHERE question_uid='uid-r1'") == "pending_review"

        # 通过
        resp = env.client.post("/review/action", json={
            "question_uid": "uid-a1", "subject": "english", "decision": "通过"})
        assert resp.status_code == 200, resp.data[:300]
        assert resp.get_json()["status"] == "approved"
        assert scalar(db, "SELECT status FROM questions WHERE question_uid='uid-a1'") == "approved"
        assert scalar(db, "SELECT reviewed_by FROM questions WHERE question_uid='uid-a1'") == "human"
        assert scalar(db, "SELECT version FROM questions WHERE question_uid='uid-a1'") == 1
        logs = fetch(db, "SELECT result FROM review_log WHERE question_uid='uid-a1'")
        assert [r[0] for r in logs] == ["approved"], logs

        # 拒绝（英文别名 rejected + 合法原因）
        resp = env.client.post("/review/action", json={
            "question_uid": "uid-r1", "subject": "english", "decision": "reject", "reason": "答案错误"})
        assert resp.status_code == 200, resp.data[:300]
        body = resp.get_json()
        assert body["status"] == "rejected" and body["reason"] == "答案错误" and body["reason_logged"] is True
        assert scalar(db, "SELECT status FROM questions WHERE question_uid='uid-r1'") == "rejected"

        reject_log = env.logs / "review_rejects.jsonl"
        assert reject_log.exists(), "拒绝原因必须写 logs/review_rejects.jsonl"
        lines = [json.loads(x) for x in reject_log.read_text(encoding="utf-8").splitlines() if x.strip()]
        assert len(lines) == 1
        assert lines[0]["question_uid"] == "uid-r1" and lines[0]["reason"] == "答案错误"
        assert lines[0]["subject"] == "english" and lines[0]["source"] == "web_ui"

        # 非法原因 → 400
        bad = env.client.post("/review/action", json={
            "question_uid": "uid-r1", "subject": "english", "decision": "拒绝", "reason": "心情不好"})
        assert bad.status_code == 400 and len(bad.get_json()["allowed"]) == 7

        # 未知 decision / 不存在的题
        assert env.client.post("/review/action", json={
            "question_uid": "uid-r1", "subject": "english", "decision": "maybe"}).status_code == 400
        assert env.client.post("/review/action", json={
            "question_uid": "nope", "subject": "english", "decision": "通过"}).status_code == 404

    after_bytes = DISTRACTORS.read_bytes() if DISTRACTORS.exists() else b"<missing>"
    assert after_bytes == before_bytes, "config/distractors.json 被改动了（只应写 logs/review_rejects.jsonl）"
    assert b"uid-r1" not in after_bytes and "答案错误".encode("utf-8") not in after_bytes


def test_review_edit_keeps_pending_review() -> None:
    with web_env("review_edit") as env:
        add_question(env.data, "english", "uid-e1", status="pending_review", version=0)
        db = env.data / "english.sqlite"
        resp = env.client.post("/review/action", json={
            "question_uid": "uid-e1", "subject": "english", "decision": "修改",
            "stem": "改后的题干", "answer": "B", "explanation": "改后的解析"})
        assert resp.status_code == 200 and resp.get_json()["status"] == "pending_review"
        assert scalar(db, "SELECT status FROM questions WHERE question_uid='uid-e1'") == "pending_review"
        assert scalar(db, "SELECT stem FROM questions WHERE question_uid='uid-e1'") == "改后的题干"
        assert scalar(db, "SELECT answer FROM questions WHERE question_uid='uid-e1'") == "B"
        assert scalar(db, "SELECT version FROM questions WHERE question_uid='uid-e1'") == 1
        # 页面仍能列出该题（一屏一题）
        html = env.client.get("/review").get_data(as_text=True)
        assert "改后的题干" in html and "pending_review" in html


# --------------------------------------------------------------------- ⑤ progress


def test_api_progress_shape() -> None:
    with web_env("progress") as env:
        conn = sqlite3.connect(str(env.data / "english.sqlite"))
        conn.execute("INSERT INTO daily_progress(date, total_done, correct_count, wrong_count, subjects)"
                     " VALUES(?,?,?,?,?)", ("2026-01-02", 4, 3, 1, json.dumps({"grammar_fill": 4})))
        conn.commit()
        conn.close()

        data = env.client.get("/api/progress?date=2026-01-02").get_json()
        for key in ("date", "total_done", "correct_count", "wrong_count", "accuracy", "subjects",
                    "due_review", "judge_queue", "generated_at"):
            assert key in data, f"/api/progress 缺字段 {key}"
        assert data["date"] == "2026-01-02"
        assert data["total_done"] == 4 and data["correct_count"] == 3 and data["wrong_count"] == 1
        assert abs(data["accuracy"] - 0.75) < 1e-6, data["accuracy"]
        assert isinstance(data["subjects"], dict) and set(data["subjects"]) >= {"english"}
        assert data["subjects"]["english"]["total_done"] == 4
        assert isinstance(data["due_review"], int)
        assert set(data["judge_queue"]) == {"pending", "submitted", "synced", "failed"}

        today = env.client.get("/api/progress?date=today").get_json()
        assert len(today["date"]) == 10 and today["total_done"] == 0
        assert env.client.get("/api/progress?date=2026-1-2").status_code == 400


# --------------------------------------------------------------------- ⑥ 四态


def test_queue_page_shows_four_states_and_requeue() -> None:
    with web_env("queue") as env:
        for status in ("pending", "submitted", "synced", "failed"):
            add_question(env.data, "aca_llm", f"uid-{status}")
            add_queue_row(env.data, f"att-{status}", "aca_llm", f"uid-{status}", status,
                          judge_reason="retry 3x: boom" if status == "failed" else None)

        html = env.client.get("/queue").get_data(as_text=True)
        for status in ("pending", "submitted", "synced", "failed"):
            assert status in html, f"队列页缺少四态关键字 {status}"
            assert f'badge-{status}' in html, f"缺少 {status} 徽标样式"
        assert 'data-status="failed"' in html, "缺少 failed 行的 data-status"
        assert "手动重投" in html and "requeue" in html, "failed 必须有手动重投按钮"
        assert "retry 3x: boom" in html, "应展示失败原因"

        # 计数与筛选
        data = env.client.get("/api/queue").get_json()
        assert data["counts"] == {"pending": 1, "submitted": 1, "synced": 1, "failed": 1}, data["counts"]
        only = env.client.get("/queue?status=failed").get_data(as_text=True)
        assert 'data-status="failed"' in only and 'data-status="synced"' not in only
        assert env.client.get("/api/queue?status=bogus").status_code == 400


def test_requeue_failed_only() -> None:
    with web_env("requeue") as env:
        add_queue_row(env.data, "att-f", "english", "uid-f", "failed", judge_reason="boom")
        add_queue_row(env.data, "att-p", "english", "uid-p", "pending")
        db = env.data / "attempts.sqlite"

        assert env.client.post("/api/requeue", json={"attempt_id": "att-missing"}).status_code == 404
        denied = env.client.post("/api/requeue", json={"attempt_id": "att-p"})
        assert denied.status_code == 400, "非 failed 不应允许重投"

        ok = env.client.post("/api/requeue", json={"attempt_id": "att-f"})
        assert ok.status_code == 200 and ok.get_json()["status"] == "pending"
        assert scalar(db, "SELECT judge_status FROM judge_queue WHERE attempt_id='att-f'") == "pending"
        assert scalar(db, "SELECT judge_reason FROM judge_queue WHERE attempt_id='att-f'").count("手动重投") == 1


# --------------------------------------------------------------------- ⑦ 无外链


def test_pages_have_no_external_resources() -> None:
    with web_env("noexternal") as env:
        for path in ("/", "/quiz", "/analysis", "/compare", "/queue", "/settings", "/review"):
            html = env.client.get(path).get_data(as_text=True)
            assert "http://" not in html, f"{path} 出现 http:// 外链"
            assert "https://" not in html, f"{path} 出现 https:// 外链"
            assert "//cdn" not in html and "unpkg" not in html and "jsdelivr" not in html

    # 静态资源本身也要零外链 / 零 @import
    for path in sorted((webapp.STATIC_DIR).rglob("*")):
        if path.suffix.lower() not in (".css", ".js"):
            continue
        text = path.read_text(encoding="utf-8")
        assert "http://" not in text, f"{path.name} 含 http://"
        assert "https://" not in text, f"{path.name} 含 https://"
        assert "//cdn" not in text, f"{path.name} 含 CDN"
        if path.suffix == ".css":
            assert "@import" not in text, f"{path.name} 含 @import"

    # 模板源码里的资源属性不得指向绝对地址
    for path in sorted(webapp.TEMPLATE_DIR.glob("*.html")):
        text = path.read_text(encoding="utf-8")
        for attr in ('src="http', "src='http", 'href="http', "href='http", "src=\"//", 'href="//'):
            assert attr not in text, f"{path.name} 含外链资源属性 {attr}"


# --------------------------------------------------------------------- ⑨ 只读不写库


def test_readonly_endpoints_do_not_write_db() -> None:
    with web_env("readonly") as env:
        add_question(env.data, "english", "uid-ro")
        add_queue_row(env.data, "att-ro", "english", "uid-ro", "pending")
        watched = [env.data / f"{s}.sqlite" for s in SUBJECTS] + [env.data / "attempts.sqlite"]
        counts = {p: scalar(p, "SELECT count(*) FROM sqlite_master") for p in watched}
        before = {p: (p.stat().st_size, p.stat().st_mtime_ns) for p in watched}

        for path in ("/", "/quiz", "/analysis", "/compare", "/queue", "/settings", "/review"):
            env.client.get(path)
        for api in ("/api/questions?subject=english", "/api/progress?date=today",
                    "/api/attempts", "/api/papers", "/api/queue"):
            assert env.client.get(api).status_code == 200

        for p in watched:
            after = (p.stat().st_size, p.stat().st_mtime_ns)
            assert after == before[p], f"只读接口写入了 {p.name}：{before[p]} → {after}"
            assert scalar(p, "SELECT count(*) FROM sqlite_master") == counts[p]


# --------------------------------------------------------------------- ⑩ sync（mock）


SYNC_WRAPPER = '''"""测试用路径重定向包装器：跑**真实的** sync_outbox.main()，但把 DATA/LOGS/ROOT 指到临时根。"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # 临时根（tests/.tmp/web_ui/<name>）
REAL = Path(r"{real_script}")

_spec = importlib.util.spec_from_file_location("sync_outbox_redirected", REAL)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)
mod.ROOT = ROOT
mod.DATA = ROOT / "data"
mod.ATTEMPTS_DB = mod.DATA / "attempts.sqlite"
mod.LOGS = ROOT / "logs"
raise SystemExit(mod.main(sys.argv[1:]))
'''


def _install_sync_wrapper(env) -> None:
    (env.base / "config").mkdir(parents=True, exist_ok=True)
    for name in ("aca_rules.json", "judge_prompt.json"):
        src = ROOT / "config" / name
        if src.exists():
            shutil.copy(src, env.base / "config" / name)
    scripts = env.base / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    wrapper = scripts / "run_sync_outbox.py"
    wrapper.write_text(SYNC_WRAPPER.format(real_script=ROOT / "scripts" / "sync_outbox.py"),
                       encoding="utf-8")
    webapp.SYNC_SCRIPT = wrapper


def test_api_sync_mock_subprocess() -> None:
    with web_env("sync") as env:
        _install_sync_wrapper(env)
        add_question(env.data, "aca_llm", "uid-sync", question_type="single_choice", answer="A")
        add_queue_row(env.data, "att-sync", "aca_llm", "uid-sync", "pending", user_answer="A")
        db = env.data / "attempts.sqlite"

        resp = env.client.post("/api/sync", json={"mock": True})
        assert resp.status_code == 200, resp.data[:400]
        body = resp.get_json()
        assert body["mock"] is True and body["returncode"] == 0, body
        result = body["result"]
        assert result and result.get("mock") is True, f"未解析到 mock 汇总: {body['stdout_tail'][-400:]}"
        assert result["pending"] == 1 and result["synced"] == 1, result
        assert scalar(db, "SELECT judge_status FROM judge_queue WHERE attempt_id='att-sync'") == "synced"
        assert scalar(db, "SELECT synced FROM attempts WHERE attempt_id='att-sync'") == 1

        # 付费闸门：mock=false 且未确认 → 400（不得真跑）
        gate = env.client.post("/api/sync", json={"mock": False})
        assert gate.status_code == 400 and gate.get_json().get("paid_gate") is True


# --------------------------------------------------------------------- 入口


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
