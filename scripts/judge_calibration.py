#!/usr/bin/env python
"""阶段 6 · 判分校准（Pro 生成标准 → Flash 重判 → 一致率 → 失败模式报告）。

用法:
    python scripts/judge_calibration.py --dry-run            # 只打印抽样与成本预估，不发请求
    python scripts/judge_calibration.py --pilot 12           # 小样本 pilot（推荐先跑）
    python scripts/judge_calibration.py --pilot 12 --cap-cny 1.5

设计（依据 DESIGN.md 第 10/12 节 + .tools/题库项目-决策记录.md）:
  1. **ACA 不参与校准**（本地规则判分，零 LLM）。
  2. 判分标准由 **Pro** 生成 → 写 `config/judge_prompt.json`（version="1.0"），**冻结后不再改动**，
     否则会破坏判分输入的缓存前缀并让前后结果不可比。
  3. 每条题**不生成学生答案**（省一次调用），而是用参考答案构造 3 档作答：
     `exact`（原答案）/ `partial`（截断 60%）/ `blank`（答非所问），恰好覆盖满分/部分分/零分三档。
  4. 一致率口径：**非写作题按四舍五入到整数完全相同**；写作题按总分误差 ≤1 或三维度档位一致。
  5. 🔴 成本闸门：调用前查余额；预估成本 > `--cap-cny`（默认 1.5 元）直接拒绝执行。
     每次真实调用都 append 到 `logs/cost_ledger.jsonl`。
  6. 实测平台事实：官方 API **无 Batch API** → 串行 `chat/completions`；判分档位固定
     `reasoning_effort='low'`（思考 token 按输出计费）。
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
LOGS = ROOT / "logs"
ENV_FILE = ROOT / ".env"
PROMPT_FILE = ROOT / "config" / "judge_prompt.json"
LEDGER = LOGS / "cost_ledger.jsonl"
REPORT = LOGS / "judge_calibration_report.md"

# 参与校准的题型（ACA 单选/多选本地判分，不在此列）
CALIB_TYPES = {
    "english": ["reading_fill", "grammar_fill", "translation_fill", "sentence_build", "reading_qa"],
    "c_wuhan": ["program_fill"],
}

PRICE = {  # 元 / 1M tokens（官方空闲时段价）
    "deepseek-flash": {"in": 1.0, "out": 4.0, "cache": 0.02},
    "deepseek-v4-pro": {"in": 4.5, "out": 13.5, "cache": 0.15},
}
PRO_MODEL = "deepseek-v4-pro"
FLASH_MODEL = "deepseek-flash"


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


def cost_of(model: str, usage: dict) -> float:
    p = PRICE[model]
    pin = usage.get("prompt_tokens", 0) or 0
    pout = usage.get("completion_tokens", 0) or 0
    cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0) or 0
    return ((pin - cached) * p["in"] + cached * p["cache"] + pout * p["out"]) / 1_000_000


def log_call(stage: str, model: str, usage: dict, note: str) -> float:
    c = cost_of(model, usage)
    LOGS.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": now_iso(), "stage": stage, "kind": "llm_call", "model": model,
                             "usage": usage, "cost_cny": round(c, 6), "note": note}, ensure_ascii=False) + "\n")
    return c


def balance_cny() -> float | None:
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


# ------------------------------------------------------------------ 判分标准


def load_prompt_cfg() -> dict:
    if PROMPT_FILE.exists():
        try:
            return json.loads(PROMPT_FILE.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass
    return {"version": "0.0", "prompts": {}}


def full_score_for(subject: str, qtype: str) -> float:
    try:
        tax = json.loads((ROOT / "config" / "taxonomy.json").read_text(encoding="utf-8"))
        cfg = (tax["subjects"][subject]["question_types"].get(qtype) or {})
        for k in ("per_item", "paper_score"):
            if isinstance(cfg.get(k), (int, float)) and cfg[k] > 0:
                return float(cfg[k])
    except Exception:  # noqa: BLE001
        pass
    return 1.0


RUBRIC_SYS = "你是湖北专升本考试的命题与阅卷专家，负责制定**可复现**的判分标准。只输出 JSON。"


def rubric_user(subject: str, qtype: str, name: str) -> str:
    return (
        f"请为【{subject} · {name}（question_type={qtype}）】制定判分标准，输出严格 JSON：\n"
        '{"dimensions": ["评分维度…"], "levels": [{"score": 满分, "desc": "…"}], '
        '"examples": [{"answer": "…", "score": 满分, "why": "…"}], "notes": "常见误判"}\n'
        f"本机该题型每题满分 = {full_score_for(subject, qtype)} 分。给出 2 个示例。"
    )


def ensure_rubrics(client, cfg: dict, types_by_subject: dict[str, list[str]], cap_state: dict) -> tuple[dict, float]:
    spent = 0.0
    prompts = cfg.setdefault("prompts", {})
    tax = json.loads((ROOT / "config" / "taxonomy.json").read_text(encoding="utf-8"))
    for subject, types in types_by_subject.items():
        for qtype in types:
            key = f"{subject}.{qtype}"
            if key in prompts:
                continue
            name = ((tax["subjects"][subject]["question_types"].get(qtype) or {}).get("name") or qtype)
            resp = client.chat.completions.create(
                model=PRO_MODEL,
                messages=[{"role": "system", "content": RUBRIC_SYS},
                          {"role": "user", "content": rubric_user(subject, qtype, name)}],
                reasoning_effort="high",
                response_format={"type": "json_object"},
                temperature=0,
            )
            usage = resp.usage.model_dump() if getattr(resp, "usage", None) else {}
            call_cost = log_call("stage6.rubric", PRO_MODEL, usage, f"rubric {key}")
            spent += call_cost
            cap_state["spent"] += call_cost   # ⚠️ 只能累加"本次调用"的费用
            rubric = json.loads(resp.choices[0].message.content or "{}")
            rubric["full_score"] = full_score_for(subject, qtype)
            rubric["name"] = name
            rubric["generated_at"] = now_iso()
            prompts[key] = rubric
            print(f"  [rubric] {key}  满分={rubric['full_score']}  维度={len(rubric.get('dimensions') or [])}")
            if cap_state["spent"] > cap_state["cap"]:
                raise RuntimeError(f"成本超出上限 {cap_state['cap']} 元（已花 {cap_state['spent']:.3f}）")
    if prompts:
        cfg["version"] = "1.0"
        cfg["model_for_standard"] = PRO_MODEL
        cfg["frozen_at"] = cfg.get("frozen_at") or now_iso()
        PROMPT_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return cfg, spent


# ------------------------------------------------------------------ 判分


def grade(client, model: str, effort: str, subject: str, qtype: str, rubric: dict,
          stem: str, answer: str, user_answer: str) -> tuple[float, str, dict]:
    full = rubric.get("full_score", 1.0)
    sys_msg = (
        f"你是严格的阅卷老师。题型={qtype}，每题满分={full}。判分标准（唯一依据）：\n"
        + json.dumps({k: rubric.get(k) for k in ("dimensions", "levels", "examples", "notes")},
                     ensure_ascii=False)
        + '\n只输出 JSON：{"score": <数字>, "reason": "<简短理由>"}'
    )
    user_msg = f"【题干】{stem}\n【参考答案】{answer}\n【学生作答】{user_answer}\n请给分。"
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": sys_msg}, {"role": "user", "content": user_msg}],
        reasoning_effort=effort,
        response_format={"type": "json_object"},
        temperature=0,
    )
    usage = resp.usage.model_dump() if getattr(resp, "usage", None) else {}
    txt = resp.choices[0].message.content or "{}"
    try:
        data = json.loads(txt)
    except Exception:  # noqa: BLE001
        m = re.search(r"\{.*\}", txt, re.S)
        data = json.loads(m.group(0)) if m else {}
    return float(data.get("score", 0) or 0), str(data.get("reason", ""))[:200], usage


def make_variants(answer: str) -> list[tuple[str, str]]:
    a = (answer or "").strip()
    if not a:
        return [("exact", "（标准答案缺失）"), ("blank", "不知道")]
    cut = max(1, int(len(a) * 0.6))
    return [("exact", a), ("partial", a[:cut]), ("blank", "我不会，随便写一点内容。" + a[:3])]


# ------------------------------------------------------------------ 主流程


def sample_questions(per_type: int) -> list[tuple[str, str, str, str, str]]:
    out: list[tuple[str, str, str, str, str]] = []
    for subject, types in CALIB_TYPES.items():
        p = DATA / f"{subject}.sqlite"
        if not p.exists():
            continue
        conn = sqlite3.connect(str(p))
        for qtype in types:
            rows = conn.execute(
                "SELECT question_uid, stem, answer FROM questions WHERE question_type=? AND answer<>'' "
                "ORDER BY RANDOM() LIMIT ?", (qtype, per_type)).fetchall()
            for uid, stem, answer in rows:
                out.append((subject, qtype, uid, stem or "", answer or ""))
        conn.close()
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pilot", type=int, default=3, help="每个题型抽多少题（默认 3）")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--cap-cny", type=float, default=1.5)
    args = ap.parse_args()

    qs = sample_questions(args.pilot)
    by_type: dict[str, int] = {}
    for _s, t, _u, _st, _a in qs:
        by_type[t] = by_type.get(t, 0) + 1
    n_pairs = sum(len(make_variants(a)) for *_x, a in qs)

    # 粗略预估：Pro 判分 1 次 ≈ 1200 in + 300 out；Flash 同量；rubric ≈ 1000 in + 2000 out
    pro_each = (1200 * PRICE[PRO_MODEL]["in"] + 300 * PRICE[PRO_MODEL]["out"]) / 1_000_000
    flash_each = (1200 * PRICE[FLASH_MODEL]["in"] + 300 * PRICE[FLASH_MODEL]["out"]) / 1_000_000
    n_types = len({t for _s, t, *_ in qs})
    est = n_pairs * (pro_each + flash_each) + n_types * ((1000 * PRICE[PRO_MODEL]["in"] + 2000 * PRICE[PRO_MODEL]["out"]) / 1_000_000)

    bal = balance_cny()
    print(f"抽样: {len(qs)} 题 / {len(by_type)} 个题型 -> {by_type}")
    print(f"判分对: {n_pairs}（每题 3 档作答：exact/partial/blank）")
    print(f"预估成本: ¥{est:.3f}（上限 ¥{args.cap_cny}）  当前余额: {bal if bal is None else f'¥{bal:.2f}'}")
    if bal is not None and bal <= 5.50:
        print("拒绝执行：余额已到停机线（≤¥5.50）")
        return 2
    if est > args.cap_cny:
        print(f"拒绝执行：预估 ¥{est:.3f} > 上限 ¥{args.cap_cny}")
        return 2
    if args.dry_run:
        print("dry-run：不发起任何请求。")
        return 0

    from openai import OpenAI

    env = load_env()
    client = OpenAI(api_key=env["DEEPSEEK_API_KEY"], base_url=env.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"), timeout=90)

    cap_state = {"spent": 0.0, "cap": args.cap_cny}
    cfg = load_prompt_cfg()
    cfg, spent = ensure_rubrics(client, cfg, {s: [t for _s2, t, *_ in qs if _s2 == s] for s in CALIB_TYPES}, cap_state)
    print(f"判分标准已冻结为 version={cfg['version']}（本轮 rubric 花费 ¥{spent:.3f}）")

    t0 = time.time()
    rows: list[dict] = []
    for subject, qtype, uid, stem, answer in qs:
        rubric = cfg["prompts"][f"{subject}.{qtype}"]
        for kind, ua in make_variants(answer):
            p_score, p_reason, p_usage = grade(client, PRO_MODEL, "high", subject, qtype, rubric, stem, answer, ua)
            cap_state["spent"] += log_call("stage6.standard", PRO_MODEL, p_usage, f"{qtype}/{kind}")
            f_score, f_reason, f_usage = grade(client, FLASH_MODEL, "low", subject, qtype, rubric, stem, answer, ua)
            cap_state["spent"] += log_call("stage6.flash", FLASH_MODEL, f_usage, f"{qtype}/{kind}")
            same = round(p_score) == round(f_score)
            rows.append({"uid": uid, "subject": subject, "type": qtype, "variant": kind,
                         "pro": p_score, "flash": f_score, "same": same,
                         "pro_reason": p_reason, "flash_reason": f_reason})
            print(f"  [{qtype}/{kind:7}] pro={p_score:<5} flash={f_score:<5} {'同' if same else '**异**'}  已花 ¥{cap_state['spent']:.3f}")
            if cap_state["spent"] > cap_state["cap"]:
                print(f"⚠️ 超出上限 ¥{cap_state['cap']}，提前停止")
                break

    agree = sum(1 for r in rows if r["same"])
    rate = agree / len(rows) if rows else 0
    by_type_stat: dict[str, list[int]] = {}
    for r in rows:
        s = by_type_stat.setdefault(r["type"], [0, 0])
        s[0] += 1
        s[1] += 1 if r["same"] else 0

    md = [
        "# 判分校准报告（阶段 6）", "",
        f"- 生成时间：{now_iso()}",
        f"- 判分标准版本：`config/judge_prompt.json` version **{cfg['version']}**（由 {PRO_MODEL} 生成并冻结）",
        f"- 样本：{len(qs)} 题 × 3 档作答 = **{len(rows)}** 个判分对",
        f"- **一致率（四舍五入到整数完全相同）：{agree}/{len(rows)} = {rate:.1%}**",
        f"- 本轮实际花费：**¥{cap_state['spent']:.3f}**",
        "", "## 分题型一致率", "", "| 题型 | 判分对 | 一致 | 一致率 |", "|---|---|---|---|",
    ]
    for t, (n, ok) in sorted(by_type_stat.items()):
        md.append(f"| {t} | {n} | {ok} | {ok / n:.1%} |")

    md += ["", "## 失败模式（不一致样本）", "", "| 失败模式 | 例子（题干/作答） | 次数 |", "|---|---|---|"]
    pat: dict[str, list[str]] = {}
    for r in rows:
        if r["same"]:
            continue
        if r["variant"] == "blank":
            key = "空/答非所问时给分过宽或过严"
        elif r["variant"] == "partial":
            key = "部分分尺度不一致"
        else:
            key = "参考答案有多种合理表达"
        pat.setdefault(key, []).append(f"pro={r['pro']} vs flash={r['flash']}｜{r['type']}")
    if not pat:
        md.append("| （本轮无不一致） | — | 0 |")
    for k, v in pat.items():
        md.append(f"| {k} | {v[0]} | {len(v)} |")

    md += ["", "## 原始样本（前 20 条）", "", "| 题型 | 档位 | Pro | Flash | 一致 |", "|---|---|---|---|---|"]
    for r in rows[:20]:
        md.append(f"| {r['type']} | {r['variant']} | {r['pro']} | {r['flash']} | {'✅' if r['same'] else '❌'} |")
    md += ["", "> 双阈值判定：一致率 ≥85% 视为通过；未达则调 Prompt 重跑（最多 3 轮）。"]
    REPORT.write_text("\n".join(md) + "\n", encoding="utf-8")

    print(f"\n=== 一致率 {agree}/{len(rows)} = {rate:.1%}  花费 ¥{cap_state['spent']:.3f}  耗时 {time.time()-t0:.0f}s")
    print(f"报告：{REPORT}")
    return 0 if rate >= 0.85 else 1


if __name__ == "__main__":
    raise SystemExit(main())
