#!/usr/bin/env python
"""阶段 7 · 覆盖矩阵 + 补题生成（**唯一会为"补题"花钱的脚本**）。

用法:
    python scripts/validate_and_fill.py --dry-run                 # 只出矩阵与成本预估（推荐先跑）
    python scripts/validate_and_fill.py --basis approved --max-new 20 --cap-cny 2.0
    python scripts/validate_and_fill.py --review-only             # 只重写 review_queue.md

产出:
    data/coverage_matrix.json     覆盖矩阵（按 --basis 口径统计）
    output/review_queue.md        人工审核队列（**5 列**，供 update_review_status.py 消费）
    logs/cost_ledger.jsonl        真实生成时逐题记账

设计（DESIGN.md 第 12/17 节 + .tools/题库项目-决策记录.md）:
  1. **覆盖口径**由 `--basis` 决定：
     - `any`（早期口径）= approved + pending_review + parsed
     - `approved`（默认，诚实口径）= **只算已通过审核的题**
       实测教训：698 道英语题里 413 道被审出问题而拒绝，按 any 口径缺口为 0，
       按 approved 口径才暴露出真实短缺 —— 覆盖率必须只认真实可用的题。
  2. 考纲条目来源：ACA 用 `subjects/aca_llm/syllabus_index.json` 的知识点（47 条）；
     英语/C 用 `config/taxonomy.json` 的题型。
  3. 补题一律 `status='pending_review'` + `fact_verified=0`，`fact_source` 只允许
     真实来源 URL / 教材章节 / 显式 `AI生成-未验证`（**绝不编造 URL**）。
  4. 生成前查 `generation_cache.sqlite`；每批附上**上一批题干摘要**防重复。
  5. 🔴 **进度守卫**（独立测试抓出的 P0）：连续 2 轮没有新题入库即放弃该题型 ——
     否则模型反复返回同一题干时 uid 命中 `continue`、gap 不减，会永久空转或每轮真实扣费。
  6. 🔴 成本闸门：读 `config/cost_budget.json`；预估超 80% 或超 `--cap-cny` 直接拒绝。
     成本按**每题型各自的 routing 模型**计价（含 pro 题型），并计入高峰 ×2 的最坏情况 ——
     早期按科目取单键且不计高峰，实测低估 3.7 倍。
  7. 少样本蒸馏：**优先从 `data/generation_reference.json` 取该题型的官方真题样例**
     （含考试出处 `exam` 与可信度 `trust`，材料型题连材料整块给出）——
     参考库由 `scripts/build_reference.py` 构建，只收 official_exam/textbook/third_party，
     **绝不含 ai_generated**；参考库不存在或该题型无样例时回退到原来的随机取样（不报错）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from lib.uid import generate_uid  # noqa: E402

DATA = ROOT / "data"
LOGS = ROOT / "logs"
SUBJECTS = ["english", "c_wuhan", "c_hbpu", "aca_llm"]
LEDGER = LOGS / "cost_ledger.jsonl"
MATRIX = DATA / "coverage_matrix.json"
REVIEW_Q = ROOT / "output" / "review_queue.md"
GEN_CACHE = DATA / "generation_cache.sqlite"
ENV_FILE = ROOT / ".env"
REF_NAME = "generation_reference.json"      # 参考库（scripts/build_reference.py 构建）
_REF_CACHE: dict = {}                       # 参考库解析缓存：{(路径, mtime, size): doc}

PRICE = {"deepseek-flash": {"in": 1.0, "out": 4.0}, "deepseek-v4-pro": {"in": 4.5, "out": 13.5}}
EST_IN, EST_OUT = 1600, 900   # 每题生成的大致 token 量（预估用）

REJECT_REASONS = ["答案错误", "来源不可信", "表述歧义", "重复题", "超纲", "格式问题", "其他"]

# 题型 -> routing.json 的 generate 键（**逐题型映射**，不再按科目取单键）
ROUTING_KEY = {
    "english": {"grammar_fill": "english_grammar", "translation_fill": "english_grammar",
                "reading_fill": "english_grammar", "reading_qa": "english_grammar",
                "sentence_build": "english_grammar", "writing": "english_writing"},
    "c_wuhan": {"code_correction": "c_error", "program_fill": "c_error", "programming": "c_program"},
    "c_hbpu": {"code_correction": "c_error", "program_fill": "c_error", "programming": "c_program"},
    "aca_llm": {"single_choice": "aca_choice", "multiple_choice": "aca_choice"},
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(p: Path) -> sqlite3.Connection:
    c = sqlite3.connect(str(p))
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=30000")
    return c


def load_json(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception:  # noqa: BLE001
        return default


def load_env() -> dict[str, str]:
    out: dict[str, str] = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out


# ------------------------------------------------------------------ 覆盖矩阵


def build_matrix(basis: str = "approved") -> dict:
    """basis='any'：approved + pending_review + parsed 都算已覆盖（早期口径）。
    basis='approved'：**只算已通过审核的题** —— 有了真实审核流水线后这才是诚实覆盖率。"""
    tax = load_json(ROOT / "config" / "taxonomy.json", {"subjects": {}})
    syllabus = load_json(ROOT / "subjects" / "aca_llm" / "syllabus_index.json", {"modules": []})
    matrix: dict = {"generated_at": now_iso(), "basis": basis, "subjects": {}, "syllabus_modules": []}

    for subj in SUBJECTS:
        p = DATA / f"{subj}.sqlite"
        if not p.exists():
            continue
        conn = connect(p)
        rows = conn.execute("SELECT question_type, status, count(*) FROM questions GROUP BY 1,2").fetchall()
        conn.close()
        types: dict[str, dict] = {}
        for qtype, status, n in rows:
            t = types.setdefault(qtype, {"approved": 0, "pending_review": 0, "parsed": 0, "rejected": 0, "other": 0})
            if status in t:
                t[status] += n
            else:
                t["other"] += n

        target = (tax["subjects"].get(subj, {}) or {}).get("target_count", 50)
        if basis == "approved":
            def have(t: dict) -> int:
                return t["approved"]
        else:
            def have(t: dict) -> int:
                return t["approved"] + t["pending_review"] + t["parsed"]

        quota: dict[str, int] = {}
        qt_cfg = (tax["subjects"].get(subj, {}) or {}).get("question_types", {})
        total_items = sum((c.get("paper_count") or 0) for c in qt_cfg.values())
        if total_items:
            for qtype, c in qt_cfg.items():
                if c.get("paper_count"):
                    quota[qtype] = max(1, round(target * c["paper_count"] / total_items))
        elif qt_cfg:
            share = max(1, target // len(qt_cfg))
            for qtype in qt_cfg:
                quota[qtype] = share

        gaps = {qtype: max(0, quota.get(qtype, 0) - have(t)) for qtype, t in types.items()}
        for qtype, q in quota.items():
            if qtype not in types:
                types[qtype] = {"approved": 0, "pending_review": 0, "parsed": 0, "rejected": 0, "other": 0}
                gaps[qtype] = q
        matrix["subjects"][subj] = {
            "target": target,
            "covered_any": sum(have(t) for t in types.values()),
            "covered_approved": sum(t["approved"] for t in types.values()),
            "covered_pending": sum(t["pending_review"] + t["parsed"] for t in types.values()),
            "rejected": sum(t["rejected"] for t in types.values()),
            "by_type": types, "quota": quota, "gaps": gaps,
            "gap_total": sum(gaps.values()),
        }

    matrix["syllabus_modules"] = [
        {"no": m.get("no"), "name": m.get("name"), "weight": m.get("weight"),
         "points": len(m.get("points") or [])}
        for m in (syllabus.get("modules") or [])
    ]
    matrix["syllabus_total_points"] = syllabus.get("total_points", 0)
    return matrix


def write_review_queue(limit: int = 200) -> int:
    """生成 5 列审核队列（列名与 update_review_status.py 的契约一致）。"""
    lines = [
        "# 人工审核队列（output/review_queue.md）", "",
        "> 由 `scripts/validate_and_fill.py` 生成。**请勿改动列顺序与前 3 列的内容**：",
        "> `question_uid` / `subject` / `status_snapshot` 是快照校验依据，被改动会导致该行被拒绝更新。",
        "> decision 取值：`通过` / `拒绝` / `修改`；reason 仅在「拒绝」时必填"
        "（" + "/".join(REJECT_REASONS) + "）。",
        "> 留空的 decision 会被跳过（视为尚未审核），不会被计为无效行。",
        "",
        "| question_uid | subject | status_snapshot | decision | reason |",
        "|---|---|---|---|---|",
    ]
    n = 0
    for subj in SUBJECTS:
        p = DATA / f"{subj}.sqlite"
        if not p.exists():
            continue
        conn = connect(p)
        rows = conn.execute(
            "SELECT question_uid, status FROM questions WHERE status IN ('parsed','pending_review') "
            "ORDER BY id LIMIT ?", (limit,)).fetchall()
        conn.close()
        for uid, status in rows:
            lines.append(f"| {uid} | {subj} | {status} |  |  |")
            n += 1
    REVIEW_Q.parent.mkdir(parents=True, exist_ok=True)
    REVIEW_Q.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return n


# ------------------------------------------------------------------ 生成缓存


def _cache_conn() -> sqlite3.Connection:
    c = connect(GEN_CACHE)
    c.executescript(
        "CREATE TABLE IF NOT EXISTS gen_cache (cache_key TEXT PRIMARY KEY, response TEXT, "
        "model TEXT, created_at TEXT, hit_count INTEGER DEFAULT 0);"
    )
    return c


def gen_cache_get(key: str) -> str | None:
    if not GEN_CACHE.exists():
        return None
    c = _cache_conn()
    row = c.execute("SELECT response FROM gen_cache WHERE cache_key=?", (key,)).fetchone()
    if row:
        c.execute("UPDATE gen_cache SET hit_count=hit_count+1 WHERE cache_key=?", (key,))
        c.commit()
    c.close()
    return row[0] if row else None


def gen_cache_put(key: str, response: str, model: str) -> None:
    c = _cache_conn()
    c.execute("INSERT OR REPLACE INTO gen_cache(cache_key,response,model,created_at,hit_count) VALUES(?,?,?,?,0)",
              (key, response, model, now_iso()))
    c.commit()
    c.close()


def load_reference() -> dict:
    """读参考库 `data/generation_reference.json`（不存在 / 读坏都返回 `{}`，绝不抛异常）。

    按 (路径, mtime, size) 缓存，避免每轮生成都重读几百 KB 的 JSON。
    路径用模块级 `DATA` 拼，测试通过 patch `vaf.DATA` 即可让参考库一起隔离。
    """
    p = DATA / REF_NAME
    try:
        st = p.stat()
    except OSError:
        return {}
    key = (str(p), st.st_mtime_ns, st.st_size)
    if _REF_CACHE.get("key") != key:
        try:
            data = json.loads(p.read_text(encoding="utf-8-sig"))
        except Exception:  # noqa: BLE001
            return {}
        _REF_CACHE["key"], _REF_CACHE["data"] = key, data
    return _REF_CACHE.get("data") or {}


def reference_samples(subject: str, qtype: str, k: int = 2) -> list[dict]:
    """参考库里该题型的样例（带 `exam` 出处 / `trust` 可信度 / 材料型题的 `material`+`blanks`）。

    参考库缺失、结构不符、该题型无样例 → 返回空列表（调用方据此回退）。
    """
    ref = load_reference()
    by_type = ((ref.get("subjects") or {}).get(subject) or {}).get("by_type") or {}
    samples = (by_type.get(qtype) or {}).get("samples") or []
    out: list[dict] = []
    for s in samples[:max(0, k)]:
        if not isinstance(s, dict):
            continue
        item = {"stem": s.get("stem") or "", "answer": s.get("answer") or "",
                "explanation": s.get("explanation") or ""}
        for key in ("material", "blanks", "options", "blanks_total", "exam", "trust", "kind"):
            if s.get(key):
                item[key] = s[key]
        out.append(item)
    return out


def few_shot(subject: str, qtype: str, k: int = 2) -> list[dict]:
    """少样本样例：**优先取参考库里的真题/教材题**，没有再回退到随机取样。

    参考库（`data/generation_reference.json`，由 `scripts/build_reference.py` 构建）
    只收 `official_exam`（官方真题，带标准答案与解析）/ `textbook` / `third_party`，
    **绝不含 `ai_generated`**；材料型题连材料整块给出，模型才学得会"整块题"。
    回退分支保持原行为：先取 approved、其次任意有答案的题，条数 ≤ k。
    """
    ref = reference_samples(subject, qtype, k)
    if ref:
        return ref
    p = DATA / f"{subject}.sqlite"
    if not p.exists():
        return []
    c = connect(p)
    rows = c.execute("SELECT stem, answer, explanation FROM questions WHERE question_type=? AND status='approved' "
                     "ORDER BY RANDOM() LIMIT ?", (qtype, k)).fetchall()
    if not rows:
        rows = c.execute("SELECT stem, answer, explanation FROM questions WHERE question_type=? AND answer<>'' "
                         "ORDER BY RANDOM() LIMIT ?", (qtype, k)).fetchall()
    c.close()
    return [{"stem": r[0], "answer": r[1], "explanation": r[2]} for r in rows]


# ------------------------------------------------------------------ 成本


def estimate_cost(subject: str, gaps: dict[str, int], peak: bool = True) -> float:
    """按**每题型各自的 routing 模型**计价；`peak=True` 时按高峰时段 ×2 估最坏情况。

    独立测试抓出的 P1：原实现每科目只取一个 routing 键（english→english_grammar=flash、
    c_*→c_error=flash），而实跑对 writing/programming 用 **pro** → 闸门系统性低估
    （实测 100 题预算 ¥0.52，真实约 ¥1.9，差 3.7 倍）。顺带把高峰 ×2 计入。
    """
    routing = load_json(ROOT / "config" / "routing.json", {})
    gen = routing.get("generate") or {}
    total = 0.0
    for qtype, n in (gaps or {}).items():
        if n <= 0:
            continue
        key = (ROUTING_KEY.get(subject) or {}).get(qtype)
        cfg = gen.get(key) or {}
        model = cfg.get("model", "deepseek-flash")
        p = PRICE.get(model, PRICE["deepseek-flash"])
        total += n * (EST_IN * p["in"] + EST_OUT * p["out"]) / 1_000_000
    return total * (2.0 if peak else 1.0)


GEN_SYS = "你是湖北专升本/阿里云认证的命题老师。产出**可核查、无编造**的题目。只输出 JSON。"

# 参考库样例的可信度 → 提示词里的中文标注（让模型知道这是真题而不是 AI 自产的题）
TRUST_LABEL = {"official_exam": "官方真题", "textbook": "教材/校本题库",
               "third_party": "第三方练习题（未核实）"}


def fmt_examples(examples: list[dict], limit: int = 2) -> str:
    """把少样本样例渲染成提示词文本：**保留出处 `exam` 与可信度 `trust`**；
    材料型题连 `material` + `blanks` 一起给（整块题不拆开）。"""
    if not examples:
        return "[]"
    out = []
    for x in examples[:limit]:
        item = {k: x[k] for k in ("stem", "answer", "explanation") if x.get(k) is not None}
        for k in ("material", "blanks", "options", "blanks_total", "kind", "exam", "trust"):
            if x.get(k):
                item[k] = x[k]
        out.append(item)
    return json.dumps(out, ensure_ascii=False)


def example_header(examples: list[dict]) -> str:
    """样例来源标注：真题要**显式**说明，模型才知道该模仿什么水准。"""
    trusts = {x.get("trust") for x in examples[:2] if x.get("trust")}
    if "official_exam" in trusts:
        head = ("【同题型真题样例（trust=official_exam 官方真题，带 exam 考试出处、标准答案与解析；"
                "请严格模仿其题型格式、难度与解析写法）】")
    elif trusts:
        names = "/".join(TRUST_LABEL.get(t, t) for t in sorted(trusts))
        head = f"【同题型样例（来源：{names}；模仿其格式与解析写法）】"
    else:
        head = "【同题型范例】"
    if any(x.get("material") or x.get("blanks") for x in examples[:2]):
        # 材料型真题在库里是按空分行存的：material 是整块原文、blanks 是这一组全部空。
        # 生成侧没有 material_text 列可写，故必须提醒模型：**自己出题时 stem 要写完整题干**。
        head += ("（材料型整块题：material 为整块原文、blanks 为该组全部空，请勿拆散模仿；"
                 "你自己出题时 stem 必须写完整题干——材料型题请把材料连同各空一起写进 stem，"
                 "答案用 ` | ` 分隔，不得留空 stem）")
    return head


def build_gen_prompt(subject: str, qtype: str, name: str, n: int, avoid: list[str],
                     source_hint: str, examples: list[dict], focus: str = "", batch_no: int = 0) -> str:
    ex = fmt_examples(examples, 2)
    focus_txt = (f"\n【本批聚焦知识点】{focus}（本批题目都要围绕它，覆盖它的不同侧面）") if focus else ""
    avoid_txt = ("\n【已生成过的题干（不要再出类似的）】\n"
                 + "\n".join(f"- {s[:60]}" for s in avoid[-20:])) if avoid else ""
    return (
        f"请为【{subject} · {name}】出 {n} 道题。{focus_txt}\n"
        f"【可依据的考纲/素材】{source_hint}\n"
        f"{example_header(examples)}{ex}\n{avoid_txt}\n\n"
        '严格输出 JSON：{"questions":[{"stem":"题干","answer":"参考答案","explanation":"解析",'
        '"knowledge_point":"考点","difficulty":"易|中|难","fact_claim":"可核查的事实主张",'
        '"fact_source":"来源（真实URL或教材章节，没有就写 AI生成-未验证）"}]}\n'
        "硬约束：参考答案必须唯一确定；不得编造 URL；拿不准的信息写 `未获取`。"
        + (f"\n（本批编号 {batch_no}）" if batch_no else "")
    )


def ensure_columns(conn: sqlite3.Connection) -> None:
    """幂等补齐生成所需的字段（对**老库/测试夹具**也稳健，避免 "no column named trust_level"）。

    `trust_level` 决定"只看真题 / 只看生成题"的开关能否筛到；`group_uid`/`material_text`
    决定材料型题能否整块显示（用户要求整块题不要拆开）。
    """
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(questions)")}
    except sqlite3.Error:
        return
    for name, decl in (("trust_level", "TEXT"), ("group_uid", "TEXT"), ("material_text", "TEXT")):
        if name not in cols:
            conn.execute(f"ALTER TABLE questions ADD COLUMN {name} {decl}")


def reference_kp_pool(subject: str, qtype: str) -> list[str]:
    """该题型的知识点池（用于**每批轮换聚焦**）。

    轮换有两个作用：① 打破"确定性少样本 → prompt 恒定 → 命中缓存 → 空转"的死循环；
    ② 让每批围绕不同知识点出题，**显著提高知识点覆盖率**（而不是反复出同一个点）。
    """
    import sqlite3 as _sq
    out: list[str] = []
    p = DATA / f"{subject}.sqlite"
    if p.exists():
        try:
            c = _sq.connect(f"file:{p}?mode=ro", uri=True)
            out = [r[0] for r in c.execute(
                "SELECT DISTINCT knowledge_point FROM questions WHERE status='approved' "
                "AND question_type=? AND knowledge_point IS NOT NULL AND knowledge_point<>'' LIMIT 60",
                (qtype,))]
            c.close()
        except Exception:  # noqa: BLE001
            out = []
    if not out:
        # 回退：用参考库里该题型的知识点清单
        ref = load_reference()
        node = (((ref.get("subjects") or {}).get(subject) or {}).get("by_type") or {}).get(qtype) or {}
        out = [str(x) for x in (node.get("knowledge_points") or []) if str(x).strip()]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--subject", default="all", choices=SUBJECTS + ["all"])
    ap.add_argument("--basis", default="approved", choices=["any", "approved"],
                    help="覆盖口径：approved=只算已通过审核（默认）；any=含待审/已解析")
    ap.add_argument("--dry-run", action="store_true", help="只出矩阵与成本预估，不生成")
    ap.add_argument("--review-only", action="store_true", help="只重写审核队列")
    ap.add_argument("--batch", type=int, default=5)
    ap.add_argument("--max-new", type=int, default=0, help="本次最多生成多少题（0=不限）")
    ap.add_argument("--cap-cny", type=float, default=2.0)
    ap.add_argument("--force-new", type=int, default=0,
                    help="**无视缺口**，按考纲卷面配额比例额外生成 N 题（用于「用新参考库重新生成一批」）")
    args = ap.parse_args()

    matrix = build_matrix(basis=args.basis)
    MATRIX.write_text(json.dumps(matrix, ensure_ascii=False, indent=2), encoding="utf-8")
    n_queue = write_review_queue()
    print(f"覆盖矩阵 -> {MATRIX}（口径 basis={args.basis}）")
    print(f"审核队列 -> {REVIEW_Q}（{n_queue} 条）")

    print("\n=== 覆盖矩阵 ===")
    for subj, m in matrix["subjects"].items():
        print(f"  {subj:9} 目标 {m['target']:3}  已通过 {m['covered_approved']:4}  "
              f"待审 {m['covered_pending']:4}  已拒 {m['rejected']:4}  缺口 {m['gap_total']:4}")
        for qtype, gap in sorted(m["gaps"].items()):
            if gap:
                print(f"      缺 {qtype:18} {gap:3}（配额 {m['quota'].get(qtype, 0)}）")

    subjects = SUBJECTS if args.subject == "all" else [args.subject]
    gap_total = sum(matrix["subjects"].get(s, {}).get("gap_total", 0) for s in subjects)
    est = sum(estimate_cost(s, matrix["subjects"].get(s, {}).get("gaps", {})) for s in subjects)
    budget = load_json(ROOT / "config" / "cost_budget.json", {"total": 20, "warning": 0.8})
    print(f"\n缺口合计 {gap_total} 题，预估生成成本 ¥{est:.2f}"
          f"（预算总额 ¥{budget.get('total')}，告警线 {budget.get('warning')}）")

    if args.review_only or args.dry_run:
        print("dry-run：未发起任何生成请求。")
        return 0

    if est > args.cap_cny:
        print(f"⚠️ 预估 ¥{est:.2f} 超过本次上限 ¥{args.cap_cny:.2f} —— 停下（请调小范围或提高上限）。")
        return 2
    if est > float(budget.get("total", 20)) * float(budget.get("warning", 0.8)):
        print("⚠️ 预估超过预算告警线（80%）—— 停下等人工确认。")
        return 2

    from openai import OpenAI

    env = load_env()
    if not env.get("DEEPSEEK_API_KEY"):
        print("缺少 DEEPSEEK_API_KEY（题库项目/.env）")
        return 1
    client = OpenAI(api_key=env["DEEPSEEK_API_KEY"],
                    base_url=env.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"), timeout=120)
    routing = load_json(ROOT / "config" / "routing.json", {})
    tax = load_json(ROOT / "config" / "taxonomy.json", {"subjects": {}})
    spent = 0.0
    made = 0
    t0 = time.time()

    for subj in subjects:
        m = matrix["subjects"].get(subj)
        if not m:
            continue
        for qtype, gap in sorted(m["gaps"].items(), key=lambda kv: -kv[1]):
            # --force-new：无视缺口，按卷面配额比例给每个题型分配生成量
            if args.force_new and not gap:
                quota = m.get("quota") or {}
                tot_q = sum(quota.values()) or 1
                gap = max(0, round(args.force_new * (quota.get(qtype, 0) / tot_q)))
            if gap <= 0:
                continue
            name = ((tax["subjects"][subj]["question_types"].get(qtype) or {}).get("name") or qtype)
            gkey = (ROUTING_KEY.get(subj) or {}).get(qtype) or ("aca_choice" if subj == "aca_llm" else "c_error")
            gcfg = (routing.get("generate") or {}).get(gkey) or {}
            model = gcfg.get("model", "deepseek-flash")
            effort = gcfg.get("effort", "low")
            batch = min(args.batch or gcfg.get("batch", 5), gap)
            avoid: list[str] = []
            stall = 0   # 🔴 进度守卫：连续 N 轮没有新题入库就放弃该题型
            batch_no = 0
            kp_pool = reference_kp_pool(subj, qtype)
            while gap > 0 and (args.max_new == 0 or made < args.max_new):
                n = min(batch, gap, (args.max_new - made) if args.max_new else batch)
                if n <= 0:
                    break
                made_before = made
                batch_no += 1
                examples = few_shot(subj, qtype)
                # **每批轮换聚焦一个知识点**：既打破"确定性少样本→prompt 恒定→命中缓存→空转"，
                # 又显著提高知识点覆盖率（而不是反复出同一个点）。
                if kp_pool:
                    focus = kp_pool[(batch_no - 1) % len(kp_pool)]
                else:
                    focus = ""
                src_hint = ("阿里云 ACA 大模型工程师 V2.4 官方课程 11 课时 + 考纲六大模块"
                            if subj == "aca_llm" else
                            ("湖北专升本《大学英语》官方考试大纲 + 历年真题（2020-2026）"
                             if subj == "english" else "湖北专升本 C 语言教材（谭浩强）与各校专业课真题"))
                prompt = build_gen_prompt(subj, qtype, name, n, avoid, src_hint, examples,
                                          focus=focus, batch_no=batch_no)
                ck = hashlib.sha256(f"{subj}|{qtype}|{n}|{focus}|{prompt[:400]}".encode()).hexdigest()[:24]
                cached = gen_cache_get(ck)
                if cached:
                    content = cached
                    usage = {}
                    print(f"  [cache hit] {subj}/{qtype} x{n}")
                else:
                    resp = client.chat.completions.create(
                        model=model,
                        messages=[{"role": "system", "content": GEN_SYS}, {"role": "user", "content": prompt}],
                        reasoning_effort=effort,
                        response_format={"type": "json_object"},
                        temperature=0.7,
                    )
                    content = resp.choices[0].message.content or "{}"
                    usage = resp.usage.model_dump() if getattr(resp, "usage", None) else {}
                    p = PRICE.get(model, PRICE["deepseek-flash"])
                    c = ((usage.get("prompt_tokens", 0) or 0) * p["in"]
                         + (usage.get("completion_tokens", 0) or 0) * p["out"]) / 1_000_000
                    spent += c
                    LOGS.mkdir(parents=True, exist_ok=True)
                    with LEDGER.open("a", encoding="utf-8") as fh:
                        fh.write(json.dumps({"ts": now_iso(), "stage": "stage7.generate", "kind": "llm_call",
                                             "subject": subj, "model": model, "usage": usage,
                                             "cost_cny": round(c, 6), "note": f"{qtype} x{n}"},
                                            ensure_ascii=False) + "\n")
                    gen_cache_put(ck, content, model)
                    print(f"  [gen] {subj}/{qtype} x{n} model={model} 花费 ¥{spent:.3f}")

                try:
                    items = json.loads(content).get("questions") or []
                except Exception:  # noqa: BLE001
                    items = []
                conn = connect(DATA / f"{subj}.sqlite")
                ensure_columns(conn)
                for it in items:
                    stem = (it.get("stem") or "").strip()
                    if len(stem) < 6:
                        continue
                    fs = (it.get("fact_source") or "AI生成-未验证").strip() or "AI生成-未验证"
                    uid = generate_uid(subj, fs, stem)
                    if conn.execute("SELECT 1 FROM questions WHERE question_uid=?", (uid,)).fetchone():
                        continue
                    conn.execute(
                        """INSERT OR IGNORE INTO questions
                           (question_uid, subject, source_type, source_url, source_credit, question_type, stem,
                            options, answer, explanation, knowledge_point, difficulty, status, version,
                            fact_claim, fact_source, fact_verified, trust_level, group_uid, material_text)
                           VALUES (?,?,'generate',?,?,?,?,?,?,?,?,?, 'pending_review', 1, ?, ?, 0,
                                   'ai_generated', ?, ?)""",
                        (uid, subj, "AI生成-未验证", fs, qtype, stem,
                         json.dumps(it.get("options") or [], ensure_ascii=False),
                         it.get("answer") or "", it.get("explanation") or "", it.get("knowledge_point") or "",
                         it.get("difficulty") or "中", it.get("fact_claim") or "", fs,
                         # 必须写 trust_level，否则"只看真题/只看生成题"的开关筛不出它；
                         # 材料型题同时要带 material_text，否则渲染层会丢材料（用户要求整块题不拆开）
                         f"gen-{uid[:10]}", it.get("material") or it.get("material_text") or ""),
                    )
                    made += 1
                    avoid.append(stem)
                    gap -= 1
                conn.commit()
                conn.close()

                # 🔴 进度守卫（独立测试抓出的 P0）：模型若反复返回同一题干，uid 会命中导致
                #    `continue`、gap 不减 —— 无 few_shot 样例时 prompt 恒定 → 缓存命中 →
                #    **永久空转**；有样例时 prompt 每轮变化 → 缓存失效 → **每轮真实扣费**。
                if made == made_before:
                    stall += 1
                    print(f"  [stall] {subj}/{qtype} 本轮无新题入库（第 {stall} 次）")
                    if stall >= 2:
                        print(f"  [stall] 连续 {stall} 轮无新增 → 放弃 {subj}/{qtype}，避免无限空转/持续扣费")
                        break
                else:
                    stall = 0

                if spent > args.cap_cny:
                    print(f"⚠️ 已达本次上限 ¥{args.cap_cny}，停止生成。")
                    break
            if spent > args.cap_cny:
                break

    n_queue = write_review_queue()
    print(f"\n生成 {made} 题（pending_review），实际花费 ¥{spent:.3f}，耗时 {time.time() - t0:.0f}s")
    print(f"审核队列已刷新：{n_queue} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
