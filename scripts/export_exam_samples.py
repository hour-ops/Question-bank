#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""按「科目 / 题型」把全部真题整编成样板库（**纯本地、零 API 花费**）。

产出 `data/exam_samples/`：
    _index.json          总索引（各科目/题型样例数、来源卷、知识点覆盖、与旧库关系）
    _knowledge_map.json  题型 ↔ 知识点 映射（来自三个知识点库）
    english/<type>.json
    c_common/<type>.json
    aca_llm/_NO_REAL_EXAM.json

设计要点（每条都对应一个已知数据陷阱，见 --help-epilogue 与 _index.json 的 design_notes）：
  1. **只读原始 JSON**（`inbox/real_exams/*.json`），不从 SQLite 读题干。
     原因：`scripts/import_real_exams.py` 的 `strip_html()` 把 `#include <stdio.h>`
     整段当成 HTML 标签删掉了，库里存的是 `#include `（已实测）。原始 JSON 无此损伤。
  2. **题目原文零改写**：题干/材料/答案/解析全部按原样落盘；
     唯一的"渲染"是把 `{type:'blank'}` 块显式写成 `{{__BLANK_<n>__}}`（源里它只是一段空白，
     不标出来材料就读不通），连词成句保留真题的 `词组 / 词组` 斜杠格式。
  3. **材料型题整组不拆**：一篇短文 + 它的全部空 = 一条 sample（`material` + `material_blanks`）。
     脚本内有断言：sample 的空数必须等于源里的空数，不等则记入 `_index.json.validation_issues`。
  4. **优先取有解析的**，并按 `exam` 轮转取样（保证每套卷都有代表），默认每题型上限 40 条。
  5. **同题干去重**：多校同卷（如 042/043/044 字节完全相同）只留 1 条，重复来源记在
     `same_stem_exams` 里 —— 让 40 条样例尽量覆盖不同考点，而不是同一题的 20 份拷贝。
  6. 题型 ↔ 知识点：C 语言用 `c_common.knowledge_points[].alias_chapters` 反查；
     英语用 `english.question_type_to_points`；对不上的记 `unmapped` 并写明原因。

用法:
    python scripts/export_exam_samples.py                     # 生成
    python scripts/export_exam_samples.py --dry-run           # 只统计不写盘
    python scripts/export_exam_samples.py --per-type 40       # 改每题型上限
    python scripts/export_exam_samples.py --no-dedupe         # 关闭同题干去重
    python scripts/export_exam_samples.py --proof             # 生成后打印材料型整组证明
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from collections import Counter, OrderedDict, defaultdict
from datetime import datetime, timezone
from pathlib import Path

# 中文 Windows 控制台默认 GBK：把无法编码的字符替换掉，别让打印把脚本搞崩
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(errors="replace")
    except Exception:  # noqa: BLE001
        pass

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "inbox" / "real_exams"
OUTDIR = ROOT / "data" / "exam_samples"
OLD_REF = ROOT / "data" / "generation_reference.json"
DATA = ROOT / "data"

SCHEMA_VERSION = "1.0"

# ----------------------------------------------------------------------------
# 题型映射（原始题型名 → 本项目题型 key）
# ----------------------------------------------------------------------------
# 英语：sections 型的 section.displayName / questions 型的 question.type
TYPE_MAP_EN = {
    "语法填空": "grammar_fill",
    "连词成句": "sentence_build",
    "阅读填空": "reading_fill", "阅读填词": "reading_fill",
    "阅读填空 / 词汇填空": "reading_fill", "填空题": "reading_fill",   # 湖北 2020/2022 卷把阅读填空写作「填空题」
    "阅读理解": "reading_qa", "阅读理解 Section B": "reading_qa",
    "阅读理解 Passage 1": "reading_qa", "阅读理解 Passage 2": "reading_qa",
    "Reading Comprehension": "reading_qa",
    "Reading Comprehension Passage 1": "reading_qa",
    "Reading Comprehension Passage 2": "reading_qa",
    "Reading Comprehension Section B": "word_fill",   # 带词库(word bank)的选词填空
    "选词填空": "word_fill", "词汇填空": "word_fill",
    "完形填空": "cloze", "Cloze": "cloze",
    "情景对话": "dialogue", "Situational Dialogue": "dialogue",
    "语音题": "phonetics", "语音": "phonetics", "语音知识": "phonetics", "Phonetics": "phonetics",
    "词汇与结构": "single_choice", "词汇与语法结构": "single_choice",
    "词汇与语法": "single_choice", "单选题": "single_choice", "单项选择": "single_choice",
    "英译汉选择": "translation_choice",
    "英译汉": "translation", "段落翻译": "translation", "翻译题": "translation",
    "翻译填空": "translation_fill", "完成句子": "sentence_completion",
    "写作": "writing", "书面表达": "writing", "Writing": "writing",
    "写作题": "writing", "作文": "writing", "书信写作": "writing",
    "提纲填空": "outline_fill",
}

# C 语言 / 程序设计：questions 型的 question.type
TYPE_MAP_C = {
    "填空题": "program_fill", "程序填空题": "program_fill",
    "单选题": "single_choice", "选择题": "single_choice", "多选题": "multiple_choice",
    "判断题": "true_false",
    "编程题": "programming",
    "程序阅读题": "reading_qa",
    "改错题": "code_correction", "程序改错题": "code_correction",
}

# sections 型 kind 兜底
KIND_FALLBACK = {
    "cloze": "cloze", "single_choice": "single_choice", "reading_qa": "reading_qa",
    "writing": "writing", "translation_paragraph": "translation",
    "translation_fill": "translation_fill", "sentence_reorder": "sentence_build",
    "fill_blank": "reading_fill", "short_text": "translation_fill",
    "dialogue": "dialogue", "phonetics": "phonetics", "word_fill": "word_fill",
}

# 这些题型天然是「一篇文章 + 若干空」的材料型
MATERIAL_TYPES = {"grammar_fill", "reading_fill", "reading_qa", "word_fill", "cloze",
                  "dialogue", "outline_fill"}

# 题型中文名（C 语言里 reading_qa 实际是「程序阅读题」，与英语的「阅读理解」同名不同义）
TYPE_NAME_CN_C = {"reading_qa": "程序阅读题（读程序写结果）", "program_fill": "程序填空",
                  "single_choice": "单选题", "multiple_choice": "多选题",
                  "true_false": "判断题", "programming": "编程题",
                  "code_correction": "程序改错"}

COLLEGE_HBPU = ("湖北理工学院",)

BLANK_RE = re.compile(r"\{\{__BLANK_(\d+)__\}\}")
SELECT_RE = re.compile(r"\{\{__SELECT_(\d+)__\}\}")
PLACEHOLDER_RE = re.compile(r"\{\{__(?:BLANK|SELECT)_(\d+)__\}\}")
NUM_LINE_RE = re.compile(r"(?m)^\s*(\d{1,2})\s*[.、．)）]\s*")
DIRECTIONS_RE = re.compile(r"^\s*Directions?\s*[:：]", re.I)


# ----------------------------------------------------------------------------
# 通用工具
# ----------------------------------------------------------------------------
def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def load_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8-sig"))


def dump_json(p: Path, obj) -> int:
    p.parent.mkdir(parents=True, exist_ok=True)
    txt = json.dumps(obj, ensure_ascii=False, indent=2)
    p.write_text(txt, encoding="utf-8", newline="\n")
    return p.stat().st_size


