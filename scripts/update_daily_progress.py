#!/usr/bin/env python
"""日进度聚合（**只写 `daily_progress`，绝不碰 `questions` 表**）。

用法:
    python scripts/update_daily_progress.py [--date YYYY-MM-DD] [--dry-run]
    # 测试用参数（默认走项目真实库）:
    #   --attempts-db PATH  覆盖 data/attempts.sqlite
    #   --data-dir PATH     覆盖科目库目录（默认 data/）

口径（与 DESIGN.md 第 6 / 8 / 10 节、config/aca_rules.json 一致）:

  1. 数据源 = `data/attempts.sqlite.attempts`，按 **本地时区** 的自然日过滤 `created_at`
     （支持 `YYYY-MM-DDTHH:MM:SS[+HH:MM|Z]`、空格分隔、无时区（视为本地）等写法；
     带时区的时间戳先换算到本地再取日期）。
  2. 聚合 = 按 **date + subject**；`total_done` = 当天该科目的 attempts **条数**。
  3. **对错判定 = `judge_correct()`（唯一入口，阈值集中在文件头部常量区）**:
     - ACA（`aca_llm`，本地规则判分，不调模型）：`judge_score >= 该题满分`；
       满分来自 **`config/aca_rules.json`**（`single_choice.correct = 2.0`、
       `multiple_choice.all_correct = 2.0`），读不到配置时回落到常量 `ACA_QUESTION_FULL_SCORE`。
     - 主观题（英语 / C 语言，LLM 判分）：`judge_score` 先归一化到 0–1
       （`<= 1` 视为判分模型已给 0–1 分，原样使用；`> 1` 时除以**该题满分**，并裁剪到 [0,1]），
       归一化得分 `>= SUBJECTIVE_PASS_RATIO`（0.8）记正确。
     - `judge_score IS NULL`（尚未判分）→ **既不计正确也不计错误**，单独计入 `unjudged`
       （即 `total_done = correct_count + wrong_count + unjudged`）。
  4. 「该题满分」解析顺序（`_resolve_full_score`，先具体后笼统）:
     ① 科目库 `questions` 表若带 `full_score`/`max_score`/`score` 列 → 用题目自带满分
     ② `config/taxonomy.json` 的 `subjects.<科目>.question_types.<题型>.full_score`（未来可配）
     ③ 本文件常量表 `SUBJECTIVE_FULL_SCORE[(科目, 题型)]` / `[(科目, "*")]`
     ④ 默认 `DEFAULT_SUBJECTIVE_FULL_SCORE`（= 1.0，即判分输出本身已归一化到 0–1）
     ⚠️ 若判分刻度改成百分制，务必在 ②/③ 里显式配置满分，否则 >1 的得分会按满分 1.0 处理
     （脚本会打印 `[warn]` 提示）。
  5. 输出 = 各科目库 `data/{subject}.sqlite` 的
     `daily_progress(date, total_done, correct_count, wrong_count, subjects)`；
     `subjects` 写该日该科目的**题型 / 来源 / 判分模型摘要**（JSON 字符串）。
     当天没有 attempts 的科目**不写行**（避免刷出无意义的 0 行）。
  6. **幂等**：每次按当天 attempts **全量重算** + `INSERT ... ON CONFLICT(date) DO UPDATE`
     覆盖式写入 → 重复跑同一天不会累加；有新增/回改的 attempts 时以重算结果为准。
  7. 所有 sqlite 连接 `PRAGMA busy_timeout=30000`；**可写**连接再设 `PRAGMA journal_mode=WAL`。
     只读连接（`--dry-run` 走只读）**不设 WAL** —— 只读连接改 journal_mode 会报错且可能写盘，
     而 `--dry-run` 的契约是「不落库」，因此 dry-run 下连 attempts 库也用只读 URI 打开。
     ⚠️ 已知边车行为（已实测）：对 **WAL 模式**的库做只读打开时，SQLite 需要 `-shm`
     共享内存索引，可能在 `data/` 下留下 **0 字节 `-wal` + `-shm`** 两个边车文件——**库内容零改动**
     （不建表、不写行、不改 journal_mode），且随后任何可写连接都会正常复用/清理它们。
  8. `--dry-run` 只打印将写入的行 + 一行 JSON 摘要（含 `"dry_run": true`），**不建表、不写行**。
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
ATTEMPTS_DB = DATA / "attempts.sqlite"
ACA_RULES = ROOT / "config" / "aca_rules.json"
TAXONOMY = ROOT / "config" / "taxonomy.json"

SUBJECTS = ["english", "c_wuhan", "c_hbpu", "aca_llm"]
ACA_SUBJECT = "aca_llm"

# ========================= 判分口径（全站唯一阈值集中处，改这里即可） =========================
# 主观题（英语 / C 语言）通过线：归一化到 0–1 后 >= 该比例记正确。
SUBJECTIVE_PASS_RATIO = 0.8
# ACA 每题满分兜底值（真值来自 config/aca_rules.json：单选 correct / 多选 all_correct）。
ACA_QUESTION_FULL_SCORE = 2.0
# 主观题默认满分：1.0 表示「判分模型输出的 judge_score 已经是 0–1 归一化分」。
DEFAULT_SUBJECTIVE_FULL_SCORE = 1.0
# 显式覆盖该题满分：{(科目, 题型): 满分}，("科目", "*") 为科目级默认。
# 例：判分改成 10 分制 → SUBJECTIVE_FULL_SCORE[("english", "*")] = 10.0
SUBJECTIVE_FULL_SCORE: dict[tuple[str, str], float] = {}
# 浮点比较容差（0.8 / 2.0 这类边界值不受二进制表示误差影响）。
EPS = 1e-9
# ==========================================================================================


# --------------------------------------------------------------------------- 时间

def local_tz():
    """本机本地时区（取当前时刻的偏移；用于把 UTC 时间戳换算成"本地自然日"）。"""
    return datetime.now().astimezone().tzinfo or timezone.utc


def today_local() -> str:
    return datetime.now(local_tz()).date().isoformat()


def parse_ts(value) -> datetime | None:
    """把 attempts.created_at 尽量解析成 **本地时区** 的 datetime，解析失败返回 None。

    兼容：`2026-10-11T09:15:00+08:00` / `...Z` / `2026-10-11 09:15:00`（无时区 → 视为本地）
    / `2026-10-11T09:15:00.123` / 只给日期。
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    s = s.replace("/", "-")
    if s.endswith(("Z", "z")):
        s = s[:-1] + "+00:00"
    if "T" not in s and " " in s:
        s = s.replace(" ", "T", 1)
    dt: datetime | None = None
    for cand in (s, s[:19], s[:10]):  # 依次退化：完整 → 截到秒 → 只取日期
        try:
            dt = datetime.fromisoformat(cand)
            break
        except ValueError:
            continue
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=local_tz())
    return dt.astimezone(local_tz())


