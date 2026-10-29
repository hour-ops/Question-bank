#!/usr/bin/env python
"""sync_outbox.py 离线测试 —— **全程不联网、不读真实 key、不碰真实库**。

新契约（作者已按独立测试反馈修复，本文件对齐修订 SHA256=3EB940F6…）：
  · sync_outbox 只写 `judge_queue` / `attempts` / **`review_log`（科目库）**；
    **`wrong_book` 由 sm2_scheduler 独占维护** —— sync_outbox 跑完错题本必须**零变化**
    （根因：两边都写会把水位推到事件同一时刻 → sm2 判 stale → 答错事件永不被 SM-2 处理）。
  · 满分来自 `config/taxonomy.json` 的 `per_item`（读不到才回落 1.0），不再写死。
  · 队列消费 `judge_status IN ('pending','submitted')`（submitted 是中断残留态）。
  · 题目 / 科目库缺失**不再猜**：直接标 `failed` + 汇总 `lookup_failed`，不进入判分。
  · 最终 failed 前先 `conn.rollback()`，不提交 attempts/judge_queue 半成品。

覆盖：
  ① ACA 本地规则判分（不调 LLM；规则值从真实 config/aca_rules.json 读，不写死）
  ② --mock 启发式判分，并正面证明「没走真实分支、没 import openai」（假 openai 模块 + 属性探针）
  ③ 写回完整性：judge_queue(synced) / attempts(synced=1) / review_log(科目库新增一行, result∈{correct,wrong})
  ④ 满分契约：full_score_for 从 taxonomy.json 读；2 分题得 1 分判 wrong（半对不再记 correct）
  ⑤ 🔴 wrong_book 零变化（既有行一字不改、新错题不建行）
  ⑥ 🔴 跨模块回归防线：sync_outbox → sm2_scheduler → 错题本出现该行且 next_review_at 非空（P0）
  ⑦ 重试 MAX_RETRY 次 → failed + reason 摘要 + 退避；失败路径回滚半成品（P1）
  ⑧ --dry-run：pending 计数正确但 judge_queue 内容哈希前后一致
  ⑨ 空队列 → pending=0 退出码 0（附：库不存在 → 1）
  ⑩ --limit N / --subject 过滤
  ⑪ 成本账本：--mock 不写；真实分支有 usage 才写（成本算式核对）
  ⑫ 题目/科目库缺失 → failed + lookup_failed，不写 review_log、不建科目库文件
  ⑬ `submitted` 残留行必须被消费

⚠️ `test_known_issue_*` 是"现状记录"（characterization）：断言当前真实行为，今天全绿，
   一旦有人改动对应行为就会失败并提示复核。🔴 本文件不修改被测脚本。

⚠️ 不使用 tempfile.TemporaryDirectory()：本机沙箱拒绝对系统临时目录做删除（WinError 5），
   临时环境统一放 **tests/.tmp/sync_outbox/<用例名>.p<pid>/**（共享目录，只清自己的子目录）。
   带 pid 后缀是硬需求：本机实测并发跑同一测试时 rmtree 会互相删掉现场 → 残留 DB 注入脏数据；
   删除失败会大声报错，绝不静默吞掉。

运行: python tests/test_sync_outbox.py
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import shutil
import sqlite3
import sys
import time
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

REAL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REAL_ROOT / "scripts"))

import init_db  # noqa: E402
import sync_outbox as so  # noqa: E402

PY = sys.executable
TMPROOT = REAL_ROOT / "tests" / ".tmp" / "sync_outbox"
RUN_TAG = f"p{os.getpid()}"

# 被测脚本的修订版本（本套用例按这一版对齐；变了会在 test_target_revision_checked 里提示）
VALIDATED_SHA256 = "3EB940F671BCE1230317DF106D0A19A3FA5B8ECB00B2ECBAD184C52928048BCF"

# 真实规则/配置（不写死数值：断言与这些文件里的值比对）
RULES = json.loads((REAL_ROOT / "config" / "aca_rules.json").read_text(encoding="utf-8"))
TAXONOMY = json.loads((REAL_ROOT / "config" / "taxonomy.json").read_text(encoding="utf-8"))

PATCHED_GLOBALS = ("ROOT", "DATA", "LOGS", "ENV_FILE", "ATTEMPTS_DB", "LEDGER")
_MISSING = object()


def fresh_dir(name: str) -> Path:
    """工作区内干净的临时目录：tests/.tmp/sync_outbox/<name>.<pid>/（只动自己的子目录）。"""
    d = TMPROOT / f"{name}.{RUN_TAG}"
    shutil.rmtree(d, ignore_errors=True)
    if d.exists():                      # 可能被并发运行的测试短暂占用，再试一次
        time.sleep(0.3)
        shutil.rmtree(d, ignore_errors=True)
    if d.exists():                      # 仍失败 → 逐个删残留文件（残留 DB 会注入脏数据）
        for p in sorted(d.rglob("*"), reverse=True):
            with contextlib.suppress(OSError):
                p.unlink() if p.is_file() else p.rmdir()
        shutil.rmtree(d, ignore_errors=True)
    if d.exists():
        raise RuntimeError(f"临时目录无法清理（疑似被并发测试占用）：{d}")
    return d


def real_db_fingerprint() -> str:
    """**只读**打开真实 data/attempts.sqlite（URI mode=ro，绝不写），取 judge_queue 指纹。"""
    path = REAL_ROOT / "data" / "attempts.sqlite"
    if not path.exists():
        return "absent"
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        rows = [tuple(r) for r in conn.execute(
            "SELECT id, attempt_id, judge_status, judge_score FROM judge_queue ORDER BY id")]
    finally:
        conn.close()
    return hashlib.sha256(repr(rows).encode("utf-8")).hexdigest()


REAL_JQ_BASELINE = real_db_fingerprint()


# --------------------------------------------------------------------- 临时环境（monkeypatch 全局）


class TempEnv:
    """临时「项目根」：config/ + data/ + logs/ + .env 全在里面，schema 复用 init_db。"""

    def __init__(self, base: Path) -> None:
        self.base = base
        self.root = base / "proj"
        self.data = self.root / "data"
        self.logs = self.root / "logs"
        self.config = self.root / "config"

    # ---- 建环境
    def build(self) -> None:
        for p in (self.data, self.logs, self.config):
            p.mkdir(parents=True, exist_ok=True)
        # 复制**真实项目的全部 config/*.json**：ROOT 被重定向后仍读到同一份规则/满分表
        # （taxonomy.json 决定 full_score_for，aca_rules.json 决定 ACA 判分 —— 都不写死）
        for src in sorted((REAL_ROOT / "config").glob("*.json")):
            shutil.copyfile(src, self.config / src.name)

    @property
    def attempts_db(self) -> Path:
        return self.data / "attempts.sqlite"

    @property
    def ledger(self) -> Path:
        return self.logs / "cost_ledger.jsonl"

    def subject_path(self, subject: str) -> Path:
        return self.data / f"{subject}.sqlite"

    # ---- 建库（复用 init_db 的真实 DDL，与真实库同构）
    def make_attempts(self) -> None:
        conn = init_db.connect(self.attempts_db)
        conn.executescript(init_db.ATTEMPTS_SCHEMA)
        conn.commit()
        conn.close()

    def make_subject(self, subject: str, *, wrong_book: bool = True, review_log: bool = True) -> None:
        conn = init_db.connect(self.subject_path(subject))
        conn.executescript(init_db.SUBJECT_SCHEMA)
        if not wrong_book:
            conn.execute("DROP TABLE wrong_book")
        if not review_log:
            conn.execute("DROP TABLE review_log")   # 故障注入：写回时 INSERT 必炸
        conn.commit()
        conn.close()

    def tables(self, db: str = "attempts") -> list[str]:
        if not self.path_of(db).exists():
            return []
        return [r[0] for r in self.q("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name", db=db)]

    # ---- 读写
    def path_of(self, db: str) -> Path:
        return self.attempts_db if db == "attempts" else self.subject_path(db)

    def connect(self, db: str = "attempts"):
        return so.connect(self.path_of(db))

    def q(self, sql: str, params: tuple = (), db: str = "attempts") -> list[tuple]:
        conn = self.connect(db)
        try:
            return [tuple(r) for r in conn.execute(sql, params)]
        finally:
            conn.close()

    def exec(self, sql: str, params: tuple = (), db: str = "attempts") -> None:
        conn = self.connect(db)
        try:
            conn.execute(sql, params)
            conn.commit()
        finally:
            conn.close()

    def one(self, sql: str, params: tuple = (), db: str = "attempts"):
        return self.q(sql, params, db)[0]

    def count(self, table: str, db: str = "attempts") -> int:
        return int(self.one(f"SELECT count(*) FROM {table}", db=db)[0])

    # ---- 种子数据
    def seed_question(self, subject: str, uid: str, *, qtype: str = "single_choice",
                      answer: str = "A", stem: str = "题干", options: str | None = None) -> None:
        self.exec(
            "INSERT INTO questions(question_uid, subject, question_type, stem, options, answer, "
            "status, source_url, source_type) VALUES(?,?,?,?,?,?,'approved','https://x/1','smoke')",
            (uid, subject, qtype, stem, options, answer), db=subject,
        )

    def seed_wrong_book(self, subject: str, uid: str, **cols: object) -> None:
        """预置一条错题记录（模拟 sm2_scheduler 之前写过的行）。"""
        base = {"wrong_count": 1, "correct_streak": 0, "last_wrong_at": "2020-01-01T00:00:00+00:00",
                "next_review_at": "2020-01-02T00:00:00+00:00", "mastery": 0, "notes": None,
                "updated_at": "2020-01-02T00:00:00+00:00"}
        base.update(cols)
        self.exec(
            "INSERT INTO wrong_book(question_uid, wrong_count, correct_streak, last_wrong_at, "
            "next_review_at, mastery, notes, updated_at) VALUES(?,?,?,?,?,?,?,?)",
            (uid, base["wrong_count"], base["correct_streak"], base["last_wrong_at"],
             base["next_review_at"], base["mastery"], base["notes"], base["updated_at"]), db=subject,
        )

    def seed_queue_row(self, attempt_id: str, subject: str, uid: str, user_answer: str,
                       status: str = "pending") -> None:
        conn = self.connect()
        try:
            ts = so.now_iso()
            conn.execute(
                "INSERT INTO attempts(attempt_id, question_uid, subject, user_answer, synced, "
                "source_type, created_at) VALUES(?,?,?,?,0,'smoke',?)",
                (attempt_id, uid, subject, user_answer, ts),
            )
            conn.execute(
                "INSERT INTO judge_queue(attempt_id, subject, question_uid, user_answer, "
                "judge_status, source_type, created_at) VALUES(?,?,?,?,?,'smoke',?)",
                (attempt_id, subject, uid, user_answer, status, ts),
            )
            conn.commit()
        finally:
            conn.close()

    def judge_queue_dump(self) -> list[tuple]:
        return self.q("SELECT * FROM judge_queue ORDER BY id")

    def judge_queue_hash(self) -> str:
        return hashlib.sha256(repr(self.judge_queue_dump()).encode("utf-8")).hexdigest()

    def write_judge_prompt(self, version: str) -> None:
        (self.config / "judge_prompt.json").write_text(
            json.dumps({"version": version, "prompts": {}}, ensure_ascii=False), encoding="utf-8")


@contextlib.contextmanager
def temp_env(name: str):
    """把 sync_outbox 的 ROOT/DATA/LOGS/ENV_FILE/ATTEMPTS_DB/LEDGER 指向临时环境，退出时复原。"""
    base = fresh_dir(name)
    env = TempEnv(base)
    env.build()
    saved = {n: getattr(so, n) for n in PATCHED_GLOBALS}
    so.ROOT = env.root
    so.DATA = env.data
    so.LOGS = env.logs
    so.ENV_FILE = env.root / ".env"
    so.ATTEMPTS_DB = env.attempts_db
    so.LEDGER = env.ledger
    try:
        yield env
    finally:
        for n, v in saved.items():
            setattr(so, n, v)
        # 故意不删现场：失败时便于排查（__main__ 全绿时按 RUN_TAG 清自己的目录）


@contextlib.contextmanager
def probe_openai(seen: list):
    """装一个**会炸的假 openai**：任何 `openai.X` 访问都被记录并抛错。

    正面证明「这条路径根本没 import openai / 没走真实 LLM 分支」：跑完断言 `seen == []`。
    ⚠️ sync_outbox 的重试循环会吃掉异常，所以必须同时看 seen 与判分结果。
    """

    class _Probe(types.ModuleType):
        def __getattr__(self, item):   # 只有正常查找失败才会进来
            seen.append(item)
            raise AssertionError(f"真实 LLM 分支被触发：openai.{item}")

    probe = _Probe("openai", seen)
    saved = sys.modules.get("openai", _MISSING)
    sys.modules["openai"] = probe
    try:
        yield probe
    finally:
        if saved is _MISSING:
            sys.modules.pop("openai", None)
        else:
            sys.modules["openai"] = saved


@contextlib.contextmanager
def stub_openai(rec: list):
    """装一个"可 import 但一构造就炸"的假 openai：验证「缺 key 应先报错、绝不构造客户端」。"""

    class OpenAI:  # noqa: N801
        def __init__(self, *a, **k):
            rec.append((a, k))
            raise AssertionError("缺少 key 时不应构造 OpenAI 客户端（更不该联网）")

    mod = types.ModuleType("openai")
    mod.OpenAI = OpenAI  # type: ignore[attr-defined]
    saved = sys.modules.get("openai", _MISSING)
    sys.modules["openai"] = mod
    try:
        yield mod
    finally:
        if saved is _MISSING:
            sys.modules.pop("openai", None)
        else:
            sys.modules["openai"] = saved


@contextlib.contextmanager
def fake_sleep(rec: list):
    """把 time.sleep 换成记录器（真跑退避会白等 3 秒），退出复原。"""
    orig = time.sleep
    time.sleep = lambda s: rec.append(s)  # type: ignore[assignment]
    try:
        yield
    finally:
        time.sleep = orig  # type: ignore[assignment]


@contextlib.contextmanager
def patch_judge_llm(fn):
    """临时替换 so.judge_llm（离线模拟 LLM 判分结果），退出复原。"""
    orig = so.judge_llm
    so.judge_llm = fn
    try:
        yield
    finally:
        so.judge_llm = orig


def parse_iso(s: str) -> datetime:
    dt = datetime.fromisoformat(s)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def make_case(env: TempEnv, subject: str, qtype: str, answer: str, pairs: list[tuple[str, str, str]],
              *, seed_questions: bool = True, **kw) -> None:
    """建库 + 造题 + 入队；pairs = [(attempt_id, question_uid, user_answer), ...]。"""
    env.make_attempts()
    env.make_subject(subject, **kw)
    if seed_questions:
        for uid in sorted({p[1] for p in pairs}):
            env.seed_question(subject, uid, qtype=qtype, answer=answer)
    for aid, uid, ua in pairs:
        env.seed_queue_row(aid, subject, uid, ua)


def run_main(argv: list[str]) -> tuple[int, dict, str]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = so.main(argv)
    out = buf.getvalue()
    return rc, json.loads(out), out


def sm2_run(env: TempEnv, subject: str = "english") -> dict:
    """跑真实 sm2_scheduler（只读 review_log、写 wrong_book），吞掉它的打印。"""
    import sm2_scheduler as sm2

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        return sm2.run(subject, False, data_dir=env.data)


# ===================================================================== ① ACA 本地规则


def test_aca_rules_config_is_source_of_truth() -> None:
    """规则值来自 config/aca_rules.json（本用例钉住现行 v1.0 契约值）。"""
    assert RULES["single_choice"]["correct"] == 2.0, RULES
    assert RULES["single_choice"]["wrong"] == 0.0, RULES
    assert RULES["multiple_choice"]["all_correct"] == 2.0, RULES
    assert RULES["multiple_choice"]["partial"] == 0.0, RULES
    assert "不调用 LLM" in RULES.get("notes", "")


def test_aca_single_choice_local_rule() -> None:
    seen: list = []
    with temp_env("aca_single") as env:
        env.make_attempts()
        env.make_subject("aca_llm")
        env.seed_question("aca_llm", "aca_s1", qtype="single_choice", answer="A",
                          options=json.dumps(["A. 甲", "B. 乙"], ensure_ascii=False))
        conn = env.connect("aca_llm")
        try:
            with probe_openai(seen):
                ok = so.judge_aca_local("aca_llm", conn, "aca_s1", "A")
                bad = so.judge_aca_local("aca_llm", conn, "aca_s1", "B")
                lower = so.judge_aca_local("aca_llm", conn, "aca_s1", "a ")   # 归一化：大小写/空白
        finally:
            conn.close()
    rule = RULES["single_choice"]
    assert ok[0] == rule["correct"] == 2.0, ok
    assert bad[0] == rule["wrong"] == 0.0, bad
    assert ok[1] == "单选正确" and bad[1] == "单选错误", (ok, bad)
    assert lower[0] == rule["correct"], lower
    assert ok[2] == bad[2] == "local_rule", (ok, bad)
    assert seen == [], f"ACA 判分不应 import openai，实际访问了 {seen}"


def test_aca_multiple_choice_local_rule() -> None:
    seen: list = []
    with temp_env("aca_multi") as env:
        env.make_attempts()
        env.make_subject("aca_llm")
        env.seed_question("aca_llm", "aca_m1", qtype="multiple_choice", answer="ABD")
        conn = env.connect("aca_llm")
        try:
            with probe_openai(seen):
                full = so.judge_aca_local("aca_llm", conn, "aca_m1", "BDA")    # 顺序无关
                part = so.judge_aca_local("aca_llm", conn, "aca_m1", "AB")     # 部分对
                wrong = so.judge_aca_local("aca_llm", conn, "aca_m1", "C")     # 全错
                extra = so.judge_aca_local("aca_llm", conn, "aca_m1", "ABDE")  # 多选了一个
        finally:
            conn.close()
    rule = RULES["multiple_choice"]
    assert full[0] == rule["all_correct"] == 2.0, full
    assert full[1] == "多选全对"
    for got in (part, wrong, extra):
        assert got[0] == rule["partial"] == rule["wrong"] == 0.0, got   # all-or-nothing，无部分分
    assert part[1] == "多选部分对（按规则不给部分分）", part
    assert seen == [], f"ACA 判分不应 import openai，实际访问了 {seen}"


def test_aca_blank_answers_are_never_full_marks() -> None:
    """标准答案缺失 / 作答为空 → 一律 0 分（不得因为"两边都空"而判对）。"""
    with temp_env("aca_blank") as env:
        env.make_attempts()
        env.make_subject("aca_llm")
        env.seed_question("aca_llm", "aca_blank", qtype="single_choice", answer="", stem="答案缺失")
        env.seed_question("aca_llm", "aca_ok", qtype="single_choice", answer="A")
        conn = env.connect("aca_llm")
        try:
            got = so.judge_aca_local("aca_llm", conn, "aca_blank", "")
            got2 = so.judge_aca_local("aca_llm", conn, "aca_blank", "未作答")
            blank = so.judge_aca_local("aca_llm", conn, "aca_ok", "")
            blank2 = so.judge_aca_local("aca_llm", conn, "aca_ok", "   ")
        finally:
            conn.close()
    assert got == (0.0, "题库缺少标准答案（未获取）", "local_rule"), got
    assert got2 == (0.0, "题库缺少标准答案（未获取）", "local_rule"), got2
    assert blank == (0.0, "未作答", "local_rule"), blank
    assert blank2 == (0.0, "未作答", "local_rule"), blank2


def test_aca_queue_path_is_local_rule_only() -> None:
    """走 run() 的 ACA 队列：judge_model=local_rule、score 来自本地规则、绝不触发 LLM。"""
    seen: list = []

    def boom(*a, **k):
        raise AssertionError("ACA 路径不得调用 judge_llm")

    with temp_env("aca_e2e") as env:
        make_case(env, "aca_llm", "single_choice", "A", [("att_aca", "q_aca", "B")])
        with probe_openai(seen), fake_sleep([]), patch_judge_llm(boom):
            stats = so.run(mock=False, limit=None, subject=None, dry_run=False)
        assert stats["synced"] == 1 and stats["failed"] == 0, stats
        row = env.one("SELECT judge_status, judge_score, judge_model, judge_reason "
                      "FROM judge_queue WHERE attempt_id='att_aca'")
        assert row[0] == "synced", row
        assert row[1] == RULES["single_choice"]["wrong"] == 0.0, row
        assert row[2] == "local_rule", row
        assert row[3] == "单选错误", row
        assert env.one("SELECT judge_model FROM attempts WHERE attempt_id='att_aca'")[0] == "local_rule"
        assert env.one("SELECT result FROM review_log", db="aca_llm")[0] == "wrong"
        assert env.count("wrong_book", db="aca_llm") == 0, "ACA 答错也不得由 sync_outbox 建错题行"
    assert seen == [], f"ACA 不应 import openai，实际访问了 {seen}"


# ===================================================================== ② --mock 不联网


def test_mock_heuristic_and_no_openai_import() -> None:
    seen: list = []
    with probe_openai(seen):
        exact = so.judge_llm(True, "english", "grammar_fill", "题干", "I am here", "I am here", {}, "deepseek-flash")
        prefix = so.judge_llm(True, "english", "grammar_fill", "题干", "I am here", "I am", {}, "deepseek-flash")
        miss = so.judge_llm(True, "english", "grammar_fill", "题干", "I am here", "nope", {}, "deepseek-flash")
    assert exact[0] == 1.0, exact
    assert prefix[0] == 0.6, prefix
    assert miss[0] == 0.0, miss
    assert "[mock]" in exact[1] and exact[2] == {"mock": True}, exact
    assert seen == [], f"mock 模式不应 import openai，实际访问 {seen}"


def test_mock_queue_path_is_offline() -> None:
    """--mock 端到端（含 CLI）：全程不 import openai。"""
    seen: list = []
    with temp_env("mock_e2e") as env:
        make_case(env, "english", "grammar_fill", "I am here", [("att_m", "q_m", "I am here")])
        with probe_openai(seen):
            rc, payload, out = run_main(["--mock"])
        assert rc == 0 and payload["mock"] is True and payload["synced"] == 1, payload
        assert '"mock": true' in out
        assert env.count("review_log", db="english") == 1
        assert env.count("wrong_book", db="english") == 0
    assert seen == [], f"mock 模式不应 import openai，实际访问 {seen}"


def test_real_branch_without_key_raises_before_any_call() -> None:
    """真实分支缺 key：必须在**构造客户端之前**报错（离线断言，不发任何请求）。"""
    with temp_env("no_key") as env:
        rec: list = []
        with stub_openai(rec):   # (a) .env 不存在
            try:
                so.judge_llm(False, "english", "grammar_fill", "s", "a", "a", {}, "deepseek-flash")
            except RuntimeError as exc:
                msg = str(exc)
            else:
                raise AssertionError("缺 DEEPSEEK_API_KEY 时应抛 RuntimeError")
        assert "DEEPSEEK_API_KEY" in msg, msg
        # (b) .env 存在但只有 BASE_URL
        (env.root / ".env").write_text("DEEPSEEK_BASE_URL=https://api.deepseek.com\n", encoding="utf-8")
        with stub_openai(rec):
            try:
                so.judge_llm(False, "english", "grammar_fill", "s", "a", "a", {}, "deepseek-flash")
            except RuntimeError as exc:
                msg2 = str(exc)
            else:
                raise AssertionError("空 key 也应抛 RuntimeError")
        assert "DEEPSEEK_API_KEY" in msg2, msg2
        assert rec == [], "缺 key 时绝不能构造 OpenAI 客户端"


# ===================================================================== ③/④ 写回完整性 + 满分契约


def test_full_score_for_reads_taxonomy() -> None:
    """满分从 config/taxonomy.json 的 per_item 读（不写死）；读不到才回落 1.0。"""
    en = TAXONOMY["subjects"]["english"]["question_types"]
    for qt in ("grammar_fill", "sentence_build", "reading_fill", "reading_qa", "translation_fill", "writing"):
        assert so.full_score_for("english", qt) == float(en[qt]["per_item"]), qt
    assert so.full_score_for("english", "grammar_fill") == 2.0
    assert so.full_score_for("english", "translation_fill") == 3.0
    assert so.full_score_for("english", "writing") == 10.0
    aca = TAXONOMY["subjects"]["aca_llm"]["question_types"]
    assert so.full_score_for("aca_llm", "single_choice") == float(aca["single_choice"]["per_item"]) == 2.0
    assert so.full_score_for("aca_llm", "multiple_choice") == 2.0
    # C 语言 taxonomy 里没有 per_item（缺口）→ 明确回落 1.0
    assert "per_item" not in TAXONOMY["subjects"]["c_wuhan"]["question_types"]["code_correction"]
    assert so.full_score_for("c_wuhan", "code_correction") == 1.0
    assert so.full_score_for("english", "不存在的题型") == 1.0
    assert so.full_score_for("nope", "nope") == 1.0


def test_full_score_falls_back_when_taxonomy_missing() -> None:
    """taxonomy.json 缺失 → 满分回落 1.0（反过来证明满分确实是"读 config"而不是写死 2.0）。"""
    with temp_env("taxonomy_missing") as env:
        (env.config / "taxonomy.json").unlink()
        assert so.full_score_for("english", "grammar_fill") == 1.0
        make_case(env, "english", "grammar_fill", "I am here", [("att_fb", "q_fb", "I am here")])
        stats = so.run(mock=True, limit=None, subject=None, dry_run=False)   # mock 精确匹配 → 1.0
        assert stats["synced"] == 1, stats
        assert env.one("SELECT judge_score FROM judge_queue WHERE attempt_id='att_fb'")[0] == 1.0
        assert env.one("SELECT result FROM review_log", db="english")[0] == "correct", \
            "满分回落 1.0 时 mock 的 1.0 才够线（同一份作答在 taxonomy 存在时会判 wrong）"


def test_write_back_full_contract() -> None:
    """一题全对（判分器按 taxonomy 的 2 分制给 2.0）→ 四个落点全部正确。"""
    seen: list = []
    full = float(TAXONOMY["subjects"]["english"]["question_types"]["grammar_fill"]["per_item"])
    with temp_env("write_back") as env:
        env.write_judge_prompt("9.9-test")   # 证明 judge_prompt_version 真从 config 取
        make_case(env, "english", "grammar_fill", "I am here", [("att_ok", "q_ok", "I am here")])
        q_before = env.q("SELECT * FROM questions ORDER BY id", db="english")
        t0 = datetime.now(timezone.utc)
        with probe_openai(seen), patch_judge_llm(lambda *a, **k: (full, "全对", {})):
            stats = so.run(mock=True, limit=None, subject=None, dry_run=False)
        t1 = datetime.now(timezone.utc)

        assert stats["pending"] == 1 and stats["synced"] == 1 and stats["failed"] == 0, stats
        assert stats["subjects"] == {"english": 1} and "lookup_failed" not in stats, stats

        jq = env.one("SELECT judge_status, judge_score, judge_model, judge_reason, submitted_at "
                     "FROM judge_queue WHERE attempt_id='att_ok'")
        assert jq[0] == "synced", jq
        assert jq[1] == full == 2.0, jq               # 满分按 taxonomy 的 2 分制
        assert jq[2] == "deepseek-flash", jq          # 非写作题 → flash
        assert jq[3] == "全对", jq
        assert jq[4], "submitted_at 应被回填（COALESCE）"

        at = env.one("SELECT synced, judge_score, judge_model, judge_reason, judge_prompt_version "
                     "FROM attempts WHERE attempt_id='att_ok'")
        assert at[0] == 1, f"attempts.synced 应为 1，实际 {at}"
        assert at[1] == full and at[2] == "deepseek-flash" and at[3] == "全对", at
        assert at[4] == "9.9-test", f"judge_prompt_version 应取自 config/judge_prompt.json，实际 {at[4]}"

        # 🔴 review_log 必须落在**科目库**（sm2_scheduler 的事实源就在那儿）
        assert "review_log" not in env.tables("attempts"), \
            f"attempts 库不该有 review_log 表（真实库也没有），实际 {env.tables('attempts')}"
        rl = env.q("SELECT question_uid, reviewed_at, result FROM review_log", db="english")
        assert len(rl) == 1, f"review_log 必须新增且只新增一行，实际 {rl}"
        uid, reviewed_at, result = rl[0]
        assert uid == "q_ok" and reviewed_at, rl
        assert result in ("correct", "wrong"), f"result 只能取 correct|wrong（sm2 事实源），实际 {result!r}"
        assert result == "correct", rl
        assert t0 - timedelta(seconds=5) <= parse_iso(reviewed_at) <= t1 + timedelta(seconds=5), reviewed_at

        assert env.q("SELECT * FROM questions ORDER BY id", db="english") == q_before, "不得改 questions 表"
        assert env.count("wrong_book", db="english") == 0, "错题本由 sm2 独占，sync_outbox 不得建行"
    assert seen == [], f"mock 判分不应 import openai，实际访问 {seen}"


def test_half_credit_on_two_point_question_is_wrong() -> None:
    """2 分题得 1.0（半对）→ 记 wrong；得 2.0（全对）→ 记 correct（P2a 回归）。"""
    with temp_env("half_credit") as env:
        make_case(env, "english", "grammar_fill", "I am here", [("att_half", "q_half", "I am here")])
        with patch_judge_llm(lambda *a, **k: (1.0, "半对（2 分题得 1 分）", {})):
            stats = so.run(mock=True, limit=None, subject=None, dry_run=False)
        assert stats["synced"] == 1, stats
        assert env.one("SELECT judge_score FROM judge_queue WHERE attempt_id='att_half'")[0] == 1.0
        assert env.one("SELECT result FROM review_log", db="english")[0] == "wrong", \
            "2 分题得 1 分必须判 wrong（此前被错误的 1.0 满分记成 correct）"

        env.seed_queue_row("att_full", "english", "q_half", "I am here")
        with patch_judge_llm(lambda *a, **k: (2.0, "全对", {})):
            stats2 = so.run(mock=True, limit=None, subject=None, dry_run=False)
        assert stats2["synced"] == 1, stats2
        assert [r[0] for r in env.q("SELECT result FROM review_log ORDER BY id", db="english")] == \
            ["wrong", "correct"]


# ===================================================================== ⑤/⑥ wrong_book 归属 + 跨模块回归


def test_sync_outbox_never_touches_wrong_book() -> None:
    """🔴 P0：sync_outbox 只写 review_log；错题本零变化（既有行一字不改、新错题不建行）。"""
    with temp_env("wrong_book_untouched") as env:
        make_case(env, "english", "grammar_fill", "I am here",
                  [("att_x1", "q_old", "zzz")])                       # 答错，且错题本里已有该题
        env.seed_wrong_book("english", "q_old", wrong_count=5, correct_streak=3, mastery=2,
                            notes="用户备注", updated_at="2020-01-02T00:00:00+00:00")
        before = env.q("SELECT * FROM wrong_book ORDER BY question_uid", db="english")

        stats = so.run(mock=True, limit=None, subject=None, dry_run=False)
        assert stats["synced"] == 1, stats
        assert env.q("SELECT * FROM wrong_book ORDER BY question_uid", db="english") == before, \
            "🔴 sync_outbox 绝不能碰 wrong_book（含 updated_at 水位）"
        assert env.one("SELECT result FROM review_log", db="english")[0] == "wrong"

        # 第二条：错题本里没有的新题答错 → 也不得建行
        env.seed_question("english", "q_new", qtype="grammar_fill", answer="I am here")
        env.seed_queue_row("att_x2", "english", "q_new", "zzz")
        stats2 = so.run(mock=True, limit=None, subject=None, dry_run=False)
        assert stats2["synced"] == 1, stats2
        assert env.count("wrong_book", db="english") == 1, "新错题也不得由 sync_outbox 建行"
        assert env.q("SELECT * FROM wrong_book ORDER BY question_uid", db="english") == before
        assert [r[0] for r in env.q("SELECT result FROM review_log ORDER BY id", db="english")] == \
            ["wrong", "wrong"]


def test_wrong_event_creates_wrong_book_via_sm2() -> None:
    """🔴 P0 回归防线（跨模块）：sync_outbox 判分 → sm2_scheduler → 错题本出现该行、
    next_review_at 非空（+1 天），且水位严格晚于事件时间戳（事件不会被判 stale）。"""
    with temp_env("sm2_flow") as env:
        make_case(env, "english", "grammar_fill", "I am here", [("att_i", "q_i", "zzz")])  # 答错
        t0 = datetime.now(timezone.utc)
        stats = so.run(mock=True, limit=None, subject=None, dry_run=False)
        t1 = datetime.now(timezone.utc)
        assert stats["synced"] == 1 and stats["failed"] == 0, stats

        ev = env.q("SELECT question_uid, reviewed_at, result FROM review_log", db="english")
        assert len(ev) == 1 and ev[0][2] == "wrong", ev
        assert t0 - timedelta(seconds=5) <= parse_iso(ev[0][1]) <= t1 + timedelta(seconds=5), ev
        assert env.count("wrong_book", db="english") == 0, "错题本此刻必须还是空的（sm2 独占）"

        sub = sm2_run(env, "english")["subjects"]["english"]
        assert (sub["events"], sub["processed"], sub["added"], sub["stale"]) == (1, 1, 1, 0), sub

        wb = env.one("SELECT wrong_count, correct_streak, mastery, next_review_at, updated_at "
                     "FROM wrong_book WHERE question_uid='q_i'", db="english")
        assert wb[0] == 1 and wb[1] == 0, f"首次答错应建行 wrong_count=1/streak=0，实际 {wb}"
        assert wb[3], "next_review_at 必须非空（SM-2 已排程）"
        assert wb[4], "updated_at 必须写（sm2 水位）"
        assert wb[4] > ev[0][1], \
            f"🔴 水位必须严格晚于事件时间戳，否则事件永远判 stale（P0 根因）：{wb[4]} vs {ev[0][1]}"
        delta = parse_iso(wb[3]) - parse_iso(ev[0][1])
        assert timedelta(hours=23) <= delta <= timedelta(hours=25), f"首次答错应排到 +1 天，实际 {delta}"

        # 水位生效：再跑一次不重放
        sub2 = sm2_run(env, "english")["subjects"]["english"]
        assert (sub2["events"], sub2["processed"], sub2["stale"]) == (1, 0, 1), sub2
        assert env.one("SELECT wrong_count FROM wrong_book WHERE question_uid='q_i'",
                       db="english")[0] == 1, "不得重复计数"


# ===================================================================== ⑦ 重试与失败回滚


def test_retry_three_times_then_failed() -> None:
    calls = {"n": 0}

    def boom(*a, **k):
        calls["n"] += 1
        raise RuntimeError("判分服务炸了")

    with temp_env("retry") as env:
        make_case(env, "english", "grammar_fill", "I am here", [("att_r", "q_r", "I am here")])
        delays: list = []
        with fake_sleep(delays), patch_judge_llm(boom):
            stats = so.run(mock=True, limit=None, subject=None, dry_run=False)

        assert calls["n"] == so.MAX_RETRY == 3, f"应重试 {so.MAX_RETRY} 次，实际 {calls['n']}"
        assert delays == [1, 2], f"指数退避应为 1s/2s（MAX_RETRY-1 次），实际 {delays}"
        assert stats["failed"] == 1 and stats["synced"] == 0, stats

        jq = env.one("SELECT judge_status, judge_reason, judge_score FROM judge_queue "
                     "WHERE attempt_id='att_r'")
        assert jq[0] == "failed", jq
        assert jq[1].startswith(f"retry {so.MAX_RETRY}x:"), f"reason 应带重试次数摘要，实际 {jq[1]!r}"
        assert "RuntimeError" in jq[1] and "判分服务炸了" in jq[1], f"reason 应含错误摘要，实际 {jq[1]!r}"
        assert jq[2] is None, jq

        assert env.one("SELECT synced FROM attempts WHERE attempt_id='att_r'")[0] == 0, "失败不得标 synced"
        assert env.count("review_log", db="english") == 0, "失败不得写 review_log（否则 sm2 会数出幽灵事件）"
        assert env.count("wrong_book", db="english") == 0
        assert not env.ledger.exists(), "判分函数抛出前未调用 LLM → 不应记账"


def test_failed_row_rolls_back_partial_writes() -> None:
    """🟠 P1 回归：写回中途失败（科目库缺 review_log 表）→ 重试 3 次全败后，
    attempts/judge_queue 的**半成品必须被回滚**（此前会带着 judge_score + synced=1 一起提交）。"""
    with temp_env("rollback") as env:
        make_case(env, "english", "grammar_fill", "I am here", [("att_p", "q_p", "zzz")],
                  review_log=False)      # 故障注入：科目库没有 review_log 表
        assert "review_log" not in env.tables("english")
        delays: list = []
        with fake_sleep(delays):
            stats = so.run(mock=True, limit=None, subject=None, dry_run=False)
        assert stats["failed"] == 1 and stats["synced"] == 0, stats
        assert delays == [1, 2], delays

        jq = env.one("SELECT judge_status, judge_score, judge_reason FROM judge_queue "
                     "WHERE attempt_id='att_p'")
        assert jq[0] == "failed", jq
        assert jq[1] is None, f"P1 回归：半成品 judge_score 未被回滚（{jq}）"
        assert jq[2].startswith(f"retry {so.MAX_RETRY}x:") and "no such table: review_log" in jq[2], jq
        at = env.one("SELECT synced, judge_score, judge_reason FROM attempts WHERE attempt_id='att_p'")
        assert at[0] == 0 and at[1] is None, f"P1 回归：失败的 attempt 仍被写了半成品（{at}）"
        assert env.count("wrong_book", db="english") == 0


# ===================================================================== ⑧ --dry-run


def test_dry_run_pending_count_without_any_write() -> None:
    seen: list = []
    with temp_env("dry_run") as env:
        make_case(env, "english", "grammar_fill", "I am here",
                  [("att_d1", "q_d1", "I am here"), ("att_d2", "q_d2", "zzz")])
        before_hash = env.judge_queue_hash()
        before_jq = env.judge_queue_dump()
        before_at = env.q("SELECT * FROM attempts ORDER BY attempt_id")

        with probe_openai(seen):
            stats = so.run(mock=True, limit=None, subject=None, dry_run=True)
        assert stats["dry_run"] is True, stats
        assert stats["pending"] == 2, f"dry-run 仍应报出 pending 计数，实际 {stats}"
        assert stats["skipped"] == 2 and stats["synced"] == 0 and stats["failed"] == 0, stats

        assert env.judge_queue_hash() == before_hash, "🔴 dry-run 一行都不许改（judge_queue 哈希变了）"
        assert env.judge_queue_dump() == before_jq
        assert env.q("SELECT * FROM attempts ORDER BY attempt_id") == before_at, "attempts 也不许改"
        assert env.count("review_log", db="english") == 0
        assert env.count("wrong_book", db="english") == 0
        assert not env.ledger.exists()

        rc, payload, _ = run_main(["--dry-run"])
        assert rc == 0 and payload["dry_run"] is True and payload["pending"] == 2, payload
        assert env.judge_queue_hash() == before_hash, "CLI dry-run 也不许改库"
    assert seen == [], f"dry-run 不应 import openai，实际访问 {seen}"


# ===================================================================== ⑨ 空队列


def test_empty_queue_exit_code_zero() -> None:
    with temp_env("empty") as env:
        env.make_attempts()
        rc, payload, _ = run_main(["--mock"])
        assert rc == 0, f"空队列应退出码 0，实际 {rc}：{payload}"
        assert payload["pending"] == 0 and payload["synced"] == 0 and payload["failed"] == 0, payload
        assert not env.ledger.exists()


def test_missing_attempts_db_is_error_exit_1() -> None:
    with temp_env("missing_db") as env:
        assert not env.attempts_db.exists()
        rc, payload, _ = run_main(["--mock"])
        assert rc == 1, payload
        assert "不存在" in payload.get("error", ""), payload
        assert payload["pending"] == 0, payload


# ===================================================================== ⑩ --limit / --subject


def test_limit_processes_only_first_n() -> None:
    with temp_env("limit") as env:
        make_case(env, "english", "grammar_fill", "I am here",
                  [("att_l1", "q_l1", "I am here"), ("att_l2", "q_l2", "I am here"),
                   ("att_l3", "q_l3", "I am here")])
        stats = so.run(mock=True, limit=2, subject=None, dry_run=False)
        assert stats["pending"] == 2, f"--limit 2 应只取前 2 条，实际 pending={stats['pending']}"
        assert stats["synced"] == 2, stats
        assert [r[0] for r in env.q("SELECT judge_status FROM judge_queue ORDER BY id")] == \
               ["synced", "synced", "pending"], "其余必须仍是 pending"
        assert env.count("review_log", db="english") == 2

        stats2 = so.run(mock=True, limit=None, subject=None, dry_run=False)
        assert stats2["pending"] == 1 and stats2["synced"] == 1, stats2
        assert [r[0] for r in env.q("SELECT judge_status FROM judge_queue ORDER BY id")] == ["synced"] * 3

        stats3 = so.run(mock=True, limit=None, subject=None, dry_run=False)   # 已 synced 的行不得重复消费
        assert stats3["pending"] == 0 and stats3["synced"] == 0, stats3
        assert env.count("review_log", db="english") == 3, "重复消费会把作答事件重复写进 sm2 事实源"


def test_subject_filter_selects_one_subject() -> None:
    with temp_env("subject_filter") as env:
        env.make_attempts()
        for subj in ("english", "c_wuhan"):
            env.make_subject(subj)
            env.seed_question(subj, f"q_{subj}", qtype="grammar_fill", answer="I am here")
            env.seed_queue_row(f"att_{subj}", subj, f"q_{subj}", "I am here")
        stats = so.run(mock=True, limit=None, subject="c_wuhan", dry_run=False)
        assert stats["pending"] == 1 and stats["subjects"] == {"c_wuhan": 1}, stats
        assert env.one("SELECT judge_status FROM judge_queue WHERE attempt_id='att_english'")[0] == "pending"
        assert env.one("SELECT judge_status FROM judge_queue WHERE attempt_id='att_c_wuhan'")[0] == "synced"
        assert env.count("review_log", db="c_wuhan") == 1 and env.count("review_log", db="english") == 0


# ===================================================================== ⑪ 成本账本


def test_mock_writes_no_ledger_but_real_usage_does() -> None:
    usage = {"prompt_tokens": 1000, "completion_tokens": 500,
             "prompt_tokens_details": {"cached_tokens": 200}}
    with temp_env("ledger") as env:
        make_case(env, "english", "grammar_fill", "I am here", [("att_m", "q_m", "I am here")])
        so.run(mock=True, limit=None, subject=None, dry_run=False)
        assert not env.ledger.exists(), "🔴 --mock 不得往 logs/cost_ledger.jsonl 写行"

        # 真实分支：离线 monkeypatch judge_llm 返回带 usage 的结果（不发请求）
        env.seed_queue_row("att_real", "english", "q_m", "I am here")
        with patch_judge_llm(lambda *a, **k: (2.0, "real-ish", dict(usage))):
            stats = so.run(mock=False, limit=None, subject=None, dry_run=False)
        assert stats["pending"] == 1 and stats["synced"] == 1, stats

        lines = env.ledger.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1, f"有 usage 的真实调用应记一行，实际 {lines}"
        rec = json.loads(lines[0])
        assert rec["kind"] == "llm_call" and rec["stage"] == "sync_outbox", rec
        assert rec["model"] == "deepseek-flash" and rec["subject"] == "english", rec
        assert rec["usage"] == usage, rec
        assert rec["ts"] and rec["note"] == "grammar_fill", rec
        price = so.PRICE["deepseek-flash"]
        expected = ((1000 - 200) * price["in"] + 200 * price["cache"] + 500 * price["out"]) / 1_000_000
        assert rec["cost_cny"] == round(expected, 6) != 0, f"成本算式不符：{rec['cost_cny']} vs {expected}"
        assert env.one("SELECT result FROM review_log ORDER BY id DESC LIMIT 1", db="english")[0] == "correct"


# ===================================================================== ⑫/⑬ 缺失数据 + submitted 残留态


def test_missing_question_is_failed_not_graded() -> None:
    """题目不存在 → 直接 failed + lookup_failed；不猜（不写 review_log / 错题本）。"""
    with temp_env("lookup_missing_q") as env:
        env.make_attempts()
        env.make_subject("english")
        env.make_subject("aca_llm")
        env.seed_queue_row("att_g1", "english", "q_ghost", "")      # 题干/答案不可得
        env.seed_queue_row("att_g2", "aca_llm", "q_ghost2", "A")
        stats = so.run(mock=True, limit=None, subject=None, dry_run=False)

        assert stats["synced"] == 0 and stats["failed"] == 2, stats
        assert stats["lookup_failed"] == ["题目不存在: english/q_ghost",
                                          "题目不存在: aca_llm/q_ghost2"], stats
        for aid, subj in (("att_g1", "english"), ("att_g2", "aca_llm")):
            st, reason = env.one("SELECT judge_status, judge_reason FROM judge_queue "
                                 "WHERE attempt_id=?", (aid,))
            assert st == "failed" and reason.startswith("题目不存在:"), (aid, st, reason)
            assert env.count("review_log", db=subj) == 0, f"{subj}: 缺失题不得进入事件源"
            assert env.count("wrong_book", db=subj) == 0


def test_missing_subject_db_fails_without_creating_file() -> None:
    """科目库不存在 → failed + lookup_failed，且**不得凭空建空 sqlite**。"""
    with temp_env("lookup_missing_db") as env:
        env.make_attempts()
        env.seed_queue_row("att_nodb", "aca_llm", "q_x", "A")
        assert not env.subject_path("aca_llm").exists()
        stats = so.run(mock=True, limit=None, subject=None, dry_run=False)

        assert stats["synced"] == 0 and stats["failed"] == 1, stats
        err = stats["lookup_failed"][0]
        assert err.startswith("科目库不存在:") and "aca_llm.sqlite" in err, stats
        assert env.one("SELECT judge_status, judge_reason FROM judge_queue "
                       "WHERE attempt_id='att_nodb'") == ("failed", err)
        assert not env.subject_path("aca_llm").exists(), "不得凭空创建一个空科目库文件"


def test_submitted_rows_are_consumed() -> None:
    """`submitted` 是中断残留态 → 必须被消费（原实现只认 pending，会让这些行永久跳过）。"""
    with temp_env("submitted") as env:
        make_case(env, "english", "grammar_fill", "I am here", [("att_sub", "q_sub", "I am here")])
        env.exec("UPDATE judge_queue SET judge_status='submitted' WHERE attempt_id='att_sub'")
        stats = so.run(mock=True, limit=None, subject=None, dry_run=False)
        assert stats["pending"] == 1 and stats["synced"] == 1 and stats["failed"] == 0, stats
        assert env.one("SELECT judge_status FROM judge_queue WHERE attempt_id='att_sub'")[0] == "synced"
        assert env.count("review_log", db="english") == 1


# ===================================================================== 现状记录（KNOWN-ISSUE，不改被测文件）


def test_known_issue_limit_zero_means_no_limit() -> None:
    """KNOWN-ISSUE：`if limit:` 把 `--limit 0` 当成"不限量"（3 条全处理）。"""
    with temp_env("ki_limit0") as env:
        make_case(env, "english", "grammar_fill", "I am here",
                  [("a1", "q1", "I am here"), ("a2", "q2", "I am here"), ("a3", "q3", "I am here")])
        stats = so.run(mock=True, limit=0, subject=None, dry_run=False)
        assert stats["pending"] == 3 and stats["synced"] == 3, \
            f"KNOWN-ISSUE 行为已变（--limit 0 现在被当成 0 条？）：{stats}"


def test_mock_scale_is_normalized_by_full_score() -> None:
    """回归：mock 启发式必须**按该题型满分折算**（`ratio * full_score_for(...)`）。

    修复前：mock 返回 0~1 比率，而英语 per_item 满分是 2/3/10 → `ratio >= full*0.999` 恒不成立
    → `--mock` 下英语题**永远判 wrong**；C 科因 taxonomy 缺 per_item 回落 1.0 反而判 correct
    —— 同一份"完全一致"的作答得到两种相反结论，`--mock` 因此不能当链路自检。
    修复后：英语 2 分题全对 → score == 2.0，且**与 C 科同为 correct**（语义一致）。
    """
    with temp_env("mock_scale_normalized") as env:
        env.make_attempts()
        for subj, qtype in (("english", "grammar_fill"), ("c_wuhan", "code_correction")):
            env.make_subject(subj)
            env.seed_question(subj, f"q_{subj}", qtype=qtype, answer="I am here")
            env.seed_queue_row(f"att_{subj}", subj, f"q_{subj}", "I am here")   # 与答案完全一致
        stats = so.run(mock=True, limit=None, subject=None, dry_run=False)
        assert stats["synced"] == 2, stats
        scores = {r[0]: r[1] for r in env.q("SELECT subject, judge_score FROM judge_queue")}
        assert so.full_score_for("english", "grammar_fill") == 2.0
        assert so.full_score_for("c_wuhan", "code_correction") == 1.0
        # 英语题必须拿到**它的满分 2.0**（而不是比率 1.0）
        assert scores["english"] == 2.0, f"mock 未按满分折算：{scores}"
        assert scores["c_wuhan"] == 1.0, scores
        # 语义一致：两边"完全一致"的作答都应判 correct
        assert env.one("SELECT result FROM review_log", db="english")[0] == "correct", \
            "修复后英语 mock 全对必须判 correct（原 KNOWN-ISSUE 已消除）"
        assert env.one("SELECT result FROM review_log", db="c_wuhan")[0] == "correct"


# ===================================================================== 收尾自检


def test_target_revision_checked() -> None:
    """记录本套用例对齐的被测脚本修订；若脚本又被改过，打印提示（不失败）。"""
    got = hashlib.sha256((REAL_ROOT / "scripts" / "sync_outbox.py").read_bytes()).hexdigest().upper()
    if got != VALIDATED_SHA256:
        print(f"    [note] sync_outbox.py 已改动：现值 {got[:16]}… ≠ 对齐值 {VALIDATED_SHA256[:16]}…，"
              f"请复核受影响用例")
    assert True


def test_module_globals_restored_and_real_db_untouched() -> None:
    """测试全程必须留在临时环境里：模块全局已复原，且真实 data/attempts.sqlite 指纹未变。"""
    for name in PATCHED_GLOBALS:
        got = getattr(so, name)
        assert str(REAL_ROOT) in str(got), f"sync_outbox.{name} 未复原到真实项目路径：{got}"
    assert so.ATTEMPTS_DB == REAL_ROOT / "data" / "attempts.sqlite"
    assert callable(so.judge_llm), "judge_llm 必须被复原"
    assert real_db_fingerprint() == REAL_JQ_BASELINE, \
        "真实 data/attempts.sqlite 的 judge_queue 被改动了（测试泄漏！）"


def test_compile() -> None:
    import py_compile

    py_compile.compile(str(REAL_ROOT / "scripts" / "sync_outbox.py"), doraise=True)


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
    print(f"{len(fns) - failed}/{len(fns)} passed")
    if failed:
        print(f"  （现场保留在 {TMPROOT}，本次运行后缀 .{RUN_TAG}）")
    else:
        for d in TMPROOT.glob(f"*.{RUN_TAG}"):   # 只清自己这一次运行的目录
            shutil.rmtree(d, ignore_errors=True)
        with contextlib.suppress(OSError):
            TMPROOT.rmdir()                      # 空目录才删得掉，绝不碰别人的现场
    raise SystemExit(1 if failed else 0)
