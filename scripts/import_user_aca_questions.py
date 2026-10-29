#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把用户提供的 3 个 ACA/ACP 题库 txt 分类入库（`data/aca_llm.sqlite`）。

输入（只读，项目内副本）
------------------------
`inbox/aca_llm/user_provided/题目{,2,3}.txt`

两种格式
--------
A. 空行分隔块（`题目.txt`）::

       <题干，可多行>

       A、<选项>
       ...
       答案：C          # 多选写作 答案：ABC；可能整块缺失
       标签：RAG，召回   # 可能缺失

B. 编号题（`题目2.txt` / `题目3.txt`）::

       二、大模型LLM ACA - ACP认证考试模拟试卷     ← 卷头，排除
       （一）单选题：70 题 × 1 分 = 70 分          ← 分节头，排除（决定 question_type）
       1. <题干>
       A. <选项>
       ...
       （二）多选题：30 题 × 1 分 = 30 分
       ...
       ⚠️ 这两个文件**全文没有答案行**（`答案：` 命中全是选项正文里的“答案”二字）。

分类（ACA 助理级 / ACP 专业级）
--------------------------------
规则优先（零成本，关键词+标签打分），规则判不出的残差交 `deepseek-flash`
（`reasoning_effort='low'`、每批 20 题、严格 JSON）。🔴 成本闸门 `--cap-cny`（默认 1.0），
每次调用 append `logs/cost_ledger.jsonl`（`stage='aca_acp_sort'`），余额 < ¥6 立即停止。

用法
----
    python scripts/import_user_aca_questions.py --dry-run
    python scripts/import_user_aca_questions.py --apply --cap-cny 1.0
    python scripts/import_user_aca_questions.py --dump      # 只导出解析结果供人工核对
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from lib.uid import content_fingerprint, generate_uid, normalize_stem  # noqa: E402

SUBJECT = "aca_llm"
DB = ROOT / "data" / "aca_llm.sqlite"
KB_FILE = ROOT / "subjects" / "aca_llm" / "knowledge_base.json"
SRC_DIR = ROOT / "inbox" / "aca_llm" / "user_provided"
ENV_FILE = ROOT / ".env"
LEDGER = ROOT / "logs" / "cost_ledger.jsonl"
TMP = ROOT / "tests" / ".tmp" / "aca_acp"

STAGE = "aca_acp_sort"
FLASH_MODEL = "deepseek-flash"
# 与 scripts/tag_english_kp.py / judge_calibration.py 同一张价目表（元 / 1M tokens），保证账本可比
PRICE = {
    "deepseek-flash": {"in": 1.0, "out": 4.0, "cache": 0.02},
    "deepseek-v4-pro": {"in": 4.5, "out": 13.5, "cache": 0.15},
}
BALANCE_STOP_CNY = 6.0
EXAM_TITLE = "用户提供题库（ACA/ACP）"

FILES = ("题目.txt", "题目2.txt", "题目3.txt")

# =========================================================================== 解析

_OPT_RE = re.compile(r"^([A-Ha-h])\s*[、.．,，:：]\s*(.*)$")
_NUM_RE = re.compile(r"^(\d{1,3})\s*[、.．]\s*(.*)$")
_ANS_RE = re.compile(r"^答案\s*[：:]\s*([A-Ha-h][A-Ha-h,\s、，]*)$")
_TAG_RE = re.compile(r"^标签\s*[：:]\s*(.*)$")
_SEC_RE = re.compile(r"^[（(]?[一二三四五六七八九十][）)、.．]")
# 卷头/分节头：**必须整行**匹配，避免误吃真正的题干（如含“模拟/真题”字样的题）
_HEAD_RE = re.compile(r"^[（(]?[一二三四五六七八九十][）)、.．].*$|^.*题\s*[×xX*]\s*\d+\s*分.*$")


class Q:
    def __init__(self, stem: str, src: str, order: int):
        self.stem = stem.strip()
        self.options: list[tuple[str, str]] = []
        self.answer = ""
        self.tags: list[str] = []
        self.qtype = ""
        self.src = src
        self.order = order
        self.note = ""
        # 分类结果
        self.clabel: str | None = None
        self.csrc = "none"
        self.cwhy = ""
        self.llm_kp = ""
        self.update_uid: str | None = None      # 非 None = 刷新既有行的 uid（--update-existing）

    def to_dict(self) -> dict:
        return {"stem": self.stem, "options": self.options, "answer": self.answer,
                "tags": self.tags, "qtype": self.qtype, "src": self.src, "order": self.order,
                "note": self.note, "clabel": self.clabel, "csrc": self.csrc, "cwhy": self.cwhy}


