#!/usr/bin/env python
"""按**官方考纲 V2.4** 出一套完整 ACA 模拟卷（50 题 / 100 分）并写进题库。

与旧版（20 题）的差别 —— 用户反馈三条，逐条对治：

1. **知识点分数占比**：旧版只在模块级按 18/20/22/12/16/12 分题，**模块内部不分**，
   于是 9 道「大模型概念」可能 5 道都在问幻觉。新版从
   `inbox/aca_llm/aca_v24_knowledge_points.md` 解析出 **35 条具体知识点**，
   在模块内**轮转分配**（单选/多选错开），每题 prompt 只指定一条，保证铺开。

2. **题型占比 + 不混杂**：官方 = 单选 35 + 多选 15。新版**先插完 35 道单选、
   再插 15 道多选**（同一事务、顺序插入），所以 `ORDER BY id` 就是卷面顺序：
   第 1–35 题单选、第 36–50 题多选，`/api/paper` 的 `seq` 天然分段。
   （旧版是按模块交替插 single/multi，套卷页看到的就是"单-单-多-单…"）

3. **"怎么全是微调"**：微调只占 12%（6 题），用户看到的多是**干扰项**里的微调。
   新版在 prompt 里加了两条硬约束：
   - 考点**不是**微调时：至多一个干扰项可以是"用企业数据微调/再训练"；
   - 四个选项的**错误类型必须各不相同**（选型错 / 环节错位 / 顺序颠倒 / 过度投入）。
   同时给每题分配不同行业，避免 50 题长得一样。

成本（RAG 优先，不塞整本书）：
  每题上下文 = 备考指南 500 字（按模块缓存，只查一次）+ RAG 检索 2×350 字
  + 官方样题 400 字 + 指令 ≈ 1,400 token；输出 ≈ 350 token。
  flash 单价 ¥4.4/¥17.3 每 1M → 约 ¥0.012/题，50 题 ≈ ¥0.6（并发 4）。

用法:
    python scripts/generate_mock_paper.py --paper "AI模拟卷·ACA-全真50题"            # dry-run
    python scripts/generate_mock_paper.py --paper "..." --apply --cap-cny 1.2
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
LOGS = ROOT / "logs"
OUT = ROOT / "output"
ENV_FILE = ROOT / ".env"
KMD = ROOT / "inbox" / "aca_llm" / "aca_v24_knowledge_points.md"
sys.path.insert(0, str(ROOT / "scripts"))
import kb  # noqa: E402
try:
    from lib.uid import generate_uid  # noqa: E402
except Exception:  # noqa: BLE001
    generate_uid = None

SUBJECT = "aca_llm"
MODEL_DEFAULT = "deepseek-flash"
PRICE = {"in": 4.4, "out": 17.3}      # CNY / 1M（保守含峰时上浮）

# 官方考纲 V2.4：六大模块权重 + 对应知识库里的备考指南节点
MODULES = [
    dict(no=1, label="大模型概念", pct=0.18, guide="考点·大模型概念"),
    dict(no=2, label="提示词工程", pct=0.20, guide="考点·提示词工程"),
    dict(no=3, label="增强大模型应用的能力", pct=0.22, guide="考点·增强大模型应用的能力"),
    dict(no=4, label="大模型微调", pct=0.12, guide="考点·大模型微调"),
    dict(no=5, label="大模型 Agent", pct=0.16, guide="考点·大模型 Agent"),
    dict(no=6, label="安全合规", pct=0.12, guide="考点·安全合规"),
]
FINE = "大模型微调"      # 只有这个模块的"正确答案"才是微调

# 行业池：每题轮换一个，避免 50 道题都是同一类现场
INDUSTRIES = [
    "三甲医院门诊", "汽车零部件制造", "区县政务大厅", "职业院校教务", "城市商业银行",
    "连锁零售门店", "第三方物流仓储", "新能源电站运维", "农业合作社", "地方电视台",
    "建筑施工总包", "电信运营商营业厅", "律师事务所", "保险公司理赔", "药品流通企业",
    "在线教育机构",
]

SYS = (
    "你是阿里云大模型工程师 ACA 认证的资深出题人。只输出 JSON。\n"
    "硬性要求：\n"
    "1. 只考**概念辨析与场景判断**，不考技术实现细节、不写代码、不问参数数值；\n"
    "2. 题干先给具体业务现场（角色 + 任务 + 现象），再问「哪种方案最合适/更有效」；\n"
    "3. 干扰项必须是**真实存在但用错场景的手段**（词频分类/正则匹配/重新预训练/加大参数/"
    "看损失收敛/提高温度 等），不得是明显离谱的胡编项；\n"
    "4. 单选 4 选 1；多选 4 选 2~3；\n"
    "5. 解析 80~150 字，**逐项**说明对错原因，并点出对应考点的哪条考法；\n"
    '6. JSON 结构：{"q":{"stem":"","options":["A. …","B. …","C. …","D. …"],'
    '"answer":"B","explanation":""}}'
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_env() -> dict[str, str]:
    out: dict[str, str] = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def allocate(total: int, weights: list[float]) -> list[int]:
    """按权重把 total 题分配到各模块（最大余额法）。"""
    raw = [total * w for w in weights]
    base = [int(x) for x in raw]
    rest = total - sum(base)
    order = sorted(range(len(raw)), key=lambda i: raw[i] - base[i], reverse=True)
    for i in order[:rest]:
        base[i] += 1
    return base


def load_fine_points() -> dict[int, list[tuple[str, str, str]]]:
    """从考纲知识点 md 解析出 {模块号: [(编号, 知识点, 考纲依据), …]}。"""
    if not KMD.exists():
        return {}
    text = KMD.read_text(encoding="utf-8")
    out: dict[int, list[tuple[str, str, str]]] = {}
    module = 0
    for line in text.splitlines():
        m = re.match(r"^##\s*模块\s*(\d+)", line)
        if m:
            module = int(m.group(1))
            continue
        m = re.match(r"^\|\s*(\d+\.\d+)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*$", line)
        if m and module:
            name = re.sub(r"\*\*", "", m.group(2)).strip()
            basis = re.sub(r"\*\*", "", m.group(3)).strip()
            out.setdefault(module, []).append((m.group(1), name, basis))
    return out


class GuideCache:
    """备考指南按模块只查一次库（旧版每题都查一次）。"""

    def __init__(self, limit: int = 500):
        self.limit = limit
        self._cache: dict[str, str] = {}
        self._lock = threading.Lock()

    def get(self, kp_name: str) -> str:
        with self._lock:
            if kp_name in self._cache:
                return self._cache[kp_name]
        conn = kb.open_db(SUBJECT)
        try:
            rows = conn.execute(
                "SELECT c.text FROM kp k JOIN kp_chunk kc ON kc.kp_id=k.id "
                "JOIN chunks c ON c.id=kc.chunk_id JOIN docs d ON d.id=c.doc_id "
                "WHERE k.name=? AND d.kind='guide' ORDER BY c.id", (kp_name,)).fetchall()
            text = "\n".join(r["text"] for r in rows)[: self.limit]
        finally:
            conn.close()
        with self._lock:
            self._cache[kp_name] = text
        return text


def rag_context(query: str, k: int = 2, limit: int = 350) -> list[dict]:
    return [dict(c, text=str(c.get("text") or "")[:limit]) for c in kb.search(SUBJECT, query, k)]


def validate(q: dict, qtype: str) -> tuple[bool, str]:
    stem = str(q.get("stem") or "").strip()
    opts = [str(o).strip() for o in (q.get("options") or [])]
    ans = re.sub(r"[^A-H]", "", str(q.get("answer") or "").upper())
    expl = str(q.get("explanation") or "").strip()
    if len(stem) < 25:
        return False, "题干太短"
    if len(opts) != 4:
        return False, f"选项数 {len(opts)}"
    keys = []
    for i, o in enumerate(opts):
        m = re.match(r"^([A-H])\s*[.、)．]\s*(.+)$", o)
        if not m:
            return False, f"选项 {i + 1} 缺字母前缀"
        if m.group(1) != "ABCD"[i]:
            return False, f"选项 {i + 1} 字母不连续"
        if len(m.group(2).strip()) < 4:
            return False, f"选项 {i + 1} 太短"
        keys.append(m.group(2).strip())
    if len(set(keys)) != 4:
        return False, "选项重复"
    if not ans or any(c not in "ABCD" for c in ans):
        return False, f"答案不合法 {ans!r}"
    if qtype == "single_choice" and len(ans) != 1:
        return False, "单选题答案多于 1 个"
    if qtype == "multiple_choice" and not (2 <= len(ans) <= 3):
        return False, "多选题答案应是 2~3 个"
    if len(expl) < 60:
        return False, "解析太短"
    return True, "ok"


def norm(s: str) -> str:
    return re.sub(r"[\s\u3000，。、；：？！“”‘’（）()【】\[\]《》,.;:?!\"'*]+", "", s or "")


def ngrams(s: str, n: int = 4) -> set[str]:
    t = norm(s)
    return {t[i:i + n] for i in range(max(0, len(t) - n + 1))}


def similarity(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / max(1, len(a | b))


def call(client, model: str, reasoning: str, user: str) -> tuple[dict, dict]:
    kw = dict(model=model,
              messages=[{"role": "system", "content": SYS}, {"role": "user", "content": user}],
              response_format={"type": "json_object"}, temperature=0.55)
    if reasoning:
        kw["reasoning_effort"] = reasoning
    resp = client.chat.completions.create(**kw)
    usage = resp.usage.model_dump() if getattr(resp, "usage", None) else {}
    try:
        data = json.loads(resp.choices[0].message.content or "{}")
    except Exception:  # noqa: BLE001
        data = {}
    q = data.get("q") or data
    return (q if isinstance(q, dict) else {}), usage


# 各模块**专门的**错误方向（干扰项素材）。写死在脚本里，是为了让 50 题的干扰项不重样：
# 用户反馈"怎么全是微调"——根因不是题数配比（微调只有 6 题/12%），而是**别的模块拿微调当
# 万能干扰项**，导致考生一看到"微调"就能排除。所以除微调模块外一律禁用微调类提法。
DISTRACT = {
    1: "指望模型记住企业内部事实 / 加大参数或换更大模型就能解决 / 把温度调到最高让模型自由发挥 / "
       "用关键词模板取代语言组织 / 认为模型可以替人做最终决定",
    2: "堆砌关键词与修饰语 / 把关键约束写在最后一句 / 不给示例靠多轮试错 / 只换模型不改提示词 / "
       "用态度词代替明确约束 / 一次要求七八件事",
    3: "RAG 环节错位（解析 / 切分 / 检索 / 重排序 / 评测做错一环） / 把需要实时变化的数据当静态知识 / "
       "用正则关键词抽取代替语义检索 / 不做评测直接上线",
    5: "不给工具边界 / 不设阶段检查点 / 让 Agent 自主决定高风险动作 / 把 Skill 当成知识库 / "
       "只给目标不给资料来源",
    6: "只做关键词过滤就当合规 / 生成内容不标识 / 来源与日志不留存 / 高风险场景免人工复核 / "
       "权限一律放开图省事",
}
FINE_WORDS = "微调 / 重新训练 / 再训练 / 预训练 / 用企业数据继续训练"


def distractor_rule(label: str, module_no: int) -> str:
    """按模块给干扰项方向；非微调模块**禁止**出现微调类提法。"""
    if module_no == 4:
        return ("本题考的就是微调：正确项应是「该场景适合/需要用微调」，"
                "错误项要体现「本该用 RAG / 工具 / 提示词却上了微调」或「微调流程里某一步做错」。")
    if module_no == 3:
        return (f"本模块可以有一项提到「{FINE_WORDS}」，因为 RAG 与微调的选型对比是本模块必考点；"
                f"但**最多一个**，其余干扰项用本模块的错误方向：{DISTRACT[3]}")
    return (f"⛔ **四个选项里不得出现「{FINE_WORDS}」这类提法**（本卷微调只占 12%，"
            f"若每题都摆一个微调选项，考生一看到微调就能排除，题就废了）。"
            f"请改用本模块专属的错误方向：{DISTRACT.get(module_no, '选错手段 / 环节错位 / 顺序颠倒 / 过度投入')}。")


def assign_answers(plan: list[dict], seed: int = 20261024) -> None:
    """给每题**指定**答案位置，避免"答案总在 A"（纯机械分配，不花模型钱）。

    单选：A/B/C/D 均分后打散（35 题 → 9/9/9/8）；
    多选：1/3 的题用 3 个正确项（15 题 → 5 个三选 + 10 个双选），正确组合从池里轮取再打散。
    """
    import random
    rnd = random.Random(seed)
    singles = [it for it in plan if it["qtype"] == "single_choice"]
    multis = [it for it in plan if it["qtype"] == "multiple_choice"]

    letters: list[str] = []
    while len(letters) < len(singles):
        letters += list("ABCD")
    letters = letters[: len(singles)]
    rnd.shuffle(letters)
    for it, letter in zip(singles, letters):
        it["answer"] = letter

    two = ["AB", "AC", "AD", "BC", "BD", "CD"]
    three = ["ABC", "ABD", "ACD", "BCD"]
    n_three = max(1, round(len(multis) / 3)) if multis else 0
    pool = ([rnd.choice(three) for _ in range(n_three)]
            + [rnd.choice(two) for _ in range(max(0, len(multis) - n_three))])
    rnd.shuffle(pool)
    for it, ans in zip(multis, pool):
        it["answer"] = ans


def answer_hint(answer: str) -> str:
    """把"指定答案"翻译成一句可执行的排布要求。"""
    if len(answer) == 1:
        return (f"本题**正确答案固定在 {answer}**：请把最符合考法的那一项放在 {answer}，"
                f"另外三项放干扰项。**不要**为了凑位置把 {answer} 写成明显正确、把干扰项写得敷衍——"
                "干扰项仍要让考生需要辨析。")
    others = [x for x in "ABCD" if x not in answer]
    return (f"本题**正确项固定为 {answer}（共 {len(answer)} 项）**，"
            f"{''.join(others)} 必须全部是错误项。正确项之间不互斥、不包含关系；"
            f"错误项各自错在不同点（选型错 / 环节错位 / 顺序颠倒 / 过度投入）。")


def build_prompt(paper: str, seq: int, total: int, label: str, pct: float, fp: tuple[str, str, str],
                 qtype_cn: str, module_count: int, industry: str, guide: str, ctx: list[dict],
                 sample: str, avoid: str, answer: str = "", item_module_no: int = 1) -> str:
    rag = "\n".join(f"- 【{c['title']}】{c['text']}" for c in ctx)
    kp_id, kp_name, kp_basis = fp
    return f"""【试卷】{paper}　第 {seq}/{total} 题（{qtype_cn}题，每题 2 分）
