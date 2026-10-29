#!/usr/bin/env python
"""套卷（模拟考试）支撑 —— 需求 6 的**数据层唯一事实源**。

## 关键数据事实（2026-10-13 实测，决定了实现方式）
`questions.no`（原卷题号）**没有入库**，但**不需要补**：
同一 `exam_title` 下的题目 `id` **完全连号（断点 = 0）**，因为导入脚本是逐题 append 的。
因此 **`ORDER BY id` 就是原卷题目顺序**：

    河北专升本英语18      n=69   断点=0  id=803..871
    湖北2022            n=57   断点=0  id=1260..1316
    湖北文理学院理工学院…  n=200  断点=0  id=8400..8599
    阿里云大模型 ACA …    n=129  断点=0  id=403..531

## 套卷清单位于哪
- `exam_title` 非空的 approved 题按 `exam_title` 分组 = 一套卷（英语 23 套、c_wuhan 29 套、
  c_hbpu 2 套、aca_llm 2 套，合计 **57 套**，另有"无套卷归属"的散题不参与）。
- `group_uid` 是"同一篇材料下的若干小题"（阅读整块题），套卷里按它把整块题排在一起，
  但**不改动原始顺序**（只用于前端分组显示）。

## 判分口径
与刷题页**完全共用** `scripts/judge_local.py`：规则判得了的当场出分，
判不了的（写作/整段翻译）标 `pending` 交给 AI，绝不在这里另写一套。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SUBJECTS = ("english", "c_wuhan", "c_hbpu", "aca_llm")
# 真题/教材题才算"真套卷"；AI 生成的不成套
REAL_TRUST = ("official_exam", "textbook")
# 一套卷至少要这么多题才值得做成"模拟考试"（挡住只有 1-2 题的碎片分组）
MIN_PAPER_SIZE = 10


def connect(subject: str, *, write: bool = False) -> sqlite3.Connection:
    path = DATA / f"{subject}.sqlite"
    if write:
        conn = sqlite3.connect(str(path))
        conn.execute("PRAGMA journal_mode=WAL")
    else:
        conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def list_papers(subject: str | None = None, *, min_size: int = MIN_PAPER_SIZE) -> list[dict]:
    """套卷清单（按科目分组前的扁平列表，供 `/api/paper/list` 用）。

    `real_count` = 该套卷里 official_exam/textbook 的条数（"是不是真卷"的判据）；
    `kinds` = 题型分布；`title` 为空的分组**不返回**（那不是套卷，是散题）。
    """
    out: list[dict] = []
    for subj in ([subject] if subject in SUBJECTS else SUBJECTS):
        try:
            conn = connect(subj)
        except sqlite3.Error:
            continue
        try:
            rows = conn.execute(
                "SELECT COALESCE(exam_title,'') AS title, count(*) AS n, "
                "sum(CASE WHEN trust_level IN ('official_exam','textbook') THEN 1 ELSE 0 END) AS real_n, "
                "min(id) AS id_min, max(id) AS id_max "
                "FROM questions WHERE status='approved' AND COALESCE(exam_title,'')<>'' "
                "GROUP BY 1 HAVING n >= ? ORDER BY n DESC, title", (min_size,)).fetchall()
            for row in rows:
                title = str(row["title"])
                kinds = {str(r[0]): int(r[1]) for r in conn.execute(
                    "SELECT question_type, count(*) FROM questions WHERE status='approved' "
                    "AND exam_title=? GROUP BY 1 ORDER BY 2 DESC", (title,))}
                out.append({
                    "subject": subj, "title": title, "count": int(row["n"]),
                    "real_count": int(row["real_n"] or 0),
                    "id_min": int(row["id_min"]), "id_max": int(row["id_max"]),
                    "question_types": kinds,
                })
        finally:
            conn.close()
    return out


def paper_questions(subject: str, title: str, *, limit: int = 200) -> list[dict]:
    """一套卷的题目，**按原卷顺序**（= `ORDER BY id`）返回。

    字段与 `/api/questions` 保持一致的命名习惯（`options_parsed`/`answer_keys`/`objective`/
    `show_explanation`…），这样前端可以复用同一套渲染；`seq` 是卷面题号（1 起）。
    """
    conn = connect(subject)
    try:
        rows = conn.execute(
            "SELECT question_uid, question_type, stem, options, answer, explanation, difficulty, "
            "knowledge_point, chapter, group_uid, COALESCE(material_text,'') AS material_text, "
            "trust_level, exam_title, id, COALESCE(source_url,'') AS source_url, "
            "COALESCE(source_credit,'') AS source_credit, COALESCE(fact_source,'') AS fact_source "
            "FROM questions WHERE status='approved' AND exam_title=? ORDER BY id LIMIT ?",
            (title, limit)).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def paper_summary(subject: str, title: str, *, limit: int = 200) -> dict:
    """套卷元信息 + 题量校验（前端进考场前先看这个）。"""
    qs = paper_questions(subject, title, limit=limit)
    kinds: dict[str, int] = {}
    total_score = 0.0
    for q in qs:
        kinds[q["question_type"] or ""] = kinds.get(q["question_type"] or "", 0) + 1
    # 满分按 taxonomy 的 per_item 逐题累加（与判分口径同源）
    import sys
    if str(ROOT / "scripts") not in sys.path:
        sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import judge_local as jl  # type: ignore
        for q in qs:
            total_score += jl.full_score_for(subject, q.get("question_type"))
    except Exception:  # noqa: BLE001
        total_score = float(len(qs))
    return {"subject": subject, "title": title, "count": len(qs),
            "question_types": kinds, "total_score": round(total_score, 2)}


if __name__ == "__main__":  # 自检：打印套卷清单
    papers = list_papers()
    print(f"共 {len(papers)} 套卷（≥{MIN_PAPER_SIZE} 题，approved）")
    for p in papers:
        print(f"  [{p['subject']:<8}] {p['title'][:44]:<46} {p['count']:>4} 题"
              f"（真题 {p['real_count']}）")