def blocks_text(node, blank_fmt: str = "{{__BLANK_%s__}}") -> str:
    """`{blocks:[{type,value|blank}]}` → 文本。

    与旧脚本不同：`{type:'blank'}` 块**显式**渲染成 `{{__BLANK_<n>__}}`（不再变成空白），
    否则材料里被挖掉的位置读不通、也核对不出空数。markdown 块之间的分段用空行保留。
    """
    if isinstance(node, str):
        return node.strip()
    if not isinstance(node, dict):
        return ""
    bs = node.get("blocks")
    if not isinstance(bs, list):
        for k in ("value", "text", "content"):
            if isinstance(node.get(k), str):
                return node[k].strip()
        return ""

    segs = []
    for b in bs:
        if not isinstance(b, dict):
            continue
        if b.get("type") == "blank":
            key = str(b.get("placeholder") or b.get("key") or "").strip()
            segs.append(("blank", (blank_fmt % key) if key else "____"))
        else:
            v = str(b.get("value") or "")
            segs.append(("para", "") if not v.strip() else ("text", v))

    out, prev, pending = [], None, False
    for kind, val in segs:
        if kind == "para":
            pending = True
            continue
        sep = ""
        if kind == "text" and (prev == "text" or (prev is not None and pending)):
            sep = "\n\n"
        elif kind == "text" and prev is None:
            sep = ""
        out.append(sep + val)
        if kind == "text":
            pending = False
        prev = kind
    return "".join(out).strip()


def strip_leading_directions(text: str):
    """拆出开头的 Directions 段 → (directions, rest)。只用于**判断**是否材料型，不改写原文。"""
    if not text or not DIRECTIONS_RE.match(text):
        return "", text
    idx = text.find("\n\n")
    if idx < 0:
        return text.strip(), ""
    return text[:idx].strip(), text[idx:].strip()


def dedup_keep_order(seq):
    seen, out = set(), []
    for x in seq:
        x = str(x).strip()
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


def split_numbered_analysis(text: str, n: int) -> dict:
    """把 `1. xxx\\n2. yyy` 形式的整段解析按序号切给各个空。切不动就返回 {}。"""
    if not text or n <= 1:
        return {}
    hits = list(NUM_LINE_RE.finditer(text))
    if len(hits) < n:
        return {}
    got = {}
    for i, m in enumerate(hits):
        num = int(m.group(1))
        if not (1 <= num <= n) or num in got:
            continue
        end = hits[i + 1].start() if i + 1 < len(hits) else len(text)
        got[num] = text[m.start():end].strip()
    return got if len(got) == n else {}


def norm_chapter(name: str) -> str:
    """与 tests/build_c_kb.py 的 denum() 保持一致：剥掉「第N章」前缀。"""
    return re.sub(r"^第\s*\d+\s*章\s*", "", (name or "").strip()).strip()


# 源数据缺答案的记账（不静默丢；汇总进 _index.json 的 source_data_gaps）
SOURCE_GAPS: list = []


# ----------------------------------------------------------------------------
# 知识点库
# ----------------------------------------------------------------------------
def load_knowledge_bases():
    kb = {}
    for name in ("english", "c_common", "aca_llm"):
        kb[name] = load_json(ROOT / "subjects" / name / "knowledge_base.json")
    return kb


def build_kp_index(kb):
    """→ (全部知识点 dict, 章节名→知识点id 反查表, 题型→知识点id 列表)"""
    out = {}

    # ---- english：题型维度 E-T* / 语言知识维度 E-G* / 阅读技能 E-S*
    en = kb["english"]
    points = {}
    for p in en.get("knowledge_points") or []:
        points[p["id"]] = {"id": p["id"], "name": p.get("name"),
                           "dimension": p.get("dimension"),
                           "question_type": p.get("question_type"),
                           "format_era": p.get("format_era")}
    t2p = {t: list(v) for t, v in (en.get("question_type_to_points") or {}).items()}
    out["english"] = {"kb_path": "subjects/english/knowledge_base.json",
                      "points": points, "chapter_index": {}, "type_to_points": t2p,
                      "basis": "题型维度(E-T*) + 语言知识维度(E-G*/E-S*)，映射取自 knowledge_base.json 的 question_type_to_points"}

    # ---- c_common：15 个知识点，alias_chapters 反查
    cc = kb["c_common"]
    cpoints, chap_index, collisions = {}, {}, []
    for p in cc.get("knowledge_points") or []:
        cpoints[p["id"]] = {"id": p["id"], "name": p.get("name"), "dimension": "chapter",
                            "desc": p.get("desc")}
        for alias in p.get("alias_chapters") or []:
            a = str(alias).strip()
            if a in chap_index and chap_index[a] != p["id"]:
                collisions.append({"chapter": a, "kept": chap_index[a], "dropped": p["id"]})
            else:
                chap_index[a] = p["id"]
    out["c_common"] = {"kb_path": "subjects/c_common/knowledge_base.json",
                       "points": cpoints, "chapter_index": chap_index, "type_to_points": {},
                       "basis": "题型无关：C 语言的知识点由原题教材章节名(source.chapter)决定，"
                                "经 knowledge_points[].alias_chapters 反查（190 个别名）",
                       "alias_collisions": collisions}

    # ---- aca_llm：六大模块 252 点
    ac = kb["aca_llm"]
    apoints = {}
    for m in ac.get("modules") or []:
        for p in m.get("points") or []:
            apoints[p["id"]] = {"id": p["id"], "name": p.get("name"),
                                "dimension": "module",
                                "module_no": m.get("no"), "module": m.get("name"),
                                "lesson": p.get("lesson"), "difficulty": p.get("difficulty")}
    out["aca_llm"] = {"kb_path": "subjects/aca_llm/knowledge_base.json",
                      "points": apoints, "chapter_index": {}, "type_to_points": {},
                      "basis": "六大模块 252 个知识点（模块/课时定位）；无官方真题，故无题型↔知识点实测映射"}
    return out


# ----------------------------------------------------------------------------
# 真题解析 → 记录（record）
# ----------------------------------------------------------------------------
def exam_meta(path: Path):
    d = load_json(path)
    title = d.get("title") or ""
    raw_subject = d.get("subject") or ""
    if raw_subject == "英语" or "英语" in title:
        subject, trust = "english", "official_exam"
    else:
        subject, trust = "c_common", "textbook"
    origin_db = "c_hbpu" if any(k in title for k in COLLEGE_HBPU) else ("c_wuhan" if subject == "c_common" else None)
    school = ""
    if subject == "c_common":
        school = re.sub(r"(专升本专业课考试|专升本教材|专升本|软件工程)$", "", title).strip() or title
    return d, subject, trust, origin_db, school


def map_en_type(raw: str) -> str:
    raw = (raw or "").strip()
    if raw in TYPE_MAP_EN:
        return TYPE_MAP_EN[raw]
    for k, v in TYPE_MAP_EN.items():
        if k and k in raw:
            return v
    return ""


def map_c_type(raw: str) -> str:
    raw = (raw or "").strip()
    if raw in TYPE_MAP_C:
        return TYPE_MAP_C[raw]
    for k, v in TYPE_MAP_C.items():
        if k and k in raw:
            return v
    return ""


