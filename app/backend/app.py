#!/usr/bin/env python
"""阶段 8 · Web UI 后端（Flask，**仅 127.0.0.1**，`debug=False`）。

依据:
    - `docs/UI_DESIGN.md`（页面结构 / 色彩 / 交互 / 判分三态+异常态 / 审核页）
    - `DESIGN.md` 第 6 节 schema、第 8 节两套枚举、第 10 节判分机制
    - `.tools/题库项目-决策记录.md` 第 0 节六条 + 第 6 节坑清单（第 15 条即本模块）

关键约定（改代码前先读）:
  1. **只绑 127.0.0.1**，`debug=False`；端口 5000，被占用回退 5001，
     并把**实际端口**写进 `app/port.txt`（验收脚本必须读它，不得硬编码 5000）。
  2. 静态/模板目录**显式**指向 `app/frontend/{static,templates}`；
     前端纯原生 HTML/CSS/JS，**零框架、零 CDN、零外链**。
  3. **两套枚举不混用**：`questions.status`（题目生命周期 6 值）与
     `judge_queue.judge_status`（判分任务 4 值：pending/submitted/synced/**failed**）。
     判分队列页必须呈现四态，`failed` 可**手动重投**（`POST /api/requeue`）。
  4. 写连接：`PRAGMA journal_mode=WAL` + `busy_timeout=30000`；
     **只读接口一律走 `mode=ro` URI 且不设 WAL**（改 journal_mode 会写库头），
     因此 GET 系列接口**零写盘**。
  5. 拒绝原因只写 `logs/review_rejects.jsonl`，
     ⚠️ **绝不写 `config/distractors.json`**（那里只存干扰项）。
  6. `.env` 只读不打印：页面/日志里**不出现任何 key**（只显示「已配置 / 未配置」）。
  7. `POST /api/sync` 默认 `--mock`（不联网、零花费）；要跑真实判分必须显式
     `mock=false` + `confirm_paid=true`（付费闸门，见决策记录第 5 节）。
  8. **解释（explanation）只在真题上显示**：用户要求「只在真题显示解释，全部都给太贵」。
     接口（`/api/questions`、`/api/reveal`）**照常返回 `explanation` 正文**（`reveal=1` 时），
     只额外给 `show_explanation` / `explanation_source` / `explanation_hidden_reason` 三个字段，
     由前端按 `show_explanation` 决定是否渲染。唯一判定入口 `explanation_policy()`；
     要临时放开非真题的解释，加 query `explain_policy=all`。**纯展示策略，不改任何题库数据。**
  9. 模块级 `ROOT / DATA_DIR / LOGS_DIR / OUTPUT_DIR / SYNC_SCRIPT` 都是
     **测试可 monkeypatch 的全局**，函数内按调用时取值（不要在导入期算派生路径）。

用法:
    python app/backend/app.py                 # 自动选端口（5000 → 5001）并启动
    python app/backend/app.py --check-port    # 只做端口选择 + 写 port.txt，不启动服务
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import socket
import sqlite3
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, render_template, request

# ============================================================== 路径（测试可覆盖）

ROOT = Path(__file__).resolve().parent.parent.parent  # 题库项目/
APP_DIR = ROOT / "app"
FRONTEND_DIR = APP_DIR / "frontend"
TEMPLATE_DIR = FRONTEND_DIR / "templates"
STATIC_DIR = FRONTEND_DIR / "static"
CONFIG_DIR = ROOT / "config"
SCRIPTS_DIR = ROOT / "scripts"
DATA_DIR = ROOT / "data"          # ← 测试 monkeypatch 这里
LOGS_DIR = ROOT / "logs"          # ← 测试 monkeypatch 这里
OUTPUT_DIR = ROOT / "output"      # ← 测试 monkeypatch 这里
PORT_FILE = APP_DIR / "port.txt"
SYNC_SCRIPT = SCRIPTS_DIR / "sync_outbox.py"  # ← 测试 monkeypatch 这里

# ============================================================== 常量

SUBJECTS = ("english", "c_wuhan", "c_hbpu", "aca_llm")
SUBJECT_LABELS = {
    "english": "英语（湖北专升本）",
    "c_wuhan": "C 语言（武汉商学院）",
    "c_hbpu": "C 语言（湖北理工学院）",
    "aca_llm": "阿里云 ACA 大模型工程师",
}
# `judge_queue.judge_status` 四值（与 DESIGN.md 第 8 节严格一致）
JUDGE_STATUSES = ("pending", "submitted", "synced", "failed")
# `questions.status` 六值（与 DESIGN.md 第 8 节严格一致）
QUESTION_STATUSES = ("raw", "parsed", "pending_review", "approved", "rejected", "archived")
OBJECTIVE_TYPES = ("single_choice", "multiple_choice")
# ⚠️ 2026-10-24 修正：只认这两个题型会让「有选项的题」退化成文本框——
#    实测英语库里有选项、却被判成主观题的题：phonetics 40、translation_choice 20、
#    cloze 92、reading_qa 187、grammar_fill 10。用户报「音标题压根没有单词让我看」就是这条。
#    现在改成**以数据为准**：有 ≥2 个选项 且 参考答案能解析成选项字母 → 就算客观题；
#    下面这个元组只用来**排除**明显是主观题的题型。
SUBJECTIVE_ONLY_TYPES = ("writing", "translation", "sentence_build", "paragraph", "essay",
                         "code_correction", "programming", "program_fill")


def is_objective(question_type: str | None, options: list, answer) -> bool:
    """是否按「可点选项的客观题」渲染（数据驱动，不看题型白名单）。"""
    if (question_type or "") in SUBJECTIVE_ONLY_TYPES:
        return False
    if len(options or []) < 2:
        return False
    return bool(answer_keys(answer))
# 规则判分写入 `judge_prompt_version` 的标记（与 LLM 判分的 prompt 版本区分开）
LOCAL_PROMPT_VERSION = "local_rule_v1"
# 拒绝原因下拉 7 项（权威列表来自 scripts/update_review_status.py）
REJECT_REASONS = ("答案错误", "来源不可信", "表述歧义", "重复题", "超纲", "格式问题", "其他")
DECISION_ALIASES = {
    "通过": "approve", "批准": "approve", "同意": "approve",
    "approve": "approve", "approved": "approve", "pass": "approve", "ok": "approve",
    "拒绝": "reject", "驳回": "reject",
    "reject": "reject", "rejected": "reject", "deny": "reject",
    "修改": "edit", "编辑": "edit", "待改": "edit",
    "edit": "edit", "edited": "edit", "revise": "edit",
}
DECISION_TO_STATUS = {"approve": "approved", "reject": "rejected", "edit": "pending_review"}

MAX_PAGE_LIMIT = 500
DEFAULT_LIMIT = 100

# 可选的既有口径模块（scripts/ 已实现，Web 侧复用以免判定分叉；缺失时走本地兜底）
progress_lib = None
review_lib = None
rule_judge = None
kb_lib = None      # scripts/kb.py：按科目隔离的知识库（/kb 页面与检索接口复用）
try:  # pragma: no cover - 导入成功是常态
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    import update_daily_progress as progress_lib  # type: ignore  # noqa: E402
    import update_review_status as review_lib  # type: ignore  # noqa: E402
    import judge_local as rule_judge  # type: ignore  # noqa: E402
    import kb as kb_lib  # type: ignore  # noqa: E402
    if hasattr(review_lib, "REJECT_REASONS"):
        REJECT_REASONS = tuple(review_lib.REJECT_REASONS)
    if hasattr(review_lib, "DECISION_ALIASES"):
        DECISION_ALIASES = dict(review_lib.DECISION_ALIASES)
    if hasattr(review_lib, "DECISION_TO_STATUS"):
        DECISION_TO_STATUS = dict(review_lib.DECISION_TO_STATUS)
except Exception:  # noqa: BLE001 - 脚本目录缺失时仍要能起 Web
    progress_lib = None
    review_lib = None
    rule_judge = None
    kb_lib = None

# ============================================================== Flask

app = Flask(__name__, static_folder=str(STATIC_DIR), template_folder=str(TEMPLATE_DIR))
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0  # 开发期不吃静态缓存
try:  # Flask >= 2.2：中文不转义
    app.json.ensure_ascii = False
except Exception:  # noqa: BLE001  # pragma: no cover
    app.config["JSON_AS_ASCII"] = False


# ============================================================== 通用小工具


def now_iso() -> str:
    """UTC ISO-8601（与 scripts/ 各模块写法一致）。"""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def today_local() -> str:
    if progress_lib is not None:
        return progress_lib.today_local()
    return datetime.now().strftime("%Y-%m-%d")


def local_date(value) -> str | None:
    if progress_lib is not None:
        return progress_lib.local_date(value)
    return _fallback_local_date(value)


def parse_ts(value) -> datetime | None:
    if progress_lib is not None:
        return progress_lib.parse_ts(value)
    return _fallback_parse_ts(value)


def _fallback_parse_ts(value):
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(s, fmt)
                break
            except ValueError:
                continue
        else:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.now().astimezone().tzinfo)
    return dt.astimezone(timezone.utc)


def _fallback_local_date(value):
    dt = _fallback_parse_ts(value)
    return dt.astimezone().strftime("%Y-%m-%d") if dt else None


def judge_full_score(subject: str, question_type: str | None = None) -> float:
    """该题型的满分：从 `config/taxonomy.json` 的 `per_item` 读，读不到回落 1.0。

    与 `scripts/sync_outbox.py:full_score_for()` 保持同一口径（英语语法填空 2 / 翻译填空 3 /
    写作 10 / ACA 2），否则页面显示的"得分 X / 满分 Y"会和判分器的对错判定不一致。
    """
    try:
        data = json.loads((CONFIG_DIR / "taxonomy.json").read_text(encoding="utf-8"))
        cfg = ((data.get("subjects") or {}).get(subject) or {}).get("question_types") or {}
        item = cfg.get(question_type or "") or {}
        for k in ("per_item", "score_correct", "score_all_correct"):
            v = item.get(k)
            if isinstance(v, (int, float)) and v > 0:
                return float(v)
    except Exception:  # noqa: BLE001
        pass
    return 1.0


def judge_correct(subject: str, judge_score, question_type: str | None = None) -> bool:
    """对错判定唯一入口：复用 `scripts/update_daily_progress.judge_correct`。"""
    if progress_lib is not None:
        try:
            return bool(progress_lib.judge_correct(subject, judge_score, question_type=question_type))
        except Exception:  # noqa: BLE001
            pass
    if judge_score is None:
        return False
    try:
        score = float(judge_score)
    except (TypeError, ValueError):
        return False
    if subject == "aca_llm":
        return score >= 2.0 - 1e-9
    return score >= 0.8 - 1e-9


def local_verdict(subject: str, question_uid: str, user_answer: str) -> dict | None:
    """**规则判分**（需求 2）：读该题 answer/type/stem → `judge_local.judge_local`。

    返回：
      - `None` → 规则判不了（题目不在库 / 模块缺失 / 答案形态不适合本地判分）；
      - `{"gradeable": False, ...}` → 模块明确说"交给 AI"（含原因）；
      - `{"gradeable": True, "score":…, "full_score":…, "correct":…}` → 就地判完，不花钱。
    """
    if rule_judge is None or subject not in SUBJECTS:
        return None
    conn = open_db(subject)
    if conn is None:
        return None
    try:
        if not table_exists(conn, "questions"):
            return None
        row = conn.execute("SELECT answer, question_type, stem FROM questions WHERE question_uid=?",
                           (question_uid,)).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    answer, qtype, stem = row["answer"], row["question_type"], row["stem"]
    try:
        verdict = rule_judge.judge_local(subject, qtype, answer, user_answer, stem=stem)
    except Exception as exc:  # noqa: BLE001 - 规则判分绝不拖垮提交路径
        return {"gradeable": False, "reason": f"规则判分异常: {type(exc).__name__}: {exc}",
                "question_type": qtype or "", "model": "local_rule"}
    out = verdict.to_dict()
    out["question_type"] = qtype or ""
    out["type_name"] = type_label(qtype)
    out["correct"] = bool(out.get("correct")) if out.get("gradeable") else None
    return out


def mark_attempt_unanswered(attempt_id: str, reason: str = "未作答，按答错计 0 分") -> None:
    """把「没作答」的 attempt **直接判 0 分**，不让它留在 AI 判分队列里。

    为什么：套卷交卷是整卷提交，用户跳过/没做完的题也会写一条 attempt。
    这些题如果留在 `judge_queue(pending)`，之后跑真实判分会给**空白答案**按题付费
    （实测一份 82 题的 ACA 卷，有 81 条是这样进队列的）。
    客观题有标准答案，空作答等价于答错，不需要任何模型参与。
    """
    conn = open_db("attempts", write=True)
    if conn is None:
        return
    try:
        conn.execute("UPDATE attempts SET judge_score=0, judge_model='unanswered', judge_reason=?, "
                     "synced=1 WHERE attempt_id=?", (reason, attempt_id))
        conn.execute("UPDATE judge_queue SET judge_score=0, judge_model='unanswered', judge_reason=?, "
                     "judge_status='synced' WHERE attempt_id=?", (reason, attempt_id))
        conn.commit()
    except sqlite3.Error:
        conn.rollback()
    finally:
        conn.close()


def apply_local_verdict(subject: str, question_uid: str, attempt_id: str, user_answer: str,
                        source_type: str | None = None) -> dict | None:
    """规则判分 + **就地落库**（attempts / judge_queue / review_log），并重算当日进度。

    🔴 契约（见 sync_outbox.py docstring）：
      - `wrong_book` **绝不在这里写** —— 那是 `sm2_scheduler` 的独占职责；
      - 只写 `review_log(question_uid, reviewed_at, result)`（`result ∈ {correct, wrong}`）；
      - `daily_progress` 由 `update_daily_progress.py` 按 attempts **全量重算**，
        这里只是"提交后立刻重算一次"，保证首页今日进度即时更新（需求 10）。

    `source_type`：调用方可以先自己写 attempt（例如套卷交卷用 `'paper'`），
    这里只在传了值时把 `source_type` 一并更新（不传就不动它）。
    """
    verdict = local_verdict(subject, question_uid, user_answer)
    if not verdict or not verdict.get("gradeable"):
        return verdict
    score = float(verdict.get("score") or 0.0)
    full = float(verdict.get("full_score") or 0.0)
    reason = str(verdict.get("reason") or "")[:500]
    model = str(verdict.get("model") or "local_rule")
    result = "correct" if verdict.get("correct") else "wrong"
    ts = now_iso()
    conn = open_db("attempts", write=True)
    if conn is None:
        return verdict
    try:
        conn.execute("UPDATE attempts SET judge_score=?, judge_model=?, judge_reason=?, "
                     "judge_prompt_version=?, synced=1 WHERE attempt_id=?",
                     (score, model, reason, LOCAL_PROMPT_VERSION, attempt_id))
        conn.execute("UPDATE judge_queue SET judge_score=?, judge_model=?, judge_reason=?, "
                     "judge_status='synced', submitted_at=COALESCE(submitted_at, ?) WHERE attempt_id=?",
                     (score, model, reason, ts, attempt_id))
        if source_type:
            conn.execute("UPDATE attempts SET source_type=? WHERE attempt_id=?", (source_type, attempt_id))
            conn.execute("UPDATE judge_queue SET source_type=? WHERE attempt_id=?", (source_type, attempt_id))
        conn.commit()
    except sqlite3.Error as exc:
        conn.rollback()
        verdict["warning"] = f"规则判分回写失败: {exc}"
        return verdict
    finally:
        conn.close()

    sconn = open_db(subject, write=True)
    if sconn is not None:
        try:
            if table_exists(sconn, "review_log"):
                sconn.execute("INSERT INTO review_log(question_uid, reviewed_at, result) VALUES(?,?,?)",
                              (question_uid, ts, result))
                sconn.commit()
        except sqlite3.Error as exc:
            verdict["warning"] = f"review_log 写入失败: {exc}"
        finally:
            sconn.close()

    verdict["judge_score"] = score
    verdict["judge_reason"] = reason
    verdict["judge_model"] = model
    verdict["progress"] = recompute_today_progress()
    return verdict


def recompute_today_progress() -> dict | None:
    """重算各科目**当日** `daily_progress`（幂等；失败只返回错误，不影响判分结果）。

    为什么需要：`daily_progress` 只由 `scripts/update_daily_progress.py` 全量重算，
    而以前那条链路要等 LLM 判分（`sync_outbox`）→ 没 key 时首页「今日进度」永远不动（需求 10）。
    规则判分就地出分后，**立刻**用**同一份脚本函数**重算一次：
      `fetch_attempts` → `read_question_meta` → `aggregate_rows` → `ensure/upsert_progress`。
    ⚠️ 不另写一套聚合口径（避免与 CLI 分叉），也不碰 `questions` 表。
    """
    if progress_lib is None:
        return None
    try:
        date_str = today_local()
    except Exception:  # noqa: BLE001
        return None
    out: dict = {}
    try:
        aconn = progress_lib.connect(db_path("attempts"), readonly=False)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"打开 attempts 库失败: {exc}"}
    try:
        if not progress_lib.table_exists(aconn, "attempts"):
            return None
        rows = progress_lib.fetch_attempts(aconn, date_str)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"读取 attempts 失败: {exc}"}
    finally:
        aconn.close()

    by_subject: dict[str, list[dict]] = {}
    for rec in rows:
        subj = str(rec.get("subject") or "").strip()
        if subj in SUBJECTS:
            by_subject.setdefault(subj, []).append(rec)
    aca = progress_lib.load_aca_rules()
    taxonomy = progress_lib.load_json(CONFIG_DIR / "taxonomy.json")

    for subj, subj_rows in by_subject.items():
        conn = open_db(subj, write=True)
        if conn is None:
            continue
        try:
            progress_lib.ensure_daily_progress(conn)
            qmeta = progress_lib.read_question_meta(conn)
            agg = progress_lib.aggregate_rows(subj, subj_rows, question_meta=qmeta,
                                              taxonomy=taxonomy, aca=aca)
            progress_lib.upsert_progress(conn, date_str, agg)
            conn.commit()
            out[subj] = {"total_done": agg["total_done"], "correct_count": agg["correct_count"],
                         "wrong_count": agg["wrong_count"], "unjudged": agg["unjudged"]}
        except Exception as exc:  # noqa: BLE001
            out[subj] = f"error: {type(exc).__name__}: {exc}"
        finally:
            conn.close()
    out["date"] = date_str
    return out


def normalize_decision(raw: str) -> str | None:
    key = "".join(ch for ch in str(raw or "").strip().lower() if not ch.isspace())
    key = key.replace("（", "").replace("）", "")
    return DECISION_ALIASES.get(key)


def match_reject_reason(raw: str) -> str | None:
    """命中规范原因即返回（`其他：xxx` 这类带补充说明也接受）。"""
    s = str(raw or "").strip().strip("`").strip()
    if not s:
        return None
    for reason in REJECT_REASONS:
        if s == reason:
            return reason
    for reason in REJECT_REASONS:
        if s.startswith(reason) and len(s) > len(reason) and s[len(reason)] in "：:，,、/ -—（(；;":
            return reason
    return None


def json_body() -> dict:
    data = request.get_json(silent=True)
    if isinstance(data, dict):
        return data
    if request.form:
        return request.form.to_dict()
    return {}


def param(name: str, default=None):
    """query 优先，其次 body。"""
    if name in request.args:
        return request.args.get(name)
    return json_body().get(name, default)


def as_bool(value, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "y", "on", "是")


def as_int(value, default=None, lo=None, hi=None):
    try:
        out = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    if lo is not None:
        out = max(lo, out)
    if hi is not None:
        out = min(hi, out)
    return out


# ============================================================== 数据库


def db_path(name: str) -> Path:
    """`name` 可为科目名或 `attempts`。"""
    return DATA_DIR / f"{name}.sqlite"


def open_db(name: str, write: bool = False):
    """打开库；不存在返回 None。

    write=True → 普通连接 + `journal_mode=WAL`；
    write=False → **只读** `mode=ro` URI，且**不设 WAL**（改 journal_mode 会写库头，
    违反「只读接口不写库」）。`busy_timeout=30000` 两类连接都设。
    """
    path = db_path(name)
    if not path.exists():
        return None
    if write:
        conn = sqlite3.connect(str(path))
        conn.execute("PRAGMA journal_mode=WAL")
    else:
        conn = None
        try:
            conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
            conn.execute("SELECT count(*) FROM sqlite_master")  # 触发实际打开
        except sqlite3.Error:
            if conn is not None:
                conn.close()
            conn = sqlite3.connect(str(path))  # 兜底：仍不执行任何写语句
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def table_exists(conn, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def rows_to_dicts(rows) -> list[dict]:
    return [dict(r) for r in rows]


def iter_subjects(subject: str | None):
    """`subject` 为空 → 4 个科目依次；非法科目 → 空列表（调用方返回 400）。"""
    if not subject:
        return list(SUBJECTS)
    return [subject] if subject in SUBJECTS else []


def subject_labels() -> dict:
    """优先用 `config/taxonomy.json` 的名称，缺失回落内置标签。"""
    labels = dict(SUBJECT_LABELS)
    path = CONFIG_DIR / "taxonomy.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        for key, meta in (data.get("subjects") or {}).items():
            name = (meta or {}).get("name")
            if name:
                labels[key] = name
    except Exception:  # noqa: BLE001
        pass
    return labels


def parse_options(raw) -> list[dict]:
    """`questions.options` 容错解析 → `[{"key": "A", "text": "..."}]`。

    支持 JSON 数组（字符串 / 对象）、JSON 对象 `{"A": "..."}`，以及普通文本兜底。
    """
    if raw is None:
        return []
    data = raw
    if isinstance(raw, str):
        text = raw.strip()
        if not text or text in ("{}", "[]", "null"):
            return []
        try:
            data = json.loads(text)
        except Exception:  # noqa: BLE001
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
            return [{"key": _letter(i), "text": ln} for i, ln in enumerate(lines)]
    if isinstance(data, dict):
        items = list(data.items())
        return [{"key": str(k).strip() or _letter(i), "text": _opt_text(v)} for i, (k, v) in enumerate(items)]
    if isinstance(data, list):
        out = []
        for i, item in enumerate(data):
            if isinstance(item, dict):
                key = item.get("key") or item.get("label") or item.get("option") or _letter(i)
                text = item.get("text") or item.get("value") or item.get("content") or ""
                out.append({"key": str(key).strip(), "text": str(text)})
            else:
                out.append({"key": _letter(i), "text": str(item)})
        return out
    return []


def runtime_options(rec: dict) -> list[dict]:
    """运行时选项：先看 `questions.options`，为空时**从题干里解析内嵌选项**。

    为什么需要：全库 7,961 题里 `options` **一条都没有值**（采集时选项写进了 `stem`，
    形如 `"...\\nA. xxx\\nB. yyy"`）。不解析的话，刷题页会把客观题渲染成文本框，
    而且 `answer_keys` 永远为空 → 客观题的本地规则判分也拿不到字母。
    解析器是 `scripts/judge_local.py:options_from_stem()`（**与判分共用同一套**，
    带"长度/题面词"闸门，宁可返回空也不给出错误选项）。
    """
    opts = parse_options(rec.get("options"))
    if len(opts) >= 2:
        return opts
    if rule_judge is None:
        return opts
    try:
        embedded = rule_judge.options_from_stem(rec.get("stem") or "")
    except Exception:  # noqa: BLE001
        return opts
    if len(embedded) >= 2:
        return [{"key": k, "text": v} for k, v in sorted(embedded.items())]
    return opts


def _opt_text(value) -> str:
    if isinstance(value, dict):
        return str(value.get("text") or value.get("value") or value.get("content") or "")
    return str(value)


def _letter(i: int) -> str:
    return chr(ord("A") + i) if 0 <= i < 26 else str(i + 1)


_PURE_LETTERS_RE = re.compile(r"^[A-Ha-h]{1,8}$")
_LETTER_PREFIX_RE = re.compile(r"^\s*([A-Ha-h])\s*[.、)．:：]")
_SEP_LETTERS_RE = re.compile(r"^[A-Ha-h](?:\s*[、,，/|]\s*[A-Ha-h])+$")


def answer_keys(answer, stem: str | None = None) -> str:
    """答案 → 归一化选项字母集合。

    ⚠️ 2026-10-24 修正：原来是把答案里**所有 A–H 字母**都抠出来，于是
       `"D. great"` 被抠成 `ADEG`（great 里的 r/e/a 全当选项字母），
       音标题因此被判成「多选题」、判分也对不上。
    现在只认三种形态：纯字母（`ABD`/`A、B、D`）、「字母+分隔符」（`D. great`→`D`）、
    以及和题干里某个选项原文完全一致的情况（交给 judge_local 判定）。
    """
    text = json.dumps(answer, ensure_ascii=False) if isinstance(answer, (list, tuple)) else str(answer or "")
    text = text.strip()
    if not text:
        return ""

    # ① 优先用判分模块的口径（与判分共用一个事实源）
    if rule_judge is not None:
        try:
            letters = rule_judge.answer_option_letters(answer, stem)
        except Exception:  # noqa: BLE001
            letters = ""
        if letters:
            return "".join(sorted(set(letters.upper())))

    # ② 兜底：纯字母 / 逗号分隔字母
    compact = re.sub(r"[\s、,，/|]+", "", text)
    if _PURE_LETTERS_RE.match(compact):
        return "".join(sorted(set(compact.upper())))
    if _SEP_LETTERS_RE.match(text):
        return "".join(sorted({ch for ch in text.upper() if "A" <= ch <= "H"}))

    # ③ 「字母 + 选项原文」→ 只取那个字母
    m = _LETTER_PREFIX_RE.match(text)
    if m and len(text) < 200:
        return m.group(1).upper()

    # ④ 其余（整段作文/代码/论述）→ 不是选项答案
    return ""


# ============================================================== 领域查询


def queue_counters(conn) -> dict:
    out = {s: 0 for s in JUDGE_STATUSES}
    if conn is None or not table_exists(conn, "judge_queue"):
        return out
    for row in conn.execute("SELECT judge_status, count(*) FROM judge_queue GROUP BY judge_status"):
        out[str(row[0])] = int(row[1])
    return out


def current_queue_counters() -> dict:
    """四态计数（自己开关连接，只读）。"""
    conn = open_db("attempts")
    if conn is None:
        return {s: 0 for s in JUDGE_STATUSES}
    try:
        return queue_counters(conn)
    finally:
        conn.close()


def queue_rows(status: str | None = None, limit: int = 200) -> list[dict]:
    """判分队列明细。`judge_queue` 里只存 `question_uid`，这里**补出题干/选项/答案**。

    为什么补：用户报「判分队列里只有解析、看不见选项，不知道自己错在哪」。
    队列本身不存题面（那是科目库的事），所以按 subject 打开对应库查一次，并按
    subject 缓存连接（200 条记录不会开 200 次库）。
    """
    conn = open_db("attempts")
    if conn is None:
        return []
    try:
        sql = "SELECT * FROM judge_queue"
        params: list = []
        if status in JUDGE_STATUSES:
            sql += " WHERE judge_status=?"
            params.append(status)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        out = rows_to_dicts(conn.execute(sql, params))
    finally:
        conn.close()

    qcache: dict[str, dict] = {}
    for rec in out:
        subj = rec.get("subject") or ""
        if subj not in qcache:
            qcache[subj] = {}
            qconn = open_db(subj)
            if qconn is not None:
                try:
                    if table_exists(qconn, "questions"):
                        for row in qconn.execute(
                                "SELECT question_uid, question_type, COALESCE(stem,'') AS stem, "
                                "COALESCE(options,'') AS options, COALESCE(answer,'') AS answer, "
                                "COALESCE(explanation,'') AS explanation, "
                                "COALESCE(knowledge_point,'') AS knowledge_point "
                                "FROM questions"):
                            qcache[subj][row["question_uid"]] = dict(row)
                except sqlite3.Error:
                    pass
                finally:
                    qconn.close()
        q = qcache[subj].get(rec.get("question_uid"))
        if not q:
            rec.update({"stem": "", "options_parsed": [], "answer_keys": "",
                        "answer_text": "", "type_name": ""})
            continue
        rec["stem"] = q["stem"]
        rec["question_type"] = q["question_type"]
        rec["type_name"] = type_label(q["question_type"])
        rec["explanation"] = q["explanation"]
        rec["knowledge_point"] = q["knowledge_point"]
        rec["options_parsed"] = runtime_options(q)
        rec["answer_keys"] = answer_keys(q["answer"], q["stem"])
        rec["answer_text"] = q["answer"]
        rec["objective"] = is_objective(q["question_type"], rec["options_parsed"], q["answer"])
    return out


def due_review_rows(subject: str | None = None, limit: int = 50) -> list[dict]:
    """`wrong_book.next_review_at <= now` 的到期复习题（含题干）。"""
    now = datetime.now(timezone.utc)
    labels = subject_labels()
    out: list[dict] = []
    for subj in iter_subjects(subject):
        conn = open_db(subj)
        if conn is None:
            continue
        try:
            if not table_exists(conn, "wrong_book"):
                continue
            for row in conn.execute(
                "SELECT question_uid, wrong_count, correct_streak, last_wrong_at, next_review_at, mastery "
                "FROM wrong_book ORDER BY next_review_at"
            ):
                rec = dict(row)
                due_at = parse_ts(rec.get("next_review_at"))
                if due_at is None or due_at > now:
                    continue
                rec["subject"] = subj
                rec["subject_label"] = labels.get(subj, subj)
                stem = conn.execute(
                    "SELECT stem, question_type, knowledge_point FROM questions WHERE question_uid=?",
                    (rec["question_uid"],),
                ).fetchone()
                rec["stem"] = (stem["stem"] if stem else "") or ""
                rec["question_type"] = (stem["question_type"] if stem else "") or ""
                rec["knowledge_point"] = (stem["knowledge_point"] if stem else "") or ""
                out.append(rec)
        finally:
            conn.close()
    out.sort(key=lambda r: str(r.get("next_review_at") or ""))
    return out[:limit]


def subject_cards() -> list[dict]:
    labels = subject_labels()
    cards = []
    for subj in SUBJECTS:
        conn = open_db(subj)
        total = approved = pending = raw = 0
        if conn is not None:
            try:
                if table_exists(conn, "questions"):
                    for row in conn.execute("SELECT status, count(*) FROM questions GROUP BY status"):
                        n = int(row[1])
                        total += n
                        if row[0] == "approved":
                            approved = n
                        elif row[0] == "pending_review":
                            pending = n
                        elif row[0] == "raw":
                            raw = n
            finally:
                conn.close()
        cards.append({
            "key": subj, "name": labels.get(subj, subj), "db_exists": conn is not None,
            "total": total, "approved": approved, "pending_review": pending, "raw": raw,
            "target": _subject_target(subj), "due": len(due_review_rows(subj)),
        })
    return cards


def question_types_map() -> dict:
    """`config/taxonomy.json` → `{科目: [{key, name}]}`（题型下拉用）。"""
    out: dict = {}
    try:
        data = json.loads((CONFIG_DIR / "taxonomy.json").read_text(encoding="utf-8"))
        for subj, meta in (data.get("subjects") or {}).items():
            out[subj] = [{"key": key, "name": (val or {}).get("name") or key}
                         for key, val in ((meta or {}).get("question_types") or {}).items()]
    except Exception:  # noqa: BLE001
        out = {}
    if not out:
        out = {subj: [{"key": "single_choice", "name": "单选"},
                      {"key": "multiple_choice", "name": "多选"}] for subj in SUBJECTS}
    return out


def display_meta() -> dict:
    """`config/display.json` → 题型中文名 + 「该题型怎么做」说明 + 科目中文名。

    这是 Web UI 与单文件 HTML 题库**共用**的展示数据源（避免两处各写一份、改一处漏一处）。
    """
    try:
        data = json.loads((CONFIG_DIR / "display.json").read_text(encoding="utf-8-sig"))
        if isinstance(data, dict):
            data.setdefault("types", {})
            data.setdefault("subject_names", {})
            return data
    except Exception:  # noqa: BLE001
        pass
    return {"types": {}, "subject_names": {}}


def type_label(qtype: str) -> str:
    """题型 key → 中文名（查不到就原样返回）。"""
    meta = (display_meta().get("types") or {}).get(qtype or "") or {}
    return meta.get("name") or qtype or "未标题型"


# ============================================================== 解释显示策略（只在真题显示）

# 「算真题」的两个 `trust_level` + 它们的中文短名。
# ⚠️ 只有这两项是**契约固定值**（前端按它显示来源徽标），其余取值的中文名
#    一律查 `config/display.json:trust_levels`（见 `explanation_policy()`），不在这里维护第二套映射。
REAL_TRUST_LEVELS = {"official_exam": "官方真题", "textbook": "教材/校考真题"}
UNKNOWN_TRUST_LABEL = "来源未标注"
HIDDEN_EXPLANATION_REASON = "非真题：解释可能不可靠，已隐藏"


def explanation_policy(trust_level: str | None, trust_labels: dict | None = None) -> dict:
    """解释显示策略：**只在"真题/教材真题"上显示解释**（唯一判定入口，页面/接口都走它）。

    用户原话：「有一些题有解释这点做得很好，我希望其他也有（全部都有的话花费太高了，
    所以只在真题显示解释，一定确保解释的正确）」→ 非真题的解释**不展示**，避免让人误信。

    口径（必须一致，改这里就够，别在路由里另写一份）:
      - `official_exam` → `{"show": True, "source_label": "官方真题", "reason": ""}`
      - `textbook`      → `{"show": True, "source_label": "教材/校考真题", "reason": ""}`
      - 其余（`third_party` / `ai_generated` / `acp` / 空 / NULL / 未知取值）→
        `{"show": False, "source_label": <中文名>, "reason": "非真题：解释可能不可靠，已隐藏"}`
        其中 `<中文名>` 优先取 `display.json:trust_levels` 的映射（`trust_labels` 可传入
        省一次读盘），查不到就原样返回该取值，空 / NULL 返回 `来源未标注`。

    ⚠️ 这只是**展示策略**：接口仍然照常返回 `explanation` 正文，是否渲染由前端按 `show` 决定。
    """
    raw = str(trust_level or "").strip()
    labels = trust_labels if trust_labels else (display_meta().get("trust_levels") or {})
    if raw in REAL_TRUST_LEVELS:
        return {"show": True, "source_label": REAL_TRUST_LEVELS[raw], "reason": ""}
    return {"show": False,
            "source_label": labels.get(raw) or raw or UNKNOWN_TRUST_LABEL,
            "reason": HIDDEN_EXPLANATION_REASON}


def explanation_fields(trust_level: str | None, trust_labels: dict | None = None,
                       show_all: bool = False) -> dict:
    """`explanation_policy()` → 接口的三个字段（不含 `explanation` 正文本身）。

    `show_all=True`（query `explain_policy=all` / `include_generated_explain=1`）时
    `show_explanation` 恒为 True —— 留给以后「只看真题」开关放开用，不需要改代码。
    """
    pol = explanation_policy(trust_level, trust_labels)
    return {
        "show_explanation": True if show_all else bool(pol["show"]),
        "explanation_source": pol["source_label"],
        "explanation_hidden_reason": "" if show_all else pol["reason"],
    }


def explain_show_all() -> bool:
    """是否放开"非真题也显示解释"（query 开关）。

    规范化参数名：**`explain_policy=all`**（取值 `all` / `full` / `any` / `include_generated`）；
    同时接受等价写法 **`include_generated_explain=1`**（`as_bool` 口径：1/true/yes/y/on/是）。
    默认（不带参数）= `real`，即只在真题上显示解释。
    """
    raw = str(request.args.get("explain_policy") or "").strip().lower()
    if raw in ("all", "full", "any", "include_generated", "include_generated_explain"):
        return True
    return as_bool(request.args.get("include_generated_explain"), False)


def _subject_target(subj: str) -> int:
    try:
        data = json.loads((CONFIG_DIR / "taxonomy.json").read_text(encoding="utf-8"))
        return int(((data.get("subjects") or {}).get(subj) or {}).get("target_count") or 0)
    except Exception:  # noqa: BLE001
        return 0


def progress_payload(date_str: str) -> dict:
    """`/api/progress` 的载荷（各科目 `daily_progress` 聚合）。"""
    labels = subject_labels()
    subjects: dict[str, dict] = {}
    tot = cor = wrg = 0
    for subj in SUBJECTS:
        conn = open_db(subj)
        if conn is None:
            continue
        try:
            if not table_exists(conn, "daily_progress"):
                continue
            row = conn.execute(
                "SELECT date, total_done, correct_count, wrong_count, subjects FROM daily_progress WHERE date=?",
                (date_str,),
            ).fetchone()
        finally:
            conn.close()
        item = {"name": labels.get(subj, subj), "total_done": 0, "correct_count": 0, "wrong_count": 0, "accuracy": 0.0}
        if row is not None:
            item["total_done"] = int(row["total_done"] or 0)
            item["correct_count"] = int(row["correct_count"] or 0)
            item["wrong_count"] = int(row["wrong_count"] or 0)
            judged = item["correct_count"] + item["wrong_count"]
            item["accuracy"] = round(item["correct_count"] / judged, 4) if judged else 0.0
            try:
                item["detail"] = json.loads(row["subjects"] or "{}")
            except Exception:  # noqa: BLE001
                item["detail"] = {}
        subjects[subj] = item
        tot += item["total_done"]
        cor += item["correct_count"]
        wrg += item["wrong_count"]

    attempts_today = 0
    conn = open_db("attempts")
    if conn is not None:
        try:
            if table_exists(conn, "attempts"):
                for row in conn.execute("SELECT created_at FROM attempts"):
                    if local_date(row["created_at"]) == date_str:
                        attempts_today += 1
            counters = queue_counters(conn)
        finally:
            conn.close()
    else:
        counters = {s: 0 for s in JUDGE_STATUSES}

    judged = cor + wrg
    return {
        "date": date_str,
        "total_done": tot,
        "correct_count": cor,
        "wrong_count": wrg,
        "accuracy": round(cor / judged, 4) if judged else 0.0,
        "subjects": subjects,
        "attempts_today": attempts_today,
        "due_review": len(due_review_rows()),
        "judge_queue": counters,
        "generated_at": now_iso(),
    }


def analysis_data(subject: str | None = None) -> dict:
    """各科正确率 / 题型分布 / 知识点薄弱项（服务端聚合）。"""
    labels = subject_labels()
    per_subject: dict[str, dict] = {}
    # 题型分布
    for subj in iter_subjects(subject):
        conn = open_db(subj)
        if conn is None:
            continue
        try:
            types: list[dict] = []
            if table_exists(conn, "questions"):
                for row in conn.execute(
                    "SELECT question_type, count(*) AS n, "
                    "sum(CASE WHEN status='approved' THEN 1 ELSE 0 END) AS approved "
                    "FROM questions GROUP BY question_type ORDER BY n DESC"
                ):
                    key = row["question_type"] or ""
                    # 用户反馈：分析页原来只显示 reading_fill 这类英文 key，看不懂
                    types.append({"type": key or "(未标)", "name": type_label(key),
                                  "total": int(row["n"]), "approved": int(row["approved"] or 0)})
            kp: list[dict] = []
            if table_exists(conn, "wrong_book") and table_exists(conn, "questions"):
                for row in conn.execute(
                    "SELECT q.knowledge_point AS kp, count(*) AS n, sum(w.wrong_count) AS wrongs "
                    "FROM wrong_book w JOIN questions q ON q.question_uid = w.question_uid "
                    "GROUP BY q.knowledge_point ORDER BY wrongs DESC LIMIT 10"
                ):
                    kp.append({"knowledge_point": row["kp"] or "(未标)", "questions": int(row["n"]),
                               "wrong_count": int(row["wrongs"] or 0)})
            per_subject[subj] = {"name": labels.get(subj, subj), "question_types": types, "weak_points": kp}
        finally:
            conn.close()

    # 正确率（来自 attempts）
    accuracy: dict[str, dict] = {}
    conn = open_db("attempts")
    if conn is not None:
        try:
            if table_exists(conn, "attempts"):
                sql = "SELECT subject, question_uid, judge_score FROM attempts"
                params: list = []
                if subject:
                    sql += " WHERE subject=?"
                    params.append(subject)
                buckets: dict[str, dict] = {}
                for row in conn.execute(sql, params):
                    subj = row["subject"] or "(未知)"
                    b = buckets.setdefault(subj, {"judged": 0, "correct": 0, "wrong": 0, "unjudged": 0})
                    if row["judge_score"] is None:
                        b["unjudged"] += 1
                        continue
                    b["judged"] += 1
                    if judge_correct(subj, row["judge_score"]):
                        b["correct"] += 1
                    else:
                        b["wrong"] += 1
                for subj, b in buckets.items():
                    b["name"] = labels.get(subj, subj)
                    b["accuracy"] = round(b["correct"] / b["judged"], 4) if b["judged"] else 0.0
                    accuracy[subj] = b
        finally:
            conn.close()

    return {"subjects": per_subject, "accuracy": accuracy, "generated_at": now_iso()}


def compare_data(subject: str | None, date_str: str) -> dict:
    """复盘对比：`date_str` 当天 vs 之前全部历史 + 错题对照。"""
    labels = subject_labels()
    recent: list[dict] = []
    conn = open_db("attempts")
    own: dict[str, dict] = {}
    hist: dict[str, dict] = {}
    if conn is not None:
        try:
            if table_exists(conn, "attempts"):
                sql = ("SELECT a.attempt_id, a.question_uid, a.subject, a.judge_score, a.judge_reason, "
                       "a.created_at, q.judge_status FROM attempts a "
                       "LEFT JOIN judge_queue q ON q.attempt_id = a.attempt_id")
                params: list = []
                if subject:
                    sql += " WHERE a.subject=?"
                    params.append(subject)
                sql += " ORDER BY a.created_at DESC LIMIT 500"
                for row in conn.execute(sql, params):
                    rec = dict(row)
                    rec["correct"] = judge_correct(rec["subject"] or "", rec["judge_score"])
                    rec["name"] = labels.get(rec["subject"] or "", rec["subject"] or "")
                    bucket = own if local_date(rec["created_at"]) == date_str else hist
                    b = bucket.setdefault(rec["subject"] or "(未知)",
                                          {"total": 0, "correct": 0, "wrong": 0, "unjudged": 0})
                    b["total"] += 1
                    if rec["judge_score"] is None:
                        b["unjudged"] += 1
                    elif rec["correct"]:
                        b["correct"] += 1
                    else:
                        b["wrong"] += 1
                    if len(recent) < 30:
                        recent.append(rec)
        finally:
            conn.close()

    def finish(buckets: dict) -> dict:
        for subj, b in buckets.items():
            judged = b["correct"] + b["wrong"]
            b["accuracy"] = round(b["correct"] / judged, 4) if judged else 0.0
            b["name"] = labels.get(subj, subj)
        return buckets

    return {
        "date": date_str,
        "today": finish(own),
        "history": finish(hist),
        "recent": recent,
        "wrong_book": all_wrong_book(subject, limit=50),
        "generated_at": now_iso(),
    }


def all_wrong_book(subject: str | None = None, limit: int = 50) -> list[dict]:
    """错题对照（不限到期时间）。"""
    labels = subject_labels()
    out: list[dict] = []
    for subj in iter_subjects(subject):
        conn = open_db(subj)
        if conn is None:
            continue
        try:
            if not table_exists(conn, "wrong_book"):
                continue
            for row in conn.execute(
                "SELECT question_uid, wrong_count, correct_streak, last_wrong_at, next_review_at, mastery "
                "FROM wrong_book ORDER BY wrong_count DESC, last_wrong_at DESC LIMIT ?", (limit,)
            ):
                rec = dict(row)
                rec["subject"] = subj
                rec["subject_label"] = labels.get(subj, subj)
                q = conn.execute("SELECT stem, knowledge_point FROM questions WHERE question_uid=?",
                                 (rec["question_uid"],)).fetchone()
                rec["stem"] = (q["stem"] if q else "") or ""
                rec["knowledge_point"] = (q["knowledge_point"] if q else "") or ""
                out.append(rec)
        finally:
            conn.close()
    out.sort(key=lambda r: (-int(r.get("wrong_count") or 0), str(r.get("last_wrong_at") or "")))
    return out[:limit]


def list_papers() -> list[dict]:
    papers_dir = OUTPUT_DIR / "papers"
    if not papers_dir.exists():
        return []
    out = []
    for p in sorted(papers_dir.rglob("*")):
        if not p.is_file():
            continue
        st = p.stat()
        out.append({
            "name": p.name,
            "rel": str(p.relative_to(papers_dir)).replace("\\", "/"),
            "ext": p.suffix.lower(),
            "size": st.st_size,
            "size_kb": round(st.st_size / 1024, 1),
            "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
        })
    out.sort(key=lambda r: r["mtime"], reverse=True)
    return out


def review_queue(subject: str | None = None) -> list[dict]:
    """待人工审核（`status='pending_review'`）的题，按科目 + id 排序。"""
    out: list[dict] = []
    for subj in iter_subjects(subject):
        conn = open_db(subj)
        if conn is None:
            continue
        try:
            if not table_exists(conn, "questions"):
                continue
            for row in conn.execute(
                "SELECT id, question_uid, subject, source_type, source_url, source_credit, chapter, "
                "knowledge_point, syllabus_ref, question_type, stem, options, answer, explanation, "
                "difficulty, status, reviewed_by, version, fact_claim, fact_source, fact_verified, quality_score "
                "FROM questions WHERE status='pending_review' ORDER BY id"
            ):
                rec = dict(row)
                rec["options_parsed"] = parse_options(rec.get("options"))
                out.append(rec)
        finally:
            conn.close()
    return out


def settings_data() -> dict:
    """设置页：模型档位 / 批量大小 / 预算 / 端口 / key 是否配置（**绝不回显 key**）。"""
    routing: dict = {}
    budget: dict = {}
    try:
        routing = json.loads((CONFIG_DIR / "routing.json").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        routing = {}
    try:
        budget = json.loads((CONFIG_DIR / "cost_budget.json").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        budget = {}

    spent = 0.0
    ledger = LOGS_DIR / "cost_ledger.jsonl"
    if ledger.exists():
        for line in ledger.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                spent += float(json.loads(line).get("cost_cny") or 0.0)
            except Exception:  # noqa: BLE001
                continue

    total_budget = float(budget.get("total") or 0.0)
    used_ratio = round(spent / total_budget, 4) if total_budget else 0.0
    port = read_port_file()
    return {
        "routing": routing,
        "budget": budget,
        "spent_cny": round(spent, 4),
        "used_ratio": used_ratio,
        "over_warning": bool(total_budget and used_ratio >= float(budget.get("warning") or 0.8)),
        "port": port,
        "port_file": str(PORT_FILE),
        "data_dir": str(DATA_DIR),
        "root": str(ROOT),
        # ⚠️ 只报告"是否存在"+掩码，任何 key 内容都不进页面（需求 9 的设置页靠它显示状态）
        "api_key_configured": bool(_env_flags().get("DEEPSEEK_API_KEY")),
        "api_key_hint": mask_secret(read_env_value("DEEPSEEK_API_KEY")),
        "env_file": str(ROOT / ".env"),
        "base_url_configured": bool(_env_flags().get("DEEPSEEK_BASE_URL")),
        "db": [{"name": s, "exists": db_path(s).exists()} for s in SUBJECTS] + [
            {"name": "attempts", "exists": db_path("attempts").exists()},
        ],
        "judge_statuses": list(JUDGE_STATUSES),
        "question_statuses": list(QUESTION_STATUSES),
    }


def _env_flags() -> dict:
    """.env 里**每个键是否有值**，**不返回任何值本身**。"""
    out: dict[str, bool] = {}
    env_file = ROOT / ".env"
    if not env_file.exists():
        return out
    for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = bool(value.strip().strip('"').strip("'"))
    return out


def read_env_value(key: str) -> str:
    """读 `.env` 里某个键的值（读不到返回空串）。**只给掩码/内部判断用，绝不回显给页面。**"""
    env_file = ROOT / ".env"
    if not env_file.exists():
        return ""
    for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        if k.strip() == key:
            return v.strip().strip('"').strip("'")
    return ""


def mask_secret(value: str) -> str | None:
    """密钥掩码（需求 9 前端要显示"当前是哪个 key"但**绝不能回显完整 key**）。

    `sk-abcdefghijkl` → `sk-…ghij`（留前缀 3 位 + 末尾 4 位）；太短的只留 `…末2位`。
    """
    s = str(value or "").strip()
    if not s:
        return None
    if len(s) <= 8:
        return "…" + s[-2:]
    return s[:3] + "…" + s[-4:]


def write_env_value(key: str, value: str) -> Path:
    """把 `KEY=value` 写进 `.env`（保留其余行与注释；`value` 为空则**删除该行**）。

    🔴 安全约定：
      - 写入前校验 key 名与 value（不得含换行/回车/NUL，防注入多行把别的配置顶掉）；
      - 文件权限沿用项目既有做法（本机单用户离线工具，`.env` 已被 `.gitignore` 排除）；
      - **绝不把 key 内容写进日志**，也绝不让它出现在任何 HTTP 响应里。
    """
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", str(key or "")):
        raise ValueError(f"非法配置键名: {key!r}")
    text = str(value or "")
    if any(ch in text for ch in ("\n", "\r", "\x00")):
        raise ValueError("值里不能有换行或 NUL")
    env_file = ROOT / ".env"
    lines: list[str] = []
    if env_file.exists():
        lines = env_file.read_text(encoding="utf-8", errors="replace").splitlines()
    out: list[str] = []
    replaced = False
    for line in lines:
        s = line.strip()
        if s and not s.startswith("#") and "=" in s and s.split("=", 1)[0].strip() == key:
            if not replaced:
                if text:
                    out.append(f"{key}={text}")
                replaced = True
            continue
        out.append(line)
    if text and not replaced:
        if out and out[-1].strip():
            out.append("")
        out.append(f"{key}={text}")
    env_file.parent.mkdir(parents=True, exist_ok=True)
    env_file.write_text("\n".join(out) + "\n", encoding="utf-8")
    return env_file


def settings_payload() -> dict:
    """`/api/settings` 载荷：**只报状态与掩码，绝不回显 key 内容**。"""
    key = read_env_value("DEEPSEEK_API_KEY")
    base = read_env_value("DEEPSEEK_BASE_URL")
    return {
        "api_key_configured": bool(key),
        "api_key_hint": mask_secret(key),
        "base_url": base or None,
        "base_url_configured": bool(base),
        "env_file": str(ROOT / ".env"),
        "note": ("API key 只写在项目根目录的 .env 里；填了它才能让写作/整段翻译这类主观题走 AI 判分，"
                 "客观题/填空题/连词成句已由本地规则判分当场出分，不需要 key。"),
    }


def read_port_file():
    try:
        return int(PORT_FILE.read_text(encoding="utf-8").strip())
    except Exception:  # noqa: BLE001
        return None


def write_port_file(port: int) -> Path:
    PORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    PORT_FILE.write_text(f"{port}\n", encoding="utf-8")
    return PORT_FILE


# ============================================================== 页面路由


def _nav(active: str) -> dict:
    return {"active": active, "subjects": [{"key": s, "name": subject_labels().get(s, s)} for s in SUBJECTS]}


def knowledge_data() -> list[dict]:
    """「按知识点刷题」数据：各科目的知识点清单 + 该点下的已通过题量 + 刷题链接。

    - C 语言：用 `subjects/c_common/knowledge_base.json` 的 15 个规范点，按 `alias_chapters`
      反查两库（c_wuhan + c_hbpu）的题量。
    - 英语：用 `subjects/english/knowledge_base.json`。题型维度按 `question_type` 统计（一定有效）；
      语言知识维度按 `knowledge_point` 统计（打标后才有量，未打标则显示为待补标）。
    - ACA：用 252 个官方知识点，按 `knowledge_point` 统计。
    """
    out: list[dict] = []
    specs = [("c_common", ["c_wuhan", "c_hbpu"], "C 语言"), ("english", ["english"], "英语"),
             ("aca_llm", ["aca_llm"], "阿里云 ACA")]
    for kb_subj, dbs, label in specs:
        p = ROOT / "subjects" / kb_subj / "knowledge_base.json"
        if not p.exists():
            continue
        try:
            kb = json.loads(p.read_text(encoding="utf-8-sig"))
        except Exception:  # noqa: BLE001
            continue
        points = kb.get("knowledge_points") or []
        # ACA 是 modules[].points[] 结构
        if not points:
            for m in (kb.get("modules") or []):
                for pt in (m.get("points") or []):
                    q = dict(pt)
                    q.setdefault("module", m.get("name"))
                    points.append(q)
        items: list[dict] = []
        conns = {}
        for d in dbs:
            c = open_db(d)
            if c is not None:
                conns[d] = c
        try:
            for pt in points:
                if not isinstance(pt, dict):
                    continue
                name = str(pt.get("name") or pt.get("title") or "").strip()
                if not name:
                    continue
                aliases = pt.get("alias_chapters") or []
                types = pt.get("question_types") or ([pt.get("question_type")] if pt.get("question_type") else [])
                n = 0
                for c in conns.values():
                    if not table_exists(c, "questions"):
                        continue
                    if aliases:
                        ph = ",".join("?" * len(aliases))
                        n += c.execute(f"SELECT count(*) FROM questions WHERE status='approved' "
                                       f"AND knowledge_point IN ({ph})", list(aliases)).fetchone()[0]
                    elif types:
                        ph = ",".join("?" * len(types))
                        n += c.execute(f"SELECT count(*) FROM questions WHERE status='approved' "
                                       f"AND question_type IN ({ph})", list(types)).fetchone()[0]
                    else:
                        n += c.execute("SELECT count(*) FROM questions WHERE status='approved' "
                                       "AND (knowledge_point=? OR knowledge_point LIKE ?)",
                                       (name, f"%{name}%")).fetchone()[0]
                db_main = dbs[0]
                items.append({
                    "id": pt.get("id") or "", "name": name,
                    "desc": (pt.get("desc") or "")[:120],
                    "module": pt.get("module") or "", "difficulty": pt.get("difficulty") or "",
                    "count": n, "kp": name, "subject": db_main,
                    "quiz_url": f"/quiz?subject={db_main}&kp={name}",
                })
        finally:
            for c in conns.values():
                try:
                    c.close()
                except Exception:  # noqa: BLE001
                    pass
        items.sort(key=lambda x: (-x["count"], x["id"] or x["name"]))
        out.append({"subject": kb_subj, "label": label, "dbs": dbs,
                    "total_points": len(items), "with_questions": sum(1 for i in items if i["count"] > 0),
                    "points": items})
    return out


@app.route("/knowledge", methods=["GET"])
def page_knowledge():
    """按知识点刷题（用户要求：点知识点 → 直接刷该知识点/题型的题）。"""
    return render_template("knowledge.html", page="knowledge", nav=_nav("knowledge"),
                           data=knowledge_data())


# 「模拟题」专区：考试宝抓来的那份「阿里云大模型aca认证题库」（用户指定参照）。
# 它和普通科目不同——不是独立 `SUBJECTS` 键，而是 aca_llm 库里按 `exam_title` 切出来的一个视图。
# 为什么不做成新科目：科目键在 20 个脚本 + 4 个测试 fixture 里都是硬编码常量，
# 新增一个会牵动进度聚合 / SM2 / 弱点诊断等一整条链路，收益不抵风险。
MOCK_EXAM = "考试宝预览"
MOCK_NAME = "ACA 大模型（考试宝题库）"


def mock_entry() -> dict | None:
    """首页「模拟题」卡片的入口数据（没题就返回 None，卡片不显示）。"""
    conn = open_db("aca_llm")
    if conn is None:
        return None
    n = 0
    try:
        if table_exists(conn, "questions"):
            n = conn.execute(
                "SELECT count(*) FROM questions WHERE status='approved' AND COALESCE(exam_title,'') LIKE ?",
                (f"%{MOCK_EXAM}%",)).fetchone()[0]
    except sqlite3.Error:
        n = 0
    finally:
        conn.close()
    if not n:
        return None
    return {
        "name": MOCK_NAME,
        "exam": MOCK_EXAM,
        "total": n,
        "desc": "考试宝整理的「阿里云大模型aca认证题库」：答案与解析由题库作者提供，"
                "解析是该网站用 AI 生成的，不是阿里云官方答案。",
        "quiz_url": f"/quiz?subject=aca_llm&exam={MOCK_EXAM}",
        "analysis_url": "/analysis?subject=aca_llm",
    }


def extended_entries() -> list[dict]:
    """「拓展专区」入口：超纲但可能考到的题。

    用户明确要求：超纲≠题目有问题，真题/考试确实可能考到，所以要**单独留一份能专门看**，
    而不是直接丢掉（这些题的解析里都带 `【超纲提示】` 说明为什么超纲）。
    """
    out: list[dict] = []
    labels = display_meta().get("trust_levels") or {}
    for trust in ("acp", "out_of_syllabus"):
        label = labels.get(trust)
        if not label:
            continue
        conn = open_db("aca_llm")
        n = 0
        if conn is not None:
            try:
                if table_exists(conn, "questions"):
                    n = conn.execute("SELECT count(*) FROM questions WHERE trust_level=? AND status='approved'",
                                     (trust,)).fetchone()[0]
            except sqlite3.Error:
                n = 0
            finally:
                conn.close()
        if n:
            out.append({
                "name": label,
                "desc": "通用机器学习/深度学习细节，不在 ACA 六大模块内，但考试可能涉及；每题解析里注明了超纲原因",
                "total": n,
                "quiz_url": f"/quiz?subject=aca_llm&trust={trust}",
                "analysis_url": "/analysis?subject=aca_llm",
            })
    return out


@app.route("/kb", methods=["GET"])
def page_kb():
    """知识库（RAG 底座）页面：**每个科目一个独立库文件**，检索不跨科目。

    - `/kb?subject=aca_llm`            概览 + 知识点列表
    - `/kb?subject=aca_llm&kp=<名称>`  单个知识点的材料（每点一页）
    - `/kb?subject=aca_llm&q=提示词`   科目内检索
    """
    if kb_lib is None:
        return render_template("kb.html", page="kb", nav=_nav("kb"), subject=SUBJECTS[0],
                               subject_labels=subject_labels(), kps=[], docs=[], stats={},
                               kp="", q="", chunks=[], searched=[], error="知识库模块不可用（scripts/kb.py）")
    subject = request.args.get("subject") or SUBJECTS[0]
    if subject not in SUBJECTS:
        subject = SUBJECTS[0]
    kp_name = (request.args.get("kp") or "").strip()
    q = (request.args.get("q") or "").strip()

    stats: dict = {}
    kps: list = []
    docs: list = []
    chunks: list = []
    conn = kb_lib.open_db(subject)
    if conn is not None:
        try:
            stats = {
                "docs": conn.execute("SELECT COUNT(*) FROM docs").fetchone()[0],
                "chunks": conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0],
                "chars": conn.execute("SELECT COALESCE(SUM(chars),0) FROM chunks").fetchone()[0],
                "kp": conn.execute("SELECT COUNT(*) FROM kp").fetchone()[0],
            }
            kps = [dict(r) for r in conn.execute(
                "SELECT k.id, k.name, k.parent, k.weight, COUNT(kc.chunk_id) AS n "
                "FROM kp k LEFT JOIN kp_chunk kc ON kc.kp_id=k.id "
                "GROUP BY k.id ORDER BY (k.parent<>''), k.id")]
            docs = [dict(r) for r in conn.execute(
                "SELECT id, title, kind, chars, "
                "(SELECT COUNT(*) FROM chunks c WHERE c.doc_id=docs.id) AS n "
                "FROM docs ORDER BY id")]
            if kp_name:
                chunks = [dict(r) for r in conn.execute(
                    "SELECT c.id, c.text, c.heading, d.title FROM kp k "
                    "JOIN kp_chunk kc ON kc.kp_id=k.id JOIN chunks c ON c.id=kc.chunk_id "
                    "JOIN docs d ON d.id=c.doc_id WHERE k.name=? ORDER BY c.id LIMIT 50", (kp_name,))]
        finally:
            conn.close()

    searched = kb_lib.search(subject, q, 6) if q else []
    return render_template("kb.html", page="kb", nav=_nav("kb"), subject=subject,
                           subject_labels=subject_labels(), kps=kps, docs=docs, stats=stats,
                           kp=kp_name, q=q, chunks=chunks, searched=searched, error="")


@app.route("/api/kb/search", methods=["GET"])
def api_kb_search():
    """科目内检索（给生成脚本/其它页面调用）。**必须传 subject**，物理上不跨库。"""
    if kb_lib is None:
        return jsonify({"error": "知识库模块不可用"}), 500
    subject = request.args.get("subject") or ""
    q = (request.args.get("q") or "").strip()
    k = as_int(request.args.get("k"), 5, lo=1, hi=30)
    if subject not in SUBJECTS:
        return jsonify({"error": f"未知科目: {subject}", "subjects": list(SUBJECTS)}), 400
    if not q:
        return jsonify({"error": "缺 q"}), 400
    rows = kb_lib.search(subject, q, k)
    return jsonify({"subject": subject, "q": q, "count": len(rows), "chunks": rows})


@app.route("/", methods=["GET"])
def page_index():
    cards = subject_cards()
    prog = progress_payload(today_local())
    return render_template(
        "index.html", page="index", nav=_nav("index"), cards=cards, progress=prog,
        due=due_review_rows(limit=8), queue=current_queue_counters(),
        papers=len(list_papers()),
        extended=extended_entries(),
        mock=mock_entry(),
    )


@app.route("/quiz", methods=["GET"])
def page_quiz():
    subject = request.args.get("subject") or ""
    qtype = request.args.get("type") or ""
    difficulty = request.args.get("difficulty") or ""
    status = request.args.get("status") or "approved"
    trust = request.args.get("trust") or ""
    kp = request.args.get("kp") or ""
    # 「模拟题」专区：exam=考试宝预览 时只刷那一份题库
    exam = request.args.get("exam") or ""
    # 刷错题：wrong=1 → 只出「判分记录里判过错」的题（从判分记录页一键进）
    wrong = request.args.get("wrong") or ""
    qtypes = question_types_map()
    type_names = {t["key"]: t["name"] for lst in qtypes.values() for t in lst}
    disp = display_meta()
    return render_template(
        "quiz.html", page="quiz", nav=_nav("quiz"),
        subject=subject, qtype=qtype, difficulty=difficulty, status=status, trust=trust, kp=kp,
        exam=exam, wrong=wrong,
        qtypes=qtypes, type_names=type_names, subject_labels=subject_labels(),
        question_statuses=QUESTION_STATUSES,
        # 题型说明（"这题要干嘛"）——用户反馈连词成句看不懂，必须每题给作答指引
        type_meta=disp.get("types", {}),
        # 来源可信度选项（官方真题 / 教材题库 / 第三方练习 / AI 生成）
        trust_levels=disp.get("trust_levels", {}),
    )


@app.route("/analysis", methods=["GET"])
def page_analysis():
    subject = request.args.get("subject") or ""
    data = analysis_data(subject or None)
    return render_template("analysis.html", page="analysis", nav=_nav("analysis"),
                           subject=subject, data=data, subject_labels=subject_labels())


@app.route("/compare", methods=["GET"])
def page_compare():
    subject = request.args.get("subject") or ""
    date_str = request.args.get("date") or today_local()
    data = compare_data(subject or None, date_str)
    return render_template("compare.html", page="compare", nav=_nav("compare"),
                           subject=subject, date=date_str, data=data,
                           subject_labels=subject_labels())


@app.route("/queue", methods=["GET"])
def page_queue():
    status = request.args.get("status") or ""
    if status not in JUDGE_STATUSES:
        status = ""
    counters = current_queue_counters()
    return render_template("queue.html", page="queue", nav=_nav("queue"),
                           status=status, counters=counters, rows=queue_rows(status or None, 200),
                           judge_statuses=JUDGE_STATUSES)


# ============================================================== 弱势诊断（需求 8）


def _weakness_lib():
    """懒加载 `scripts/weakness.py`（缺失时返回 None）。"""
    global _WEAKNESS_LIB
    if _WEAKNESS_LIB is not None:
        return _WEAKNESS_LIB
    try:
        if str(SCRIPTS_DIR) not in sys.path:
            sys.path.insert(0, str(SCRIPTS_DIR))
        import weakness  # type: ignore
        _WEAKNESS_LIB = weakness
    except Exception:  # noqa: BLE001
        _WEAKNESS_LIB = False
    return _WEAKNESS_LIB or None


_WEAKNESS_LIB = None


@app.route("/api/weakness", methods=["GET"])
def api_weakness():
    """弱势诊断（需求 8）：**我的**正确率 + 弱势科目/知识点/题型 + 覆盖缺口 + 趋势。

    对错口径走 `update_daily_progress.judge_correct()`（全项目唯一阈值），未判分的作答单列。
    `?remember=1` 会把当日快照追加进 `logs/weakness_history.jsonl`（幂等，一天一条）。
    """
    lib = _weakness_lib()
    if lib is None:
        return jsonify({"error": "scripts/weakness.py 不可用"}), 500
    try:
        data = lib.analyze(remember_snapshot=as_bool(param("remember"), False))
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": f"弱势诊断失败: {type(exc).__name__}: {exc}"}), 500
    return jsonify(data)


@app.route("/api/weakness/advice", methods=["POST"])
def api_weakness_advice():
    """**学习强化方案**（需求 8 第 ③ 点）：默认只返回给云端大模型的提示词，**不发付费请求**。

    为什么默认不直接调：按项目铁律，任何真实计费调用前都要先算成本并让用户知情。
    这里先把"要发什么、大概多少钱"摆出来；真正调用留给下一步（`confirm_paid=true` 预留位，
    当前**故意不实现**真实调用，避免误触烧钱）。
    """
    lib = _weakness_lib()
    if lib is None:
        return jsonify({"error": "scripts/weakness.py 不可用"}), 500
    body = json_body()
    try:
        data = lib.analyze(remember_snapshot=False)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": f"弱势诊断失败: {exc}"}), 500
    prompt = lib.build_advice_prompt(data)
    model = str(body.get("model") or "deepseek-flash")
    if as_bool(body.get("confirm_paid"), False):
        return jsonify({
            "ok": False, "paid_gate": True, "model": model, "prompt": prompt,
            "error": "本机版本尚未接通云端调用（避免误触计费）。提示词已生成，可复制到任意大模型使用；"
                     "要接通请先在设置页配置 API key，再让维护者打开付费通道。",
        }), 501
    return jsonify({
        "ok": True, "paid_call": False, "model": model, "prompt": prompt,
        "prompt_chars": len(prompt),
        "estimate": {"note": "按 deepseek-flash 估价（仅参考，未实际调用）",
                     "input_tokens_est": int(len(prompt) / 1.6),
                     "cost_cny_est": round(len(prompt) / 1.6 / 1_000_000 * 2.2, 4)},
        "tip": "把上面的提示词复制到任意大模型（或配置 API key 后由维护者接通）即可拿到强化方案。",
        "summary": data.get("totals"),
        "weakest": data.get("weakest"),
    })


@app.route("/paper", methods=["GET"])
def page_paper():
    """套卷模式（需求 6）页面。真正的数据走 `/api/paper/list` 与 `/api/paper`（前端拉）。"""
    subject = request.args.get("subject") or ""
    title = request.args.get("title") or ""
    if subject and subject not in SUBJECTS:
        subject = ""
    return render_template("paper.html", page="paper", nav=_nav("paper"),
                           subject=subject, title=title,
                           subject_labels=subject_labels(), subjects=SUBJECTS)


@app.route("/settings", methods=["GET"])
def page_settings():
    return render_template("settings.html", page="settings", nav=_nav("settings"),
                           data=settings_data(), subject_labels=subject_labels(), subjects=SUBJECTS)


@app.route("/api/settings", methods=["GET"])
def api_settings():
    """设置状态（**只报"是否配置"+掩码，绝不回显 key 内容**）——需求 9 的前端读它。"""
    return jsonify(settings_payload())


# ============================================================== 套卷模式（需求 6）


def _paper_lib():
    """懒加载 `scripts/paper_lib.py`（缺失时返回 None，页面给出明确提示而不是 500）。"""
    global _PAPER_LIB
    if _PAPER_LIB is not None:
        return _PAPER_LIB
    try:
        if str(SCRIPTS_DIR) not in sys.path:
            sys.path.insert(0, str(SCRIPTS_DIR))
        import paper_lib  # type: ignore
        _PAPER_LIB = paper_lib
    except Exception:  # noqa: BLE001
        _PAPER_LIB = False
    return _PAPER_LIB or None


_PAPER_LIB = None


def paper_attempt_stats() -> dict:
    """每套卷「做过多少题 / 算不算做完」——用户要求做完的卷子灰显并可折叠。

    ⚠️ 不能只按 question_uid 匹配：卷子重建一次 uid 就全变了（本会话就重建过几轮），
    所以这里按**题干归一化**匹配 attempts 里的题——重建后依然认得出"这题做过"。
    做完门槛取 80%：考到一半退出的不标灰。
    """
    conn_a = open_db("attempts")
    if conn_a is None:
        return {}
    try:
        if not table_exists(conn_a, "attempts"):
            return {}
        uid_list = [str(r[0]) for r in conn_a.execute(
            "SELECT DISTINCT question_uid FROM attempts") if r[0]]
    except sqlite3.Error:
        return {}
    finally:
        conn_a.close()
    if not uid_list:
        return {}

    def norm(s: str) -> str:
        return re.sub(r"[\s\u3000，。、；：？！“”‘’（）【】《》〈〉,.;:?!\"'()\[\]<>~—\-_/\\|+*=&%$#@^`{}]+",
                      "", (s or "")).lower()

    uid_norm: dict[str, str] = {}
    agg: dict[tuple[str, str], list[int]] = {}
    for subj in SUBJECTS:
        conn = open_db(subj)
        if conn is None:
            continue
        try:
            if not table_exists(conn, "questions"):
                continue
            for title, uid, stem in conn.execute(
                    "SELECT COALESCE(exam_title,'') AS t, question_uid, COALESCE(stem,'') "
                    "FROM questions WHERE status='approved' AND COALESCE(exam_title,'')<>''"):
                n = norm(stem)
                uid_norm[str(uid)] = n
                key = (subj, str(title))
                a = agg.setdefault(key, [0, 0])
                a[0] += 1
                a[1] += 0          # 命中数最后统一算
        except sqlite3.Error:
            continue
        finally:
            conn.close()
    hit_norm = {uid_norm.get(u, "") for u in uid_list}
    hit_norm.discard("")
    if not hit_norm:
        return {}
    out: dict[tuple[str, str], dict] = {}
    for key, (total, _) in agg.items():
        subj, title = key
        conn = open_db(subj)
        hit = 0
        if conn is not None:
            try:
                for (stem,) in conn.execute(
                        "SELECT COALESCE(stem,'') FROM questions WHERE status='approved' AND exam_title=?",
                        (title,)):
                    if norm(stem) in hit_norm:
                        hit += 1
            except sqlite3.Error:
                hit = 0
            finally:
                conn.close()
        out[key] = {"total": total, "attempted": hit,
                    "done": hit >= max(1, int(total * 0.8))}
    return out


PAPER_FLAGS = DATA_DIR / "paper_flags.json"


def paper_flags() -> dict:
    """手动标记"这套卷我做完了"（{subject|title: true}）。

    为什么还要手动：卷子重建一次，attempts 里的 question_uid 就全变了，
    历史作答再也对不上（题干匹配也只能救回还在库里的题）。用户明确要求
    "做完的卷子灰显、可折叠"，给个手动开关最实在。
    """
    try:
        if PAPER_FLAGS.exists():
            data = json.loads(PAPER_FLAGS.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        pass
    return {}


@app.route("/api/paper/flag", methods=["POST"])
def api_paper_flag():
    """标记/取消标记某套卷「已完成」。body: {subject, title, done: true|false}"""
    body = json_body()
    subject = str(body.get("subject") or "")
    title = str(body.get("title") or "")
    done = bool(body.get("done"))
    if subject not in SUBJECTS or not title:
        return jsonify({"error": "需要合法的 subject 和 title"}), 400
    flags = paper_flags()
    key = f"{subject}|{title}"
    if done:
        flags[key] = True
    else:
        flags.pop(key, None)
    try:
        PAPER_FLAGS.parent.mkdir(parents=True, exist_ok=True)
        PAPER_FLAGS.write_text(json.dumps(flags, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        return jsonify({"error": f"写标记失败: {exc}"}), 500
    return jsonify({"ok": True, "key": key, "done": done})


@app.route("/api/paper/list", methods=["GET"])
def api_paper_list():
    """套卷清单（需求 6）：按 `exam_title` 分组的整卷，**按科目分组返回**。

    ⚠️ 口径提醒：英语的套卷是**真正的历年真题卷**（湖北 2020-2026 / 河北 16-25，41–69 题/套，
    与真实卷面结构一致）；C 语言的 `exam_title` 是**按学校/教材来源**聚合的（一套 139–454 题），
    它不是"一张卷子"而是"某校的题集"，前端必须如实标注，不要谎称"真题卷"。
    """
    lib = _paper_lib()
    if lib is None:
        return jsonify({"error": "scripts/paper_lib.py 不可用", "papers": []}), 500
    subject = param("subject") or None
    if subject and subject not in SUBJECTS:
        return jsonify({"error": f"未知科目: {subject!r}", "subjects": list(SUBJECTS)}), 400
    min_size = as_int(param("min_size", None), 10, lo=1, hi=1000)
    papers = lib.list_papers(subject, min_size=min_size)
    stats = paper_attempt_stats()
    flags = paper_flags()
    groups: dict[str, list] = {s: [] for s in SUBJECTS}
    for item in papers:
        item["is_real_exam"] = item["real_count"] >= item["count"] * 0.8
        item["exam_kind"] = ("真题卷" if item["subject"] == "english" and item["is_real_exam"]
                             else "校/教材题集" if item["subject"].startswith("c_")
                             else "认证题库" if item["subject"] == "aca_llm" else "混合来源")
        st = stats.get((item["subject"], item["title"])) or {}
        item["attempted"] = int(st.get("attempted") or 0)
        item["auto_done"] = bool(st.get("done"))
        item["manual_done"] = bool(flags.get(f"{item['subject']}|{item['title']}"))
        item["done"] = item["auto_done"] or item["manual_done"]
        groups[item["subject"]].append(item)
    return jsonify({"count": len(papers), "subjects": list(SUBJECTS),
                    "subject_labels": subject_labels(), "groups": groups,
                    "note": "英语 = 历年真题整卷（按原卷顺序）；C 语言 = 某校/某教材题集；"
                            "ACA = 认证题库。顺序取题目入库顺序（同套卷 id 连号，等于原卷顺序）。"})


def origin_label(rec: dict) -> str:
    """这道题**到底从哪来**，以及**答案可不可信**——用户考前要按来源挑卷子。

    分四档（不猜，只看 source_url + trust_level）：
      - 考试宝·有原答案 ：31210250 这类，答案是从网页上抓到的（最可信）
      - 考试宝·答案AI推断：37563622 这类，题干/选项来自考试宝，但网页答案要 APP/会员，
                          答案是模型两次作答一致的推断值（题目真、答案需自己判断）
      - 用户提供/其它    ：用户给的题库或别的第三方
      - AI 生成          ：题干和答案都是模型写的
    """
    url = str(rec.get("source_url") or "")
    tl = str(rec.get("trust_level") or "")
    low = url.lower()
    if tl == "ai_generated":
        return "AI 生成"
    if "kaoshibao" in low:
        fs = str(rec.get("fact_source") or "")
        ai_answer = ("AI" in fs) or ("推断" in fs) or ("37563622" in low)
        return "考试宝·答案AI推断" if ai_answer else "考试宝·有原答案"
    if tl == "acp":
        return "ACP 超纲"
    if tl in ("official_exam", "textbook"):
        return "官方/教材"
    if not url:
        return "来源未标注"
    return "用户提供/其它"


@app.route("/api/paper", methods=["GET"])
def api_paper():
    """取一套卷（需求 6）：元信息 + **按原卷顺序**的题目（含选项与参考答析）。"""
    lib = _paper_lib()
    if lib is None:
        return jsonify({"error": "scripts/paper_lib.py 不可用"}), 500
    subject = str(param("subject") or "")
    title = str(param("title") or "")
    if subject not in SUBJECTS:
        return jsonify({"error": f"未知科目: {subject!r}", "subjects": list(SUBJECTS)}), 400
    if not title:
        return jsonify({"error": "缺少 title（套卷名，取自 /api/paper/list）"}), 400
    limit = as_int(param("limit", None), MAX_PAGE_LIMIT, lo=1, hi=MAX_PAGE_LIMIT)
    summary = lib.paper_summary(subject, title, limit=limit)
    if summary["count"] == 0:
        return jsonify({"error": f"没有找到套卷: {subject}/{title}"}), 404
    rows = lib.paper_questions(subject, title, limit=limit)
    total_in_db = lib.paper_questions(subject, title, limit=10**6)
    summary["limit_applied"] = limit
    summary["total_in_db"] = len(total_in_db)
    summary["truncated"] = len(total_in_db) > summary["count"]
    labels = display_meta().get("trust_levels") or {}
    explain_all = explain_show_all()
    questions = []
    for i, rec in enumerate(rows, start=1):
        rec["seq"] = i
        rec["subject"] = subject
        rec["options_parsed"] = runtime_options(rec)
        rec["objective"] = is_objective(rec.get("question_type"), rec["options_parsed"], rec.get("answer"))
        rec["answer_keys"] = answer_keys(rec.get("answer"), rec.get("stem")) if rec["objective"] else ""
        rec["type_name"] = type_label(rec.get("question_type"))
        rec["trust_label"] = labels.get(rec.get("trust_level") or "", rec.get("trust_level") or "来源未标注")
        rec["origin"] = origin_label(rec)
        rec.update(explanation_fields(rec.get("trust_level"), labels, explain_all))
        questions.append(rec)
    summary["questions"] = questions
    summary["seq_source"] = "id（同套卷 id 连号 = 原卷顺序）"
    return jsonify(summary)


@app.route("/api/paper/submit", methods=["POST"])
def api_paper_submit():
    """交卷（需求 6）：**整卷一次交**，逐题规则判分 + 出分报告。

    - 规则判得了的题 → 当场出分，写 `attempts`(source_type='paper') / `judge_queue(synced)` / `review_log`；
    - 判不了的（写作/整段翻译）→ 入队 `pending`，由 AI 通道处理（`/api/judge_one` 单题、`/api/sync` 批量）；
    - 返回每题结果 + 汇总（得分/满分/正确数/待 AI 数/正确率），并重算当日 `daily_progress`。
    """
    lib = _paper_lib()
    if lib is None:
        return jsonify({"error": "scripts/paper_lib.py 不可用"}), 500
    body = json_body()
    subject = str(body.get("subject") or "")
    title = str(body.get("title") or "")
    answers = body.get("answers")
    if subject not in SUBJECTS:
        return jsonify({"error": f"未知科目: {subject!r}", "subjects": list(SUBJECTS)}), 400
    if not title:
        return jsonify({"error": "缺少 title"}), 400
    if not isinstance(answers, dict):
        return jsonify({"error": 'answers 需为 {"question_uid": "作答"}'}), 400

    elapsed = body.get("elapsed_ms")
    elapsed_ms = as_int(elapsed, 0, lo=0, hi=86_400_000) or 0
    # ⚠️ 与 `/api/paper` **用同一个 limit**：C 语言有 448/454 题的巨卷，
    #    若看卷用 300、判分用 200，就会出现"我看到的题没全判"（子代理实测发现）。
    limit = as_int(param("limit", None) or body.get("limit"), MAX_PAGE_LIMIT, lo=1, hi=MAX_PAGE_LIMIT)
    rows = lib.paper_questions(subject, title, limit=limit)
    if not rows:
        return jsonify({"error": f"没有找到套卷: {subject}/{title}"}), 404
    err = _ensure_attempts_db()
    if err:
        return jsonify({"error": err}), 500

    results: list[dict] = []
    got = full_total = 0.0
    correct = wrong = pending = unanswered = 0
    per_type: dict[str, dict] = {}
    for seq, rec in enumerate(rows, start=1):
        uid = str(rec["question_uid"])
        raw = answers.get(uid)
        if isinstance(raw, (list, tuple)):
            raw = "".join(str(x) for x in raw)
        user_answer = str(raw if raw is not None else "")
        full = judge_full_score(subject, rec.get("question_type"))
        full_total += full
        attempt_id = "att-{}-{}".format(datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"),
                                        uuid.uuid4().hex[:8])
        _try_write_attempt(attempt_id, uid, subject, user_answer, "paper", elapsed_ms)
        item = {"question_uid": uid, "seq": seq, "question_type": rec.get("question_type"),
                "type_name": type_label(rec.get("question_type")), "user_answer": user_answer,
                "attempt_id": attempt_id, "full_score": full, "status": "pending",
                # 结果页要能对照选项看错在哪（用户明确要求）：
                # 题干 + 选项 + 答案字母集合都带上，前端才好标出「正确项 / 你选的项」
                "stem": rec.get("stem") or "",
                "options_parsed": runtime_options(rec),
                "answer_keys": answer_keys(rec.get("answer"), rec.get("stem")),
                "explanation": rec.get("explanation") or ""}
        if not user_answer.strip():
            unanswered += 1
        objective_ans = answer_keys(rec.get("answer"), rec.get("stem"))
        if not user_answer.strip() and objective_ans:
            # 没作答的**客观题**：直接按 0 分计，不要进 AI 判分队列（省钱、也不污染队列）
            mark_attempt_unanswered(attempt_id)
            item.update({"status": "synced", "judge_score": 0.0, "correct": False,
                         "judge_reason": "未作答，按答错计 0 分", "judged_by": "unanswered",
                         "answer": rec.get("answer")})
            wrong += 1
            bucket = per_type.setdefault(item["question_type"] or "", {
                "name": item["type_name"], "count": 0, "correct": 0, "pending": 0, "score": 0.0, "full": 0.0})
            bucket["count"] += 1
            bucket["full"] = round(bucket["full"] + full, 2)
            results.append(item)
            continue
        verdict = apply_local_verdict(subject, uid, attempt_id, user_answer, source_type="paper")
        if verdict and verdict.get("gradeable"):
            score = float(verdict.get("judge_score") or 0.0)
            item.update({"status": "synced", "judge_score": score,
                         "judge_reason": verdict.get("judge_reason"),
                         "correct": bool(verdict.get("correct")), "judged_by": "local_rule",
                         "answer": rec.get("answer")})
            got += score
            correct += 1 if verdict.get("correct") else 0
            wrong += 0 if verdict.get("correct") else 1
        else:
            pending += 1
            item["judge_reason"] = (verdict or {}).get("reason", "交给 AI 判分")
            item["judged_by"] = "pending_ai"
        bucket = per_type.setdefault(item["question_type"] or "", {
            "name": item["type_name"], "count": 0, "correct": 0, "pending": 0, "score": 0.0, "full": 0.0})
        bucket["count"] += 1
        bucket["full"] = round(bucket["full"] + full, 2)
        if item["status"] == "synced":
            bucket["correct"] += 1 if item.get("correct") else 0
            bucket["score"] = round(bucket["score"] + float(item.get("judge_score") or 0), 2)
        else:
            bucket["pending"] += 1
        results.append(item)

    judged = correct + wrong
    return jsonify({
        "ok": True, "subject": subject, "title": title, "count": len(results),
        "limit_applied": limit, "truncated": lib.paper_summary(subject, title, limit=10**6)["count"] > len(results),
        "total_score": round(full_total, 2),
        "score": round(got, 2),
        "correct": correct, "wrong": wrong, "pending": pending, "unanswered": unanswered,
        "accuracy": round(correct / judged, 4) if judged else 0.0,
        "per_type": per_type, "results": results,
        "progress": recompute_today_progress(),
        "note": "规则判分当场出分；标 pending 的是写作/整段翻译，走 AI 判分（/api/judge_one 或 /api/sync）。",
    })


def _ensure_attempts_db():
    """确认 attempts 库可写；返回错误信息（可写则返回空串）。"""
    conn = open_db("attempts", write=True)
    if conn is None:
        return f"attempts 库不存在: {db_path('attempts')}"
    try:
        if not table_exists(conn, "attempts") or not table_exists(conn, "judge_queue"):
            return "attempts 库缺 attempts/judge_queue 表（先跑 scripts/init_db.py）"
    finally:
        conn.close()
    return ""


def _try_write_attempt(attempt_id: str, uid: str, subject: str, user_answer: str,
                       source_type: str, elapsed_ms: int = 0) -> bool:
    """写一条 attempt + judge_queue(pending)；失败返回 False（不抛，交卷不能被单题打断）。"""
    conn = open_db("attempts", write=True)
    if conn is None:
        return False
    ts = now_iso()
    try:
        conn.execute(
            "INSERT INTO attempts(attempt_id, question_uid, subject, user_answer, judge_score, "
            "judge_model, judge_reason, judge_prompt_version, elapsed_ms, synced, source_type, created_at) "
            "VALUES(?,?,?,?,NULL,NULL,NULL,NULL,?,0,?,?)",
            (attempt_id, uid, subject, user_answer, elapsed_ms, source_type, ts))
        conn.execute(
            "INSERT INTO judge_queue(attempt_id, subject, question_uid, user_answer, judge_score, "
            "judge_model, judge_reason, judge_status, batch_id, submitted_at, source_type, created_at) "
            "VALUES(?,?,?,?,NULL,NULL,NULL,'pending',NULL,NULL,?,?)",
            (attempt_id, subject, uid, user_answer, source_type, ts))
        conn.commit()
        return True
    except sqlite3.Error:
        conn.rollback()
        return False
    finally:
        conn.close()


@app.route("/api/ingest", methods=["POST", "OPTIONS"])
def api_ingest():
    """**抓取收件箱**（需求 13 用）：把浏览器里抓到的一批题目落到 `inbox/_ingest/<name>.jsonl`。

    为什么需要它：抓考试宝的题目时，数据是在**浏览器页面里**产生的（站点有 JS 机器人挑战，
    Node 直连拿不到）。若让数据经模型上下文传回来，144 题会吃掉大量 token；
    由页面直接 POST 到本机接口落盘，**数据不经过模型**，既省又准。

    ⚠️ 安全边界：
      - 只允许写入 `inbox/_ingest/` 下、文件名只含 `[A-Za-z0-9._-]`；
      - 只接受 JSON 数组或 `{"rows": [...]}`，单批上限 2000 条；
      - 是**本地收集口**，不参与做题逻辑（`/api` 里唯一会往数据目录外写文件的接口）。
    """
    if request.method == "OPTIONS":            # 跨源预检（浏览器页面在别的域名上）
        resp = app.make_default_options_response()
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        resp.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        return resp

    body = request.get_json(silent=True)
    name = str(request.args.get("name") or (body.get("name") if isinstance(body, dict) else "") or "batch").strip()
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,40}", name):
        return jsonify({"error": "name 只允许字母数字._-（≤40 字符）"}), 400
    rows = body if isinstance(body, list) else (body or {}).get("rows")
    if not isinstance(rows, list):
        return jsonify({"error": 'POST body 需为 JSON 数组或 {"rows": [...]}'}), 400
    if len(rows) > 2000:
        return jsonify({"error": f"单批上限 2000 条（收到 {len(rows)}）"}), 400

    target_dir = ROOT / "inbox" / "_ingest"
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"{name}.jsonl"
    with path.open("a", encoding="utf-8") as fh:
        for row in rows:
            if isinstance(row, dict):
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    resp = jsonify({"ok": True, "appended": len(rows), "file": str(path)})
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp


@app.route("/api/settings/api_key", methods=["POST"])
def api_settings_api_key():
    """保存/清空 API key（需求 9）：写项目根 `.env` 的 `DEEPSEEK_API_KEY`。

    - `{"api_key": "sk-..."}` → 写入；`{"api_key": ""}` → **删除该行**（清空）；
    - **只由用户点按钮触发**（前端无 oninput/onblur 自动保存）；
    - 响应只回 `api_key_configured` + 掩码，**永不回显完整 key**；
    - 非法值（含换行/NUL、超长、明显不是 key）→ 400，且不写文件。
    """
    body = json_body()
    raw = body.get("api_key")
    if raw is None:
        return jsonify({"error": "缺少 api_key 字段（传空字符串表示清空）"}), 400
    value = str(raw).strip()
    if value:
        if len(value) > 200:
            return jsonify({"error": f"API key 过长（{len(value)} 字符），请检查是否粘贴错了"}), 400
        if any(ch in value for ch in ("\n", "\r", "\x00")):
            return jsonify({"error": "API key 不能包含换行"}), 400
        if any(ch.isspace() for ch in value):
            return jsonify({"error": "API key 不能包含空格"}), 400
        # 只挡明显粘贴错的（HTTP 头/JWT/说明文字）；不强行要求 sk- 前缀，
        # 因为用户可配自定义 BASE_URL（中转站 key 未必以 sk- 开头）。
        if re.search(r"[\u4e00-\u9fff]", value):
            return jsonify({"error": "API key 里出现了中文，看着像把说明文字粘进来了"}), 400
        if len(value) < 8:
            return jsonify({"error": f"API key 太短（{len(value)} 字符），请检查是否复制完整"}), 400
    try:
        env_file = write_env_value("DEEPSEEK_API_KEY", value)
    except (OSError, ValueError) as exc:
        return jsonify({"error": f"写入 .env 失败: {exc}"}), 500
    return jsonify({"ok": True, "api_key_configured": bool(value), "api_key_hint": mask_secret(value),
                    "env_file": str(env_file)})


@app.route("/api/settings/base_url", methods=["POST"])
def api_settings_base_url():
    """可选：保存自定义 `DEEPSEEK_BASE_URL`（留空＝删除，回到官方 `https://api.deepseek.com`）。"""
    body = json_body()
    if "base_url" not in body:
        return jsonify({"error": "缺少 base_url 字段（传空字符串表示恢复默认）"}), 400
    value = str(body.get("base_url") or "").strip().rstrip("/")
    if value and not value.startswith(("http://", "https://")):
        return jsonify({"error": "base_url 必须以 http:// 或 https:// 开头"}), 400
    try:
        write_env_value("DEEPSEEK_BASE_URL", value)
    except (OSError, ValueError) as exc:
        return jsonify({"error": f"写入 .env 失败: {exc}"}), 500
    return jsonify({"ok": True, "base_url": value or None, "base_url_configured": bool(value)})


@app.route("/review", methods=["GET"])
def page_review():
    subject = request.args.get("subject") or ""
    idx = as_int(request.args.get("idx"), 0, lo=0) or 0
    items = review_queue(subject or None)
    total = len(items)
    if total and idx >= total:
        idx = total - 1
    item = items[idx] if total else None
    return render_template(
        "review.html", page="review", nav=_nav("review"), item=item, items=items,
        idx=idx, total=total, subject=subject, subject_labels=subject_labels(),
        reject_reasons=REJECT_REASONS, decision_map=DECISION_TO_STATUS,
    )


@app.route("/history", methods=["GET"])
def page_history():
    """判分记录：把「我做过哪些题、判了多少分、正确答案是什么」一屏看完。

    用户反馈：用 API 判分后**找不到判完分的题目** —— 因为旧接口只回作答记录、不带题干。
    本页直接读 /api/attempts 的同一份数据（含题干/题型/参考答案/判分理由）。
    """
    subject = request.args.get("subject") or ""
    return render_template("history.html", page="history", nav=_nav("history"),
                           subject=subject, subject_labels=subject_labels(),
                           subjects=SUBJECTS, types=display_meta().get("types", {}))


# ============================================================== API


# ============================================================== 英语译文 / 点词查义
# 数据源 `data/english_zh.sqlite`（由 `scripts/build_english_zh.py` 一次性预生成）：
#   translations(doc_key, kind, source, zh, ...)  doc_key = "m:<材料 sha1 前16位>" / "s:<question_uid>"
#   glossary(word, pos, zh)
# 设计要点：**运行时只读本地 sqlite**，点击不联网、不计费、毫秒级返回。
ZH_DB_FILE = "english_zh.sqlite"


def open_zh_db(write: bool = False):
    """英语译文/词表库（只读）。文件不存在时返回 None，接口据此降级。"""
    path = DATA_DIR / ZH_DB_FILE
    if not path.exists():
        return None
    try:
        if write:
            conn = sqlite3.connect(str(path))
        else:
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error:
        return None


# 点词查不到时的词形还原候选（够覆盖专升本阅读里 90% 的变形）
_LEMMA_RULES = (
    ("ies", "y"), ("ied", "y"), ("ying", "y"),
    ("es", ""), ("ed", ""), ("ing", ""), ("er", ""), ("est", ""),
    ("s", ""), ("ly", ""), ("d", ""),
)


def lemma_candidates(word: str) -> list[str]:
    """按常见后缀生成还原候选（不追求语言学完备，只求点得动）。"""
    out = [word]
    for suf, rep in _LEMMA_RULES:
        if len(word) > len(suf) + 2 and word.endswith(suf):
            base = word[: -len(suf)] + rep
            if base not in out:
                out.append(base)
    # 双写辅音（stopped → stop）
    if len(word) > 3 and word[-1] == word[-2] and word[-1] not in "aeiou":
        cand = word[:-1]
        if word.endswith(("ed", "ing", "er", "est")) and cand not in out:
            out.append(cand)
    return out


@app.route("/api/dict", methods=["GET"])
def api_dict():
    """点词查义：`/api/dict?w=trees` → {found, word, lemma, pos, zh}。纯本地查询。"""
    raw = (request.args.get("w") or "").strip()
    word = re.sub(r"[^A-Za-z'-]", "", raw).lower()
    if not word or len(word) > 40:
        return jsonify({"found": False, "error": "单词不合法"}), 400
    conn = open_zh_db()
    if conn is None:
        return jsonify({"found": False, "word": word, "error": "词表未生成（缺 data/english_zh.sqlite）"}), 404
    try:
        for cand in lemma_candidates(word):
            row = conn.execute("SELECT pos, zh FROM glossary WHERE word=?", (cand,)).fetchone()
            if row:
                return jsonify({"found": True, "word": word, "lemma": cand,
                                "pos": row["pos"] or "", "zh": row["zh"] or ""})
    finally:
        conn.close()
    return jsonify({"found": False, "word": word})


@app.route("/api/translate", methods=["GET"])
def api_translate():
    """整段译文：`/api/translate?subject=english&uid=<question_uid>`。

    返回 `{material_zh, stem_zh}`（没生成/没收录的为 None，前端据此隐藏按钮）。
    材料按**内容哈希**存——同一篇短文被多个小题共享，天然只存一份。
    """
    subject = request.args.get("subject") or "english"
    uid = request.args.get("uid") or ""
    if subject not in SUBJECTS:
        return jsonify({"error": f"未知科目: {subject}", "subjects": list(SUBJECTS)}), 400
    if not uid:
        return jsonify({"error": "缺 uid"}), 400

    out: dict = {"uid": uid, "material_zh": None, "stem_zh": None}
    qconn = open_db(subject)
    if qconn is not None:
        try:
            row = qconn.execute("SELECT stem, material_text FROM questions WHERE question_uid=?",
                                (uid,)).fetchone()
        finally:
            qconn.close()
    else:
        row = None

    zh = open_zh_db()
    if zh is not None:
        try:
            if row is not None:
                mat = row["material_text"] or ""
                if mat:
                    key = "m:" + hashlib.sha1(mat.encode("utf-8")).hexdigest()[:16]
                    hit = zh.execute("SELECT zh FROM translations WHERE doc_key=?", (key,)).fetchone()
                    if hit:
                        out["material_zh"] = hit["zh"]
            hit = zh.execute("SELECT zh FROM translations WHERE doc_key=?", ("s:" + uid,)).fetchone()
            if hit:
                out["stem_zh"] = hit["zh"]
        finally:
            zh.close()
    return jsonify(out)


def wrong_question_uids(subject: str = "") -> list[str]:
    """「刷错题」用的 uid 白名单：判分记录里判**错**的题（判分中的不算错）。

    为什么要它：判分记录页要能"一键只刷错题"，而 /api/questions 的筛选条件都是按题目
    字段（题型/知识点/来源）组合的，错题是**作答历史**的属性，题目表里没有，只能现查 attempts。
    """
    conn = open_db("attempts")
    if conn is None:
        return []
    try:
        if not table_exists(conn, "attempts"):
            return []
        rows = conn.execute(
            "SELECT question_uid, subject, judge_score FROM attempts "
            "WHERE judge_score IS NOT NULL ORDER BY created_at DESC").fetchall()
    except sqlite3.Error:
        return []
    finally:
        conn.close()
    seen: set[str] = set()
    out: list[str] = []
    for r in rows:
        subj = str(r["subject"] or "")
        if subject and subj != subject:
            continue
        try:
            if judge_correct(subj, r["judge_score"]):
                continue
        except Exception:  # noqa: BLE001
            pass
        uid = str(r["question_uid"] or "")
        if uid and uid not in seen:
            seen.add(uid)
            out.append(uid)
    return out


@app.route("/api/questions", methods=["GET"])
def api_questions():
    """题目列表（刷题页数据源）。

    每条记录除既有字段外，**新增三个解释展示字段**（见 `explanation_policy()`）:
      - `show_explanation` (bool)：True = 该题来源是真题/教材真题，可以展示解释；
      - `explanation_source` (str)：来源中文名（真题两个取值固定为「官方真题」「教材/校考真题」，
        其余查 `config/display.json:trust_levels`）；
      - `explanation_hidden_reason` (str)：不展示时的原因，展示时为空串。

    ⚠️ `explanation` 正文的返回逻辑**完全不变**（`reveal=1` 返回，`reveal≠1` 仍然 pop 掉）——
    过滤是前端/展示层的事，接口照样把数据给到，这样「只看真题」的开关随时能打开。

    Query 开关（默认 `real` = 只在真题显示）:
      - `explain_policy=all`（等价写法 `include_generated_explain=1`）→ 放开，
        此时每条记录 `show_explanation` 恒为 True（`explanation_hidden_reason` 为空串）。
    """
    subject = request.args.get("subject") or ""
    qtype = request.args.get("type") or ""
    status = request.args.get("status") or ""
    knowledge_point = request.args.get("kp") or ""
    difficulty = request.args.get("difficulty") or ""
    # 「模拟题」专区用：按题库名（exam_title）切一个子集，如 exam=考试宝预览
    exam = request.args.get("exam") or ""
    # 来源可信度筛选（用户要"严格参考真题"，必须能只练真题）
    trust = request.args.get("trust") or ""
    # 用户要求：每次打开刷题从**随机**的题开始（否则永远从第一题开始）
    shuffle = as_bool(request.args.get("shuffle"), False)
    # 刷错题：只出「判分记录里判过错」的题（判分记录页「刷错题」按钮带过来的）
    wrong_only = as_bool(request.args.get("wrong"), False)
    limit = as_int(request.args.get("limit"), DEFAULT_LIMIT, lo=0, hi=MAX_PAGE_LIMIT)
    reveal = as_bool(request.args.get("reveal"), False)
    # 解释展示开关（默认 real：只在真题显示；`explain_policy=all` 才放开非真题）
    explain_all = explain_show_all()
    if subject and subject not in SUBJECTS:
        return jsonify({"error": f"未知科目: {subject}", "subjects": list(SUBJECTS)}), 400
    if status and status not in QUESTION_STATUSES:
        return jsonify({"error": f"未知 status: {status}", "allowed": list(QUESTION_STATUSES)}), 400

    # 来源中文名只读一次盘（每条题都调 `display_meta()` 会白读几百次 JSON）
    trust_labels = display_meta().get("trust_levels") or {}
    out: list[dict] = []
    for subj in iter_subjects(subject):
        conn = open_db(subj)
        if conn is None:
            continue
        try:
            if not table_exists(conn, "questions"):
                continue
            sql = ("SELECT question_uid, subject, school, year, source_type, source_url, source_credit, "
                   "chapter, knowledge_point, syllabus_ref, question_type, stem, options, answer, explanation, "
                   "difficulty, status, version, fact_claim, fact_source, fact_verified, quality_score, "
                   # 整块题所需：同篇短文的题共享 material_text + group_uid（用户要求"整块不要拆开"）
                   "group_uid, material_text, trust_level, exam_title "
                   "FROM questions WHERE 1=1")
            params: list = []
            if qtype:
                sql += " AND question_type=?"
                params.append(qtype)
            if status:
                sql += " AND status=?"
                params.append(status)
            else:
                # 去重口径（scripts/dedupe_questions.py）：重复题被标成 archived 后
                # **默认不进刷题池**，否则「去重」只改了数据、页面照样重复。
                # 显式 `status=archived` 仍可查到（体检/回滚时要用）。
                sql += " AND status<>'archived'"
            if knowledge_point:
                sql += " AND knowledge_point=?"
                params.append(knowledge_point)
            if difficulty:
                sql += " AND difficulty=?"
                params.append(difficulty)
            if exam:
                # 「模拟题」卡片：只要某个题库（exam_title）里的题
                sql += " AND COALESCE(exam_title,'') LIKE ?"
                params.append(f"%{exam}%")
            if trust == "real":
                # 快捷开关：只要真题/教材题（排除 AI 生成与第三方）
                sql += " AND (trust_level IN ('official_exam','textbook','acp') " \
                       "OR source_type='real_exam')"
            elif trust == "generated":
                # 快捷开关：只要 AI 生成的题
                sql += " AND (trust_level='ai_generated' OR source_type='generate')"
            elif trust:
                sql += " AND trust_level=?"
                params.append(trust)
            elif subject == "aca_llm":
                # 用户要求：ACA 刷题里**不要再混进 ACP 的题**（ACP 是另一个认证，走拓展专区）
                sql += " AND (trust_level IS NULL OR trust_level<>'acp')"
            if wrong_only:
                # 刷错题：uid 白名单来自 attempts 库（判错的那些），再叠加其它筛选条件
                wuids = wrong_question_uids(subj)
                if not wuids:
                    continue
                sql += " AND question_uid IN (%s)" % ",".join("?" * len(wuids))
                params.extend(wuids)
            # 用户要求"每次打开可以随机"：shuffle=1 时打乱（刷题页默认开）
            sql += " ORDER BY RANDOM()" if shuffle else " ORDER BY id"
            wrong = {}
            if table_exists(conn, "wrong_book"):
                for row in conn.execute("SELECT question_uid, wrong_count, next_review_at, mastery FROM wrong_book"):
                    wrong[row["question_uid"]] = dict(row)
            for row in conn.execute(sql, params):
                rec = dict(row)
                rec["options_parsed"] = parse_options(rec.get("options"))
                wb = wrong.get(rec["question_uid"]) or {}
                rec["wrong_count"] = int(wb.get("wrong_count") or 0)
                rec["next_review_at"] = wb.get("next_review_at")
                rec["mastery"] = int(wb.get("mastery") or 0)
                due_at = parse_ts(rec["next_review_at"])
                rec["due"] = bool(due_at is not None and due_at <= datetime.now(timezone.utc))
                # 选项：`options` 列为空时从题干解析（见 runtime_options 注释）
                rec["options_parsed"] = runtime_options(rec)
                rec["objective"] = is_objective(rec.get("question_type"), rec["options_parsed"], rec.get("answer"))
                # 选项字母集合只对客观题有意义（主观题的 answer 是文本，抽字母会得到噪声）
                rec["answer_keys"] = answer_keys(rec.get("answer"), rec.get("stem")) if rec["objective"] else ""
                # 解释展示策略（只加字段，不动 explanation 正文的 reveal 逻辑）
                rec.update(explanation_fields(rec.get("trust_level"), trust_labels, explain_all))
                if not reveal:
                    rec.pop("answer", None)
                    rec.pop("explanation", None)
                out.append(rec)
        finally:
            conn.close()
        if len(out) >= limit:
            break
    out = out[:limit]
    return jsonify({"count": len(out), "limit": limit, "questions": out,
                    "explain_policy": "all" if explain_all else "real"})


@app.route("/api/attempts", methods=["GET"])
def api_attempts():
    subject = request.args.get("subject") or ""
    date_str = request.args.get("date") or ""
    limit = as_int(request.args.get("limit"), 200, lo=0, hi=2000)
    if subject and subject not in SUBJECTS:
        return jsonify({"error": f"未知科目: {subject}", "subjects": list(SUBJECTS)}), 400
    conn = open_db("attempts")
    if conn is None:
        return jsonify({"count": 0, "attempts": [], "db": str(db_path("attempts"))})
    try:
        if not table_exists(conn, "attempts"):
            return jsonify({"count": 0, "attempts": []})
        sql = ("SELECT a.*, q.judge_status, q.submitted_at FROM attempts a "
               "LEFT JOIN judge_queue q ON q.attempt_id = a.attempt_id WHERE 1=1")
        params: list = []
        if subject:
            sql += " AND a.subject=?"
            params.append(subject)
        sql += " ORDER BY a.created_at DESC"
        rows = rows_to_dicts(conn.execute(sql, params))
    finally:
        conn.close()
    if date_str:
        rows = [r for r in rows if local_date(r.get("created_at")) == date_str]
    rows = rows[:limit]

    # 🔴 补齐题干 / 题型中文名 / 参考答案 / 判分理由
    # 用户反馈原话：「我用 api 判分后没办法很快找到判完分的题目」——
    # 只返回作答记录（uid + 分数）是没用的，必须把题目内容一起带回来。
    disp = display_meta()
    qcache: dict[str, dict] = {}
    subj_conns: dict = {}
    try:
        for r in rows:
            subj = r.get("subject") or ""
            uid = r.get("question_uid") or ""
            r["correct"] = judge_correct(subj, r.get("judge_score"))
            r["subject_label"] = (disp.get("subject_names") or {}).get(subj) or subj
            info: dict = {}
            if uid:
                key = f"{subj}|{uid}"
                if key not in qcache:
                    found: dict = {}
                    c = subj_conns.get(subj)
                    if c is None:
                        c = open_db(subj)
                        subj_conns[subj] = c
                    if c is not None and table_exists(c, "questions"):
                        row = c.execute(
                            "SELECT stem, question_type, answer, explanation, knowledge_point, difficulty, "
                            "COALESCE(options,'') AS options, COALESCE(material_text,'') AS material_text "
                            "FROM questions WHERE question_uid=?", (uid,)).fetchone()
                        if row:
                            found = dict(row)
                    qcache[key] = found
                info = qcache[key]
            for k in ("stem", "answer", "explanation", "knowledge_point", "difficulty", "material_text"):
                r[k] = (info.get(k) or "")
            # 判分记录页也要能对照选项看错在哪（用户报「我之前作答的还是看不到选项」）：
            # 这里按 uid 现查，**历史记录同样生效**，不需要重新作答。
            r["options_parsed"] = runtime_options({"options": info.get("options") or "",
                                                   "stem": info.get("stem") or ""})
            r["answer_keys"] = answer_keys(info.get("answer"), info.get("stem"))
            r["objective"] = is_objective(info.get("question_type"), r["options_parsed"], info.get("answer"))
            qt = info.get("question_type") or ""
            r["question_type"] = qt
            r["type_name"] = ((disp.get("types") or {}).get(qt) or {}).get("name") or qt or "未标题型"
    finally:
        for c in subj_conns.values():
            try:
                c.close()
            except Exception:  # noqa: BLE001
                pass
    return jsonify({"count": len(rows), "attempts": rows})


@app.route("/api/attempts/delete", methods=["POST"])
def api_attempts_delete():
    """删判分记录（用户要求：「判分记录中也可以删掉记录」）。

    三种删法（前端都有二次确认）：
      - `attempt_ids: ["..."]` → 只删这几条；
      - `date: "2026-10-24"` / `"today"` → 删该日全部（可再加 `subject` 限定）；
      - `all: true` → 清空（危险操作）。
    同时删 `judge_queue` 里挂着的同一 attempt（否则判分队列还留着可重试的壳），
    删完立刻用**同一套聚合口径**重算当日 `daily_progress`，首页"今日进度"不会虚高。
    """
    body = json_body()
    ids = [str(x) for x in (body.get("attempt_ids") or []) if str(x).strip()]
    date_str = str(body.get("date") or "").strip()
    wipe = bool(body.get("all"))
    subject = str(body.get("subject") or "").strip()
    # only=correct / wrong：按判分对错筛选（配「刷完错题后清掉已掌握的记录」用）
    only = str(body.get("only") or "").strip()
    if only and only not in ("correct", "wrong"):
        return jsonify({"error": "only 只支持 correct / wrong"}), 400
    if subject and subject not in SUBJECTS:
        return jsonify({"error": f"未知科目: {subject}", "subjects": list(SUBJECTS)}), 400
    if not ids and not date_str and not wipe and not only:
        return jsonify({"error": "需要 attempt_ids / date / all / only 之一"}), 400
    if date_str == "today":
        date_str = today_local()

    conn = open_db("attempts", write=True)
    if conn is None:
        return jsonify({"error": "attempts 库打不开"}), 500
    removed = 0
    try:
        if not table_exists(conn, "attempts"):
            return jsonify({"removed": 0, "attempts": []})
        rows = conn.execute(
            "SELECT attempt_id, subject, created_at, judge_score FROM attempts").fetchall()
        targets: list[str] = []
        for r in rows:
            aid = str(r["attempt_id"] or "")
            if ids:
                if aid not in ids:
                    continue
            else:
                if subject and (r["subject"] or "") != subject:
                    continue
                if date_str and local_date(r["created_at"]) != date_str:
                    continue
                if only:
                    if r["judge_score"] is None:
                        continue
                    try:
                        ok = judge_correct(r["subject"] or "", r["judge_score"])
                    except Exception:  # noqa: BLE001
                        continue
                    if (only == "correct") != bool(ok):
                        continue
            targets.append(aid)
        has_q = table_exists(conn, "judge_queue")
        for aid in targets:
            conn.execute("DELETE FROM attempts WHERE attempt_id=?", (aid,))
            if has_q:
                conn.execute("DELETE FROM judge_queue WHERE attempt_id=?", (aid,))
        conn.commit()
        removed = len(targets)
    except sqlite3.Error as exc:
        return jsonify({"error": f"删除失败: {exc}"}), 500
    finally:
        conn.close()
    return jsonify({"removed": removed, "progress": recompute_today_progress()})


@app.route("/api/progress", methods=["GET"])
def api_progress():
    raw = request.args.get("date") or "today"
    date_str = today_local() if raw in ("today", "", "now") else raw
    if len(date_str) != 10:
        return jsonify({"error": "date 需为 today 或 YYYY-MM-DD", "got": raw}), 400
    return jsonify(progress_payload(date_str))


@app.route("/api/papers", methods=["GET"])
def api_papers():
    papers = list_papers()
    return jsonify({"count": len(papers), "dir": str(OUTPUT_DIR / "papers"), "papers": papers})


@app.route("/api/queue", methods=["GET"])
def api_queue():
    status = request.args.get("status") or ""
    if status and status not in JUDGE_STATUSES:
        return jsonify({"error": f"未知 judge_status: {status}", "allowed": list(JUDGE_STATUSES)}), 400
    limit = as_int(request.args.get("limit"), 200, lo=1, hi=1000)
    return jsonify({"counts": current_queue_counters(), "statuses": list(JUDGE_STATUSES),
                    "rows": queue_rows(status or None, limit)})


@app.route("/api/reveal", methods=["GET"])
def api_reveal():
    """取单题答案与解析（答题后展示解析用）。

    ⚠️ 与 `/api/questions` 同一口径：**解释是否展示由前端按 `show_explanation` 决定**，
    本接口**不会**因为策略而不返回 `explanation`（数据照给，只多三个字段）:
      - `show_explanation` (bool) / `explanation_source` (str) / `explanation_hidden_reason` (str)。

    Query 开关与 `/api/questions` 完全一致：`explain_policy=all`
    （或 `include_generated_explain=1`）→ `show_explanation` 恒为 True。
    """
    uid = request.args.get("question_uid") or ""
    subject = request.args.get("subject") or ""
    explain_all = explain_show_all()
    if not uid or subject not in SUBJECTS:
        return jsonify({"error": "需要 question_uid + 合法 subject"}), 400
    conn = open_db(subject)
    if conn is None:
        return jsonify({"error": f"科目库不存在: {subject}"}), 404
    try:
        row = conn.execute("SELECT answer, explanation, options, trust_level FROM questions "
                           "WHERE question_uid=?", (uid,)).fetchone()
    finally:
        conn.close()
    if row is None:
        return jsonify({"error": "题目不存在"}), 404
    payload = {"question_uid": uid, "subject": subject, "answer": row["answer"],
               "explanation": row["explanation"], "options": parse_options(row["options"]),
               "explain_policy": "all" if explain_all else "real"}
    payload.update(explanation_fields(row["trust_level"], None, explain_all))
    return jsonify(payload)


@app.route("/api/submit", methods=["POST"])
def api_submit():
    """写 `attempts` + `judge_queue`，**能规则判分的就地判完**（需求 2）。

    - 规则判得了（客观题/填空/连词成句/C 短输出…）→ `judge_status='synced'`，
      当场返回 `judge_score`/`judge_reason`/`correct`，并立刻重算当日进度（需求 10）；
    - 规则判不了（写作/整段翻译/论述题）→ 仍入队 `pending`，由 `/api/judge_one`（付费 AI）
      或 `/api/sync` 处理，行为与改动前一致。
    """
    body = json_body()
    uid = str(body.get("question_uid") or "").strip()
    subject = str(body.get("subject") or "").strip()
    user_answer = body.get("user_answer")
    if isinstance(user_answer, (list, tuple)):
        user_answer = "".join(str(x) for x in user_answer)
    user_answer = str(user_answer or "")
    elapsed_ms = as_int(body.get("elapsed_ms"), 0, lo=0, hi=86_400_000) or 0
    no_local = as_bool(body.get("no_local_judge"), False)
    if not uid:
        return jsonify({"error": "缺少 question_uid"}), 400
    if subject not in SUBJECTS:
        return jsonify({"error": f"未知科目: {subject!r}", "subjects": list(SUBJECTS)}), 400

    attempt_id = "att-{}-{}".format(datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"), uuid.uuid4().hex[:8])
    ts = now_iso()
    warning = ""
    sconn = open_db(subject)
    if sconn is None:
        warning = f"科目库不存在: {subject}"
    else:
        try:
            if table_exists(sconn, "questions"):
                hit = sconn.execute("SELECT 1 FROM questions WHERE question_uid=?", (uid,)).fetchone()
                if hit is None:
                    warning = "题目不在该科目库中（attempt 仍已记录）"
            else:
                warning = "questions 表不存在"
        finally:
            sconn.close()

    conn = open_db("attempts", write=True)
    if conn is None:
        return jsonify({"error": f"attempts 库不存在: {db_path('attempts')}"}), 500
    try:
        conn.execute(
            "INSERT INTO attempts(attempt_id, question_uid, subject, user_answer, judge_score, judge_model, "
            "judge_reason, judge_prompt_version, elapsed_ms, synced, source_type, created_at) "
            "VALUES(?,?,?,?,NULL,NULL,NULL,NULL,?,0,'ui',?)",
            (attempt_id, uid, subject, user_answer, elapsed_ms, ts),
        )
        conn.execute(
            "INSERT INTO judge_queue(attempt_id, subject, question_uid, user_answer, judge_score, judge_model, "
            "judge_reason, judge_status, batch_id, submitted_at, source_type, created_at) "
            "VALUES(?,?,?,?,NULL,NULL,NULL,'pending',NULL,NULL,'ui',?)",
            (attempt_id, subject, uid, user_answer, ts),
        )
        conn.commit()
    except sqlite3.Error as exc:
        conn.rollback()
        return jsonify({"error": f"写库失败: {exc}"}), 500
    finally:
        conn.close()

    payload = {"attempt_id": attempt_id, "status": "pending", "subject": subject,
               "question_uid": uid, "created_at": ts}
    if warning:
        payload["warning"] = warning

    # ---- 规则判分（本地、零成本、即时）----
    if not no_local:
        verdict = apply_local_verdict(subject, uid, attempt_id, user_answer)
        if verdict is not None:
            payload["local_judge"] = verdict
            if verdict.get("gradeable"):
                payload["status"] = "synced"
                payload["judge_score"] = verdict.get("judge_score")
                payload["full_score"] = verdict.get("full_score")
                payload["judge_model"] = verdict.get("judge_model")
                payload["judge_reason"] = verdict.get("judge_reason")
                payload["correct"] = verdict.get("correct")
                payload["judged_by"] = "local_rule"
            else:
                payload["judge_reason"] = verdict.get("reason")
                payload["judged_by"] = "pending_ai"
    return jsonify(payload), 201


@app.route("/api/judge_local", methods=["POST"])
def api_judge_local():
    """**规则判分通道**（需求 2）：对已存在的 attempt 就地判分，零联网零计费。

    两种用法：
      - `{"attempt_id": "att-..."}`：判这一条（刷题页提交后立刻出分用）；
      - `{"limit": 200}` / `{"subject": "english"}`：批量补判历史 `pending`/`submitted` 的
        规则可判题（LLM 判分上线前积压的队列，一次补完，不花钱）。
    返回 `local_judge` 字段与 `/api/submit` 里的同构。
    """
    body = json_body()
    attempt_id = str(body.get("attempt_id") or "").strip()
    subject = str(param("subject") or "").strip()
    limit = as_int(param("limit", None), None, lo=1, hi=2000)
    if subject and subject not in SUBJECTS:
        return jsonify({"error": f"未知科目: {subject!r}", "subjects": list(SUBJECTS)}), 400

    if attempt_id:
        targets = [{"attempt_id": attempt_id}]
    else:
        conn = open_db("attempts")
        if conn is None:
            return jsonify({"error": "attempts 库不存在"}), 500
        try:
            sql = ("SELECT attempt_id, subject, question_uid, user_answer FROM judge_queue "
                   "WHERE judge_status IN ('pending','submitted')")
            params: list = []
            if subject:
                sql += " AND subject=?"
                params.append(subject)
            sql += " ORDER BY id"
            if limit:
                sql += " LIMIT ?"
                params.append(limit)
            targets = [dict(r) for r in conn.execute(sql, params)]
        finally:
            conn.close()

    results: list[dict] = []
    synced = skipped = 0
    for rec in targets:
        row = dict(rec)
        if "subject" not in row or "question_uid" not in row:
            conn = open_db("attempts")
            if conn is None:
                break
            try:
                got = conn.execute("SELECT subject, question_uid, user_answer FROM attempts WHERE attempt_id=?",
                                   (row["attempt_id"],)).fetchone()
            finally:
                conn.close()
            if got is None:
                results.append({"attempt_id": row["attempt_id"], "error": "attempt 不存在"})
                continue
            row.update(dict(got))
        verdict = apply_local_verdict(str(row["subject"]), str(row["question_uid"]),
                                      str(row["attempt_id"]), str(row.get("user_answer") or ""))
        if verdict is None:
            results.append({"attempt_id": row["attempt_id"], "gradeable": False,
                            "reason": "题目不在库中或规则判分模块不可用"})
            skipped += 1
            continue
        item = {"attempt_id": row["attempt_id"], "subject": row["subject"],
                "question_uid": row["question_uid"], **verdict}
        results.append(item)
        synced += 1 if verdict.get("gradeable") else 0
        skipped += 0 if verdict.get("gradeable") else 1
    return jsonify({"ok": True, "count": len(results), "synced": synced, "pending_ai": skipped,
                    "results": results})


@app.route("/api/requeue", methods=["POST"])
def api_requeue():
    """`failed` 手动重投：置回 `pending`（`force=true` 可重投任意态）。"""
    body = json_body()
    attempt_id = str(body.get("attempt_id") or "").strip()
    force = as_bool(body.get("force"), False)
    if not attempt_id:
        return jsonify({"error": "缺少 attempt_id"}), 400
    conn = open_db("attempts", write=True)
    if conn is None:
        return jsonify({"error": "attempts 库不存在"}), 500
    try:
        row = conn.execute("SELECT judge_status FROM judge_queue WHERE attempt_id=?", (attempt_id,)).fetchone()
        if row is None:
            return jsonify({"error": f"队列中无此 attempt_id: {attempt_id}"}), 404
        current = str(row["judge_status"])
        if current != "failed" and not force:
            return jsonify({"error": f"仅 failed 可重投（当前 {current}）；如需强制请传 force=true",
                            "judge_status": current}), 400
        conn.execute(
            "UPDATE judge_queue SET judge_status='pending', submitted_at=NULL, "
            "judge_reason=COALESCE(judge_reason,'') || ? WHERE attempt_id=?",
            (f"\n[手动重投 {now_iso()}] 上次状态={current}", attempt_id),
        )
        conn.commit()
    finally:
        conn.close()
    return jsonify({"ok": True, "attempt_id": attempt_id, "from": current, "status": "pending"})


@app.route("/api/sync", methods=["POST", "GET"])
def api_sync():
    """子进程调用 `scripts/sync_outbox.py`，默认 `--mock`（零联网零花费）。"""
    mock = as_bool(param("mock", True), True)
    confirm_paid = as_bool(param("confirm_paid", False), False)
    if not mock and not confirm_paid:
        return jsonify({
            "error": "真实判分会调用付费 API；请显式传 mock=true，或 mock=false + confirm_paid=true 确认",
            "paid_gate": True,
        }), 400
    script = Path(SYNC_SCRIPT)
    if not script.exists():
        return jsonify({"error": f"找不到 {script}"}), 500
    cmd = [sys.executable, str(script)]
    if mock:
        cmd.append("--mock")
    limit = as_int(param("limit", None), None, lo=1, hi=1000)
    if limit:
        cmd += ["--limit", str(limit)]
    subject = param("subject", None)
    if subject in SUBJECTS:
        cmd += ["--subject", str(subject)]
    dry = as_bool(param("dry_run", False), False)
    if dry:
        cmd.append("--dry-run")

    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=900, cwd=str(ROOT), env=env)
    except subprocess.TimeoutExpired:
        return jsonify({"error": "sync_outbox.py 超时（900s）", "cmd": cmd}), 504
    result = _extract_json(proc.stdout)
    return jsonify({
        "ok": proc.returncode == 0 and result is not None,
        "mock": mock, "returncode": proc.returncode, "cmd": cmd,
        "result": result,
        "stdout_tail": (proc.stdout or "")[-2000:],
        "stderr_tail": (proc.stderr or "")[-2000:],
    })


@app.route("/api/judge_one", methods=["POST"])
def api_judge_one():
    """**单题即时判分**：刷题页提交后当场出分。

    用户诉求原话：「我连着做 20 道主观题，当场看不到任何对错，必须切到别处触发判分再回来找」。
    这里把「提交 → 只判这一道 → 出分 + 参考答案 + 判分理由」缩成一次请求。
    ⚠️ 会真实调用付费 API，必须显式 `confirm_paid=true`（与 /api/sync 同一道付费闸门）。

    ⚠️ 本接口也回 `answer` + `explanation`，所以**同样带解释展示三字段**
    （`show_explanation` / `explanation_source` / `explanation_hidden_reason`，口径见
    `explanation_policy()`）—— 否则刷题页判完分就会把非真题的解释直接显示出来，绕过策略。
    开关同 `/api/questions`：`explain_policy=all`（或 `include_generated_explain=1`）。
    """
    body = json_body()
    attempt_id = str(body.get("attempt_id") or "").strip()
    explain_all = explain_show_all()
    if not attempt_id:
        return jsonify({"error": "缺少 attempt_id"}), 400
    if not as_bool(body.get("confirm_paid"), False):
        return jsonify({"error": "即时判分会调用付费 API；请传 confirm_paid=true", "paid_gate": True}), 400
    script = Path(SYNC_SCRIPT)
    if not script.exists():
        return jsonify({"error": f"找不到 {script}"}), 500

    cmd = [sys.executable, str(script), "--attempt-id", attempt_id]
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=300, cwd=str(ROOT), env=env)
    except subprocess.TimeoutExpired:
        return jsonify({"error": "判分超时（300s）"}), 504
    stats = _extract_json(proc.stdout) or {}

    score = reason = model = None
    subject = uid = ""
    conn = open_db("attempts")
    if conn is not None:
        try:
            if table_exists(conn, "attempts"):
                row = conn.execute("SELECT question_uid, subject, judge_score, judge_model FROM attempts "
                                   "WHERE attempt_id=?", (attempt_id,)).fetchone()
                if row:
                    uid, subject = row["question_uid"] or "", row["subject"] or ""
                    score, model = row["judge_score"], row["judge_model"]
            if table_exists(conn, "judge_queue"):
                r2 = conn.execute("SELECT judge_status, judge_reason FROM judge_queue WHERE attempt_id=?",
                                  (attempt_id,)).fetchone()
                if r2:
                    reason = r2["judge_reason"]
        finally:
            conn.close()

    answer = explanation = qtype = trust_level = ""
    c2 = open_db(subject) if subject in SUBJECTS else None
    if c2 is not None:
        try:
            if table_exists(c2, "questions"):
                q = c2.execute("SELECT answer, explanation, question_type, trust_level FROM questions "
                               "WHERE question_uid=?", (uid,)).fetchone()
                if q:
                    answer, explanation, qtype = q["answer"] or "", q["explanation"] or "", q["question_type"] or ""
                    trust_level = q["trust_level"] or ""
        finally:
            c2.close()

    full = judge_full_score(subject, qtype) if subject else None
    return jsonify({
        "ok": proc.returncode == 0 and score is not None,
        "attempt_id": attempt_id, "subject": subject, "question_uid": uid,
        "question_type": qtype, "type_name": type_label(qtype),
        "judge_score": score, "full_score": full, "judge_model": model, "judge_reason": reason,
        "correct": judge_correct(subject, score, qtype) if subject else None,
        "answer": answer, "explanation": explanation,
        "stats": stats, "stderr_tail": (proc.stderr or "")[-500:],
        # 解释展示策略：与 /api/questions、/api/reveal 同一口径（只加字段，explanation 照常返回）
        **explanation_fields(trust_level, None, explain_all),
    })


def _extract_json(text: str):
    """从子进程 stdout 里抠出最后一个 JSON 对象（脚本末尾 `json.dumps(stats, indent=2)`）。"""
    if not text:
        return None
    for i, ch in enumerate(text):
        if ch != "{":
            continue
        try:
            data = json.loads(text[i:])
        except Exception:  # noqa: BLE001
            continue
        if isinstance(data, dict):
            return data
    return None


@app.route("/review/action", methods=["POST"])
def review_action():
    """人工审核落库：通过→approved / 拒绝→rejected / 修改→保持 pending_review。

    - 写 `review_log` + `reviewed_by='human'` + `version+1`
    - 拒绝原因写 `logs/review_rejects.jsonl`
    - ⚠️ **绝不写 `config/distractors.json`**（那里只存干扰项）
    """
    body = json_body()
    uid = str(body.get("question_uid") or "").strip()
    subject = str(body.get("subject") or "").strip()
    decision = normalize_decision(body.get("decision"))
    reason_raw = body.get("reason")
    if not uid:
        return jsonify({"error": "缺少 question_uid"}), 400
    if subject not in SUBJECTS:
        return jsonify({"error": f"未知科目: {subject!r}", "subjects": list(SUBJECTS)}), 400
    if decision is None:
        return jsonify({"error": "decision 需为 通过/拒绝/修改（或 approve/reject/edit）",
                        "allowed": sorted(set(DECISION_ALIASES.values()))}), 400

    new_status = DECISION_TO_STATUS[decision]
    reason = None
    if decision == "reject":
        reason = match_reject_reason(reason_raw)
        if reason is None:
            return jsonify({"error": "拒绝必须选择原因", "allowed": list(REJECT_REASONS),
                            "got": str(reason_raw or "")}), 400

    conn = open_db(subject, write=True)
    if conn is None:
        return jsonify({"error": f"科目库不存在: {db_path(subject)}"}), 404
    try:
        row = conn.execute("SELECT status, COALESCE(version,0) FROM questions WHERE question_uid=?",
                           (uid,)).fetchone()
        if row is None:
            return jsonify({"error": f"题目不存在: {uid}", "subject": subject}), 404
        before = row[0]
        edits: list[str] = []
        params: list = [new_status]
        for field in ("stem", "answer", "explanation"):
            value = body.get(field)
            if decision == "edit" and value is not None:
                edits.append(f"{field}=?")
                params.append(str(value))
        sql = ("UPDATE questions SET status=?, reviewed_by='human', version=COALESCE(version,0)+1"
               + (", " + ", ".join(edits) if edits else "") + " WHERE question_uid=?")
        params.append(uid)
        conn.execute(sql, params)
        conn.execute(
            "INSERT INTO review_log(question_uid, reviewed_at, result) VALUES(?,?,?)",
            (uid, now_iso(), new_status),
        )
        conn.commit()
        version = conn.execute("SELECT COALESCE(version,0) FROM questions WHERE question_uid=?",
                               (uid,)).fetchone()[0]
    except sqlite3.Error as exc:
        conn.rollback()
        return jsonify({"error": f"写库失败: {exc}"}), 500
    finally:
        conn.close()

    logged = False
    if decision == "reject":
        # 拒绝原因的唯一落点（**不是** config/distractors.json）
        log_path = LOGS_DIR / "review_rejects.jsonl"
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8", newline="\n") as fh:
                fh.write(json.dumps({"ts": now_iso(), "question_uid": uid, "subject": subject,
                                     "reason": reason, "reason_raw": str(reason_raw or ""),
                                     "source": "web_ui", "from_status": before}, ensure_ascii=False) + "\n")
            logged = True
        except OSError as exc:  # 日志写失败不推翻已完成的库更新
            return jsonify({"ok": True, "status": new_status, "warnings": [f"review_rejects.jsonl 写入失败: {exc}"]})

    return jsonify({"ok": True, "question_uid": uid, "subject": subject, "decision": decision,
                    "status": new_status, "from_status": before, "version": int(version or 0),
                    "reason": reason, "reason_logged": logged, "edited": bool(edits)})


# ============================================================== 端口选择 / 启动


def port_in_use(host: str, port: int) -> bool:
    """判断端口是否已被监听。

    Windows 上 `SO_REUSEADDR` 允许"抢占式"绑定已占用端口 → **不设**该选项，
    并先用 `connect_ex` 探测既有监听者（双保险）。
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.35)
        if probe.connect_ex((host, port)) == 0:
            return True
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
            return False
        except OSError:
            return True


