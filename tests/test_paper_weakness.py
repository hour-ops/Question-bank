#!/usr/bin/env python
"""需求 6（套卷模式）+ 需求 8（弱势诊断）离线测试。

特点：**只碰临时库**，用 `test_client()` 不起服务；涉及"交卷写库"的用例在临时
`attempts.sqlite` 上跑，跑完把临时目录整体删掉（不碰用户真实数据）。

覆盖:
  ① `scripts/paper_lib.py`：套卷清单（≥N 题、真卷标记）、按 id 排列 = 原卷顺序、满分累加
  ② `GET /api/paper/list`：分组形状 + `exam_kind` 标注（英语=真题卷 / C 语言=校教材题集）
  ③ `GET /api/paper`：题序 `seq` 从 1 连续、客观题带 `options_parsed`/`answer_keys`
  ④ `POST /api/paper/submit`：整卷判分 —— 对/错分别计分、未作答单列、写作题进 pending、
     写 `attempts(source_type='paper')` + `review_log`，且 **`wrong_book` 一行都不写**
  ⑤ `GET /api/weakness`：形状完整；空库不崩；有作答时能算出弱势知识点与覆盖率
  ⑥ `POST /api/weakness/advice`：默认只回提示词（**不发付费请求**），`confirm_paid` 返回 501 付费闸门

运行: python tests/test_paper_weakness.py
"""

from __future__ import annotations

import contextlib
import json
import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app" / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

import init_db  # noqa: E402
import app as webapp  # noqa: E402
import paper_lib  # noqa: E402
import weakness as weak_lib  # noqa: E402

TMPROOT = ROOT / "tests" / ".tmp" / "paper_weakness"
SUBJECTS = ("english", "c_wuhan", "c_hbpu", "aca_llm")


def _new_db(path: Path, schema: str) -> sqlite3.Connection:
    conn = init_db.connect(path)
    conn.executescript(schema)
    conn.commit()
    return conn


@contextlib.contextmanager
def temp_env(name: str):
    """临时 data/logs/output；paper_lib / weakness / webapp 的路径全部指过去。"""
    base = TMPROOT / name
    shutil.rmtree(base, ignore_errors=True)
    data, logs, output = base / "data", base / "logs", base / "output"
    for d in (data, logs, output / "papers"):
        d.mkdir(parents=True, exist_ok=True)
    for subj in SUBJECTS:
        conn = _new_db(data / f"{subj}.sqlite", init_db.SUBJECT_SCHEMA)
        conn.close()
    conn = _new_db(data / "attempts.sqlite", init_db.ATTEMPTS_SCHEMA)
    conn.close()

    saved = (webapp.DATA_DIR, webapp.LOGS_DIR, webapp.OUTPUT_DIR,
             paper_lib.DATA, weak_lib.DATA, weak_lib.LOGS)
    webapp.DATA_DIR, webapp.LOGS_DIR, webapp.OUTPUT_DIR = data, logs, output
    paper_lib.DATA = data
    weak_lib.DATA = data
    weak_lib.LOGS = logs
    webapp.app.config["TESTING"] = True
    try:
        yield base, data
    finally:
        (webapp.DATA_DIR, webapp.LOGS_DIR, webapp.OUTPUT_DIR,
         paper_lib.DATA, weak_lib.DATA, weak_lib.LOGS) = saved
        webapp.app.config["TESTING"] = False
        shutil.rmtree(base, ignore_errors=True)


def add_q(data: Path, subject: str, uid: str, **kw) -> None:
    """插一道题（默认带套卷名，便于组装"套卷"）。`question_type` / `stem` 可用 kw 覆盖。

    ⚠️ 选项正文必须**各不相同**：内嵌选项解析会做去重，四个选项若文本一样就只剩 1 个。
    ⚠️ 题干末尾的真实题库都带换行（`splitlines()` 读出来时最后一行没有结尾换行）——
       这里用 `\n` 分隔，行尾不留换行，与真实库一致。
    """
    stem = kw.get("stem", f"题干 {uid} 的题目？\nA. 选项甲 {uid}\nB. 选项乙 {uid}\n"
                          f"C. 选项丙 {uid}\nD. 选项丁 {uid}")
    fields = {
        "question_uid": uid, "subject": subject,
        "question_type": kw.get("question_type", "single_choice"),
        "stem": stem,
        "options": "[]", "answer": kw.get("answer", "B"),
        "explanation": kw.get("explanation", "因为 B 对"), "difficulty": "中",
        "status": kw.get("status", "approved"), "knowledge_point": kw.get("kp", "kp-1"),
        "trust_level": kw.get("trust", "official_exam"),
        "exam_title": kw.get("exam", "测试套卷2026"), "version": 1,
        "source_type": "real_exam", "source_url": "local://test",
    }
    conn = sqlite3.connect(str(data / f"{subject}.sqlite"))
    cols = ", ".join(fields)
    marks = ", ".join("?" for _ in fields)
    conn.execute(f"INSERT INTO questions({cols}) VALUES({marks})", list(fields.values()))
    conn.commit()
    conn.close()


