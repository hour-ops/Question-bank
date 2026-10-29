#!/usr/bin/env python
"""弱势诊断（需求 8）——"越刷题越了解我哪里弱"的**数据层唯一事实源**。

用户原话：「分析之中我希望所有的题都可以全覆盖，然后分析可以通过我答题分析我的弱势科目、
弱势知识点、弱势题型（我的想法是可以像 ai 一样越刷题越了解我，越知道我哪里弱势，
越知道该怎么强化，下次联通 api 后可以选择调用云端大模型给我一个学习强化方案）」

设计要点：
  1. **对错口径只走 `update_daily_progress.judge_correct()`**（全项目唯一阈值处），
     这里不另写一套；"未判分"的作答单独计数，不计入正确率分母。
  2. 「弱势」= 把**做过的题**按 科目 / 知识点 / 题型 三个维度聚合，按
     （错误数 ↓，正确率 ↑）排序；样本太少的维度会标 `low_sample`，避免"做 1 题错 1 题 = 100% 弱"。
  3. 「记忆」：每次调用都把当日快照写入 `logs/weakness_history.jsonl`（append，幂等追加），
     于是"越刷越了解"有据可依（能看正确率随时间的变化）。
  4. 全库覆盖率：同时报告"题库里每个知识点的题目数 vs 我做过的题数"，回答"还有多少没刷过"。
"""

from __future__ import annotations

import json
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
LOGS = ROOT / "logs"
SUBJECTS = ("english", "c_wuhan", "c_hbpu", "aca_llm")
ACA_SUBJECT = "aca_llm"
WEAKNESS_HISTORY_NAME = "weakness_history.jsonl"


def history_path() -> Path:
    """历史快照文件路径。**必须每次现算**：模块级常量在 import 时就固定了，
    测试把 `LOGS` 指到临时目录后，常量仍会指向真实 `logs/`（本测试实测踩到）。"""
    return LOGS / WEAKNESS_HISTORY_NAME


# 少于这个作答数的维度标 low_sample（正确率不可信）
MIN_SAMPLE = 3
# 正确率低于这个值算"弱"
WEAK_RATIO = 0.6

sys.path.insert(0, str(ROOT / "scripts"))
import update_daily_progress as udp  # noqa: E402


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_question_meta() -> dict[str, dict[str, dict]]:
    """{科目: {question_uid: {question_type, knowledge_point, trust_level, exam_title}}}（只读）。

    ⚠️ 路径一律用**模块级 `DATA`**（测试会把它指到临时目录）；不要用 `ROOT / "data"`
    另算一份 —— 那样测试读到的是真实库（实测踩过：临时环境里 attempts 为 0 却被当成真实库）。
    """
    out: dict[str, dict[str, dict]] = {}
    for subj in SUBJECTS:
        path = DATA / f"{subj}.sqlite"
        meta: dict[str, dict] = {}
        if path.exists():
            try:
                conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
                conn.row_factory = sqlite3.Row
                for row in conn.execute(
                        "SELECT question_uid, COALESCE(question_type,'') AS question_type, "
                        "COALESCE(knowledge_point,'') AS knowledge_point, "
                        "COALESCE(trust_level,'') AS trust_level, "
                        "COALESCE(exam_title,'') AS exam_title, status "
                        "FROM questions"):
                    meta[str(row["question_uid"])] = dict(row)
                conn.close()
            except sqlite3.Error:
                meta = {}
        out[subj] = meta
    return out


def load_attempts() -> list[dict]:
    """读全部 attempts（只读）。字段名按 schema 探测，兼容未来加列。"""
    path = DATA / "attempts.sqlite"
    if not path.exists():
        return []
    try:
        conn = udp.connect(path, readonly=True)
    except sqlite3.Error:
        return []
    try:
        cols = udp.columns_of(conn, "attempts")
        wanted = [c for c in ("attempt_id", "question_uid", "subject", "judge_score", "judge_model",
                              "source_type", "created_at") if c in cols]
        rows = [dict(zip(wanted, r)) for r in conn.execute(f"SELECT {', '.join(wanted)} FROM attempts")]
    except sqlite3.Error:
        rows = []
    finally:
        conn.close()
    return rows


def judge_all(rows: list[dict], meta: dict[str, dict[str, dict]]) -> list[dict]:
    """给每条 attempt 打上「对/错/未判分」标记（口径来自 update_daily_progress）。"""
    aca = udp.load_aca_rules()
    tax = udp.load_json(udp.TAXONOMY)
    out: list[dict] = []
    for rec in rows:
        subj = str(rec.get("subject") or "")
        qid = str(rec.get("question_uid") or "")
        m = (meta.get(subj) or {}).get(qid) or {}
        qtype = m.get("question_type") or ""
        full = (udp.aca_full_score(aca, qtype) if subj == ACA_SUBJECT
                else udp._resolve_full_score(subj, qtype, m, tax)[0])
        score = udp._to_float(rec.get("judge_score"))
        if score is None:
            result = "unjudged"
        elif udp.judge_correct(subj, score, question_type=qtype, full_score=full, aca=aca):
            result = "correct"
        else:
            result = "wrong"
        out.append({
            "attempt_id": rec.get("attempt_id"), "subject": subj, "question_uid": qid,
            "question_type": qtype, "knowledge_point": m.get("knowledge_point") or "",
            "trust_level": m.get("trust_level") or "", "exam_title": m.get("exam_title") or "",
            "judge_model": rec.get("judge_model") or "", "source_type": rec.get("source_type") or "",
            "created_at": rec.get("created_at") or "", "date": udp.local_date(rec.get("created_at")),
            "result": result, "score": score, "full_score": full,
        })
    return out


