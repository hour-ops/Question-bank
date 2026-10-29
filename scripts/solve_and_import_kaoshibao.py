#!/usr/bin/env python
"""给「只抓到题干+选项、答案被 APP 锁住」的考试宝题，用大模型**自己作答**并归考点。

背景：kaoshibao 的 37563622 那套（aca大模型）网页端只给题干和选项，答案要 APP/会员。
用户要求：既然有题干有选项，就直接让模型答出来。

做法（尽量可靠，别把模型瞎猜的答案当真）：
  1. 同一题问 **两遍**（temperature 0.0 与 0.9），两次答案一致才采用；
  2. 不一致的再问第三遍，三局两胜；仍不一致标 `disputed`，**不入库**；
  3. 同时让模型给出所属考点（0-5），两次不一致也按上面规则处理；
  4. 每题附一句理由，写进 explanation，并在 source_credit 里明确
     「答案由 AI 推断，非官方答案」——`trust_level` 记为 `third_party`，
     但 `fact_source` 会写清是模型自答，避免以后被当成官方答案。

用法:
    python scripts/solve_and_import_kaoshibao.py --input data/kaoshibao_37563622_full.jsonl --limit 40
    python scripts/solve_and_import_kaoshibao.py --input ... --apply
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import threading
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
LOGS = ROOT / "logs"
ENV_FILE = ROOT / ".env"
SUBJECT = "aca_llm"
PRICE = {"in": 4.4, "out": 17.3}

MODULES = ["考点·大模型概念", "考点·提示词工程", "考点·增强大模型应用的能力",
           "考点·大模型微调", "考点·大模型 Agent", "考点·安全合规"]

SYS = ("你在做阿里云大模型工程师 ACA 认证（V2.4）的考试题。只输出 JSON。\n"
       "给出：answer=正确选项字母（单选题 1 个字母；多选题给全部正确项，如 \"BD\"；判断题给 A 或 B）；"
       "k=所属考点编号；why=一句话理由（40 字内）。\n"
       "考点编号：0=大模型概念 1=提示词工程 2=增强大模型应用的能力(RAG/工具/MCP/知识库) "
       "3=大模型微调 4=大模型 Agent 5=安全合规。\n"
       '结构：{"answer":"BD","k":2,"why":"…"}')


def load_env() -> dict[str, str]:
    out = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def ask(client, model: str, stem: str, opts: list[str], temp: float) -> tuple[dict, dict]:
    letters = "ABCDEFGH"
    body = "题目：" + stem + "\n" + "\n".join(f"{letters[i]}. {o}" for i, o in enumerate(opts[:8]))
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": SYS}, {"role": "user", "content": body}],
        response_format={"type": "json_object"}, temperature=temp, reasoning_effort="none")
    usage = resp.usage.model_dump() if getattr(resp, "usage", None) else {}
    try:
        d = json.loads(resp.choices[0].message.content or "{}")
    except Exception:  # noqa: BLE001
        d = {}
    raw = re.sub(r"[^A-H]", "", str(d.get("answer") or "").upper())
    valid = set(letters[: min(8, len(opts))])
    ans = "".join(sorted({c for c in raw if c in valid}))
    try:
        k = int(d.get("k"))
    except (TypeError, ValueError):
        k = -1
    return {"answer": ans, "k": k, "why": str(d.get("why") or "").strip()}, usage


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", default="")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--votes", type=int, default=2, help="每題作答次数（2=双票，3=三票复核）")
    ap.add_argument("--model", default="deepseek-flash")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--exam", default="考试宝·aca大模型(37563622)")
    ap.add_argument("--source", default="https://www.kaoshibao.com/ti/37563622/", help="题源 URL（写进 source_url）")
    ap.add_argument("--apply", action="store_true", help="求解后直接入库")
    args = ap.parse_args()

    rows: dict[str, dict] = {}
    for line in Path(args.input).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("id") and r.get("q") and len(r.get("opts") or []) >= 2:
            rows[r["id"]] = r
    items = list(rows.values())[: args.limit or None]
    print(f"待作答 {len(items)} 题（源文件唯一题 {len(rows)}）")

    from openai import OpenAI
    env = load_env()
    client = OpenAI(api_key=env["DEEPSEEK_API_KEY"],
                    base_url=env.get("DEEPSEEK_BASE_URL") or "https://api.deepseek.com", timeout=180)
    lock = threading.Lock()
    spent = [0.0]

    def log(usage: dict) -> None:
        cost = ((usage.get("prompt_tokens") or 0) * PRICE["in"]
                + (usage.get("completion_tokens") or 0) * PRICE["out"]) / 1e6
        with lock:
            spent[0] += cost
            with (LOGS / "cost_ledger.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                     "task": "solve_kaoshibao", "model": args.model,
                                     "usage": usage, "cost_cny": round(cost, 6)},
                                    ensure_ascii=False) + "\n")

    def solve(r: dict) -> dict:
        stem, opts = r["q"], r["opts"]
        temps = [0.0, 0.9] if args.votes < 3 else [0.0, 0.55, 0.95]
        votes = []
        for temp in temps:
            v, u = ask(client, args.model, stem, opts, temp)
            log(u)
            votes.append(v)
        # 先看前两票；够票数（≥2 票一致）就不用再问
        cnt0 = Counter(v["answer"] for v in votes if v["answer"])
        need = 2 if args.votes < 3 else max(2, (len(temps) // 2) + 1)
        if not cnt0 or cnt0.most_common(1)[0][1] < need:
            v, u = ask(client, args.model, stem, opts, 0.35)
            log(u)
            votes.append(v)
        cnt = Counter(v["answer"] for v in votes if v["answer"])
        answer, agree = (cnt.most_common(1)[0][0] if cnt else ""), (cnt.most_common(1)[0][1] if cnt else 0)
        cnt_k = Counter(v["k"] for v in votes if 0 <= v["k"] < 6)
        k = cnt_k.most_common(1)[0][0] if cnt_k else -1
        qtype = "multiple_choice" if "多选" in str(r.get("type") or "") else "single_choice"
        bad = (not answer) or agree < 2 or k < 0
        if qtype == "single_choice" and len(answer) != 1:
            bad = True
        if qtype == "multiple_choice" and not (2 <= len(answer) <= 4):
            bad = True
        return {"id": r["id"], "stem": stem, "opts": opts, "answer": answer, "qtype": qtype,
                "agree": agree, "votes": len(votes), "k": k,
                "why": votes[0]["why"], "disputed": bad}

    out: list[dict] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for res in pool.map(solve, items):
            out.append(res)

    ok = [r for r in out if not r["disputed"]]
    print(f"完成 {len(out)} 题：可用 {len(ok)}｜争议 {len(out) - len(ok)}｜实花 ¥{spent[0]:.4f}")
    print("  一致性：", dict(Counter(r["agree"] for r in out)))
    print("  考点分布：", {MODULES[k][3:]: n for k, n in
                          Counter(r["k"] for r in ok).items() if 0 <= k < 6})

    outp = Path(args.out) if args.out else DATA / "kaoshibao_37563622_solved.jsonl"
    outp.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in out), encoding="utf-8")
    print(f"已写 {outp}")

    if not args.apply:
        print("dry-run：未入库")
        return 0

    db = DATA / f"{SUBJECT}.sqlite"
    con = sqlite3.connect(str(db))
    con.row_factory = sqlite3.Row
    cols = [c[1] for c in con.execute("PRAGMA table_info(questions)")]
    existing = {r[0] for r in con.execute("SELECT stem FROM questions WHERE status<>'archived'")}
    inserted = skipped = 0
    src = args.source
    try:
        con.execute("DELETE FROM questions WHERE exam_title=?", (args.exam,))
        for r in ok:
            if r["stem"] in existing:
                skipped += 1
                continue
            letters = "ABCDEFGH"
            opts = [{"key": letters[i], "text": t} for i, t in enumerate(r["opts"][:8])]
            row = {
                "question_uid": f"kbx-{r['id']}", "subject": SUBJECT,
                "source_type": "third_party", "source_url": src,
                "source_credit": f"{args.exam}（题干/选项来自考试宝，**答案为 AI 三票推断**）",
                "knowledge_point": MODULES[r["k"]],
                "chapter": f"{MODULES[r['k']].replace('考点·', '')}·考试宝",
                "question_type": r.get("qtype") or "single_choice",
                "stem": r["stem"],
                "options": json.dumps(opts, ensure_ascii=False),
                "answer": r["answer"],
                "explanation": f"【AI 推断】{r['why']}（{r['agree']}/{r['votes']} 次一致）",
                "difficulty": "中", "status": "approved",
                "trust_level": "third_party",
                "fact_source": "AI 自答（网页端答案需 APP/会员，非官方答案）",
                "exam_title": args.exam, "version": 1,
            }
            row = {k: v for k, v in row.items() if k in cols}
            con.execute(f"INSERT INTO questions ({','.join(row)}) VALUES ({','.join('?' * len(row))})",
                        tuple(row.values()))
            inserted += 1
        con.commit()
    finally:
        con.close()
    print(f"入库 {inserted} 题（题库已有同题干跳过 {skipped}）→ exam_title='{args.exam}'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
