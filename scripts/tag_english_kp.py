#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""英语题库 · 逐题知识点打标（E-T* 题型维度 + E-G*/E-S* 语言知识维度）。

背景
----
`data/english.sqlite` 的 `questions` 表共 1473 题，其中 1464 题 `knowledge_point` 为空
（仅 9 题为上一轮遗留的自由文本，如「细节理解」，不符合知识点体系写法）。
知识点体系唯一权威来源：`subjects/english/knowledge_base.json`
  17 个题型维度 E-T01..E-T17 + 31 个语言知识维度 E-G01..E-G17 / E-S01..E-S14。

打标口径
--------
`knowledge_point` = 「主知识点 ID + 名称」，跨点用 ` | ` 连接、最多 2 个：
    第 1 位 = **题型维度**（必填，由 `question_type` 决定，reading_qa/writing 需细分）
    第 2 位 = **语言知识维度**（能判定才写；判不出就只留题型维度，宁缺勿造）
`syllabus_ref` = `subjects/english/knowledge_base.json#<题型点 ID>`（指向体系来源）。

方法与成本
----------
1. **规则优先**（零成本，覆盖绝大多数）：
   - `FORMAT_BY_TYPE`：题型 → 题型维度（reading_qa 按答案形态分 E-T04/E-T16；writing 按卷别/体裁分 E-T06/E-T17）
   - `SC_TAGS` / `GF_TAGS`：沿用 `tests/build_english_kb.py` 的逐题人工标注表（官方单选 103 题、
     官方语法填空 31 题），保证与知识库统计口径完全一致
   - `tag_rq()`：沿用 `build_english_kb.py` 的阅读技能判定函数（官方 240 题口径一致）
   - 关键词规则：完形 E-S13/E-S14、选词填空 E-G06/E-G16/E-G10、写作体裁、语法填空非官方句的虚拟/倒装
2. **LLM 兜底**（仅规则判不出的）：`deepseek-flash`、`reasoning_effort='low'`、每批 20 题、
   严格 JSON 输出，结果按题型白名单校验，越界即丢弃（记入未打标）。
3. 🔴 **成本闸门**：`--cap-cny`（默认 2.0）。预估超限直接拒绝执行；运行中累计超限立即停止。
   每次调用 append 到 `logs/cost_ledger.jsonl`（`stage='en_tagging'`）。余额 < ¥6 立即停止。

用法
----
    python scripts/tag_english_kp.py --dry-run                 # 只报告规则覆盖/LLM 题量/预估花费
    python scripts/tag_english_kp.py --apply --cap-cny 2.0     # 写库（先用 backup.py 做快照）
    python scripts/tag_english_kp.py --apply --no-llm          # 只用规则，不留 LLM 残差
    python scripts/tag_english_kp.py --sample 5                # 随机抽 5 题打印打标结果与依据
    python scripts/tag_english_kp.py --report                  # 只按当前库内容重生成简报

幂等：默认只处理「knowledge_point 为空 / 不是 E-* 体系写法」的行；重复执行不产生变更。
      `--force` 才会重刷全部行（规则结果确定，重跑结果一致）。

只写 `knowledge_point` 与 `syllabus_ref` 两列，**不改 status、不改任何其他字段**。
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import random
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "english.sqlite"
KB_FILE = ROOT / "subjects" / "english" / "knowledge_base.json"
ENV_FILE = ROOT / ".env"
LEDGER = ROOT / "logs" / "cost_ledger.jsonl"
REPORT = ROOT / "logs" / "english_tagging_report.md"
TMP = ROOT / "tests" / ".tmp" / "en_tagging"

STAGE = "en_tagging"
FLASH_MODEL = "deepseek-flash"
# 与 scripts/judge_calibration.py 保持同一张价目表（元 / 1M tokens），保证账本可比
PRICE = {
    "deepseek-flash": {"in": 1.0, "out": 4.0, "cache": 0.02},
    "deepseek-v4-pro": {"in": 4.5, "out": 13.5, "cache": 0.15},
}
BALANCE_STOP_CNY = 6.0
SYLLABUS_REF = "subjects/english/knowledge_base.json"

# --------------------------------------------------------------------------- 规则表

# 题型 → 题型维度（KB `question_type_to_points` 中的 format 点）
FORMAT_BY_TYPE = {
    "grammar_fill": "E-T01",
    "sentence_build": "E-T02",
    "reading_fill": "E-T03",
    "translation_fill": "E-T05",
    "sentence_completion": "E-T07",
    "single_choice": "E-T08",
    "translation_choice": "E-T09",
    "translation": "E-T10",
    "outline_fill": "E-T11",
    "phonetics": "E-T12",
    "dialogue": "E-T13",
    "cloze": "E-T14",
    "word_fill": "E-T15",
    "program_fill": "E-T16",   # KB data_quality_notes 明确把这 2 题归入 E-T16
}
# reading_qa / writing 需要细分，见 rule_tag()

# LLM 允许输出的语言点白名单（题型白名单 ∪ 该题型实际可能考到的点）
LANG_CANDIDATES = {
    "grammar_fill": [f"E-G{i:02d}" for i in range(1, 18)],
    "sentence_build": [f"E-G{i:02d}" for i in range(1, 18)],
    "single_choice": [f"E-G{i:02d}" for i in range(1, 18)],
    "reading_qa": ["E-S02", "E-S03", "E-S04", "E-S05", "E-S06", "E-S07", "E-S08"],
    "reading_fill": ["E-S07", "E-S09"],
    "translation_fill": ["E-S09", "E-G07"],
    "writing": ["E-S10", "E-S11"],
    "translation_choice": ["E-S08"],
    "translation": ["E-S08"],
    "sentence_completion": ["E-S09"],
    "outline_fill": ["E-S07"],
    "phonetics": ["E-S01"],
    "dialogue": ["E-S12"],
    "cloze": ["E-S13", "E-S14"],
    "word_fill": ["E-G06", "E-G10", "E-G16", "E-G17"],
    "program_fill": ["E-S07"],
}

