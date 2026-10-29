#!/usr/bin/env python
"""阶段 5b · 判分同步（judge_queue 队列消费 → 判分 → 回写）。

用法:
    python scripts/sync_outbox.py [--mock] [--limit N] [--subject S] [--dry-run]

设计要点（依据 DESIGN.md 与 .tools/题库项目-决策记录.md）:
  1. 🔴 **官方 API 没有 Batch API**（/batches 全 404）→ 原设计的 `client.beta.batches.create`
     **作废**，改为**串行 `chat/completions`**；`judge_status='submitted'` 语义退化为"已进入本地串行队列"。
  2. **ACA 走本地规则判分**（`config/aca_rules.json`），**不调用 LLM**；其余科目用 LLM 判分。
  3. 判分档位固定 `effort=low`（思考 token 按输出计费，判分不需要长思考）。
  4. 回写四个位置：`judge_queue` / `attempts` / `wrong_book` / `daily_progress` 触发条件解耦——
     本脚本负责 judge_queue + attempts + **review_log + wrong_book**；`daily_progress` 由
     `update_daily_progress.py` 按 attempts 全量重算（不要在这里写，避免双写冲突）。
  5. 🔴 **集成契约（sm2_scheduler 依赖）**：
     - 作答事实源 = `review_log(question_uid, reviewed_at, result)`，`result` 取 `correct|wrong`
     - 只要写了 `wrong_book`，**必须同时写 `updated_at=now`**（它是 sm2 的事件水位）
  6. 失败**指数退避重试 3 次**（1s/2s/4s）→ 仍失败置 `judge_status='failed'`（UI 需可手动重投）。
  7. 每次调用把 token 用量与估算成本 append 到 `logs/cost_ledger.jsonl`（阶段 7 的 80% 闸门依赖它）。
  8. `--mock` 全程不联网、不读 key，用确定性启发式给分，用于链路自检。
"""

from __future__ import annotations

import argparse
import json
import os
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
ATTEMPTS_DB = DATA / "attempts.sqlite"
LEDGER = LOGS / "cost_ledger.jsonl"
SUBJECTS = ["english", "c_wuhan", "c_hbpu", "aca_llm"]

# 官方价目（元 / 百万 tokens，空闲时段；高峰翻倍）
PRICE = {
    "deepseek-flash": {"in": 1.0, "out": 4.0, "cache": 0.02},
    "deepseek-v4-pro": {"in": 4.5, "out": 13.5, "cache": 0.15},
}
MAX_RETRY = 3


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def load_env() -> dict[str, str]:
    if not ENV_FILE.exists():
        return {}
    out: dict[str, str] = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def log_cost(model: str, usage: dict, subject: str, note: str = "") -> None:
    price = PRICE.get(model)
    cost = 0.0
    if price and usage:
        pin = usage.get("prompt_tokens", 0) or 0
        pout = usage.get("completion_tokens", 0) or 0
        cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0) or 0
        cost = ((pin - cached) * price["in"] + cached * price["cache"] + pout * price["out"]) / 1_000_000
    LOGS.mkdir(parents=True, exist_ok=True)
    rec = {"ts": now_iso(), "stage": "sync_outbox", "kind": "llm_call", "subject": subject,
           "model": model, "usage": usage, "cost_cny": round(cost, 6), "note": note}
    with LEDGER.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


# ------------------------------------------------------------------ 判分


def load_judge_prompt() -> dict:
    p = ROOT / "config" / "judge_prompt.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass
    return {"version": "0.0", "prompts": {}}


def build_messages(subject: str, qtype: str, stem: str, answer: str, user_answer: str, prompt_cfg: dict) -> list[dict]:
    key = f"{subject}.{qtype}"
    sys_prompt = (prompt_cfg.get("prompts") or {}).get(key) or (prompt_cfg.get("prompts") or {}).get(subject) or (
        "你是严谨的阅卷老师。根据参考答案给学生的作答打分，只输出 JSON。"
    )
    user = (
        f"【题干】{stem}\n【参考答案】{answer}\n【学生作答】{user_answer}\n\n"
        '严格输出 JSON：{"score": <数字>, "full_score": <数字>, "reason": "<简短理由>"}'
    )
    return [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user}]