def local_date(value) -> str | None:
    """时间戳 → 本地自然日 `YYYY-MM-DD`（解析失败返回 None）。"""
    dt = parse_ts(value)
    return dt.date().isoformat() if dt else None


def _day_prefixes(date_str: str) -> list[str]:
    """粗筛用的 `YYYY-MM-DD` 前缀（±1 天，覆盖所有时区偏移）。"""
    d = date.fromisoformat(date_str)
    return [(d + timedelta(days=off)).isoformat() for off in (-1, 0, 1)]


# --------------------------------------------------------------------------- 配置

def load_json(path) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError) as exc:
        print(f"  [warn] 读取配置失败 {path}: {exc}", file=sys.stderr)
        return {}


def load_aca_rules(path=None) -> dict:
    """读 `config/aca_rules.json`（ACA 满分/判分规则的唯一来源）。"""
    return load_json(path or ACA_RULES)


def aca_full_score(rules: dict | None = None, question_type: str | None = None) -> float:
    """ACA 该题满分（满分即正确线）：单选取 `single_choice.correct`，多选取 `multiple_choice.all_correct`。

    config/aca_rules.json 里两者都是 2.0；未知题型 / 配置缺字段 → 取两套规则的最大值兜底。
    """
    r = rules if isinstance(rules, dict) else {}
    qtype = (question_type or "").lower()
    multi = qtype in ("multiple_choice", "multi", "多选")
    key, field = ("multiple_choice", "all_correct") if multi else ("single_choice", "correct")
    try:
        val = float((r.get(key) or {}).get(field))
        if val > 0:
            return val
    except (TypeError, ValueError):
        pass
    best = ACA_QUESTION_FULL_SCORE
    for k, f in (("single_choice", "correct"), ("multiple_choice", "all_correct")):
        try:
            best = max(best, float((r.get(k) or {}).get(f)))
        except (TypeError, ValueError):
            continue
    return best


