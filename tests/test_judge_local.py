#!/usr/bin/env python
"""需求 2 · 规则判分离线测试（**不联网、不付费、不碰真实 data/**）。

覆盖（对应需求 2 的四条通道 + 需求 10 的进度即时更新）:
  ① 单元：`scripts/judge_local.py` 对真实题型形态的判定
     - 客观选择题：字母 / `"B. 选项原文"` / 多选全对 / 多选少选（全对才给分）
     - 是非题：正确/错误、T/F、A/B（题干带 A.正确 B.错误）
     - 填空：忽略大小写/空白/标点；`a | b` 备选任一都算对
     - 连词成句：忽略标点与大小写，词序不同判错
     - 长答案（论述题）/ 多空题（`A | C | D`）/ 写作 → **交给 AI**（不得判分）
     - 🔴 回归：`"D. great"` 当作答**必须判对**（早期实现抽出 "ADEG" 判错）
  ② 接口：`POST /api/submit` 对规则可判题**当场 synced 并出分**；
     对写作题仍是 `pending`（走 AI）；`no_local_judge=true` 可关闭规则判分
  ③ 进度：规则判分后当日 `daily_progress` 立刻有 correct/wrong（需求 10 的根因修复）
  ④ 契约：`wrong_book` **一行都不许写**（那是 sm2_scheduler 的独占职责）；
     `review_log` 必须写入回答事实
  ⑤ `/api/judge_local`：批量补判历史 pending 队列 + 单条判分

⚠️ 临时库/目录只放 `tests/.tmp/judge_local/`（共享目录，只清自己的子目录）。
⚠️ 不用 `tempfile.TemporaryDirectory()`：本机沙箱拒绝对系统临时目录做删除（WinError 5）。

运行: python tests/test_judge_local.py
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app" / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

import init_db  # noqa: E402
import app as webapp  # noqa: E402  ← app/backend/app.py
import judge_local as jl  # noqa: E402
from test_web_ui import add_question, add_queue_row, scalar, web_env  # noqa: E402

TMPROOT = ROOT / "tests" / ".tmp" / "judge_local"


# --------------------------------------------------------------------- ① 单元


def test_choice_types() -> None:
    # 纯字母
    v = jl.judge_local("c_wuhan", "single_choice", "B", "B")
    assert v.gradeable and v.correct and v.score == v.full_score, v
    v = jl.judge_local("c_wuhan", "single_choice", "B", "b ")
    assert v.gradeable and v.correct, "大小写/空白必须归一化"
    v = jl.judge_local("c_wuhan", "single_choice", "B", "C")
    assert v.gradeable and not v.correct and v.score == 0.0, v
    # 🔴 回归：一整句话里出现字母 A/B**不得**被当成选项字母（早期实现抽出 "AB"）
    v = jl.judge_local("c_wuhan", "single_choice", "B", "我看 A 和 B 都不太对")
    assert v.gradeable and not v.correct, v

    # 🔴 回归：答案/作答带选项原文时**只取首字母**（早期实现抽出 "ADEG" → 答对被判错）
    assert jl.extract_letters("D. great") == "D"
    assert jl.extract_letters("A、正确") == "A"
    assert jl.extract_letters("整句话里 A 和 B 都出现") == "", "非选项形态不得硬猜字母"
    v = jl.judge_local("english", "phonetics", "D. great", "D. great")
    assert v.gradeable and v.correct, v

    # 🔴 回归：单独一个字母/多字母串不能被当成"多空题"（`_PURE_LETTERS` 曾只允许分隔写法，
    #    于是多选答案 `"ABD"` 被判成"参考答案里没有可用的选项字母"）
    assert jl.is_multi_blank("ABD") is False
    assert jl.answer_option_letters("ABD") == "ABD"
    assert jl.judge_local("aca_llm", "multiple_choice", "ABD", "ABD").correct is True

    # 多选：全对才给分（多选/少选都判错）
    full = jl.full_score_for("aca_llm", "multiple_choice")
    v = jl.judge_local("aca_llm", "multiple_choice", "ABD", "DBA")
    assert v.gradeable and v.correct and v.score == full, v
    for bad in ("AB", "ABDE", "C"):
        v = jl.judge_local("aca_llm", "multiple_choice", "ABD", bad)
        assert v.gradeable and not v.correct, (bad, v)

    # 空作答 → 不判（不污染统计）
    v = jl.judge_local("c_wuhan", "single_choice", "B", "")
    assert not v.gradeable, v


def test_bool_types() -> None:
    v = jl.judge_local("c_wuhan", "true_false", "正确", "正确")
    assert v.gradeable and v.correct, v
    v = jl.judge_local("c_wuhan", "true_false", "正确", "错误")
    assert v.gradeable and not v.correct, v
    # 题干带 "A. 正确 / B. 错误"，答案是 A → 用户答 A 也要判对
    stem = "str 是一维字符数组。  ______\nA. 正确\nB. 错误"
    v = jl.judge_local("c_wuhan", "true_false", "A", "A", stem=stem)
    assert v.gradeable and v.correct, v
    v = jl.judge_local("c_wuhan", "true_false", "A", "B", stem=stem)
    assert v.gradeable and not v.correct, v


def test_blank_types() -> None:
    # 忽略大小写/空白/标点
    for user in ("Were I you", "were i you.", "  WERE I YOU  "):
        v = jl.judge_local("english", "grammar_fill", "Were I you", user)
        assert v.gradeable and v.correct, (user, v)
    v = jl.judge_local("english", "grammar_fill", "Were I you", "Was I you")
    assert v.gradeable and not v.correct, v

    # `a | b` 备选：任一都算对（题干只有 1 个空 → 是"同义备选"而不是多空题）
    one_blank = "你能保持安静吗?我需要集中精力。\n\nCan you \n\n? I need to concentrate. (quiet)"
    for user in ("keep quiet", "be quiet", "Be Quiet."):
        v = jl.judge_local("english", "translation_fill", "keep quiet | be quiet", user, stem=one_blank)
        assert v.gradeable and v.correct, (user, v)
    v = jl.judge_local("english", "translation_fill", "keep quiet | be quiet", "keep silence",
                       stem=one_blank)
    assert v.gradeable and not v.correct, v

    # 前缀噪声：答案写成 "空(1)处填：b"
    v = jl.judge_local("c_hbpu", "program_fill", "空(1)处填：b", "b")
    assert v.gradeable and v.correct, v

    # 答案带选项前缀 "A. Because ..." → 两边剥掉前缀后仍能比中
    v = jl.judge_local("english", "reading_qa", "A. Because smoking is harmful.",
                       "Because smoking is harmful.")
    assert v.gradeable and v.correct, v


def test_sentence_build() -> None:
    std = "He heard a noise coming from the campsite."
    for user in ("he heard a noise coming from the campsite",
                 "He heard a noise coming from the campsite.",
                 "He heard a noise coming from the campsite"):
        v = jl.judge_local("english", "sentence_build", std, user)
        assert v.gradeable and v.correct, (user, v)
    v = jl.judge_local("english", "sentence_build", std, "He heard a noise from the campsite coming.")
    assert v.gradeable and not v.correct, "词序错必须判错"
    # 带 "|" 的同义句（只差句号）不能当成多空题
    v = jl.judge_local("english", "sentence_build",
                       "She has completed her homework. | She has completed her homework",
                       "she has completed her homework")
    assert v.gradeable and v.correct, v


def test_defer_to_ai() -> None:
    # 写作 / 整段翻译 → 必须交给 AI
    for qtype in ("writing", "translation"):
        v = jl.judge_local("english", qtype, "Some long model essay.", "my essay")
        assert not v.gradeable, (qtype, v)
        assert "AI" in v.reason, v
    # 论述题（答案超长）
    long_ans = "作为一个完整的计算机系统，" + "硬件和软件按层次组织。" * 10
    v = jl.judge_local("c_wuhan", "program_fill", long_ans, long_ans)
    assert not v.gradeable and "过长" in v.reason, v
    # 多空题（题干有 2 个以上空标记）必须交给 AI；无题干的形态不明 → 也交 AI
    v = jl.judge_local("c_wuhan", "single_choice", "A | C | D", "A",
                       stem="源文件是 {{__SELECT_1__}}，目标是 {{__SELECT_2__}}，可执行是 {{__SELECT_3__}}。\n"
                            "A. .c\nB. .cpp\nC. .obj\nD. .exe")
    assert not v.gradeable, v
    v = jl.judge_local("c_wuhan", "single_choice", "A | C | D", "A")
    assert not v.gradeable, v
    # C 的整段编程题（答案是代码）：短代码（"看程序写结果"）能判，长代码必须交给 AI
    short_code = "```c\nint main(){return 0;}\n```"
    v = jl.judge_local("c_wuhan", "programming", short_code, short_code)
    assert v.gradeable and v.correct, ("短答案应能规则判分", v)
    long_code = ("```c\n#include <stdio.h>\nint main() {\n"
                 + "    printf(\"hello world\\n\");\n" * 5 + "    return 0;\n}\n```")
    v = jl.judge_local("c_wuhan", "programming", long_code, long_code)
    assert not v.gradeable and "过长" in v.reason, v
    # C 的"看程序写结果"（短答案）→ 要能判
    v = jl.judge_local("c_hbpu", "programming", "5050", "5050")
    assert v.gradeable and v.correct, v
    v = jl.judge_local("c_hbpu", "programming", "2 1", " 2  1 ")
    assert v.gradeable and v.correct, v


def test_options_from_stem() -> None:
    good = ("C语言源程序经过编译后，生成的目标程序文件的扩展名通常是  ______\n"
            "A. .c\nB. .exe\nC. .obj\nD. .cpp")
    opts = jl.options_from_stem(good)
    assert len(opts) == 4 and opts["C"] == ".obj", opts
    # 题面里含"正确/不包括"这类词 → 不可信，必须丢弃（否则前端会渲染出错误选项）
    bad = ("关于程序文档和软件的关系，以下描述正确的是  ______\n"
           "A. 软件仅指计算机程序本身，不包括文档\n"
           "B. 程序文档是软件的一个重要组成部分")
    assert jl.options_from_stem(bad) == {}, "含题面词的选项必须丢弃"


# --------------------------------------------------------------------- ②③④ 接口


def _daily(env, subject: str, date: str) -> tuple | None:
    conn = sqlite3.connect(str(env.data / f"{subject}.sqlite"))
    try:
        return conn.execute("SELECT total_done, correct_count, wrong_count FROM daily_progress "
                            "WHERE date=?", (date,)).fetchone()
    finally:
        conn.close()


def test_submit_local_judge_and_progress() -> None:
    with web_env("submit") as env:
        add_question(env.data, "aca_llm", "uid-obj", question_type="single_choice", answer="A")
        add_question(env.data, "english", "uid-write", question_type="writing",
                     answer="Model essay", stem="Write an essay.")
        db = env.data / "attempts.sqlite"
        today = webapp.today_local()

        resp = env.client.post("/api/submit", json={
            "question_uid": "uid-obj", "subject": "aca_llm", "user_answer": "A"})
        assert resp.status_code == 201, resp.data[:300]
        body = resp.get_json()
        assert body["status"] == "synced", body
        assert body["judged_by"] == "local_rule", body
        assert body["correct"] is True and body["judge_model"] == "local_rule", body
        # 落库：attempts + judge_queue 都是已判分态
        assert scalar(db, "SELECT judge_status FROM judge_queue WHERE attempt_id=?",
                      (body["attempt_id"],)) == "synced"
        assert scalar(db, "SELECT synced FROM attempts WHERE attempt_id=?",
                      (body["attempt_id"],)) == 1
        assert scalar(db, "SELECT judge_score FROM attempts WHERE attempt_id=?",
                      (body["attempt_id"],)) == body["full_score"]
        # 需求 10：当日进度立刻更新（以前要等 AI 判分才动）
        row = _daily(env, "aca_llm", today)
        assert row == (1, 1, 0), f"daily_progress 未即时更新: {row}"
        # 契约：review_log 有事实、wrong_book 一行都不许写
        assert scalar(env.data / "aca_llm.sqlite",
                      "SELECT result FROM review_log WHERE question_uid='uid-obj'") == "correct"
        assert scalar(env.data / "aca_llm.sqlite", "SELECT count(*) FROM wrong_book") == 0

        # 答错 → wrong + 进度 wrong_count=1
        resp2 = env.client.post("/api/submit", json={
            "question_uid": "uid-obj", "subject": "aca_llm", "user_answer": "B"})
        body2 = resp2.get_json()
        assert body2["status"] == "synced" and body2["correct"] is False, body2
        row = _daily(env, "aca_llm", today)
        assert row == (2, 1, 1), f"答错后进度不对: {row}"

        # 写作题 → 仍入队 pending（走付费 AI 通道）
        resp3 = env.client.post("/api/submit", json={
            "question_uid": "uid-write", "subject": "english", "user_answer": "my essay"})
        body3 = resp3.get_json()
        assert body3["status"] == "pending" and body3["judged_by"] == "pending_ai", body3
        assert scalar(db, "SELECT judge_status FROM judge_queue WHERE attempt_id=?",
                      (body3["attempt_id"],)) == "pending"
        assert scalar(db, "SELECT judge_score FROM attempts WHERE attempt_id=?",
                      (body3["attempt_id"],)) is None

        # 显式关闭规则判分（给"我要 AI 判分"的场景留后门）
        resp4 = env.client.post("/api/submit", json={
            "question_uid": "uid-obj", "subject": "aca_llm", "user_answer": "A",
            "no_local_judge": True})
        body4 = resp4.get_json()
        assert body4["status"] == "pending" and "local_judge" not in body4, body4


def test_judge_local_endpoint_backfill() -> None:
    with web_env("backfill") as env:
        add_question(env.data, "c_wuhan", "uid-bf", question_type="single_choice", answer="B")
        add_question(env.data, "english", "uid-bf2", question_type="writing", answer="essay")
        add_queue_row(env.data, "att-bf", "c_wuhan", "uid-bf", "pending", user_answer="B")
        add_queue_row(env.data, "att-bf2", "english", "uid-bf2", "pending", user_answer="essay")
        db = env.data / "attempts.sqlite"

        resp = env.client.post("/api/judge_local", json={"limit": 100})
        assert resp.status_code == 200, resp.data[:300]
        body = resp.get_json()
        assert body["count"] == 2 and body["synced"] == 1 and body["pending_ai"] == 1, body
        assert scalar(db, "SELECT judge_status FROM judge_queue WHERE attempt_id='att-bf'") == "synced"
        assert scalar(db, "SELECT judge_status FROM judge_queue WHERE attempt_id='att-bf2'") == "pending"
        assert scalar(env.data / "c_wuhan.sqlite",
                      "SELECT count(*) FROM wrong_book") == 0, "规则判分绝不能写 wrong_book"

        # 单条判分：再判一次同样幂等（不改对错）
        one = env.client.post("/api/judge_local", json={"attempt_id": "att-bf"})
        item = one.get_json()["results"][0]
        assert item["gradeable"] and item["correct"] is True, item
        # 不存在的 attempt → 明确报错而不是 500
        miss = env.client.post("/api/judge_local", json={"attempt_id": "nope"})
        assert miss.status_code == 200 and miss.get_json()["results"][0].get("error"), miss.data[:200]


def test_submit_does_not_touch_wrong_book_or_questions() -> None:
    with web_env("noclobber") as env:
        add_question(env.data, "english", "uid-q", question_type="single_choice", answer="A")
        qdb = env.data / "english.sqlite"
        before = scalar(qdb, "SELECT count(*) FROM questions")
        resp = env.client.post("/api/submit", json={
            "question_uid": "uid-q", "subject": "english", "user_answer": "A"})
        assert resp.status_code == 201, resp.data[:300]
        assert scalar(qdb, "SELECT count(*) FROM questions") == before, "questions 表不得被改动"
        assert scalar(qdb, "SELECT count(*) FROM wrong_book") == 0, "wrong_book 归 sm2 独占"
        assert scalar(qdb, "SELECT count(*) FROM review_log") == 1, "必须写一条回答事实"
        assert scalar(env.data / "attempts.sqlite", "SELECT count(*) FROM attempts") == 1


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
            print(f"  FAIL {fn.__name__}: {type(exc).__name__}: {exc}")
    print(f"[test_judge_local] {len(fns) - failed}/{len(fns)} passed")
    raise SystemExit(1 if failed else 0)
