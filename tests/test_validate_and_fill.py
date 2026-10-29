#!/usr/bin/env python
"""validate_and_fill.py 离线测试 —— **零真实 API 调用、零花费**。

被测对象: `scripts/validate_and_fill.py`（唯一会为"补题"花钱的脚本）
下游契约: `scripts/update_review_status.py`（审核队列 5 列 + 解析器的 skip/invalid 语义）

覆盖（按重要性）:
  ① 覆盖分档   basis="any" 覆盖 = approved+pending_review+parsed；basis="approved"（默认）**只算已通过审核**，
               待审/被拒不减少缺口；并守住防线「同一数据 approved 缺口 ≥ any 缺口」
  ② 配额与缺口 paper_count 比例折算 / 无 paper_count 科目均分 / 超配额时 gap 夹到 0
  ③ 审核队列契约 产物必须能被 update_review_status.parse_queue 读入（未填 decision = skip ≠ invalid）
  ④ 成本闸门   estimate_cost **逐题型**取 routing.json 价 + 默认高峰 ×2；--dry-run 不碰 sqlite；cap / 80% 预算线退出 2 且零 API
  ⑤ 生成缓存   gen_cache_put → gen_cache_get 命中并递增 hit_count；未命中 None
  ⑥ 少样本蒸馏 few_shot 优先 approved、无 approved 时回落、条数 ≤ k
  ⑦ 矩阵落盘   build_matrix 形状 + ACA 模块数一致 + 读不到考纲时优雅降级
  ⑧ 进度守卫   恒返回重复题干（P0）必须在 2 轮无新增后打 `[stall]` 有界退出；有进展时不得误伤
  ⑨ 题型路由   ROUTING_KEY 必须覆盖 taxonomy 全部题型（P2：英语四题型 / c_* 不再回退 c_error）

🔴 全程不联网怎么做（关键设计）:
   CLI 用例把被测脚本**逐字节复制**到临时项目根（脚本用 `__file__` 推导 ROOT，副本即隔离），
   再用 `PYTHONPATH` 注入**假 openai 模块**（`<root>/fake_openai/openai.py`）。
   真 openai（本机 site-packages 里确实装了）永远不会被 import。
   `test_cli_control_fake_openai_is_reachable` 是**反向对照**：预算放开时必须触发假模块，
   以此证明"闸门拒绝"用例里 marker 缺失 == 真的没进生成分支（而不是假模块没挂上）。

⚠️ 临时目录只用 tests/.tmp/validate_and_fill/<case>/（沙箱拒删系统临时目录，见决策记录第 10 节）。

运行: python tests/test_validate_and_fill.py
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import init_db  # noqa: E402
import update_review_status as urs  # noqa: E402
import validate_and_fill as vaf  # noqa: E402

PY = sys.executable
TMPROOT = ROOT / "tests" / ".tmp" / "validate_and_fill"
VAF_SRC = ROOT / "scripts" / "validate_and_fill.py"
LIB_DIR = ROOT / "scripts" / "lib"
REAL_SYLLABUS = ROOT / "subjects" / "aca_llm" / "syllabus_index.json"

FLASH = vaf.PRICE["deepseek-flash"]
PRO = vaf.PRICE["deepseek-v4-pro"]
PER_Q_FLASH = (vaf.EST_IN * FLASH["in"] + vaf.EST_OUT * FLASH["out"]) / 1_000_000  # ¥/题（flash）
PER_Q_PRO = (vaf.EST_IN * PRO["in"] + vaf.EST_OUT * PRO["out"]) / 1_000_000        # ¥/题（pro）

# 与真实 config/routing.json 同形（英语语法 → flash；写作/C编程 → pro）
DEFAULT_ROUTING = {
    "generate": {
        "aca_choice": {"model": "deepseek-flash", "batch": 8, "effort": "low"},
        "english_grammar": {"model": "deepseek-flash", "batch": 5, "effort": "low"},
        "english_writing": {"model": "deepseek-v4-pro", "batch": 3, "effort": "high"},
        "c_error": {"model": "deepseek-flash", "batch": 5, "effort": "low"},
        "c_program": {"model": "deepseek-v4-pro", "batch": 3, "effort": "high"},
    }
}

# --------------------------------------------------------------- 假 openai 模块
# r'''...'''：反斜杠原样写入文件（生成的是 `fh.write(tag + "\n")`）。
FAKE_OPENAI_SRC = r'''"""假 openai 模块（仅测试用）：证明被测脚本没有调用真实 API。"""
import os
from pathlib import Path

_MARKER = Path(os.environ["FAKE_OPENAI_MARKER"])
_MODE = os.environ.get("FAKE_OPENAI_MODE", "raise")
_PAYLOAD = os.environ.get("FAKE_OPENAI_PAYLOAD", "{}")
_STATE = {"n": 0}


def _mark(tag):
    with _MARKER.open("a", encoding="utf-8") as fh:
        fh.write(tag + "\n")


_mark("import")


class _Message:
    def __init__(self, content):
        self.content = content


class _Choice:
    def __init__(self, content):
        self.message = _Message(content)


class _Usage:
    def model_dump(self):
        return {"prompt_tokens": 1600, "completion_tokens": 900}


class _Completions:
    def create(self, **kw):
        _STATE["n"] += 1
        _mark("create#%d" % _STATE["n"])
        if _MODE == "raise":
            raise RuntimeError("FAKE_OPENAI_API_CALLED")
        content = _PAYLOAD.replace("@@N@@", str(_STATE["n"]))
        return type("Resp", (), {"choices": [_Choice(content)], "usage": _Usage()})()


class OpenAI:
    def __init__(self, *a, **kw):
        _mark("construct")
        self.chat = type("Chat", (), {"completions": _Completions()})()
'''


# --------------------------------------------------------------------- 夹具


def fresh_dir(name: str) -> Path:
    """工作区内干净临时目录（系统临时目录删不掉，见决策记录第 10 节）。"""
    d = TMPROOT / name
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True, exist_ok=True)
    return d


def file_sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


class Env:
    """临时项目根 + 把 vaf 的模块级常量重定向过去（monkeypatch 风格）。"""

    PATCHED = ("ROOT", "DATA", "LOGS", "LEDGER", "MATRIX", "REVIEW_Q", "GEN_CACHE", "ENV_FILE")

    def __init__(self, name: str):
        self.root = fresh_dir(name)
        self.data = self.root / "data"
        self.config = self.root / "config"
        self.output = self.root / "output"
        self.logs = self.root / "logs"
        for d in (self.data, self.config, self.output, self.logs):
            d.mkdir(parents=True, exist_ok=True)
        self._saved: dict = {}

    def __enter__(self) -> "Env":
        self._saved = {k: getattr(vaf, k) for k in self.PATCHED}
        vaf.ROOT = self.root
        vaf.DATA = self.data
        vaf.LOGS = self.logs
        vaf.LEDGER = self.logs / "cost_ledger.jsonl"
        vaf.MATRIX = self.data / "coverage_matrix.json"
        vaf.REVIEW_Q = self.output / "review_queue.md"
        vaf.GEN_CACHE = self.data / "generation_cache.sqlite"
        vaf.ENV_FILE = self.root / ".env"
        return self

    def __exit__(self, *exc) -> bool:
        for k, v in self._saved.items():
            setattr(vaf, k, v)
        return False


def tax(target: int = 50, types: dict | None = None) -> dict:
    """单科目（english）taxonomy；默认一个题型 paper_count=10 → quota == target。"""
    return {
        "english": {
            "name": "英语（测试）",
            "target_count": target,
            "question_types": types or {"grammar_fill": {"name": "语法填空", "paper_count": 10}},
        }
    }


def write_taxonomy(root: Path, subjects_cfg: dict) -> None:
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "config" / "taxonomy.json").write_text(
        json.dumps({"version": "test", "subjects": subjects_cfg}, ensure_ascii=False), encoding="utf-8")


def write_routing(root: Path, generate: dict | None) -> None:
    (root / "config").mkdir(parents=True, exist_ok=True)
    p = root / "config" / "routing.json"
    if generate is None:
        p.unlink(missing_ok=True)
    else:
        p.write_text(json.dumps({"generate": generate}, ensure_ascii=False), encoding="utf-8")


def seed_db(root: Path, subject: str, spec: dict, answer: str = "参考答案") -> list[tuple[str, str, str]]:
    """建科目库（复用 init_db.SUBJECT_SCHEMA，与真实库同构）并插题。

    spec = {qtype: {status: n}}。返回 [(uid, qtype, status)]。
    """
    (root / "data").mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(root / "data" / f"{subject}.sqlite"))
    conn.execute("PRAGMA journal_mode=WAL")  # 与 init_db 一致：WAL 写进库文件，避免后续改 mtime
    conn.executescript(init_db.SUBJECT_SCHEMA)
    uids: list[tuple[str, str, str]] = []
    for qtype, by_status in spec.items():
        for status, n in by_status.items():
            for i in range(n):
                uid = f"uid-{subject}-{qtype}-{status}-{i}"
                conn.execute(
                    "INSERT INTO questions(question_uid, subject, question_type, stem, answer, explanation,"
                    " status, version) VALUES(?,?,?,?,?,?,?,1)",
                    (uid, subject, qtype, f"【{subject}/{qtype}】第 {i} 题题干（{status}）",
                     answer, "解析", status))
                uids.append((uid, qtype, status))
    conn.commit()
    conn.close()
    return uids


def non_subject_dbs(root: Path) -> None:
    """attempts / cache / generation_cache（与 init_db 同构）。"""
    for name, schema in (("attempts.sqlite", init_db.ATTEMPTS_SCHEMA),
                         ("cache.sqlite", init_db.CACHE_SCHEMA),
                         ("generation_cache.sqlite", init_db.GEN_SCHEMA)):
        conn = sqlite3.connect(str(root / "data" / name))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(schema)
        conn.commit()
        conn.close()


def db_snapshot(data_dir: Path) -> dict[str, dict]:
    """每个 sqlite 的 mtime_ns / size / questions 行数（只读连接，不改库）。"""
    out: dict[str, dict] = {}
    for p in sorted(data_dir.glob("*.sqlite")):
        st = p.stat()
        conn = sqlite3.connect(str(p))
        try:
            has_q = conn.execute(
                "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='questions'").fetchone()[0]
            rows = conn.execute("SELECT count(*) FROM questions").fetchone()[0] if has_q else None
        finally:
            conn.close()
        out[p.name] = {"mtime_ns": st.st_mtime_ns, "size": st.st_size, "questions": rows}
    return out


def tree_snapshot(root: Path) -> dict[str, tuple[int, int]]:
    """整棵树的 (mtime_ns, size)；忽略 __pycache__ 与 sqlite 的 -wal/-shm 辅助文件。"""
    out: dict[str, tuple[int, int]] = {}
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        if "__pycache__" in rel or rel.endswith(("-wal", "-shm")):
            continue
        st = p.stat()
        out[rel] = (st.st_mtime_ns, st.st_size)
    return out


# ------------------------------------------------------------------- CLI 夹具


def build_cli_root(name: str, *, target: int = 6, types: dict | None = None, spec: dict | None = None,
                   routing: dict | None = None, budget: dict | None = None, syllabus: bool = False,
                   env_file: bool = True) -> Path:
    """临时项目根：复制被测脚本（逐字节）+ 最小 config/data，供 subprocess 跑真 CLI。"""
    root = fresh_dir(name)
    for sub in ("data", "config", "output", "logs", "scripts", "subjects"):
        (root / sub).mkdir(parents=True, exist_ok=True)

    shutil.copy2(VAF_SRC, root / "scripts" / "validate_and_fill.py")
    shutil.copytree(LIB_DIR, root / "scripts" / "lib",
                    ignore=shutil.ignore_patterns("__pycache__"))
    # 🔴 不允许改被测脚本 → 只跑副本，但副本必须与原文件逐字节一致（否则测的不是被测对象）
    assert file_sha(root / "scripts" / "validate_and_fill.py") == file_sha(VAF_SRC), \
        "临时副本与 scripts/validate_and_fill.py 不一致"

    write_taxonomy(root, tax(target, types))
    write_routing(root, routing or DEFAULT_ROUTING["generate"])
    (root / "config" / "cost_budget.json").write_text(
        json.dumps(budget or {"version": "test", "currency": "CNY", "total": 20.0, "warning": 0.8},
                   ensure_ascii=False), encoding="utf-8")
    # 假凭据 + 死地址（双保险：假模块已拦截，即便漏了也连不上任何服务）
    if env_file:
        (root / ".env").write_text(
            "DEEPSEEK_API_KEY=sk-TEST-DUMMY-NOT-A-REAL-KEY\n"
            "DEEPSEEK_BASE_URL=http://127.0.0.1:9/dead-end\n", encoding="utf-8")

    (root / "fake_openai").mkdir(exist_ok=True)
    (root / "fake_openai" / "openai.py").write_text(FAKE_OPENAI_SRC, encoding="utf-8")

    if syllabus and REAL_SYLLABUS.exists():
        (root / "subjects" / "aca_llm").mkdir(parents=True, exist_ok=True)
        shutil.copy2(REAL_SYLLABUS, root / "subjects" / "aca_llm" / "syllabus_index.json")

    non_subject_dbs(root)
    for subject, typespec in (spec or {}).items():
        seed_db(root, subject, typespec)
    return root


def fake_marker(root: Path) -> Path:
    return root / "fake_openai_calls.log"


def run_cli(root: Path, args: list[str], *, fake_mode: str = "raise", payload: str = "{}",
            timeout: int = 120) -> subprocess.CompletedProcess:
    """跑临时根里的 CLI，PYTHONPATH 注入假 openai（真 openai 不会被 import）。"""
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    parts = [str(root / "fake_openai")] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])
    env["PYTHONPATH"] = os.pathsep.join(parts)
    env["FAKE_OPENAI_MARKER"] = str(fake_marker(root))
    env["FAKE_OPENAI_MODE"] = fake_mode
    env["FAKE_OPENAI_PAYLOAD"] = payload
    env["DEEPSEEK_API_KEY"] = "sk-TEST-DUMMY-NOT-A-REAL-KEY"
    env["OPENAI_API_KEY"] = "sk-TEST-DUMMY-NOT-A-REAL-KEY"
    return subprocess.run(
        [PY, str(root / "scripts" / "validate_and_fill.py"), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout, cwd=str(root), env=env,
    )


def gen_payload(template: bool = True) -> str:
    return json.dumps({"questions": [{
        "stem": "离线生成题干 @@N@@ 号（端到端离线测试用，长度足够）" if template else "永远相同的题干内容（重复题，长度足够）",
        "answer": "参考答案 @@N@@" if template else "参考答案", "explanation": "解析",
        "knowledge_point": "考点", "difficulty": "中", "fact_claim": "可核查主张",
        "fact_source": "AI生成-未验证"}]}, ensure_ascii=False)


def q_item(stem: str) -> dict:
    return {"stem": stem, "answer": "参考答案", "explanation": "解析", "knowledge_point": "考点",
            "difficulty": "中", "fact_claim": "可核查主张", "fact_source": "AI生成-未验证"}


def printed_est(stdout: str) -> float:
    """取 CLI 打印的"预估生成成本 ¥x.xx"（不依赖浮点格式化逐位一致）。"""
    m = re.search(r"预估生成成本 ¥([0-9]+(?:\.[0-9]+)?)", stdout)
    assert m, f"未在输出里找到成本预估行：\n{stdout[-600:]}"
    return float(m.group(1))


def question_count(root: Path, subject: str = "english") -> int:
    conn = sqlite3.connect(str(root / "data" / f"{subject}.sqlite"))
    try:
        return conn.execute("SELECT count(*) FROM questions").fetchone()[0]
    finally:
        conn.close()


def fake_calls(root: Path) -> int:
    marker = fake_marker(root)
    return marker.read_text(encoding="utf-8").count("create#") if marker.exists() else 0


# ===================================================================== ① 覆盖分档


def test_coverage_basis_any_counts_pending_and_parsed() -> None:
    """basis="any"（早期口径）：覆盖 = approved + pending_review + parsed，缺口按三者之和算。"""
    with Env("coverage_any") as env:
        write_taxonomy(env.root, tax(50))
        seed_db(env.root, "english", {"grammar_fill": {
            "approved": 4, "pending_review": 3, "parsed": 5, "rejected": 2, "raw": 1}})
        m = vaf.build_matrix("any")
        assert m["basis"] == "any", f"矩阵必须记录本次口径，实际 {m.get('basis')}"
        s = m["subjects"]["english"]

        assert s["covered_approved"] == 4, f"已通过只算 approved=4，实际 {s['covered_approved']}"
        assert s["covered_pending"] == 8, f"待审应 = pending_review(3)+parsed(5)=8，实际 {s['covered_pending']}"
        assert s["covered_any"] == 12, f"any 口径覆盖 = 4+8=12，实际 {s['covered_any']}"
        assert s["rejected"] == 2, f"被拒题必须单列计数，实际 {s['rejected']}"
        assert s["gaps"]["grammar_fill"] == 38, f"any 口径缺口 = 50-12=38，实际 {s['gaps']}"
        assert s["gap_total"] == 38, s["gap_total"]

        t = s["by_type"]["grammar_fill"]
        assert (t["approved"], t["pending_review"], t["parsed"], t["rejected"]) == (4, 3, 5, 2), t
        assert t["other"] == 1, f"未列入分档的 status（raw）应进 other，实际 {t['other']}"


def test_coverage_basis_approved_ignores_pending_and_rejected() -> None:
    """basis="approved"（新默认，诚实覆盖率）：待审 / 被拒题**都不减少缺口**。"""
    with Env("coverage_approved") as env:
        write_taxonomy(env.root, tax(50))
        seed_db(env.root, "english", {"grammar_fill": {
            "approved": 4, "pending_review": 3, "parsed": 5, "rejected": 2, "raw": 1}})

        m = vaf.build_matrix()                       # 默认口径
        assert m["basis"] == "approved", f"默认口径必须是 approved，实际 {m.get('basis')}"
        s = m["subjects"]["english"]
        assert s["covered_approved"] == 4, s["covered_approved"]
        assert s["covered_pending"] == 8, "待审计数仍要如实上报（只作展示，不参与缺口）"
        assert s["rejected"] == 2, s["rejected"]
        assert s["covered_any"] == 4, "approved 口径下 covered_any 只累计 have()（=approved）"
        assert s["gaps"]["grammar_fill"] == 46, f"缺口只能按 approved=4 算 → 46，实际 {s['gaps']}"
        assert s["gap_total"] == 46, s["gap_total"]

        assert vaf.build_matrix("approved")["basis"] == "approved", "显式传 approved 也必须生效"
        assert vaf.build_matrix("approved")["subjects"]["english"]["gap_total"] == 46


def test_parsed_only_subject_is_pending_under_any_but_not_covered_under_approved() -> None:
    """回归守卫：旧口径漏算 parsed 会让"仅 parsed"的科目覆盖显示 0（any 必须认得它）；
    而 approved 口径下"已解析未审核"不算可用覆盖，缺口保持全额。"""
    with Env("parsed_only") as env:
        write_taxonomy(env.root, tax(50))
        seed_db(env.root, "english", {"grammar_fill": {"parsed": 12}})

        any_s = vaf.build_matrix("any")["subjects"]["english"]
        assert any_s["covered_approved"] == 0, any_s["covered_approved"]
        assert any_s["covered_pending"] == 12, f"parsed 必须计入 any 口径的待审覆盖，实际 {any_s['covered_pending']}"
        assert any_s["gaps"]["grammar_fill"] == 38, any_s["gaps"]

        app_s = vaf.build_matrix("approved")["subjects"]["english"]
        assert app_s["covered_pending"] == 12, app_s["covered_pending"]
        assert app_s["gaps"]["grammar_fill"] == 50, f"approved 口径下 parsed 不减少缺口，实际 {app_s['gaps']}"
        assert app_s["gap_total"] == 50, app_s["gap_total"]


def test_approved_basis_gap_is_never_smaller_than_any_basis() -> None:
    """🔴 防线（本轮新增语义）：同一份数据下 approved 口径的缺口**不可能更小**。

    动机：实测 698 道英语题里 413 道被审核拒绝，旧 any 口径把缺口算成 0 → 掩盖真实短缺。
    """
    with Env("basis_regression") as env:
        write_taxonomy(env.root, {
            "english": {"name": "英语", "target_count": 50,
                        "question_types": {"grammar_fill": {"name": "语法填空", "paper_count": 10}}},
            # 无 paper_count → 均分：单题型 quota = 50
            "c_wuhan": {"name": "C 武汉", "target_count": 50,
                        "question_types": {"program_fill": {"name": "程序填空"}}},
        })
        seed_db(env.root, "english", {"grammar_fill": {
            "approved": 4, "pending_review": 3, "parsed": 5, "rejected": 9}})
        seed_db(env.root, "c_wuhan", {"program_fill": {"approved": 10, "pending_review": 6}})

        any_m = vaf.build_matrix("any")["subjects"]
        app_m = vaf.build_matrix("approved")["subjects"]
        assert set(any_m) == set(app_m) == {"english", "c_wuhan"}, (sorted(any_m), sorted(app_m))

        for subj in app_m:
            a, b = app_m[subj], any_m[subj]
            assert a["gap_total"] >= b["gap_total"], \
                f"{subj}: approved 缺口 {a['gap_total']} 必须 ≥ any 缺口 {b['gap_total']}"
            assert a["covered_any"] <= b["covered_any"], f"{subj}: approved 口径覆盖不得更多"
            assert all(g >= 0 for g in a["gaps"].values()), a["gaps"]

        # 有待审/被拒题时必须是**严格**更大（正是它暴露了被 any 掩盖的短缺）
        assert app_m["english"]["gap_total"] > any_m["english"]["gap_total"]
        assert (any_m["english"]["gap_total"], app_m["english"]["gap_total"]) == (38, 46)
        assert (any_m["c_wuhan"]["gap_total"], app_m["c_wuhan"]["gap_total"]) == (34, 40)


# ================================================================ ② 配额与缺口


def test_quota_proportional_to_paper_count() -> None:
    """有 paper_count 的科目（english / aca_llm）按比例折算到 target_count。"""
    with Env("quota_proportional") as env:
        write_taxonomy(env.root, {
            "english": {"name": "英语", "target_count": 50, "question_types": {
                "grammar_fill": {"name": "语法填空", "paper_count": 10},
                "sentence_build": {"name": "连词成句", "paper_count": 6},
                "reading_fill": {"name": "阅读填空", "paper_count": 10},
                "reading_qa": {"name": "阅读理解", "paper_count": 10},
                "translation_fill": {"name": "翻译填空", "paper_count": 6},
                "writing": {"name": "写作", "paper_count": 1}}},
            "aca_llm": {"name": "ACA", "target_count": 50, "question_types": {
                "single_choice": {"name": "单选", "paper_count": 35},
                "multiple_choice": {"name": "多选", "paper_count": 15}}},
        })
        for subj in ("english", "aca_llm"):
            seed_db(env.root, subj, {})  # 空库：gaps == quota，便于直接断言配额
        m = vaf.build_matrix()["subjects"]

        # round(50*10/43)=12, round(50*6/43)=7, round(50*1/43)=1
        assert m["english"]["quota"] == {"grammar_fill": 12, "sentence_build": 7, "reading_fill": 12,
                                         "reading_qa": 12, "translation_fill": 7, "writing": 1}, m["english"]["quota"]
        assert m["english"]["gaps"] == m["english"]["quota"], m["english"]["gaps"]
        assert m["english"]["gap_total"] == 51, m["english"]["gap_total"]
        q = m["english"]["quota"]
        assert q["grammar_fill"] > q["sentence_build"] > q["writing"], "配额必须随 paper_count 单调"
        assert m["aca_llm"]["quota"] == {"single_choice": 35, "multiple_choice": 15}, m["aca_llm"]["quota"]
        assert m["aca_llm"]["gap_total"] == 50, m["aca_llm"]["gap_total"]


def test_quota_even_split_when_no_paper_count() -> None:
    """没有 paper_count 的科目（c_wuhan / c_hbpu）均分——原实现 total_items=0 → 缺口恒为 0。"""
    c_types = {"code_correction": {"name": "改错"}, "program_fill": {"name": "程序填空"},
               "programming": {"name": "编程"}}
    with Env("quota_even") as env:
        write_taxonomy(env.root, {
            "c_wuhan": {"name": "C 武汉", "target_count": 50, "question_types": dict(c_types)},
            "c_hbpu": {"name": "C 湖理", "target_count": 50, "question_types": dict(c_types)},
        })
        seed_db(env.root, "c_wuhan", {})
        seed_db(env.root, "c_hbpu", {})
        m = vaf.build_matrix()["subjects"]

        for subj in ("c_wuhan", "c_hbpu"):
            mm = m[subj]
            assert mm["quota"] == {"code_correction": 16, "program_fill": 16, "programming": 16}, \
                f"{subj} 无 paper_count 应均分 50//3=16，实际 {mm['quota']}"
            assert mm["gap_total"] == 48, \
                f"{subj} 空库缺口应为 48（原实现恒为 0，本轮修复），实际 {mm['gap_total']}"
            assert set(mm["gaps"]) == set(mm["quota"]), mm["gaps"]
            assert all(g > 0 for g in mm["gaps"].values()), mm["gaps"]


def test_gap_is_clamped_to_zero_when_over_quota() -> None:
    """题量超配额时 gap 为 0，不出现负数。"""
    c_types = {"code_correction": {"name": "改错"}, "program_fill": {"name": "程序填空"},
               "programming": {"name": "编程"}}
    with Env("quota_clamp") as env:
        write_taxonomy(env.root, {"c_wuhan": {"name": "C 武汉", "target_count": 50, "question_types": c_types}})
        # quota 各 16：改错 20（超 4）→ 必须夹到 0；程序填空 2 → 14；编程 16 → 0
        seed_db(env.root, "c_wuhan", {"code_correction": {"approved": 20},
                                      "program_fill": {"approved": 2},
                                      "programming": {"approved": 16}})
        m = vaf.build_matrix()["subjects"]["c_wuhan"]

        assert m["gaps"]["code_correction"] == 0, f"20-16 超配额应夹到 0，实际 {m['gaps']['code_correction']}"
        assert m["gaps"]["program_fill"] == 14, m["gaps"]
        assert m["gaps"]["programming"] == 0, m["gaps"]
        assert m["gap_total"] == 14, m["gap_total"]
        assert all(g >= 0 for g in m["gaps"].values()), "缺口不得为负"
        assert m["covered_approved"] == 38, m["covered_approved"]


# ============================================================= ③ 审核队列契约


def test_review_queue_parsed_by_downstream_contract() -> None:
    """队列产物必须能被 update_review_status.parse_queue 正确读入，且未填 decision = skip ≠ invalid。"""
    with Env("review_queue") as env:
        write_taxonomy(env.root, tax(50))
        seed_db(env.root, "english", {"grammar_fill": {"parsed": 4, "pending_review": 3, "approved": 2}})
        n = vaf.write_review_queue()
        assert n == 7, f"队列只应收 parsed+pending_review（4+3=7），实际 {n}（approved 不得入队）"

        text = vaf.REVIEW_Q.read_text(encoding="utf-8")
        head = next(l for l in text.splitlines() if l.startswith("| question_uid"))
        head_cols = [c.strip() for c in head.strip("|").split("|")]
        assert head_cols == list(urs.CANONICAL_COLUMNS), \
            f"表头必须与下游 CANONICAL_COLUMNS 完全一致，实际 {head_cols}"

        rows, invalid = urs.parse_queue(vaf.REVIEW_Q)
        assert invalid == [], f"下游不得把任何一行判为 invalid，实际 {invalid}"
        assert len(rows) == n == 7, f"有效行数应 == 队列条数 7，实际 {len(rows)}"
        assert all(r["decision"] == "skip" for r in rows), \
            f"未填 decision 必须当作 skip（本轮修过），实际 {[r['decision'] for r in rows]}"
        assert all(r["reason"] == "" for r in rows), "未拒绝时 reason 应为空"
        assert {r["subject"] for r in rows} == {"english"}, rows
        assert {r["status_snapshot"] for r in rows} == {"parsed", "pending_review"}, rows

        conn = sqlite3.connect(str(env.data / "english.sqlite"))
        db = dict(conn.execute("SELECT question_uid, status FROM questions").fetchall())
        conn.close()
        assert all(db[r["question_uid"]] == r["status_snapshot"] for r in rows), \
            "status_snapshot 必须等于库中当前 status（否则下游快照校验全冲突）"

        # 真的走一遍下游（dry-run）：7 行都算"未填决策"，既不 invalid 也不落库
        res = urs.run(vaf.REVIEW_Q, dry_run=True, root=env.root)
        assert (res["updated"], res["conflicts"], res["missing"], res["invalid"]) == (0, 0, 0, 0), res
        assert res.get("skipped_unfilled") == 7, f"未填决策应计入 skipped_unfilled=7，实际 {res.get('skipped_unfilled')}"


def test_现状_queue_limit_is_per_subject_not_global() -> None:
    """现状记录（不失败）：write_review_queue(limit) 的 limit 是**每科目**上限，不是全局队列长度。"""
    with Env("queue_limit") as env:
        write_taxonomy(env.root, tax(50))
        seed_db(env.root, "english", {"grammar_fill": {"parsed": 5}})
        seed_db(env.root, "aca_llm", {"single_choice": {"parsed": 5}})
        n = vaf.write_review_queue(limit=3)
        assert n == 6, f"现状：limit=3 得到 6 条（3×2 个科目），实际 {n}"


# ================================================================= ④ 成本闸门


def test_estimate_cost_linear_and_uses_routing_price() -> None:
    with Env("estimate") as env:
        write_routing(env.root, {"english_grammar": {"model": "deepseek-flash"},
                                 "english_writing": {"model": "deepseek-v4-pro"},
                                 "aca_choice": {"model": "deepseek-v4-pro"}})
        e1 = vaf.estimate_cost("english", {"grammar_fill": 100})
        e2 = vaf.estimate_cost("english", {"grammar_fill": 200})
        assert abs(e2 - 2 * e1) < 1e-12, f"成本必须随缺口线性增长：{e1} → {e2}"
        assert abs(e1 - 100 * PER_Q_FLASH * 2) < 1e-12, \
            f"英语语法填空应按 routing.json 的 english_grammar=flash、且默认高峰 ×2 计价" \
            f"（{100 * PER_Q_FLASH * 2}），实际 {e1}"
        e_aca = vaf.estimate_cost("aca_llm", {"single_choice": 100})
        assert abs(e_aca - 100 * PER_Q_PRO * 2) < 1e-12, \
            f"ACA 应按 routing.json 的 aca_choice=pro 计价（{100 * PER_Q_PRO * 2}），实际 {e_aca}"
        assert e_aca > e1, "pro 单价必须高于 flash"
        assert vaf.estimate_cost("english", {"grammar_fill": 0}) == 0.0, "缺口 0 → 成本 0"

        write_routing(env.root, None)  # routing.json 不存在 → 回落默认 flash
        assert abs(vaf.estimate_cost("english", {"grammar_fill": 50}) - 50 * PER_Q_FLASH * 2) < 1e-12, \
            "读不到 routing 必须回落默认价"


def test_estimate_cost_prices_each_question_type_and_peak() -> None:
    """P1 回归：estimate_cost 逐题型取各自 routing 模型，并默认计入高峰 ×2。

    原实现每科目只取一个 routing 键（english→english_grammar、c_*→c_error，都是 flash），
    实跑却对 writing / programming 用 **pro** → 闸门系统性低估（实测差 3.7 倍）。
    """
    with Env("estimate_bias") as env:
        write_routing(env.root, DEFAULT_ROUTING["generate"])

        c_prog = vaf.estimate_cost("c_wuhan", {"programming": 10})
        c_fill = vaf.estimate_cost("c_wuhan", {"program_fill": 10})
        assert c_prog > c_fill * 3, f"编程(pro) 必须明显高于同数量程序填空(flash)：{c_prog} vs {c_fill}"
        assert abs(c_prog / c_fill - PER_Q_PRO / PER_Q_FLASH) < 1e-9, "比值应等于 pro/flash 单价比"
        assert c_prog > vaf.estimate_cost("c_wuhan", {"code_correction": 10}), "改错(flash) 应便宜于编程(pro)"

        en_prog = vaf.estimate_cost("english", {"writing": 10})
        en_fill = vaf.estimate_cost("english", {"grammar_fill": 10})
        assert en_prog > en_fill * 3, f"英语写作(pro) 应贵于语法填空(flash)：{en_prog} vs {en_fill}"

        # 同一科目内多题型求和（混合分布才是真实情形）
        mixed = vaf.estimate_cost("english", {"grammar_fill": 90, "writing": 10})
        assert abs(mixed - (90 * PER_Q_FLASH + 10 * PER_Q_PRO) * 2) < 1e-12, mixed

        off = vaf.estimate_cost("c_wuhan", {"programming": 10}, peak=False)
        assert abs(c_prog - off * 2) < 1e-12, "peak=True 必须恰好是 peak=False 的两倍（高峰单价 ×2）"

        assert vaf.estimate_cost("c_wuhan", {}) == 0.0, "空 gaps → 0"
        assert vaf.estimate_cost("c_hbpu", {}) == 0.0
        assert vaf.estimate_cost("english", {"grammar_fill": -5}) == 0.0, "负缺口不计价"


def test_routing_key_covers_every_taxonomy_type() -> None:
    """P2 回归：ROUTING_KEY 必须逐题型映射；英语四题型与 c_* 不得再静默回退到 c_error。"""
    assert vaf.ROUTING_KEY["english"]["sentence_build"] == "english_grammar", vaf.ROUTING_KEY["english"]
    assert vaf.ROUTING_KEY["english"]["reading_fill"] == "english_grammar"
    assert vaf.ROUTING_KEY["english"]["reading_qa"] == "english_grammar"
    assert vaf.ROUTING_KEY["english"]["translation_fill"] == "english_grammar"
    assert vaf.ROUTING_KEY["english"]["writing"] == "english_writing"
    assert vaf.ROUTING_KEY["c_wuhan"]["programming"] == "c_program"
    assert vaf.ROUTING_KEY["c_hbpu"]["programming"] == "c_program"
    assert vaf.ROUTING_KEY["aca_llm"]["multiple_choice"] == "aca_choice"

    tax_cfg = json.loads((ROOT / "config" / "taxonomy.json").read_text(encoding="utf-8-sig"))
    routing = json.loads((ROOT / "config" / "routing.json").read_text(encoding="utf-8-sig"))
    gen_keys = routing.get("generate") or {}
    for subj, cfg in tax_cfg["subjects"].items():
        for qtype in (cfg.get("question_types") or {}):
            key = (vaf.ROUTING_KEY.get(subj) or {}).get(qtype)
            assert key, f"{subj}/{qtype} 缺 ROUTING_KEY 映射 → 会静默回退到 c_error"
            assert key in gen_keys, f"{subj}/{qtype} → {key} 在 config/routing.json 的 generate 里不存在"


def test_cli_dry_run_touches_no_db_and_writes_only_two_artifacts() -> None:
    """--dry-run 不写库（sqlite mtime/size/行数前后一致），只写 coverage_matrix.json 与 review_queue.md。"""
    root = build_cli_root("cli_dry", target=6,
                          spec={"english": {"grammar_fill": {"approved": 1, "parsed": 2}}})
    before_tree = tree_snapshot(root)
    before_db = db_snapshot(root / "data")

    proc = run_cli(root, ["--dry-run", "--subject", "english"])
    assert proc.returncode == 0, f"dry-run 退出码应为 0，实际 {proc.returncode}\n{proc.stderr[-800:]}"
    assert "dry-run：未发起任何生成请求。" in proc.stdout, proc.stdout[-500:]
    assert "覆盖矩阵" in proc.stdout and "审核队列" in proc.stdout and "（2 条）" in proc.stdout, proc.stdout[-800:]

    after_db = db_snapshot(root / "data")
    assert after_db == before_db, \
        f"dry-run 不得触碰任何 sqlite（mtime_ns/size/questions）：\n  前 {before_db}\n  后 {after_db}"

    changed = {rel for rel, v in tree_snapshot(root).items() if before_tree.get(rel) != v}
    assert changed == {"data/coverage_matrix.json", "output/review_queue.md"}, \
        f"dry-run 只应写这两个产物，实际变化 {changed}"

    matrix = json.loads((root / "data" / "coverage_matrix.json").read_text(encoding="utf-8-sig"))
    assert {"generated_at", "basis", "subjects", "syllabus_modules"} <= set(matrix), sorted(matrix)
    assert matrix["basis"] == "approved", f"CLI 默认口径应为 approved，实际 {matrix['basis']}"
    assert list(matrix["subjects"]) == ["english"], sorted(matrix["subjects"])
    assert matrix["subjects"]["english"]["covered_approved"] == 1
    assert matrix["subjects"]["english"]["covered_pending"] == 2
    assert matrix["subjects"]["english"]["rejected"] == 0
    assert (root / "output" / "review_queue.md").read_text(encoding="utf-8").count("| uid-") == 2

    assert not fake_marker(root).exists(), "dry-run 不应 import openai"
    assert not (root / "logs" / "cost_ledger.jsonl").exists(), "dry-run 不应产生任何记账"


def test_cli_basis_flag_switches_coverage_semantics() -> None:
    """CLI `--basis`：同一份数据下 approved（默认）必须暴露被 any 口径掩盖的缺口。"""
    root = build_cli_root("cli_basis", target=6,
                          spec={"english": {"grammar_fill": {"approved": 1, "parsed": 2, "pending_review": 3}}})

    proc_app = run_cli(root, ["--dry-run", "--subject", "english"])
    assert proc_app.returncode == 0, f"退出码 {proc_app.returncode}\n{proc_app.stderr[-400:]}"
    assert "（口径 basis=approved）" in proc_app.stdout, proc_app.stdout[-400:]
    m_app = json.loads((root / "data" / "coverage_matrix.json").read_text(encoding="utf-8-sig"))
    assert m_app["basis"] == "approved", m_app["basis"]
    # quota 6、approved 只有 1 → 缺口 5（旧 any 口径会算成 0，掩盖短缺）
    assert m_app["subjects"]["english"]["gap_total"] == 5, m_app["subjects"]["english"]

    proc_any = run_cli(root, ["--dry-run", "--subject", "english", "--basis", "any"])
    assert proc_any.returncode == 0, f"退出码 {proc_any.returncode}\n{proc_any.stderr[-400:]}"
    assert "（口径 basis=any）" in proc_any.stdout, proc_any.stdout[-400:]
    m_any = json.loads((root / "data" / "coverage_matrix.json").read_text(encoding="utf-8-sig"))
    assert m_any["basis"] == "any", m_any["basis"]
    assert m_any["subjects"]["english"]["gap_total"] == 0, m_any["subjects"]["english"]

    assert m_app["subjects"]["english"]["gap_total"] > m_any["subjects"]["english"]["gap_total"], \
        "approved 口径必须严格暴露 any 口径掩盖的缺口"
    assert not fake_marker(root).exists(), "两次都必须是 dry-run（零 API）"
    assert not (root / "logs" / "cost_ledger.jsonl").exists()


def test_cli_missing_api_key_exits_1_without_calling_api() -> None:
    """`.env` 里没有 DEEPSEEK_API_KEY 时必须退出 1，且**一次 API 都不调用**。"""
    root = build_cli_root("cli_nokey", target=6, spec={"english": {"grammar_fill": {}}}, env_file=False)
    proc = run_cli(root, ["--subject", "english", "--cap-cny", "2.0"])

    assert proc.returncode == 1, f"缺 key 应退出 1，实际 {proc.returncode}\n{proc.stdout[-400:]}"
    assert "缺少 DEEPSEEK_API_KEY" in proc.stdout, proc.stdout[-400:]
    assert fake_calls(root) == 0, f"没有 key 就绝不能发起调用，实际 {fake_calls(root)} 次"
    assert not (root / "logs" / "cost_ledger.jsonl").exists(), "缺 key 不得产生记账"


def test_cli_cap_gate_exit_2_and_zero_api_calls() -> None:
    """预估 > --cap-cny → 退出码 2，且**没有任何 openai 导入**（零 API 调用）。"""
    root = build_cli_root("cli_gate", target=3500, spec={"english": {"grammar_fill": {"parsed": 1}}})
    proc = run_cli(root, ["--subject", "english", "--cap-cny", "2.0"])

    est = 3500 * PER_Q_FLASH * 2  # quota 3500；该行是 parsed → approved 口径下算 0 覆盖；逐题型 flash 价 + 高峰 ×2
    assert proc.returncode == 2, f"超上限应退出 2，实际 {proc.returncode}\n{proc.stdout[-500:]}"
    assert "超过本次上限" in proc.stdout, proc.stdout[-500:]
    assert abs(printed_est(proc.stdout) - est) < 0.005, \
        f"预估应 = 3500 题 × ¥{PER_Q_FLASH}/题 × 2（高峰）= ¥{est:.2f}\n{proc.stdout[-500:]}"

    assert not fake_marker(root).exists(), \
        "闸门拒绝必须发生在 `from openai import OpenAI` 之前 —— 假 openai 的 import 标记缺失即为零 API 调用"
    assert "FAKE_OPENAI" not in proc.stderr, proc.stderr[-500:]
    assert not (root / "logs" / "cost_ledger.jsonl").exists(), "闸门拒绝不得产生记账"


def test_cli_budget_80pct_gate_exit_2_and_zero_api_calls() -> None:
    """预估 > 预算 80%（20×0.8=16）→ 同样退出 2 且零 API 调用（本次上限放开到 ¥100）。"""
    root = build_cli_root("cli_gate", target=3500, spec={"english": {"grammar_fill": {"parsed": 1}}})
    proc = run_cli(root, ["--subject", "english", "--cap-cny", "100"])

    est = 3500 * PER_Q_FLASH * 2
    assert est > 20 * 0.8, "前置条件：本用例的预估必须超过预算告警线（¥16）"
    assert proc.returncode == 2, f"超预算告警线应退出 2，实际 {proc.returncode}\n{proc.stdout[-500:]}"
    assert "预算告警线" in proc.stdout, proc.stdout[-500:]
    assert "超过本次上限" not in proc.stdout, "上限已放到 ¥100，不应命中上限分支"
    assert abs(printed_est(proc.stdout) - est) < 0.005, f"预估应约 ¥{est:.2f}\n{proc.stdout[-500:]}"
    assert not fake_marker(root).exists(), "预算闸门必须发生在 import openai 之前（零 API 调用）"
    assert not (root / "logs" / "cost_ledger.jsonl").exists()


def test_cli_control_fake_openai_is_reachable() -> None:
    """**反向对照**：预算放开 + 缺口>0 时必须进生成分支并触发假模块。

    没有这条，前面"marker 缺失"的结论可能只是假模块没挂上。真 openai 在 site-packages 里是装了的。
    """
    root = build_cli_root("cli_ctl", target=6, spec={"english": {"grammar_fill": {"approved": 1}}})
    proc = run_cli(root, ["--subject", "english", "--cap-cny", "2.0"])

    assert proc.returncode == 1, f"假模块抛错应让进程以 1 结束，实际 {proc.returncode}\n{proc.stdout[-400:]}"
    marker = fake_marker(root)
    assert marker.exists(), "假 openai 必须被 import（否则 PYTHONPATH 注入失效，全部'零 API'结论作废）"
    assert "import" in marker.read_text(encoding="utf-8")
    assert "FAKE_OPENAI_API_CALLED" in proc.stderr, \
        f"假模块应拦住第一次 chat.completions.create，stderr:\n{proc.stderr[-600:]}"


def test_cli_generation_end_to_end_offline() -> None:
    """假 openai 返回合法 JSON → 生成/落库/刷新队列全链路离线跑通（**零真实请求**）。"""
    root = build_cli_root("cli_gen", target=6, spec={"english": {"grammar_fill": {}}})
    proc = run_cli(root, ["--subject", "english", "--cap-cny", "2.0", "--batch", "3"],
                   fake_mode="ok", payload=gen_payload())
    assert proc.returncode == 0, f"生成链路应退出 0，实际 {proc.returncode}\n{proc.stderr[-800:]}"

    conn = sqlite3.connect(str(root / "data" / "english.sqlite"))
    rows = conn.execute("SELECT question_uid, status, fact_verified, source_type, question_type,"
                        " fact_source, answer, version FROM questions").fetchall()
    conn.close()
    assert len(rows) == 6, f"缺口 6、每次假响应 1 题 → 应生成 6 题，实际 {len(rows)}"
    assert len({r[0] for r in rows}) == 6, "uid 必须唯一"
    for r in rows:
        assert r[1] == "pending_review", f"补题一律 pending_review，实际 {r[1]}"
        assert r[2] == 0, "AI 补题必须 fact_verified=0（防幻觉硬约束）"
        assert r[3] == "generate" and r[4] == "grammar_fill", r
        assert r[5] == "AI生成-未验证", f"fact_source 应显式标注未验证，实际 {r[5]}"
        assert r[6], "答案不得为空"
        assert r[7] == 1, r

    qrows, invalid = urs.parse_queue(root / "output" / "review_queue.md")
    assert len(qrows) == 6 and invalid == [], f"生成后队列应刷新为 6 行且无 invalid，实际 {len(qrows)}/{invalid}"

    ledger = [json.loads(x) for x in (root / "logs" / "cost_ledger.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    assert len(ledger) == 6, f"逐题记账应有 6 条，实际 {len(ledger)}"
    assert all(r["model"] == "deepseek-flash" and r["cost_cny"] > 0 for r in ledger), ledger
    assert all(r["stage"] == "stage7.generate" for r in ledger), ledger

    gc = sqlite3.connect(str(root / "data" / "generation_cache.sqlite"))
    assert gc.execute("SELECT count(*) FROM gen_cache").fetchone()[0] == 6, "每次生成都应写缓存"
    gc.close()
    assert fake_marker(root).read_text(encoding="utf-8").count("create#") == 6, "6 轮 = 6 次（假）调用"


def test_stall_guard_bounds_duplicate_only_response() -> None:
    """P0 回归（原为"现状记录"）：模型反复返回**同一条**题干时，生成循环必须有界退出。

    修复前的行为：uid 命中 → `continue` → gap 不减 → 无样例时 prompt 恒定 → 缓存命中 →
    **永久空转不退出**；有样例时 ORDER BY RANDOM() 让 prompt 每轮变化 → 缓存失效 → **每轮真实扣费**。
    修复后：连续 2 轮无新题入库 → 打印 `[stall] …放弃 …` 并 break。
    """
    root = build_cli_root("cli_dup", target=6, spec={"english": {"grammar_fill": {}}})
    try:
        proc = run_cli(root, ["--subject", "english", "--cap-cny", "2.0"], fake_mode="ok",
                       payload=gen_payload(template=False), timeout=25)
    except subprocess.TimeoutExpired:
        raise AssertionError("P0 未修复：重复题干让生成循环无界空转（25s 超时仍未退出）") from None

    assert proc.returncode == 0, f"应正常结束（退出 0），实际 {proc.returncode}\n{proc.stderr[-500:]}"
    assert "[stall]" in proc.stdout, f"应打印 [stall] 并放弃该题型\n{proc.stdout[-600:]}"
    assert "连续 2 轮无新增" in proc.stdout, f"应以「连续 2 轮无新增」为退出条件\n{proc.stdout[-600:]}"
    assert "已达本次上限" not in proc.stdout, "应由进度守卫退出，而不是撞上花费上限"

    calls = fake_calls(root)
    assert 1 <= calls <= 3, f"重复响应最多允许 2~3 次调用（首次生成 + stall 期间），实际 {calls}"
    assert question_count(root) == 1, "恒定重复题干只应入库 1 题"
    assert "生成 1 题" in proc.stdout, proc.stdout[-300:]


def test_stall_guard_does_not_fire_on_progress() -> None:
    """进度守卫不得误伤：只要每轮仍有新题入库（哪怕同时夹杂重复题），就要一直生成到缺口填满。"""
    root = build_cli_root("cli_progress", target=6, spec={"english": {"grammar_fill": {}}})
    payload = json.dumps({"questions": [
        q_item("固定重复题干（每轮都出现，长度足够）"),
        q_item("每轮递增的新题干 @@N@@ 号（长度足够）"),
    ]}, ensure_ascii=False)

    proc = run_cli(root, ["--subject", "english", "--cap-cny", "2.0", "--batch", "3"],
                   fake_mode="ok", payload=payload, timeout=60)
    assert proc.returncode == 0, f"退出码 {proc.returncode}\n{proc.stderr[-500:]}"
    assert "[stall]" not in proc.stdout, f"有新增却触发进度守卫 = 误伤\n{proc.stdout[-600:]}"
    assert question_count(root) == 6, f"缺口 6 应被填满，实际 {question_count(root)}"
    assert "生成 6 题" in proc.stdout, proc.stdout[-300:]


# ================================================================= ⑤ 生成缓存


def test_gen_cache_put_get_and_hit_count() -> None:
    with Env("gen_cache") as env:
        assert vaf.gen_cache_get("never-put") is None, "库文件都不存在时应返回 None（且不崩）"

        vaf.gen_cache_put("k1", '{"questions":[]}', "deepseek-flash")
        assert vaf.gen_cache_get("k1") == '{"questions":[]}', "put 后必须能命中"
        assert vaf.gen_cache_get("k1") == '{"questions":[]}', "重复命中仍返回同一响应"
        assert vaf.gen_cache_get("k-miss") is None, "未命中必须返回 None"

        conn = sqlite3.connect(str(vaf.GEN_CACHE))
        cols = [r[1] for r in conn.execute("PRAGMA table_info(gen_cache)")]
        hits = conn.execute("SELECT hit_count, model FROM gen_cache WHERE cache_key='k1'").fetchone()
        conn.close()
        assert cols == ["cache_key", "response", "model", "created_at", "hit_count"], cols
        assert hits == (2, "deepseek-flash"), f"两次命中应让 hit_count=2，实际 {hits}"

        # 现状记录（不失败）：put 用 INSERT OR REPLACE，重写同 key 会把 hit_count 归零
        vaf.gen_cache_put("k1", '{"questions":[1]}', "deepseek-flash")
        conn = sqlite3.connect(str(vaf.GEN_CACHE))
        row = conn.execute("SELECT response, hit_count FROM gen_cache WHERE cache_key='k1'").fetchone()
        n_rows = conn.execute("SELECT count(*) FROM gen_cache").fetchone()[0]
        conn.close()
        assert row == ('{"questions":[1]}', 0), f"现状：重写同 key → hit_count 归零，实际 {row}"
        assert n_rows == 1, "同 key 不得产生第二行"


def test_gen_cache_table_matches_init_db_schema() -> None:
    """缓存表结构必须与 init_db.GEN_SCHEMA 同构（避免两处建表漂移）。"""
    with Env("gen_cache_schema") as env:
        vaf.gen_cache_put("k", "r", "m")
        conn = sqlite3.connect(str(vaf.GEN_CACHE))
        got = conn.execute("SELECT sql FROM sqlite_master WHERE name='gen_cache'").fetchone()[0]
        conn.close()
        for col in ("cache_key TEXT PRIMARY KEY", "response TEXT", "model TEXT", "created_at TEXT",
                    "hit_count INTEGER DEFAULT 0"):
            assert col.replace(" ", "") in got.replace(" ", "").replace("\n", ""), f"缺列 {col}：{got}"
        assert "gen_cache" in init_db.GEN_SCHEMA and "hit_count INTEGER DEFAULT 0" in init_db.GEN_SCHEMA


# ============================================================== ⑥ 少样本蒸馏


def test_few_shot_prefers_approved() -> None:
    with Env("few_shot_approved") as env:
        rows = seed_db(env.root, "english", {"grammar_fill": {"approved": 4, "pending_review": 4}})
        approved_stems = {f"【english/grammar_fill】第 {i} 题题干（approved）" for i in range(4)}

        got = vaf.few_shot("english", "grammar_fill", k=2)
        assert len(got) == 2, f"k=2 应返回 2 条，实际 {len(got)}"
        assert all(set(x) == {"stem", "answer", "explanation"} for x in got), got
        assert {x["stem"] for x in got} <= approved_stems, f"必须优先取 approved，实际 {[x['stem'] for x in got]}"

        got3 = vaf.few_shot("english", "grammar_fill", k=3)
        assert len(got3) == 3 and {x["stem"] for x in got3} <= approved_stems
        assert len(rows) == 8, "前置：库中有 4 approved + 4 pending_review"


def test_few_shot_falls_back_and_respects_k() -> None:
    with Env("few_shot_fallback") as env:
        seed_db(env.root, "english", {"grammar_fill": {"pending_review": 3}})
        got = vaf.few_shot("english", "grammar_fill", k=2)
        assert len(got) == 2 and all(x["answer"] for x in got), f"无 approved 时应回落任意有答案的题，实际 {got}"

        # 只有 1 条 approved 时不得用非 approved 补足（条数 ≤ k）
        seed_db(env.root, "english", {"writing": {"approved": 1, "pending_review": 5}})
        assert len(vaf.few_shot("english", "writing", k=2)) == 1, "只有 1 条 approved → 只返回 1 条"

        # 空答案 / NULL 答案不得作为样例（回落分支要求 answer <> ''）
        conn = sqlite3.connect(str(env.data / "english.sqlite"))
        conn.execute("INSERT INTO questions(question_uid, subject, question_type, stem, answer, status)"
                     " VALUES('uid-empty','english','reading_fill','空答案题干','','pending_review')")
        conn.execute("INSERT INTO questions(question_uid, subject, question_type, stem, answer, status)"
                     " VALUES('uid-null','english','reading_fill','无答案题干',NULL,'pending_review')")
        conn.execute("INSERT INTO questions(question_uid, subject, question_type, stem, answer, status)"
                     " VALUES('uid-ok1','english','reading_fill','有答案题干1','A','pending_review')")
        conn.execute("INSERT INTO questions(question_uid, subject, question_type, stem, answer, status)"
                     " VALUES('uid-ok2','english','reading_fill','有答案题干2','B','pending_review')")
        conn.commit()
        conn.close()
        got = vaf.few_shot("english", "reading_fill", k=5)
        stems = {x["stem"] for x in got}
        assert stems == {"有答案题干1", "有答案题干2"}, f"空/NULL 答案必须被排除，实际 {stems}"

        assert vaf.few_shot("c_hbpu", "programming") == [], "库不存在时返回空列表（不崩）"
        assert vaf.few_shot("english", "no_such_type") == [], "题型不存在时返回空列表"


# ================================================================= ⑦ 矩阵落盘


def test_matrix_shape_and_aca_syllabus_module_count() -> None:
    """build_matrix 形状 + ACA syllabus_modules 与 subjects/aca_llm/syllabus_index.json 模块数一致。"""
    with Env("matrix") as env:
        write_taxonomy(env.root, tax(50))
        seed_db(env.root, "english", {"grammar_fill": {"approved": 1}})
        assert REAL_SYLLABUS.exists(), f"前置：真实考纲索引存在 {REAL_SYLLABUS}"
        (env.root / "subjects" / "aca_llm").mkdir(parents=True, exist_ok=True)
        shutil.copy2(REAL_SYLLABUS, env.root / "subjects" / "aca_llm" / "syllabus_index.json")
        real = json.loads(REAL_SYLLABUS.read_text(encoding="utf-8-sig"))

        m = vaf.build_matrix()
        assert {"generated_at", "basis", "subjects", "syllabus_modules", "syllabus_total_points"} <= set(m), sorted(m)
        assert m["generated_at"], "generated_at 不得为空"
        assert m["basis"] == "approved", f"默认口径应为 approved，实际 {m['basis']}"
        assert list(m["subjects"]) == ["english"], sorted(m["subjects"])
        assert m["subjects"]["english"]["rejected"] == 0, "每科目都要有 rejected 计数"
        assert len(m["syllabus_modules"]) == len(real["modules"]) == 6, \
            f"模块数应与考纲索引一致（{len(real['modules'])}），实际 {len(m['syllabus_modules'])}"
        assert m["syllabus_total_points"] == real["total_points"] == 47, m["syllabus_total_points"]
        for mod in m["syllabus_modules"]:
            assert {"no", "name", "weight", "points"} <= set(mod), mod
        assert sum(x["points"] for x in m["syllabus_modules"]) == 47, m["syllabus_modules"]

        # 落盘（main 的职责）：JSON 可被 utf-8-sig 读回，且与内存对象一致
        vaf.MATRIX.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
        on_disk = json.loads(vaf.MATRIX.read_text(encoding="utf-8-sig"))
        assert {"generated_at", "subjects", "syllabus_modules"} <= set(on_disk)
        assert on_disk["subjects"] == m["subjects"]


def test_matrix_graceful_when_syllabus_missing() -> None:
    """读不到考纲索引时优雅降级（不抛异常）。"""
    with Env("matrix_no_syllabus") as env:
        write_taxonomy(env.root, tax(50))
        seed_db(env.root, "english", {})
        assert not (env.root / "subjects" / "aca_llm" / "syllabus_index.json").exists()

        m = vaf.build_matrix()
        assert m["syllabus_modules"] == [], f"应降级为空列表，实际 {m['syllabus_modules']}"
        assert m["syllabus_total_points"] == 0, m["syllabus_total_points"]
        assert m["subjects"]["english"]["target"] == 50, "降级不得影响 subject 部分"


def test_matrix_skips_missing_subject_dbs() -> None:
    """科目库不存在时跳过（不崩），SUBJECTS 里 4 科只收录实际存在的库。"""
    with Env("matrix_missing_db") as env:
        write_taxonomy(env.root, {"english": {"target_count": 50, "question_types": {}},
                                  "aca_llm": {"target_count": 50, "question_types": {}}})
        seed_db(env.root, "english", {})
        m = vaf.build_matrix()
        assert set(m["subjects"]) == {"english"}, sorted(m["subjects"])
        assert m["subjects"]["english"]["quota"] == {}, "无题型配置时配额为空"


def test_compile() -> None:
    import py_compile

    py_compile.compile(str(VAF_SRC), doraise=True)


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):  # pragma: no cover
            pass

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
