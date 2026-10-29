#!/usr/bin/env python
"""需求 7 的一半：**本地零成本预筛**「官方真题/教材真题」的解释是否可能有问题。

思路：AI 逐题复核 6,673 条解释要花真钱，先用确定性规则把**明显可疑**的挑出来，
只把可疑的送 AI（或用便宜模型全量过一遍 + 只对可疑的用强模型细看）。

可疑判据（**只认确定性硬伤**，不做语义猜测）：

  - `explanation_too_short`：去标点空白后 < 8 字（等于没解释）
  - `explanation_placeholder`：占位符文本（「请输入解析」「略」「无」「暂无」…）
  - `explanation_equals_answer`：解释与答案一字不差（没说明任何东西）
  - `answer_empty`：答案为空（判不了对错，解释再对也没用）
  - `stem_empty`：题干为空（题目残缺）

⚠️ 曾经加过 `no_answer_mention`（"解释里没提到答案字面"），实测**误报率极高**：
   英语语法填空的答案字段是 `"biggest | for | started"`（多空挤一行），而解释是按空逐条讲的，
   字面永远对不上；C 科选择题的解释常用定义/译文论证，也不会复述选项字母。
   它把 59.7% 的真题标成可疑 —— 这种"狼来了"的判据只会让人不再看报告，故**已删除**。

用法:
    python scripts/audit_explanations.py [--subject english] [--limit 20] [--json]
    python scripts/audit_explanations.py --checklist out.jsonl   # 导出待 AI 复核清单
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SUBJECTS = ("english", "c_wuhan", "c_hbpu", "aca_llm")
# 只有这两类算"真题"（用户要求只在真题上显示解释，所以也只有这两类值得花钱复核）
REAL_TRUST = ("official_exam", "textbook")
LETTERS = "ABCDEFGH"
MAX_OPTION_LEN = 40          # 选项原文超过这个长度就不拿它当关键词（多半是代码/长句）
# 采集阶段的占位符解释（实测存在，必须当成"没有解释"）
PLACEHOLDER_EXPLANATIONS = {
    "请输入解析", "请输入答案解析", "暂无解析", "暂无", "无", "略", "待补充", "略。", "n/a", "na",
    "none", "null", "待补充解析", "此题暂无解析", "没有解析", "-",
}


def _norm(text: str) -> str:
    s = re.sub(r"\s+", "", str(text or "")).lower()
    return re.sub(r"[，。、；：？！（）【】“”‘’·,.;:?!()\[\]<>\"'`-]", "", s)


def _letters(text: str) -> str:
    m = re.fullmatch(r"\s*([A-Ha-h])(?:\s*[.,、，;；/|]\s*[A-Ha-h])*\s*[.,、，;；]?\s*", str(text or ""))
    if m:
        return "".join(sorted({c for c in str(text).upper() if c in LETTERS}))
    return ""


def _option_texts(stem: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for letter, body in re.findall(r"(?:^|\n|\s)([A-H])\s*[.、)．]\s*([^\n]{1,60}?)(?=\s*(?:\n|\s)[A-H]\s*[.、)．]|$)",
                                   str(stem or ""), re.M):
        if letter not in out:
            out[letter] = body.strip()
    return out


def audit_row(subject: str, qtype: str, stem: str, answer: str, explanation: str,
              material: str = "") -> list[str]:
    """返回该行的"确定性硬伤"标记（空列表 = 没发现问题）。**不做语义猜测。**

    ⚠️ `stem_empty` 必须**同时**看 `material_text`：英语的完形/对话题把正文放在 material 里，
       题干本来就是空的（实测 298 题如此），只看 stem 会把这批全部误报。
    """
    flags: list[str] = []
    ans = str(answer or "").strip()
    expl = str(explanation or "").strip()
    if not ans:
        flags.append("answer_empty")
    if not str(stem or "").strip() and not str(material or "").strip():
        flags.append("stem_and_material_empty")
    if not expl:
        flags.append("explanation_empty")
        return flags
    n_expl = _norm(expl)
    if len(n_expl) < 8:
        flags.append("explanation_too_short")
    if n_expl in PLACEHOLDER_EXPLANATIONS or any(
            n_expl.startswith(p) and len(n_expl) <= len(p) + 4 for p in PLACEHOLDER_EXPLANATIONS):
        flags.append("explanation_placeholder")
    if ans and _norm(ans) and n_expl == _norm(ans):
        flags.append("explanation_equals_answer")
    return flags


def find_placeholder_explanations(conn: sqlite3.Connection,
                                  trust_levels: tuple = REAL_TRUST) -> list[tuple[str, str, str]]:
    """找出"占位符解释"（如「请输入解析」）→ [(question_uid, trust_level, explanation)]。

    由 `scripts/repair_explanations.py` 复用来做修复；判据集中在 `audit_row()` 里，**不另写一套**。
    """
    sql = ("SELECT question_uid, COALESCE(trust_level,''), COALESCE(explanation,''), "
           "COALESCE(stem,''), COALESCE(answer,''), COALESCE(material_text,'') FROM questions")
    params: list = []
    if trust_levels:
        marks = ",".join("?" for _ in trust_levels)
        sql += f" WHERE trust_level IN ({marks})"
        params = list(trust_levels)
    out: list[tuple[str, str, str]] = []
    for uid, trust, expl, stem, ans, material in conn.execute(sql, params):
        flags = audit_row("", "", stem, ans, expl, material)
        if "explanation_placeholder" in flags:
            out.append((str(uid), str(trust), str(expl)))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="官方真题/教材题解释的本地预筛（零成本）")
    ap.add_argument("--subject", default=None)
    ap.add_argument("--limit", type=int, default=8, help="每种问题最多打印几条样例")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--checklist", default=None, help="把待 AI 复核的题导出成 JSONL")
    args = ap.parse_args()

    subjects = [args.subject] if args.subject in SUBJECTS else list(SUBJECTS)
    summary: dict = {}
    checklist: list[dict] = []
    for subj in subjects:
        path = DATA / f"{subj}.sqlite"
        if not path.exists():
            continue
        conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            rows = conn.execute(
                "SELECT question_uid, question_type, stem, answer, explanation, trust_level, "
                "COALESCE(material_text,'') "
                "FROM questions WHERE trust_level IN (?,?)", REAL_TRUST).fetchall()
        finally:
            conn.close()
        per_flag: dict[str, int] = {}
        samples: dict[str, list[str]] = {}
        total = flagged = 0
        for uid, qtype, stem, answer, explanation, trust, material in rows:
            total += 1
            flags = audit_row(subj, qtype, stem, answer, explanation, material)
            if not flags:
                continue
            flagged += 1
            for f in flags:
                per_flag[f] = per_flag.get(f, 0) + 1
                if len(samples.setdefault(f, [])) < args.limit:
                    samples[f].append(f"{uid} [{trust}/{qtype}] 答案={str(answer)[:30]!r} "
                                      f"解释={str(explanation)[:60]!r}")
            checklist.append({"subject": subj, "question_uid": uid, "question_type": qtype,
                              "trust_level": trust, "stem": stem, "answer": answer,
                              "explanation": explanation, "flags": flags})
        summary[subj] = {"total_real": total, "flagged": flagged, "per_flag": per_flag}
        pct = (flagged / total * 100) if total else 0.0
        print(f"===== {subj}：真题/教材题 {total} 条，本地预筛可疑 {flagged} 条（{pct:.1f}%）")
        for f, n in sorted(per_flag.items(), key=lambda kv: -kv[1]):
            print(f"  {f:<26} {n:>5}")
            for s in samples[f][:2]:
                print(f"      · {s}")

    grand_total = sum(v["total_real"] for v in summary.values())
    grand_flagged = sum(v["flagged"] for v in summary.values())
    print(f"\n合计：真题/教材题 {grand_total} 条 → 可疑 {grand_flagged} 条"
          f"（{(grand_flagged / grand_total * 100) if grand_total else 0:.1f}%）")
    if args.checklist:
        out = Path(args.checklist)
        with out.open("w", encoding="utf-8") as fh:
            for rec in checklist:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"待复核清单已写出：{out}（{len(checklist)} 条）")
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
