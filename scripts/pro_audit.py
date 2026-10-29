#!/usr/bin/env python
"""用 **deepseek-v4-pro** 对题库做独立质量审计（量化：approved 正确率 + rejected 误杀率）。

为什么用脚本而不是让 pro 跑一个会话：
  - 会话会把「读文件、跑 SQL、来回对话」的上下文也算 pro 的钱；本脚本只发「题干+答案」，
    花费可预估、可复现、结论是百分比。
  - 审计的核心是**判定**，不需要 agent 能力。

用法:
    python scripts/pro_audit.py --pilot 15            # 小样本测试（约 ¥0.3）
    python scripts/pro_audit.py --approved 60 --rejected 40 --cap-cny 3
    python scripts/pro_audit.py --dry-run

输出: logs/pro_audit_report.md（含逐题明细），并逐次调用记账到 logs/cost_ledger.jsonl
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
LOGS = ROOT / "logs"
ENV_FILE = ROOT / ".env"
SUBJECTS = ["english", "c_wuhan", "c_hbpu", "aca_llm"]
MODEL = "deepseek-v4-pro"          # 审计必须用最强的
PRICE = {"in": 4.5, "out": 13.5}   # CNY / 1M（空闲时段官方价）
EST_IN, EST_OUT = 1300, 350        # 每次判定的预估 token

SYS = ("你是考试的终审阅卷专家。只看题目本身，判断它**能否直接用于正式考试**。"
       "标准：题干完整可独立作答；参考答案正确且唯一；无广告/推广/乱码；符合该科目考纲。"
       "只输出 JSON。")

RUBRIC = {
    "english": "湖北专升本《大学英语》考纲：**无选择题、无判断题**，全部主观题。",
    "c_wuhan": "武汉商学院 C 语言考纲：改错、程序填空、编程；无选择题与判断题。",
    "c_hbpu": "湖北理工学院 C 语言考纲：改错、程序填空、编程；无选择题与判断题。",
    "aca_llm": "阿里云 ACA 大模型工程师 V2.4：单选 35 题 + 多选 15 题；考纲六大模块为 "
               "大模型概念 18%、提示词工程 20%、增强大模型应用的能力 22%、大模型微调 12%、"
               "大模型Agent 16%、大模型安全合规 12%。通用机器学习/深度学习细节属超纲。",
}


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


def sample(subject: str, status: str, n: int) -> list[dict]:
    p = DATA / f"{subject}.sqlite"
    if not p.exists():
        return []
    c = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    rows = c.execute(
        "SELECT question_uid, question_type, stem, options, answer, explanation FROM questions "
        "WHERE status=? ORDER BY question_uid LIMIT ?", (status, n)).fetchall()
    c.close()
    return [{"subject": subject, "status": status, "uid": r[0], "type": r[1], "stem": r[2] or "",
             "options": r[3] or "", "answer": r[4] or "", "explanation": r[5] or ""} for r in rows]


def judge(client, item: dict) -> tuple[bool, str, dict]:
    payload = {"科目": item["subject"], "题型": item["type"], "题干": item["stem"][:600],
               "参考答案": item["answer"][:300]}
    if item["options"] and item["options"].strip() not in ("", "[]", "null"):
        payload["选项"] = item["options"][:400]
    user = (f"考纲约束：{RUBRIC.get(item['subject'], '')}\n\n"
            + json.dumps(payload, ensure_ascii=False)
            + '\n\n只输出 JSON：{"usable": true|false, "problem": "若不 usable，一句话说明；否则空字符串"}')
    resp = client.chat.completions.create(
        model=MODEL, messages=[{"role": "system", "content": SYS}, {"role": "user", "content": user}],
        reasoning_effort="high", response_format={"type": "json_object"}, temperature=0)
    usage = resp.usage.model_dump() if getattr(resp, "usage", None) else {}
    try:
        d = json.loads(resp.choices[0].message.content or "{}")
    except Exception:  # noqa: BLE001
        d = {}
    return bool(d.get("usable")), str(d.get("problem") or "")[:160], usage


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pilot", type=int, default=0, help="每个科目抽 N 道 approved + N 道 rejected")
    ap.add_argument("--subject", default="", help="只审这个科目（空=全科）")
    ap.add_argument("--approved", type=int, default=0, help="approved 抽样总数（按科目均分）")
    ap.add_argument("--rejected", type=int, default=0, help="rejected 抽样总数（按科目均分）")
    ap.add_argument("--cap-cny", type=float, default=2.0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.pilot:
        per_appr, per_rej = args.pilot, args.pilot
    else:
        n_subj = 1 if args.subject else len(SUBJECTS)
        per_appr = max(1, args.approved // n_subj) if args.approved else 0
        per_rej = max(1, args.rejected // n_subj) if args.rejected else 0

    items: list[dict] = []
    target_subjects = [args.subject] if args.subject in SUBJECTS else SUBJECTS
    for s in target_subjects:
        items += sample(s, "approved", per_appr)
        items += sample(s, "rejected", per_rej)
    n = len(items)
    est = n * (EST_IN * PRICE["in"] + EST_OUT * PRICE["out"]) / 1_000_000
    print(f"抽样 {n} 题（approved {per_appr}/科 + rejected {per_rej}/科），预估 ¥{est:.3f}（上限 ¥{args.cap_cny}）")
    if est > args.cap_cny:
        print(f"拒绝执行：预估 ¥{est:.3f} > 上限 ¥{args.cap_cny}")
        return 2
    if args.dry_run:
        print("dry-run：未发起请求。")
        return 0

    from openai import OpenAI

    env = load_env()
    client = OpenAI(api_key=env["DEEPSEEK_API_KEY"],
                    base_url=env.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"), timeout=120)
    spent = 0.0
    t0 = time.time()
    for it in items:
        try:
            usable, problem, usage = judge(client, it)
        except Exception as exc:  # noqa: BLE001
            it["usable"], it["problem"] = None, f"调用失败: {type(exc).__name__}"
            continue
        c = ((usage.get("prompt_tokens", 0) or 0) * PRICE["in"]
             + (usage.get("completion_tokens", 0) or 0) * PRICE["out"]) / 1_000_000
        spent += c
        with (LOGS / "cost_ledger.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": now_iso(), "stage": "pro_audit", "kind": "llm_call", "model": MODEL,
                                 "subject": it["subject"], "usage": usage, "cost_cny": round(c, 6),
                                 "note": it["uid"]}, ensure_ascii=False) + "\n")
        it["usable"], it["problem"] = usable, problem
        print(f"  [{it['status']:8}] {it['subject']:9} {it['type']:16} "
              f"{'可用' if usable else '有问题'}  {problem[:40]}  已花 ¥{spent:.3f}")
        if spent > args.cap_cny:
            print(f"⚠️ 超出上限 ¥{args.cap_cny}，提前停止")
            break

    appr = [i for i in items if i["status"] == "approved" and i.get("usable") is not None]
    rej = [i for i in items if i["status"] == "rejected" and i.get("usable") is not None]
    ok_a = sum(1 for i in appr if i["usable"])
    ok_r = sum(1 for i in rej if i["usable"])          # rejected 里被判"可用" = 疑似误杀
    lines = [
        "# Pro 独立审计报告（deepseek-v4-pro）", "",
        f"- 生成时间：{now_iso()}",
        f"- 抽样：approved {len(appr)} 题、rejected {len(rej)} 题",
        f"- **approved 抽样正确率：{ok_a}/{len(appr)} = "
        f"{(ok_a / len(appr) if appr else 0):.1%}**（越高越好）",
        f"- **rejected 误杀率：{ok_r}/{len(rej)} = "
        f"{(ok_r / len(rej) if rej else 0):.1%}**（越低越好；高说明自动审核过严，丢了可用题）",
        f"- 花费 ¥{spent:.3f}（{len([i for i in items if i.get('usable') is not None])} 次 pro 调用）",
        "", "## 逐题明细", "", "| 原状态 | 科目 | 题型 | Pro 判定 | 问题 | uid |", "|---|---|---|---|---|---|",
    ]
    for i in items:
        if i.get("usable") is None:
            continue
        lines.append(f"| {i['status']} | {i['subject']} | {i['type']} | "
                     f"{'可用' if i['usable'] else '**有问题**'} | {i['problem'][:60]} | `{i['uid']}` |")
    report = LOGS / "pro_audit_report.md"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n=== approved 正确率 {ok_a}/{len(appr)}   rejected 误杀率 {ok_r}/{len(rej)}"
          f"   花费 ¥{spent:.3f}   耗时 {time.time() - t0:.0f}s")
    print(f"报告：{report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