def has_cjk(s: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", s or ""))


# ---- sections 型（英语 v2）--------------------------------------------------
def records_from_sections(path: Path, d, subject, trust, origin_db, school, issues):
    ex = d.get("exam") or {}
    recs = []
    for si, sec in enumerate(ex.get("sections") or []):
        if not isinstance(sec, dict):
            continue
        disp = (sec.get("displayName") or sec.get("kind") or "").strip()
        kind = (sec.get("kind") or "").strip()
        qtype = map_en_type(disp) or KIND_FALLBACK.get(kind, "")
        if not qtype:
            issues.append({"exam": path.name, "where": f"s{si}", "issue": f"题型无法映射: displayName={disp!r} kind={kind!r}"})
            qtype = "unmapped:" + (disp or kind or "?")
        items = [it for it in (sec.get("items") or []) if isinstance(it, dict)]
        materials = [blocks_text(m) for m in (sec.get("materials") or [])]
        materials = [m for m in materials if m]
        material_txt = "\n\n".join(materials)
        directions = blocks_text(sec.get("directions"))
        bank = [str(c.get("label") or c.get("key") or "") for c in (sec.get("sharedChoices") or [])
                if isinstance(c, dict)]
        group_uid = f"{d.get('id')}-s{si}"

        def mk_item(it):
            stem = blocks_text(it.get("stem"))
            spec = it.get("answerSpec") or {}
            st = spec.get("type")
            ans, blanks = [], []
            if st == "one_of":
                ans = list(spec.get("values") or [])
            elif st == "exact":
                ans = [spec.get("value")]
            elif st == "blank_set":
                for a in spec.get("answers") or []:
                    acc = a.get("accepted") or []
                    ans.append(" / ".join(str(x) for x in acc))
                    blanks.append({"no": it.get("no"), "placeholder": a.get("target"),
                                   "stem": stem, "answer": " / ".join(str(x) for x in acc),
                                   "explanation": blocks_text(it.get("analysis"))})
            ref = blocks_text(it.get("referenceAnswer"))
            if not ans:
                ans = [ref] if ref else []
            answer = " | ".join(dedup_keep_order(ans))
            choices = [str(c.get("label") or "") for c in ((it.get("interaction") or {}).get("choices") or [])
                       if isinstance(c, dict)]
            inter = (it.get("interaction") or {}).get("type") or ""
            # 语音题这类：题干在源里是空块，真正的提问写在 section.directions 里
            # （「Compare the underlined parts and identify the one that is different…」）。
            # 无材料又无题干时把 directions 原文提上来当题干 —— 仍是零改写（directions 字段同时保留）。
            if not stem and not material_txt:
                stem = directions
            return {"stem": stem, "answer": answer,
                    "explanation": blocks_text(it.get("analysis")),
                    "options": [c for c in choices if c.strip()],
                    "interaction": inter,
                    "blanks": blanks, "no": it.get("no")}

        if material_txt:
            # 材料型：整组一条 sample
            blanks, ans_list, expl_list = [], [], []
            for it in items:
                r = mk_item(it)
                if r["blanks"]:
                    for b in r["blanks"]:
                        blanks.append(b)
                        ans_list.append(b["answer"])
                        expl_list.append(b["explanation"])
                else:
                    blanks.append({"no": it.get("no"), "placeholder": None,
                                   "stem": r["stem"], "answer": r["answer"],
                                   "explanation": r["explanation"],
                                   "options": r["options"]})
                    ans_list.append(r["answer"])
                    expl_list.append(r["explanation"])
            expected = len(items)
            if len(blanks) != expected:
                issues.append({"exam": path.name, "where": group_uid,
                               "issue": f"空数不符: 组内 {len(blanks)} 个空 vs section {expected} 题"})
            n_ans = sum(1 for b in blanks if b["answer"].strip())
            if n_ans == 0:
                # 源卷整卷无答案（107_英语_河北专升本英语22.json 全部 answerSpec='manual_only'）
                SOURCE_GAPS.append({"exam": path.name, "where": group_uid, "type": qtype,
                                    "blanks": len(blanks), "reason": "整组无标准答案（源卷缺答案）"})
                continue
            rec = {
                "subject": subject, "origin_db": origin_db, "school": school,
                "exam_file": path.name, "exam_title": d.get("title") or "",
                "trust": trust, "type": qtype, "type_raw": disp, "kind": "material",
                "group_uid": group_uid, "no": None,
                "stem": "", "answer": " | ".join(dedup_keep_order(ans_list)),
                "explanation": "\n\n".join(x for x in dedup_keep_order(expl_list)),
                "explanation_source": "blanks_joined",
                "material": material_txt, "material_blanks": blanks,
                "material_blocks_total": len(blanks), "materials_count": len(materials),
                "directions": directions, "options": [],
                "word_bank": bank or None, "type_source": "section.displayName/materials",
            }
            if n_ans < len(blanks):
                rec["blanks_without_answer"] = len(blanks) - n_ans
                SOURCE_GAPS.append({"exam": path.name, "where": group_uid, "type": qtype,
                                    "blanks": len(blanks), "blanks_without_answer": len(blanks) - n_ans,
                                    "reason": "组内部分空缺答案（源卷）"})
            recs.append(rec)
        else:
            for i, it in enumerate(items):
                r = mk_item(it)
                if not r["answer"]:
                    issues.append({"exam": path.name, "where": f"{group_uid}-i{i}",
                                   "issue": "无答案，已跳过"})
                    continue
                recs.append({
                    "subject": subject, "origin_db": origin_db, "school": school,
                    "exam_file": path.name, "exam_title": d.get("title") or "",
                    "trust": trust, "type": qtype, "type_raw": disp, "kind": "single",
                    "group_uid": f"{group_uid}-i{i}", "no": r["no"],
                    "stem": r["stem"], "answer": r["answer"], "explanation": r["explanation"],
                    "explanation_source": "item" if r["explanation"] else "",
                    "material": "", "material_blanks": [], "material_blocks_total": 0,
                    "materials_count": 0, "directions": directions,
                    "options": r["options"], "word_bank": bank or None,
                    "type_source": "section.displayName",
                })
    return recs


# ---- questions 型（C 语言题库 / 英语 2020-2026 老结构）----------------------
def records_from_questions(path: Path, d, subject, trust, origin_db, school, issues):
    ex = d.get("exam") or {}
    recs = []
    is_en = subject == "english"
    for q in ex.get("questions") or []:
        if not isinstance(q, dict):
            continue
        qid = q.get("id")
        raw_type = (q.get("type") or "").strip()
        content = q.get("content") or ""
        options = [str(o) for o in (q.get("options") or []) if str(o).strip()]
        answer_raw = q.get("answer")
        analysis = q.get("analysis") or ""
        subs = [s for s in (q.get("subQuestions") or []) if isinstance(s, dict)]
        chapter = ((q.get("source") or {}).get("chapter") or "").strip()

        if is_en:
            qtype = map_en_type(raw_type)
        else:
            qtype = map_c_type(raw_type)
        if not qtype:
            issues.append({"exam": path.name, "where": f"q{qid}",
                           "issue": f"题型无法映射: type={raw_type!r}"})
            qtype = "unmapped:" + (raw_type or "?")

        # 把 content 开头的 Directions 拆出来（只用于判断，原文不动）
        directions, rest = strip_leading_directions(content)
        # ⚠️ 两种占位符含义不同，不能混：
        #   {{__BLANK_n__}}  = 填空位 → 一个题项含 ≥2 个且答案数对得上，才算「材料组」
        #   {{__SELECT_n__}} = 题内选择位（如 `… 是 {{__SELECT_1__}}，… 是 {{__SELECT_2__}}`）
        #                      这种是**一道**多空单选题，不是材料组（030 q152 / 048 q4 即此）
        n_blank = len(BLANK_RE.findall(content))
        n_select = len(SELECT_RE.findall(content))
        ans_list = answer_raw if isinstance(answer_raw, list) else ([answer_raw] if str(answer_raw or "").strip() else [])

        def norm_ans(a):
            if isinstance(a, list):
                return " | ".join(dedup_keep_order(a))
            return str(a or "").strip()

        base = {
            "subject": subject, "origin_db": origin_db, "school": school,
            "exam_file": path.name, "exam_title": d.get("title") or "",
            "trust": trust, "type_raw": raw_type, "chapter_raw": chapter,
            "difficulty": q.get("difficulty") or "",
            "is_from_textbook": bool(q.get("isFromTextbook")) if "isFromTextbook" in q else None,
            "type_source": "question.type",
        }

        # ---------- 情况 1：材料型整组（有短文，若干空依赖它） ----------
        #   判据：无子题时，正文里有 ≥2 个填空位**且答案条数对得上**（对不上说明源把多个答案
        #   并成了一条，如 022 q62「2 个空 / 1 条答案」—— 那种按单题存更忠实）；
        #   有子题时，正文里有填空位或去掉 Directions 后仍 ≥300 字符。
        if not subs:
            is_material = n_blank >= 2 and len(ans_list) == n_blank
        else:
            is_material = (n_blank >= 2) or (len(rest) >= 300)

        if is_material:
            blanks = []
            if subs:
                for s in subs:
                    s_content = s.get("content") or ""
                    s_ans = s.get("answer")
                    s_expl = s.get("analysis") or ""
                    s_opts = [str(o) for o in (s.get("options") or []) if str(o).strip()]
                    phs = PLACEHOLDER_RE.findall(s_content)
                    alist = s_ans if isinstance(s_ans, list) else ([s_ans] if str(s_ans or "").strip() else [])
                    if len(phs) >= 2:
                        # 一个子题里挖了多个空（如湖北 2020/2021 的表格型阅读填空）
                        parts = split_numbered_analysis(s_expl, len(phs))
                        shared = s_content if len(phs) > 1 else ""
                        for k in range(len(phs)):
                            blanks.append({"no": s.get("id"), "placeholder": f"{{{{__BLANK_{k+1}__}}}}",
                                           "stem": "" if shared else s_content,
                                           "answer": str(alist[k]).strip() if k < len(alist) else "",
                                           "explanation": parts.get(k + 1, "" if parts else s_expl),
                                           "options": s_opts,
                                           **({"blank_stem_shared": shared} if shared else {})})
                    else:
                        blanks.append({"no": s.get("id"), "placeholder": None,
                                       "stem": s_content, "answer": norm_ans(s_ans),
                                       "explanation": s_expl, "options": s_opts})
            else:
                phs = BLANK_RE.findall(content)          # 只认填空位；{{__SELECT_n__}} 不算
                parts = split_numbered_analysis(analysis, len(phs))
                for k in range(len(phs)):
                    blanks.append({"no": k + 1, "placeholder": f"{{{{__BLANK_{phs[k]}__}}}}",
                                   "stem": "", "answer": str(ans_list[k]).strip() if k < len(ans_list) else "",
                                   "explanation": parts.get(k + 1, "" if parts else ""),
                                   "options": []})
            expected = sum(max(1, len(BLANK_RE.findall(s.get("content") or ""))) for s in subs) if subs else n_blank
            if len(blanks) != expected:
                issues.append({"exam": path.name, "where": f"q{qid}",
                               "issue": f"空数不符: 组内 {len(blanks)} 个空 vs 源 {expected} 空"})
            # 断言：源里的每个答案都必须在某个空里出现（不静默丢答案）
            src_answers = []
            for s in subs:
                a = s.get("answer")
                src_answers += [str(x).strip() for x in (a if isinstance(a, list) else [a]) if str(x or "").strip()]
            if not subs:
                src_answers = [str(x).strip() for x in ans_list if str(x or "").strip()]
            got_answers = {b["answer"].strip() for b in blanks}
            lost = [a for a in src_answers if a not in got_answers and a not in " | ".join(got_answers)]
            if lost:
                issues.append({"exam": path.name, "where": f"q{qid}",
                               "issue": f"{len(lost)} 个答案未进 blanks: {lost[:3]}"})
            n_ans = sum(1 for b in blanks if b["answer"].strip())
            if n_ans == 0:
                # 源卷整题无答案（如 107_英语_河北专升本英语22.json 全卷 answerSpec='manual_only'
                # 且 referenceAnswer 为空）—— 无标准答案的题不能当样板，跳过并如实记账。
                SOURCE_GAPS.append({"exam": path.name, "where": f"q{qid}", "type": qtype,
                                    "blanks": len(blanks), "reason": "整组无标准答案（源卷缺答案）"})
                continue
            expl_joined = "\n\n".join(dedup_keep_order([b["explanation"] for b in blanks]))
            rec = {**base, "type": qtype, "kind": "material",
                   "group_uid": f"{d.get('id')}-q{qid}", "no": None,
                   "stem": "", "answer": " | ".join(dedup_keep_order([b["answer"] for b in blanks])),
                   "explanation": analysis.strip() or expl_joined,
                   "explanation_source": "parent" if analysis.strip() else "blanks_joined",
                   "material": content, "material_blanks": blanks,
                   "material_blocks_total": len(blanks), "materials_count": 1,
                   "directions": directions, "options": [],
                   "word_bank": None,
                   "analysis_split_ok": bool(split_numbered_analysis(analysis, max(n_blank, 1))) if not subs else None}
            if n_ans < len(blanks):
                rec["blanks_without_answer"] = len(blanks) - n_ans
                SOURCE_GAPS.append({"exam": path.name, "where": f"q{qid}", "type": qtype,
                                    "blanks": len(blanks), "blanks_without_answer": len(blanks) - n_ans,
                                    "reason": "组内部分空缺答案（源卷）"})
            recs.append(rec)
            continue

        # ---------- 情况 2：逐子题 / 单题 ----------
        rows = []
        if subs:
            for s in subs:
                rows.append({
                    "stem": s.get("content") or "", "answer": norm_ans(s.get("answer")),
                    "explanation": s.get("analysis") or "",
                    "options": [str(o) for o in (s.get("options") or []) if str(o).strip()],
                    "no": s.get("id"),
                })
        else:
            rows.append({"stem": content, "answer": norm_ans(answer_raw),
                         "explanation": analysis, "options": options, "no": qid})

        MCQ_TYPES = ("单选题", "单项选择", "选择题", "多选题")
        for i, r in enumerate(rows):
            t = qtype
            if is_en:
                # 英语 questions 型的父题名常常很粗（「单选题」「翻译题」），按子题实际形态细分：
                #   · 选项是中文 → 英译汉选择（translation_choice）
                #   · 选项 ≥3 个，或父题本来就是单选 → 单选题
                #   · 只有 2 个选项的语法空（如 2024 卷 `(in/ on)`）→ 仍算语法填空，不降级成单选
                #   · 带空占位符却挂在「翻译题/单选题」下的 → 翻译填空（2024 卷的实际形态）
                opts = r["options"] or []
                if opts and has_cjk(" ".join(opts)):
                    t = "translation_choice"
                elif opts and (len(opts) >= 3 or raw_type in MCQ_TYPES):
                    t = "single_choice"
                elif r["stem"] and PLACEHOLDER_RE.search(r["stem"]) and qtype in ("translation", "single_choice"):
                    t = "translation_fill"
            if not r["answer"]:
                issues.append({"exam": path.name, "where": f"q{qid}-sub{i}",
                               "issue": "无答案，已跳过"})
                continue
            recs.append({**base, "type": t, "kind": "single",
                         "group_uid": f"{d.get('id')}-q{qid}-s{i}", "no": r["no"],
                         "stem": r["stem"], "answer": r["answer"],
                         "explanation": r["explanation"],
                         "explanation_source": "item" if r["explanation"] else "",
                         "material": "", "material_blanks": [], "material_blocks_total": 0,
                         "materials_count": 0, "directions": directions,
                         "options": r["options"], "word_bank": None})
    return recs


# ----------------------------------------------------------------------------
# 全量收集
# ----------------------------------------------------------------------------
def collect(verbose=True):
    issues, recs, exam_index = [], [], []
    SOURCE_GAPS.clear()
    files = [f for f in sorted(SRC.glob("*.json"))
             if not f.name.startswith("_") and not f.name.startswith("aihaoti_")]
    for f in files:
        d, subject, trust, origin_db, school = exam_meta(f)
        ex = d.get("exam") or {}
        secs = ex.get("sections")
        qs = ex.get("questions")
        if isinstance(secs, list) and secs:
            rs = records_from_sections(f, d, subject, trust, origin_db, school, issues)
            struct = "sections"
        elif isinstance(qs, list) and qs:
            rs = records_from_questions(f, d, subject, trust, origin_db, school, issues)
            struct = "questions"
        else:
            issues.append({"exam": f.name, "where": "-",
                           "issue": f"未知/空结构: sections={type(secs).__name__} questions={type(qs).__name__}"})
            continue
        recs.extend(rs)
        exam_index.append({
            "file": f.name, "exam_id": d.get("id"), "title": d.get("title"),
            "subject": subject, "structure": struct, "trust": trust,
            "origin_db": origin_db, "school": school or None,
            "bytes": f.stat().st_size, "records": len(rs),
            "types": dict(sorted(Counter(r["type"] for r in rs).items())),
        })
    if verbose:
        print(f"  扫描 {len(files)} 个文件 → {len(recs)} 条记录（材料组算 1 条）")
    return recs, exam_index, issues


# ----------------------------------------------------------------------------
# 知识点映射
# ----------------------------------------------------------------------------
def map_knowledge(rec, kbi):
    """→ (knowledge_point 显示串, id, 说明)"""
    subj = rec["subject"]
    if subj == "english":
        ids = kbi["english"]["type_to_points"].get(rec["type"]) or []
        pts = kbi["english"]["points"]
        names = [f"{i} {pts[i]['name']}" for i in ids if i in pts]
        if names:
            return "；".join(names), ids, "english.question_type_to_points[%s]" % rec["type"]
        return "", [], "unmapped: 题型 %s 不在 english.knowledge_base.question_type_to_points 里" % rec["type"]
    if subj == "c_common":
        ch = rec.get("chapter_raw") or ""
        if not ch:
            return "", [], "unmapped: 原题未标注教材章节（source.chapter 为空）"
        idx = kbi["c_common"]["chapter_index"]
        kid = idx.get(ch)
        how = "alias_chapters 精确匹配"
        if not kid:
            kid = idx.get(norm_chapter(ch))
            how = "alias_chapters 剥离「第N章」后匹配"
        if not kid:
            for alias, pid in idx.items():
                if alias in ch or ch in alias:
                    kid, how = pid, "alias_chapters 子串匹配"
                    break
        if not kid:
            return "", [], "unmapped: 章节名 %r 不在 alias_chapters 的 190 个里" % ch
        p = kbi["c_common"]["points"][kid]
        return f"{kid} {p['name']}", [kid], f"c_common.{how}（原章节：{ch}）"
    return "", [], "unmapped: 该科目无题型↔知识点映射"


# ----------------------------------------------------------------------------
# 取样
# ----------------------------------------------------------------------------
def stem_hash(rec) -> str:
    """去重键 = 题干 + 选项。

    ⚠️ 必须带上 options：语音题的题干每道都一样（「Compare the underlined parts…」），
    区别全在 A/B/C/D 四个词上；只看题干会把 40 道语音题压成 1 道。
    """
    parts = [(rec.get("stem") or ""), (rec.get("material") or "")]
    parts += list(rec.get("options") or [])
    for b in rec.get("material_blanks") or []:
        parts += [str(b.get("stem") or ""), str(b.get("answer") or "")]
        parts += list(b.get("options") or [])
    key = re.sub(r"\s+", " ", " | ".join(parts)).strip()
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def quality_key(r):
    """比较两条同题干记录的优劣：解析 → 知识点 → 解析长度。"""
    return (bool(r["explanation"].strip()), bool(r["knowledge_point_ids"]),
            len(r["explanation"]))


def pick(records, limit, dedupe=True):
    """优先有解析 → 按 exam 轮转 → 上限 limit。返回 (选中, 统计)"""
    # 1) 同题干去重（记录重复来源），保留"有解析 + 有知识点 + 解析更长"的那条
    by_hash = OrderedDict()
    dupe_exams = defaultdict(list)
    for r in records:
        h = stem_hash(r)
        if h in by_hash:
            dupe_exams[h].append(r["exam_file"])
            by_hash[h] = max(by_hash[h], r, key=quality_key)
        else:
            by_hash[h] = r
    pool = list(by_hash.values()) if dedupe else list(records)

    # 2) 组内排序：有解析优先 → 有知识点优先 → 解析长 → 空多 → 材料长
    def rank(r):
        return (0 if r["explanation"].strip() else 1,
                0 if r["knowledge_point_ids"] else 1,
                -len(r["explanation"]),
                -r.get("material_blocks_total", 0),
                -len(r.get("material") or ""))

    # 3) 按 exam 轮转
    by_exam = defaultdict(list)
    for r in pool:
        by_exam[r["exam_file"]].append(r)
    for k in by_exam:
        by_exam[k].sort(key=rank)
    exams = sorted(by_exam.keys(), key=lambda f: (-len(by_exam[f]), f))
    picked, round_i = [], 0
    while len(picked) < limit:
        added = False
        for e in exams:
            lst = by_exam[e]
            if round_i < len(lst):
                picked.append(lst[round_i])
                added = True
                if len(picked) >= limit:
                    break
        if not added:
            break
        round_i += 1

    for r in picked:
        h = stem_hash(r)
        if dupe_exams.get(h):
            r["same_stem_exams"] = dedup_keep_order(dupe_exams[h])[:8]
            r["same_stem_exam_count"] = len(dupe_exams[h])
    return picked, {
        "usable_records": len(pool),
        "exams_in_type": len(by_exam),
        "duplicated_records_removed": len(records) - len(pool) if dedupe else 0,
        "cap": limit,
        "truncated": len(pool) > len(picked),
        "unique_sources_kept": len({r["exam_file"] for r in picked}),
        "unique_sources_available": len(by_exam),
    }


# ----------------------------------------------------------------------------
# 落盘
# ----------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--per-type", type=int, default=40, help="每题型样例上限（默认 40）")
    ap.add_argument("--no-dedupe", action="store_true", help="关闭同题干去重")
    ap.add_argument("--proof", action="store_true", help="生成后打印材料型整组证明")
    args = ap.parse_args()

    print("=== 1/5 读知识点库 ===")
    kbs = load_knowledge_bases()
    kbi = build_kp_index(kbs)
    for s in ("english", "c_common", "aca_llm"):
        n = len(kbi[s]["points"])
        print(f"  {s:<9} 知识点 {n:>3} 个  章节别名 {len(kbi[s]['chapter_index']):>3} 条  "
              f"题型映射 {len(kbi[s]['type_to_points']):>2} 项")
    if kbi["c_common"]["alias_collisions"]:
        print("  [注意] alias 冲突: " + json.dumps(kbi["c_common"]["alias_collisions"], ensure_ascii=False))

    print("\n=== 2/5 扫描真题 ===")
    recs, exam_index, issues = collect()
    subj_cnt = Counter(r["subject"] for r in recs)
    print("  按科目: " + str(dict(subj_cnt)))
    print("  按结构: " + str(dict(Counter(r["kind"] for r in recs))))
    # 覆盖到的「逻辑小题」数：单选题算 1，材料组按组内空数展开。
    # 注意它**可以大于** 6754：原始 JSON 里有 1 个题项内含多个 `{{__BLANK_n__}}` 的情况
    # （如 014 的语法填空 1 题 = 10 空、017 的阅读填空 1 题 = 5 空）。
    items_covered = sum(r["material_blocks_total"] if r["kind"] == "material" else 1 for r in recs)
    raw_total, raw_by_subject = 0, Counter()
    for f in sorted(SRC.glob("*.json")):
        if f.name.startswith("_") or f.name.startswith("aihaoti_"):
            continue
        d0 = load_json(f)
        subj0 = "english" if (d0.get("subject") == "英语" or "英语" in (d0.get("title") or "")) else "c_common"
        ex = d0.get("exam") or {}
        secs, qs = ex.get("sections"), ex.get("questions")
        n = 0
        if isinstance(secs, list) and secs:
            n = sum(len(s.get("items") or []) for s in secs if isinstance(s, dict))
        elif isinstance(qs, list):
            n = len(qs)
        raw_total += n
        raw_by_subject[subj0] += n
    print(f"  原始题项容器 {raw_total} 个（{dict(raw_by_subject)}）；"
          f"提取记录 {len(recs)} 条；覆盖逻辑小题 {items_covered} 个")
    print("  （逻辑小题 > 题项容器 是正常的：1 个题项可能内含多个 {{__BLANK_n__}}）")

    print("\n=== 3/5 知识点映射 ===")
    unmapped = Counter()
    for r in recs:
        kp, ids, how = map_knowledge(r, kbi)
        r["knowledge_point"], r["knowledge_point_ids"], r["knowledge_point_how"] = kp, ids, how
        if not ids:
            unmapped[how.split("：")[0] if "：" in how else how] += 1
    named = sum(1 for r in recs if r["knowledge_point_ids"])
    print(f"  已映射 {named}/{len(recs)} = {named/len(recs)*100:.1f}%")
    for k, v in unmapped.most_common():
        print(f"    unmapped {v:>5}  {k}")
    if SOURCE_GAPS:
        print(f"  源数据缺答案而排除: {len(SOURCE_GAPS)} 条/组 -> "
              + str(dict(Counter(g['exam'] for g in SOURCE_GAPS).most_common(5))))

    print("\n=== 4/5 按科目/题型取样 ===")
    disp = load_json(ROOT / "config" / "display.json")
    disp_types = disp.get("types") or {}
    groups = defaultdict(list)
    for r in recs:
        groups[(r["subject"], r["type"])].append(r)

    # 同卷双版本探测：湖北卷同时存在 sections 版与 questions 版
    year_of = defaultdict(list)
    for e in exam_index:
        m = re.search(r"湖北.*?(\d{4})", str(e["title"] or "")) or re.search(r"(\d{4})", str(e["title"] or ""))
        if m and e["subject"] == "english":
            year_of[m.group(1)].append({"exam": e["file"], "title": e["title"],
                                        "structure": e["structure"], "records": e["records"]})
    dup_groups = [{"year": y, "versions": v} for y, v in sorted(year_of.items()) if len(v) > 1]
    if dup_groups:
        print(f"  同卷双版本：{len(dup_groups)} 组（" +
              ", ".join(f"{g['year']}×{len(g['versions'])}" for g in dup_groups) + "）")

    files_out, index_types = {}, {}
    for (subj, t), lst in sorted(groups.items()):
        picked, st = pick(lst, args.per_type, dedupe=not args.no_dedupe)
        kp_list = kbi[subj]["type_to_points"].get(t) or []
        kp_objs = []
        for i in kp_list:
            p = kbi[subj]["points"].get(i)
            if p:
                kp_objs.append({k: v for k, v in p.items() if v is not None})
        if subj == "c_common":
            # C 语言：题型不决定知识点，列出该题型实际出现过的知识点
            seen = Counter()
            for r in picked:
                if r["knowledge_point"]:
                    seen[r["knowledge_point"]] += 1
            kp_objs = [{"id": k.split()[0], "name": " ".join(k.split()[1:]),
                        "dimension": "chapter", "sample_count": v}
                       for k, v in seen.most_common()]
        how = disp_types.get(t, {}).get("how", "")
        name_cn = (TYPE_NAME_CN_C.get(t) if subj == "c_common" else None) or disp_types.get(t, {}).get("name") or t
        doc = OrderedDict([
            ("schema_version", SCHEMA_VERSION),
            ("subject", subj),
            ("subject_name_cn", disp.get("subject_names", {}).get(subj, subj)),
            ("type", t),
            ("type_name_cn", name_cn),
            ("how", how),
            ("answer_label", disp_types.get(t, {}).get("answer_label", "参考答案")),
            ("knowledge_points", kp_objs),
            ("knowledge_point_basis", kbi[subj]["basis"]),
            ("knowledge_base", kbi[subj]["kb_path"]),
            ("source", "inbox/real_exams/*.json（只读；不从 SQLite 取题干）"),
            ("type_raw_values", sorted({r["type_raw"] for r in picked})),
            ("built_at", now_iso()),
            ("built_by", "scripts/export_exam_samples.py"),
            ("rules", {
                "trust_priority": ["official_exam", "textbook", "third_party"],
                "exclude": ["ai_generated", "source_type='generate'"],
                "prefer": "有解析者优先；其次解析更长、空更多、材料更长",
                "sampling": f"按 exam 轮转（每套卷先取 1 条再取第 2 条…），上限 {args.per_type} 条",
                "dedupe": "关闭" if args.no_dedupe else "同题干（去空白差异）只留解析最好的一条，其余来源记在 same_stem_exams",
                "material_rule": "材料型题整组存：material 存整篇原文、material_blanks 存该组全部空（空数经断言校验）；材料型 sample 的 stem 为空串，题干在各空的 stem 里",
                "zero_rewrite": "题干/材料/答案/解析零改写；唯一渲染是把源里的 {type:'blank'} 块显式写成 {{__BLANK_<n>__}}；连词成句保留 `词组 / 词组` 斜杠格式",
                "deterministic": "不使用随机数；排序键固定为 (exam, 组内 rank)",
            }),
            ("stats", {
                "samples": len(picked),
                "source_records": len(lst),
                "with_explanation": sum(1 for r in picked if r["explanation"].strip()),
                "material_blocks": sum(1 for r in picked if r["kind"] == "material"),
                "total_blanks_in_material_blocks": sum(r["material_blocks_total"] for r in picked),
                "blanks_with_own_stem": sum(
                    1 for r in picked for b in (r["material_blanks"] or [])
                    if str(b.get("stem") or "").strip()),
                **st,
            }),
            ("exams", [{"exam": e, "samples": n} for e, n in
                       Counter(r["exam_file"] for r in picked).most_common()]),
            ("samples", []),
        ])
        for r in picked:
            s = OrderedDict([
                ("stem", r["stem"]),
                ("answer", r["answer"]),
                ("explanation", r["explanation"]),
                ("exam", r["exam_file"]),
                ("exam_title", r["exam_title"]),
                ("trust", r["trust"]),
                ("knowledge_point", r["knowledge_point"]),
                ("material", r["material"]),
                ("type", r["type"]),
                ("type_raw", r["type_raw"]),
                ("kind", r["kind"]),
                ("group_uid", r["group_uid"]),
                ("no", r["no"]),
                ("options", r["options"]),
                ("word_bank", r["word_bank"]),
                ("directions", r["directions"]),
                ("explanation_source", r["explanation_source"]),
                ("material_blanks_total", r["material_blocks_total"]),
                ("material_blanks", r["material_blanks"]),
                ("knowledge_point_ids", r["knowledge_point_ids"]),
                ("knowledge_point_how", r["knowledge_point_how"]),
                ("origin_db", r["origin_db"]),
                ("school", r["school"] or None),
                ("chapter_raw", r.get("chapter_raw") or None),
                ("difficulty", r.get("difficulty") or None),
                ("same_stem_exams", r.get("same_stem_exams")),
                ("same_stem_exam_count", r.get("same_stem_exam_count")),
            ])
            doc["samples"].append(s)
        files_out[(subj, t)] = doc
        index_types.setdefault(subj, OrderedDict())[t] = doc
        print(f"  {subj:<9} {t:<20} {len(picked):>3} 条  (可用 {st['usable_records']:>4} / "
              f"来源卷 {st['unique_sources_kept']}/{st['unique_sources_available']}"
              f"{' 截断' if st['truncated'] else ''})")

    # ---- aca_llm：没有官方真题 ----
    aca_rows = 0
    aca_db = DATA / "aca_llm.sqlite"
    aca_detail = {}
    if aca_db.exists():
        con = sqlite3.connect(f"file:{aca_db}?mode=ro", uri=True)
        aca_rows = con.execute("SELECT count(*) FROM questions WHERE source_type='real_exam'").fetchone()[0]
        aca_detail = {
            "fetch": con.execute("SELECT count(*) FROM questions WHERE source_type='fetch'").fetchone()[0],
            "fetch_aca_extended": con.execute("SELECT count(*) FROM questions WHERE trust_level='aca_extended'").fetchone()[0],
            "generate": con.execute("SELECT count(*) FROM questions WHERE source_type='generate'").fetchone()[0],
        }
        con.close()
    aca_doc = OrderedDict([
        ("schema_version", SCHEMA_VERSION),
        ("subject", "aca_llm"),
        ("subject_name_cn", disp.get("subject_names", {}).get("aca_llm", "阿里云 ACA 大模型工程师")),
        ("type", None),
        ("status", "empty_no_real_exam"),
        ("built_at", now_iso()),
        ("built_by", "scripts/export_exam_samples.py"),
        ("samples", []),
        ("why_empty", [
            "`data/aca_llm.sqlite` 中 source_type='real_exam' 的题数 = %d（ACA 是机考认证，官方不公开真题）。" % aca_rows,
            "本库的定位是「真题样板库」，答案与解析必须来自真实考卷；ACA 没有真题可作样板，故按要求留空，不拿 AI 生成题或第三方练习冒充。",
        ]),
        ("knowledge_points_available", {
            "kb_path": kbi["aca_llm"]["kb_path"],
            "total_points": len(kbi["aca_llm"]["points"]),
            "modules": [{"no": m.get("no"), "name": m.get("name"), "weight": m.get("weight"),
                         "points": len(m.get("points") or [])} for m in kbs["aca_llm"].get("modules") or []],
        }),
        ("what_does_exist", {
            "note": "以下**不是**真题，仅作库存说明，本次未生成任何 aca_llm 样例文件。",
            "db": "data/aca_llm.sqlite",
            **aca_detail,
        }),
        ("how_to_enable_later", "如需要，可复制 scripts/export_exam_samples.py 里的 `records_from_*` 逻辑，"
                                "把 aca_llm.sqlite 里 source_type='fetch' 的题按知识点（模块/课时）分文件导出，"
                                "并在每个 sample 的 trust 上写 'aca_official_course'，与 official_exam 区分。"),
    ])
    index_types["aca_llm"] = OrderedDict()

    print("\n=== 5/5 写盘 ===")
    total_bytes, total_samples = 0, 0
    if args.dry_run:
        print("  --dry-run：未写入任何文件")
    else:
        OUTDIR.mkdir(parents=True, exist_ok=True)
        for (subj, t), doc in files_out.items():
            p = OUTDIR / subj / f"{t}.json"
            n = dump_json(p, doc)
            total_bytes += n
            total_samples += doc["stats"]["samples"]
            print(f"  + data/exam_samples/{subj}/{t}.json  {n:>7} B  {doc['stats']['samples']:>3} 条")
        n = dump_json(OUTDIR / "aca_llm" / "_NO_REAL_EXAM.json", aca_doc)
        total_bytes += n
        print(f"  + data/exam_samples/aca_llm/_NO_REAL_EXAM.json  {n:>7} B  （如实留空）")

        # ---- _knowledge_map.json ----
        kmap = OrderedDict([
            ("schema_version", SCHEMA_VERSION),
            ("built_at", now_iso()),
            ("built_by", "scripts/export_exam_samples.py"),
            ("note", "题型 ↔ 知识点 映射表，来自三个既有知识点库，未新增任何知识点。"),
            ("subjects", OrderedDict()),
        ])
        for subj in ("english", "c_common", "aca_llm"):
            entry = OrderedDict([
                ("kb_path", kbi[subj]["kb_path"]),
                ("total_points", len(kbi[subj]["points"])),
                ("basis", kbi[subj]["basis"]),
            ])
            if subj == "english":
                entry["type_to_points"] = OrderedDict()
                for t, ids in sorted(kbi["english"]["type_to_points"].items()):
                    entry["type_to_points"][t] = [
                        {"id": i, "name": kbi["english"]["points"].get(i, {}).get("name"),
                         "dimension": kbi["english"]["points"].get(i, {}).get("dimension")}
                        for i in ids]
                entry["points"] = [{"id": p["id"], "name": p["name"], "dimension": p["dimension"],
                                    "question_type": p.get("question_type"),
                                    "format_era": p.get("format_era")}
                                   for p in kbi["english"]["points"].values()]
            elif subj == "c_common":
                entry["type_to_points"] = {
                    t: {"mapping": "by_chapter",
                        "candidate_points": [p["id"] for p in kbi["c_common"]["points"].values()]}
                    for t in sorted({r["type"] for r in recs if r["subject"] == "c_common"})}
                entry["type_to_points_note"] = ("C 语言的题型**不决定**知识点：任何题型都可以考任何一个章节。"
                                                "所以这里列出全部候选知识点，实际取值由每道题的 source.chapter 反查得到，"
                                                "见各 sample 的 knowledge_point / chapter_raw。")
                entry["chapter_index"] = OrderedDict(
                    sorted(kbi["c_common"]["chapter_index"].items()))
                entry["points"] = [{"id": p["id"], "name": p["name"],
                                    "alias_count": len(p.get("alias_chapters") or [])}
                                   for p in kbs["c_common"].get("knowledge_points") or []]
                entry["alias_collisions"] = kbi["c_common"]["alias_collisions"]
            else:
                entry["type_to_points"] = {}
                entry["points_by_module"] = aca_doc["knowledge_points_available"]["modules"]
            kmap["subjects"][subj] = entry

        # ---- 映射覆盖率 ----
        cov = OrderedDict()
        for (subj, t), doc in sorted(files_out.items()):
            s = doc["samples"]
            n_ok = sum(1 for x in s if x["knowledge_point_ids"])
            cov[f"{subj}/{t}"] = {"samples": len(s), "mapped": n_ok,
                                  "unmapped": len(s) - n_ok,
                                  "rate": round(n_ok / len(s), 4) if s else 0}
        kmap["sample_coverage"] = cov
        kmap["unmapped_reasons"] = dict(unmapped)
        n = dump_json(OUTDIR / "_knowledge_map.json", kmap)
        total_bytes += n
        print(f"  + data/exam_samples/_knowledge_map.json  {n:>7} B")

        # ---- _index.json ----
        old_info = {}
        if OLD_REF.exists():
            old = load_json(OLD_REF)
            old_types = sum(len((v.get("by_type") or {})) for v in (old.get("subjects") or {}).values())
            old_samples = sum(tv.get("sample_count") or 0
                              for v in (old.get("subjects") or {}).values()
                              for tv in (v.get("by_type") or {}).values())
            old_info = {
                "path": "data/generation_reference.json",
                "bytes": OLD_REF.stat().st_size,
                "built_at": old.get("built_at"),
                "schema_version": old.get("schema_version"),
                "subjects": sorted((old.get("subjects") or {}).keys()),
                "types": old_types, "samples": old_samples,
                "samples_per_type_rule": (old.get("rules") or {}).get("samples_per_type"),
            }
        idx = OrderedDict([
            ("schema_version", SCHEMA_VERSION),
            ("built_at", now_iso()),
            ("built_by", "scripts/export_exam_samples.py"),
            ("what", "全部真题按「科目 / 题型」整理的样板库：题目 + 知识点 + 标准答案 + 解析，供 AI 生成题目时对照。"),
            ("relation_to_old_reference", OrderedDict([
                ("old", old_info),
                ("relation", "本库是 data/generation_reference.json 的**超集与替代**："
                             "旧库每题型只取 3–5 条、丢弃 options、把材料里的空渲染成空白、"
                             "知识点沿用库内未归一的原始章节名；本库每题型最多 %d 条、"
                             "保留原始 options/词库、空位显式标出且整组不拆、知识点已归一到三个既有知识点库。"
                             % args.per_type),
                ("old_file_kept", True),
                ("old_file_note", "旧文件按用户要求保留未删；如需下游只认一个入口，请以 data/exam_samples/_index.json 为准。"),
            ])),
            ("sources", OrderedDict([
                ("real_exams_dir", "inbox/real_exams/*.json"),
                ("files_scanned", len(exam_index)),
                ("records_extracted", len(recs)),
                ("raw_items_total", raw_total),
                ("raw_items_by_subject", dict(raw_by_subject)),
                ("logical_subitems_covered", items_covered),
                ("logical_subitems_note", "1 个原始题项可能内含多个 {{__BLANK_n__}}，故本数可大于题项容器数"),
                ("exams", exam_index),
            ])),
            ("knowledge_bases", {s: {"path": kbi[s]["kb_path"], "points": len(kbi[s]["points"])}
                                 for s in ("english", "c_common", "aca_llm")}),
            ("totals", OrderedDict([
                ("samples", sum(d["stats"]["samples"] for d in files_out.values())),
                ("files", len(files_out)),
                ("by_subject", dict(Counter({s: sum(d["stats"]["samples"] for (ss, _), d in files_out.items() if ss == s)
                                             for s in {ss for ss, _ in files_out}}))),
                ("material_blocks", sum(d["stats"]["material_blocks"] for d in files_out.values())),
                ("total_blanks_in_material_blocks",
                 sum(d["stats"]["total_blanks_in_material_blocks"] for d in files_out.values())),
                ("with_explanation", sum(d["stats"]["with_explanation"] for d in files_out.values())),
            ])),
            ("knowledge_point_coverage", cov),
            ("unmapped", OrderedDict([
                ("reason_counts", dict(unmapped)),
                ("explanation", "unmapped 一律如实记录，不猜测、不补造知识点。"),
            ])),
            ("by_subject_type", OrderedDict()),
            ("duplicate_representation_groups", dup_groups),
            ("duplicate_representation_note",
             "同一套湖北卷在 inbox/real_exams 里有**两个抓取版本**：sections 版（111–116/128，材料按块存、"
             "材料里的空位带 inline 标记）与 questions 版（014/015/017–020，小题干更完整、"
             "每题自带 options）。两版内容互补，本库**都保留**，未做跨格式去重 —— "
             "下游生成时按 type_raw / 结构自行取舍；如需合并请以 sections 版为材料基准。"),
            ("validation_issues", issues),
            ("source_data_gaps", OrderedDict([
                ("note", "源真题自身的缺口（不是本脚本的 bug）：这些题/组没有标准答案，已被排除，"
                         "不拿空答案充数。"),
                ("total", len(SOURCE_GAPS)),
                ("by_exam", {e: n for e, n in Counter(g["exam"] for g in SOURCE_GAPS).most_common()}),
                ("items", SOURCE_GAPS[:80]),
            ])),
            ("design_notes", [
                "题干一律取自 inbox/real_exams/*.json 原始 JSON。**不从 SQLite 读题干**："
                "scripts/import_real_exams.py 的 strip_html() 把 `#include <stdio.h>` 当成 HTML 标签删掉了，"
                "库里存的是 `#include `，原始 JSON 无此损伤。",
                "材料型题（一篇短文 + 若干空）整组一条 sample：material = 整篇原文，material_blanks = 全部空。"
                "脚本对每组的空数做断言，不符的记入 validation_issues，不静默丢弃。",
                "空位渲染：源里 {type:'blank'} 只是一个无字空白，本库显式写成 {{__BLANK_<n>__}}，"
                "否则材料读不通、也核对不出空数。文字内容一字未改。",
                "连词成句保留真题 `词组 / 词组` 斜杠原格式（渲染层再切词卡）。",
                "同题干跨校重复（如 042/043/044 字节完全相同）只留 1 条，其余来源写入 same_stem_exams，"
                "使每题型 40 条尽量覆盖不同考点。",
                "取样按 exam 轮转，保证每套卷都有代表；上限只在样例富余时生效，唯一来源不会被丢掉。",
            ]),
        ])
        for (subj, t), doc in sorted(files_out.items()):
            idx["by_subject_type"].setdefault(subj, OrderedDict())[t] = OrderedDict([
                ("file", f"{subj}/{t}.json"),
                ("type_name_cn", doc["type_name_cn"]),
                ("samples", doc["stats"]["samples"]),
                ("source_records", doc["stats"]["source_records"]),
                ("with_explanation", doc["stats"]["with_explanation"]),
                ("material_blocks", doc["stats"]["material_blocks"]),
                ("exams", [e["exam"] for e in doc["exams"]]),
                ("type_raw_values", doc["type_raw_values"]),
                ("knowledge_points", [p["id"] for p in doc["knowledge_points"]]),
            ])
        idx["by_subject_type"]["aca_llm"] = OrderedDict([
            ("_NO_REAL_EXAM.json", OrderedDict([
                ("samples", 0), ("status", "empty_no_real_exam"),
                ("reason", "ACA 是机考认证，官方不公开真题；data/aca_llm.sqlite 里 source_type='real_exam' 为 0 条。"),
            ]))])
        n = dump_json(OUTDIR / "_index.json", idx)
        total_bytes += n
        print(f"  + data/exam_samples/_index.json  {n:>7} B")
        print(f"\n  合计 {total_samples} 条样例 / {len(files_out)} 个题型文件 / {total_bytes} 字节")

    if args.proof:
        print("\n=== 材料型整组证明 ===")
        cands = [(k, d) for k, d in files_out.items()
                 if k[1] in ("reading_fill", "reading_qa") and d["stats"]["material_blocks"] > 0]
        cands.sort(key=lambda kv: -kv[1]["samples"][0]["material_blanks_total"] if kv[1]["samples"] else 0)
        for (subj, t), doc in cands[:2]:
            for s in doc["samples"][:2]:
                bl = s["material_blanks"]
                print(f"\n  [{subj}/{t}] {s['exam']}  group_uid={s['group_uid']}  trust={s['trust']}")
                print(f"  材料前60字: {s['material'][:60]!r}")
                print(f"  材料总长 {len(s['material'])} 字符；空数 {len(bl)}（声明 {s['material_blanks_total']}）")
                print(f"  各空: " + " || ".join(f"#{b.get('no')}→{b['answer'][:24]!r}" for b in bl))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