# ---- 沿用 tests/build_english_kb.py 的逐题标注表（官方单选 103 题） ----
SC_TAGS = [
    ('湖北2020', 'D. made', 'E-G16'), ('湖北2020', 'B. take', 'E-G16'), ('湖北2020', 'A. qualified', 'E-G06'),
    ('湖北2020', 'B. which', 'E-G05'), ('湖北2020', 'C. writing', 'E-G04'), ('湖北2020', 'D. in which', 'E-G05'),
    ('湖北2020', 'D. has made', 'E-G01'), ('湖北2020', 'C. had known', 'E-G03'), ('湖北2020', 'B. run', 'E-G16'),
    ('湖北2020', 'A. offers', 'E-G17'), ('湖北2020', 'C. allowed', 'E-G02'), ('湖北2020', 'D. played', 'E-G16'),
    ('湖北2020', 'B. efficient', 'E-G06'), ('湖北2020', 'C. affect', 'E-G17'), ('湖北2020', 'A. put off', 'E-G16'),
    ('湖北2020', 'D. to', 'E-G10'), ('湖北2020', 'A. since', 'E-G11'), ('湖北2020', 'D. using', 'E-G04'),
    ('湖北2020', 'A. account for', 'E-G16'), ('湖北2020', 'C. put', 'E-G04'), ('湖北2020', 'B. working', 'E-G04'),
    ('湖北2020', 'D. when', 'E-G11'), ('湖北2020', 'A. that', 'E-G05'), ('湖北2020', 'B. will have completed', 'E-G01'),
    ('湖北2020', 'C. on', 'E-G10'),
    ('湖北2021', 'A. a', 'E-G09'), ('湖北2021', 'B. began', 'E-G01'), ('湖北2021', 'A. will be improved', 'E-G02'),
    ('湖北2021', 'C. how I can improve my listening', 'E-G05'), ('湖北2021', 'D. fifth', 'E-G14'),
    ('湖北2021', 'B. is watering', 'E-G01'), ('湖北2021', 'C. would have died', 'E-G03'), ('湖北2021', 'B. Although', 'E-G11'),
    ('湖北2021', 'D. To work out', 'E-G04'), ('湖北2021', 'C. your calling', 'E-G04'), ('湖北2021', 'B. had studied', 'E-G03'),
    ('湖北2021', 'C. by', 'E-G10'), ('湖北2021', 'B. are', 'E-G08'), ('湖北2021', 'A. that#2', 'E-G05'),
    ('湖北2021', "B. wasn't it", 'E-G15'), ('湖北2021', 'D. any other', 'E-G07'), ('湖北2021', 'B. treat', 'E-G16'),
    ('湖北2021', 'A. matters', 'E-G17'), ('湖北2021', 'D. promise', 'E-G17'), ('湖北2021', 'C. impressed', 'E-G17'),
    ('湖北2021', 'B. usual', 'E-G07'), ('湖北2021', 'D. in short', 'E-G16'), ('湖北2021', 'C. librarian', 'E-G06'),
    ('湖北2021', 'D. went out', 'E-G16'), ('湖北2021', 'A. steadily', 'E-G06'),
    ('湖北2022', "A. won't", 'E-G01'), ('湖北2022', 'A. was shopping', 'E-G01'), ('湖北2022', 'B. were taken', 'E-G02'),
    ('湖北2022', 'C. to wait', 'E-G04'), ('湖北2022', 'A. would', 'E-G03'), ('湖北2022', 'B. the', 'E-G09'),
    ('湖北2022', 'C. is', 'E-G08'), ('湖北2022', "A. Could; can't", 'E-G13'), ('湖北2022', 'D. Although', 'E-G11'),
    ('湖北2022', 'D. than', 'E-G07'), ('湖北2022', 'C. as well as', 'E-G08'), ('湖北2022', 'A. how I can improve my English', 'E-G05'),
    ('湖北2022', 'C. yourself', 'E-G12'), ('湖北2022', 'D. to#2', 'E-G10'), ('湖北2022', 'A. act three', 'E-G14'),
    ('湖北2022', 'B. forget', 'E-G17'), ('湖北2022', 'B. tell', 'E-G17'), ('湖北2022', 'A. made', 'E-G16'),
    ('湖北2022', 'C. showing off', 'E-G16'), ('湖北2022', 'D. looking for', 'E-G16'), ('湖北2022', 'C. touch', 'E-G16'),
    ('湖北2022', 'D. free', 'E-G16'), ('湖北2022', 'C. spare', 'E-G17'), ('湖北2022', 'D. rather', 'E-G07'),
    ('湖北2022', 'D. whatever', 'E-G05'),
    ('湖北2023', 'C. mine', 'E-G12'), ('湖北2023', 'C. the', 'E-G09'), ('湖北2023', 'B. is', 'E-G08'),
    ('湖北2023', 'C. One third', 'E-G14'), ('湖北2023', 'A. about', 'E-G10'), ('湖北2023', 'A. is reading', 'E-G01'),
    ('湖北2023', 'D. to give', 'E-G04'), ('湖北2023', 'B. saying', 'E-G04'), ('湖北2023', 'A. who', 'E-G05'),
    ('湖北2023', 'B. higher', 'E-G07'), ('湖北2023', 'D. was praised', 'E-G02'), ('湖北2023', 'B. has worked', 'E-G01'),
    ('湖北2023', 'A. can', 'E-G13'), ('湖北2023', 'C. that', 'E-G15'), ('湖北2023', 'B. can she draw', 'E-G15'),
    ('湖北2023', 'C. Even though', 'E-G11'), ('湖北2023', 'C. problem', 'E-G17'), ('湖北2023', 'B. faithful', 'E-G06'),
    ('湖北2023', 'A. tell', 'E-G17'), ('湖北2023', 'B. invited', 'E-G17'), ('湖北2023', 'A. agreed', 'E-G17'),
    ('湖北2023', 'D. fill', 'E-G16'), ('湖北2023', 'C. look after', 'E-G16'), ('湖北2023', 'C. going on', 'E-G16'),
    ('河北专升本英语18', 'B#1', 'E-G15'), ('河北专升本英语18', 'B#2', 'E-G05'),
    ('河北专升本英语18', 'A', 'E-G16'), ('河北专升本英语18', 'A#2', 'E-G08'),
]