def scalar(db: Path, sql: str, params=()):
    conn = sqlite3.connect(str(db))
    try:
        row = conn.execute(sql, params).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


# --------------------------------------------------------------------- ① paper_lib


def test_paper_lib_shape_and_order() -> None:
    with temp_env("lib") as (_base, data):
        for i in range(12):
            add_q(data, "english", f"u{i:02d}", answer="B" if i % 2 == 0 else "C")
        add_q(data, "english", "tiny1", exam="只有一题的组")
        papers = paper_lib.list_papers()
        assert len(papers) == 1, f"应只有 1 套卷（≥10 题）：{papers}"
        p = papers[0]
        assert p["title"] == "测试套卷2026" and p["count"] == 12, p
        assert p["real_count"] == 12, p
        # 原卷顺序 = id 升序
        rows = paper_lib.paper_questions("english", "测试套卷2026")
        ids = [r["id"] for r in rows]
        assert ids == sorted(ids), f"必须按 id 升序（= 原卷顺序）: {ids}"
        assert [r["question_uid"] for r in rows][0] == "u00", rows[0]
        s = paper_lib.paper_summary("english", "测试套卷2026")
        assert s["count"] == 12 and s["total_score"] == 12.0, s


# --------------------------------------------------------------------- ②③④ 接口


