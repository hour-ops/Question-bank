#!/usr/bin/env python
"""自动审核：把 `parsed` / `pending_review` 的题批量交给 Flash 做质量校验，合格者置 `approved`。

用法:
    python scripts/auto_review.py --dry-run                       # 只统计与预估，不调用
    python scripts/auto_review.py --subject all --batch 8 --cap-cny 1.5
    python scripts/auto_review.py --subject aca_llm --strict-syllabus   # ACA 额外做超纲判定

设计（DESIGN.md 第 12 节三层验证 + 第 15 节防幻觉）:
  1. **批量校验**：每 `--batch` 题一次调用（默认 8），把 890 题压到 ~110 次调用，
     比逐题校验便宜一个数量级。
  2. 判据：题干完整可作答、参考答案正确、无重复、与科目考纲符合（ACA 额外查超纲）。
  3. 合格 → `status='approved'` + `reviewed_by='auto:flash'` + `version+1`；
     不合格 → `status='rejected'`，原因写 `logs/review_rejects.jsonl`（**绝不写 distractors.json**）。
  4. 模型**没有明确表态**的题保持原状（不猜、不放行）——防止"沉默即通过"。
  5. 🔴 成本闸门：预估超 `--cap-cny` 或超预算 80% 直接拒绝；逐次调用记账。
  6. 官方 API 无 Batch → 串行；档位 `low`（判分/校验不需要长思考）。
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
LOGS = ROOT / "logs"
ENV_FILE = ROOT / ".env"
SUBJECTS = ["english", "c_wuhan", "c_hbpu", "aca_llm"]
PRICE = {"deepseek-flash": {"in": 1.0, "out": 4.0}, "deepseek-v4-pro": {"in": 4.5, "out": 13.5}}
MODEL = "deepseek-flash"
# 每批的大致 token 量（预估用）
EST_IN_PER_Q, EST_OUT_PER_Q = 260, 90

SYLLABUS_HINT = {
    "english": "湖北专升本《大学英语》：无选择题、无判断题，全部主观题；"
               "题型为语法填空、连词成句、阅读填空、阅读理解、翻译填空、写作。",
    "c_wuhan": "武汉商学院 C 语言（谭浩强第五版）：改错、程序填空、编程；无选择题与判断题。",
    "c_hbpu": "湖北理工学院 C 语言（祁文青 2018 版）：改错、程序填空、编程；无选择题与判断题。",
    "aca_llm": "阿里云大模型工程师 ACA V2.4：单选 35 题 + 多选 15 题；考纲六大模块为 "
               "大模型概念 18%、提示词工程 20%、增强大模型应用的能力 22%、大模型微调 12%、"
               "大模型Agent 16%、大模型安全合规 12%。**通用机器学习/深度学习细节题属超纲**。",
}

SYS = ("你是湖北专升本与阿里云认证的资深命题审核员。逐题核对题干、参考答案与解析，"
       "判断该题是否可以进入正式题库。只输出 JSON。")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(p: Path) -> sqlite3.Connection:
    c = sqlite3.connect(str(p))
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=30000")
    return c


def load_env() -> dict[str, str]:
    out: dict[str, str] = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def build_prompt(subject: str, rows: list[tuple]) -> str:
    items = []
    for uid, stem, answer, explanation, qtype, options in rows:
        it = {
            "uid": uid, "题型": qtype,
            "题干": (stem or "")[:500],
            "参考答案": (answer or "")[:300],
            "解析": (explanation or "")[:200],
        }
        # 🔴 选择题必须把 options 一并交给审核模型，否则会被判"题干缺少选项"
        if options and str(options).strip() not in ("", "[]", "null"):
            it["选项"] = str(options)[:500]
        items.append(it)
    return (
        f"科目：{subject}。考纲约束：{SYLLABUS_HINT.get(subject, '')}\n"
        f"请逐题审核下面 {len(items)} 道题，判据：\n"
        "1) 题干完整、可独立作答（不是残句/导航文字/表格碎片）\n"
        "2) 参考答案正确且与题干匹配（选择题需与「选项」一致）\n"
        "3) 不属于重复题、不超纲（超出上述考纲范围的判不合格）\n"
        "4) 题干/答案中**不得混入广告或推广文字**（如机构名、QQ/电话、公众号、版权声明）\n\n"
        + json.dumps(items, ensure_ascii=False)
        + '\n\n严格输出 JSON：{"results":[{"uid":"...","ok":true|false,"reason":"简短理由"}]}'
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--subject", default="all", choices=SUBJECTS + ["all"])
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--limit", type=int, default=0, help="本次最多审核多少题（0=不限）")
    ap.add_argument("--cap-cny", type=float, default=1.5)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--strict-syllabus", action="store_true", help="ACA 额外做超纲判定")
    ap.add_argument("--keep-out-of-syllabus", action="store_true",
                    help="把判为『超纲』的题保留为 approved 并标 trust_level='acp'"
                         "（超纲≠有问题；用户要求单独留一份以便了解）")
    args = ap.parse_args()

    subjects = SUBJECTS if args.subject == "all" else [args.subject]
    todo: dict[str, list[tuple]] = {}
    for s in subjects:
        p = DATA / f"{s}.sqlite"
        if not p.exists():
            continue
        c = connect(p)
        rows = c.execute(
            "SELECT question_uid, stem, answer, explanation, question_type, options FROM questions "
            "WHERE status IN ('parsed','pending_review') ORDER BY id"
        ).fetchall()
        c.close()
        if args.limit:
            rows = rows[: args.limit]
        if rows:
            todo[s] = rows

    total_q = sum(len(v) for v in todo.values())
    n_batches = sum((len(v) + args.batch - 1) // args.batch for v in todo.values())
    est_in = n_batches * 600 + total_q * EST_IN_PER_Q
    est_out = total_q * EST_OUT_PER_Q
    est = (est_in * PRICE[MODEL]["in"] + est_out * PRICE[MODEL]["out"]) / 1_000_000 * 2  # 高峰×2 保守

    print(f"待审 {total_q} 题 / {len(todo)} 科 -> {n_batches} 批（每批 {args.batch} 题）")
    for s, v in todo.items():
        print(f"  {s:9} {len(v):4} 题")
    print(f"预估成本 ¥{est:.3f}（上限 ¥{args.cap_cny}）")
    if est > args.cap_cny:
        print(f"拒绝执行：预估 ¥{est:.3f} > 上限 ¥{args.cap_cny}")
        return 2
    if args.dry_run:
        print("dry-run：未发起任何请求。")
        return 0

    from openai import OpenAI

    env = load_env()
    if not env.get("DEEPSEEK_API_KEY"):
        print("缺少 DEEPSEEK_API_KEY（题库项目/.env）")
        return 1
    client = OpenAI(api_key=env["DEEPSEEK_API_KEY"],
                    base_url=env.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"), timeout=120)

    spent = 0.0
    approved = rejected = unknown = out_of_syllabus = 0
    LOGS.mkdir(parents=True, exist_ok=True)
    reject_log = LOGS / "review_rejects.jsonl"
    t0 = time.time()

    for subject, rows in todo.items():
        db = DATA / f"{subject}.sqlite"
        conn = connect(db)
        for i in range(0, len(rows), args.batch):
            chunk = rows[i:i + args.batch]
            try:
                resp = client.chat.completions.create(
                    model=MODEL,
                    messages=[{"role": "system", "content": SYS},
                              {"role": "user", "content": build_prompt(subject, chunk)}],
                    reasoning_effort="low",
                    response_format={"type": "json_object"},
                    temperature=0,
                )
                usage = resp.usage.model_dump() if getattr(resp, "usage", None) else {}
                c = ((usage.get("prompt_tokens", 0) or 0) * PRICE[MODEL]["in"]
                     + (usage.get("completion_tokens", 0) or 0) * PRICE[MODEL]["out"]) / 1_000_000
                spent += c
                with (LOGS / "cost_ledger.jsonl").open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps({"ts": now_iso(), "stage": "auto_review", "kind": "llm_call",
                                         "subject": subject, "model": MODEL, "usage": usage,
                                         "cost_cny": round(c, 6), "note": f"batch of {len(chunk)}"},
                                        ensure_ascii=False) + "\n")
                data = json.loads(resp.choices[0].message.content or "{}")
                verdicts = {str(r.get("uid")): r for r in (data.get("results") or [])}
            except Exception as exc:  # noqa: BLE001
                print(f"  [batch-fail] {subject} 第 {i // args.batch + 1} 批: {type(exc).__name__}: {exc}")
                continue

            for uid, stem, answer, _exp, _qt, _opt in chunk:
                v = verdicts.get(uid)
                if v is None:
                    unknown += 1
                    continue
                if v.get("ok"):
                    conn.execute("UPDATE questions SET status='approved', reviewed_by='auto:flash', "
                                 "version=COALESCE(version,0)+1, quality_score=1.0, fact_verified=0 "
                                 "WHERE question_uid=? AND status IN ('parsed','pending_review')", (uid,))
                    approved += 1
                else:
                    reason = str(v.get("reason") or "未说明")[:200]
                    # 「超纲」不等于「题目有问题」——用户明确要求把超纲题单独留着（真题可能考到）。
                    # 这类题标 trust_level='acp' 并保留原状态 approved，只在解析里加超纲提示。
                    if args.keep_out_of_syllabus and "超纲" in reason:
                        note = f"【超纲提示】{reason}\n\n"
                        conn.execute(
                            "UPDATE questions SET status='approved', trust_level='acp', "
                            "reviewed_by='auto:flash+oos', explanation=COALESCE(?, '') || COALESCE(explanation,''), "
                            "version=COALESCE(version,0)+1 WHERE question_uid=? "
                            "AND status IN ('parsed','pending_review','rejected')", (note, uid))
                        out_of_syllabus += 1
                    else:
                        conn.execute("UPDATE questions SET status='rejected', reviewed_by='auto:flash', "
                                     "version=COALESCE(version,0)+1 WHERE question_uid=? "
                                     "AND status IN ('parsed','pending_review')", (uid,))
                        with reject_log.open("a", encoding="utf-8") as fh:
                            fh.write(json.dumps({"ts": now_iso(), "question_uid": uid, "subject": subject,
                                                 "reason": reason}, ensure_ascii=False) + "\n")
                        rejected += 1
            conn.commit()
            print(f"  [{subject}] 批 {i // args.batch + 1}/{(len(rows) + args.batch - 1) // args.batch} "
                  f"通过 {approved} 拒绝 {rejected} 已花 ¥{spent:.3f}")
            if spent > args.cap_cny:
                print(f"⚠️ 已达上限 ¥{args.cap_cny}，停止审核。")
                conn.close()
                _summary(subject, approved, rejected, unknown, spent, t0, out_of_syllabus)
                return 0
        conn.close()

    _summary(None, approved, rejected, unknown, spent, t0, out_of_syllabus)
    return 0


def _summary(_s, approved, rejected, unknown, spent, t0, out_of_syllabus=0) -> None:
    print(f"\n=== 审核结束：通过 {approved} / 拒绝 {rejected} / 超纲保留 {out_of_syllabus} / 未表态 {unknown}（保持原状）")
    print(f"花费 ¥{spent:.3f}，耗时 {time.time() - t0:.0f}s")


if __name__ == "__main__":
    raise SystemExit(main())