# ---- 沿用 tests/build_english_kb.py 的逐题标注表（官方语法填空 31 题） ----
GF_TAGS = [
    ('湖北2025', 'biggest', 'E-G07'), ('湖北2025', 'for', 'E-G10'), ('湖北2025', 'started', 'E-G01'),
    ('湖北2025', 'and', 'E-G11'), ('湖北2025', 'beautiful', 'E-G06'), ('湖北2025', 'designs', 'E-G06'),
    ('湖北2025', 'finished', 'E-G01'), ('湖北2025', 'walking', 'E-G04'), ('湖北2025', 'a', 'E-G09'),
    ('湖北2025', 'happiness', 'E-G06'),
    ('湖北2024', 'in', 'E-G10'), ('湖北2024', 'How', 'E-G12'), ('湖北2024', 'is', 'E-G01'), ('湖北2024', 'many', 'E-G13'),
    ('湖北2024', 'the', 'E-G09'), ('湖北2024', 'yourself', 'E-G12'), ('湖北2024', 'if', 'E-G11'),
    ('湖北2024', 'greatly', 'E-G06'), ('湖北2024', 'took', 'E-G01'), ('湖北2024', 'will', 'E-G01'),
    ('湖北2026', 'proudly', 'E-G06'), ('湖北2026', 'was seen', 'E-G02'), ('湖北2026', 'a', 'E-G09'),
    ('湖北2026', 'focuses', 'E-G01'), ('湖北2026', 'longer', 'E-G07'), ('湖北2026', 'favoring', 'E-G04'),
    ('湖北2026', 'in', 'E-G10'), ('湖北2026', 'who', 'E-G05'), ('湖北2026', 'and', 'E-G11'), ('湖北2026', 'tourists', 'E-G06'),
]


def norm(x: str) -> str:
    """与 tests/build_english_kb.py 完全一致的规范化（弯引号 → 直引号）。"""
    return (x or "").strip().replace("\u2019", "'").replace("\u2018", "'").replace("\uff07", "'")


# --------------------------------------------------------------------------- 工具

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_env() -> dict:
    out: dict = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def cost_of(model: str, usage: dict) -> float:
    p = PRICE[model]
    pin = usage.get("prompt_tokens", 0) or 0
    pout = usage.get("completion_tokens", 0) or 0
    cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0) or 0
    return ((pin - cached) * p["in"] + cached * p["cache"] + pout * p["out"]) / 1_000_000


def log_ledger(entry: dict) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def balance_cny():
    import requests
    env = load_env()
    key = env.get("DEEPSEEK_API_KEY", "")
    base = env.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
    if not key:
        return None
    try:
        r = requests.get(f"{base}/user/balance", headers={"Authorization": f"Bearer {key}"}, timeout=20)
        info = (r.json().get("balance_infos") or [{}])[0]
        return float(info.get("total_balance", 0) or 0)
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------- 知识体系

def load_kb() -> dict:
    kb = json.loads(KB_FILE.read_text(encoding="utf-8-sig"))
    points = {p["id"]: p for p in kb["knowledge_points"]}
    return {
        "raw": kb,
        "points": points,
        "name": {pid: p["name"] for pid, p in points.items()},
        "format_ids": {pid for pid, p in points.items() if p.get("dimension") == "format"},
        "lang_ids": {pid for pid, p in points.items() if p.get("dimension") == "knowledge"},
        "map": kb.get("question_type_to_points", {}),
    }


def fmt(kb: dict, pid: str) -> str:
    return f"{pid} {kb['name'][pid]}"


# --------------------------------------------------------------------------- 规则引擎

_CN_APP = re.compile(r"写信|一封信|信函|信件|感谢信|邀请信|道歉信|投诉信|申请信|求职信|推荐信|回信|通知|notice|letter|"
                     r"e-?mail|邮件|短信|邀请|invitation|申请|感谢|道歉|投诉|请假|便条|倡议|recommendation")
_CN_ESSAY = re.compile(r"composition|议论文|saying|no less than 100|提纲|my view|my major|entitled|haze|air pollution|围绕|作文|不少于|观点")
# 错档题：question_type=writing 但内容其实是四选一词汇/语法题（DB 来源质量问题）
_MCQ_LIKE = re.compile(r"[A-D][)）.、]\s*\S")
# 正误判断型阅读题（知识库 E-S04 定义包含此类）
_TRUE_TYPE = re.compile(r"which of the following.*(true|not true|correct|incorrect|right|wrong)", re.I)
# 整段答案都是中文（含中文标点）——说明该题实际是英译汉
_CJK_ONLY = re.compile(r"[\u4e00-\u9fff，。、；：？！“”‘’（）《》\s]+")


