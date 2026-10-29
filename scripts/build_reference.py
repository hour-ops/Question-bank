#!/usr/bin/env python
"""参考库构建 · 把**考纲 / 知识点 / 真题样例**结构化，供 AI 生成题目时做少样本参考。

用法:
    python scripts/build_reference.py                 # 构建（默认每题型 5 条样例）
    python scripts/build_reference.py --k 4 --quiet
    python scripts/build_reference.py --out tests/.tmp/x.json

产出:
    data/generation_reference.json

设计（为什么这样做）:
  1. **只取真题/教材题，绝不取 AI 自产题**（用户明确要求摆脱"自产自销"）。
     可信度优先级：`official_exam` > `textbook` > `third_party`；
     `trust_level='ai_generated'`、`source_type='generate'`、`fact_source` 含 `AI生成`
     的行**一律排除**。
  2. 样例必须**可学**：答案非空 + **有解析**（解析才教得会"怎么出题"）；
     有解析的不足 3 条时才逐级放宽，并在 `quality_note` 里如实标注。
  3. **材料型题（阅读填空 / 完形 / 选词填空 / 语法填空短文）必须连材料整块存**：
     `material` 存原文、`blanks` 存这一组的**全部空**（题干+答案+解析），
     否则模型学不会"整块题"长什么样（用户特别强调"整块题不要拆开"）。
  4. 连词成句的题干保持 `词组 / 词组` 的**斜杠格式**（真题原格式，渲染层再切词卡）——
     本脚本**只读不改**任何题目字段。
  5. 取样确定性：不使用 `ORDER BY RANDOM()`；按 (可信度, 有解析, 信息完整度) 排序，
     再按 `exam_title` 轮转，保证同一份库每次构建结果一致、且跨年份/跨校覆盖。
  6. 🔴 数据库一律**只读连接**（`mode=ro`），不写任何题目数据。
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
DATA = ROOT / "data"
SUBJECTS = ["english", "c_wuhan", "c_hbpu", "aca_llm"]
OUT = DATA / "generation_reference.json"

TRUST_ORDER = {"official_exam": 0, "textbook": 1, "third_party": 2}
EXCLUDED_TRUST = "ai_generated"

SAMPLE_K = 5          # 每题型目标样例数（要求 3–5）
SAMPLE_MIN = 3        # 低于这个数要在 quality_note 里标注
MAX_MATERIAL = 3200   # 单条材料截断上限（字符）
MAX_EXPLANATION = 1500
MAX_STEM = 2000
MAX_BLANKS = 12       # 整块题最多存几个空（超出记 blanks_truncated）
MAX_KP_PER_TYPE = 40
CHAPTER_RE = re.compile(r"^第\s*(\d+)\s*章")
BLANK_MARK_RE = re.compile(r"\{\{__BLANK_?\d*__\}\}")
# 目标考区优先：英语科目考的是**湖北省**专升本，湖北真题的题型/话题比外省（河北）更贴近考纲，
# 故同等可信度下先取湖北卷，外省真题只作补充（仍会按 exam_title 轮转保证多样性）。
EXAM_PREFIX_PRIORITY = {"english": ["湖北"]}
# 选择题型：选项若为空，样例只剩正确答案、教不了模型"怎么写干扰项"，需在 data_issues 里提醒
CHOICE_TYPES = {"single_choice", "multiple_choice", "true_false", "cloze", "dialogue",
                "phonetics", "translation_choice", "word_fill"}

# 英语考纲要点（来源：inbox/english/zsbzt_exam_guide.md —— 第三方考纲解读，非官方原文）
ENGLISH_FOCUS = {
    "grammar_fill": "有提示词→词形变化（时态/语态/非谓语/词性转换/比较级最高级）；无提示词→冠词 a/an/the、"
                    "介词 in/on/for/at/by/with/to、连词 and/but/if/when/that。十大考点：冠词、介词、连词、"
                    "动词时态、词性转换（形↔名↔副）、比较级最高级、被动语态、非谓语动词、主谓一致、代词。",
    "sentence_build": "把斜杠分隔的词组排成语法正确、意思完整的句子。五种必会句型：主+谓+宾、被动语态句、"
                      "主+谓+宾+宾补(to do)、主系表、现在完成时/含情态动词。句首字母大写、句末加标点。",
    "reading_fill": "2 篇、每篇 5 空、每空 1 词。四种填空能力：原词定位、同义转换、信息归纳、词性适配；"
                    "答案约 90% 是原文原词。话题规律：一篇偏中国文化，一篇偏社会/科普。",
    "reading_qa": "2 篇、每篇 5 题：细节题约 60%（答案可在原文直接找到）、原因/推断题约 20%"
                  "（定位 because/so/in order to 句）、每篇最后 1 题为英译汉。简短回答即可，尽量用原文词。",
    "translation_fill": "给中文 + 不完整英文 + 提示词，每题 3 分。高频考法：if 条件句时态、taught me how to 结构、"
                        "词性转换（形→名）、so...that、固定搭配（keep quiet / make sure）、进行时/被动语态、"
                        "介词短语补全。",
    "writing": "应用文 1 篇、不少于 40 词。可能体裁：电子邮件、通知、邀请函、感谢信、便条留言、自荐信。"
               "覆盖全部要点 > 辞藻；格式为 称呼 Dear... + 正文（2-3 段）+ 落款 Best regards, 名字。",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_json(p: Path, default):
    """读 JSON（容忍 PowerShell 写出的 BOM）。"""
    try:
        return json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception:  # noqa: BLE001
        return default


def connect_ro(p: Path) -> sqlite3.Connection:
    """**只读**连接：绝不修改题库数据。"""
    return sqlite3.connect(f"file:{p.as_posix()}?mode=ro", uri=True)


def clip(s: str | None, limit: int) -> str:
    s = (s or "").strip()
    return s if len(s) <= limit else s[:limit].rstrip() + "…"


# ------------------------------------------------------------------ 可信度判定


def trust_of(trust_level: str | None, source_type: str | None,
             fact_source: str | None) -> tuple[str, bool]:
    """→ (可信度标签, 是否由 source_type 推断得出)。ai_generated 由调用方排除。"""
    tl = (trust_level or "").strip()
    if tl in TRUST_ORDER or tl == EXCLUDED_TRUST:
        return tl, False
    if (source_type or "") == "generate" or "AI生成" in (fact_source or ""):
        return EXCLUDED_TRUST, True
    return "third_party", True   # trust_level 为空（fetch/real_exam 未标注）→ 按第三方处理


# ------------------------------------------------------------------ 取样


def fetch_rows(conn: sqlite3.Connection, qtype: str) -> list[dict]:
    rows = conn.execute(
        "SELECT id, question_uid, group_uid, exam_title, trust_level, source_type, fact_source, "
        "stem, material_text, answer, explanation, options, knowledge_point, status "
        "FROM questions WHERE question_type=? ORDER BY id", (qtype,)).fetchall()
    keys = ("id", "uid", "group", "exam", "trust_level", "source_type", "fact_source",
            "stem", "material", "answer", "explanation", "options", "kp", "status")
    return [dict(zip(keys, r)) for r in rows]


def is_block_group(rows: list[dict]) -> bool:
    """一组是否应视为**整块题**：共享材料，或组内存在空题干（空＝属于某篇材料的某个空）。"""
    if len(rows) < 2:
        return False
    if any((r["material"] or "").strip() for r in rows):
        return True
    return any(not (r["stem"] or "").strip() for r in rows)


def parse_options(raw: str | None) -> list:
    try:
        opts = json.loads(raw or "[]")
    except Exception:  # noqa: BLE001
        return []
    return opts if isinstance(opts, list) and opts else []


def make_block(rows: list[dict], exam: str, trust: str, inferred: bool, kind: str) -> dict:
    """把一组行组装成**整块题**样例：材料 + 该组全部空（整块不拆开）。"""
    material = ""
    for r in rows:  # 组内材料一致，取最长的一条最保险
        if len((r["material"] or "").strip()) > len(material):
            material = (r["material"] or "").strip()
    blanks, truncated = [], False
    for i, r in enumerate(rows, 1):
        if len(blanks) >= MAX_BLANKS:
            truncated = True
            break
        b = {"no": i, "stem": clip(r["stem"], MAX_STEM) or f"第{i}空",
             "answer": (r["answer"] or "").strip(), "explanation": clip(r["explanation"], MAX_EXPLANATION)}
        opts = parse_options(r.get("options"))
        if opts:
            b["options"] = opts
        blanks.append(b)
    first = blanks[0]
    stem_top = next((clip(r["stem"], MAX_STEM) for r in rows if (r["stem"] or "").strip()), "")
    s = {
        "kind": kind,                              # material_block（有材料）/ group（无材料、按空编号）
        "stem": stem_top,
        "answer": first["answer"],
        "explanation": first["explanation"],
        "exam": exam, "trust": trust,
        "group_uid": next((r["group"] for r in rows if r["group"]), ""),
        "blanks_total": len(rows),
        "blanks": blanks,
        "_id": min(r["id"] for r in rows),
    }
    if material:
        s["material"] = clip(material, MAX_MATERIAL)
    if not stem_top:
        # 空题干 + 有材料 = 这一组的"题干"就是材料本身（逐空见 blanks）。
        # 明确打标记，避免消费方（含生成提示词）误以为"题干可以为空"。
        s["stem_in_material"] = True
    if truncated:
        s["blanks_truncated"] = True
    if inferred:
        s["trust_inferred"] = True
    kps = sorted({(r["kp"] or "").strip() for r in rows if (r["kp"] or "").strip()})
    if kps:
        s["knowledge_point"] = "；".join(kps[:3])
    return s


def make_single(r: dict, exam: str, trust: str, inferred: bool) -> dict:
    s = {"kind": "single", "stem": clip(r["stem"], MAX_STEM), "answer": (r["answer"] or "").strip(),
         "explanation": clip(r["explanation"], MAX_EXPLANATION), "exam": exam, "trust": trust,
         "_id": r["id"]}
    opts = parse_options(r.get("options"))
    if opts:
        s["options"] = opts
    if (r["kp"] or "").strip():
        s["knowledge_point"] = r["kp"].strip()
    if inferred:
        s["trust_inferred"] = True
    if BLANK_MARK_RE.search(r["stem"] or ""):
        s["blank_markers"] = True   # 整块题干内嵌 {{__BLANK_n__}} 标记（连空白一起保留）
    return s


def has_expl(s: dict) -> bool:
    if s["kind"] == "single":
        return bool(s["explanation"])
    return any(b["explanation"] for b in s["blanks"])


def completeness(s: dict) -> int:
    """越信息完整越靠前（负数用于升序排序）。"""
    if s["kind"] == "single":
        return -(min(len(s["explanation"]), 600) + min(len(s["stem"]), 300) // 3)
    n_expl = sum(1 for b in s["blanks"] if b["explanation"])
    return -(n_expl * 40 + len(s["blanks"]) * 5 + (30 if s.get("material") else 0)
             + min(len(s["explanation"]), 400) // 10)


def exam_rank(s: dict, prefixes: list[str]) -> int:
    """目标考区（如湖北）真题排前面。"""
    return 0 if any(s["exam"].startswith(p) for p in prefixes) else 1


def build_candidates(rows: list[dict], prefixes: list[str]) -> tuple[list[dict], Counter, dict]:
    """过滤 + 组装 + 排序 → (候选样例, 可信度统计, 过滤统计)。

    硬性过滤：答案非空 且（题干非空 或 材料非空）；排除 ai_generated。
    排序：可信度 → 有解析优先 → 目标考区优先 → 信息完整度 → 题干（稳定序，保证可重复）。
    """
    stats = {"rows": len(rows), "excluded_ai": 0, "excluded_rejected": 0, "no_answer": 0,
             "no_content": 0, "no_expl": 0}
    trust_cnt: Counter = Counter()
    kept: list[dict] = []
    for r in rows:
        trust, inferred = trust_of(r["trust_level"], r["source_type"], r["fact_source"])
        if trust == EXCLUDED_TRUST:
            stats["excluded_ai"] += 1
            continue
        if (r["status"] or "").strip() == "rejected":
            # 审核已判不合格的题绝不能当范例（实测 official_exam/textbook 全部为 approved，
            # 被拒的都是没标 trust 的抓取/AI 题，但 third_party 回退层必须挡住）
            stats["excluded_rejected"] += 1
            continue
        trust_cnt[trust] += 1
        if not (r["answer"] or "").strip():
            stats["no_answer"] += 1
            continue
        if not (r["stem"] or "").strip() and not (r["material"] or "").strip():
            stats["no_content"] += 1
            continue
        if not (r["explanation"] or "").strip():
            stats["no_expl"] += 1
        r["_trust"], r["_inferred"] = trust, inferred
        kept.append(r)

    # 分组：同 group_uid 且确属整块题的合成一条；其余各自成条（保持 id 顺序）
    groups: dict[str, list[dict]] = {}
    for r in kept:
        g = (r["group"] or "").strip()
        groups.setdefault(g or f"uid:{r['uid']}", []).append(r)

    cands: list[dict] = []
    for grp in groups.values():
        best = min(grp, key=lambda r: TRUST_ORDER.get(r["_trust"], 9))
        trust, inferred = best["_trust"], best["_inferred"]
        exam = next((g["exam"] for g in grp if (g["exam"] or "").strip()), "") or ""
        if is_block_group(grp):
            kind = "material_block" if any((g["material"] or "").strip() for g in grp) else "group"
            cands.append(make_block(grp, exam, trust, inferred, kind))
        else:
            for r in grp:
                cands.append(make_single(r, (r["exam"] or "").strip(), r["_trust"], r["_inferred"]))

    cands.sort(key=lambda s: (TRUST_ORDER.get(s["trust"], 9), 0 if has_expl(s) else 1,
                              exam_rank(s, prefixes), completeness(s), s["exam"], s["_id"],
                              s["stem"][:40]))
    return cands, trust_cnt, stats


def pick_samples(cands: list[dict], k: int, prefixes: list[str] | None = None) -> tuple[list[dict], str, list[str]]:
    """按可信度分层取样 + 按 exam_title 轮转（跨年份/跨校覆盖、结果确定）。

    → (样例列表, 实际使用的最高可信度, 质量备注)
    """
    prefixes = prefixes or []
    notes: list[str] = []
    if not cands:
        return [], "", ["无可用样例（题干/材料/答案缺失，或全部为 AI 生成）"]

    with_expl = [c for c in cands if has_expl(c)]
    if len(with_expl) >= SAMPLE_MIN:
        pool = with_expl
    else:
        pool = cands
        notes.append(f"该题型有解析的样例仅 {len(with_expl)} 条（<{SAMPLE_MIN}），已放宽解析要求")

    top = pool[0]["trust"]           # pool 已按可信度排序
    tier = [c for c in pool if c["trust"] == top]
    if len(tier) < SAMPLE_MIN:
        notes.append(f"最高可信度 {top} 可用样例仅 {len(tier)} 条（<{SAMPLE_MIN}），已混入更低可信度")
        tier = pool

    picked: list[dict] = []
    seen_exam: Counter = Counter()
    rest = sorted(tier, key=lambda s: (exam_rank(s, prefixes), s["_id"]))
    while rest and len(picked) < k:
        # 未用过的 exam 优先（跨套覆盖），同层内目标考区（湖北）在前 → 轮转
        rest.sort(key=lambda s: (seen_exam[s["exam"]], exam_rank(s, prefixes), s["_id"]))
        s = rest.pop(0)
        seen_exam[s["exam"]] += 1
        picked.append(s)

    if len(picked) < SAMPLE_MIN:
        notes.append(f"仅取到 {len(picked)} 条样例（<{SAMPLE_MIN}）")
    mixed = sorted({s["trust"] for s in picked})
    if len(mixed) > 1:
        notes.append("样例混合可信度：" + "/".join(mixed))
    return picked, top, notes


# ------------------------------------------------------------------ 科目 / 知识点 / 考纲


def build_subject(subj: str, k: int, display: dict, debug: list[str]) -> dict:
    p = DATA / f"{subj}.sqlite"
    if not p.exists():
        return {}
    conn = connect_ro(p)
    types = [r[0] for r in conn.execute(
        "SELECT question_type FROM questions WHERE question_type IS NOT NULL AND question_type<>'' "
        "GROUP BY 1 ORDER BY 1")]
    out: dict = {"name": (display.get("subject_names") or {}).get(subj, subj), "db": f"data/{subj}.sqlite",
                 "by_type": {}, "exams": [], "trust_counts": {}}
    overall_trust: Counter = Counter()
    all_exams: Counter = Counter()
    prefixes = EXAM_PREFIX_PRIORITY.get(subj, [])
    for qtype in types:
        rows = fetch_rows(conn, qtype)
        cands, trust_cnt, stats = build_candidates(rows, prefixes)
        overall_trust.update(trust_cnt)
        for r in rows:
            if (r["exam"] or "").strip():
                all_exams[r["exam"].strip()] += 1
        samples, top_trust, notes = pick_samples(cands, k, prefixes)
        for s in samples:
            s.pop("_id", None)      # 清掉内部排序键，不落盘
        kp = Counter((r["kp"] or "").strip() for r in rows if (r["kp"] or "").strip())
        cfg = (display.get("types") or {}).get(qtype) or {}
        entry = {
            "name": cfg.get("name", qtype),
            "how": cfg.get("how", ""),
            "answer_label": cfg.get("answer_label", "参考答案"),
            "count": stats["rows"],                  # 库里该题型总题数
            "usable_count": len(cands),              # 过滤后可当样例的题数（整块题算 1 条）
            "sample_count": len(samples),
            "sample_trust": top_trust,
            "samples": samples,
            "knowledge_points": [x for x, _ in kp.most_common(MAX_KP_PER_TYPE)],
            "quality_note": "；".join(notes),
            "excluded": {"ai_generated": stats["excluded_ai"], "rejected": stats["excluded_rejected"],
                         "no_answer": stats["no_answer"], "no_content": stats["no_content"],
                         "no_explanation": stats["no_expl"]},
        }
        if qtype == "sentence_build":
            entry["stem_format"] = "词组 / 词组（斜杠分隔，真题原格式；渲染层再切词卡，构建时不得改动）"
        if any(s["kind"] != "single" for s in samples):
            entry["material_blocks"] = sum(1 for s in samples if s["kind"] != "single")
            entry["material_note"] = ("整块题不拆开：`material` 是整块原文，`blanks` 是这一组的**全部空**"
                                      "（每空带 no/stem/answer/explanation）；材料在库中是以『按空分行』存放的，"
                                      "构建时按 group_uid 重新合成整块，未改动任何字段。"
                                      "`stem_in_material=true` 表示该组的题干即材料本身。")
        out["by_type"][qtype] = entry
        if stats["no_content"]:
            debug.append(f"{subj}/{qtype}: {stats['no_content']} 行既无题干也无材料（如语音题丢了选项词），已排除")
        if stats["no_expl"]:
            debug.append(f"{subj}/{qtype}: {stats['no_expl']} 行无解析（仍可作样例，但排序靠后）")
        if stats["excluded_ai"]:
            debug.append(f"{subj}/{qtype}: 排除 AI 生成 {stats['excluded_ai']} 行")
        if len(samples) < SAMPLE_MIN:
            debug.append(f"{subj}/{qtype}: 样例只有 {len(samples)} 条（<{SAMPLE_MIN}）")
        if qtype in CHOICE_TYPES and samples and all(not s.get("options") for s in samples):
            debug.append(f"{subj}/{qtype}: 该题型 options 列为空，样例只有正确答案、没有干扰项 —— "
                         f"AI 无法从样例学到选项写法（数据侧待补，构建脚本只读不改）")
    conn.close()
    out["trust_counts"] = dict(overall_trust)
    out["exams"] = [{"title": t, "count": n} for t, n in all_exams.most_common()]
    out["official_exam"] = {"count": int(overall_trust.get("official_exam", 0)),
                            "exams": [e["title"] for e in out["exams"]]}
    return out


def build_knowledge_points() -> tuple[dict, dict]:
    kps: dict[str, list[str]] = {}
    meta: dict[str, dict] = {}
    for subj in SUBJECTS:
        p = DATA / f"{subj}.sqlite"
        if not p.exists():
            continue
        conn = connect_ro(p)
        cnt = Counter((r[0] or "").strip() for r in conn.execute(
            "SELECT knowledge_point FROM questions WHERE knowledge_point IS NOT NULL AND knowledge_point<>''"))
        conn.close()
        chapters = sorted((x for x in cnt if CHAPTER_RE.match(x)),
                          key=lambda x: (int(CHAPTER_RE.match(x).group(1)), x))
        ch_set = set(chapters)
        others = [x for x, _ in cnt.most_common() if x not in ch_set]
        kps[subj] = chapters + others
        meta[subj] = {"source": f"data/{subj}.sqlite questions.knowledge_point（库内标签汇总）",
                      "distinct": len(cnt), "chapters": len(chapters), "top": cnt.most_common(8)}

    # ACA 以**考纲 47 个知识点**为准（库里的自由标签噪声大，只保留在题型级 knowledge_points）
    syl_p = ROOT / "subjects" / "aca_llm" / "syllabus_index.json"
    sy = load_json(syl_p, {})
    pts = []
    for m in (sy.get("modules") or []):
        for pt in (m.get("points") or []):
            txt = re.sub(r"\*\*", "", pt.get("knowledge_point") or "").strip()
            if txt:
                pts.append(f"{pt.get('code', '')} {txt}".strip())
    if pts:
        kps["aca_llm"] = pts
        meta["aca_llm"] = {"source": "subjects/aca_llm/syllabus_index.json（考纲 V2.4，权威；"
                                     "对应 inbox/aca_llm/aca_v24_knowledge_points.md）",
                           "distinct": len(pts), "chapters": 0,
                           "db_tags_note": "库内 knowledge_point 是抓取源的自由标签（如「RAG，检索」），"
                                           "噪声大，未作为知识点清单，仅出现在各题型 knowledge_points 里"}
    return kps, meta


def build_syllabus(tax: dict, kps: dict, display: dict) -> dict:
    """考纲要点摘要（**字符串**，可直接塞进提示词）。数字全部取自 taxonomy.json，避免口径漂移。"""
    out: dict[str, str] = {}
    subs = tax.get("subjects") or {}

    en = subs.get("english") or {}
    qt = en.get("question_types") or {}
    lines = ["## 湖北省普通专升本《大学英语》考纲要点",
             "- 来源：config/taxonomy.json（paper_note 引《2026年湖北省普通高等学校专升本〈大学英语〉考试要求》）"
             " + inbox/english/zsbzt_exam_guide.md（第三方考纲解读，非官方原文）",
             f"- 卷面：满分 {en.get('paper_total_score', 100)} 分 / {en.get('paper_duration_minutes', 120)} 分钟 /"
             f" 共 {en.get('paper_total_items', 43)} 题；**全部主观题，无选择题、无判断题**"
             f"（禁止题型：{'、'.join(en.get('forbidden_types') or [])}）",
             "- 题型与分值："]
    for t, c in qt.items():
        lines.append(f"  - {c.get('name', t)}：{c.get('paper_count')} 题 × {c.get('per_item')} 分"
                     f" = {c.get('paper_score')} 分")
    lines.append("- 各题型考点要点：")
    for t, c in qt.items():
        focus = ENGLISH_FOCUS.get(t)
        if focus:
            lines.append(f"  - {c.get('name', t)}：{focus}")
    out["english"] = "\n".join(lines)

    ac = subs.get("aca_llm") or {}
    aqt = ac.get("question_types") or {}
    lines = ["## 阿里云大模型工程师 ACA V2.4 考纲要点",
             "- 来源：inbox/aca_llm/aca_v24_syllabus.pdf（官方）→ subjects/aca_llm/syllabus_index.json；"
             "认证页 https://edu.aliyun.com/certification/aca13",
             f"- 卷面：满分 {ac.get('paper_total_score', 100)} 分 / {ac.get('paper_duration_minutes', 60)} 分钟；"
             "及格 80 分；" + "；".join(f"{c.get('name', t)} {c.get('paper_count')} 题 × {c.get('per_item')} 分"
                                        for t, c in aqt.items()),
             "- 六大模块与权重（考纲原文）："]
    for name, w in (ac.get("syllabus_v2_4") or {}).items():
        lines.append(f"  - {name}：{int(round(w * 100))}%")
    lines.append(f"- 知识点共 {len(kps.get('aca_llm') or [])} 条（见 knowledge_points.aca_llm，按考纲条目编号）；"
                 "命题须落在这些条目内，不得超纲")
    out["aca_llm"] = "\n".join(lines)

    for subj in ("c_wuhan", "c_hbpu"):
        sc = subs.get(subj) or {}
        sqt = sc.get("question_types") or {}
        chs = [x for x in (kps.get(subj) or []) if CHAPTER_RE.match(x)]
        lines = [f"## {sc.get('name', subj)} 考纲要点",
                 f"- 来源：config/taxonomy.json（{sc.get('notes', '')}）",
                 f"- 卷面：满分 {sc.get('paper_total_score', '?')} 分；题型：" +
                 "；".join(f"{c.get('name', t)}（判分 {c.get('judge', '')}）" for t, c in sqt.items()) +
                 f"；禁止题型：{'、'.join(sc.get('forbidden_types') or [])}",
                 f"- 教材章节范围（{len(chs)} 章，取自题库 knowledge_point）：" + "、".join(chs),
                 "- ⚠️ 尚未取得该科目官方考纲原文，卷面题数与分值待补（taxonomy 的 notes 已如实标注）"]
        out[subj] = "\n".join(lines)
    return out


# ------------------------------------------------------------------ main


def main() -> int:
    ap = argparse.ArgumentParser(description="构建 AI 生成用的参考库（考纲 + 知识点 + 真题样例）")
    ap.add_argument("--k", type=int, default=SAMPLE_K, help=f"每题型样例数（默认 {SAMPLE_K}）")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    display = load_json(ROOT / "config" / "display.json", {})
    tax = load_json(ROOT / "config" / "taxonomy.json", {})
    debug: list[str] = []

    subjects: dict[str, dict] = {}
    for subj in SUBJECTS:
        s = build_subject(subj, args.k, display, debug)
        if s:
            subjects[subj] = s
    kps, kp_meta = build_knowledge_points()
    doc = {
        "schema_version": 1,
        "built_at": now_iso(),
        "built_by": "scripts/build_reference.py",
        "note": "AI 生成题目时的少样本参考库：真题样例（带出处/解析）+ 知识点 + 考纲摘要。"
                "取样只认 official_exam > textbook > third_party，绝不使用 ai_generated。",
        "rules": {
            "trust_priority": list(TRUST_ORDER),
            "exclude": [EXCLUDED_TRUST, "source_type='generate'", "fact_source 含『AI生成』",
                        "status='rejected'（审核已判不合格的题不得当范例）"],
            "require": "答案非空 且（题干非空 或 材料非空）；有解析者优先（有解析才教得会怎么出题）",
            "material_rule": "材料型题整块存：material 存原文、blanks 存该组全部空（题干+答案+解析），"
                             f"单块最多 {MAX_BLANKS} 空（超出记 blanks_truncated）；"
                             "连词成句保持 `词组 / 词组` 斜杠原格式，构建时零改写",
            "samples_per_type": [SAMPLE_MIN, SAMPLE_K],
            "deterministic": "不使用 ORDER BY RANDOM()；按可信度/有解析/目标考区/完整度排序 + 按 exam_title 轮转",
            "exam_priority": EXAM_PREFIX_PRIORITY,
            "keys": {"by_type.*": ["name", "how", "answer_label", "count(库里本题型总题数)", "usable_count(过滤后可用)",
                                   "sample_count", "sample_trust", "samples", "knowledge_points",
                                   "quality_note", "excluded", "material_blocks", "stem_format"]},
        },
        "subjects": subjects,
        "knowledge_points": kps,
        "knowledge_points_meta": kp_meta,
        "syllabus": build_syllabus(tax, kps, display),
        "data_issues": debug,
    }
    out_p = Path(args.out)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    size_kb = out_p.stat().st_size / 1024
    n_samp = sum(t["sample_count"] for s in subjects.values() for t in s["by_type"].values())
    n_oe = sum(1 for s in subjects.values() for t in s["by_type"].values()
               for x in t["samples"] if x["trust"] == "official_exam")
    n_blocks = sum(1 for s in subjects.values() for t in s["by_type"].values()
                   for x in t["samples"] if x["kind"] != "single")
    print(f"参考库 -> {out_p}（{size_kb:.1f} KB）")
    print(f"样例合计 {n_samp} 条（整块题 {n_blocks} 条），其中 official_exam {n_oe} 条"
          f"（{100 * n_oe / max(1, n_samp):.1f}%）")
    if not args.quiet:
        print("\n=== 各科各题型样例数 ===")
        for subj, s in subjects.items():
            print(f"  {subj}（{s['name']}）official_exam={s['official_exam']['count']}  "
                  f"真题卷 {len(s['exams'])} 套")
            for qt, t in s["by_type"].items():
                flag = "  ⚠️ 样例不足" if t["sample_count"] < SAMPLE_MIN else ""
                print(f"    {qt:20} 样例 {t['sample_count']}  可用 {t['usable_count']:5}  "
                      f"总题数 {t['count']:5}  trust={t['sample_trust'] or '-':14} "
                      f"知识点 {len(t['knowledge_points']):3}{flag}")
        if debug:
            print("\n=== 数据提醒 ===")
            for d in debug[:25]:
                print("  -", d)
    return 0


if __name__ == "__main__":
    sys.exit(main())
