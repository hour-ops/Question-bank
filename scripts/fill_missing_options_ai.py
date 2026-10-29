#!/usr/bin/env python
"""给「题干/解析里有 A、B、D 之类的字母答案，但从来没有选项正文」的客观题**补出选项**。

背景（2026-10-24 实测）：ACA 库里有 35 道早期 AI 生成的题，只生成了
`stem`（题面）、`answer`（如 `A、B、D`）、`explanation`（把每个选项讲了一遍），
**没有生成 `options`** —— 查 `generation_cache.sqlite` 里当初的原始输出确认过，
缓存里也没有。前端因此把它们渲染成文本框，点不了选项。

所以这里让模型**只做一件事**：按题面 + 参考答案 + 解析，把 A/B/C/D 四个选项的正文写出来。
成本极低（deepseek-flash，35 题约 ¥0.1），但生成完必须过校验，不合格的一律不要：

  ① 选项字母必须从 A 起连续，且数量 ≥ 参考答案里最大字母；
  ② 每项正文非空、去空白后不重复；
  ③ 系统提示里明确要求"干扰项必须与解析中判错理由一致"，校验端再核对
     解析里点名的字母集合与参考答案是否一致（不一致就丢弃，交人工）。

用法:
    python scripts/fill_missing_options_ai.py --limit 1 --dry-run      # 先看 1 条样例
    python scripts/fill_missing_options_ai.py --limit 1                # 真发 1 条（几分钱）
    python scripts/fill_missing_options_ai.py --apply                  # 全部生成并写库
    python scripts/fill_missing_options_ai.py --apply --data-dir "...便携版/data"
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
BACKUP = DATA / "backup"
MODEL = "deepseek-flash"
# 人民币/1M token（中转站 $0.30/$1.20 按 7.2 折算，再按峰时 ×2 上浮，宁可高估）
PRICE = {"in": 4.4, "out": 17.3}
EST_IN, EST_OUT = 500, 260          # 单个请求的预估 token

SYS = (
    "你是中文考试题库的编辑。用户会给你一道选择题的题面、参考答案（如 A、B、D）和解析。"
    "这道题**丢失了选项正文**，请严格依据解析把 A/B/C/D 四个选项的内容补写出来。\n"
    "硬性要求：\n"
    "1. 选项个数必须覆盖参考答案的最大字母（例如答案是 A、B、D，就输出 A/B/C/D 四项）；\n"
    "2. 与参考答案对应的选项必须写成**正确表述**，与解析中说明其正确的理由一致；\n"
    "3. 其余选项必须写成**明确错误的干扰项**，与解析里说明它错在哪里的理由一致；\n"
    "4. 每项 10–60 字，中文，不要重复题干，不要出现「以上都对/都不对」除非解析明确如此；\n"
    '5. 只输出 JSON：{"options": [{"key": "A", "text": "…"}, …]}，不要输出任何解释文字。'
)

_LETTER_SET = "ABCDEFGH"


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


def opt_count(raw) -> int:
    try:
        arr = json.loads(raw) if isinstance(raw, str) else raw
        return len(arr) if isinstance(arr, list) else 0
    except (TypeError, ValueError):
        return 0


def answer_letters(answer) -> str:
    return "".join(sorted({c for c in str(answer or "").upper() if c in _LETTER_SET}))


def targets(data_dir: Path, subject: str, limit: int) -> list[dict]:
    db = data_dir / f"{subject}.sqlite"
    if not db.exists():
        return []
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute(
        "SELECT id, question_uid, question_type, stem, answer, explanation, knowledge_point "
        "FROM questions WHERE status<>'archived' "
        "AND question_type IN ('single_choice','multiple_choice') "
        "AND (options IS NULL OR options='' OR options='[]') ORDER BY id")]
    con.close()
    if limit:
        rows = rows[:limit]
    return rows


def check(letters: str, opts: list[dict], explanation: str) -> tuple[bool, str]:
    keys = [str(o.get("key") or "").strip().upper() for o in opts]
    if len(keys) < 2 or keys != list(_LETTER_SET[: len(keys)]):
        return False, f"字母不合法 {keys}"
    if letters and max(letters) > keys[-1]:
        return False, f"参考答案 {letters} 超出选项范围"
    texts = [str(o.get("text") or "").strip() for o in opts]
    if any(not t for t in texts):
        return False, "有空选项"
    if len({re.sub(r"\s+", "", t) for t in texts}) != len(texts):
        return False, "选项重复"
    for t in texts:
        if not 4 <= len(t) <= 160:
            return False, f"选项长度异常({len(t)})"
    # 解析里点名的字母必须落在选项范围内。
    # ⚠️ 必须用「独立大写字母」而不是任意大写字母：解析里出现 "Few-shot" 时，
    #    F/E/W/H 都会被当成选项字母（实测 id=83 就是这么被误判丢弃的）。
    named = {m.group(0) for m in re.finditer(r"(?<![A-Za-z])[A-H](?![A-Za-z])", explanation)}
    if named and not named <= set(keys):
        return False, f"解析提到 {sorted(named)}，选项只有 {keys}"
    return True, "ok"


def main() -> int:
    ap = argparse.ArgumentParser(description="用 LLM 补出缺失的选项（默认 dry-run，不发请求）")
    ap.add_argument("--subject", default="aca_llm")
    ap.add_argument("--data-dir", default=str(DATA))
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 题（调试用）")
    ap.add_argument("--cap-cny", type=float, default=1.0, help="预估花费上限（元）")
    ap.add_argument("--apply", action="store_true", help="真写库（写前备份；不写则只生成提案 JSON）")
    ap.add_argument("--dry-run", action="store_true", help="连请求都不发")
    args = ap.parse_args()

    data_dir = Path(args.data_dir)
    items = targets(data_dir, args.subject, args.limit)
    est = len(items) * (EST_IN * PRICE["in"] + EST_OUT * PRICE["out"]) / 1_000_000
    print(f"待补选项 {len(items)} 题（{data_dir}/{args.subject}.sqlite），预估 ¥{est:.3f}（上限 ¥{args.cap_cny}）")
    if not items:
        return 0
    if est > args.cap_cny:
        print(f"拒绝执行：预估 ¥{est:.3f} > 上限 ¥{args.cap_cny}（可用 --cap-cny 提高）")
        return 2
    if args.dry_run:
        for it in items[:3]:
            print(f"  · id={it['id']} ans={it['answer']!r} stem={it['stem'][:50]!r}")
        print("dry-run：未发起请求。")
        return 0

    from openai import OpenAI

    env = load_env()
    if "DEEPSEEK_API_KEY" not in env:
        print("缺 DEEPSEEK_API_KEY（.env）")
        return 3
    client = OpenAI(api_key=env["DEEPSEEK_API_KEY"],
                    base_url=env.get("DEEPSEEK_BASE_URL") or "https://api.deepseek.com", timeout=120)

    LOGS.mkdir(parents=True, exist_ok=True)
    proposals, failed = [], []
    spent = 0.0
    for i, it in enumerate(items, 1):
        letters = answer_letters(it["answer"])
        payload = {
            "题面": it["stem"][:600],
            "参考答案": it["answer"],
            "解析": (it["explanation"] or "")[:800],
            "知识点": it["knowledge_point"] or "",
        }
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "system", "content": SYS},
                          {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
                response_format={"type": "json_object"},
                temperature=0,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[STOP] 第 {i} 题请求失败，按成本策略立即停手：{exc}")
            break
        usage = resp.usage.model_dump() if getattr(resp, "usage", None) else {}
        cost = ((usage.get("prompt_tokens", 0) or 0) * PRICE["in"]
                + (usage.get("completion_tokens", 0) or 0) * PRICE["out"]) / 1_000_000
        spent += cost
        with (LOGS / "cost_ledger.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"at": now_iso(), "task": "fill_missing_options", "model": MODEL,
                                 "subject": args.subject, "question_uid": it["question_uid"],
                                 "usage": usage, "cost_cny": round(cost, 6)}, ensure_ascii=False) + "\n")
        try:
            got = json.loads(resp.choices[0].message.content or "{}")
            opts = got.get("options") or []
        except Exception:  # noqa: BLE001
            opts = []
        ok, why = check(letters, opts, it["explanation"] or "")
        if ok:
            proposals.append({
                "uid": it["question_uid"], "id": it["id"], "answer": it["answer"],
                "options": [{"key": str(o["key"]).strip().upper(), "text": str(o["text"]).strip()} for o in opts],
            })
            print(f"  [{i}/{len(items)}] ✓ id={it['id']} {len(opts)} 选项")
        else:
            failed.append({"uid": it["question_uid"], "id": it["id"], "why": why, "raw": opts})
            print(f"  [{i}/{len(items)}] ✗ id={it['id']} {why}")

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    BACKUP.mkdir(parents=True, exist_ok=True)
    out = BACKUP / f"ai-options-{args.subject}-{stamp}.json"
    out.write_text(json.dumps(proposals, ensure_ascii=False, indent=2), encoding="utf-8")
    if failed:
        bad = BACKUP / f"ai-options-{args.subject}-{stamp}-failed.json"
        bad.write_text(json.dumps(failed, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"丢弃样例: {bad}")
    print(f"\n生成 {len(proposals)} 条，丢弃 {len(failed)} 条，实花 ¥{spent:.4f}")
    print(f"提案: {out}")

    if args.apply and proposals:
        db = data_dir / f"{args.subject}.sqlite"
        bak_dir = data_dir / "backup"
        bak_dir.mkdir(parents=True, exist_ok=True)
        bak = bak_dir / f"{db.stem}-{stamp}{db.suffix}"
        s = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        d = sqlite3.connect(str(bak))
        s.backup(d)
        d.close()
        s.close()
        print(f"[备份] {bak.name}")
        con = sqlite3.connect(str(db))
        con.execute("PRAGMA busy_timeout=30000")
        ts = now_iso()
        try:
            for p in proposals:
                con.execute("UPDATE questions SET options=?, reviewed_by=?, "
                            "version=COALESCE(version,1)+1 WHERE question_uid=?",
                            (json.dumps(p["options"], ensure_ascii=False),
                             f"auto:fill_options_ai({MODEL})@{ts}", p["uid"]))
            con.commit()
        finally:
            con.close()
        print(f"[已改库] 补选项 {len(proposals)} 题")
    elif proposals:
        print("（未写库：加 --apply，或用 fix_stem_options.py --from-json 合并写入）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