def rule_tag(row: dict, kb: dict, scmap: dict, gfmap: dict) -> dict:
    """返回 {'fmt':id|None, 'lang':id|None, 'source':str, 'why':str}。source ∈ rule:* / none。"""
    qt = row["question_type"] or ""
    stem = row["stem"] or ""
    ans = row["answer"] or ""
    expl = row["explanation"] or ""
    exam = row["exam_title"] or ""
    res = {"fmt": None, "lang": None, "source": "none", "why": ""}

    # ---------- 1) 题型维度（必填） ----------
    if qt == "reading_qa":
        # 沿用 KB 口径：答案是裸选项字母（河北 42 题）→ E-T16 阅读理解（选择题），其余 → E-T04
        res["fmt"] = "E-T16" if re.fullmatch(r"[A-Da-d]", ans.strip()) else "E-T04"
    elif qt == "writing":
        if exam.startswith("河北"):
            res["fmt"] = "E-T17"
        elif _MCQ_LIKE.search(stem) and "答案" in ans and len(stem) > 300:
            # 错档题：question_type 标成 writing，实际是四选一词汇/语法题
            res["fmt"] = "E-T08"
            res["misfiled"] = True
        elif _CN_APP.search(stem) or _CN_APP.search(expl):
            res["fmt"] = "E-T06"
        elif _CN_ESSAY.search(stem.lower()) or _CN_ESSAY.search(expl.lower()):
            res["fmt"] = "E-T17"
    else:
        res["fmt"] = FORMAT_BY_TYPE.get(qt)

    # ---------- 2) 语言知识维度 ----------
    lang, why, src = None, "", "none"

    if qt == "single_choice":
        # 逐题人工表（与知识库统计口径一致）；同 (卷别, 答案) 重复出现时由调用方按下标取
        key = (exam, norm(ans))
        lst = scmap.get(key) or []
        lang = lst[0] if lst else None
        if lang:
            src, why = "rule:per_item", "官方单选逐题标注表"

    elif qt == "grammar_fill":
        key = (exam, norm(ans))
        lst = gfmap.get(key) or []
        if lst:
            lang, src, why = lst[0], "rule:per_item", "官方语法填空逐题标注表"
        else:
            s = stem
            if _CJK_ONLY.fullmatch(ans.strip()) and re.search(r"_{6,}", s):
                # 错档题：question_type=grammar_fill，实际是「给英文句子 + 长空，写出中文译文」的英译汉题
                lang, src, why = "E-S08", "rule:keyword", "错档题（实为英译汉）：答案为纯中文译文"
            elif re.search(r"^If\b.{0,80}?(were|had|should)", s, re.I | re.S) \
                    or re.search(r"as if|would rather|if only|but for|wish(ed)?\b|"
                                 r"It is (very )?(important|necessary|essential|impossible) that|"
                                 r"(suggest|demand|require|insist|order|propose)\w* that", s, re.I):
                lang, src, why = "E-G03", "rule:keyword", "虚拟语气（if 虚拟条件句 / 省略 if 的倒装 / as if / would rather / It is+adj+that）"

    elif qt == "reading_qa":
        # 官方 240 题沿用 build_english_kb.py 的 tag_rq()（口径一致）；
        # 非官方题里混入的短文片段（不是提问句）规则判不了，交给 LLM 或留空。
        looks_like_q = ("?" in stem) or bool(re.match(r"\s*(translate|read the|according)", stem, re.I))
        if row.get("trust_level") == "official_exam" or looks_like_q or len(stem.strip()) <= 60:
            if _TRUE_TYPE.search(stem):
                # 知识库 E-S04 的定义与证据都写明「Which of the following is TRUE/NOT true」属推理判断，
                # 但其自带的 tag_rq() 漏了这一类（会落到 E-S02），此处按定义补上。
                lang = "E-S04"
                why = "正误判断型（Which of the following is TRUE/NOT true）→ 知识库 E-S04 定义"
            else:
                lang, why = tag_rq(stem), "阅读题干句式判定（build_english_kb 同款函数）"
            src = "rule:keyword"

    elif qt == "reading_fill":
        lang, src, why = "E-S07", "rule:qtype", "阅读填空·信息提取（原词定位/同义转换）"

    elif qt == "program_fill":
        lang, src, why = "E-S07", "rule:qtype", "短文信息提取填空（KB 归入 E-T16，语言维度按阅读填空处理）"

    elif qt == "outline_fill":
        lang, src, why = "E-S07", "rule:qtype", "提纲填空＝阅读填空·信息提取"

    elif qt == "translation_fill":
        lang, src, why = "E-S09", "rule:qtype", "汉译英填空（中文提示 + 英文挖空）"

    elif qt == "sentence_completion":
        lang, src, why = "E-S09", "rule:qtype", "完成句子＝汉译英填空"

    elif qt == "translation_choice":
        lang, src, why = "E-S08", "rule:qtype", "英译汉选择"

    elif qt == "translation":
        lang, src, why = "E-S08", "rule:qtype", "段落英译汉"

    elif qt == "phonetics":
        lang, src, why = "E-S01", "rule:qtype", "语音辨析（划线部分读音）"

    elif qt == "dialogue":
        lang, src, why = "E-S12", "rule:qtype", "情景对话与交际用语"

    elif qt == "cloze":
        if re.search(r"从句|引导|时态|语态|非谓语|搭配|介词|冠词|固定|短语|词形|单复数|比较级|词性|语法|虚拟|倒装|主谓|代词|连词|形式主语", expl):
            lang, src, why = "E-S14", "rule:keyword", "解析含语法/搭配术语 → 词汇与语法辨析"
        else:
            lang, src, why = "E-S13", "rule:keyword", "解析仅谈语义与上下文 → 语境逻辑"

    elif qt == "word_fill":
        if re.search(r"固定搭配|固定短语|固定结构|短语|搭配", expl):
            lang, src, why = "E-G16", "rule:keyword", "解析点名固定搭配/短语"
        elif re.search(r"介词", expl):
            lang, src, why = "E-G10", "rule:keyword", "解析点名介词"
        else:
            lang, src, why = "E-G06", "rule:qtype", "选词填空按词性匹配/词形变化（KB 映射）"

    elif qt == "writing":
        if res.get("misfiled"):
            if re.search(r"固定搭配|搭配|词汇|辨析|词义", ans):
                lang, src, why = "E-G17", "rule:keyword", "错档题（实为词汇单选）：考词义辨析/搭配"
            elif re.search(r"从句", ans):
                lang, src, why = "E-G05", "rule:keyword", "错档题（实为语法单选）：解析点名从句"
            elif re.search(r"时态|完成时|进行时", ans):
                lang, src, why = "E-G01", "rule:keyword", "错档题（实为语法单选）：解析点名时态"
            else:
                lang, src, why = "E-G17", "rule:keyword", "错档题（实为词汇单选）：默认词汇辨析"
        elif res["fmt"] == "E-T06":
            lang, src, why = "E-S10", "rule:keyword", "应用文（信/通知/邮件/短信）"
        elif res["fmt"] == "E-T17":
            lang, src, why = "E-S11", "rule:keyword", "提纲作文/议论文"

    elif qt == "sentence_build":
        if re.search(r"被动", expl):
            lang, src, why = "E-G02", "rule:keyword", "解析点名被动语态"
        elif re.search(r"不定式|动名词|分词|非谓语", expl):
            lang, src, why = "E-G04", "rule:keyword", "解析点名非谓语"
        elif re.search(r"从句", expl):
            lang, src, why = "E-G05", "rule:keyword", "解析点名从句"
        elif re.search(r"时态|完成时|进行时", expl):
            lang, src, why = "E-G01", "rule:keyword", "解析点名时态"

    if lang is None and src == "none" and res["fmt"] is not None:
        res["source"] = "rule:fmt_only"
    else:
        res["source"] = src
    res["lang"] = lang
    res["why"] = why
    return res


def tag_rq(stem: str) -> str:
    """阅读技能判定：与 tests/build_english_kb.py::tag_rq 逐行一致（官方 240 题口径）。"""
    s = (stem or "").strip()
    sl = s.lower()
    if sl.startswith("translate"):
        return "E-S08"
    if "main idea" in sl or "mainly about" in sl or "best title" in sl or "suitable title" in sl or "mainly" in sl:
        return "E-S03"
    if "underlined" in sl or "probably mean" in sl or "most likely mean" in sl or "closest meaning" in sl or "refers to" in sl:
        return "E-S05"
    if sl.startswith("why") or "in order to" in sl:
        return "E-S06"
    if "we learn" in sl or "suggest" in sl or "author" in sl or "infer" in sl or "attitude" in sl or "trying to" in sl or "conclusion" in sl or "title" in sl:
        return "E-S04"
    return "E-S02"


# --------------------------------------------------------------------------- LLM 兜底