def test_paper_endpoints_and_submit() -> None:
    with temp_env("api") as (_base, data):
        c = webapp.app.test_client()
        # 10 道单选（答案 B）+ 1 道写作题 → 一起凑成一套卷
        for i in range(10):
            add_q(data, "english", f"p{i:02d}", answer="B", kp=f"kp-{i % 2}")
        add_q(data, "english", "w01", question_type="writing", answer="Model essay.",
              explanation="范文", kp="kp-w")
        listing = c.get("/api/paper/list").get_json()
        assert listing["count"] == 1, listing
        item = listing["groups"]["english"][0]
        assert item["title"] == "测试套卷2026" and item["count"] == 11, item
        assert item["exam_kind"] == "真题卷", item
        assert item["is_real_exam"] is True, item

        detail = c.get("/api/paper?subject=english&title=测试套卷2026").get_json()
        assert detail["count"] == 11, detail.get("count")
        seqs = [q["seq"] for q in detail["questions"]]
        assert seqs == list(range(1, 12)), seqs
        first = detail["questions"][0]
        assert len(first["options_parsed"]) == 4, \
            f"题干内嵌选项应解析出 4 个（回归：splitlines 吃掉结尾换行会导致少一个）: {first['options_parsed']}"
        assert [o["key"] for o in first["options_parsed"]] == ["A", "B", "C", "D"], first["options_parsed"]
        assert first["objective"] is True and first["answer_keys"] == "B", first
        # 判分前不该把答案藏起来（套卷要能出成绩报告）
        assert first.get("answer") == "B", first.get("answer")

        # 交卷：前 6 题答对、中间 3 题答错、1 题不答，写作题留空
        answers = {}
        for i in range(10):
            uid = f"p{i:02d}"
            if i < 6:
                answers[uid] = "B"
            elif i < 9:
                answers[uid] = "C"
            # i == 9 → 不答
        answers["w01"] = "my essay"     # 写作题：作答了，但仍必须交给 AI（本地判不了）
        resp = c.post("/api/paper/submit", json={"subject": "english", "title": "测试套卷2026",
                                                 "answers": answers, "elapsed_ms": 123456})
        assert resp.status_code == 200, resp.data[:400]
        rep = resp.get_json()
        assert "error" not in rep, rep
        assert rep["count"] == 11, rep
        assert rep["correct"] == 6 and rep["wrong"] == 4, rep
        assert rep["unanswered"] == 1, rep          # 只有第 10 题没答
        # 2026-10-24 行为变更：**没作答的客观题直接判 0 分**，不再进 AI 判分队列
        # （一份 82 题的 ACA 卷曾有 81 条空作答塞进 pending，跑真实判分等于给空白答案付钱）
        assert rep["pending"] == 1, rep             # 只剩写作题需要 AI
        assert rep["score"] == 6.0, rep             # 10 道单选各 1 分，对 6
        assert rep["total_score"] == 20.0, rep      # 10×1 + 写作 10
        assert rep["accuracy"] == round(6 / 10, 4), rep
        assert rep["per_type"]["writing"]["pending"] == 1, rep["per_type"]
        assert rep["per_type"]["writing"]["full"] == 10.0, rep["per_type"]

        adb = data / "attempts.sqlite"
        assert scalar(adb, "SELECT count(*) FROM attempts") == 11, \
            f"应写 11 条 attempt，实际 {scalar(adb, 'SELECT count(*) FROM attempts')}"
        assert scalar(adb, "SELECT count(*) FROM attempts WHERE source_type='paper'") == 11, \
            scalar(adb, "SELECT source_type, count(*) FROM attempts GROUP BY 1")
        assert scalar(adb, "SELECT count(*) FROM judge_queue WHERE judge_status='synced'") == 10, \
            scalar(adb, "SELECT judge_status, count(*) FROM judge_queue GROUP BY 1")
        assert scalar(adb, "SELECT count(*) FROM judge_queue WHERE judge_status='pending'") == 1, \
            scalar(adb, "SELECT judge_status, count(*) FROM judge_queue GROUP BY 1")
        # 契约：只写 review_log，绝不写 wrong_book
        eng = data / "english.sqlite"
        assert scalar(eng, "SELECT count(*) FROM wrong_book") == 0, "套卷判分绝不能写 wrong_book"
        assert scalar(eng, "SELECT count(*) FROM review_log") == 9, \
            f"9 道规则判分的题应各写一条事实，实际 {scalar(eng, 'SELECT count(*) FROM review_log')}"
        # 结果里每题都带作答/判定
        by_uid = {r["question_uid"]: r for r in rep["results"]}
        assert by_uid["p00"]["correct"] is True and by_uid["p00"]["judge_score"] == 1.0
        assert by_uid["p06"]["correct"] is False and by_uid["p06"]["judge_score"] == 0.0
        # 空作答的客观题：当场判 0 分，标注来源 unanswered（不进 AI 队列）
        assert by_uid["p09"]["status"] == "synced" and by_uid["p09"]["judged_by"] == "unanswered", by_uid["p09"]
        assert by_uid["p09"]["judge_score"] == 0.0 and by_uid["p09"]["correct"] is False
        assert by_uid["w01"]["status"] == "pending" and by_uid["w01"]["judged_by"] == "pending_ai"

        # 参数校验
        assert c.post("/api/paper/submit", json={"subject": "english"}).status_code == 400
        assert c.post("/api/paper/submit", json={"subject": "nope", "title": "x",
                                                 "answers": {}}).status_code == 400
        assert c.get("/api/paper?subject=english&title=不存在的卷").status_code == 404


def test_paper_kind_labels_for_c_subjects() -> None:
    with temp_env("kind") as (_base, data):
        for i in range(10):
            add_q(data, "c_wuhan", f"c{i:02d}", trust="textbook")
        listing = webapp.app.test_client().get("/api/paper/list").get_json()
        item = listing["groups"]["c_wuhan"][0]
        assert item["exam_kind"] == "校/教材题集", \
            f"C 语言的题集不能谎称真题卷：{item}"
        assert item["is_real_exam"] is True   # textbook 也算"真来源"


# --------------------------------------------------------------------- ⑤⑥ 弱势诊断


def test_weakness_empty_state() -> None:
    with temp_env("weak_empty"):
        c = webapp.app.test_client()
        resp = c.get("/api/weakness")
        assert resp.status_code == 200, resp.data[:300]
        body = resp.get_json()
        for key in ("totals", "by_subject", "by_knowledge_point", "by_question_type",
                    "weakest", "trend", "coverage", "thresholds"):
            assert key in body, (key, list(body))
        assert body["totals"]["attempts"] == 0, body["totals"]
        assert body["coverage"], "即使没做过题也要报告覆盖率（题库有多少）"
        assert body["coverage"]["english"]["total"] == 0