【模块】{label}　考纲权重 {pct:.0%}　本卷该模块共 {module_count} 题
【本题指定的知识点】{kp_id} {kp_name}
【考纲原文依据】{kp_basis}

【官方备考指南·该模块要点（节选）】
{guide}

【知识库检索材料（RAG）】
{rag or '（无额外材料，按考纲与指南即可）'}

【官方样题风格（只学句式与难度，不要照抄场景/行业）】
{sample[:400]}

【本题场景行业】{industry}（必须用这个行业，且业务动词要具体）

【本卷已出的题干（禁止重复或改写）】
{avoid or '（暂无）'}

【答案位置（硬约束，必须照做）】
{answer_hint(answer) if answer else '正确答案位置随机。'}

【硬性要求】
1. 只考知识点 {kp_id}「{kp_name}」，四个选项都围绕它设计，不要跑题到同模块其他小节；
2. 题干先给具体业务现场（角色 + 任务 + 现象），再问「哪种做法最合适/最有效」；
3. 四个选项的**错误类型必须各不相同**（选型错 / 环节错位 / 顺序颠倒 / 过度投入），不得两项同义；
   {distractor_rule(label, item_module_no)}
4. 解析 80~150 字，逐项说明对错（用选项字母指代），并点明依据考纲该模块的哪条考法；
5. `answer` 字段必须正好等于上面指定的答案。

