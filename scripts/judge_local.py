#!/usr/bin/env python
"""规则判分（本地确定性判分，**不联网、不计费**）—— 需求 2 的单一事实源。

用户诉求原话：「有明确答案的题不要 AI 判分」。
根因：`/api/submit` 只入队，判分全靠 `sync_outbox.py` 走付费 LLM；没填 key 时
`judge_score` 恒为 NULL → `daily_progress` 全零 → 首页「今日进度」永远不动（需求 10）。

设计原则（**宁放不误**）：
  1. **判错（false negative）可接受**：分数写 0，用户仍能看到正确答案；再点「AI 复核」
     还能走付费通道。误判成 unknown 不写库，不损坏数据。
  2. **判对（false positive）不可接受**：把错的记成对，会污染 SM-2 复习排程与正确率。
     因此任何「规范化后仍不确定」的情况一律 `gradeable=False`（交给 AI 或人工）。
  3. 判分口径与 `sync_outbox.py` / `update_daily_progress.py` 对齐：
     - 满分来自 `config/taxonomy.json`（`per_item` / `score_correct` / `score_all_correct`），
       ACA 走 `config/aca_rules.json`；
     - 正确 = 全对（`score == full`），与 `judge_correct()` 的 `score >= full` 等价。

用法（库）:
    from judge_local import judge_local
    v = judge_local(subject, question_type, answer, user_answer)
    if v.gradeable:
        # v.score / v.full_score / v.reason / v.model / v.correct
    else:
        # 交给 AI：v.reason 是"为什么本地判不了"

命令行（覆盖率体检，**只读**）:
    python scripts/judge_local.py --coverage
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import unicodedata
from dataclasses import dataclass, asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
TAXONOMY = ROOT / "config" / "taxonomy.json"
ACA_RULES = ROOT / "config" / "aca_rules.json"
SUBJECTS = ("english", "c_wuhan", "c_hbpu", "aca_llm")
ACA_SUBJECT = "aca_llm"

# ========================= 题型分类（需求 2 的四条通道） =========================

CHOICE_TYPES = frozenset({
    # ④ 客观选择题：答案就是一个选项字母（可含 "B. needed" 这类选项原文）
    "single_choice", "multiple_choice", "cloze", "phonetics", "dialogue",
    "word_fill", "translation_choice", "matching", "reading_choice",
})
# ① 是非题：答案可能是 正确/错误、对/错、T/F、True/False
BOOL_TYPES = frozenset({"true_false", "judgement", "judge", "true_or_false", "boolean"})
# ② 填空类：答案是一小段文本（可有 "a | b" 备选），规范化后比对
BLANK_TYPES = frozenset({
    "grammar_fill", "reading_fill", "translation_fill", "outline_fill",
    "sentence_completion", "program_fill", "code_correction",
    "word_spelling", "blank", "fill", "fill_blank", "short_answer",
})
# ③ 短答类：C 语言的"运行结果 / 改错"多为短文本，但长答案往往是论述题 → 长度闸门
SHORT_ANSWER_TYPES = frozenset({"reading_qa", "reading_comprehension", "short_answer_text"})
# ⑤ 连词成句：给出乱序单词，答案句子唯一 → 标点/大小写/空白无关，词序有关
SENTENCE_BUILD_TYPES = frozenset({"sentence_build", "sentence_reorder", "reorder"})
# ⑥ 明确必须走 AI：写作、整段翻译、开放式简答
AI_ONLY_TYPES = frozenset({"writing", "translation", "essay", "composition", "paragraph_translation"})
# ⑦ C 语言"看程序写结果 / 填空"类：答案是一小段输出或表达式，长度闸门内可精确比对。
#    实测 c_hbpu 有 119 题标成 programming，答案只是 '5050' / '2 1' / 'c=2.000000, d=2.500000'。
PROGRAM_OUTPUT_TYPES = frozenset({"programming", "code_output", "program_output", "code_reading"})

# 文本题长度闸门：规范化后的参考答案或作答超过该长度 → 判不了（多是论述题/整段翻译）。
# 例：c_wuhan 有把"简述计算机系统的层次结构"标成 program_fill 的题，答案 100+ 字。
MAX_TEXT_LEN = 80
# SHORT_ANSWER 更严：C 的 reading_qa 里既有 "a=10" 这种短答案，也有整段改正后的代码。
MAX_SHORT_ANSWER_LEN = 40
# 客观题答案里允许抽出的选项字母上限：超过就是代码/论述里凑出来的假字母
# （实测 c_wuhan 的 programming 答案是一整段 C 代码 → 抽出 "ABCDFGH"）。
MAX_OPTION_LETTERS = 4
# 客观题答案长度闸门：`"A. 软件仅指计算机程序本身，不包括文档"` 这种要放行，
# 但"整段代码 + 换行"要挡住（换行/代码标记出现即判为不是选项答案）。
MAX_OPTION_ANSWER_LEN = 24

# 选项字母集合的字符集：题库实测出现到 O（英语 word_fill 是 15 选 10 的匹配题）
_LETTERS = "ABCDEFGHIJKLMNOP"
_LETTER_SET = set(_LETTERS)
_BOOL_TRUE = {"t", "true", "y", "yes", "1", "对", "正确", "是", "√", "v"}
_BOOL_FALSE = {"f", "false", "n", "no", "0", "错", "错误", "否", "×", "x", "ⅹ"}

# "A" / "C" / "AC" / "A,C" / "A、C" 这种"纯选项答案"（**没有**选项原文）
# 形态：单个字母 + 可选分隔符序列，或 2–4 个连续字母（`"ABD"` = 多选题答案）
# ⚠️ 两个踩过的坑：① 早期只允许分隔写法 → 多选答案 `"ABD"` 被拒；
#    ② 分隔符写成可选 → `"B. has worked"` 被当成纯字母串 `"bhasworked"` 而判成"没有选项字母"。
_PURE_LETTERS = re.compile(r"^(?:[A-Za-z]"
                           r"|[A-Za-z](?:\s*[.,、，;；/|]\s*[A-Za-z])+[.,、，;；]?"
                           r"|[A-Za-z]{2,4}[.,、，;；]?)$")
# 题干里的空标记（多空题判据）：`{{__BLANK_1__}}` / `{{__SELECT_2__}}`
_BLANK_MARKER = re.compile(r"\{\{\s*__[A-Z_]+\d*__\s*\}\}")
# "B. has worked" / "A、正确" / "ABD. 说明" 这种"字母 + 选项原文"
_LETTER_PREFIX = re.compile(r"^([A-Za-z]{1,4})\s*[.、)．]\s*(\S.*)$", re.S)
# 题干内嵌选项：换行/空白 + 单个字母 + `.`/`、`/`)` + 选项原文（长度 1–60，遇下一选项即止）
_EMBEDDED_OPT = re.compile(
    r"(?:^|\n|\s)([A-P])\s*[.、)．]\s*([^\n]{1,60}?)(?=\s*(?:\n|\s)[A-P]\s*[.、)．]|$)",
    re.M,
)

# 参考答案里的常见前缀噪声（采集自带）：【答案】/ 答案】/ 答案:/ Answer:/ 空(1)处填：/ 1.
_PREFIX_PATTERNS = (
    re.compile(r"^\s*[【\[(（]\s*答\s*案\s*[】\])）]\s*[:：]?\s*"),
    re.compile(r"^\s*答\s*案\s*[】\])）]\s*[:：]?\s*"),
    re.compile(r"^\s*答\s*案\s*[:：]\s*"),
    re.compile(r"^\s*[Aa]nswer\s*[:：]\s*"),
    re.compile(r"^\s*空\s*[（(]?\s*\d+\s*[）)]?\s*处\s*(填|应填|填写)\s*[:：]?\s*"),
    re.compile(r"^\s*参\s*考\s*答\s*案\s*[:：]\s*"),
    re.compile(r"^\s*[（(]\s*\d+\s*[）)]\s*"),
    re.compile(r"^\s*\d+\s*[.、)]\s*"),
)
# "B. needed" / "B、needed" / "B needed" → 取字母
_OPTION_LETTER = re.compile(r"^([A-Ha-h])\s*[.、)．,，:：]?\s*(.*)$", re.S)
# 备选答案分隔符：`a | b`（题库惯用）、`a / b`、`a；b`
_ALT_SPLIT = re.compile(r"\s*[|｜]\s*")
# 中文/英文标点统一（比对时忽略）
_PUNCT_MAP = {
    "，": ",", "。": ".", "、": ",", "；": ";", "：": ":",
    "？": "?", "！": "!", "（": "(", "）": ")", "【": "[", "】": "]",
    "《": "<", "》": ">", "“": '"', "”": '"', "‘": "'", "’": "'",
    "—": "-", "–": "-", "－": "-", "…": "...", "·": ".", "～": "~",
}
# 句末标点（比对时去掉）
_TRAILING_PUNCT = " \t\r\n.。!！?？;；,，:：\"'`"


@dataclass
class Verdict:
    """规则判分结果。`gradeable=False` 时 score/full_score 无语义（一律为 0）。"""

    gradeable: bool
    correct: bool = False
    score: float = 0.0
    full_score: float = 0.0
    reason: str = ""
    model: str = "local_rule"

    def to_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------- 配置


def _load_json(path: Path, encoding: str = "utf-8") -> dict:
    """读 JSON；`utf-8-sig` 是给 PS 写的带 BOM 文件兜底的（见项目约束第 7 条）。"""
    for enc in (encoding, "utf-8-sig"):
        try:
            data = json.loads(path.read_text(encoding=enc))
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            continue
    return {}


def aca_rules() -> dict:
    return _load_json(ACA_RULES)


def aca_full_score(rules: dict | None = None, question_type: str | None = None) -> float:
    """ACA 满分：单选取 `single_choice.correct`，多选取 `multiple_choice.all_correct`。

    与 `update_daily_progress.aca_full_score()` 同口径（两边都读同一份 aca_rules.json，
    读不到才回落到 2.0）。
    """
    r = rules if isinstance(rules, dict) else aca_rules()
    multi = (question_type or "").lower() == "multiple_choice"
    key, field = ("multiple_choice", "all_correct") if multi else ("single_choice", "correct")
    try:
        val = float((r.get(key) or {}).get(field))
        if val > 0:
            return val
    except (TypeError, ValueError):
        pass
    return 2.0


def full_score_for(subject: str, question_type: str | None = None,
                   taxonomy: dict | None = None) -> float:
    """该题型满分：与 `sync_outbox.full_score_for()` / `app.judge_full_score()` 同口径。

    顺序：taxonomy 的 `per_item` → `score_correct` → `score_all_correct` → aca_rules → 1.0。
    """
    tax = taxonomy if isinstance(taxonomy, dict) else _load_json(TAXONOMY)
    cfg = (((tax.get("subjects") or {}).get(subject) or {}).get("question_types") or {}).get(question_type or "") or {}
    for key in ("per_item", "score_correct", "score_all_correct"):
        try:
            val = float(cfg.get(key))
            if val > 0:
                return val
        except (TypeError, ValueError):
            continue
    if subject == ACA_SUBJECT:
        return aca_full_score(question_type=question_type)
    return 1.0


# --------------------------------------------------------------------------- 规范化


def strip_answer_prefix(text: str) -> str:
    """去掉参考答案自带的标签噪声（【答案】/ Answer:/ 空(1)处填：/ 1.）。可反复命中。"""
    out = str(text or "")
    for _ in range(4):
        before = out
        for pat in _PREFIX_PATTERNS:
            out = pat.sub("", out, count=1)
        if out == before:
            break
    return out


def normalize_text(text: str) -> str:
    """文本规范化：NFKC → 标点统一 → 去前缀 → 折叠空白 → 小写 → 去句末标点。"""
    s = unicodedata.normalize("NFKC", str(text or ""))
    for src, dst in _PUNCT_MAP.items():
        s = s.replace(src, dst)
    s = strip_answer_prefix(s)
    s = re.sub(r"\s+", " ", s).strip()
    s = s.lower()
    return s.strip(_TRAILING_PUNCT).strip()


def normalize_compact(text: str) -> str:
    """比 `normalize_text` 更宽：再抹掉所有空白与标点（连接词成句、拼写类比对用）。"""
    s = normalize_text(text)
    return re.sub(r"[\s.,;:!?()\[\]{}<>\"'`~_\-+=*/\\|&%$#@^]", "", s)


def normalize_tokens(text: str) -> str:
    """紧凑形再抹掉标点（`"a. because smoking is harmful"` → `"abecausesmokingisharmful"`）。

    用途：紧凑比对（C 的"运行结果"、短答）里，用户写 `1, 2` 而参考答案写 `1 2` 时也要能比中。
    """
    return re.sub(r"[\s.,;:!?()\[\]{}<>\"'`~\-+=*/\\|&%$#@^]", "", normalize_text(text))


def alternatives(answer) -> list[str]:
    """参考答案 → 备选列表（`a | b` / 列表 → 多项都算对），**dedupe 保序**。

    ⚠️ 曾经的坑：`"A | B"` 这种带分隔符的原始串会被当成一个备选，
    于是用户答 `A` 或 `B` 都判错（探针实测）。这里先展开、再按规范化结果去重。
    """
    if answer is None:
        return []
    if isinstance(answer, (list, tuple)):
        raw = [str(x) for x in answer]
    else:
        raw = _ALT_SPLIT.split(str(answer))
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        text = item.strip()
        if not text:
            continue
        key = normalize_compact(text)
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def _answer_variants(answer) -> tuple[list[str], list[str], list[str]]:
    """参考答案 → (文本形, 紧凑形, 抹标点形) 三套备选（各自去重、去空）。

    - 文本形：`normalize_text`（保空白，折叠标点）；
    - 紧凑形：`normalize_compact`（抹标点，保空白）；
    - 抹标点形：`normalize_tokens`（空白+标点都抹），**由"去掉标签噪声后的原始备选"直接算**——
      否则 `"A. Because …"` 会变成 `"abecause…"`，选项前缀就再也剥不掉（实测过的坑）。
    """
    text_alts: list[str] = []
    compact_alts: list[str] = []
    token_alts: list[str] = []
    seen = (set(), set(), set())
    for alt in alternatives(answer):
        raw = strip_answer_prefix(alt)
        for bucket, seen_set, value in (
            (text_alts, seen[0], normalize_text(alt)),
            (compact_alts, seen[1], normalize_compact(alt)),
            (token_alts, seen[2], normalize_tokens(raw)),
        ):
            if value and value not in seen_set:
                seen_set.add(value)
                bucket.append(value)
    return text_alts, compact_alts, token_alts


def extract_letters(text: str) -> str:
    """从**作答**里抽选项字母集合。`"B. needed"`→`"B"`，`"A,C"`→`"AC"`。

    🔴 关键（实测被探针抓出的过严 P0）：`"D. great"` 这种**字母 + 选项原文**，
    早期实现在整串里扫字母 → 抽出 `"ADEG"`，于是答对的学生被判错。
    所以只认完整匹配的形态，不做"整串扫字母"：
      1. 纯字母串（`"B"` / `"A,C"` / `"ACD"`）→ 抽全部字母；
      2. `"B. 选项原文"` / `"B、选项原文"` → **只取首字母**；
      3. 其余（一整句话/代码）→ 返回空串（不猜）。

    ⚠️ 调用方（`_judge_choice`）要能区分"其实是句子里提到字母"和"空作答"，
    所以这里返回空串时用 `looks_like_option_input` 再判一次。
    """
    s = unicodedata.normalize("NFKC", str(text or "")).strip()
    if not s:
        return ""
    first_line = s.splitlines()[0].strip()
    if _PURE_LETTERS.match(first_line):
        return "".join(sorted({ch for ch in first_line.upper() if ch in _LETTER_SET}))
    m = _LETTER_PREFIX.match(first_line)
    if m:
        return "".join(sorted({ch for ch in m.group(1).upper() if ch in _LETTER_SET}))
    return ""


def looks_like_option_input(text: str) -> bool:
    """作答是不是"想选字母"（含乱写）：`""`/空白 → False；`"B"`/`"A,C"`/`"我看 A 和 B"` → True。

    用来区分"空白作答"（不判对错，交 AI）与"写了但不是有效选项"（判错）。
    """
    if not str(text or "").strip():
        return False
    for ch in str(text).upper():
        if ch in _LETTER_SET:
            return True
    return False


def parse_embedded_options(stem: str) -> dict[str, str]:
    """从**题干**里解析内嵌选项 `A. xxx / B. yyy`（题库 options 列几乎全空，见下）。

    背景：`questions.options` 实测**全库 0 条有值**，选项其实写在 stem 里。所以：
      - 客观题的答案可能只是 `"B"`（要能对上题干的 B 选项）；
      - 也可能被采集成了 `"B. has worked"`（选项原文），需要能认出来。
    返回 `{字母: 选项原文}`；解析不出 2 个以上选项就返回空 dict（不硬猜）。
    """
    text = unicodedata.normalize("NFKC", str(stem or ""))
    if not text:
        return {}
    out: dict[str, str] = {}
    for letter, body in _EMBEDDED_OPT.findall(text):
        key = letter.upper()
        body = re.sub(r"\s+", " ", body).strip()
        if key not in out and body:
            out[key] = body
    return out if len(out) >= 2 else {}


# 选项原文里出现这些词，说明题干是"下列哪项**不**正确"这类题，选项正文混进了题面 → 不可信
_UNSAFE_OPTION_WORDS = ("正确", "错误", "不正确", "不是", "不包括", "不属于", "不依赖", "不需要",
                        "不合适", "不能", "无法", "not ", "true", "false", "选出", "选择")


def options_from_stem(stem: str, *, max_body: int = 60) -> dict[str, str]:
    """**可信**的题干内嵌选项（给前端渲染成可点选项用）。

    比 `parse_embedded_options` 多两道闸门：
      1. 每个选项原文长度 1–`max_body`（长正文说明正则把题面吞进来了）；
      2. 选项原文里不得出现"正确/错误/不是/not/true/false"等题面词
         （例如 `"A. 软件仅指…不包括文档"` 出现在题面 `"下列描述正确的是"` 之后时，
         `parse_embedded_options` 会把整段解析成 A 的原文 → 这种一律丢弃）。
    返回空 dict = 题干里没有可信选项，前端继续按填空题渲染。
    """
    opts = parse_embedded_options(stem)
    chars = {ch for ch in "ABCDEFGHIJKLMNOP"}
    if set(opts) - chars or len(opts) < 2:
        return {}
    for body in opts.values():
        if not (1 <= len(body) <= max_body):
            return {}
        low = body.lower()
        if any(word in low for word in _UNSAFE_OPTION_WORDS):
            return {}
    return opts


def answer_option_letters(answer, stem: str | None = None) -> str:
    """参考答案 → 选项字母集合（**只在答案确实"像选项答案"时才给**，否则返回空串）。

    判据（实测自 7,794 题）：
      1. 纯字母答案（`"B"` / `"A | C"` 拆开后 / `"ACD"`）→ 直接抽字母；
      2. `"B. has worked"` 这类"字母 + 选项原文"→ 取那个字母；
      3. 题干里能解析出选项时，若答案（或其规范化形式）**等于某个选项原文** → 取该选项字母；
      4. 其余（整段 C 代码、论述文字）→ 返回空串，交给 AI。
    """
    alts = alternatives(answer)
    if not alts:
        return ""
    opts = parse_embedded_options(stem) if stem else {}

    # ①② 纯字母（`"B"` / `"ABD"`）、"字母 + 选项原文"（`"B. has worked"`）→ 直接得答案
    pure: set[str] = set()
    all_pure = True
    for alt in alts:
        text = unicodedata.normalize("NFKC", alt).strip()
        if not text or "\n" in text or "```" in text:
            all_pure = False
            break
        if _PURE_LETTERS.match(text):
            pure |= {ch for ch in text.upper() if ch in _LETTER_SET}
            continue
        m = _LETTER_PREFIX.match(text)
        if m:
            pure |= {ch for ch in m.group(1).upper() if ch in _LETTER_SET}
            continue
        all_pure = False
        break
    if all_pure and pure:
        # 长字母串（>MAX_OPTION_LETTERS）不是"选项答案"，而是被采集进 answer 的噪声文字
        # （实测 english/reading_qa/outline_fill 有整句话被当成选项字母的情况）
        return "".join(sorted(pure)) if len(pure) <= MAX_OPTION_LETTERS else ""

    # ③ 答案文本恰好等于题干里的某个选项原文 → 取该选项字母
    #    实测 english/dialogue `"E. out on business today."`、reading_fill `"C.短语辨析A)…"`
    #    ⚠️ 必须**唯一命中**才算（选项原文可能互为子串，多个命中说明题干解析不可靠）
    if opts:
        hits: set[str] = set()
        for alt in alts:
            target = normalize_text(alt)
            if not target:
                continue
            for letter, body in opts.items():
                if normalize_text(body) == target:
                    hits.add(letter)
        if len(hits) == 1:
            return hits.pop()
    return ""


def letter_keys(answer, stem: str | None = None) -> str:
    """兼容旧名：`answer_option_letters` 的别名（多个调用点/测试用旧名）。"""
    return answer_option_letters(answer, stem)


def blank_marker_count(stem: str | None) -> int:
    """题干里"空"的个数：模板标记 `{{__BLANK_1__}}` 优先，其次下划线 `___`。"""
    text = str(stem or "")
    marks = _BLANK_MARKER.findall(text)
    if marks:
        return len(marks)
    return len(re.findall(r"_{3,}", text))


def is_multi_blank(answer, stem: str | None = None) -> bool:
    """答案是不是"一道题多个空"。

    这类题**一道题的答案字段里塞了同一份材料的多个空的答案**，用户界面上却是逐空作答 →
    规则判分无法对齐，必须交给 AI / 人工。实测两种形态：
      - `c_wuhan/single_choice`：题干有三个空，答案 `"A | C | D"`；
      - `english/reading_fill`：整篇完形的答案挤在一行 `"a | b | c | …"`。

    判据（**保守**：拿不准时宁可"可判"再靠其余闸门兜底）：
      1. 题干里 2 个以上空标记 → 一定是多空（除非答案只有 1 项）；
      2. 题干里没有任何空标记、也没有空标记可用 → 退回前缀启发式
         （同义备选常互相是前缀：`"8 years old" | "8"`；完全不同 → 多空）。
    """
    alts = alternatives(answer)
    if len(alts) < 2:
        return False
    # 形态③：多个"单字母备选"（`"A | C | D"`）= 一道题多个空的答案。
    # （真正的多选题答案是 `"ABD"` 这种写在一个备选里的字符串，不会被拆开）
    if all(_PURE_LETTERS.match(a.strip()) and len(a.strip().rstrip(".,、，;；")) == 1 for a in alts):
        return True
    markers = blank_marker_count(stem)
    if markers >= 2:
        return True
    text = str(stem or "").strip()
    if not text:
        keys = [normalize_compact(a) for a in alts]
        keys = [k for k in keys if k]
        if len(keys) < 2:
            return False
        shortest, longest = min(keys, key=len), max(keys, key=len)
        return not (longest.startswith(shortest) or shortest.startswith(longest))
    return False


def _strip_option_prefix(normalized: str) -> str:
    """规范化文本开头的选项字母前缀（`"a. because people..."` → `"because people..."`）。

    ⚠️ 前缀字母可以多于一个（`"abd. ..."` 是多选题答案 + 说明）；必须**要求分隔符**
    （`.`/`、`/`)`），否则会把普通的英文单词首字母也剥掉（`"because"` → `"ecause"`）。
    """
    return re.sub(r"^[a-p]{1,4}\s*[.,、)．]\s*", "", str(normalized or "")).strip()


def normalize_bool(text: str) -> bool | None:
    """是非题答案 → True/False/None。"""
    s = normalize_text(text)
    if s in _BOOL_TRUE:
        return True
    if s in _BOOL_FALSE:
        return False
    return None


# --------------------------------------------------------------------------- 判分


def _ok(full: float, reason: str) -> Verdict:
    return Verdict(True, True, full, full, reason)


def _bad(full: float, reason: str) -> Verdict:
    return Verdict(True, False, 0.0, full, reason)


def _defer(reason: str) -> Verdict:
    return Verdict(False, reason=reason)


def _judge_choice(subject: str, qtype: str, answer, user_answer: str, full: float,
                  stem: str | None = None) -> Verdict:
    if is_multi_blank(answer, stem):
        return _defer("答案含多个空的答案（一道题多空）→ 交给 AI")
    std = answer_option_letters(answer, stem)
    if not std:
        return _defer("参考答案里没有可用的选项字母 → 交给 AI")
    mine = extract_letters(user_answer)
    if not mine:
        # 用户可能输入了选项原文而不是字母（题干里内嵌了选项时才能这样救）
        mine = answer_option_letters(user_answer, stem) if user_answer.strip() else ""
    if not mine:
        # 空的作答**不判"错"**：让上层走 AI/人工，避免"没作答也算已判分"污染统计；
        # 但"写了却不是有效选项"（例如一句话里提到字母）→ 判错。
        if not looks_like_option_input(user_answer):
            return _defer("未作答（空作答不判定对错）→ 交给 AI/人工")
        return _bad(full, f"作答不是有效选项：{str(user_answer).strip()[:40]!r}")
    return _ok(full, f"选项匹配：{mine} == {std}") if mine == std else _bad(full, f"选项不符：{mine} ≠ {std}")


def _judge_bool(answer, user_answer: str, full: float, stem: str | None = None) -> Verdict:
    if is_multi_blank(answer, stem):
        return _defer("答案含多个空 → 交给 AI")
    std = normalize_bool(answer)
    if std is None:
        return _defer("参考答案不是可识别的是非值 → 交给 AI")
    mine = normalize_bool(user_answer)
    if mine is None:
        # 空作答不判错（同 `_judge_choice`），交给 AI/人工
        return _defer("未作答或无法识别为是非值 → 交给 AI/人工")
    return _ok(full, "是非题判定一致") if mine == std else _bad(full, "是非题判定不一致")


def _judge_text(answer, user_answer: str, full: float, *, compact: bool = False,
                stem: str | None = None) -> Verdict:
    """填空/短答：规范化后与任一备选完全相等才算对（宁放不误）。

    额外容忍"选项前缀"：题目采集时会把答案写成 `"A. Because ..."`，
    用户作答/标准答案都可能带或不带这个前缀 → 比对时**两边都剥掉**再比。
    """
    if is_multi_blank(answer, stem):
        return _defer("答案含多个空的答案（一道题多空）→ 交给 AI")
    text_alts, compact_alts, token_alts = _answer_variants(answer)
    std_alts = compact_alts if compact else text_alts
    if not std_alts:
        return _defer("参考答案为空或只有标签 → 交给 AI")
    limit = MAX_SHORT_ANSWER_LEN if compact else MAX_TEXT_LEN
    if max(len(a) for a in std_alts) > limit:
        return _defer(f"参考答案过长（>{limit} 字，疑似论述题）→ 交给 AI")
    mine = normalize_compact(user_answer) if compact else normalize_text(user_answer)
    if not mine:
        # 空作答不判错（让上层决定是 AI 复核还是人工）——与"未判分"语义保持一致
        return _defer("未作答（空作答不判定对错）→ 交给 AI/人工")
    if len(mine) > limit:
        return _defer(f"作答过长（>{limit} 字，疑似自由作答）→ 交给 AI")
    stripped = _strip_option_prefix(mine)
    if compact:
        # 紧凑比对：连标点一起抹平（`1, 2` ≈ `1 2`）；参考答案用**预先算好的抹标点形**
        # （由原始备选直接算，所以 `"a. because …"` 的选项前缀能被正确剥掉）。
        candidates = {t for t in (mine, stripped) if t}
        for text in (mine, stripped):
            tok = normalize_tokens(text)
            if len(tok) >= 3:
                candidates.add(tok)
        std_set = set(std_alts) | set(token_alts)
        for text in (mine, stripped):
            std_set.add(_strip_option_prefix(text))
        for raw in alternatives(answer):
            std_set.add(_strip_option_prefix(normalize_compact(raw)))
    else:
        candidates = {mine}
        if stripped:
            candidates.add(stripped)
        std_set = set(std_alts)
        for alt in std_alts:
            std_set.add(_strip_option_prefix(alt))
    if candidates & std_set:
        return _ok(full, "与参考答案一致（已忽略大小写/空白/标点）")
    # 空格无关：`"a = 10"` ≈ `"a=10"`（但**要求参考答案本身不含空格**，
    # 否则 `"int main"` 这类代码会被抹成 `"intmain"` 而产生假匹配）
    for alt in std_alts:
        if " " in alt:
            continue
        if alt.replace(" ", "") in {c.replace(" ", "") for c in candidates}:
            return _ok(full, "与参考答案一致（已忽略空格/标点差异）")
    return _bad(full, "与参考答案不一致")


def _judge_sentence_build(answer, user_answer: str, full: float, stem: str | None = None) -> Verdict:
    """连词成句：标点/大小写/空白无关；整句抹平后仍不同 → 错（词序错就是错）。

    不额外判 AI：这类题题干里给全了单词，答案句子唯一，规则判分足够。
    """
    if is_multi_blank(answer, stem):
        return _defer("答案含多个空 → 交给 AI")
    _text_alts, compact_alts, _token_alts = _answer_variants(answer)
    if not compact_alts:
        return _defer("参考答案为空 → 交给 AI")
    if max(len(a) for a in compact_alts) > 200:
        return _defer("参考答案过长（不是连词成句题）→ 交给 AI")
    mine = normalize_compact(user_answer)
    if not mine:
        return _defer("未作答（空作答不判定对错）→ 交给 AI/人工")
    if mine in compact_alts:
        return _ok(full, "与参考答案一致（已忽略标点/大小写/空白）")
    return _bad(full, "词序或拼写与参考答案不一致")


def judge_local(subject: str, question_type: str | None, answer, user_answer,
                *, taxonomy: dict | None = None, stem: str | None = None) -> Verdict:
    """规则判分唯一入口。

    返回 `Verdict`；`gradeable=False` 表示「本地判不了，请走 AI/人工」。

    分派顺序（先按题型，题型拿不准时**逐级回退**，但每次回退都要求答案形态吻合，
    避免"为了多判而乱判"）：
      主观写作/翻译 → 选择题 → 是非题 → 连词成句 → 填空 → 短答 → 题干/答案形态回退。
    """
    qtype = str(question_type or "").strip().lower()
    if subject not in SUBJECTS:
        return _defer(f"未知科目: {subject!r}")
    ua_raw = "" if user_answer is None else str(user_answer)
    full = full_score_for(subject, qtype, taxonomy)
    reason = ""

    if qtype in AI_ONLY_TYPES:
        reason = f"题型 {qtype} 属于主观题（写作/翻译）→ 交给 AI"
    elif qtype in CHOICE_TYPES:
        return _judge_choice(subject, qtype, answer, ua_raw, full, stem)
    elif qtype in BOOL_TYPES:
        verdict = _judge_bool(answer, ua_raw, full, stem)
        if verdict.gradeable:
            return verdict
        reason = verdict.reason
    elif qtype in SENTENCE_BUILD_TYPES:
        return _judge_sentence_build(answer, ua_raw, full, stem)
    elif qtype in BLANK_TYPES:
        verdict = _judge_text(answer, ua_raw, full, stem=stem)
        if verdict.gradeable:
            return verdict
        reason = verdict.reason
    elif qtype in SHORT_ANSWER_TYPES:
        verdict = _judge_text(answer, ua_raw, full, compact=True, stem=stem)
        if verdict.gradeable:
            return verdict
        reason = verdict.reason
    elif qtype in PROGRAM_OUTPUT_TYPES:
        # C 语言"看程序写结果"：短答案（`5050` / `2 1`）可精确比对；
        # 整段代码（要求"编写函数"）超长 → 由长度闸门挡下交给 AI。
        verdict = _judge_text(answer, ua_raw, full, compact=True, stem=stem)
        if verdict.gradeable:
            return verdict
        reason = verdict.reason
    else:
        reason = f"题型 {qtype or '(未标)'} 未登记为规则判分题型"

    # ---- 回退：按"答案自身形态"再试（只在能唯一判定时才用） ----
    if reason and qtype not in AI_ONLY_TYPES:
        if answer_option_letters(answer, stem):
            verdict = _judge_choice(subject, qtype, answer, ua_raw, full, stem)
            if verdict.gradeable:
                return verdict
        bool_std = normalize_bool(answer)
        if bool_std is not None and normalize_bool(ua_raw) is not None:
            verdict = _judge_bool(answer, ua_raw, full, stem)
            if verdict.gradeable:
                return verdict
        verdict = _judge_text(answer, ua_raw, full, compact=True, stem=stem)
        if verdict.gradeable:
            return verdict
    return _defer(f"{reason or '规则判分未能判定'} → 交给 AI")


# --------------------------------------------------------------------------- 覆盖率体检


def coverage(*, data_dir: Path | None = None, limit_reports: int = 12) -> dict:
    """**只读**扫描各科目库，统计「规则判分能覆盖多少题、规则过严的有多少」。

    探针语义（关键）：把题库**自带的每一个备选答案**分别当作"用户作答"喂给规则判分。
    任何一个备选被判 `gradeable 且 错误` = **规则过严**（上线会把答对的判成错），
    记为 `strict` 并在 samples 里给出证据。这样探针是语义正确的，不会像
    「整串答案（含 `|`）当作答」那样制造假警报。

    返回 `{科目: {题型: {total, gradeable, strict, samples:[...]}}}`。
    """
    base = Path(data_dir) if data_dir else DATA
    stats: dict[str, dict] = {}
    for subj in SUBJECTS:
        path = base / f"{subj}.sqlite"
        if not path.exists():
            continue
        conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            per_type: dict[str, dict] = {}
            for qtype, answer, stem in conn.execute("SELECT question_type, answer, stem FROM questions"):
                qtype = qtype or "(未标)"
                item = per_type.setdefault(qtype, {"total": 0, "gradeable": 0, "strict": 0, "samples": []})
                item["total"] += 1
                variants = alternatives(answer) or [str(answer or "")]
                verdicts = [judge_local(subj, qtype, answer, v, stem=stem) for v in variants]
                usable = [v for v in verdicts if v.gradeable]
                if usable:
                    item["gradeable"] += 1
                wrong_hits = [(v, d) for v, d in zip(variants, verdicts) if d.gradeable and not d.correct]
                if wrong_hits:
                    item["strict"] += 1
                    if len(item["samples"]) < limit_reports:
                        item["samples"].append({
                            "answer": str(answer)[:80],
                            "probe": str(wrong_hits[0][0])[:40],
                            "reason": wrong_hits[0][1].reason,
                        })
            stats[subj] = per_type
        finally:
            conn.close()
    return stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="规则判分（本地、离线、零成本）")
    ap.add_argument("--coverage", action="store_true", help="只读扫描题库，统计规则判分覆盖率")
    ap.add_argument("--data-dir", default=None)
    ap.add_argument("--json", action="store_true", help="输出 JSON（默认人类可读表格）")
    args = ap.parse_args(argv)

    if not args.coverage:
        ap.print_help()
        return 0

    stats = coverage(data_dir=Path(args.data_dir) if args.data_dir else None)
    if args.json:
        print(json.dumps(stats, ensure_ascii=False, indent=2))
        return 0
    grand = {"total": 0, "gradeable": 0, "strict": 0}
    for subj, per_type in stats.items():
        total = sum(i["total"] for i in per_type.values())
        gradeable = sum(i["gradeable"] for i in per_type.values())
        strict = sum(i["strict"] for i in per_type.values())
        grand["total"] += total
        grand["gradeable"] += gradeable
        grand["strict"] += strict
        pct = (gradeable / total * 100) if total else 0.0
        print(f"===== {subj}  总 {total} 题｜规则可判 {gradeable}（{pct:.1f}%）｜规则过严 {strict}")
        print(f"  {'题型':<22}{'总题':>7}{'规则可判':>10}{'过严':>7}  证据")
        for qtype, item in sorted(per_type.items(), key=lambda kv: -kv[1]["total"]):
            note = ""
            if item["samples"]:
                note = "答对却判错: " + item["samples"][0]["reason"][:34]
            print(f"  {qtype:<22}{item['total']:>7}{item['gradeable']:>10}{item['strict']:>7}  {note}")
    pct = (grand["gradeable"] / grand["total"] * 100) if grand["total"] else 0.0
    print(f"===== 合计  总 {grand['total']} 题｜规则可判 {grand['gradeable']}（{pct:.1f}%）"
          f"｜规则过严 {grand['strict']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
