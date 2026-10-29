#!/usr/bin/env python
"""需求 7 的数据修复：**只修"确定性硬伤"**，不做任何语义改写。

修复三类（判据全部来自 `scripts/audit_explanations.py`，不另写一套）：

  ① **模板残留题**（stem 里就是「请输入题目内容 / A. 选项内容…」、解释是「请输入解析」）
     → `status='rejected'` + `reviewed_by='auto:repair_explanations'`，从刷题里消失。
     依据：题干和四个选项全是占位符，答案 'A' 也没有意义，留着只会浪费用户时间。

  ② **缺题干的语音题/辨音题**（`phonetics`、少量 `reading_qa`：answer='B. lift'、
     explanation 里已列出全部对比词）→ 从**解释文本**里解析出选项，补回 stem。
     依据（实测样例）：
       stem=''  answer='B. lift'
       explanation='white、light、knife 中的字母 i 发 /aɪ/，而 lift 中发 /ɪ/，因此 B 不同。'
     → 补出的 stem 为「Compare the underlined parts and choose the one with a different
        pronunciation.\nA. white\nB. lift\nC. light\nD. knife」
     ⚠️ 选项顺序由解释里的列举顺序决定（A/B/C 为同类项、答案项按字母落位），
     这样字母与选项的对应关系和原卷一致；解析不出来的一律**不猜**，只报告。

  ③ 顺带报告：`explanation_too_short`、`explanation_empty` 等（**不自动改**，交给人工/AI）。

用法:
    python scripts/repair_explanations.py                 # dry-run（默认，只报告）
    python scripts/repair_explanations.py --apply         # 真改库（先自动备份）
    python scripts/repair_explanations.py --subject english --apply
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
BACKUP = DATA / "backup"
SUBJECTS = ("english", "c_wuhan", "c_hbpu", "aca_llm")
sys.path.insert(0, str(ROOT / "scripts"))
try:
    from audit_explanations import audit_row, PLACEHOLDER_EXPLANATIONS, _norm  # type: ignore
except Exception:  # noqa: BLE001 - 审计脚本缺失时仍要能跑
    audit_row = None

PLACEHOLDER_STEM_RE = re.compile(r"请输入题目内容|请输入题干|示例题目|A\.\s*选项内容|A\.\s*A\.\s*选项内容")
PHONETIC_STEM = ("Compare the underlined parts and choose the one with a different pronunciation.")

# 解释里的两种句式（实测）：
#   ① "white、light、knife 中的字母 i 发 /aɪ/，而 lift 中发 /ɪ/，因此 B 不同。"
#   ② "字母 a 在 nature 中读 /eɪ/，其余三项都读 /æ/。"
RE_GROUP_THEN_ANSWER = re.compile(
    r"^\s*(?P<others>.+?)\s*中(?:的)?(?P<unit>[^，,]{1,20}?)发\s*(?P<p1>/[^/]+/)\s*[，,]\s*"
    r"而\s*(?P<answer>.+?)\s*中(?:的)?[^，,]{0,20}?发\s*(?P<p2>/[^/]+/)")
RE_UNIT_IN_ANSWER = re.compile(
    r"^\s*(?P<unit>字母组合|字母|画线部分|下划线部分)\s*(?P<key>[A-Za-z]{1,4})\s*在\s*(?P<answer>.+?)\s*中读\s*"
    r"(?P<p1>/[^/]+/)\s*[，,]\s*其余(?:三项|各项|都)")
SPLIT_OTHERS = re.compile(r"[、,，/]|\s+和\s+|\s+and\s+")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_phonetic_options(answer: str, explanation: str) -> list[tuple[str, str]] | None:
    """从解释里解析出 (字母, 单词) 列表；解析不出来返回 None（**绝不猜**）。"""
    ans = str(answer or "").strip()
    m_ans = re.match(r"^\s*([A-Ha-h])\s*[.、)．]\s*(.+?)\s*$", ans)
    if not m_ans:
        return None
    letter, word = m_ans.group(1).upper(), m_ans.group(2).strip()
    expl = str(explanation or "").strip()

    others: list[str] = []
    m = RE_GROUP_THEN_ANSWER.match(expl)
    if m:
        answer_in_expl = m.group("answer").strip()
        # 解释里的"答案侧"文字必须与 answer 字段里的单词一致，否则不敢用
        if _norm(word) not in _norm(answer_in_expl) and _norm(answer_in_expl) not in _norm(word):
            return None
        others = [w.strip() for w in SPLIT_OTHERS.split(m.group("others")) if w.strip()]
    else:
        m2 = RE_UNIT_IN_ANSWER.match(expl)
        if m2:
            answer_in_expl = m2.group("answer").strip()
            if _norm(word) not in _norm(answer_in_expl) and _norm(answer_in_expl) not in _norm(word):
                return None
            # "其余三项"没列举出来 → 只有单词数足够才敢用不了，这里直接放弃（宁缺勿造）
            return None
    if len(others) != 3:
        return None
    if any(not re.fullmatch(r"[A-Za-z][A-Za-z'’\- ]{0,24}", w) for w in others):
        return None
    if len({_norm(w) for w in others} | {_norm(word)}) != 4:
        return None

    letters = ["A", "B", "C", "D"]
    if letter not in letters:
        return None
    pool = list(others)
    options: list[tuple[str, str]] = []
    for idx, lt in enumerate(letters):
        options.append((lt, word if lt == letter else pool.pop(0)))
    return options


def build_stem(options: list[tuple[str, str]]) -> str:
    body = "\n".join(f"{lt}. {word}" for lt, word in options)
    return f"{PHONETIC_STEM}\n{body}"


def backup_db(path: Path) -> Path:
    BACKUP.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = BACKUP / f"{path.stem}-{stamp}{path.suffix}"
    shutil.copy2(path, target)
    return target


def main() -> int:
    ap = argparse.ArgumentParser(description="修「确定性硬伤」的模板残留题/缺题干辨音题（默认 dry-run）")
    ap.add_argument("--subject", default=None, choices=list(SUBJECTS))
    ap.add_argument("--apply", action="store_true", help="真改库（会先自动备份到 data/backup/）")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    subjects = [args.subject] if args.subject else list(SUBJECTS)
    report: dict = {}
    for subj in subjects:
        path = DATA / f"{subj}.sqlite"
        if not path.exists():
            continue
        conn = sqlite3.connect(str(path))
        conn.execute("PRAGMA busy_timeout=30000")
        placeholders, rebuilt, other_flags = [], [], {}
        rows = conn.execute(
            "SELECT question_uid, question_type, COALESCE(stem,''), COALESCE(answer,''), "
            "COALESCE(explanation,''), COALESCE(material_text,''), COALESCE(trust_level,'') "
            "FROM questions").fetchall()
        for uid, qtype, stem, answer, expl, material, trust in rows:
            # ① 模板残留题：**只看题干特征**（「请输入题目内容 / A. 选项内容」）。
            #    ⚠️ 曾经把"解释是占位符"也放进这个条件，结果 `_norm(expl) in ...` 对
            #    692 条 explanation='' 的题也成立 → 差点把正常题目下架。
            #    占位符解释的题（如 c_wuhan「请输入解析」）题干本身也是模板文本，会被这一条抓到。
            if PLACEHOLDER_STEM_RE.search(stem):
                placeholders.append((uid, qtype, stem[:40], expl[:20]))
                continue
            # ② 缺题干但解释里有全部选项的辨音题
            if not stem.strip() and not material.strip() and qtype in ("phonetics", "reading_qa"):
                opts = parse_phonetic_options(answer, expl)
                if opts:
                    rebuilt.append((uid, qtype, answer, build_stem(opts)))
            # ③ 其它硬伤只报告
            if audit_row:
                for flag in audit_row(subj, qtype, stem, answer, expl, material):
                    if flag in ("explanation_too_short", "explanation_empty", "answer_empty",
                                "explanation_equals_answer", "stem_and_material_empty"):
                        other_flags[flag] = other_flags.get(flag, 0) + 1
        report[subj] = {"placeholders": len(placeholders), "stem_rebuilt": len(rebuilt),
                        "other_flags": other_flags,
                        "placeholder_samples": placeholders[:3],
                        "rebuilt_samples": [{"uid": u, "qtype": t, "answer": a,
                                             "new_stem": s[:160]} for u, t, a, s in rebuilt[:3]]}
        print(f"===== {subj}")
        print(f"  模板残留题（建议 status=rejected）：{len(placeholders)}")
        for uid, qtype, stem_head, expl_head in placeholders[:3]:
            print(f"      · {uid} [{qtype}] stem={stem_head!r} explanation={expl_head!r}")
        print(f"  缺题干但可从解释还原选项的辨音题：{len(rebuilt)}")
        for uid, qtype, ans, stem in rebuilt[:2]:
            print(f"      · {uid} [{qtype}] answer={ans!r}")
            print("        新题干：" + stem.replace("\n", " / "))
        if other_flags:
            print(f"  其它硬伤（只报告不改）：{other_flags}")

        if args.apply and (placeholders or rebuilt):
            bak = backup_db(path)
            print(f"  [备份] {bak.name}")
            ts = now_iso()
            for uid, *_ in placeholders:
                conn.execute("UPDATE questions SET status='rejected', reviewed_by=?, version=COALESCE(version,1)+1 "
                             "WHERE question_uid=?", (f"auto:repair_explanations@{ts}", uid))
            for uid, _qtype, _ans, stem in rebuilt:
                conn.execute("UPDATE questions SET stem=?, reviewed_by=?, "
                             "version=COALESCE(version,1)+1 WHERE question_uid=?",
                             (stem, f"auto:repair_explanations@{ts}", uid))
            conn.commit()
            print(f"  [已改库] 下架 {len(placeholders)} 题、补题干 {len(rebuilt)} 题")
        conn.close()

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    if not args.apply:
        print("\n（dry-run：未改任何库。加 --apply 才写入，写入前会自动备份到 data/backup/）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