def _resolve_full_score(subject: str, question_type: str | None,
                        question_meta: dict | None = None,
                        taxonomy: dict | None = None) -> tuple[float, str]:
    """主观题「该题满分」→ (满分, 来源标签)。顺序见模块 docstring 第 4 条。"""
    meta = question_meta or {}
    for key in ("full_score", "max_score", "score"):  # ① 题目自带满分（schema 未来扩展）
        try:
            val = float(meta.get(key))
            if val > 0:
                return val, f"question.{key}"
        except (TypeError, ValueError):
            continue
    types = ((taxonomy or {}).get("subjects") or {}).get(subject, {}).get("question_types") or {}
    cfg = types.get(question_type or "") or {}
    for key in ("full_score", "score_full", "max_score"):  # ② taxonomy 显式配置
        try:
            val = float(cfg.get(key))
            if val > 0:
                return val, f"taxonomy.{key}"
        except (TypeError, ValueError):
            continue
    for key in ((subject, question_type or ""), (subject, "*")):  # ③ 脚本内常量表
        if key in SUBJECTIVE_FULL_SCORE:
            try:
                val = float(SUBJECTIVE_FULL_SCORE[key])
                if val > 0:
                    return val, "SUBJECTIVE_FULL_SCORE"
            except (TypeError, ValueError):
                continue
    return DEFAULT_SUBJECTIVE_FULL_SCORE, "default"  # ④ 默认：判分已归一化到 0–1


def subjective_full_score(subject: str, question_type: str | None = None,
                          question_meta: dict | None = None, taxonomy: dict | None = None) -> float:
    """该主观题满分（只返回数值；来源标签见 `_resolve_full_score`）。"""
    return _resolve_full_score(subject, question_type, question_meta, taxonomy)[0]


# --------------------------------------------------------------------------- 对错判定