SYS_PROMPT = """你是英语题库的知识点标注器。只能从下面给定的 ID 里选，禁止自创 ID 或名称。
【语法】E-G01 时态 | E-G02 被动语态 | E-G03 虚拟语气 | E-G04 非谓语动词 | E-G05 从句 | E-G06 词性转换与构词 | E-G07 比较级与最高级 | E-G08 主谓一致 | E-G09 冠词与限定词 | E-G10 介词与介词短语 | E-G11 连词与状语从句 | E-G12 代词与感叹结构 | E-G13 情态动词与限定词 | E-G14 数词与序数词 | E-G15 强调句与倒装 | E-G16 固定搭配与短语动词 | E-G17 词汇辨析
【阅读】E-S02 事实细节 | E-S03 主旨大意 | E-S04 推理判断 | E-S05 词义猜测 | E-S06 原因与目的 | E-S07 阅读填空·信息提取 | E-S08 翻译·英译汉 | E-S09 翻译·汉译英（填空）
【其他】E-S01 语音辨析 | E-S10 写作·应用文 | E-S11 写作·提纲议论文 | E-S12 情景对话与交际用语 | E-S13 完形填空·语境逻辑 | E-S14 完形填空·词汇与语法辨析
规则：
1. 每题只给 1 个最贴合的语言知识 ID；看不出来就填空字符串 ""，不要猜。
2. 只输出 JSON，格式 {"r":[{"i":序号,"k":"E-Gxx","w":"不超过12字的依据"}]}，序号与输入一致，一条不漏。"""


def build_user_msg(items: list) -> str:
    lines = []
    for i, it in enumerate(items, 1):
        lines.append(
            f"[{i}] 题型={it['question_type']} | 题干={clip(it['stem'], 180)} | 答案={clip(it['answer'], 60)}"
            f" | 解析={clip(it['explanation'], 120)}"
        )
    return "请给下列题目打语言知识标签：\n" + "\n".join(lines)


def clip(s: str, n: int) -> str:
    s = re.sub(r"\s+", " ", (s or "").strip())
    return s if len(s) <= n else s[:n] + "…"


def llm_tag_batch(client, items: list, allowed: list):
    """返回 (list[str|None], usage)。异常向上抛，由调用方处理。"""
    resp = client.chat.completions.create(
        model=FLASH_MODEL,
        messages=[{"role": "system", "content": SYS_PROMPT}, {"role": "user", "content": build_user_msg(items)}],
        reasoning_effort="low",
        response_format={"type": "json_object"},
        temperature=0,
        timeout=180,
    )
    usage = resp.usage.model_dump() if getattr(resp, "usage", None) else {}
    txt = resp.choices[0].message.content or "{}"
    try:
        data = json.loads(txt)
    except Exception:  # noqa: BLE001
        m = re.search(r"\{.*\}", txt, re.S)
        data = json.loads(m.group(0)) if m else {}
    out = [None] * len(items)
    for row in (data.get("r") or []):
        try:
            i = int(row.get("i")) - 1
        except Exception:  # noqa: BLE001
            continue
        k = str(row.get("k") or "").strip()
        if 0 <= i < len(items) and k in allowed:
            out[i] = k
    return out, usage


# --------------------------------------------------------------------------- DB

def connect() -> sqlite3.Connection:
    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    return con


def build_scmap() -> dict:
    m = collections.defaultdict(list)
    for t, a, k in SC_TAGS:
        m[(t, norm(a.split("#")[0]))].append(k)
    return m


def build_gfmap() -> dict:
    m = collections.defaultdict(list)
    for t, a, k in GF_TAGS:
        m[(t, norm(a))].append(k)
    return m


def rule_pass(rows: list, kb: dict, scmap: dict, gfmap: dict) -> dict:
    """对一批题跑完整规则引擎，返回 uid -> {fmt, lang, source, why}。

    单选/语法填空的逐题标注表按 (卷别, 答案) 去重后按下标取（与
    tests/build_english_kb.py 的 `ORDER BY exam_title, id` + seen 计数等价：
    同一 (卷别,答案) 的行在两个脚本里都按 id 升序出现）。
    """
    out: dict = {}
    sc_idx = collections.Counter()
    for r in rows:
        qt = r["question_type"]
        res = rule_tag(r, kb, scmap, gfmap)
        if qt == "single_choice":
            k = (r["exam_title"], norm(r["answer"]))
            lst = scmap.get(k) or []
            i = sc_idx[k]
            sc_idx[k] += 1
            if i < len(lst):
                res["lang"], res["source"], res["why"] = lst[i], "rule:per_item", "官方单选逐题标注表"
            else:
                res["lang"], res["source"], res["why"] = None, "rule:fmt_only", ""
        elif qt == "grammar_fill":
            a = norm(r["answer"])
            if " | " in a:
                # 聚合行（id=708）：10 个空挤在一行，取众数
                votes = collections.Counter()
                for p in [x.strip() for x in a.split(" | ") if x.strip()]:
                    votes[(gfmap.get((r["exam_title"], p)) or gfmap.get(("湖北2025", p)) or ["E-G06"])[0]] += 1
                if votes:
                    res["lang"], res["source"], res["why"] = votes.most_common(1)[0][0], "rule:per_item", "官方语法填空聚合行按 10 个空取众数"
            else:
                lst = gfmap.get((r["exam_title"], a)) or []
                if lst:
                    res["lang"], res["source"], res["why"] = lst[0], "rule:per_item", "官方语法填空逐题标注表"
        out[r["question_uid"]] = res
    return out


# --------------------------------------------------------------------------- 主流程