def _read(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "gbk"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def parse_blocks(text: str, src: str) -> list[Q]:
    """格式 A：空行分隔块。非题目（卷头/说明/ad）会在收尾时按“无选项”剔除。"""
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    out: list[Q] = []
    cur: Q | None = None
    for b in blocks:
        first = b.split("\n")[0].strip()
        m_ans = _ANS_RE.match(first)
        m_tag = _TAG_RE.match(first)
        m_opt = _OPT_RE.match(first)
        if m_ans and cur is not None:
            cur.answer = re.sub(r"[^A-H]", "", m_ans.group(1).upper())
            continue
        if m_tag and cur is not None:
            cur.tags = [t.strip() for t in re.split(r"[，,、;；/]", m_tag.group(1)) if t.strip()]
            continue
        if m_opt and cur is not None:
            cur.options.append((m_opt.group(1).upper(), _flat(m_opt.group(2))))
            continue
        # 新题块（题干可能多行）
        cur = Q(b, src, len(out))
        out.append(cur)
    return out


def parse_numbered(text: str, src: str) -> list[Q]:
    """格式 B：编号题 + 分节头。行级状态机，题干/选项均可多行续接。"""
    out: list[Q] = []
    cur: Q | None = None
    mode = "single_choice"
    last_kind: str | None = None      # 'stem' | 'opt'
    i = 0
    lines = text.replace("\r\n", "\n").split("\n")
    while i < len(lines):
        s = lines[i].strip()
        i += 1
        if not s:
            continue                   # 空行只是排版分隔，不改变「上一元素」归属
        if _HEAD_RE.match(s) and len(s) < 80:
            if "多选" in s:
                mode = "multiple_choice"
            elif "单选" in s:
                mode = "single_choice"
            elif "判断" in s:
                mode = "true_false"
            last_kind = None
            continue
        m_num = _NUM_RE.match(s)
        m_opt = _OPT_RE.match(s)
        if m_opt:
            key = m_opt.group(1).upper()
            if cur is not None:
                cur.options.append((key, _flat(m_opt.group(2))))
                last_kind = "opt"
            continue
        if m_num:
            cur = Q(m_num.group(2), src, len(out))
            cur.qtype = mode
            out.append(cur)
            last_kind = "stem"
            continue
        # 续行：接到「上一个元素」上（题干或最后一个选项）
        if cur is None:
            continue
        if last_kind == "opt" and cur.options:
            k, t = cur.options[-1]
            cur.options[-1] = (k, _flat(t + s))
        else:
            cur.stem = _flat(cur.stem + s) if last_kind == "stem" else (cur.stem + "\n" + s).strip()
            last_kind = "stem"
    return out


def _flat(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def parse_file(path: Path) -> tuple[list[Q], list[Q]]:
    """→ (题目, 被剔除的非题目块)。"""
    text = _read(path)
    src = f"用户提供：{path.name}"
    qs = parse_numbered(text, src) if re.search(r"(?m)^\s*\d{1,3}\s*[、.．]", text) else parse_blocks(text, src)
    if not qs:
        qs = parse_blocks(text, src)
    good, bad = [], []
    for q in qs:
        if len(q.options) < 2:
            q.note = "无选项（卷头/说明性文字）"
            bad.append(q)
            continue
        if len(q.stem) < 6:
            q.note = "题干过短"
            bad.append(q)
            continue
        if not q.qtype:
            q.qtype = "multiple_choice" if len(q.answer) > 1 else "single_choice"
        good.append(q)
    return good, bad


def parse_all() -> tuple[list[Q], list[Q]]:
    good: list[Q] = []
    bad: list[Q] = []
    for name in FILES:
        p = SRC_DIR / name
        if not p.exists():
            print(f"  ⚠️ 缺文件 {p}")
            continue
        g, b = parse_file(p)
        good.extend(g)
        bad.extend(b)
    return good, bad


# =========================================================================== 知识体系

def load_kb() -> dict:
    kb = json.loads(KB_FILE.read_text(encoding="utf-8-sig"))
    points: list[dict] = []
    for m in kb["modules"]:
        for p in m["points"]:
            points.append({"id": p["id"], "name": p["name"], "desc": p.get("desc") or "",
                           "module": m["no"], "mname": m["name"], "difficulty": p.get("difficulty") or ""})
    return {"modules": kb["modules"], "points": points, "by_id": {p["id"]: p for p in points}}


def kp_label(kb: dict, pid: str) -> str:
    p = kb["by_id"].get(pid)
    return f"{pid} {p['name']}" if p else pid


# =========================================================================== 分类规则

# ACP 信号（正则, 权重）：原理与内部机制 / 训练与压缩算法细节 / 工程架构 / RAG 深层调优与评测体系
ACP_PAT: list[tuple[str, int]] = [
    # —— 机器学习 / 深度学习原理与内部机制 ——
    (r"梯度下降|学习率|过拟合|欠拟合|早停|early\s*stopping|模型收敛", 4),
    (r"batch\s*size|批量大小", 3),
    (r"训练损失|验证损失|损失函数|迭代次数|epoch", 3),
    (r"分词化|tokeni[sz]|padding|统一长度|词表|拆分成单词|词汇单元|分词", 4),
    (r"自注意力|多头注意力|注意力机制|位置编码|层归一化|批归一化|残差连接", 5),
    (r"Transformer|RNN|LSTM|CNN|U-Net|DDPM|扩散模型|GAN", 3),
    (r"底层原理|内部机制|算法原理|计算过程|数学|公式", 3),
    (r"逻辑回归|支持向量机|SVM|决策树|随机森林|K-means|聚类算法", 5),
    (r"RLHF|人类反馈|奖励模型", 2),
    # —— 微调 / 压缩 / 训练算法细节 ——
    (r"LoRA|QLoRA|PEFT|Adapter|Prefix\s*Tuning|Prompt\s*Tuning|低秩", 4),
    (r"(?<!向)量化|蒸馏|剪枝|模型压缩|参数高效", 4),
    (r"分布式训练|数据并行|模型并行|流水线并行|训练循环|参数服务器", 5),
    # —— 评测体系（Ragas / GSB / 指标计算）——
    (r"context\s*precision|context\s*recall|Answer\s*Correctness|RAGAS|Ragas|ragas", 5),
    (r"评测集|自动化评测|评测机制|评测的?可信度|GSB|评测指标", 4),
    (r"精确率|召回率|混淆矩阵|AUC|ROC", 4),
    # —— 向量存储与检索架构 ——
    (r"向量数据库|Milvus|Qdrant|Faiss|HNSW|ANN|近似最近邻|向量存储|索引结构|向量检索服务", 4),
    (r"高可用|7x24|7×24|容灾|水平扩展|数百万|百万级", 4),
    (r"rerank|重排序|重排|RRF|倒数排名融合|混合检索|多路召回|精排|粗排", 4),
    (r"余弦相似度|相似度计算|内积|距离度量", 4),
    (r"相似度阈值", 2),
    # —— 部署 / 性能工程 ——
    (r"推理加速|显存|模型部署|服务化|吞吐|QPS|响应时间低于|延迟低于", 3),
    (r"多模态技术?底层原理", 5),
    # —— 采样/解码参数的**机制**（问“如何影响 Token 筛选”＝原理）——
    (r"如何影响.{0,10}(Token|候选|筛选|概率|下一个)", 6),
    # —— RAG 检索调优（准确度/效率/低相关过滤）——
    (r"检索准确度|检索不准确|检索效率|低相关|相关度很低|过滤掉低相关|召回.*相关度", 3),
]

# ACA 信号（正则, 权重）：怎么用 / 怎么配 / 怎么选 / 最佳实践 / 概念认知 / 安全合规
ACA_PAT: list[tuple[str, int]] = [
    # —— 提示词工程（应用层）——
    (r"提示词|prompt|Prompt", 3),
    (r"少样本|零样本|few-?shot|zero-?shot|思维链|chain\s*of\s*thought", 4),
    (r"角色扮演|分隔符|输出格式|系统提示", 3),
    # —— 阿里云产品功能与 API 用法 ——
    (r"百炼|DashScope|dashscope|通义千问|通义万相|Qwen-|qwen-|CosyVoice|moviepy|enable_search", 4),
    (r"BatchAPI|Assistant\s*API|代码解释器|插件|ModelScope-Agent|调用\s*API", 4),
    (r"LlamaIndex|Llamaindex|LlamalIndex|VectorStoreIndex|StorageContext|as_query_engine|"
     r"similarity_top_k|custom_prompt|prompt_template|from_documents", 2),
    (r"代码片段|这段代码|以下代码|代码段|函数的作用|参数的作用|的作用是什么|类设计为基类", 3),
    # —— RAG 应用层（切片/建库/流程/知识库运维）——
    (r"切片方法|文本切片|文档切片|切分|分块|chunk|滑动窗口|语义切分|分割成文本段", 3),
    (r"建立索引|索引阶段|检索生成|生成阶段|索引存储", 3),
    (r"知识库|私域|上传|文档解析", 3),
    (r"核心思想|主要目的|主要作用|主要任务|主要步骤|为什么需要|主要原因|知识增强", 2),
    (r"问题改写|查询改写|query\s*改写|检索前|还原.{0,4}意图|意图理解|意图识别", 3),
    # —— 安全合规 ——
    (r"内容安全|合规|脱敏|隐私|个人信息|最小权限|注入攻击|敏感信息|用户协议", 4),
    (r"安全|泄露|恶意|攻击|防护", 3),
    (r"幻觉|捏造|虚构", 3),
    # —— Agent 应用 ——
    (r"工具描述|工具调用|多智能体|智能体|Agent", 3),
    # —— 多模态应用（万相/听悟/视觉理解）——
    (r"多模态|图像理解|视觉理解|视频理解|语音合成|虚拟主播|短视频|文生图", 3),
    # —— 微调应用层（何时/怎么选/流程/数据准备）——
    (r"微调最适合|是否微调|什么时候.{0,4}微调|微调方案|微调效果|微调数据集|微调项目|"
     r"微调可能带来|微调需求|影响.{0,6}微调|微调的数据准备|数据集准备|从头训练|重头训练|从零训练", 3),
    # —— 采样/解码参数**用法**（怎么设、什么场景、参数作用）——
    (r"temperature|top_p|top_k|max_tokens|参数组合", 3),
    # —— 成本与用量 ——
    (r"成本|计费|价格", 2),
]


def _pat_hits(text: str, pats: list[tuple[str, int]]) -> tuple[int, list[str]]:
    score, hits = 0, []
    for pat, w in pats:
        m = re.search(pat, text, re.I)
        if m:
            score += w
            hits.append(m.group(0))
    return score, hits


def classify_rule(q: Q) -> dict:
    """→ {'label': 'aca'|'acp'|None, 'why': str, 'source': 'rule:...'}"""
    stem = q.stem
    tags = "，".join(q.tags)
    sa, ha = _pat_hits(stem, ACA_PAT)
    sp, hp = _pat_hits(stem, ACP_PAT)
    # 标签是出题人给的考点，权重更高（只对文件 1 有标签）
    sat, hat = _pat_hits(tags, ACA_PAT) if tags else (0, [])
    spt, hpt = _pat_hits(tags, ACP_PAT) if tags else (0, [])
    sa += sat * 2
    sp += spt * 2
    why = (f"ACA={sa}({'+'.join((ha + hat)[:5]) or '-'}) "
           f"ACP={sp}({'+'.join((hp + hpt)[:5]) or '-'})")
    if sa == 0 and sp == 0:
        return {"label": None, "why": why + " 无信号", "source": "rule:none"}
    if abs(sa - sp) < 3:
        return {"label": None, "why": why + " 差值<3", "source": "rule:close"}
    return {"label": "aca" if sa > sp else "acp", "why": why, "source": "rule:score"}


def pick_aca_kp(kb: dict, q: Q, hint_kp: str | None = None) -> tuple[str, str]:
    """规则兜底的知识点指派（LLM 未命中时用）→ (KP-x.y 名称, 依据)。

    关键词 = 知识点名称里的词 + 描述里出现的**专有名词**；只保留"区分度"足够的关键词
    （在 ≤3 个知识点里出现的），否则「模型/应用/平台/prompt」这类泛词会让所有题都
    落到同一个泛知识点上（实测曾把 20 道题全判给 KP-1.8）。
    """
    if hint_kp and hint_kp in kb["by_id"]:
        return kp_label(kb, hint_kp), "llm"
    kws = kb.setdefault("_kw", _build_kw_index(kb))
    hay = (q.stem + " " + " ".join(t for _, t in q.options) + " " + "，".join(q.tags)).lower()
    best, best_score, best_hit = None, 0.0, ""
    for pid, ws in kws.items():
        score, hit = 0.0, ""
        for kw, w in ws:
            if kw in hay:
                score += w * len(kw)
                hit = hit or kw
        if score > best_score:
            best, best_score, best_hit = pid, score, hit
    if best is None or best_score < 8.0:
        return "", ""
    return kp_label(kb, best), best_hit


def _build_kw_index(kb: dict) -> dict:
    """每个知识点 → [(关键词, 权重)]，泛词（出现在 >3 个知识点里）丢弃。"""
    raw: dict = {}
    for p in kb["points"]:
        ws: list[tuple[str, float]] = []
        for w in _kp_keywords(p):
            ws.append((w, 2.0))                      # 名称里的词权重高
        for w in re.findall(r"[A-Za-z][A-Za-z0-9\-\.]{2,}|[\u4e00-\u9fff]{3,8}", p["desc"]):
            if w not in _STOP:
                ws.append((w, 1.0))                  # 描述里的词权重低
        raw[p["id"]] = ws
    df: dict = collections.Counter()
    for ws in raw.values():
        for w, _ in {x[0]: x for x in ws}.items():
            df[w] += 1
    out: dict = {}
    for pid, ws in raw.items():
        seen, keep = set(), []
        for w, wt in ws:
            if w in seen or df[w] > 3:
                continue
            seen.add(w)
            keep.append((w, wt))
        out[pid] = keep
    return out


_STOP = set("的了和与及或在中为对是能否可以如何什么哪些以下哪种关于一个进行使用实现通过我们他们它"
            " 　，。、；：？！（）《》【】".split())


def _kp_keywords(p: dict) -> list[str]:
    """从知识点名称里切出可匹配的关键词（去掉太短的虚词）。"""
    out = []
    for w in re.split(r"[^\w\u4e00-\u9fff]+", p["name"]):
        w = w.strip()
        if len(w) >= 2 and w not in _STOP:
            out.append(w)
    return out


# =========================================================================== LLM 兜底

SYS_PROMPT = """你是阿里云大模型认证考试的题库分类专家。阿里云有两个认证：
- ACA（大模型工程师 ACA，助理级）：考「怎么用、怎么配、怎么选、最佳实践」——
  大模型基本概念、提示词工程、百炼/通义产品功能与 API 用法、RAG 应用层搭建
  （建库流程、切片方法选择、知识库运维）、什么时候该微调 / 微调流程与数据准备、
  Agent 与 MCP 应用、安全合规与脱敏。
- ACP（大模型高级工程师 ACP，专业级，比 ACA 高一级）：考「原理与内部机制、算法细节、
  工程与架构」——Transformer/自注意力/位置编码/RNN/CNN、过拟合与机器学习原理、
  分词与 padding、蒸馏/剪枝/量化/PEFT/LoRA 原理、分布式训练、向量数据库选型与
  高可用架构、模型部署与推理加速、RAG 深层调优（context precision/recall 权衡、
  混合检索 RRF、重排 rerank）与评测体系（Ragas/GSB/评测集）、数百万文档规模等
  大规模工程实践。

判定口径：
- 考点是产品功能「怎么用」「怎么配」「怎么选」→ ACA；
- 考点是算法/架构「原理」「怎么算」「怎么设计」→ ACP；
- 本批来自用户提供的 ACA/ACP 混合题库，用户明确说「这些很多都是 acp 的内容」，
  因此 ACP 是多数类别：只有确实落在 ACA 应用层知识点上的题才判 ACA。
- 仍然判不准时**宁可归 ACP**。

严格只输出 JSON：{"r":[{"i":1,"c":"aca|acp","kp":"KP-3.4"}]}
- i = 题号（从 1 开始，必须与输入一致）
- c = "aca" 或 "acp"
- kp = 仅当 c="aca" 时给最贴切的 ACA 知识点 id（必须来自给定清单）；c="acp" 时给 "" """


def build_user_msg(items: list, kp_menu: list[str]) -> str:
    lines = []
    for i, it in enumerate(items, 1):
        opts = " ".join(f"{k}.{t}" for k, t in it.options)
        lines.append(f"[{i}] 题干={clip(it.stem, 260)} | 选项={clip(opts, 320)} | 标签={','.join(it.tags)}")
    menu = "、".join(kp_menu)
    return (f"可选 ACA 知识点清单（c=aca 时 kp 必须取自此清单）：{menu}\n\n"
            "请判断下列题目各属于 ACA 还是 ACP：\n" + "\n".join(lines))


def clip(s: str, n: int) -> str:
    s = re.sub(r"\s+", " ", (s or "").strip())
    return s if len(s) <= n else s[:n] + "…"


def llm_sort_batch(client, items: list, kp_menu: list[str]):
    resp = client.chat.completions.create(
        model=FLASH_MODEL,
        messages=[{"role": "system", "content": SYS_PROMPT},
                  {"role": "user", "content": build_user_msg(items, kp_menu)}],
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
    out: list[dict] = [{} for _ in items]
    for row in (data.get("r") or []):
        try:
            i = int(row.get("i")) - 1
        except Exception:  # noqa: BLE001
            continue
        c = str(row.get("c") or "").strip().lower()
        if 0 <= i < len(items) and c in ("aca", "acp"):
            out[i] = {"label": c, "kp": str(row.get("kp") or "").strip()}
    return out, usage


# --------------------------------------------------------------------------- KP 指派 + ACA 归属闸门

KP_SYS = """你是阿里云「大模型工程师 ACA（助理级）」考纲专家。下面给出 ACA 官方考纲的
全部知识点（`id 名称`，按六大模块分组）。

对每一道题输出两个字段：
1. `kp`：从清单里选**最贴近**这道题的一个知识点 id（必须逐字来自清单）。
   即使不完全吻合，也要选最接近的那个——这份题库要按知识点归档，不能留空。
2. `cover`：这道题是否**真的落在 ACA 助理级考纲范围内**。
   - "yes"：考的就是清单里那个知识点（怎么用、怎么配、怎么选、最佳实践、概念认知、安全合规）。
   - "no"：实际考的是算法/训练内部细节、工程架构与高可用、评测指标体系等
     超出 ACA 助理级考纲的内容（此时 kp 仍填最接近的那个，供人工参考）。

严格只输出 JSON：{"r":[{"i":1,"kp":"KP-3.4","cover":"yes"}]}
- i = 题号（从 1 开始，与输入一致）
- kp = 知识点 id（必填，来自清单）
- cover = "yes" 或 "no" """


def kp_menu_text(kb: dict) -> str:
    lines = []
    for mod in kb["modules"]:
        lines.append(f"【模块{mod['no']} {mod['name']}】")
        for p in mod["points"]:
            lines.append(f"{p['id']} {p['name']}")
    return "\n".join(lines)


def build_kp_msg(items: list, menu: str) -> str:
    qs = []
    for i, it in enumerate(items, 1):
        opts = " ".join(f"{k}.{t}" for k, t in it.options)
        qs.append(f"[{i}] 题干={clip(it.stem, 280)} | 选项={clip(opts, 260)}")
    return f"ACA 考纲知识点清单：\n{menu}\n\n请逐题判断覆盖情况：\n" + "\n".join(qs)


def llm_kp_batch(client, items: list, menu: str):
    resp = client.chat.completions.create(
        model=FLASH_MODEL,
        messages=[{"role": "system", "content": KP_SYS},
                  {"role": "user", "content": build_kp_msg(items, menu)}],
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
    out: list[dict] = [{} for _ in items]
    for row in (data.get("r") or []):
        try:
            i = int(row.get("i")) - 1
        except Exception:  # noqa: BLE001
            continue
        if 0 <= i < len(items):
            out[i] = {"cover": str(row.get("cover") or "").strip().lower(),
                      "kp": str(row.get("kp") or "").strip()}
    return out, usage


# =========================================================================== 成本

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


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# =========================================================================== DB

def connect() -> sqlite3.Connection:
    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=30000")
    return con


def existing_index(con: sqlite3.Connection) -> dict:
    """库内已有题：{fingerprint: (uid, status, trust_level, source_type)}。"""
    idx: dict = {}
    for r in con.execute("SELECT question_uid, stem, status, trust_level, source_type FROM questions"):
        fp = content_fingerprint(SUBJECT, r["stem"] or "")
        idx.setdefault(fp, (r["question_uid"], r["status"], r["trust_level"], r["source_type"]))
    return idx


def migrate(con: sqlite3.Connection) -> None:
    cols = {r[1] for r in con.execute("PRAGMA table_info(questions)")}
    for name in ("trust_level", "exam_title", "group_uid", "material_text"):
        if name not in cols:
            con.execute(f"ALTER TABLE questions ADD COLUMN {name} TEXT")
            print(f"  + 加字段 {name}")


# =========================================================================== main

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dump", action="store_true", help="只导出解析+分类结果到 tests/.tmp/aca_acp/")
    ap.add_argument("--cap-cny", type=float, default=1.0)
    ap.add_argument("--batch-size", type=int, default=20)
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--answerless-status", default="raw",
                    choices=["raw", "pending_review", "approved"],
                    help="无答案题（题目2/3 全文无答案）的 status")
    ap.add_argument("--refresh-llm", action="store_true",
                    help="忽略 LLM 判定缓存，重新调用（默认复用 tests/.tmp/aca_acp/llm_labels.json）")
    ap.add_argument("--kp-llm", action="store_true", default=True,
                    help="用 ACA 考纲做「覆盖闸门 + 知识点指派」（默认开）")
    ap.add_argument("--no-kp-llm", dest="kp_llm", action="store_false")
    ap.add_argument("--export-review", action="store_true",
                    help="只读：按库内 source_type='user_provided' 的行重新导出人工复核表 review.tsv")
    ap.add_argument("--kp-gate", action="store_true",
                    help="打开「超纲即改判 ACP」：LLM 判 cover=no 且规则匹配器也无命中时把 ACA 题改判 ACP"
                         "（默认关闭——实测会误伤在考纲内的题，详见脚本内注释）")
    ap.add_argument("--update-existing", action="store_true",
                    help="对已入库的同一 uid 行刷新 knowledge_point / trust_level / 分类说明（幂等重跑用）")
    args = ap.parse_args()

    TMP.mkdir(parents=True, exist_ok=True)
    kb = load_kb()
    print("=" * 78)
    print(f"ACA/ACP 用户题库入库（stage={STAGE}，上限 ¥{args.cap_cny}）")

    if args.export_review:
        export_review(kb)
        return 0

    # ---------- 1) 解析 ----------
    per_file: dict = collections.Counter()
    for name in FILES:
        p = SRC_DIR / name
        if p.exists():
            g, b = parse_file(p)
            per_file[name] = len(g)
    good, bad = parse_all()
    print(f"\n解析：共 {len(good)} 题  " + "  ".join(f"{k}={v}" for k, v in per_file.items()))
    if bad:
        print(f"剔除非题目块 {len(bad)} 个：" + " | ".join(f"{x.src.split('：')[-1]}:{clip(x.stem, 24)}" for x in bad[:6]))

    # ---------- 2) 去重 ----------
    con = connect()
    migrate(con)
    idx = existing_index(con)
    seen_fp: dict = {}
    kept: list[Q] = []
    dup_db, dup_inner = [], []
    for q in good:
        fp = content_fingerprint(SUBJECT, q.stem)
        # ① 先判「本次三个文件内部重复」——否则 --update-existing 会把它当成"刷新既有行"，
        #    再因 source_url 不同算出新 uid 而**插入一条重复题**（实测踩过这个坑）。
        if fp in seen_fp:
            dup_inner.append((q, seen_fp[fp]))
            continue
        if fp in idx:
            uid, st, tr, stype = idx[fp]
            # --update-existing：本次脚本自己插入过的行重新走一遍分类/KP，用于幂等刷新
            if args.update_existing and stype == "user_provided":
                q.update_uid = uid
                seen_fp[fp] = q.src
                kept.append(q)
                continue
            dup_db.append((q, (uid, st, tr, stype)))
            continue
        seen_fp[fp] = q.src
        kept.append(q)
    n_upd = sum(1 for q in kept if q.update_uid)
    print(f"去重：与库内已有题重复 {len(dup_db)} 题，本次三文件内部重复 {len(dup_inner)} 题，"
          f"待处理 {len(kept)} 题"
          + (f"（其中 {n_upd} 题是刷新既有行，{len(kept) - n_upd} 题新入库）" if n_upd else ""))
    if dup_db:
        for q, v in dup_db[:8]:
            print(f"   [库内重复] {clip(q.stem, 50)} → uid={v[0]} status={v[1]} trust={v[2]} src={v[3]}")

    # ---------- 2b) 解析质量自检 ----------
    issues = []
    for q in kept:
        n = len(q.options)
        if not re.search(r"[？?]", q.stem):
            issues.append(("题干无问号", q))
        if n < 3:
            issues.append((f"选项仅 {n} 个", q))
        if q.options and len(q.options[-1][1]) > 110:
            issues.append(("末选项过长（可能吞了下一题）", q))
    opt_dist = collections.Counter(len(q.options) for q in kept)
    print(f"选项数分布：{dict(sorted(opt_dist.items()))}")
    if issues:
        print(f"解析自检提示 {len(issues)} 条（供人工复核，不影响入库）：")
        for why, q in issues[:10]:
            print(f"   [{why}] {clip(q.stem, 56)}")

    # ---------- 3) 分类 ----------
    for q in kept:
        r = classify_rule(q)
        q.note = r["source"] + " " + r["why"]
        q.clabel = r["label"]
        q.csrc = r["source"]
        q.cwhy = r["why"]
    need = [q for q in kept if q.clabel is None]
    n_batches = (len(need) + args.batch_size - 1) // args.batch_size
    est = n_batches * (2200 * PRICE[FLASH_MODEL]["in"] + 700 * PRICE[FLASH_MODEL]["out"]) / 1_000_000
    rule_n = collections.Counter(q.clabel for q in kept if q.clabel)
    print(f"规则判定 {len(kept) - len(need)} 题（ACA {rule_n.get('aca', 0)} / ACP {rule_n.get('acp', 0)}）"
          f"，规则来源 {dict(collections.Counter(q.csrc for q in kept if q.clabel))}")
    print(f"需 LLM 兜底 {len(need)} 题 / {n_batches} 批（每批 {args.batch_size}），预估 ¥{est:.4f}")

    if args.dump:
        dump(kept, bad, dup_db, dup_inner, kb)
        con.close()
        return 0

    if not args.dry_run and not args.apply:
        print("未指定 --dry-run / --apply，退出。")
        con.close()
        return 0

    if args.dry_run:
        (TMP / "rule_pending.txt").write_text(
            "\n".join(f"{i:>3} [{q.src.split('：')[-1]}] {q.cwhy}\n     {clip(q.stem, 110)}"
                      for i, q in enumerate(need, 1)), encoding="utf-8")
        menu = kp_menu_text(kb)
        est_kp = ((rule_n.get("aca", 0) // args.batch_size + 1)
                  * ((len(menu) // 2 + 300 * args.batch_size) * PRICE[FLASH_MODEL]["in"]
                     + 400 * PRICE[FLASH_MODEL]["out"]) / 1_000_000)
        print(f"\n== dry-run（不写库、不发请求）==")
        print(f"  解析 {len(good)} 题 → 去重后 {len(kept)} 题"
              f"（库内重复 {len(dup_db)} / 内部重复 {len(dup_inner)} / 剔除非题目 {len(bad)}）")
        print(f"  规则已定：ACA {rule_n.get('aca', 0)} / ACP {rule_n.get('acp', 0)}")
        print(f"  待 LLM 分类：{len(need)} 题 / {n_batches} 批 → 预估 ¥{est:.4f}")
        print(f"  待 LLM 知识点指派：最多 {rule_n.get('aca', 0)} 题（ACA 侧）→ 预估 ¥{est_kp:.4f}")
        print(f"  合计预估 ¥{est + est_kp:.4f}（上限 ¥{args.cap_cny:.2f}，余额停机线 ¥{BALANCE_STOP_CNY}）")
        print(f"  待判清单已导出 tests/.tmp/aca_acp/rule_pending.txt")
        for q in kept[:4]:
            print(f"  [{q.clabel}/{q.csrc}] {clip(q.stem, 48)}")
        con.close()
        return 0

    # ---------- 3b) LLM 兜底（带缓存，可复跑不重复花钱）----------
    spent = 0.0
    cache_file = TMP / "llm_labels.json"
    cache: dict = {}
    if cache_file.exists() and not args.refresh_llm:
        try:
            cache = json.loads(cache_file.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            cache = {}
    todo: list[Q] = []
    for q in need:
        c = cache.get(content_fingerprint(SUBJECT, q.stem))
        if c and c.get("label"):
            q.clabel, q.csrc = c["label"], "llm:cache"
            q.cwhy = f"deepseek-flash 判定（缓存）kp={c.get('kp') or '-'}"
            q.llm_kp = c.get("kp") or ""
        else:
            todo.append(q)
    if todo:
        print(f"LLM 判定：缓存命中 {len(need) - len(todo)} 题，需实调 {len(todo)} 题")

    if todo and not args.no_llm:
        n_batches = (len(todo) + args.batch_size - 1) // args.batch_size
        est = n_batches * (2200 * PRICE[FLASH_MODEL]["in"] + 700 * PRICE[FLASH_MODEL]["out"]) / 1_000_000
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
        from openai import OpenAI
        env = load_env()
        client = OpenAI(api_key=env["DEEPSEEK_API_KEY"],
                        base_url=env.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"), timeout=180)
        kp_menu = [p["id"] for p in kb["points"]]
        t0 = time.time()
        for bi in range(n_batches):
            batch = todo[bi * args.batch_size:(bi + 1) * args.batch_size]
            got, usage = [{} for _ in batch], {}
            for attempt in (1, 2):
                try:
                    got, usage = llm_sort_batch(client, batch, kp_menu)
                    if usage:
                        c = cost_of(FLASH_MODEL, usage)
                        spent += c
                        log_ledger({"ts": now_iso(), "stage": STAGE, "kind": "llm_call", "model": FLASH_MODEL,
                                    "usage": usage, "cost_cny": round(c, 6),
                                    "note": f"batch {bi + 1}/{n_batches} n={len(batch)} attempt={attempt}"})
                    break
                except Exception as e:  # noqa: BLE001
                    log_ledger({"ts": now_iso(), "stage": STAGE, "kind": "llm_error", "model": FLASH_MODEL,
                                "note": f"batch {bi + 1} attempt={attempt}: {type(e).__name__}: {str(e)[:180]}"})
                    if attempt == 2:
                        got = [{} for _ in batch]
            for q, g in zip(batch, got):
                if g.get("label"):
                    q.clabel, q.csrc = g["label"], "llm"
                    q.cwhy = f"deepseek-flash 判定 kp={g.get('kp') or '-'}"
                    q.llm_kp = g.get("kp") or ""
                    cache[content_fingerprint(SUBJECT, q.stem)] = {"label": g["label"], "kp": q.llm_kp}
            cache_file.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"  [batch {bi + 1}/{n_batches}] 已花 ¥{spent:.4f}  ({time.time() - t0:.0f}s)")
            if spent > args.cap_cny:
                print(f"⚠️ 累计 ¥{spent:.4f} 超上限，停止 LLM 阶段")
                break
            nb = balance_cny()
            if nb is not None and nb < BALANCE_STOP_CNY:
                print(f"⚠️ 余额 ¥{nb:.2f} 低于停机线，停止 LLM 阶段")
                break

    # 兜底：LLM 也未判出的按“宁可 ACP”处理
    for q in kept:
        if q.clabel is None:
            q.clabel = "acp"
            q.csrc = q.csrc + "+fallback"
            q.cwhy = q.cwhy + " → 判不准，按用户口径归 ACP"

    # ---------- 3c) ACA 题的「考纲覆盖闸门 + 知识点指派」----------
    # 规则判为 ACA 的题必须真的落在某个 ACA 知识点上；落不到 → 按用户口径归 ACP。
    aca_qs = [q for q in kept if q.clabel == "aca"]
    kp_final: dict = {}
    kp_src: dict = {}
    kp_cache_file = TMP / "kp_labels.json"
    kp_cache: dict = {}
    if kp_cache_file.exists() and not args.refresh_llm:
        try:
            kp_cache = json.loads(kp_cache_file.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            kp_cache = {}
    todo_kp = []
    for q in aca_qs:
        c = kp_cache.get(content_fingerprint(SUBJECT, q.stem))
        if c is None:
            todo_kp.append(q)
        else:
            kp_final[id(q)] = c.get("kp") or ""
            kp_src[id(q)] = c.get("src") or "llm:cache"
    if todo_kp and args.kp_llm and not args.no_llm:
        nkb = (len(todo_kp) + args.batch_size - 1) // args.batch_size
        menu = kp_menu_text(kb)
        est_kp = nkb * ((len(menu) // 2 + 300 * args.batch_size) * PRICE[FLASH_MODEL]["in"]
                        + 400 * PRICE[FLASH_MODEL]["out"]) / 1_000_000
        print(f"KP 指派：缓存命中 {len(aca_qs) - len(todo_kp)} 题，需实调 {len(todo_kp)} 题 / "
              f"{nkb} 批，预估 ¥{est_kp:.4f}")
        if spent + est_kp > args.cap_cny:
            print(f"⚠️ 预估累计 ¥{spent + est_kp:.4f} 超上限 ¥{args.cap_cny:.2f}，跳过 KP 指派（用规则兜底）")
            todo_kp = []
        else:
            from openai import OpenAI
            env = load_env()
            client = OpenAI(api_key=env["DEEPSEEK_API_KEY"],
                            base_url=env.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"), timeout=180)
            for bi in range(nkb):
                batch = todo_kp[bi * args.batch_size:(bi + 1) * args.batch_size]
                got, usage = [{} for _ in batch], {}
                for attempt in (1, 2):
                    try:
                        got, usage = llm_kp_batch(client, batch, menu)
                        if usage:
                            c = cost_of(FLASH_MODEL, usage)
                            spent += c
                            log_ledger({"ts": now_iso(), "stage": STAGE, "kind": "llm_call",
                                        "model": FLASH_MODEL, "usage": usage, "cost_cny": round(c, 6),
                                        "note": f"kp batch {bi + 1}/{nkb} n={len(batch)} attempt={attempt}"})
                        break
                    except Exception as e:  # noqa: BLE001
                        log_ledger({"ts": now_iso(), "stage": STAGE, "kind": "llm_error",
                                    "model": FLASH_MODEL,
                                    "note": f"kp batch {bi + 1} attempt={attempt}: {type(e).__name__}: {str(e)[:180]}"})
                        if attempt == 2:
                            got = [{} for _ in batch]
                for q, g in zip(batch, got):
                    kp = g.get("kp") or ""
                    ok = kp in kb["by_id"]
                    kp_final[id(q)] = kp if ok else ""
                    cover = g.get("cover") or ""
                    kp_src[id(q)] = ("llm-kp" if ok else "llm-badid") + ("" if cover == "yes" else "|低覆盖")
                    kp_cache[content_fingerprint(SUBJECT, q.stem)] = {
                        "kp": kp_final[id(q)], "src": kp_src[id(q)], "cover": cover}
                kp_cache_file.write_text(json.dumps(kp_cache, ensure_ascii=False, indent=1), encoding="utf-8")
                print(f"  [kp batch {bi + 1}/{nkb}] 累计花费 ¥{spent:.4f}")
                if spent > args.cap_cny:
                    print(f"⚠️ 累计 ¥{spent:.4f} 超上限，停止 KP 指派")
                    break
    # 规则兜底 + 可选闸门
    # 默认**不改判**：classification 由规则 + LLM 分类（见上文）定，KP 只在 ACA 内部指派。
    # `--kp-gate` 打开「超纲即改判」策略：LLM 判 cover=no **且**规则匹配器也找不到知识点时改判 ACP。
    # ⚠️ 实测（2026-10-12）：只信 LLM 一把钥匙时它会误伤（把「BatchAPI 成本优化」「微调资源考量」
    #    「提示词分隔符」「文本合规检测」这类**确实在 ACA 考纲里**的题判成超纲），故默认关闭。
    n_gate = n_rule_kp = n_fallback = 0
    for q in aca_qs:
        if kp_final.get(id(q)):
            if kp_src.get(id(q), "").endswith("|低覆盖"):
                q.cwhy += "（LLM 标注：可能超出 ACA 考纲）"
            continue
        kp, hit = pick_aca_kp(kb, q, None)
        if kp:
            kp_final[id(q)] = kp
            kp_src[id(q)] = f"rule-kp:{hit}"
            n_rule_kp += 1
        elif args.kp_gate:
            q.clabel = "acp"
            q.csrc = (q.csrc + "+kp-gate")
            q.cwhy += " → ACA 考纲未覆盖（LLM 判超纲且规则匹配器无命中），按用户口径归 ACP"
            kp_src[id(q)] = "gate→acp"
            n_gate += 1
        else:
            kp_final[id(q)] = kp_label(kb, "KP-1.26")   # 兜底：ACA 进阶路径（认知类）
            kp_src[id(q)] = "fallback-kp"
            n_fallback += 1
    print(f"KP 兜底/闸门：规则匹配器补 {n_rule_kp} 题；"
          + (f"闸门改判 ACP {n_gate} 题；" if args.kp_gate else f"兜底知识点 {n_fallback} 题；")
          + f"ACA 剩 {sum(1 for q in kept if q.clabel == 'aca')} 题")
    print(f"实际 LLM 花费（含 KP 指派）¥{spent:.4f}")

    # ---------- 4) 知识点 ----------
    final: dict = {}
    for q in kept:
        if q.clabel == "aca":
            kp = kp_final.get(id(q)) or kp_label(kb, "KP-1.23")
            final[id(q)] = (kp, kp_src.get(id(q), "rule"))
        else:
            final[id(q)] = (pick_acp_topic(q), "ACP 主题表")

    print("\n分类结果：" + str(dict(collections.Counter(q.clabel for q in kept))))
    print("判定来源：" + str(dict(collections.Counter(q.csrc.split(":")[0] for q in kept))))
    print("KP 来源：" + str(dict(collections.Counter(v.split(":")[0] for v in kp_src.values()))))

    # ---------- 5) 入库 ----------
    ins = upd = 0
    for q in kept:
        src_url = q.src
        uid = generate_uid(SUBJECT, src_url, q.stem)
        kp, _ = final[id(q)]
        answer = q.answer or ""
        status = "approved" if answer else args.answerless_status
        trust = "third_party" if q.clabel == "aca" else "acp"
        opts = json.dumps([{"label": k, "text": t} for k, t in q.options], ensure_ascii=False)
        claim = f"用户提供题库文件 {q.src.split('：')[-1]}，规则/LLM 分类为 {q.clabel.upper()}"
        n = 0
        if q.update_uid:
            # 已知库内已有同一题（fingerprint 命中）→ 只刷新，绝不新建
            upd += 1 if con.execute(
                """UPDATE questions SET knowledge_point=?, trust_level=?, explanation=?, fact_claim=?
                   WHERE question_uid=? AND source_type='user_provided'""",
                (kp, trust, "，".join(q.tags), claim, q.update_uid)).rowcount else 0
        else:
            n = con.execute(
                """INSERT OR IGNORE INTO questions
                   (question_uid, subject, source_type, source_url, source_credit, question_type, stem,
                    options, answer, explanation, knowledge_point, difficulty, status, version,
                    fact_claim, fact_source, fact_verified, trust_level, exam_title)
                   VALUES (?,?,'user_provided',?,?,?,?,?,?,?,?,?,?,1,?,?,0,?,?)""",
                (uid, SUBJECT, src_url, f"用户提供：{EXAM_TITLE}", q.qtype, q.stem, opts, answer,
                 "，".join(q.tags), kp, "中", status, claim,
                 q.src, trust, EXAM_TITLE),
            ).rowcount
            ins += 1 if n else 0
    con.commit()
    print(f"\n入库 {ins} 题（INSERT OR IGNORE），刷新既有行 {upd} 题"
          f"{'' if args.update_existing else '（未加 --update-existing，已存在的行未刷新）'}")
    print("库内 trust_level × status：")
    total = 0
    for row in con.execute("SELECT trust_level, status, count(*) FROM questions GROUP BY 1,2 ORDER BY 1,2"):
        print(f"    {str(row[0]):<14}{str(row[1]):<14}{row[2]}")
        total += row[2]
    print(f"    {'合计':<28}{total}")
    for row in con.execute("SELECT count(*) FROM questions WHERE source_type='user_provided'"):
        print(f"  本次 source_type='user_provided' 合计 {row[0]} 题")
    con.close()
    dump(kept, bad, dup_db, dup_inner, kb, final)
    return 0


def export_review(kb: dict) -> None:
    """只读导出：把库内 user_provided 的题按当前分类/KP 重新写成人可复核的 TSV。

    判定依据分两段：① 库内 `fact_claim`（当初的 ACA/ACP 结论）；② 用 `classify_rule()`
    对题干**重算**的规则证据（确定性，重跑结果一致），便于用户核对"为什么判成这一类"。
    """
    TMP.mkdir(parents=True, exist_ok=True)
    con = connect()
    rows = list(con.execute(
        "SELECT question_uid, source_url, stem, options, answer, question_type, knowledge_point,"
        " trust_level, status, explanation, fact_claim FROM questions"
        " WHERE source_type='user_provided' ORDER BY id"))
    tsv = ["来源文件\t序号\t分类\t判定来源\t知识点\t答案\t题型\t判定依据\t题干"]
    cnt = collections.Counter()
    for i, r in enumerate(rows, 1):
        q = Q(r["stem"], r["source_url"], i)
        q.options = [(o.get("label", ""), o.get("text", "")) for o in json.loads(r["options"] or "[]")]
        q.tags = [t.strip() for t in (r["explanation"] or "").split("，") if t.strip()]
        rule = classify_rule(q)
        label = "aca" if r["trust_level"] == "third_party" else "acp"
        cnt[label] += 1
        why = f"{r['fact_claim'] or ''} ‖ 规则复算：{rule['source']} {rule['why']}（规则结果={rule['label'] or '交LLM'}）"
        tsv.append("\t".join(x.replace("\t", " ") for x in (
            r["source_url"].split("：")[-1], str(i), label, r["trust_level"], r["knowledge_point"] or "",
            r["answer"] or "", r["question_type"], why, clip(r["stem"], 300))))
    out = TMP / "review.tsv"
    out.write_text("\n".join(tsv), encoding="utf-8")
    tsv_out = ROOT / "logs" / "aca_acp_review.tsv"
    tsv_out.write_text("\n".join(tsv), encoding="utf-8")
    print(f"导出人工复核表：{out} / {tsv_out}（{len(rows)} 题，{dict(cnt)}）")
    for row in con.execute("SELECT trust_level, status, count(*) FROM questions"
                           " WHERE source_type='user_provided' GROUP BY 1,2 ORDER BY 1,2"):
        print("   ", tuple(row))
    con.close()


def pick_acp_topic(q: Q) -> str:
    """ACP 主题标签：按固定主题表匹配（可读、可统计），命中不了才兜底。"""
    hay = q.stem + " " + "，".join(q.tags) + " " + " ".join(t for _, t in q.options)
    for pat, topic in ACP_TOPICS:
        if re.search(pat, hay, re.I):
            return topic
    return "ACP-大模型原理与工程"


# ACP 主题表：顺序敏感（先匹配到的先用）
ACP_TOPICS: list[tuple[str, str]] = [
    (r"自注意力|多头注意力|注意力机制|位置编码|层归一化|残差连接|Transformer",
     "ACP-Transformer 内部机制"),
    (r"LoRA|QLoRA|PEFT|Adapter|Prefix\s*Tuning|Prompt\s*Tuning|低秩",
     "ACP-参数高效微调原理"),
    (r"(?<!向)量化|蒸馏|剪枝|模型压缩", "ACP-模型压缩"),
    (r"分布式训练|数据并行|模型并行|流水线并行|参数服务器", "ACP-分布式训练"),
    (r"RLHF|人类反馈|奖励模型|偏好对齐", "ACP-对齐原理（RLHF/DPO）"),
    (r"梯度下降|学习率|过拟合|欠拟合|早停|early\s*stopping|模型收敛|训练损失|验证损失|"
     r"损失函数|batch\s*size|批量大小|迭代次数|epoch|训练循环|训练参数", "ACP-训练算法与调参"),
    (r"分词化|tokeni[sz]|padding|统一长度|词表|拆分成单词|词汇单元|分词", "ACP-文本预处理原理"),
    (r"逻辑回归|支持向量机|SVM|决策树|随机森林|K-means|聚类算法|混淆矩阵|AUC|ROC|F1",
     "ACP-机器学习算法原理"),
    (r"底层原理|内部机制|算法原理", "ACP-模型内部机制"),
    (r"多模态.{0,6}原理|原理.{0,6}多模态", "ACP-多模态原理"),
    (r"context\s*precision|context\s*recall|Answer\s*Correctness|RAGAS|Ragas|ragas|"
     r"评测集|自动化评测|评测机制|评测的?可信度|GSB", "ACP-RAG 评测体系"),
    (r"rerank|重排序|重排|RRF|倒数排名融合|混合检索|多路召回|精排|粗排",
     "ACP-检索调优与重排"),
    (r"余弦相似度|相似度计算|内积|距离度量|相似度阈值|向量相似度", "ACP-向量相似度计算"),
    (r"向量数据库|Milvus|Qdrant|Faiss|HNSW|ANN|近似最近邻|向量存储|索引结构|向量检索服务|"
     r"高可用|7x24|7×24|容灾|水平扩展|数百万|百万级", "ACP-向量数据库高可用选型"),
    (r"检索准确度|检索不准确|检索效率|低相关|相关度很低|过滤掉低相关", "ACP-检索质量调优"),
    (r"推理加速|显存|模型部署|服务化|吞吐|QPS|响应时间低于|延迟低于", "ACP-推理加速与部署"),
    (r"如何影响.{0,10}(Token|候选|筛选|概率)|温度参数|采样策略", "ACP-采样解码机制"),
    (r"微调的训练|训练目标|预训练目标|自监督", "ACP-训练目标与实现"),
]


def dump(kept: list, bad: list, dup_db: list, dup_inner: list, kb: dict, final: dict | None = None) -> None:
    final = final or {}
    out = TMP / "parsed.json"
    out.write_text(json.dumps({
        "kept": [dict(q.to_dict(), kp=(final.get(id(q)) or ("", ""))[0]) for q in kept],
        "rejected_blocks": [q.to_dict() for q in bad],
        "dup_in_db": [{"stem": q.stem, "src": q.src, "hit": list(v)} for q, v in dup_db],
        "dup_inner": [{"stem": q.stem, "src": q.src, "first": v} for q, v in dup_inner],
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    lines = []
    for i, q in enumerate(kept, 1):
        kp = (final.get(id(q)) or ("", ""))[0]
        lines.append(f"{i}\t[{q.clabel}|{q.csrc}|{q.qtype}|ans={q.answer or '-'}|kp={kp}|"
                     f"tags={'，'.join(q.tags) or '-'}]\t{clip(q.stem, 120)}")
        for k, t in q.options:
            lines.append(f"\t{k}. {clip(t, 100)}")
        lines.append(f"\tWHY: {q.cwhy}")
    (TMP / "parsed.txt").write_text("\n".join(lines), encoding="utf-8")
    # 便于用户人工复核/改判的 TSV（含来源文件、原题号、判定依据）
    tsv = ["来源文件\t序号\t分类\t判定来源\t知识点\t答案\t题型\t判定依据\t题干"]
    for i, q in enumerate(kept, 1):
        kp = (final.get(id(q)) or ("", ""))[0]
        tsv.append("\t".join(x.replace("\t", " ") for x in (
            q.src.split("：")[-1], str(i), q.clabel or "", q.csrc, kp, q.answer or "",
            q.qtype, q.cwhy, clip(q.stem, 300))))
    (TMP / "review.tsv").write_text("\n".join(tsv), encoding="utf-8")
    print(f"已导出 {out} / {TMP / 'parsed.txt'} / {TMP / 'review.tsv'}")


if __name__ == "__main__":
    raise SystemExit(main())