def _bucket(rows: list[dict], key: str) -> list[dict]:
    """按某维度聚合 → 每桶 {key, judged, correct, wrong, unjudged, accuracy, weak, low_sample}。"""
    acc: dict[str, dict] = defaultdict(lambda: {"judged": 0, "correct": 0, "wrong": 0, "unjudged": 0})
    for r in rows:
        k = str(r.get(key) or "") or "（未标注）"
        b = acc[k]
        if r["result"] == "unjudged":
            b["unjudged"] += 1
        else:
            b["judged"] += 1
            b["correct" if r["result"] == "correct" else "wrong"] += 1
    out = []
    for k, b in acc.items():
        ratio = (b["correct"] / b["judged"]) if b["judged"] else 0.0
        out.append({
            "key": k, "label": k, "judged": b["judged"], "correct": b["correct"],
            "wrong": b["wrong"], "unjudged": b["unjudged"], "accuracy": round(ratio, 4),
            "weak": bool(b["judged"] and ratio < WEAK_RATIO),
            "low_sample": bool(b["judged"] < MIN_SAMPLE),
        })
    out.sort(key=lambda x: (-x["wrong"], x["accuracy"], -x["judged"], x["key"]))
    return out


def coverage(meta: dict[str, dict[str, dict]], attempts: list[dict]) -> dict:
    """覆盖面：题库里有多少题 / 我做过多少题（按科目与知识点）。"""
    done = defaultdict(set)
    for a in attempts:
        if a["question_uid"]:
            done[a["subject"]].add(a["question_uid"])
    out: dict[str, dict] = {}
    for subj, m in meta.items():
        approved = {uid: v for uid, v in m.items() if (v.get("status") or "") == "approved"}
        touched = {uid for uid in done.get(subj, set()) if uid in approved}
        by_kp: dict[str, dict] = defaultdict(lambda: {"total": 0, "done": 0})
        for uid, v in approved.items():
            kp = v.get("knowledge_point") or "（未标注）"
            by_kp[kp]["total"] += 1
            if uid in done.get(subj, set()):
                by_kp[kp]["done"] += 1
        out[subj] = {
            "total": len(approved), "done": len(touched),
            "ratio": round(len(touched) / len(approved), 4) if approved else 0.0,
            "knowledge_points": [
                {"key": k, "label": k, "total": v["total"], "done": v["done"],
                 "ratio": round(v["done"] / v["total"], 4) if v["total"] else 0.0}
                for k, v in sorted(by_kp.items(), key=lambda kv: (-kv[1]["total"], kv[0]))
            ],
        }
    return out


def trend(attempts: list[dict], *, days: int = 14) -> list[dict]:
    """按日趋势（最近 days 天）：每天 做了多少 / 对多少 / 错多少 / 正确率。"""
    acc: dict[str, dict] = defaultdict(lambda: {"judged": 0, "correct": 0, "wrong": 0, "total": 0})
    for a in attempts:
        d = a.get("date") or ""
        if not d:
            continue
        b = acc[d]
        b["total"] += 1
        if a["result"] != "unjudged":
            b["judged"] += 1
            b["correct" if a["result"] == "correct" else "wrong"] += 1
    days_sorted = sorted(acc)[-days:]
    out = []
    for d in days_sorted:
        b = acc[d]
        out.append({"date": d, "total": b["total"], "judged": b["judged"], "correct": b["correct"],
                    "wrong": b["wrong"],
                    "accuracy": round(b["correct"] / b["judged"], 4) if b["judged"] else 0.0})
    return out


def weaknesses(attempts: list[dict], meta: dict[str, dict[str, dict]], *, top: int = 12) -> dict:
    """主入口：算全部维度的弱势清单（不落库；落库由 `remember()` 负责）。"""
    judged = [a for a in attempts if a["result"] != "unjudged"]
    by_subject = _bucket(attempts, "subject")
    for item in by_subject:
        item["label"] = item["key"]
    weak_points = [x for x in _bucket(judged, "knowledge_point") if x["weak"] and not x["low_sample"]]
    weak_types = [x for x in _bucket(judged, "question_type") if x["weak"] and not x["low_sample"]]
    payload = {
        "generated_at": _now(),
        "totals": {
            "attempts": len(attempts), "judged": len(judged),
            "correct": sum(1 for a in judged if a["result"] == "correct"),
            "wrong": sum(1 for a in judged if a["result"] == "wrong"),
            "unjudged": len(attempts) - len(judged),
            "accuracy": round(sum(1 for a in judged if a["result"] == "correct") / len(judged), 4)
                        if judged else 0.0,
        },
        "by_subject": by_subject,
        "by_question_type": _bucket(judged, "question_type"),
        "by_knowledge_point": _bucket(judged, "knowledge_point"),
        "by_exam": _bucket(judged, "exam_title"),
        "weakest": {
            "subjects": [x for x in by_subject if x["weak"] and not x["low_sample"]][:top],
            "knowledge_points": weak_points[:top],
            "question_types": weak_types[:top],
        },
        "trend": trend(attempts),
        "coverage": coverage(meta, attempts),
        "thresholds": {"weak_ratio": WEAK_RATIO, "min_sample": MIN_SAMPLE},
    }
    return payload


