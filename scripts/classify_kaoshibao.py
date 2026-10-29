#!/usr/bin/env python
"""把考试宝抓来的真题按 ACA V2.4 六大考点打标（knowledge_point / syllabus_ref）。

为什么要打标：真题入库时没有考点字段，而用户要的是"按考纲权重出卷"，
没有考点就挑不出 18/20/22/12/16/12 的配比。

判定用 deepseek-flash 一次批量（50 题/次，reasoning=none），成本约 ¥0.01/次。
判不了的（同时沾多个考点）按考纲原话兜底到"增强"（因为它最宽）。

用法:
    python scripts/classify_kaoshibao.py --exam "考试宝预览"           # dry-run
    python scripts/classify_kaoshibao.py --exam "考试宝预览" --apply
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
LOGS = ROOT / "logs"
ENV_FILE = ROOT / ".env"
sys.path.insert(0, str(ROOT / "scripts"))

MODULES = [
    ("考点·大模型概念", 0.18, "理解大模型是什么/能做什么、能力边界、幻觉、训练数据时间范围、上下文限制"),
    ("考点·提示词工程", 0.20, "目标/背景/角色/约束/示例/输出格式/评价标准；复杂任务先列计划；翻译改写总结分类要补受众目的术语"),
    ("考点·增强大模型应用的能力", 0.22, "查企业资料用 RAG；实时数据/确定性计算/业务动作用工具；RAG 的解析切分检索重排序评测；MCP；知识库原理与质量改进"),
    ("考点·大模型微调", 0.12, "微调适合稳定行为/格式/风格/分类/轻量部署；流程 定义目标→准备样本→选基模→控数据质量→评估；选型边界"),
    ("考点·大模型 Agent", 0.16, "Agent 从回答问题到完成任务；目标/资料来源/工具边界/阶段检查点；Skill 固化方法；自检清单；高风险人工确认"),
    ("考点·安全合规", 0.12, "内容安全/数据安全/权限控制/生成内容标识/来源留存与审计追踪/人工复核；高风险场景不能替代责任人"),
]

SYS = ("你是阿里云大模型工程师 ACA 认证的命题分类器。只输出 JSON。\n"
       "给你一批题目，逐题归入且只归入一个考点，返回 {{\"labels\":[{{\"i\":序号,\"k\":0-5}}, ...]}}。\n"
       "0=大模型概念 1=提示词工程 2=增强大模型应用的能力(RAG/工具/MCP/知识库) 3=大模型微调 4=大模型 Agent 5=安全合规\n"
       "题目若同时沾边，选**最主要的考法**；纯技术实现细节、具体产品 API、模型参数数值这类超纲内容标 k=-1。")


def load_env() -> dict[str, str]:
    out = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def flat(s: str, n: int = 220) -> str:
    return re.sub(r"\s+", " ", s or "").strip()[:n]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exam", default="", help="exam_title（可模糊匹配）；留空配 --scatter 处理散题")
    ap.add_argument("--scatter", action="store_true", help="只处理 exam_title 为空的散题")
    ap.add_argument("--subject", default="aca_llm")
    ap.add_argument("--batch", type=int, default=40)
    ap.add_argument("--model", default="deepseek-flash")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    db = DATA / f"{args.subject}.sqlite"
    con = sqlite3.connect(str(db))
    con.row_factory = sqlite3.Row
    if args.scatter:
        rows = con.execute(
            "SELECT id, question_type, stem, knowledge_point FROM questions "
            "WHERE status='approved' AND COALESCE(exam_title,'')='' "
            "AND COALESCE(trust_level,'')<>'acp' AND COALESCE(reviewed_by,'')<>'paper-assembly' "
            "AND COALESCE(knowledge_point,'') NOT LIKE '考点·%' ORDER BY id").fetchall()
        label = "散题"
    else:
        rows = con.execute(
            "SELECT id, question_type, stem, knowledge_point FROM questions "
            "WHERE status='approved' AND exam_title LIKE ? ORDER BY id", (f"%{args.exam}%",)).fetchall()
        label = args.exam
    print(f"待分类 {len(rows)} 题（{label}）")
    if not rows:
        return 1

    from openai import OpenAI
    env = load_env()
    client = OpenAI(api_key=env["DEEPSEEK_API_KEY"],
                    base_url=env.get("DEEPSEEK_BASE_URL") or "https://api.deepseek.com", timeout=180)

    labels: dict[int, int] = {}
    spent = 0.0
    for start in range(0, len(rows), args.batch):
        chunk = rows[start:start + args.batch]
        listing = "\n".join(f"{i}. {flat(r['stem'])}" for i, r in enumerate(chunk))
        user = ("考点定义：\n" + "\n".join(f"{i}={m[0]}（{m[2]}）" for i, m in enumerate(MODULES))
                + f"\n\n题目：\n{listing}\n\n只输出 JSON。")
        resp = client.chat.completions.create(
            model=args.model, messages=[{"role": "system", "content": SYS},
                                        {"role": "user", "content": user}],
            response_format={"type": "json_object"}, temperature=0.0, reasoning_effort="none")
        usage = resp.usage.model_dump() if getattr(resp, "usage", None) else {}
        cost = ((usage.get("prompt_tokens") or 0) * 4.4 + (usage.get("completion_tokens") or 0) * 17.3) / 1e6
        spent += cost
        with (LOGS / "cost_ledger.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                 "task": "classify_kaoshibao", "model": args.model,
                                 "usage": usage, "cost_cny": round(cost, 6)}, ensure_ascii=False) + "\n")
        try:
            data = json.loads(resp.choices[0].message.content or "{}")
        except Exception:  # noqa: BLE001
            data = {}
        for item in data.get("labels") or []:
            try:
                i = int(item.get("i"))
                k = int(item.get("k"))
            except (TypeError, ValueError):
                continue
            if 0 <= i < len(chunk) and 0 <= k < len(MODULES):
                labels[chunk[i]["id"]] = k

    from collections import Counter
    print(f"已判 {len(labels)}/{len(rows)} 题，成本 ¥{spent:.4f}")
    print("  考点分布：")
    for k, m in enumerate(MODULES):
        n = sum(1 for v in labels.values() if v == k)
        print(f"    {m[0]:<16}{n:>3} 题（权重 {m[1]:.0%} → 50 题卷应 {round(50 * m[1])} 题）")

    if not args.apply:
        for r in rows[:5]:
            k = labels.get(r["id"])
            print(f"  id={r['id']} → {MODULES[k][0] if k is not None else '未判'}"
                  f"  {flat(r['stem'], 46)}")
        print("\ndry-run：未写库")
        con.close()
        return 0

    try:
        for rid, k in labels.items():
            con.execute("UPDATE questions SET knowledge_point=?, syllabus_ref=? WHERE id=?",
                        (MODULES[k][0], f"ACA V2.4 模块{k + 1}（{MODULES[k][0]}，{MODULES[k][1]:.0%}）", rid))
        con.commit()
    finally:
        con.close()
    print(f"已写入 {len(labels)} 题的考点标签")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