def judge_aca_local(subject: str, conn: sqlite3.Connection, q_uid: str, user_answer: str) -> tuple[float, str, str]:
    """ACA 本地规则判分（不调 LLM）。返回 (score, reason, model)。"""
    rules = json.loads((ROOT / "config" / "aca_rules.json").read_text(encoding="utf-8"))
    row = conn.execute("SELECT answer, question_type, options FROM questions WHERE question_uid=?", (q_uid,)).fetchone()
    if not row:
        return 0.0, "题目不存在", "local_rule"
    std, qtype, _opts = row
    norm = lambda s: "".join(sorted(set(re.findall(r"[A-H]", (s or "").upper()))))  # noqa: E731
    std_n, usr_n = norm(std), norm(user_answer)
    if not std_n:
        # 题库里没有标准答案 → 不能判"对"（防止空答案被计满分；被独立测试标为 KNOWN-ISSUE 的问题）
        return 0.0, "题库缺少标准答案（未获取）", "local_rule"
    if not usr_n:
        return 0.0, "未作答", "local_rule"
    if qtype == "multiple_choice":
        r = rules["multiple_choice"]
        if std_n and usr_n == std_n:
            return float(r["all_correct"]), "多选全对", "local_rule"
        if usr_n and set(usr_n) & set(std_n):
            return float(r.get("partial", 0.0)), "多选部分对（按规则不给部分分）", "local_rule"
        return float(r["wrong"]), "多选错误", "local_rule"
    r = rules["single_choice"]
    return (float(r["correct"]), "单选正确", "local_rule") if std_n == usr_n else (float(r["wrong"]), "单选错误", "local_rule")


def self_consistency_cfg(prompt_cfg: dict) -> dict:
    """读「自洽判分」配置（Self-Consistency）。

    目的：主观题（写作/翻译/简答）单次判分波动大。同一份作答用**多个温度**各判一次，
    分数取平均，能把单次采样噪声压下去（用户要求的"多温度采样取均值"）。
    配置写在 config/judge_prompt.json 的 self_consistency 段；没有就默认 3 次。
    """
    raw = prompt_cfg.get("self_consistency") or {}
    enabled = bool(raw.get("enabled", True))
    samples = 1 if not enabled else max(1, min(9, int(raw.get("samples") or 3)))
    temps = raw.get("temperatures") or [0.2, 0.6, 0.9]
    try:
        temps = [float(t) for t in temps][:samples]
    except (TypeError, ValueError):
        temps = [0.2, 0.6, 0.9][:samples]
    while len(temps) < samples:
        temps.append(0.0)
    return {"enabled": enabled, "samples": samples, "temperatures": temps,
            "aggregate": str(raw.get("aggregate") or "mean")}


def _merge_usage(total: dict, usage: dict) -> dict:
    for k, v in (usage or {}).items():
        if isinstance(v, (int, float)):
            total[k] = total.get(k, 0) + v
    return total