def remember(payload: dict) -> Path:
    """把当日快照追加进 `logs/weakness_history.jsonl`（同一天重复调用只记一次）。"""
    LOGS.mkdir(parents=True, exist_ok=True)
    path = history_path()
    today = udp.today_local()
    if path.exists():
        try:
            for line in path.read_text(encoding="utf-8").splitlines()[-50:]:
                rec = json.loads(line)
                if rec.get("date") == today:
                    return path                      # 当天已记录 → 幂等
        except (OSError, json.JSONDecodeError):
            pass
    rec = {"date": today, "ts": _now(), "totals": payload.get("totals"),
           "weak_kp": [x["key"] for x in payload.get("weakest", {}).get("knowledge_points", [])],
           "weak_types": [x["key"] for x in payload.get("weakest", {}).get("question_types", [])],
           "coverage": {k: v.get("ratio") for k, v in (payload.get("coverage") or {}).items()}}
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return path


def analyze(*, remember_snapshot: bool = True) -> dict:
    """一步到位：读库 → **判对错**（`judge_all`）→ 算弱势 → （可选）写快照。

    ⚠️ 必须经 `judge_all()`：`weaknesses()` 要的是带 `result`（correct/wrong/unjudged）
    的注解行，直接喂原始 attempts 会 `KeyError: 'result'`（本测试实测踩过）。
    """
    meta = load_question_meta()
    annotated = judge_all(load_attempts(), meta)
    payload = weaknesses(annotated, meta)
    if remember_snapshot:
        payload["history_file"] = str(remember(payload))
    return payload


def build_advice_prompt(payload: dict, *, max_items: int = 8) -> str:
    """给云端大模型的"学习强化方案"提示词（需求 8 第 ③ 点：预留接口）。

    ⚠️ 只是**拼提示词**，不发请求：真正调用要由用户显式操作（并付费）。
    """
    t = payload.get("totals") or {}
    lines = [
        "你是一位专升本考试教练。下面是一名学生的真实做题统计，请给出**具体可执行**的强化方案。",
        "",
        f"总作答 {t.get('attempts')} 题（已判分 {t.get('judged')}，对 {t.get('correct')}，错 {t.get('wrong')}，"
        f"未判分 {t.get('unjudged')}），总正确率 {round((t.get('accuracy') or 0) * 100, 1)}%。",
        "",
        "【弱势科目】",
    ]
    for x in (payload.get("weakest", {}).get("subjects") or [])[:max_items]:
        lines.append(f"- {x['label']}：{x['correct']}/{x['judged']} 正确（{round(x['accuracy'] * 100, 1)}%），"
                     f"错 {x['wrong']} 次")
    lines.append("")
    lines.append("【弱势知识点】")
    for x in (payload.get("weakest", {}).get("knowledge_points") or [])[:max_items]:
        lines.append(f"- {x['label']}：{x['correct']}/{x['judged']} 正确（{round(x['accuracy'] * 100, 1)}%），"
                     f"错 {x['wrong']} 次")
    lines.append("")
    lines.append("【弱势题型】")
    for x in (payload.get("weakest", {}).get("question_types") or [])[:max_items]:
        lines.append(f"- {x['label']}：{x['correct']}/{x['judged']} 正确（{round(x['accuracy'] * 100, 1)}%），"
                     f"错 {x['wrong']} 次")
    lines.append("")
    lines.append("【近 14 天趋势】")
    for x in (payload.get("trend") or [])[-14:]:
        lines.append(f"- {x['date']}：做 {x['total']} 题，正确率 {round(x['accuracy'] * 100, 1)}%")
    lines.append("")
    lines.append("要求：① 按优先级排序给出 3–5 条强化动作（每条写清「练什么 / 练多少 / 怎么检验」）；"
                 "② 指出最该先补的 2 个知识点并说明理由；③ 给出一个 7 天计划表；④ 不要泛泛而谈。")
    return "\n".join(lines)


if __name__ == "__main__":  # 自检
    data = analyze(remember_snapshot=False)
    print(json.dumps({k: v for k, v in data.items() if k not in ("coverage", "by_knowledge_point")},
                     ensure_ascii=False, indent=2)[:2000])
    print("\n覆盖率：")
    for subj, c in (data.get("coverage") or {}).items():
        print(f"  {subj}: 做过 {c['done']}/{c['total']}（{round(c['ratio'] * 100, 1)}%）"
              f"，知识点 {len(c['knowledge_points'])} 个")