只输出 JSON：{{"q":{{"stem":"…","options":["A. …","B. …","C. …","D. …"],"answer":"{answer or 'B'}","explanation":"…"}}}}"""


def fetch_samples() -> tuple[str, str]:
    """官方模拟题里的 1 道单选 + 1 道多选，作风格锚点。"""
    p = ROOT / "inbox" / "aca_llm" / "official_mock_20.md"
    if not p.exists():
        return "", ""
    text = p.read_text(encoding="utf-8")
    s = re.search(r"## 2【单选】.*?(?=\n## )", text, re.S)
    m = re.search(r"## 18【多选】.*?(?=\n## )", text, re.S)
    return (s.group(0)[:700] if s else ""), (m.group(0)[:900] if m else "")


def export_markdown(path: Path, paper: str, made: list[dict]) -> None:
    """导出离线答案册：卷面顺序 + 每题考点/答案/解析 + 分布表。"""
    by_mod: dict[str, int] = {}
    for q in made:
        by_mod[q["kp"]] = by_mod.get(q["kp"], 0) + 1
    singles = sum(1 for q in made if q["question_type"] == "single_choice")
    lines = [f"# {paper}", "",
             f"> AI 生成（知识库增强）· 共 {len(made)} 题 · 单选 {singles} + 多选 {len(made) - singles} · 每题 2 分 · 满分 {len(made) * 2} 分",
             "", "## 知识点分布（对照考纲 V2.4）", "",
             "| 模块 | 考纲权重 | 本卷题数 | 本卷占比 |", "|---|---|---|---|"]
    for m in MODULES:
        n = by_mod.get(m["label"], 0)
        lines.append(f"| {m['label']} | {m['pct']:.0%} | {n} | {n / max(1, len(made)):.0%} |")
    lines += ["", "## 试题与答案", ""]
    for i, q in enumerate(made, 1):
        lines.append(f"### 第 {i} 题（{'单选' if q['question_type'] == 'single_choice' else '多选'}）"
                     f"　考点：{q['kp']} · {q['fine_id']} {q['fine_name']}")
        lines += ["", q["stem"].strip(), ""]
        lines += [f"- {o.strip()}" for o in q["options"]]
        lines += ["", f"**答案**：{q['answer']}　", "",
                  f"**解析**：{q['explanation'].strip()}", ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="按官方考纲比例生成完整 ACA 模拟卷并入库")
    ap.add_argument("--paper", required=True, help="卷名（写入 exam_title）")
    ap.add_argument("--singles", type=int, default=35, help="单选题数（官方 35）")
    ap.add_argument("--multiples", type=int, default=15, help="多选题数（官方 15）")
    ap.add_argument("--model", default=MODEL_DEFAULT)
    ap.add_argument("--reasoning", default="none")
    ap.add_argument("--workers", type=int, default=4, help="并发数（4 约 4 分钟出 50 题）")
    ap.add_argument("--cap-cny", type=float, default=1.2)
    ap.add_argument("--export-md", default="", help="导出答案册路径（默认 output/<卷名>.md）")
    ap.add_argument("--replace", action="store_true",
                    help="同名卷已存在时先删掉旧题再写（重出同一套卷用）")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    weights = [m["pct"] for m in MODULES]
    alloc_s = allocate(args.singles, weights)
    alloc_m = allocate(args.multiples, weights)
    alloc_t = allocate(args.singles + args.multiples, weights)
    fine = load_fine_points()

    plan: list[dict] = []
    for qtype, qtype_cn, alloc in (("single_choice", "单选", alloc_s),
                                   ("multiple_choice", "多选", alloc_m)):
        for i, m in enumerate(MODULES):
            pts = fine.get(m["no"]) or [("", m["label"], "")]
            offset = (alloc_s[i] if qtype == "multiple_choice" else 0) % max(1, len(pts))
            for j in range(alloc[i]):
                fp = pts[(offset + j) % len(pts)]
                plan.append({
                    "seq": len(plan) + 1, "module": m, "qtype": qtype, "qtype_cn": qtype_cn,
                    "fine_id": fp[0], "fine_name": fp[1], "fine_basis": fp[2],
                    "module_count": alloc_t[i],
                    "industry": INDUSTRIES[(len(plan) * 5 + i * 3) % len(INDUSTRIES)],
                })

    print(f"卷名：{args.paper}")
    assign_answers(plan)
    print("知识点题量（考纲权重 → 本卷题数）：")
    for i, m in enumerate(MODULES):
        print(f"  {m['label']:<12} {m['pct']:>4.0%} → 共 {alloc_t[i]:>2} 题"
              f"（单 {alloc_s[i]} + 多 {alloc_m[i]}）")
    print(f"合计 {len(plan)} 题 = 单选 {args.singles}（{args.singles * 2} 分）"
          f" + 多选 {args.multiples}（{args.multiples * 2} 分） = {len(plan) * 2} 分")
    from collections import Counter as _C
    print("答案位置（已按机械规则均分并指定）：单选",
          dict(sorted(_C(it["answer"] for it in plan if it["qtype"] == "single_choice").items())),
          "多选项数",
          dict(sorted(_C(len(it["answer"]) for it in plan if it["qtype"] == "multiple_choice").items())))

    est = len(plan) * (1400 * PRICE["in"] + 350 * PRICE["out"]) / 1_000_000
    print(f"预估成本 ¥{est:.3f}（{args.workers} 并发，上限 ¥{args.cap_cny}）")
    if est > args.cap_cny:
        print("拒绝执行：预估超过上限")
        return 2
    if not args.apply:
        print("dry-run：未调用模型、未写库")
        return 0

    from openai import OpenAI
    env = load_env()
    client = OpenAI(api_key=env["DEEPSEEK_API_KEY"],
                    base_url=env.get("DEEPSEEK_BASE_URL") or "https://api.deepseek.com", timeout=180)

    db = DATA / f"{SUBJECT}.sqlite"
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    # --replace 时，同名卷的旧题要从"去重比对池"里排除，否则重出会被自己挡住
    if args.replace:
        existing = [ngrams(r[0]) for r in con.execute(
            "SELECT stem FROM questions WHERE status<>'archived' "
            "AND COALESCE(exam_title,'')<>?", (args.paper,))]
    else:
        existing = [ngrams(r[0]) for r in con.execute(
            "SELECT stem FROM questions WHERE status<>'archived'")]
    con.close()
    mock = ROOT / "inbox" / "aca_llm" / "official_mock_20.md"
    if mock.exists():
        existing += [ngrams(x) for x in re.findall(r"\*\*题干\*\*：(.+)", mock.read_text(encoding="utf-8"))]

    s_single, s_multi = fetch_samples()
    guides = GuideCache()
    lock = threading.Lock()
    made: dict[int, dict] = {}
    stems: dict[int, set[str]] = {}
    spent = [0.0]

    def log_cost(usage: dict, item: dict) -> float:
        cost = ((usage.get("prompt_tokens", 0) or 0) * PRICE["in"]
                + (usage.get("completion_tokens", 0) or 0) * PRICE["out"]) / 1_000_000
        with lock:
            spent[0] += cost
            with (LOGS / "cost_ledger.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"at": now_iso(), "task": "generate_mock_paper", "model": args.model,
                                     "paper": args.paper, "kp": item["module"]["label"],
                                     "fine": item["fine_id"], "usage": usage,
                                     "cost_cny": round(cost, 6)}, ensure_ascii=False) + "\n")
        return cost

    def make_one(item: dict, avoid_n: int = 6) -> dict | None:
        m = item["module"]
        with lock:
            recent = sorted(made.items())[-avoid_n:]
            avoid = "\n".join(f"- {x['stem'][:42]}" for _, x in recent)
            peer = list(stems.values())
        ctx = rag_context(f"{m['label']} {item['fine_name']} {item['qtype_cn']}", k=2)
        user = build_prompt(args.paper, item["seq"], len(plan), m["label"], m["pct"],
                            (item["fine_id"], item["fine_name"], item["fine_basis"]),
                            item["qtype_cn"], item["module_count"], item["industry"],
                            guides.get(m["guide"]), ctx,
                            s_multi if item["qtype_cn"] == "多选" else s_single, avoid,
                            item["answer"], m["no"])
        why = ""
        for attempt in range(1, 5):
            body = user if not why else user + f"\n\n【上一版被退回的原因】{why}\n请修正后重新输出。"
            q, usage = call(client, args.model, args.reasoning, body)
            log_cost(usage, item)
            good, why = validate(q, item["qtype"])
            if good:
                got = "".join(sorted(set(re.sub(r"[^A-H]", "", str(q.get("answer")).upper()))))
                if got != item["answer"]:
                    good, why = False, f"答案位置必须是 {item['answer']}，你给的是 {got}，请把答案挪到指定位置"
            if good and m["no"] != 4:
                # 硬校验：非微调模块不许把"微调/重训"当万能干扰项（模块 3 最多 1 个）
                hits = sum(1 for o in (q.get("options") or [])
                           if re.search(r"微调|再训练|重新训练|预训练|继续训练", str(o)))
                limit = 1 if m["no"] == 3 else 0
                if hits > limit:
                    good, why = (False,
                                 f"本模块最多允许 {limit} 个「微调/重训」类干扰项，你写了 {hits} 个；"
                                 f"请换成 {label} 专属的错误方向：{DISTRACT.get(m['no'], '选错手段/环节错位')}")
            if good:
                g = ngrams(str(q.get("stem")))
                if any(similarity(g, e) >= 0.55 for e in existing) or \
                        any(similarity(g, e) >= 0.50 for e in peer):
                    good, why = False, "与既有题目或本卷其他题过于相似，请换场景与业务"
            if good:
                q.update(module=m["label"], module_no=m["no"], question_type=item["qtype"],
                         kp=m["label"], fine_id=item["fine_id"], fine_name=item["fine_name"],
                         seq=item["seq"], answer=item["answer"])
                print(f"  [{item['seq']:>2}/{len(plan)}] ✓ {m['label']}/{item['qtype_cn']}"
                      f" {item['fine_id']} {item['fine_name'][:12]} 答案={item['answer']}"
                      f"（{attempt} 次，累计 ¥{spent[0]:.4f}）")
                return q
            print(f"  [{item['seq']:>2}/{len(plan)}] ✗ {m['label']} 第{attempt}次：{why}")
        return None

    print(f"\n开始生成（{args.workers} 并发）…")
    # 预热：jieba 首次加载词典不是线程安全的，先在主线程跑一次检索
    rag_context("重排序 检索", k=1)
    guides.get(MODULES[0]["guide"])
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(make_one, it): it for it in plan}
        for fut in futures:
            item = futures[fut]
            try:
                q = fut.result()
            except Exception as exc:  # noqa: BLE001
                print(f"  [{item['seq']}] 异常：{exc}")
                q = None
            if q:
                with lock:
                    made[item["seq"]] = q
                    stems[item["seq"]] = ngrams(str(q.get("stem")))

    ordered = [made[s] for s in sorted(made)]
    print(f"\n成功 {len(ordered)}/{len(plan)} 题，实花 ¥{spent[0]:.4f}")
    if not ordered:
        print("一题都没生成成功，退出")
        return 1

    # 写库：**按卷面顺序插**（先 35 单选后 15 多选），id 顺序 = 卷面 seq 顺序
    wconn = sqlite3.connect(str(db))
    wconn.execute("PRAGMA busy_timeout=30000")
    cols = [r[1] for r in wconn.execute("PRAGMA table_info(questions)")]
    source_url = "AI生成-KB增强"
    inserted = 0
    try:
        if args.replace:
            old = wconn.execute("SELECT count(*) FROM questions WHERE exam_title=?",
                                (args.paper,)).fetchone()[0]
            if old:
                wconn.execute("DELETE FROM questions WHERE exam_title=?", (args.paper,))
                print(f"--replace：已删除同名旧卷 {old} 题")
        for q in ordered:
            stem = str(q["stem"]).strip()
            opts = [{"key": o.strip()[0], "text": re.sub(r"^[A-H]\s*[.、)．]\s*", "", o.strip())}
                    for o in q["options"]]
            ans = "".join(sorted(set(re.sub(r"[^A-H]", "", str(q["answer"]).upper()))))
            uid = (generate_uid(SUBJECT, source_url, stem) if generate_uid else None) or f"ai-{uuid.uuid4().hex[:12]}"
            row = {
                "question_uid": uid, "subject": SUBJECT,
                "source_type": "generate", "source_url": source_url,
                "source_credit": f"{args.paper}（知识库增强生成）",
                "knowledge_point": f"{q['fine_id']} {q['fine_name']}".strip(),
                "chapter": f"{q['module']}·{q['fine_id']}".strip("·"),
                "question_type": q["question_type"],
                "stem": stem,
                "options": json.dumps(opts, ensure_ascii=False),
                "answer": ans,
                "explanation": str(q["explanation"]).strip(),
                "difficulty": "中", "status": "approved",
                "trust_level": "ai_generated", "exam_title": args.paper,
                "syllabus_ref": f"ACA V2.4 模块{q['module_no']}（{q['module']}，{dict((m['label'], m['pct']) for m in MODULES)[q['module']]:.0%}）",
                "version": 1,
            }
            row = {k: v for k, v in row.items() if k in cols}
            wconn.execute(f"INSERT INTO questions ({','.join(row)}) VALUES ({','.join('?' * len(row))})",
                          tuple(row.values()))
            inserted += 1
        wconn.commit()
    finally:
        wconn.close()

    # 回读校验：顺序 / 题型分段 / 各模块题数 / 微调干扰项比例
    chk = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    chk.row_factory = sqlite3.Row
    rows = chk.execute("SELECT id, question_type, knowledge_point, chapter, options FROM questions "
                       "WHERE exam_title=? AND status='approved' ORDER BY id", (args.paper,)).fetchall()
    chk.close()
    kinds = [r["question_type"] for r in rows]
    first_multi = next((i for i, k in enumerate(kinds) if k == "multiple_choice"), len(kinds))
    tail_mixed = any(k == "single_choice" for k in kinds[first_multi:])
    print(f"已入库 {inserted} 题 → exam_title='{args.paper}'")
    print(f"回读校验：{len(rows)} 题；前 {first_multi} 题全单选，"
          f"其后 {len(rows) - first_multi} 题全多选；{'❌ 仍有混杂' if tail_mixed else '✓ 分段正确'}")
    others = [r for r in rows if not (r["chapter"] or "").startswith("大模型微调")]
    tox = [r for r in others if re.search(r"微调|再训练|重新训练|预训练", r["options"] or "")]
    print(f"微调类干扰项：非微调模块 {len(others)} 题中 {len(tox)} 题出现"
          f"（{len(tox) / max(1, len(others)):.0%}）{'✓' if len(tox) <= len(others) * 0.3 else '❌ 仍偏多'}")

    md = Path(args.export_md) if args.export_md else OUT / f"{args.paper}.md"
    export_markdown(md, args.paper, ordered)
    print(f"答案册已导出：{md}")
    return 0 if len(ordered) == len(plan) else 3


if __name__ == "__main__":
    raise SystemExit(main())