def main() -> int:
    ap = argparse.ArgumentParser(description="英语题库逐题知识点打标")
    ap.add_argument("--dry-run", action="store_true", help="只报告规则覆盖/LLM 题量/预估花费，不发请求不写库")
    ap.add_argument("--apply", action="store_true", help="真正写库")
    ap.add_argument("--report", action="store_true", help="只按当前库内容重生成简报（不写库）")
    ap.add_argument("--sample", type=int, default=0, help="随机抽 N 题打印打标结果与依据")
    ap.add_argument("--cap-cny", type=float, default=2.0, help="本轮 LLM 花费上限（默认 2.0 元）")
    ap.add_argument("--batch-size", type=int, default=20, help="LLM 每批题数（默认 20）")
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 题（试跑用）")
    ap.add_argument("--no-llm", action="store_true", help="只用规则，不调 LLM")
    ap.add_argument("--force", action="store_true", help="重刷全部行（含已有合规标签的行）")
    args = ap.parse_args()

    kb = load_kb()
    con = connect()
    all_rows = [dict(r) for r in con.execute(
        "SELECT id, question_uid, question_type, stem, options, answer, explanation, material_text, "
        "exam_title, trust_level, status, knowledge_point FROM questions ORDER BY id")]
    keep = re.compile(r"^E-[A-Z]\d{2}\b")
    legacy = [r for r in all_rows if (r["knowledge_point"] or "").strip() and not keep.match((r["knowledge_point"] or "").strip())]
    todo = all_rows if args.force else [r for r in all_rows if not keep.match((r["knowledge_point"] or "").strip())]
    if args.limit:
        todo = todo[: args.limit]

    scmap, gfmap = build_scmap(), build_gfmap()

    # ---------- 规则阶段 ----------
    results = rule_pass(todo, kb, scmap, gfmap)   # uid -> {fmt, lang, source, why}
    by_source = collections.Counter(v["source"] for v in results.values())
    need_llm = [r for r in todo if results[r["question_uid"]]["lang"] is None
                and (r["question_type"] in LANG_CANDIDATES)]
    n_batches = (len(need_llm) + args.batch_size - 1) // args.batch_size
    est_per_batch = (3200 * PRICE[FLASH_MODEL]["in"] + 900 * PRICE[FLASH_MODEL]["out"]) / 1_000_000
    est = n_batches * est_per_batch

    print("=" * 78)
    print(f"待处理 {len(todo)} 题（全库 {len(all_rows)}，其中遗留非体系标签 {len(legacy)} 条，已有合规标签 "
          f"{len(all_rows) - len(todo) if not args.force else 0} 条）")
    print("规则命中：" + "  ".join(f"{k}={v}" for k, v in sorted(by_source.items())))
    print(f"需 LLM 兜底：{len(need_llm)} 题 / {n_batches} 批（每批 {args.batch_size}）")
    print(f"预估 LLM 花费 ¥{est:.4f}（上限 ¥{args.cap_cny:.2f}）")
    cov = len(todo) - len(need_llm)
    if todo:
        print(f"规则覆盖率 {cov}/{len(todo)} = {cov / len(todo):.1%}；LLM 占比 {len(need_llm) / len(todo):.1%}")
    print("\n分题型：")
    print(f"  {'question_type':<22}{'题数':>6}{'规则':>7}{'LLM':>7}   '")
    need_by_uid = {r["question_uid"] for r in need_llm}
    agg = collections.defaultdict(lambda: [0, 0, 0])
    for r in todo:
        a = agg[r["question_type"]]
        a[0] += 1
        a[2 if r["question_uid"] in need_by_uid else 1] += 1
    for qt in sorted(agg, key=lambda x: -agg[x][0]):
        a = agg[qt]
        print(f"  {qt:<22}{a[0]:>6}{a[1]:>7}{a[2]:>7}")
    nofmt = [r for r in todo if not results[r["question_uid"]]["fmt"]]
    if nofmt:
        print("\n题型维度判不出的行（需人工确认）：")
        for r in nofmt[:20]:
            print(f"  uid={r['question_uid']} qtype={r['question_type']!r} exam={r['exam_title']!r} "
                  f"stem={(r['stem'] or '')[:60]!r}")

    if args.report:
        write_report(con, kb, results if results else None, legacy, None, "report-only")
        con.close()
        return 0
    if args.sample:
        do_sample(con, kb, args.sample, scmap, gfmap)
        con.close()
        return 0
    if not args.dry_run and not args.apply:
        print("未指定 --dry-run / --apply，退出（不做任何修改）")
        con.close()
        return 0

    if args.dry_run:
        print("dry-run：不发起任何请求、不写库。")
        con.close()
        return 0

    if est > args.cap_cny:
        print(f"拒绝执行：预估 ¥{est:.4f} > 上限 ¥{args.cap_cny:.2f}")
        con.close()
        return 2

    bal = balance_cny()
    print(f"当前余额 ¥{bal if bal is None else round(bal, 2)}")
    if bal is not None and bal < BALANCE_STOP_CNY:
        print(f"拒绝执行：余额低于停机线 ¥{BALANCE_STOP_CNY}")
        con.close()
        return 2

    spent = 0.0
    llm_stats = {"calls": 0, "ok": 0, "fail": 0, "unresolved": 0}
    fail_log = TMP / "llm_failures.jsonl"
    TMP.mkdir(parents=True, exist_ok=True)

    if need_llm and not args.no_llm:
        from openai import OpenAI
        env = load_env()
        client = OpenAI(api_key=env["DEEPSEEK_API_KEY"],
                        base_url=env.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"), timeout=180)
        t0 = time.time()
        for bi in range(n_batches):
            batch = need_llm[bi * args.batch_size:(bi + 1) * args.batch_size]
            allowed = sorted({c for r in batch for c in LANG_CANDIDATES.get(r["question_type"], [])})
            got = [None] * len(batch)
            usage = {}
            for attempt in (1, 2):
                try:
                    got, usage = llm_tag_batch(client, batch, allowed)
                    if usage:
                        c = cost_of(FLASH_MODEL, usage)
                        spent += c
                        log_ledger({"ts": now_iso(), "stage": STAGE, "kind": "llm_call", "model": FLASH_MODEL,
                                    "usage": usage, "cost_cny": round(c, 6),
                                    "note": f"batch {bi + 1}/{n_batches} n={len(batch)} attempt={attempt}"})
                    llm_stats["ok"] += 1
                    break
                except Exception as e:  # noqa: BLE001
                    llm_stats["fail"] += 1
                    log_ledger({"ts": now_iso(), "stage": STAGE, "kind": "llm_error", "model": FLASH_MODEL,
                                "note": f"batch {bi + 1} attempt={attempt}: {type(e).__name__}: {str(e)[:180]}"})
                    with fail_log.open("a", encoding="utf-8") as fh:
                        fh.write(json.dumps({"ts": now_iso(), "batch": bi + 1, "attempt": attempt,
                                             "uids": [x["question_uid"] for x in batch],
                                             "error": f"{type(e).__name__}: {str(e)[:300]}"}, ensure_ascii=False) + "\n")
                    if attempt == 2:
                        got = [None] * len(batch)
            llm_stats["calls"] += 1
            for r, k in zip(batch, got):
                if k:
                    results[r["question_uid"]]["lang"] = k
                    results[r["question_uid"]]["source"] = "llm"
                    results[r["question_uid"]]["why"] = "deepseek-flash 判定"
                else:
                    llm_stats["unresolved"] += 1
            print(f"  [batch {bi + 1}/{n_batches}] 已花 ¥{spent:.4f}  ({time.time() - t0:.0f}s)")
            if spent > args.cap_cny:
                print(f"⚠️ 累计 ¥{spent:.4f} 超上限 ¥{args.cap_cny}，立即停止 LLM 阶段")
                break
            nb = balance_cny()
            if nb is not None and nb < BALANCE_STOP_CNY:
                print(f"⚠️ 余额 ¥{nb:.2f} 低于停机线 ¥{BALANCE_STOP_CNY}，立即停止 LLM 阶段")
                break

    # ---------- 写库 ----------
    updates = []
    unresolved = []
    for r in todo:
        res = results[r["question_uid"]]
        if not res["fmt"]:
            unresolved.append((r, "题型维度判不出（question_type 不在体系内）"))
            continue
        parts = [fmt(kb, res["fmt"])]
        if res["lang"]:
            parts.append(fmt(kb, res["lang"]))
        else:
            unresolved.append((r, "只判出题型维度，语言知识维度判不出（宁缺勿造）"))
        updates.append(((" | ".join(parts)), f"{SYLLABUS_REF}#{res['fmt']}",
                        res["source"], res["why"], r["question_uid"]))

    with con:
        con.executemany("UPDATE questions SET knowledge_point=?, syllabus_ref=? WHERE question_uid=?",
                        [(u[0], u[1], u[4]) for u in updates])

    # 抽样明细落盘（append；同一 uid 以最后一条为准，供报告与人工抽查）
    detail = TMP / "tagging_detail.jsonl"
    TMP.mkdir(parents=True, exist_ok=True)
    ts = now_iso()
    with detail.open("a", encoding="utf-8") as fh:
        for r in todo:
            res = results[r["question_uid"]]
            fh.write(json.dumps({"ts": ts, "uid": r["question_uid"], "qtype": r["question_type"], "exam": r["exam_title"],
                                 "status": r["status"], "fmt": res["fmt"], "lang": res["lang"],
                                 "source": res["source"], "why": res["why"],
                                 "kp": (fmt(kb, res["fmt"]) + (" | " + fmt(kb, res["lang"]) if res["lang"] else ""))},
                                ensure_ascii=False) + "\n")

    payload = {"todo": len(todo), "updated": len(updates), "unresolved": len(unresolved),
               "by_source": dict(by_source), "llm": llm_stats, "spent": spent, "est": est,
               "legacy": [(r["question_uid"], r["knowledge_point"]) for r in legacy],
               "unresolved_samples": [(r["question_uid"], r["question_type"], why) for r, why in unresolved[:40]]}
    if spent > 0:
        log_ledger({"ts": now_iso(), "stage": STAGE, "kind": "summary", "cost_cny": round(spent, 6),
                    "note": f"updated={len(updates)} llm_calls={llm_stats['calls']} unresolved={len(unresolved)}"})
    write_report(con, kb, results, legacy, payload, "apply")
    print(f"\n写库完成：更新 {len(updates)} 行，未打标 {len(unresolved)} 行，LLM 花费 ¥{spent:.4f}")
    print(f"简报：{REPORT}")
    con.close()
    return 0


def do_sample(con, kb: dict, n: int, scmap: dict, gfmap: dict) -> None:
    rows = [dict(r) for r in con.execute(
        "SELECT id, question_uid, question_type, stem, answer, explanation, exam_title, trust_level, status, "
        "knowledge_point FROM questions WHERE TRIM(COALESCE(knowledge_point,''))<>'' ORDER BY RANDOM() LIMIT ?", (n,))]
    for r in rows:
        print("-" * 78)
        print(f"uid={r['question_uid']}  题型={r['question_type']}  卷别={r['exam_title']}  trust={r['trust_level']}  status={r['status']}")
        print(f"  题干：{clip(r['stem'], 180)}")
        print(f"  答案：{clip(r['answer'], 80)}")
        print(f"  解析：{clip(r['explanation'], 140)}")
        print(f"  标签：{r['knowledge_point']}")


def write_report(con, kb: dict, results, legacy, payload, mode: str) -> None:
    total = con.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
    filled = con.execute("SELECT COUNT(*) FROM questions WHERE TRIM(COALESCE(knowledge_point,''))<>''").fetchone()[0]
    approved = con.execute("SELECT COUNT(*) FROM questions WHERE status='approved'").fetchone()[0]
    filled_appr = con.execute("SELECT COUNT(*) FROM questions WHERE status='approved' AND TRIM(COALESCE(knowledge_point,''))<>''").fetchone()[0]
    rows = [dict(r) for r in con.execute(
        "SELECT question_uid, question_type, status, trust_level, exam_title, stem, answer, explanation, knowledge_point "
        "FROM questions")]

    # 规则复现：对全库重跑规则引擎，与库内标签比对 → 得出「规则 vs LLM」占比（不依赖运行日志）
    scmap, gfmap = build_scmap(), build_gfmap()
    rp = rule_pass(rows, kb, scmap, gfmap)
    src_stat = collections.Counter()
    for r in rows:
        res = rp[r["question_uid"]]
        if not res["fmt"]:
            src_stat["未能判定"] += 1
            continue
        rule_kp = fmt(kb, res["fmt"]) + (" | " + fmt(kb, res["lang"]) if res["lang"] else "")
        if (r["knowledge_point"] or "").strip() == rule_kp:
            src_stat[res["source"]] += 1
        else:
            src_stat["llm" if res["lang"] is None else "llm/人工修正"] += 1

    fmt_dist = collections.Counter()
    lang_dist = collections.Counter()
    combo_type = collections.defaultdict(set)
    for r in rows:
        kp = (r["knowledge_point"] or "").strip()
        codes = re.findall(r"\bE-[A-Z]\d{2}\b", kp)
        for c in codes:
            (fmt_dist if c in kb["format_ids"] else lang_dist)[c] += 1
        if codes:
            combo_type[r["question_type"]].add(codes[0])

    fmt_only = sum(1 for r in rows if (r["knowledge_point"] or "").strip()
                   and len(re.findall(r"\bE-[A-Z]\d{2}\b", r["knowledge_point"])) == 1)
    both = sum(1 for r in rows if len(re.findall(r"\bE-[A-Z]\d{2}\b", r["knowledge_point"] or "")) >= 2)
    empty = total - filled

    md = []
    md.append("# 英语题库逐题知识点打标简报")
    md.append("")
    md.append(f"- 生成时间：{now_iso()}（mode={mode}）")
    md.append(f"- 知识点体系：`{SYLLABUS_REF}`（17 题型维度 E-T01..E-T17 + 31 语言知识维度 E-G01..E-G17 / E-S01..E-S14）")
    md.append(f"- **有 knowledge_point 的题数 / 总数：{filled} / {total}**（approved 口径：{filled_appr} / {approved}）")
    md.append(f"- 未打标：**{empty}** 题" + ("（题型维度与语言维度均已覆盖全库）" if empty == 0 else ""))
    md.append(f"- 含 2 个知识点的题：{both}；只有题型维度、语言维度判不出的题：{fmt_only}")
    md.append("- 写入字段：仅 `knowledge_point`（`E-Txx 名称 [| E-Gxx/E-Sxx 名称]`）与 `syllabus_ref`（`#E-Txx`）；`status` 与其他字段一律未改动")
    md.append("")
    md.append("## 规则 vs LLM 占比（对全库重跑规则引擎与库内标签逐题比对）")
    md.append("")
    md.append("| 判定来源 | 题数 | 占比 |")
    md.append("|---|---|---|")
    rule_n = sum(v for k, v in src_stat.items() if k.startswith("rule:"))
    llm_n = sum(v for k, v in src_stat.items() if k.startswith("llm"))
    for k, v in sorted(src_stat.items(), key=lambda x: -x[1]):
        label = {"rule:per_item": "规则·逐题标注表（官方单选/语法填空）",
                 "rule:qtype": "规则·题型映射", "rule:keyword": "规则·关键词",
                 "rule:fmt_only": "规则·只判出题型维度（语言维度留空）",
                 "llm": "LLM 兜底（deepseek-flash）",
                 "llm/人工修正": "LLM/人工修正（覆盖了规则结果）",
                 "未能判定": "未能判定"}.get(k, k)
        md.append(f"| {label} | {v} | {v / total:.1%} |")
    md.append(f"| **合计：规则 {rule_n} / LLM {llm_n}** | {rule_n + llm_n} | {(rule_n + llm_n) / total:.1%} |")
    md.append("")
    spend_total, calls = 0.0, 0
    if LEDGER.exists():
        for line in LEDGER.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            if e.get("stage") == STAGE and e.get("kind") == "llm_call":
                spend_total += float(e.get("cost_cny") or 0)
                calls += 1
    md.append(f"- 本阶段账本累计（`logs/cost_ledger.jsonl`，`stage='en_tagging'`）：**¥{spend_total:.4f}**，共 {calls} 次 LLM 调用。")
    md.append("")
    if payload:
        md.append("## 最近一次执行")
        md.append("")
        md.append(f"- 处理题数：{payload['todo']}，写库 {payload['updated']} 行，未打标 {payload['unresolved']} 行")
        md.append(f"- 规则命中：{payload['by_source']}")
        md.append(f"- LLM 兜底：{payload['llm']}；实际花费 **¥{payload['spent']:.4f}**（预估 ¥{payload['est']:.4f}）")
        if payload.get("legacy"):
            md.append(f"- 归一化的遗留自由文本标签 {len(payload['legacy'])} 条：" +
                      "、".join(f"`{u}`={v!r}" for u, v in payload["legacy"][:12]))
        if payload.get("unresolved_samples"):
            md.append("- 未打标样例：" + "；".join(f"`{u}`({t}) {w}" for u, t, w in payload["unresolved_samples"][:10]))
        md.append("")

    md.append("## 题型维度分布（E-T*）")
    md.append("")
    md.append("| 知识点 | 名称 | 题数 |")
    md.append("|---|---|---|")
    for pid, n in sorted(fmt_dist.items()):
        md.append(f"| {pid} | {kb['name'].get(pid, '')} | {n} |")
    md.append("")
    md.append("## 语言知识维度分布（E-G* / E-S*）")
    md.append("")
    md.append("| 知识点 | 名称 | 题数 |")
    md.append("|---|---|---|")
    for pid, n in sorted(lang_dist.items()):
        md.append(f"| {pid} | {kb['name'].get(pid, '')} | {n} |")
    md.append("")
    md.append("## 题型 → 题型维度映射核对")
    md.append("")
    md.append("| question_type | 题数 | 落到哪些题型维度 |")
    md.append("|---|---|---|")
    for qt in sorted(combo_type):
        n = sum(1 for r in rows if r["question_type"] == qt)
        md.append(f"| {qt} | {n} | {', '.join(sorted(combo_type[qt]))} |")
    md.append("")
    md.append("## 说明与口径")
    md.append("")
    md.append("- 题型维度由 `question_type` 规则确定；`reading_qa` 按答案形态分（裸选项字母 → E-T16，其余 → E-T04，与知识库 42/219 口径一致）；")
    md.append("  `writing` 按卷别与体裁分（河北 → E-T17 提纲作文；湖北应用文 → E-T06，议论文 → E-T17）。")
    md.append("- 语言知识维度优先用规则：官方单选 103 题与官方语法填空 31 题沿用 `tests/build_english_kb.py` 的逐题标注表，")
    md.append("  官方阅读 240 题沿用同文件的 `tag_rq()` 判定函数，保证与知识库统计口径完全一致；")
    md.append("  另按知识库 E-S04 自身的定义补一条 `tag_rq()` 漏掉的规则：`Which of the following is TRUE / NOT true` 型正误判断题 → `E-S04 阅读·推理判断`（15 题）；")
    md.append("  其余用关键词规则（完形 E-S13/E-S14、选词填空 E-G06/E-G16/E-G10、语法填空非官方句的虚拟/倒装等）。")
    md.append("- 规则判不出的残差交给 `deepseek-flash`（`reasoning_effort=low`，每批 20 题，严格 JSON，越界 ID 丢弃）；")
    md.append("  仍判不出的**如实留空语言维度**，只保留题型维度，不做编造。")
    md.append("- 账本：`logs/cost_ledger.jsonl`（`stage='en_tagging'`）。可复跑：`python scripts/tag_english_kp.py --dry-run` / `--apply`（默认幂等）。")
    md.append("- **错档题**（DB 来源质量问题，已按内容纠正）：1 题 `question_type=writing` 实为四选一词汇题 → `E-T08 单项选择 | E-G17 词汇辨析`；")
    md.append("  5 题 `question_type=grammar_fill` 实为「英文句子 + 长空，写中文译文」的英译汉题 → 语言维度 `E-S08 翻译·英译汉`。")
    md.append("- **`reading_fill` 内容异质**：362 题中 279 题为 `rejected` 的第三方练习题（含词汇单选、汉译英、短文片段），")
    md.append("  其题型维度按 `question_type` 落 `E-T03 阅读填空`（遵循规则 1：题型维度由 question_type 决定），语言维度按知识库映射落 `E-S07`；")
    md.append("  83 题 `approved` 中 55 题为湖北/河北官方阅读填空，判定可靠。")
    md.append("- **只有题型维度的题**：均为 `rejected` 的第三方「句型改写/句子翻译」残题（题干与答案不匹配），语言点无法判定，按「宁缺勿造」留空。")
    md.append("")
    REPORT.write_text("\n".join(md) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