def choose_port(preferred: int = 5000, host: str = "127.0.0.1", candidates: int = 10) -> int:
    """返回第一个可用端口（5000 → 5009）。全被占用抛 RuntimeError。

    ⚠️ 2026-10-24：原来只试 2 个端口（5000/5001）。用户机器上两个**旧进程**同时占着
    这两个端口时，新进程直接 `端口全部被占用` 退出；而启动脚本的探测请求被旧服务应答，
    于是页面显示"启动成功"、随后报 `Wait-Process 找不到进程 4960`。
    放宽到 10 个端口，同时启动脚本会先检测"是否已在运行"，双重保险。
    """
    tried = []
    for offset in range(max(1, candidates)):
        port = preferred + offset
        tried.append(port)
        if not port_in_use(host, port):
            return port
    raise RuntimeError(f"端口全部被占用: {tried}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="题库 Web UI（仅 127.0.0.1）")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--check-port", action="store_true", help="只选端口 + 写 port.txt，不启动服务")
    args = parser.parse_args(argv)

    if args.host not in ("127.0.0.1", "localhost"):
        print(f"[warn] 本应用只允许绑定回环地址，已强制改为 127.0.0.1（收到 {args.host}）")
        args.host = "127.0.0.1"
    try:
        port = choose_port(args.port, args.host)
    except RuntimeError as exc:
        print(f"[error] {exc}")
        return 2
    path = write_port_file(port)
    print(f"[port] 实际端口 {port} → {path}")
    if port != args.port:
        print(f"[port] {args.port} 被占用，已回退到 {port}")
    if args.check_port:
        return 0

    print(f"[web] http://{args.host}:{port}/quiz  （debug=False）")
    app.run(host=args.host, port=port, debug=False, threaded=True, use_reloader=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