def test_weakness_detects_weak_kp() -> None:
    with temp_env("weak_data") as (_base, data):
        # kp-weak：5 题全错；kp-strong：4 题全对
        for i in range(5):
            add_q(data, "english", f"w{i}", answer="B", kp="kp-weak")
        for i in range(4):
            add_q(data, "english", f"s{i}", answer="B", kp="kp-strong")
        conn = sqlite3.connect(str(data / "attempts.sqlite"))
        ts = "2026-10-13T10:00:00+00:00"
        for uid, score in [(f"w{i}", 0.0) for i in range(5)] + [(f"s{i}", 1.0) for i in range(4)]:
            conn.execute("INSERT INTO attempts(attempt_id, question_uid, subject, user_answer, judge_score, "
                         "judge_model, synced, source_type, created_at) "
                         "VALUES(?,?,?,?,?,?,1,'ui',?)",
                         (f"att-{uid}", uid, "english", "X", score, "local_rule", ts))
        # 一条未判分（不该进正确率分母）
        conn.execute("INSERT INTO attempts(attempt_id, question_uid, subject, user_answer, judge_score, "
                     "synced, source_type, created_at) VALUES('att-unk','w0','english','X',NULL,0,'ui',?)",
                     (ts,))
        conn.commit()
        conn.close()

        body = webapp.app.test_client().get("/api/weakness").get_json()
        assert "error" not in body, body       # 出错时先把后端原文亮出来，别只报 KeyError
        t = body["totals"]
        assert t["attempts"] == 10, t
        assert t["judged"] == 9 and t["unjudged"] == 1, t
        assert t["correct"] == 4, t
        assert t["wrong"] == 5, t
        # 接口把正确率保留 4 位小数（`round(x, 4)`），比较时同样取整，别用 1e-6 硬卡
        assert t["accuracy"] == round(4 / 9, 4), t
        kps = {x["key"]: x for x in body["by_knowledge_point"]}
        assert kps["kp-weak"]["wrong"] == 5, kps["kp-weak"]
        assert kps["kp-weak"]["accuracy"] == 0.0, kps["kp-weak"]
        assert kps["kp-weak"]["weak"] is True, kps["kp-weak"]
        assert kps["kp-strong"]["weak"] is False, kps["kp-strong"]
        weakest = [x["key"] for x in body["weakest"]["knowledge_points"]]
        assert weakest and weakest[0] == "kp-weak", weakest
        assert body["trend"] and body["trend"][0]["date"] == "2026-10-13", body["trend"]
        cov = body["coverage"]["english"]
        assert cov["total"] == 9 and cov["done"] == 9, cov


def test_advice_is_free_by_default() -> None:
    with temp_env("advice"):
        c = webapp.app.test_client()
        r = c.post("/api/weakness/advice", json={})
        assert r.status_code == 200, r.data[:300]
        body = r.get_json()
        assert body["paid_call"] is False and body["prompt"], body
        assert "强化" in body["prompt"], body["prompt"][:200]
        assert body["estimate"]["cost_cny_est"] >= 0, body["estimate"]
        # 付费闸门：要真实调用必须显式确认，且当前明确未接通（501）
        g = c.post("/api/weakness/advice", json={"confirm_paid": True})
        assert g.status_code == 501 and g.get_json().get("paid_gate") is True, g.data[:300]


def test_weakness_history_is_idempotent_per_day() -> None:
    with temp_env("hist") as (base, _data):
        c = webapp.app.test_client()
        c.get("/api/weakness?remember=1")
        c.get("/api/weakness?remember=1")
        hist = base / "logs" / "weakness_history.jsonl"
        assert hist.exists(), "应写入弱势历史快照"
        lines = [json.loads(x) for x in hist.read_text(encoding="utf-8").splitlines() if x.strip()]
        assert len(lines) == 1, f"同一天只该记一条（幂等）：{lines}"


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
            print(f"  FAIL {fn.__name__}: {type(exc).__name__}: {exc}")
    print(f"[test_paper_weakness] {len(fns) - failed}/{len(fns)} passed")
    raise SystemExit(1 if failed else 0)
