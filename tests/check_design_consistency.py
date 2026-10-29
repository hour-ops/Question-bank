#!/usr/bin/env python
"""DESIGN.md 结构 + 与 config/*.json 的一致性检查（阶段 1 验收用）。

用法: python tests/check_design_consistency.py
退出码: 0 = 全部通过, 1 = 有问题
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
problems: list[str] = []
checks: list[str] = []

design_path = ROOT / "DESIGN.md"
if not design_path.exists():
    print("FAIL: DESIGN.md 不存在")
    raise SystemExit(1)
checks.append("DESIGN.md 存在")
design = design_path.read_text(encoding="utf-8")

# 1) 章节数（验收要求 >= 17）
sections = re.findall(r"(?m)^## ", design)
checks.append(f"二级章节数 = {len(sections)}")
if len(sections) < 17:
    problems.append(f"章节数 {len(sections)} < 17")

# 2) 每个科目：db 路径与科目名都要出现
tax = json.loads((ROOT / "config" / "taxonomy.json").read_text(encoding="utf-8"))
for subj, cfg in tax["subjects"].items():
    if cfg["db"] not in design:
        problems.append(f"{subj}: db 路径未出现在 DESIGN.md ({cfg['db']})")
    if f"`{subj}`" not in design:
        problems.append(f"{subj}: 科目名未出现在 DESIGN.md")
checks.append(f"科目一致性检查 {len(tax['subjects'])} 科")

# 3) 英语分值合计 = 100
eng_total = sum(t["paper_score"] for t in tax["subjects"]["english"]["question_types"].values())
checks.append(f"英语题型分值合计 = {eng_total}")
if eng_total != 100:
    problems.append(f"英语分值合计 {eng_total} != 100")

# 4) ACA 权重合计 = 1.0
w = sum(tax["subjects"]["aca_llm"]["syllabus_v2_4"].values())
checks.append(f"ACA 权重合计 = {w:.2f}")
if abs(w - 1.0) > 1e-9:
    problems.append(f"ACA 权重合计 {w} != 1.0")

# 5) 两套枚举都要在 DESIGN.md 里出现
for s in ["raw", "parsed", "pending_review", "approved", "rejected", "archived"]:
    if s not in design:
        problems.append(f"questions.status 枚举缺 {s}")
checks.append("status 枚举 6 值")
for s in ["pending", "submitted", "synced", "failed"]:
    if s not in design:
        problems.append(f"judge_queue.judge_status 枚举缺 {s}")
checks.append("judge_status 枚举 4 值")

# 6) routing.json 的 generate 模型必须在 DESIGN.md 的判分机制里出现
routing = json.loads((ROOT / "config" / "routing.json").read_text(encoding="utf-8"))
models = {v["model"] for v in routing["generate"].values()}
for m in models:
    if m not in design:
        problems.append(f"routing.json 的模型 {m} 未出现在 DESIGN.md")
checks.append(f"routing 模型一致性 {sorted(models)}")

# 7) 频率表一致性（routing.schedules 的 key 都要出现）
for k in routing["schedules"]:
    if k not in design:
        problems.append(f"routing.schedules 的 {k} 未出现在 DESIGN.md")
checks.append(f"任务频率 {len(routing['schedules'])} 项")

# 8) cost_budget 币种与总额
cb = json.loads((ROOT / "config" / "cost_budget.json").read_text(encoding="utf-8"))
checks.append(f"预算 = {cb['total']} {cb['currency']}")
if cb["currency"] != "CNY":
    problems.append("cost_budget 币种不是 CNY")

print("--- checks ---")
for c in checks:
    print(f"  ok  {c}")
print(f"\n章节数: {len(sections)} (要求 >=17)")
if problems:
    print(f"\nFAIL ({len(problems)}):")
    for p in problems:
        print(f"  - {p}")
    raise SystemExit(1)
print("\nRESULT: PASS — DESIGN.md 与 config 全部一致")
raise SystemExit(0)
