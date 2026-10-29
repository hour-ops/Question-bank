#!/usr/bin/env python
"""题目清洗：去掉题干/答案/解析里混入的**广告推广文字**，并修掉可确定的提取类拼写错误。

背景（自动审核实测）：hbzsb 页面把「欢迎关注【湖北专升本网】…QQ/电话/年份」等推广文字
混进了答案区，我的解析器把它们吃进了 `answer` 字段 → 571 道题里有大量因此被拒。

用法:
    python scripts/clean_questions.py --dry-run        # 只统计会改多少条，不写库
    python scripts/clean_questions.py --reopen         # 清洗后把 rejected 重新置为 parsed 以便重审
    python scripts/clean_questions.py --subject english

设计:
  1. **按行**删除命中推广特征的行；行内命中且位于文本后 40% 的，从命中处截断
     （保护正文，只砍尾巴上的推广）。
  2. 只做**可确定**的拼写修复（`lt's→It's`、独立 `l→I`、`haven 't→haven't` 等），
     不做任何需要语义判断的改写。
  3. 只改文本字段，**不动** question_uid / status / 分数等；改动计数与样例打印出来供人核对。
"""

from __future__ import annotations

import argparse
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SUBJECTS = ["english", "c_wuhan", "c_hbpu", "aca_llm"]

# 强推广特征（命中即认为是推广文字）
PROMO_RE = re.compile(
    r"(欢迎关注|湖北专升本网|专升本网|微信公众号|公众号|扫码|扫一扫|"
    r"QQ\s*[:：]?\s*\d|QQ群|电话\s*[:：]?\s*\d|咨询\s*(电话|QQ|微信)|客服|"
    r"更多(资料|真题|内容|信息)|获取更多|点击(查看|关注|进入)|关注我们|"
    r"版权|免责声明|转载|来源\s*[:：]|https?://|www\.|\.com|\.cn/|"
    r"第\s*\d+\s*页|上一篇|下一篇|相关阅读|编辑推荐|热门推荐|加入收藏)"
)

# 可确定的提取类拼写错误
TYPO_FIXES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\blt's\b"), "It's"),
    (re.compile(r"\blt\b"), "It"),
    (re.compile(r"\bl'm\b"), "I'm"),
    (re.compile(r"\bl've\b"), "I've"),
    (re.compile(r"\bl'll\b"), "I'll"),
    (re.compile(r"\bl'd\b"), "I'd"),
    (re.compile(r"\bls\b"), "Is"),
    (re.compile(r"\bl saw\b"), "I saw"),
    (re.compile(r"\bl am\b"), "I am"),
    (re.compile(r"\bl have\b"), "I have"),
    (re.compile(r"\bl was\b"), "I was"),
    (re.compile(r"\blt was\b"), "It was"),
    (re.compile(r"(\w) '(\w)"), r"\1'\2"),        # haven 't -> haven't
    (re.compile(r"\s+([,.!?;:])"), r"\1"),         # 空格 + 标点
]


def clean_text(s: str | None) -> tuple[str, bool]:
    """返回 (清洗后文本, 是否改动)。

    ⚠️ 关键教训：**绝不能"整行丢弃"单行字段** —— 实测答案字段常是一整行，
    里面夹着"欢迎关注…"，按行丢会把答案清成空串（首版就踩了这个坑）。
    正确做法：多行时丢推广行且保底不丢空；然后**在命中处截断、保留正文前缀**。
    """
    if not s:
        return s or "", False
    original = s

    # A) 多行：丢推广行；若全被丢掉则回退到原文（交给 B 步截断）
    if "\n" in s:
        kept = [ln for ln in s.splitlines() if not PROMO_RE.search(ln)]
        out = "\n".join(kept).strip()
        if not out:
            out = s.strip()
    else:
        out = s.strip()

    # B) 行内推广：保留命中点之前的正文（前缀太短才判为整段是推广）
    m = PROMO_RE.search(out)
    if m:
        prefix = out[: m.start()].strip().strip("，,、;；")
        out = prefix if len(prefix) >= 8 else ""

    # C) 剥离"答案"标记与后续的解析/知识点段落（答案本身应到此为止）
    out = re.sub(r"^\s*[【\[]\s*(答案|参考答案|翻译|解答)\s*[】\]]\s*", "", out)
    m2 = re.search(r"[【\[]\s*(解析|详解|知识点|考点|分析|译文|点评)\s*[】\]]", out)
    if m2 and m2.start() >= 2:
        out = out[: m2.start()].strip()

    # D) 只做可确定的拼写修复
    for pat, rep in TYPO_FIXES:
        out = pat.sub(rep, out)

    # E) 🔴 答案连读截断：源站答案键是「1. xxx 2. yyy 3. zzz」连排，我的切分器会把
    #    相邻题的答案一起吞进本题（实测 "was offered  7. were enjoying  8. has done …"）。
    #    策略：遇到「空格 + 数字 + .、． + 空格」即认为是下一题的答案，从此处截断。
    out = re.split(r"\s+\d{1,3}\s*[.、．]\s*", out)[0]

    out = re.sub(r"[ \t]{2,}", " ", out).strip().strip("，,、;；")
    return out, out != original


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--subject", default="all", choices=SUBJECTS + ["all"])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--reopen", action="store_true", help="把 rejected 且已清洗的题重开为 parsed")
    args = ap.parse_args()

    subjects = SUBJECTS if args.subject == "all" else [args.subject]
    total_changed = total_scanned = total_reopened = 0
    samples: list[str] = []

    for subj in subjects:
        p = DATA / f"{subj}.sqlite"
        if not p.exists():
            continue
        conn = sqlite3.connect(str(p))
        conn.execute("PRAGMA busy_timeout=30000")
        cols = {r[1] for r in conn.execute("PRAGMA table_info(questions)")}
        rows = conn.execute("SELECT question_uid, stem, answer, explanation FROM questions").fetchall()
        changed = reopened = 0
        for uid, stem, answer, explanation in rows:
            total_scanned += 1
            ns, cs = clean_text(stem)
            na, ca = clean_text(answer)
            ne, ce = clean_text(explanation)
            if not (cs or ca or ce):
                continue
            changed += 1
            if len(samples) < 12 and ca:
                samples.append(f"[{subj}] 答案: {str(answer)[:70]!r}\n        -> {na[:70]!r}")
            if not args.dry_run:
                sets = []
                params: list = []
                if cs:
                    sets.append("stem=?")
                    params.append(ns)
                if ca:
                    sets.append("answer=?")
                    params.append(na)
                if ce:
                    sets.append("explanation=?")
                    params.append(ne)
                if args.reopen and "status" in cols:
                    sets.append("status='parsed'")
                    sets.append("reviewed_by=NULL")
                sets.append("version=COALESCE(version,0)+1")
                params.append(uid)
                conn.execute(f"UPDATE questions SET {', '.join(sets)} WHERE question_uid=?", params)
                if args.reopen:
                    reopened += 1
        if not args.dry_run:
            conn.commit()
        print(f"  {subj:9} 扫描 {len(rows):4}  需清洗 {changed:4}" + (f"  已重开 {reopened}" if args.reopen else ""))
        conn.close()
        total_changed += changed
        total_reopened += reopened

    print(f"\n合计扫描 {total_scanned}，需清洗 {total_changed}，重开 {total_reopened}")
    if samples:
        print("\n=== 清洗样例 ===")
        for s in samples[:8]:
            print(" ", s)
    if args.dry_run:
        print("\ndry-run：未写库。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
