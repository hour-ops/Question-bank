#!/usr/bin/env python
"""阶段 8 · 组卷导出（`export_papers.py`）—— 从各科目库 **approved** 题生成整套试卷包。

用法:
    python scripts/export_papers.py [--subject all|english|c_wuhan|c_hbpu|aca_llm]
                                    [--outdir output/papers] [--dry-run] [--include-pending]
    # 测试用参数（默认走项目真实库/配置）:
    #   --data-dir PATH    覆盖科目库目录（默认 data/）
    #   --taxonomy PATH    覆盖 config/taxonomy.json
    #   --date YYYYMMDD    覆盖输出子目录名（默认本地今天）

输出（默认写到 `output/papers/<YYYYMMDD>/`）:
    english_paper.docx / c_wuhan_paper.docx / c_hbpu_paper.docx / aca_llm_paper.docx
        python-docx；含试卷头、题型分节、题号、题干、选项/代码模板、分值/uid 行
    english_paper.pdf  / c_wuhan_paper.pdf / c_hbpu_paper.pdf / aca_llm_paper.pdf
        reportlab；**必须先注册中文字体**（`C:\\Windows\\Fonts\\msyh.ttc` → `simsun.ttc` →
        `simhei.ttf`）。一个都找不到时 **不生成 PDF** 并打印明确警告 —— 绝不静默输出方块字。
    all_questions.xlsx   openpyxl，一行一题（列见 EXPORT_HEADERS）
    all_questions.csv    同上，**utf-8-sig（带 BOM）**，Excel 直接打开不乱码
    aca_llm.apkg         genanki；仅 ACA 单选/多选。model id / deck id 为固定常量，
                         note guid = question_uid → 重复导出**不产生重复卡片**

口径（与 DESIGN.md 第 2/3/4/6 节、决策记录第 6 节一致）:
  1. 只取 `status='approved'`；`--include-pending` 追加 `pending_review`（默认关）。
  2. 试卷**结构**按 `config/taxonomy.json` 的 `subjects.<科目>.question_types` **声明顺序**分节；
     有 `paper_count` 的题型按配额截取（取库内 `id` 最小 = 最早入库的 N 题）。
  3. **题量不足照实输出**：试卷头写「实收 X 题 / 目标 Y 题」，缺题型的节写「本卷暂无题目」，
     **绝不伪造题目**；被配额截掉的题量记入 `by_type.<题型>.dropped_by_quota`。
  4. 分值只认 taxonomy（`per_item` / `paper_score`）；查不到一律写 `未获取`（防幻觉硬约束），
     C 语言两校的题型配额官方考纲未取得，故不截取并注明「配额待补」。
  5. 试卷本体**不含答案与解析**（答案/解析在 xlsx / csv / apkg 里）。
  6. `--dry-run` 只统计 approved 题量与将生成的文件名，**不建目录、不落盘**。
  7. 汇总 JSON（stdout 最后一行）: `{"papers": {...}, "files": [...], "skipped": [...]}`（+ dry_run/outdir/date/warnings）。
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import sys
import xml.sax.saxutils as saxutils
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
TAXONOMY_PATH = ROOT / "config" / "taxonomy.json"
DEFAULT_OUTDIR = "output/papers"

SUBJECTS = ["english", "c_wuhan", "c_hbpu", "aca_llm"]
ACA_SUBJECT = "aca_llm"
ACA_CHOICE_TYPES = ("single_choice", "multiple_choice")

STATUS_APPROVED = "approved"
STATUS_PENDING = "pending_review"

# ---------------------------------------------------------------- 中文字体（PDF 必需）
# ⚠️ reportlab 内置字体没有 CJK 字形：不注册中文字体就会输出方块 → 必须显式检测 + 注册。
CJK_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",     # 微软雅黑（首选）
    r"C:\Windows\Fonts\simsun.ttc",   # 宋体
    r"C:\Windows\Fonts\simhei.ttf",   # 黑体
]
CJK_BOLD_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyhbd.ttc",   # 微软雅黑 Bold
    r"C:\Windows\Fonts\simhei.ttf",
]
PDF_FONT_NAME = "CJKMain"
PDF_FONT_BOLD_NAME = "CJKMain-Bold"

# ---------------------------------------------------------------- Anki 固定 id（幂等关键）
# ⚠️ 这两个常量一旦发布**不得再改**：改了 = 用户端出现重复卡组/重复 model。
ANKI_MODEL_ID = 2026101101
ANKI_DECK_ID = 2026101102
ANKI_DECK_NAME = "阿里云 ACA 大模型工程师 V2.4 · 单选多选"

EXPORT_HEADERS = ["uid", "subject", "题型", "题干", "答案", "解析", "来源", "难度", "status"]

QUESTION_COLUMNS = [
    "id", "question_uid", "subject", "school", "year", "textbook",
    "source_type", "source_url", "source_credit", "chapter", "knowledge_point", "syllabus_ref",
    "question_type", "stem", "options", "answer", "explanation",
    "difficulty", "code_template", "test_cases", "status", "quality_score",
]

CN_NUMERALS = "一二三四五六七八九十"
_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_MISSING = "未获取"          # 防幻觉硬约束：拿不到就写这个，禁止推测填空
_LEADING_SPACES = re.compile(r"^ +", re.M)
_OPT_PREFIX = re.compile(r"^([A-Za-z])\s*[.、．)）:：]\s*(.+)$")

_pdf_fonts_registered = False


# =============================================================== 基础设施

def load_json(path) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError) as exc:
        print(f"  [warn] 读取配置失败 {path}: {exc}", file=sys.stderr)
        return {}


def load_taxonomy(path=None) -> dict:
    return load_json(path or TAXONOMY_PATH)


def connect_ro(path) -> sqlite3.Connection:
    """只读打开（`file:...?mode=ro`）：导出脚本**绝不写任何库**，也不留 -wal/-shm。"""
    conn = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def columns_of(conn: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]


def _rel(path) -> str:
    p = Path(path)
    try:
        return p.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return p.as_posix()


def cn_index(i: int) -> str:
    return CN_NUMERALS[i - 1] if 1 <= i <= len(CN_NUMERALS) else str(i)


def num_text(value) -> str:
    """数值 → 去掉无意义小数尾巴的字符串。"""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return _MISSING
    return str(int(f)) if abs(f - round(f)) < 1e-9 else f"{f:g}"


def clean_text(value) -> str:
    if value is None:
        return ""
    s = str(value).replace("\r\n", "\n").replace("\r", "\n")
    s = "".join(ch for ch in s if ch in "\n\t" or ord(ch) >= 32)
    return s.strip()


# =============================================================== 读题

def fetch_questions(db_path, statuses) -> list[dict]:
    """读科目库 `questions` 表（**只读**），按 status 过滤，按 id 升序返回。"""
    conn = connect_ro(db_path)
    try:
        if not table_exists(conn, "questions"):
            raise RuntimeError(f"{Path(db_path).name} 缺 questions 表（先跑 scripts/init_db.py）")
        cols = columns_of(conn, "questions")
        wanted = [c for c in QUESTION_COLUMNS if c in cols]
        if not wanted:
            raise RuntimeError(f"{Path(db_path).name} 的 questions 表没有已知列")
        ph = ",".join("?" * len(statuses))
        rows: list[dict] = []
        for row in conn.execute(f"SELECT {', '.join(wanted)} FROM questions "
                                f"WHERE status IN ({ph}) ORDER BY id", list(statuses)):
            rec = dict(zip(wanted, row))
            for c in QUESTION_COLUMNS:                       # 补全缺失列，渲染层不必再判
                rec.setdefault(c, None)
            rows.append(rec)
        return rows
    finally:
        conn.close()


def statuses_for(include_pending: bool) -> list[str]:
    return [STATUS_APPROVED, STATUS_PENDING] if include_pending else [STATUS_APPROVED]


def subject_meta(taxonomy: dict, subject: str) -> dict:
    return ((taxonomy.get("subjects") or {}).get(subject) or {})


def question_types(taxonomy: dict, subject: str) -> dict:
    types = subject_meta(taxonomy, subject).get("question_types")
    return types if isinstance(types, dict) else {}


def resolve_target(meta: dict, types: dict) -> tuple[int | None, str]:
    """本卷**目标题量**（= 卷面题数）与依据标签。"""
    counts = [t.get("paper_count") for t in types.values()]
    if types and counts and all(isinstance(c, int) and c > 0 for c in counts):
        return sum(counts), "question_types.paper_count(卷面题数)"
    if isinstance(meta.get("paper_total_items"), int):
        return meta["paper_total_items"], "paper_total_items"
    if isinstance(meta.get("target_count"), int):
        return meta["target_count"], "target_count(题库配额，卷面配额待考纲确认)"
    return None, _MISSING


def per_item_score(cfg: dict) -> float | None:
    for key in ("per_item", "per_item_score", "score_per_item"):
        try:
            val = float(cfg.get(key))
            if val > 0:
                return val
        except (TypeError, ValueError):
            continue
    try:  # 退化：总分 / 题数
        score = float(cfg.get("paper_score"))
        count = int(cfg.get("paper_count"))
        if score > 0 and count > 0:
            return score / count
    except (TypeError, ValueError):
        pass
    return None


# =============================================================== 文本 / 选项渲染

def option_value_text(value) -> str:
    if isinstance(value, list):
        return " / ".join(clean_text(v) for v in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return clean_text(value)


def parse_options(raw) -> list[tuple[str, str]]:
    """`options` 列 → [(标签, 文本)]；标签为空串表示"原文直出"。

    支持：JSON dict（`{"A": "..."}`）、JSON list（`["...", ...]` → 自动 A/B/C…）、
    JSON list[dict]（带 label/text 键）、以及非 JSON 的纯文本（按行拆，尽量剥掉 "A." 前缀）。
    """
    text = clean_text(raw)
    if not text:
        return []
    obj = None
    try:
        obj = json.loads(text)
    except (ValueError, TypeError):
        obj = None
    if isinstance(obj, dict):
        return [(str(k), option_value_text(v)) for k, v in sorted(obj.items(), key=lambda kv: str(kv[0]))]
    if isinstance(obj, list):
        out: list[tuple[str, str]] = []
        for i, item in enumerate(obj):
            label = _LETTERS[i] if i < len(_LETTERS) else str(i + 1)
            text_i = option_value_text(item)
            if isinstance(item, dict):
                label = str(item.get("label") or item.get("key") or item.get("option") or label)
                text_i = clean_text(item.get("text") or item.get("value") or item.get("content") or "")
            out.append((label, text_i))
        return out
    out = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        m = _OPT_PREFIX.match(line)
        out.append((m.group(1).upper(), m.group(2).strip()) if m else ("", line))
    return out


def format_option(label: str, text: str) -> str:
    if not label:
        return text
    if re.match(rf"^{re.escape(label)}\s*[.、．)）:：]", text):
        return text
    return f"{label}. {text}"


def format_answer(raw) -> str:
    """答案列 → 人类可读文本（xlsx / csv / apkg 共用）。"""
    text = clean_text(raw)
    if not text:
        return ""
    try:
        obj = json.loads(text)
    except (ValueError, TypeError):
        return text
    if isinstance(obj, list):
        return "\n".join(clean_text(v) for v in obj)
    if isinstance(obj, dict):
        return "\n".join(f"{format_option(str(k), option_value_text(v))}" for k, v in sorted(obj.items(), key=lambda kv: str(kv[0])))
    return clean_text(obj)


def source_text(q: dict) -> str:
    for key in ("source_url", "source_credit", "source_type"):
        val = clean_text(q.get(key))
        if val:
            return val
    return _MISSING


def excel_row(q: dict, type_name: str) -> list:
    """一行一题（列见 EXPORT_HEADERS）。⚠️ 以 `=` 开头的字符串加 `'` 前缀防 Excel 公式注入。"""
    def safe(value: str) -> str:
        s = clean_text(value)
        return "'" + s if s.startswith("=") else s

    return [
        safe(q.get("question_uid")), safe(q.get("subject")), safe(type_name),
        clean_text(q.get("stem")), format_answer(q.get("answer")),
        clean_text(q.get("explanation")), source_text(q),
        clean_text(q.get("difficulty")) or _MISSING, clean_text(q.get("status")),
    ]


# =============================================================== 试卷文档模型

def _question_blocks(q: dict, number: int, per_item: float | None) -> list[dict]:
    """单题 → 块列表（kind: stem / option / template / score）。"""
    blocks: list[dict] = []
    stem = clean_text(q.get("stem"))
    blocks.append({"kind": "stem", "text": f"{number}. {stem}" if stem else f"{number}. （题干缺失：源数据为空，标未获取）"})

    for label, text in parse_options(q.get("options")):
        blocks.append({"kind": "option", "text": format_option(label, text)})

    template = clean_text(q.get("code_template"))
    if template:
        blocks.append({"kind": "template", "text": template})

    meta_bits = [f"uid: {clean_text(q.get('question_uid')) or _MISSING}"]
    difficulty = clean_text(q.get("difficulty"))
    meta_bits.append(f"难度: {difficulty}" if difficulty else f"难度: {_MISSING}")
    meta_bits.append(f"分值: {num_text(per_item)} 分" if per_item else "分值: 未获取")
    kp = clean_text(q.get("knowledge_point"))
    if kp:
        meta_bits.append(f"考点: {kp}")
    blocks.append({"kind": "score", "text": "[" + " · ".join(meta_bits) + "]"})
    return blocks


def build_document(subject: str, meta: dict, types: dict, questions: list[dict], *,
                   statuses: list[str], generated_at: str, warnings: list[str],
                   include_unknown: bool = False) -> dict:
    """→ {"blocks": [...], "stats": {...}, "selected": [题, ...]}（**纯函数，不落盘**）。

    `include_unknown=False`（默认）：**taxonomy 之外的题型不编入正文**，但在卷末明确标注数量与题型名
    —— 既不污染卷面结构，也不静默丢题。
    ⚠️ 之前的实现把大纲外题型无条件追加成分节且**没有配额上限**，导致英语卷面从 43 题暴涨到 431 题
    （真题导入带来完形填空/语音题/情景对话等新题型之后暴露出来）。
    """
    name = meta.get("name") or subject
    groups: dict[str, list[dict]] = {}
    unknown: dict[str, list[dict]] = {}
    for q in questions:
        qt = clean_text(q.get("question_type"))
        (groups if qt in types else unknown).setdefault(qt or "(空题型)", []).append(q)

    order = list(types.keys()) + (sorted(unknown.keys()) if include_unknown else [])
    target, target_src = resolve_target(meta, types)
    target_count = meta.get("target_count")
    total_score = meta.get("paper_total_score")
    duration = meta.get("paper_duration_minutes")

    stats_types: dict[str, dict] = {}
    selected: list[dict] = []
    capped_types: list[str] = []
    missing_stem = 0

    body: list[dict] = []      # 题型分节（先算，才知道「实收」几题）
    for i, qt in enumerate(order, start=1):
        cfg = types.get(qt) or {}
        sec_name = cfg.get("name") or qt
        # ⚠️ taxonomy 之外的题型在 unknown 桶里：必须照实单列分节，**不得静默丢题**。
        items = list((groups if qt in types else unknown).get(qt, []))
        cap = cfg.get("paper_count") if isinstance(cfg.get("paper_count"), int) else None
        dropped = 0
        if cap and len(items) > cap:
            dropped = len(items) - cap
            items = items[:cap]
            capped_types.append(qt)
        per_item = per_item_score(cfg)
        sec_score = cfg.get("paper_score")
        if sec_score is None and per_item is not None and items:
            sec_score = per_item * len(items)

        if items:
            bits = [f"共 {len(items)} 题"]
            bits.append(f"每题 {num_text(per_item)} 分" if per_item else "每题分值：未获取")
            if sec_score is not None:
                bits.append(f"共 {num_text(sec_score)} 分")
        else:
            bits = ["本卷暂无已审核题目"]
            if cap:
                bits.append(f"目标 {cap} 题")
        body.append({"kind": "section", "text": f"{cn_index(i)}、{sec_name}（{'，'.join(bits)}）"})

        if items:
            for n, q in enumerate(items, start=1):
                if not clean_text(q.get("stem")):
                    missing_stem += 1
                body.extend(_question_blocks(q, n, per_item))
                selected.append(q)
        else:
            body.append({"kind": "note", "text": "（该题型暂无可用题目 —— 照实留空，未伪造题目）"})

        stats_types[qt] = {
            "name": sec_name,
            "count": len(items),
            "target": cap,
            "dropped_by_quota": dropped,
            "per_item": per_item,
            "section_score": sec_score,
            "known_type": qt in types,
        }

    if unknown:
        n_unk = sum(len(v) for v in unknown.values())
        warnings.append(f"{subject}: {n_unk} 道题的 question_type 不在 taxonomy 里"
                        f"（{'、'.join(sorted(unknown))}）→ "
                        + ("已单列分节编入，请核对" if include_unknown else "**未编入本卷**（如需编入请加 --include-unknown）"))
        if not include_unknown:
            body.append({"kind": "note",
                         "text": f"（另有 {n_unk} 道题属于本卷大纲之外的题型，未编入本卷："
                                 f"{'、'.join(sorted(unknown))}）"})

    # ---------------------------------------------------------------- 试卷头（实收 = 实际进卷的题数）
    header2 = [f"生成时间：{generated_at}", f"题源状态：{'/'.join(statuses)}"]
    if isinstance(target_count, int):
        header2.append(f"题库配额：{target_count} 题")
    header3 = [f"卷面满分：{num_text(total_score) + ' 分' if total_score else _MISSING}"]
    if duration:
        header3.append(f"考试时长：{duration} 分钟")
    header3.append(f"实收 {len(selected)} 题 / 目标 {num_text(target)} 题")

    head_notes: list[dict] = []
    note = clean_text(meta.get("paper_note"))
    if note:
        head_notes.append({"kind": "note", "text": f"卷面依据：{note}"})
    if meta.get("notes"):
        head_notes.append({"kind": "note", "text": f"说明：{clean_text(meta['notes'])}"})
    if capped_types:
        detail = "、".join(f"{types[t].get('name') or t} 截取 {stats_types[t]['count']} 题"
                           f"（库内 {stats_types[t]['count'] + stats_types[t]['dropped_by_quota']} 题）"
                           for t in capped_types)
        head_notes.append({"kind": "note", "text": f"注：超额题型按卷面配额择题 —— {detail}。"})

    blocks: list[dict] = [
        {"kind": "title", "text": f"{name} 试卷"},
        {"kind": "meta", "text": "　".join(header2)},
        {"kind": "meta", "text": "　".join(header3)},
        *head_notes,
        *body,
        {"kind": "note", "text": "说明：本卷不含答案与解析；答案/解析见同目录 all_questions.xlsx / all_questions.csv。"},
    ]

    stats = {
        "name": name,
        "db": meta.get("db") or f"data/{subject}.sqlite",
        "statuses": list(statuses),
        "available_items": len(questions),
        "actual_items": len(selected),
        "target_items": target,
        "target_source": target_src,
        "paper_total_score": total_score,
        "duration_minutes": duration,
        "by_type": stats_types,
        "capped_types": capped_types,
        "uncategorized_items": sum(len(v) for v in unknown.values()),
        "missing_stem": missing_stem,
    }
    return {"blocks": blocks, "stats": stats, "selected": selected}


# =============================================================== DOCX

_DOCX_KIND = {
    # kind: (字号, 粗体, 缩进(cm), 对齐, 段后, 颜色)
    "title":    (18, True, 0.0, "center", 6, None),
    "meta":     (9, False, 0.0, "center", 2, "595959"),
    "note":     (9, False, 0.0, "left", 2, "595959"),
    "section":  (13, True, 0.0, "left", 4, "1F3864"),
    "stem":     (10.5, False, 0.0, "left", 2, None),
    "option":   (10.5, False, 0.3, "left", 1, None),
    "template": (9.5, False, 0.3, "left", 0, "1F3864"),
    "score":    (9, False, 0.3, "left", 3, "808080"),
}


def render_docx(doc_model: dict, path) -> None:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt, RGBColor

    doc = Document()
    section = doc.sections[0]
    section.top_margin = Cm(2.0)
    section.bottom_margin = Cm(2.0)
    section.left_margin = Cm(2.4)
    section.right_margin = Cm(2.4)

    normal = doc.styles["Normal"]
    normal.font.name = "宋体"                                  # 先设 name 才会创建 rPr/rFonts
    normal.font.size = Pt(10.5)
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")

    align_map = {"center": WD_ALIGN_PARAGRAPH.CENTER, "left": WD_ALIGN_PARAGRAPH.LEFT}

    for block in doc_model["blocks"]:
        size, bold, indent, align, space_after, color = _DOCX_KIND.get(block["kind"], _DOCX_KIND["stem"])
        # 代码模板按行拆段（Word 会自动保留行首空格 → 缩进不丢）
        lines = block["text"].split("\n") if block["kind"] == "template" else [block["text"]]
        for line in lines:
            p = doc.add_paragraph()
            p.alignment = align_map.get(align, WD_ALIGN_PARAGRAPH.LEFT)
            pf = p.paragraph_format
            pf.space_after = Pt(space_after)
            pf.space_before = Pt(8 if block["kind"] == "section" else 0)
            if indent:
                pf.left_indent = Cm(indent)
            run = p.add_run(line)
            run.font.size = Pt(size)
            run.bold = bold
            font_name = "Consolas" if block["kind"] == "template" else "宋体"
            run.font.name = font_name
            run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
            if color:
                run.font.color.rgb = RGBColor.from_string(color)

    doc.save(str(path))


# =============================================================== PDF（reportlab + 中文字体）

def find_cjk_font() -> tuple[str | None, str | None]:
    """→ (常规字体路径, 粗体路径)；找不到常规字体时返回 (None, None)。"""
    regular = next((p for p in CJK_FONT_CANDIDATES if Path(p).is_file()), None)
    if not regular:
        return None, None
    bold = next((p for p in CJK_BOLD_FONT_CANDIDATES if Path(p).is_file()), regular)
    return regular, bold


def register_cjk_fonts(regular: str, bold: str | None = None) -> tuple[str, str]:
    """注册中文字体到 reportlab（幂等）。TTC 取 subfontIndex=0。"""
    global _pdf_fonts_registered
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    bold = bold or regular
    if not _pdf_fonts_registered:
        pdfmetrics.registerFont(TTFont(PDF_FONT_NAME, regular, subfontIndex=0))
        try:
            pdfmetrics.registerFont(TTFont(PDF_FONT_BOLD_NAME, bold, subfontIndex=0))
        except Exception:  # noqa: BLE001 —— 粗体注册失败就用常规体，绝不因此放弃中文
            pdfmetrics.registerFont(TTFont(PDF_FONT_BOLD_NAME, regular, subfontIndex=0))
        pdfmetrics.registerFontFamily(PDF_FONT_NAME, normal=PDF_FONT_NAME,
                                      bold=PDF_FONT_BOLD_NAME, italic=PDF_FONT_NAME,
                                      boldItalic=PDF_FONT_BOLD_NAME)
        _pdf_fonts_registered = True
    return PDF_FONT_NAME, PDF_FONT_BOLD_NAME


def para_text(text: str) -> str:
    """reportlab Paragraph 安全文本：XML 转义 → 行首空格转 &nbsp; → 换行转 <br/>。"""
    s = saxutils.escape(clean_text(text))
    s = _LEADING_SPACES.sub(lambda m: "&nbsp;" * len(m.group(0)), s)
    return s.replace("\n", "<br/>")


def render_pdf(doc_model: dict, path, font_path: str, bold_path: str | None = None) -> None:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    font, font_bold = register_cjk_fonts(font_path, bold_path)
    common = dict(fontName=font, wordWrap="CJK", splitLongWords=1, alignment=TA_LEFT)
    styles = {
        "title": ParagraphStyle("title", fontName=font_bold, fontSize=18, leading=24,
                                alignment=TA_CENTER, spaceAfter=8),
        "meta": ParagraphStyle("meta", **{**common, "fontSize": 9, "leading": 13,
                                          "alignment": TA_CENTER, "textColor": colors.HexColor("#595959")}),
        "note": ParagraphStyle("note", **{**common, "fontSize": 9, "leading": 13,
                                          "textColor": colors.HexColor("#595959")}),
        "section": ParagraphStyle("section", fontName=font_bold, fontSize=13, leading=19,
                                  wordWrap="CJK", spaceBefore=12, spaceAfter=5,
                                  textColor=colors.HexColor("#1F3864")),
        "stem": ParagraphStyle("stem", **{**common, "fontSize": 10.5, "leading": 16, "spaceBefore": 4}),
        "option": ParagraphStyle("option", **{**common, "fontSize": 10.5, "leading": 16, "leftIndent": 14}),
        "template": ParagraphStyle("template", **{**common, "fontSize": 9.5, "leading": 13,
                                                  "leftIndent": 14, "textColor": colors.HexColor("#1F3864")}),
        "score": ParagraphStyle("score", **{**common, "fontSize": 9, "leading": 13,
                                            "leftIndent": 14, "spaceAfter": 3,
                                            "textColor": colors.HexColor("#808080")}),
    }

    doc = SimpleDocTemplate(str(path), pagesize=A4,
                            leftMargin=2.2 * cm, rightMargin=2.2 * cm,
                            topMargin=1.8 * cm, bottomMargin=1.8 * cm,
                            title=doc_model["blocks"][0]["text"] if doc_model["blocks"] else "试卷")
    story = []
    for block in doc_model["blocks"]:
        style = styles.get(block["kind"], styles["stem"])
        story.append(Paragraph(para_text(block["text"]), style))
    story.append(Spacer(1, 6))
    doc.build(story)


# =============================================================== 汇总文件（xlsx / csv / apkg）

def write_xlsx(rows: list[list], path) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = "questions"
    ws.append(EXPORT_HEADERS)
    for row in rows:
        ws.append(row)
    head_font = Font(bold=True, color="FFFFFF")
    fill = PatternFill("solid", fgColor="1F3864")
    for cell in ws[1]:
        cell.font = head_font
        cell.fill = fill
        cell.alignment = Alignment(horizontal="center", vertical="center")
    for col, width in zip("ABCDEFGHI", (22, 10, 14, 60, 18, 40, 34, 8, 12)):
        ws.column_dimensions[col].width = width
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    ws.freeze_panes = "A2"
    wb.save(str(path))


def write_csv(rows: list[list], path) -> None:
    """⚠️ 必须 `utf-8-sig`：否则 Excel 打开中文乱码。"""
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(EXPORT_HEADERS)
        writer.writerows(rows)


def _anki_html(text: str) -> str:
    return saxutils.escape(clean_text(text)).replace("\n", "<br>")


def write_apkg(questions: list[dict], path, types: dict, skipped: list[dict], subject: str = ACA_SUBJECT) -> bool:
    """只把 ACA 单选/多选写进 .apkg；model/deck id 固定 + guid=question_uid → 重复导出不重复。"""
    try:
        import genanki
    except ImportError as exc:  # pragma: no cover - 环境缺包时走这里
        skipped.append({"item": Path(path).name, "subject": subject, "reason": f"未安装 genanki：{exc}"})
        return False

    model = genanki.Model(
        ANKI_MODEL_ID,
        "ACA 大模型工程师 V2.4（单选/多选）",
        fields=[{"name": "Front"}, {"name": "Back"}, {"name": "Meta"}],
        templates=[{
            "name": "ACA 选择题",
            "qfmt": "{{Front}}",
            "afmt": "{{FrontSide}}<hr id=answer>{{Back}}<div class=\"meta\">{{Meta}}</div>",
        }],
        css=".card{font-family:'Microsoft YaHei',sans-serif;font-size:16px;text-align:left;}"
            ".meta{margin-top:10px;color:#808080;font-size:12px;}",
    )
    deck = genanki.Deck(ANKI_DECK_ID, ANKI_DECK_NAME)

    notes = 0
    excluded = 0
    for q in questions:
        qtype = clean_text(q.get("question_type"))
        uid = clean_text(q.get("question_uid"))
        if qtype not in ACA_CHOICE_TYPES or not uid:
            excluded += 1
            continue
        type_name = (types.get(qtype) or {}).get("name") or qtype
        front = [f"<b>[{type_name}]</b>", _anki_html(q.get("stem"))]
        front += [format_option(label, text) for label, text in parse_options(q.get("options"))]
        back = ["<b>答案：</b>" + (_anki_html(format_answer(q.get("answer"))) or _MISSING)]
        explanation = clean_text(q.get("explanation"))
        if explanation:
            back.append("<b>解析：</b>" + _anki_html(explanation))
        meta = f"uid: {uid}｜难度: {clean_text(q.get('difficulty')) or _MISSING}｜来源: {source_text(q)}"
        deck.add_note(genanki.Note(model=model, guid=genanki.guid_for("aca_llm", uid),
                                   fields=["<br>".join(front), "<br>".join(back), meta]))
        notes += 1

    if not notes:
        skipped.append({"item": Path(path).name, "subject": subject,
                        "reason": "无 ACA 单选/多选 approved 题，未生成 Anki 包"})
        return False
    if excluded:
        skipped.append({"item": Path(path).name, "subject": subject,
                        "reason": f"已排除 {excluded} 道非单选/多选（或缺 uid）的 ACA 题"})
    genanki.Package(deck).write_to_file(str(path))
    return True


# =============================================================== 主流程

def run_export(args) -> tuple[int, dict]:
    """返回 (退出码, 汇总 dict)。**不打印** —— 打印与 JSON 输出在 main() 里。"""
    date_str = args.date or datetime.now().strftime("%Y%m%d")
    if not re.fullmatch(r"\d{8}", str(date_str)):
        print(f"[error] --date 必须是 YYYYMMDD（8 位数字），实际 {date_str!r}", file=sys.stderr)
        return 2, {"papers": {}, "files": [], "skipped": [{"item": "--date", "reason": f"非法日期 {date_str!r}"}]}

    subjects = SUBJECTS if args.subject == "all" else [args.subject]
    data_dir = Path(args.data_dir).resolve() if args.data_dir else DATA
    taxonomy = load_taxonomy(args.taxonomy)
    if not taxonomy.get("subjects"):
        print(f"[error] taxonomy 读不到 subjects：{args.taxonomy or TAXONOMY_PATH}", file=sys.stderr)
        return 2, {"papers": {}, "files": [], "skipped": [{"item": "taxonomy", "reason": "配置缺失或不可解析"}]}

    outdir_arg = Path(args.outdir)
    out_base = outdir_arg if outdir_arg.is_absolute() else (ROOT / outdir_arg)
    out_dir = out_base / str(date_str)

    dry = bool(args.dry_run)
    statuses = statuses_for(bool(args.include_pending))
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    papers: dict[str, dict] = {}
    files: list[str] = []
    skipped: list[dict] = []
    warnings: list[str] = []
    all_rows: list[list] = []
    ace_questions: list[dict] = []
    ace_types: dict = {}
    read_any = False

    font_path, bold_path = find_cjk_font()
    if not font_path:
        msg = ("未找到可用中文字体（已尝试 " + "、".join(CJK_FONT_CANDIDATES) + "）→ "
               "**跳过全部 PDF 生成**（reportlab 无 CJK 字形，宁可不出 PDF 也不出方块字）。")
        print(f"  [warn] {msg}", file=sys.stderr)
        warnings.append(msg)

    for subject in subjects:
        db_path = data_dir / f"{subject}.sqlite"
        if not db_path.is_file():
            skipped.append({"item": _rel(db_path), "subject": subject, "reason": "科目库不存在，已跳过"})
            print(f"  [skip] {subject}: 库不存在 {_rel(db_path)}")
            continue
        try:
            questions = fetch_questions(db_path, statuses)
        except (sqlite3.Error, RuntimeError) as exc:
            skipped.append({"item": _rel(db_path), "subject": subject, "reason": f"读库失败：{exc}"})
            print(f"  [skip] {subject}: {exc}", file=sys.stderr)
            continue
        read_any = True

        meta = subject_meta(taxonomy, subject)
        types = question_types(taxonomy, subject)
        if not types:
            warnings.append(f"{subject}: taxonomy 未定义 question_types → 全部题目单列「未分类」分节")
        built = build_document(subject, meta, types, questions, statuses=statuses,
                               include_unknown=bool(getattr(args, "include_unknown", False)),
                               generated_at=generated_at, warnings=warnings)
        stats = built["stats"]
        stats["files"] = []
        papers[subject] = stats

        docx_name = f"{subject}_paper.docx"
        pdf_name = f"{subject}_paper.pdf"
        planned = [docx_name] + ([pdf_name] if font_path else [])
        tag = "dry-run" if dry else "write"
        detail = " ".join(f"{t}={v['count']}" + (f"/{v['target']}" if v["target"] else "")
                          for t, v in stats["by_type"].items())
        print(f"  [{tag}] {subject:<8} approved={stats['actual_items']}/{num_text(stats['target_items'])} "
              f"（库内 {stats['available_items']}）  {detail}")

        for q in built["selected"]:
            qtype = clean_text(q.get("question_type"))
            all_rows.append(excel_row(q, (types.get(qtype) or {}).get("name") or qtype or _MISSING))
        if subject == ACA_SUBJECT:
            ace_questions = built["selected"]
            ace_types = types

        if dry:
            for name in planned:
                files.append(_rel(out_dir / name))
            if not font_path:
                skipped.append({"item": pdf_name, "subject": subject,
                                "reason": "无可用中文字体 → 将不生成 PDF（避免中文方块字）"})
            continue

        out_dir.mkdir(parents=True, exist_ok=True)
        try:
            render_docx(built, out_dir / docx_name)
            files.append(_rel(out_dir / docx_name))
            stats["files"].append(docx_name)
        except Exception as exc:  # noqa: BLE001 —— 单个渲染器失败不拖垮整批
            skipped.append({"item": docx_name, "subject": subject, "reason": f"DOCX 生成失败：{exc}"})
            print(f"  [warn] {subject} DOCX 生成失败：{exc}", file=sys.stderr)

        if font_path:
            try:
                render_pdf(built, out_dir / pdf_name, font_path, bold_path)
                files.append(_rel(out_dir / pdf_name))
                stats["files"].append(pdf_name)
            except Exception as exc:  # noqa: BLE001
                skipped.append({"item": pdf_name, "subject": subject, "reason": f"PDF 生成失败：{exc}"})
                print(f"  [warn] {subject} PDF 生成失败：{exc}", file=sys.stderr)
        else:
            skipped.append({"item": pdf_name, "subject": subject,
                            "reason": "无可用中文字体 → 未生成 PDF（避免中文方块字）"})

    # ---------------------------------------------------------- 汇总文件
    aggregates = [("all_questions.xlsx", "xlsx"), ("all_questions.csv", "csv")]
    if ACA_SUBJECT in papers:
        aggregates.append(("aca_llm.apkg", "apkg"))

    if not read_any and not dry:
        warnings.append("选中的科目库一个都没读到 → 未生成任何文件")

    if dry:
        if papers:                      # 与落盘路径保持一致：没有可导出的科目就不列汇总文件
            for name, _kind in aggregates:
                if name == "aca_llm.apkg" and ACA_SUBJECT not in papers:
                    continue
                files.append(_rel(out_dir / name))
        print(f"[export_papers] dry-run: {len(papers)} 科目 / 将生成 {len(files)} 个文件 → {_rel(out_dir)}/")
        summary = {"papers": papers, "files": files, "skipped": skipped, "warnings": warnings,
                   "dry_run": True, "date": str(date_str), "outdir": _rel(out_dir),
                   "cjk_font": font_path}
        return 0, summary

    if papers:
        out_dir.mkdir(parents=True, exist_ok=True)
        try:
            write_xlsx(all_rows, out_dir / "all_questions.xlsx")
            files.append(_rel(out_dir / "all_questions.xlsx"))
        except Exception as exc:  # noqa: BLE001
            skipped.append({"item": "all_questions.xlsx", "reason": f"生成失败：{exc}"})
        try:
            write_csv(all_rows, out_dir / "all_questions.csv")
            files.append(_rel(out_dir / "all_questions.csv"))
        except Exception as exc:  # noqa: BLE001
            skipped.append({"item": "all_questions.csv", "reason": f"生成失败：{exc}"})
        if ACA_SUBJECT in papers:
            if write_apkg(ace_questions, out_dir / "aca_llm.apkg", ace_types, skipped):
                files.append(_rel(out_dir / "aca_llm.apkg"))
    else:
        for name, _kind in aggregates:
            skipped.append({"item": name, "reason": "没有可导出的科目库"})

    total_items = sum(p["actual_items"] for p in papers.values())
    print(f"[export_papers] {len(papers)} 科目 / {total_items} 题 / {len(files)} 个文件 → {_rel(out_dir)}/")
    for f in files:
        print(f"  - {f}")
    for item in skipped:
        print(f"  [skip] {item['item']}: {item['reason']}")
    for w in warnings:
        print(f"  [warn] {w}", file=sys.stderr)

    summary = {"papers": papers, "files": files, "skipped": skipped, "warnings": warnings,
               "dry_run": False, "date": str(date_str), "outdir": _rel(out_dir),
               "cjk_font": font_path}
    return 0, summary


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="export_papers.py",
        description="从各科目库 approved 题组卷导出（docx / pdf / xlsx / csv / apkg）",
    )
    ap.add_argument("--subject", default="all", choices=["all"] + SUBJECTS,
                    help="要导出的科目（默认 all = 全部 4 科）")
    ap.add_argument("--outdir", default=DEFAULT_OUTDIR,
                    help=f"输出根目录（默认 {DEFAULT_OUTDIR}；相对路径按项目根解析），实际写入 <outdir>/<YYYYMMDD>/")
    ap.add_argument("--dry-run", action="store_true", help="只统计题量与将生成的文件名，不写任何文件")
    ap.add_argument("--include-pending", action="store_true",
                    help="额外纳入 status='pending_review' 的题（默认只导 approved）")
    ap.add_argument("--include-unknown", action="store_true",
                    help="把 taxonomy 之外的题型也编入卷子（默认不编入，仅在卷末标注数量）")
    ap.add_argument("--data-dir", default=None, help="（测试用）覆盖科目库目录 data/")
    ap.add_argument("--taxonomy", default=None, help="（测试用）覆盖 config/taxonomy.json")
    ap.add_argument("--date", default=None, help="（测试用）覆盖输出子目录名 YYYYMMDD（默认本地今天）")
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    code, summary = run_export(args)
    print(json.dumps(summary, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
