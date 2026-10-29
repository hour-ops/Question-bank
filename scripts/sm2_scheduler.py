#!/usr/bin/env python
"""SM-2 复习排程（DESIGN.md 第 9 节：每 1h 跑，错开 15min；第 11 节：SM-2 复习机制）。

硬约束
------
**只写 `wrong_book` 表**（含 upsert 与 updated_at 水位）；`questions` 表**绝不触碰** ——
唯一入库入口是 `scripts/parse_inbox.py`。所有连接统一
`PRAGMA journal_mode=WAL` + `PRAGMA busy_timeout=30000`。

数据流
------
    作答结果来源 review_log(question_uid, reviewed_at, result)     ← 只读
        → 按 reviewed_at, id 顺序折叠事件 → 计算 SM-2 档位
        → 写回 wrong_book(question_uid, wrong_count, correct_streak,
                          last_wrong_at, next_review_at, mastery, updated_at)

**水位（watermark）= `wrong_book.updated_at`**，规则：
  1. 一次运行只处理 `reviewed_at <= 本次运行起点 now` 的事件（运行期间新写入的事件
     留到下一轮，**绝不重复应用**）；
  2. 只处理 `reviewed_at > 该行 updated_at` 的事件（已应用过的跳过，保证幂等）；
  3. 应用后统一写 `updated_at = now`（微秒精度 UTC ISO-8601）。

档位映射（`intervals_days = [1,3,7,14,30]`，档位 0..4）
------------------------------------------------------
  * **档位以 `mastery` 为准**（clamp 到 `[0, len-1]`）；`correct_streak` 只用于 ACA
    连对判定 + 展示。⚠️ 档位**不能**用 `correct_streak` 映射：降级会把 streak 清零，
    档位随即塌回 1 天档，后续"答对升级"就升不回原来那档（7 天档→3 天档后再答对应回
    7 天档）。`mastery` 为 0/NULL 时才用 `correct_streak` 兜底（判分脚本可能只写了它）。
  * **答对**：档位 n → n+1（`mastery+1`），`next_review_at = now + intervals[新档位]`，
    `correct_streak+1`。
  * **中途再错**：`downgrade_policy = step_back_one` → 回退一档（n → n-1，如 7 天档回到
    3 天档），`correct_streak = 0`、`wrong_count+1`；**不是**重置到 1 天。
  * **已是最高档且答对**：档位仍为 30 天档（`mastery+1` 会超出档位范围，索引时钳位），
    `next_review_at = now + 30 天`。
  * **ACA（subject=aca_llm）连续答对 `aca_exit_streak(=2)` 次**：视为掌握 → `mastery+1`
    且 `next_review_at = NULL`（移出到期队列）。**保留该行**是刻意的：行一旦删除，
    `updated_at` 水位随之消失，同一批 review_log 事件会在下一轮被重放。

用法
----
    python scripts/sm2_scheduler.py [--subject english|c_wuhan|c_hbpu|aca_llm|all] [--dry-run]

`--dry-run` 只打印将做的更新（subject / question_uid / 旧 next_review_at → 新），不写库。
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CONFIG = ROOT / "config" / "sm2_config.json"

SUBJECTS = ["english", "c_wuhan", "c_hbpu", "aca_llm"]
ACA_SUBJECT = "aca_llm"

DEFAULT_INTERVALS = (1, 3, 7, 14, 30)
DEFAULT_ACA_EXIT_STREAK = 2

POLICY_STEP_BACK = "step_back_one"
POLICY_RESET = "reset_to_one"
KNOWN_POLICIES = (POLICY_STEP_BACK, POLICY_RESET)

ACTION_UPGRADE = "upgrade"
ACTION_DOWNGRADE = "downgrade"
ACTION_KEEP_MAX = "keep_max"
ACTION_EXIT = "exit"
ACTION_FIRST_WRONG = "first_wrong"

# action → 统计字段
ACTION_STAT = {
    ACTION_UPGRADE: "upgraded",
    ACTION_DOWNGRADE: "downgraded",
    ACTION_KEEP_MAX: "kept_max",
    ACTION_EXIT: "exited",
    ACTION_FIRST_WRONG: "added",
}

ACTION_CN = {
    ACTION_UPGRADE: "升级",
    ACTION_DOWNGRADE: "降级",
    ACTION_KEEP_MAX: "最高档保持",
    ACTION_EXIT: "移出错题本",
    ACTION_FIRST_WRONG: "首次入错题本",
}

CORRECT_WORDS = {"correct", "right", "ok", "true", "yes", "pass", "passed", "correct_answer",
                 "1", "对", "正确", "答对", "掌握"}
WRONG_WORDS = {"wrong", "incorrect", "error", "false", "no", "fail", "failed", "0",
               "错", "错误", "答错", "不会"}

WRONG_BOOK_COLS = ("question_uid", "wrong_count", "correct_streak", "last_wrong_at",
                   "next_review_at", "mastery", "notes", "updated_at")


# --------------------------------------------------------------------- 基础工具


def connect(path: Path) -> sqlite3.Connection:
    """统一连接参数：WAL + busy_timeout=30000（DESIGN.md 第 6 节）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA foreign_keys=ON")  # 与 init_db.connect 对齐
    return conn


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def fmt_ts(dt: datetime | None) -> str | None:
    """UTC ISO-8601（微秒精度，便于与 review_log 秒级时间戳做字典序比较）。"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec="microseconds")


def disp(v: object) -> str:
    return str(v) if v else "(空)"


def _as_int(v: object) -> int:
    try:
        return int(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def normalize_result(result: object) -> bool | None:
    """把 review_log.result 归一化成 True(对) / False(错) / None(无法识别 → 跳过)。"""
    if result is None:
        return None
    if isinstance(result, bool):
        return result
    if isinstance(result, (int, float)):
        return bool(result)
    s = str(result).strip().lower()
    if not s:
        return None
    if s in CORRECT_WORDS:
        return True
    if s in WRONG_WORDS:
        return False
    return None


# --------------------------------------------------------------------- 配置 / 纯逻辑


def load_config(path: Path | None = None) -> dict:
    """读 config/sm2_config.json；缺字段回落默认值，非法值直接报错（不静默猜）。"""
    p = Path(path) if path is not None else CONFIG
    raw: dict = {}
    if p.exists():
        raw = json.loads(p.read_text(encoding="utf-8"))

    intervals = [int(x) for x in (raw.get("intervals_days") or DEFAULT_INTERVALS)]
    if not intervals or any(i <= 0 for i in intervals):
        raise ValueError(f"intervals_days 非法: {intervals}")
    if intervals != sorted(intervals):
        raise ValueError(f"intervals_days 必须递增: {intervals}")

    policy = str(raw.get("downgrade_policy") or POLICY_STEP_BACK)
    if policy not in KNOWN_POLICIES:
        raise ValueError(f"downgrade_policy 非法: {policy!r}（仅支持 {list(KNOWN_POLICIES)}）")

    exit_streak = _as_int(raw.get("aca_exit_streak")) or DEFAULT_ACA_EXIT_STREAK
    return {
        "path": str(p),
        "intervals_days": intervals,
        "aca_exit_streak": max(1, exit_streak),
        "downgrade_policy": policy,
        "notes": raw.get("notes", ""),
    }


def tier_of(correct_streak: object, n_tiers: int) -> int:
    """档位 = clamp(correct_streak, 0, n_tiers-1)。"""
    return max(0, min(_as_int(correct_streak), n_tiers - 1))


def current_tier(row: dict | None, n_tiers: int) -> int:
    """当前档位：以 mastery 为准；mastery 为 0/NULL 时用 correct_streak 兜底。

    ⚠️ 不能反过来用 correct_streak 当档位：降级会把 streak 清零，档位随即塌回
    1 天档，后续答对就升不回原来那一档。
    """
    old = row or {}
    mastery = _as_int(old.get("mastery"))
    if mastery > 0:
        return tier_of(mastery, n_tiers)
    return tier_of(old.get("correct_streak"), n_tiers)


def plan_event(row: dict | None, correct: bool, *, subject: str, cfg: dict,
               now: datetime, at: str | None = None) -> dict:
    """纯函数：给定 wrong_book 行状态 + 本次作答对错 → 计划（新行状态 + 动作名）。

    `row is None` 表示该题还不在错题本里（只可能由"答错"事件创建）。
    """
    intervals: list[int] = cfg["intervals_days"]
    now_s = fmt_ts(now)
    old = row or {}

    streak = _as_int(old.get("correct_streak"))
    mastery = _as_int(old.get("mastery"))
    cur = current_tier(old, len(intervals))
    # 升级基线：mastery 超过最高档（已毕业）时不能倒扣回低档
    base = max(mastery, cur)
    old_next = old.get("next_review_at")

    new = {
        "wrong_count": _as_int(old.get("wrong_count")),
        "correct_streak": streak,
        "last_wrong_at": old.get("last_wrong_at"),
        "next_review_at": old_next,
        "mastery": mastery,
        "updated_at": now_s,
    }
    new_tier: int | None = cur

    if correct:
        new_streak = streak + 1
        if subject == ACA_SUBJECT and new_streak >= cfg["aca_exit_streak"]:
            # ACA 连续答对达标 → 视为掌握，移出到期队列（保留行以维持水位）
            action, new_tier = ACTION_EXIT, None
            new.update(correct_streak=new_streak, mastery=base + 1, next_review_at=None)
        else:
            new_mastery = base + 1
            new_tier = tier_of(new_mastery, len(intervals))
            new["correct_streak"] = new_streak
            new["mastery"] = new_mastery
            if new_tier > cur:
                action = ACTION_UPGRADE                      # 升一档
            else:
                action = ACTION_KEEP_MAX                     # 已在最高档 → 保持 30 天档
            new["next_review_at"] = fmt_ts(now + timedelta(days=intervals[new_tier]))
    else:
        new["wrong_count"] = _as_int(old.get("wrong_count")) + 1
        new["correct_streak"] = 0
        new["last_wrong_at"] = at or now_s
        if row is None:
            action, new_tier = ACTION_FIRST_WRONG, 0
            new["mastery"] = 0
        else:
            action = ACTION_DOWNGRADE
            new_tier = 0 if cfg["downgrade_policy"] == POLICY_RESET else max(0, cur - 1)
            new["mastery"] = new_tier
        new["next_review_at"] = fmt_ts(now + timedelta(days=intervals[new_tier]))

    return {
        "action": action,
        "old_tier": cur,
        "new_tier": new_tier,
        "old_next_review_at": old_next,
        "new_next_review_at": new["next_review_at"],
        "row": new,
        "is_new_row": row is None,
    }


# --------------------------------------------------------------------- 读写


def load_wrong_book(conn: sqlite3.Connection) -> dict[str, dict]:
    if not table_exists(conn, "wrong_book"):
        return {}
    have = [c[1] for c in conn.execute("PRAGMA table_info(wrong_book)")]
    cols = [c for c in WRONG_BOOK_COLS if c in have]
    if "question_uid" not in cols:
        return {}
    out: dict[str, dict] = {}
    for rec in conn.execute(f"SELECT {','.join(cols)} FROM wrong_book"):
        d = dict(zip(cols, rec))
        for k in WRONG_BOOK_COLS:
            d.setdefault(k, None)
        out[str(d["question_uid"])] = d
    return out


def load_review_events(conn: sqlite3.Connection) -> list[dict]:
    """按 (reviewed_at, id) 升序读出全部作答结果事件（只读 review_log）。"""
    if not table_exists(conn, "review_log"):
        return []
    out: list[dict] = []
    for rid, uid, ts, result in conn.execute(
        "SELECT id, question_uid, reviewed_at, result FROM review_log "
        "ORDER BY COALESCE(reviewed_at, ''), id"
    ):
        if not uid:
            continue
        out.append({"id": rid, "question_uid": str(uid), "reviewed_at": ts or "", "result": result})
    return out


def upsert_row(conn: sqlite3.Connection, uid: str, row: dict) -> None:
    """唯一的写语句：只碰 wrong_book（notes 保留用户内容，不覆盖）。"""
    conn.execute(
        """
        INSERT INTO wrong_book(question_uid, wrong_count, correct_streak, last_wrong_at,
                               next_review_at, mastery, notes, updated_at)
        VALUES(?,?,?,?,?,?,NULL,?)
        ON CONFLICT(question_uid) DO UPDATE SET
            wrong_count    = excluded.wrong_count,
            correct_streak = excluded.correct_streak,
            last_wrong_at  = excluded.last_wrong_at,
            next_review_at = excluded.next_review_at,
            mastery        = excluded.mastery,
            updated_at     = excluded.updated_at
        """,
        (uid, row["wrong_count"], row["correct_streak"], row["last_wrong_at"],
         row["next_review_at"], row["mastery"], row["updated_at"]),
    )


# --------------------------------------------------------------------- 主流程


def process_subject(subject: str, *, cfg: dict, dry_run: bool,
                    data_dir: Path | None = None, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    now_s = fmt_ts(now)
    path = (Path(data_dir) if data_dir is not None else DATA) / f"{subject}.sqlite"
    stats = {"db": path.name, "events": 0, "processed": 0, "upgraded": 0, "downgraded": 0,
             "kept_max": 0, "exited": 0, "added": 0, "skipped": 0, "stale": 0,
             "deferred": 0, "changed_rows": 0}

    if not path.exists():
        stats["skipped_reason"] = "db 不存在"
        print(f"[{subject}] [skip] {path.name} 不存在，尚未 init_db")
        return stats

    conn = connect(path)
    try:
        if not table_exists(conn, "wrong_book"):
            stats["skipped_reason"] = "无 wrong_book 表"
            print(f"[{subject}] [skip] {path.name} 无 wrong_book 表")
            return stats

        rows = load_wrong_book(conn)
        events = load_review_events(conn)
        stats["events"] = len(events)
        watermark = {uid: (r.get("updated_at") or "") for uid, r in rows.items()}
        changed: dict[str, dict] = {}

        for ev in events:
            uid = ev["question_uid"]
            ts = ev["reviewed_at"]
            if ts > now_s:
                stats["deferred"] += 1          # 运行起点之后的事件 → 下一轮再处理
                continue
            if ts <= watermark.get(uid, ""):
                stats["stale"] += 1             # 已应用过（水位之内）
                continue

            correct = normalize_result(ev["result"])
            if correct is None:
                stats["skipped"] += 1
                print(f"  [skip] {uid}: 无法识别的 result={ev['result']!r}")
                continue

            cur_row = changed.get(uid) or rows.get(uid)
            if cur_row is None and correct:
                # 答对但不在错题本：不新建行（错题本只由答错事件创建）
                stats["skipped"] += 1
                print(f"  [skip] {uid}: 答对但不在错题本，不新建行")
                continue

            plan = plan_event(cur_row, correct, subject=subject, cfg=cfg, now=now, at=ts)
            tier_note = f" 档位{plan['old_tier']}→{plan['new_tier']}" if plan["new_tier"] is not None \
                else f" 档位{plan['old_tier']}→移出"
            tag = "dry-run" if dry_run else "apply"
            print(f"  [{tag}] {subject} {uid} next_review_at: "
                  f"{disp(plan['old_next_review_at'])} -> {disp(plan['new_next_review_at'])}"
                  f" ({ACTION_CN[plan['action']]}{tier_note})")

            if not dry_run:
                upsert_row(conn, uid, plan["row"])
            changed[uid] = plan["row"]
            stats["processed"] += 1
            stats[ACTION_STAT[plan["action"]]] += 1

        stats["changed_rows"] = len(changed)
        if not dry_run and changed:
            conn.commit()
    finally:
        conn.close()

    print(f"[{subject}] 处理 {stats['processed']} 条：升级 {stats['upgraded']} / "
          f"降级 {stats['downgraded']} / 最高档保持 {stats['kept_max']} / 移出 {stats['exited']} "
          f"（首次入本 {stats['added']}，跳过 {stats['skipped']}，已处理过 {stats['stale']}，"
          f"顺延 {stats['deferred']}）")
    return stats


def run(subject: str = "all", dry_run: bool = False, *, data_dir: Path | None = None,
        config_path: Path | None = None, now: datetime | None = None) -> dict:
    cfg = load_config(config_path)
    now = now or datetime.now(timezone.utc)
    subjects = list(SUBJECTS) if subject == "all" else [subject]

    print(f"SM-2 排程 {'[dry-run] 不写库' if dry_run else '[写入 wrong_book]'}")
    print(f"  配置   : {cfg['path']}")
    print(f"  档位   : {cfg['intervals_days']} 天；降级策略 {cfg['downgrade_policy']}；"
          f"ACA 移出连对数 {cfg['aca_exit_streak']}")
    print(f"  运行时刻: {fmt_ts(now)}（只处理该时刻之前的作答事件）")

    per_subject = {subj: process_subject(subj, cfg=cfg, dry_run=dry_run,
                                         data_dir=data_dir, now=now) for subj in subjects}
    totals = {k: sum(s.get(k, 0) for s in per_subject.values())
              for k in ("events", "processed", "upgraded", "downgraded", "kept_max",
                        "exited", "added", "skipped", "stale", "deferred", "changed_rows")}
    return {
        "subject": subject,
        "dry_run": dry_run,
        "now": fmt_ts(now),
        "config": {"path": cfg["path"], "intervals_days": cfg["intervals_days"],
                   "aca_exit_streak": cfg["aca_exit_streak"],
                   "downgrade_policy": cfg["downgrade_policy"]},
        "subjects": per_subject,
        "totals": totals,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="SM-2 复习排程：读 review_log → 计算档位 → 只写 wrong_book 表（不写 questions 表）")
    ap.add_argument("--subject", default="all", choices=SUBJECTS + ["all"],
                    help="科目（默认 all）")
    ap.add_argument("--dry-run", action="store_true",
                    help="只打印将做的更新（subject / question_uid / 旧 next_review_at → 新），不写库")
    args = ap.parse_args(argv)

    t0 = time.time()
    try:
        stats = run(args.subject, args.dry_run)
    except Exception as exc:  # noqa: BLE001
        print(f"[error] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    stats["elapsed_s"] = round(time.time() - t0, 1)

    print("\n=== 汇总 ===")
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