def judge_llm(mock: bool, subject: str, qtype: str, stem: str, answer: str, user_answer: str,
              prompt_cfg: dict, model: str, full: float = 1.0) -> tuple[float, str, dict]:
    """LLM 判分；mock=True 时用确定性启发式，完全不联网。

    ⚠️ mock 必须**按该题型满分折算**（`ratio * full`）：早期版本直接返回 0~1 比率，
    而英语 per_item 满分是 2/3/10 → `--mock` 下英语题**永远判 wrong**（全对也才 1.0），
    C 科因回落 1.0 反而判 correct —— 同一语义两种结果（被独立测试抓出）。

    🔁 非 mock 时走**自洽判分**：按 config 里的温度序列各判一次，分数取平均，
    理由里写明每次得分与分歧幅度（分歧大 = 这题判分本身不稳定，人工复核优先看）。
    """
    if mock:
        ua, ref = user_answer.strip(), (answer or "").strip()
        ratio = 1.0 if (ua and ua == ref) else (0.6 if ua and ref and ua[:5] in ref else 0.0)
        return ratio * full, f"[mock] 启发式 {ratio:.2f} × 满分 {full}", {"mock": True}
    from openai import OpenAI

    env = load_env()
    key = env.get("DEEPSEEK_API_KEY", "")
    base = env.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    if not key:
        raise RuntimeError("缺少 DEEPSEEK_API_KEY（题库项目/.env）")
    client = OpenAI(api_key=key, base_url=base, timeout=60)

    sc = self_consistency_cfg(prompt_cfg)
    scores: list[float] = []
    reasons: list[str] = []
    usage_total: dict = {}
    for temp in sc["temperatures"]:
        resp = client.chat.completions.create(
            model=model,
            messages=build_messages(subject, qtype, stem, answer, user_answer, prompt_cfg),
            reasoning_effort="low",          # 判分不需要长思考（省思考 token）
            response_format={"type": "json_object"},
            temperature=temp,
        )
        text = resp.choices[0].message.content or "{}"
        try:
            data = json.loads(text)
        except Exception:  # noqa: BLE001
            m = re.search(r"\{.*\}", text, re.S)
            data = json.loads(m.group(0)) if m else {}
        usage = resp.usage.model_dump() if getattr(resp, "usage", None) else {}
        _merge_usage(usage_total, usage)
        scores.append(max(0.0, min(float(full or 0) or 0, float(data.get("score", 0) or 0)))
                      if full else float(data.get("score", 0) or 0))
        reasons.append(str(data.get("reason", ""))[:300])

    if not scores:
        return 0.0, "判分失败（无有效采样）", usage_total
    if sc["aggregate"] == "median" and len(scores) >= 3:
        srt = sorted(scores)
        final = srt[len(srt) // 2] if len(srt) % 2 else (srt[len(srt) // 2 - 1] + srt[len(srt) // 2]) / 2
    else:
        final = sum(scores) / len(scores)
    spread = max(scores) - min(scores)
    detail = " / ".join(f"{s:g}" for s in scores)
    temps = ",".join(f"{t:g}" for t in sc["temperatures"])
    reason = (f"自洽判分（{len(scores)} 次采样 · 温度 {temps}）：{detail} → 均值 {final:.2f}"
              + (f"（分歧 {spread:g}，建议人工复核）" if spread > 0.5 else "（一致）")
              + ("；依据：" + reasons[0] if reasons and reasons[0] else ""))
    return round(final, 2), reason[:500], usage_total


# ------------------------------------------------------------------ 回写


def write_back(conn: sqlite3.Connection, subject: str, q_uid: str, attempt_id: str, score: float,
               full_score: float, model: str, reason: str, prompt_version: str) -> str:
    """回写 judge_queue + attempts + review_log，返回最终 judge_status。

    🔴 **不写 `wrong_book`** —— 那是 `sm2_scheduler` 的独占职责（避免两者争抢写入把
    sm2 的事件水位推到事件同一时刻，导致答错事件永不被 SM-2 处理）。
    """
    correct = score >= full_score * 0.999 if full_score else score > 0
    result = "correct" if correct else "wrong"
    ts = now_iso()

    conn.execute(
        """UPDATE judge_queue SET judge_score=?, judge_model=?, judge_reason=?,
             judge_status='synced', submitted_at=COALESCE(submitted_at, ?)
           WHERE attempt_id=?""",
        (score, model, reason, ts, attempt_id),
    )
    conn.execute(
        """UPDATE attempts SET judge_score=?, judge_model=?, judge_reason=?,
             judge_prompt_version=?, synced=1
           WHERE attempt_id=?""",
        (score, model, reason, prompt_version, attempt_id),
    )
    # 🔴 review_log 在**科目库**里（attempts 库只有 attempts/judge_queue）。
    # 🔴 只写 review_log，**绝不写 wrong_book**：wrong_book 由 sm2_scheduler 独占维护。
    #    原因（被独立测试抓出的 P0）：若此处也写 wrong_book 并把 updated_at 设为事件同一时刻，
    #    sm2 的水位判据 `reviewed_at > wrong_book.updated_at` 会把该事件永久判为 stale →
    #    **所有答错事件永远不会被 SM-2 处理**。单一写入者 = 单一事实源。
    subj_db = DATA / f"{subject}.sqlite"
    if not subj_db.exists():
        raise RuntimeError(f"科目库不存在: {subj_db}（先跑 scripts/init_db.py）")
    sconn = connect(subj_db)
    sconn.execute("INSERT INTO review_log(question_uid, reviewed_at, result) VALUES(?,?,?)", (q_uid, ts, result))
    sconn.commit()
    sconn.close()
    return "synced"


def full_score_for(subject: str, qtype: str) -> float:
    """该题型的满分。**从 config/taxonomy.json 读**（DESIGN.md 第 3 节：英语语法填空 2 分、
    翻译填空 3 分、写作 10 分；ACA 每题 2 分），读不到才回落到 1.0。

    早期版本把满分写死成 {aca:2, writing:10, 其余:1}，导致 2 分的题得 1.0 也被记成 correct。
    """
    try:
        tax = json.loads((ROOT / "config" / "taxonomy.json").read_text(encoding="utf-8"))
        cfg = (tax.get("subjects", {}).get(subject, {}) or {}).get("question_types", {}).get(qtype, {}) or {}
        for key in ("per_item", "score_correct", "score_all_correct"):
            v = cfg.get(key)
            if isinstance(v, (int, float)) and v > 0:
                return float(v)
    except Exception:  # noqa: BLE001
        pass
    return 1.0


def run(mock: bool, limit: int | None, subject: str | None, dry_run: bool,
        attempt_id: str | None = None) -> dict:
    stats = {"mock": mock, "dry_run": dry_run, "pending": 0, "synced": 0, "failed": 0, "skipped": 0, "subjects": {}}
    if not ATTEMPTS_DB.exists():
        stats["error"] = f"{ATTEMPTS_DB} 不存在（先跑 scripts/init_db.py）"
        return stats
    conn = connect(ATTEMPTS_DB)
    # 同时消费 'submitted'：那是"已进入本地串行队列"的中间态，若上一轮中断会残留，
    # 只认 'pending' 会让这些行被永久跳过（被独立测试指出）。
    sql = ("SELECT id, attempt_id, subject, question_uid, user_answer FROM judge_queue "
           "WHERE judge_status IN ('pending','submitted')")
    params: list = []
    if subject:
        sql += " AND subject=?"
        params.append(subject)
    if attempt_id:
        # 单题即时判分（刷题页提交后立刻出分用）：只处理这一条
        sql += " AND attempt_id=?"
        params.append(attempt_id)
    sql += " ORDER BY id"
    rows = conn.execute(sql, params).fetchall()
    if limit:
        rows = rows[:limit]
    stats["pending"] = len(rows)

    prompt_cfg = load_judge_prompt()
    version = prompt_cfg.get("version", "0.0")

    for _id, attempt_id, subj, q_uid, user_answer in rows:
        if dry_run:
            stats["skipped"] += 1
            continue
        # 取题干/答案（从科目库）。⚠️ 题目缺失不能"猜"（ACA 曾记 wrong、LLM 路径记 correct，
        #    同一数据缺失两种相反语义都进了 review_log）→ 直接标 failed 交人工处理，不进入判分。
        subj_db = DATA / f"{subj}.sqlite"
        lookup_err = ""
        r = None
        if not subj_db.exists():
            lookup_err = f"科目库不存在: {subj_db}"
        else:
            sc = connect(subj_db)
            r = sc.execute("SELECT stem, answer, question_type FROM questions WHERE question_uid=?", (q_uid,)).fetchone()
            sc.close()
            if not r:
                lookup_err = f"题目不存在: {subj}/{q_uid}"
        if lookup_err:
            conn.execute("UPDATE judge_queue SET judge_status='failed', judge_reason=? WHERE attempt_id=?",
                         (lookup_err[:500], attempt_id))
            conn.commit()
            stats["failed"] += 1
            stats.setdefault("lookup_failed", []).append(lookup_err)
            continue
        stem, answer, qtype = r[0] or "", r[1] or "", r[2] or "single_choice"

        model = "local_rule" if subj == "aca_llm" else ("deepseek-v4-pro" if qtype in {"writing", "programming"} else "deepseek-flash")
        full = full_score_for(subj, qtype)   # 提前算好：mock 也要按这个满分折算
        last_err = ""
        ok = False
        for attempt in range(1, MAX_RETRY + 1):
            try:
                if subj == "aca_llm":
                    sdb = connect(subj_db)
                    score, reason, used_model = judge_aca_local(subj, sdb, q_uid, user_answer or "")
                    sdb.close()
                    usage = {}
                else:
                    score, reason, usage = judge_llm(mock, subj, qtype, stem, answer, user_answer or "",
                                                     prompt_cfg, model, full)
                    used_model = model
                    if not mock and usage:
                        log_cost(model, usage, subj, note=f"{qtype}")
                write_back(conn, subj, q_uid, attempt_id, score, full, used_model, reason, version)
                conn.commit()
                ok = True
                stats["synced"] += 1
                stats["subjects"][subj] = stats["subjects"].get(subj, 0) + 1
                break
            except Exception as exc:  # noqa: BLE001
                last_err = f"{type(exc).__name__}: {exc}"
                if attempt < MAX_RETRY:
                    time.sleep(2 ** (attempt - 1))  # 1s, 2s, 4s
        if not ok:
            # 🔴 先回滚：否则这条 failed 的 commit 会把本轮重试里 attempts/judge_queue 的
            #    半成品一并提交（表现为 judge_status='failed' 却 judge_score 非空、synced=1，
            #    下游会误判"已判分"）——被独立测试抓出的 P1。
            conn.rollback()
            conn.execute("UPDATE judge_queue SET judge_status='failed', judge_reason=? WHERE attempt_id=?",
                         (f"retry {MAX_RETRY}x: {last_err}"[:500], attempt_id))
            conn.commit()
            stats["failed"] += 1
    conn.close()
    return stats


def positive_int(v: str) -> int:
    """`--limit` 必须是 >=1 的整数；`--limit 0` 语义含糊（曾被当成"不限量"）→ 直接拒绝。"""
    n = int(v)
    if n < 1:
        raise argparse.ArgumentTypeError("必须是 >=1 的整数（省略该参数表示不限量）")
    return n


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="判分队列消费（串行；ACA 本地规则，其余 LLM）")
    ap.add_argument("--mock", action="store_true", help="不联网，用确定性启发式给分（已按题型满分折算）")
    ap.add_argument("--limit", type=positive_int, default=None)
    ap.add_argument("--subject", default=None, choices=SUBJECTS)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--attempt-id", default=None, help="只判这一条 attempt（刷题页即时判分用）")
    args = ap.parse_args(argv)
    stats = run(args.mock, args.limit, args.subject, args.dry_run, args.attempt_id)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 1 if stats.get("error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
