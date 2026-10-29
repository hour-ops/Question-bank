#!/usr/bin/env python
"""把 inbox/real_exams 里的真题解析入库（**纯本地、零 API 花费**）。

设计（回应用户四点要求）：
  ① **整块题不拆开**：新增 `group_uid` + `material_text` —— 同一篇短文/材料的若干小题绑成一组，
     渲染时整块显示（用户明确点名「阅读填空」这类本身就是整块，不该拆成独立题）。
  ② **可信度分级**：新增 `trust_level`（official_exam / textbook / third_party / ai_generated）
     + `exam_title`（来自哪套卷），让"真题"与"第三方练习/AI生成"可区分、可筛选。
  ③ **题型说明**：题型 key 统一映射到 `config/display.json` 里带 `how`（作答要求）的题型。
  ④ 连词成句的词组以 `/` 原样保留（渲染层再切成词卡）。

两种结构：
  A. v2/sections（英语真题）：sections[].items[]，答案在 answerSpec.values / referenceAnswer
  B. meta/questions（C语言教材题库）：questions[]，字段 type/content/options/answer/analysis/source.chapter

用法:
    python scripts/import_real_exams.py --dry-run
    python scripts/import_real_exams.py --apply [--replace-ai]
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from lib.uid import generate_uid  # noqa: E402

DATA = ROOT / "data"
SRC = ROOT / "inbox" / "real_exams"

# 真题里的 section.displayName / question.type → 本项目题型 key
TYPE_MAP = {
    # 英语（湖北 2024+ 全主观题）
    "语法填空": "grammar_fill", "连词成句": "sentence_build", "阅读填空": "reading_fill",
    "阅读填词": "reading_fill", "阅读理解": "reading_qa", "翻译填空": "translation_fill",
    "完成句子": "sentence_completion", "书面表达": "writing", "写作": "writing",
    # 英语（湖北 2020-2023 老格式）
    "词汇与结构": "single_choice", "词汇与语法结构": "single_choice", "词汇与语法": "single_choice",
    "单选题": "single_choice", "单项选择": "single_choice", "英译汉选择": "translation_choice",
    "英译汉": "translation", "段落翻译": "translation", "提纲填空": "outline_fill",
    # 通用/河北
    "语音题": "phonetics", "语音": "phonetics", "语音知识": "phonetics",
    "情景对话": "dialogue", "选词填空": "word_fill", "词汇填空": "word_fill",
    "完形填空": "cloze", "阅读理解 Section B": "reading_qa",
    # C 语言 / 程序设计
    "填空": "program_fill", "程序填空": "program_fill", "程序改错": "code_correction",
    "编程": "programming", "判断题": "true_false", "多选题": "multiple_choice",
}

SUBJECT_RULES = [
    # (匹配关键词, 科目, trust_level)
    (("湖北",), "english", "official_exam"),
    (("河北",), "english", "official_exam"),
    (("C语言", "程序设计", "数据结构", "软件工程"), None, "textbook"),   # 科目按校名再分
]

COLLEGE_TO_SUBJECT = [
    (("湖北理工学院",), "c_hbpu"),
    (("武汉商学院",), "c_wuhan"),
    (("湖北师范大学", "三峡大学", "文华学院", "湖北恩施", "湖北经济学院", "湖北大学知行",
      "湖北工程学院", "湖北工业大学", "武汉东湖", "武汉文理", "武汉生物工程", "武汉设计工程",
      "武汉工程大学", "武汉晴川", "武汉城市学院", "武汉传媒", "湖北商贸", "汉江师范",
      "武汉纺织大学", "湖北文理学院"), "c_wuhan"),   # 其它学校并入 c_wuhan 作为"各校专业课"补充
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(p: Path) -> sqlite3.Connection:
    c = sqlite3.connect(str(p))
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=30000")
    return c


def blocks_text(node) -> str:
    """`{blocks:[{type,value}]}` → 纯文本。"""
    if isinstance(node, str):
        return node.strip()
    if not isinstance(node, dict):
        return ""
    bs = node.get("blocks")
    if isinstance(bs, list):
        return "\n".join(str(b.get("value") or "") for b in bs if isinstance(b, dict)).strip()
    for k in ("value", "text", "content"):
        if isinstance(node.get(k), str):
            return node[k].strip()
    return ""


def strip_html(s: str) -> str:
    """只剥离**真正的 HTML 标签**，绝不能吃掉代码里的 `<stdio.h>` 这类尖括号内容。

    🔴 事故记录：旧实现用 `re.sub(r"<[^>]+>", "", s)` —— 它把 `#include <stdio.h>` 里的
    `<stdio.h>` 当成标签删掉，导致库里 5,900+ 道 C 题的代码被**不可逆损坏**（显示成 `#include`）。
    修法：只匹配「`<` + 字母 + 不含 `>` 的内容 + `>`」这种合法标签形态，并且要求**不是** `#include`
    这种代码上下文（用负向断言排除紧跟 `#include ` / `#include<` 的情况）。
    """
    s = s or ""
    # 先保护 C 代码里的尖括号头文件：#include <xxx.h> / #include<stdio.h>
    protected: list[str] = []

    def _keep(m: re.Match) -> str:
        protected.append(m.group(0))
        return f"\x00{len(protected) - 1}\x00"

    s = re.sub(r"#\s*include\s*<[^>\n]{1,60}>", _keep, s)
    # 只删合法 HTML 标签（`<` 后必须是字母或 `/字母`）
    s = re.sub(r"</?[a-zA-Z][^<>]{0,200}>", "", s)
    for i, code in enumerate(protected):
        s = s.replace(f"\x00{i}\x00", code)
    s = (s.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<")
         .replace("&gt;", ">").replace("&quot;", '"').replace("&#39;", "'"))
    return s.strip()


def map_type(raw: str, kind: str = "") -> str:
    raw = (raw or "").strip()
    if raw in TYPE_MAP:
        return TYPE_MAP[raw]
    for k, v in TYPE_MAP.items():
        if k and k in raw:
            return v
    return {"cloze": "cloze", "sentence_reorder": "sentence_build", "short_text": "reading_qa",
            "fill_blank": "grammar_fill", "choice": "single_choice"}.get(kind, "reading_qa")


def migrate(db: Path) -> None:
    """补字段：group_uid / material_text / trust_level / exam_title。"""
    if not db.exists():
        return
    c = connect(db)
    cols = {r[1] for r in c.execute("PRAGMA table_info(questions)")}
    for name, decl in (("group_uid", "TEXT"), ("material_text", "TEXT"),
                       ("trust_level", "TEXT"), ("exam_title", "TEXT")):
        if name not in cols:
            c.execute(f"ALTER TABLE questions ADD COLUMN {name} {decl}")
            print(f"  + {db.name}: 加字段 {name}")
    c.execute("CREATE INDEX IF NOT EXISTS idx_q_group ON questions(group_uid)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_q_trust ON questions(trust_level)")
    c.commit()
    c.close()


def parse_v2(path: Path, d: dict) -> list[dict]:
    """英语真题（sections 结构）→ 题目列表（含 group/material）。"""
    ex = d.get("exam") or {}
    out: list[dict] = []
    title = d.get("title") or ""
    for si, sec in enumerate(ex.get("sections") or []):
        kind = sec.get("kind") or ""
        disp = sec.get("displayName") or kind
        qtype = map_type(disp, kind)
        directions = blocks_text(sec.get("directions"))
        material = "\n\n".join(blocks_text(m) for m in (sec.get("materials") or []) if blocks_text(m))
        group = f"{d.get('id')}-s{si}"
        for it in sec.get("items") or []:
            if not isinstance(it, dict):
                continue
            stem = blocks_text(it.get("stem"))
            # 材料型题目（阅读填空/阅读理解）题干为空 → 用材料 + 该题的小题干拼接
            ref = blocks_text(it.get("referenceAnswer"))
            spec = it.get("answerSpec") or {}
            vals = spec.get("values") if isinstance(spec.get("values"), list) else []
            answers = [strip_html(str(v)) for v in vals if str(v).strip()]
            answer = " | ".join(dict.fromkeys(answers)) or ref
            analysis = blocks_text(it.get("analysis"))
            if not answer:
                continue
            out.append({
                "no": it.get("no"), "qtype": qtype, "display": disp,
                "stem": stem, "material": material, "group_uid": group,
                "directions": directions, "answer": answer, "explanation": analysis,
                "title": title, "interaction": (it.get("interaction") or {}).get("type") or "",
            })
    return out


def parse_flat(path: Path, d: dict) -> list[dict]:
    """C语言/教材题（meta/questions 结构）。"""
    ex = d.get("exam") or {}
    meta = ex.get("meta") or {}
    out: list[dict] = []
    for q in ex.get("questions") or []:
        if not isinstance(q, dict):
            continue
        content = strip_html(q.get("content") or "")
        raw_type = q.get("type") or ""
        qtype = map_type(raw_type)
        ans = q.get("answer")
        if isinstance(ans, list):
            answer = " | ".join(str(a).strip() for a in ans if str(a).strip())
        else:
            answer = strip_html(str(ans or ""))
        opts = q.get("options")
        if isinstance(opts, list) and opts:
            # 选项转成 A./B./C./D. 文本（renderer 会按行显示）
            letters = "ABCDEFGH"
            answer = answer or ""
            opts_txt = [f"{letters[i]}. {strip_html(str(o))}" for i, o in enumerate(opts) if str(o).strip()]
            content = content.replace("{{__SELECT_1__}}", " ______ ").strip()
            stem = content + "\n" + "\n".join(opts_txt)
            qtype = qtype if qtype != "reading_qa" else "single_choice"
        else:
            stem = content
        if not stem or not answer:
            continue
        chapter = ((q.get("source") or {}).get("chapter") or "").strip()
        out.append({
            "no": q.get("id"), "qtype": qtype, "display": raw_type, "stem": stem,
            "material": "", "group_uid": f"{d.get('id')}-q{q.get('id')}",
            "directions": "", "answer": answer,
            "explanation": strip_html(q.get("analysis") or ""),
            "title": d.get("title") or "", "knowledge_point": chapter,
            "difficulty": q.get("difficulty") or "中",
        })
    return out


def subject_of(title: str, subject_field: str) -> tuple[str, str]:
    """→ (科目, trust_level)。

    ⚠️ 顺序很关键：**先判"英语"**，再判各校专业课。
    首版把 `("湖北",) → english` 放在最前，结果「湖北理工学院专升本专业课考试」这类
    标题也被判成英语（因为它含"湖北"）—— 分类全错。
    """
    t, sf = title or "", subject_field or ""
    if "英语" in t or "英语" in sf:
        return "english", "official_exam"
    for kws, subj in COLLEGE_TO_SUBJECT:
        if any(k in t for k in kws):
            return subj, "textbook"
    if "C语言" in sf or "程序设计" in sf or "数据结构" in sf or "软件" in t:
        return "c_wuhan", "textbook"
    return "c_wuhan", "textbook"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--replace-ai", action="store_true",
                    help="把 C 语言里 AI 生成的题置为 rejected（被真题取代）")
    args = ap.parse_args()
    if not args.dry_run and not args.apply:
        print("请指定 --dry-run 或 --apply")
        return 2

    for s in ("english", "c_wuhan", "c_hbpu", "aca_llm"):
        migrate(DATA / f"{s}.sqlite")

    stats: Counter = Counter()
    per_exam: list[tuple] = []
    for f in sorted(SRC.glob("*.json")):
        if f.name.startswith("_") or f.name.startswith("aihaoti_"):
            continue
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            stats["文件解析失败"] += 1
            print(f"  [skip] {f.name}: {e}")
            continue
        ex = d.get("exam") or {}
        if isinstance(ex.get("sections"), list) and ex["sections"]:
            items = parse_v2(f, d)
            kind = "英语真题(sections)"
        elif isinstance(ex.get("questions"), list) and ex["questions"]:
            items = parse_flat(f, d)
            kind = "教材/专业课(questions)"
        else:
            stats["未知结构"] += 1
            continue
        if not items:
            continue
        subj, trust = subject_of(d.get("title") or "", d.get("subject") or "")
        stats[f"{kind}"] += 1
        stats[f"{subj}:{trust}"] += len(items)
        per_exam.append((d.get("title"), subj, trust, len(items), len({i['group_uid'] for i in items})))
        if args.dry_run:
            continue
        db = DATA / f"{subj}.sqlite"
        conn = connect(db)
        for it in items:
            uid = generate_uid(subj, f"real:{d.get('id')}", f"{it['group_uid']}|{it['no']}|{it['stem'][:80]}")
            conn.execute(
                """INSERT OR IGNORE INTO questions
                   (question_uid, subject, source_type, source_url, source_credit, question_type, stem,
                    options, answer, explanation, knowledge_point, difficulty, status, version,
                    fact_claim, fact_source, fact_verified, group_uid, material_text, trust_level, exam_title)
                   VALUES (?,?,'real_exam',?,?,?,?,?,?,?,?,?, 'approved', 1, ?, ?, 1, ?, ?, ?, ?)""",
                (uid, subj, f"aihaoti:{d.get('id')}", it.get("title") or "", it["qtype"], it["stem"],
                 "[]", it["answer"], it.get("explanation") or "",
                 it.get("knowledge_point") or "", it.get("difficulty") or "中",
                 it.get("directions") or "", f"真题/教材：{it.get('title') or ''}", 
                 it["group_uid"], it.get("material") or "", trust, it.get("title") or ""),
            )
        conn.commit()
        conn.close()

    print("\n=== 解析结果 ===")
    for t, s, tr, n, g in per_exam:
        print(f"  {str(t)[:30]:<32} → {s:<8} {tr:<14} {n:>4} 题 / {g:>3} 组")
    print("\n统计:", dict(stats))
    print("总题数:", sum(v for k, v in stats.items() if ":" in k))

    if args.apply and args.replace_ai:
        for subj in ("c_wuhan", "c_hbpu"):
            conn = connect(DATA / f"{subj}.sqlite")
            n = conn.execute("SELECT count(*) FROM questions WHERE source_type='generate' AND status='approved'").fetchone()[0]
            conn.execute("UPDATE questions SET status='rejected', reviewed_by='replaced-by-real-exam' "
                         "WHERE source_type='generate' AND status='approved'")
            conn.commit()
            conn.close()
            print(f"  {subj}: 已把 {n} 道 AI 生成题标记为 rejected（被真题取代）")

    if not args.dry_run:
        print("\n⚠️ 注意：新入库的题 status=approved 且 fact_verified=1（真题自带答案与解析）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