def _to_float(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_subjective(judge_score, full_score: float = DEFAULT_SUBJECTIVE_FULL_SCORE) -> float:
    """主观题判分归一化到 0–1。

    - `judge_score <= 1`：判分模型已直接给 0–1 分 → 原样使用；
    - `judge_score > 1`：视为满分制打分 → 除以该题满分 `full_score`；
    - 结果裁剪到 [0, 1]（防判分模型给出超满分/负分）。
    """
    score = _to_float(judge_score)
    if score is None or score <= 0:
        return 0.0
    if score > 1.0 and full_score and float(full_score) > 0:
        score = score / float(full_score)
    return max(0.0, min(1.0, score))


def judge_correct(subject: str, judge_score, *, question_type: str | None = None,
                  full_score: float | None = None, aca: dict | None = None) -> bool:
    """**对错判定唯一入口**（口径见模块 docstring 第 3 条）。

    - `subject == aca_llm` → `judge_score >= 该题满分`（满分来自 config/aca_rules.json）；
    - 其余科目（主观题）→ 归一化到 0–1 后 `>= SUBJECTIVE_PASS_RATIO` 记正确；
    - `judge_score` 为 None / 非法 → False（未判分，调用方按 `unjudged` 单独计数）。
    """
    score = _to_float(judge_score)
    if score is None:
        return False
    if subject == ACA_SUBJECT:
        need = full_score if full_score else aca_full_score(aca, question_type)
        return score >= float(need) - EPS
    need = full_score if full_score else DEFAULT_SUBJECTIVE_FULL_SCORE
    return normalize_subjective(score, need) >= SUBJECTIVE_PASS_RATIO - EPS


# --------------------------------------------------------------------------- DB

def connect(path, readonly: bool = False) -> sqlite3.Connection:
    """打开 sqlite；统一 `busy_timeout=30000`，可写连接再设 `journal_mode=WAL`。

    readonly=True → `file:...?mode=ro` URI（且不设 WAL）：保证 `--dry-run` 不写盘、
    不新建 `-wal` / `-shm`。
    """
    p = Path(path)
    if readonly:
        conn = sqlite3.connect(p.resolve().as_uri() + "?mode=ro", uri=True)
    else:
        conn = sqlite3.connect(str(p))
    conn.execute("PRAGMA busy_timeout=30000")
    if not readonly:
        conn.execute("PRAGMA journal_mode=WAL")
    return conn


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
    return row is not None


def columns_of(conn: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]


def fetch_attempts(conn: sqlite3.Connection, date_str: str) -> list[dict]:
    """取当天（本地自然日）的 attempts 行。

    先用 `substr(created_at,1,10) IN (±1 天)` 粗筛（少扫全表），再在 Python 里按
    本地时区精确过滤；列名按实际 schema 探测，schema 未来加列（如 `full_score`）也不报错。
    """
    cols = columns_of(conn, "attempts")
    wanted = ["attempt_id", "question_uid", "subject", "judge_score", "judge_model",
              "source_type", "created_at"]
    select = [c for c in wanted if c in cols]
    for extra in ("full_score", "max_score"):  # 可选列（未来 schema 扩展）
        if extra in cols and extra not in select:
            select.append(extra)
    if "created_at" not in select:
        raise RuntimeError("attempts 表缺少 created_at 列")
    sql = (
        f"SELECT {', '.join(select)} FROM attempts "
        "WHERE substr(created_at,1,10) IN (?,?,?) OR created_at IS NULL OR length(created_at) < 10"
    )
    out: list[dict] = []
    for row in conn.execute(sql, _day_prefixes(date_str)):
        rec = dict(zip(select, row))
        if local_date(rec.get("created_at")) == date_str:
            out.append(rec)
    return out


def read_question_meta(conn: sqlite3.Connection) -> dict[str, dict]:
    """科目库 `questions` → {question_uid: {question_type, [full_score/max_score/score]}}（**只读**）。"""
    if not table_exists(conn, "questions"):
        return {}
    cols = columns_of(conn, "questions")
    select = ["question_uid"] + [c for c in ("question_type", "full_score", "max_score", "score") if c in cols]
    out: dict[str, dict] = {}
    for row in conn.execute(f"SELECT {', '.join(select)} FROM questions"):
        rec = dict(zip(select, row))
        uid = rec.pop("question_uid", None)
        if uid:
            out[uid] = {k: v for k, v in rec.items() if v is not None}
    return out


def read_question_meta_ro(db_path) -> dict[str, dict]:
    """`--dry-run` 用：只读打开科目库取题型表（打不开则返回 {}，不影响 dry-run 输出）。"""
    p = Path(db_path)
    if not p.exists():
        return {}
    try:
        conn = connect(p, readonly=True)
    except sqlite3.Error as exc:
        print(f"  [warn] 只读打开 {p} 失败（题型分布将标 unknown）: {exc}", file=sys.stderr)
        return {}
    try:
        return read_question_meta(conn)
    finally:
        conn.close()


# --------------------------------------------------------------------------- 聚合

def aggregate_rows(subject: str, rows: list[dict], *, question_meta: dict | None = None,
                   taxonomy: dict | None = None, aca: dict | None = None) -> dict:
    """把某科目当天的 attempts 聚合成 `daily_progress` 的一行（**纯函数，不落库**）。"""
    qmeta_all = question_meta or {}
    correct = wrong = unjudged = 0
    qtypes: Counter = Counter()
    sources: Counter = Counter()
    models: Counter = Counter()
    default_scale_hits = 0  # 得分 >1 但满分未配置 → 按默认满分 1.0 处理（需提示）

    for rec in rows:
        meta = qmeta_all.get(rec.get("question_uid")) or {}
        qtype = meta.get("question_type")
        score = _to_float(rec.get("judge_score"))

        if subject == ACA_SUBJECT:
            full = aca_full_score(aca, qtype)  # ACA：满分只认 config/aca_rules.json
        else:
            full, src = _resolve_full_score(subject, qtype, meta, taxonomy)
            if src == "default" and score is not None and score > 1.0:
                default_scale_hits += 1

        if score is None:
            unjudged += 1
        elif judge_correct(subject, score, question_type=qtype, full_score=full, aca=aca):
            correct += 1
        else:
            wrong += 1

        qtypes[qtype or "unknown"] += 1
        sources[rec.get("source_type") or "unknown"] += 1
        models[rec.get("judge_model") or "unknown"] += 1

    subjects_json = json.dumps({
        "subject": subject,
        "question_types": dict(sorted(qtypes.items())),
        "source_types": dict(sorted(sources.items())),
        "judge_models": dict(sorted(models.items())),
        "correct": correct,
        "wrong": wrong,
        "unjudged": unjudged,
    }, ensure_ascii=False, sort_keys=True)

    return {
        "subject": subject,
        "total_done": len(rows),
        "correct_count": correct,
        "wrong_count": wrong,
        "unjudged": unjudged,
        "subjects": subjects_json,
        "default_scale_hits": default_scale_hits,
    }


# --------------------------------------------------------------------------- 落库

def ensure_daily_progress(conn: sqlite3.Connection) -> None:
    """建 daily_progress（与 scripts/init_db.py 的 DDL 一致；**不碰 questions 表**）。"""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS daily_progress ("
        "date TEXT PRIMARY KEY, total_done INTEGER DEFAULT 0, correct_count INTEGER DEFAULT 0, "
        "wrong_count INTEGER DEFAULT 0, subjects TEXT)"
    )


def upsert_progress(conn: sqlite3.Connection, date_str: str, agg: dict) -> None:
    """覆盖式写入：同一天重复跑 → 按最新 attempts 重算结果覆盖（不累加）。"""
    conn.execute(
        "INSERT INTO daily_progress(date, total_done, correct_count, wrong_count, subjects) "
        "VALUES(?,?,?,?,?) "
        "ON CONFLICT(date) DO UPDATE SET total_done=excluded.total_done, "
        "correct_count=excluded.correct_count, wrong_count=excluded.wrong_count, "
        "subjects=excluded.subjects",
        (date_str, agg["total_done"], agg["correct_count"], agg["wrong_count"], agg["subjects"]),
    )


# --------------------------------------------------------------------------- CLI

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="update_daily_progress.py",
        description="按 date+subject 聚合 attempts → 各科目库 daily_progress（幂等，覆盖式写入）",
    )
    ap.add_argument("--date", metavar="YYYY-MM-DD", default=None, help="统计日期（默认今天，按本地时区）")
    ap.add_argument("--dry-run", action="store_true", help="只打印将写入的行，不落库")
    ap.add_argument("--attempts-db", default=None, help="（测试用）覆盖 data/attempts.sqlite 路径")
    ap.add_argument("--data-dir", default=None, help="（测试用）覆盖科目库所在目录（默认 data/）")
    return ap


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return path.name


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    date_str = args.date or today_local()
    try:
        date.fromisoformat(date_str)
    except ValueError:
        print(f"[error] 日期格式非法: {date_str!r}（应为 YYYY-MM-DD）", file=sys.stderr)
        return 2

    attempts_db = Path(args.attempts_db).resolve() if args.attempts_db else ATTEMPTS_DB
    data_dir = Path(args.data_dir).resolve() if args.data_dir else DATA
    dry = bool(args.dry_run)

    if not attempts_db.exists():
        print(f"[error] attempts 库不存在: {attempts_db}（先跑 scripts/init_db.py）", file=sys.stderr)
        return 2

    # dry-run 连 attempts 库都用只读打开：保证一行都不写。
    try:
        aconn = connect(attempts_db, readonly=dry)
    except sqlite3.Error as exc:
        print(f"[error] 打开 {attempts_db} 失败: {exc}", file=sys.stderr)
        return 2
    try:
        if not table_exists(aconn, "attempts"):
            print(f"[error] {attempts_db.name} 缺 attempts 表（先跑 scripts/init_db.py）", file=sys.stderr)
            return 2
        rows = fetch_attempts(aconn, date_str)
    finally:
        aconn.close()

    by_subject: dict[str, list[dict]] = defaultdict(list)
    for rec in rows:
        subj = str(rec.get("subject") or "").strip()
        if subj:
            by_subject[subj].append(rec)

    aca = load_aca_rules()
    taxonomy = load_json(TAXONOMY)
    results: list[dict] = []
    warnings: list[str] = []

    for subject in sorted(by_subject):
        if not re.fullmatch(r"[A-Za-z0-9_]+", subject):
            warnings.append(f"科目名非法，已跳过: {subject!r}")
            continue
        db_path = data_dir / f"{subject}.sqlite"
        if not db_path.exists():
            warnings.append(f"科目库不存在，已跳过: {_rel(db_path)}")
            continue
        if subject not in SUBJECTS:
            warnings.append(f"未知科目 {subject}（不在 DESIGN.md 科目表内，按同名库处理）")

        if dry:
            qmeta = read_question_meta_ro(db_path)
            agg = aggregate_rows(subject, by_subject[subject], question_meta=qmeta,
                                 taxonomy=taxonomy, aca=aca)
        else:
            conn = connect(db_path)
            try:
                ensure_daily_progress(conn)
                qmeta = read_question_meta(conn)
                agg = aggregate_rows(subject, by_subject[subject], question_meta=qmeta,
                                     taxonomy=taxonomy, aca=aca)
                upsert_progress(conn, date_str, agg)
                conn.commit()
            finally:
                conn.close()

        agg["date"] = date_str
        agg["db"] = _rel(db_path)
        results.append(agg)

    # ------------------------------------------------------------------ 输出
    tag = "dry-run" if dry else "write"
    print(f"[update_daily_progress] date={date_str} attempts={len(rows)} "
          f"subjects={len(results)} dry_run={dry}")
    for agg in results:
        print(f"  [{tag}] {agg['subject']:<9} total={agg['total_done']} "
              f"correct={agg['correct_count']} wrong={agg['wrong_count']} "
              f"unjudged={agg['unjudged']} -> {agg['db']}")
        print(f"           subjects={agg['subjects']}")
    if not results:
        print("  （当天没有可写入的 attempts）")
    for w in warnings:
        print(f"  [warn] {w}")
    hits = sum(a["default_scale_hits"] for a in results)
    if hits:
        print(f"  [warn] {hits} 条主观题得分 >1 但该题满分未配置（按默认满分 "
              f"{DEFAULT_SUBJECTIVE_FULL_SCORE} 处理）→ 请在 SUBJECTIVE_FULL_SCORE 或 "
              f"config/taxonomy.json 的 question_types.<题型>.full_score 里显式配置满分",
              file=sys.stderr)

    print(json.dumps({
        "date": date_str,
        "dry_run": dry,
        "attempts": len(rows),
        "rows": [{k: v for k, v in a.items() if k != "default_scale_hits"} for a in results],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
