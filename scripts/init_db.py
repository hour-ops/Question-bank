#!/usr/bin/env python
"""阶段 0 · 数据库初始化（幂等，可重复执行）。

创建 7 个 SQLite（4 科 + attempts + cache + generation_cache）：

  data/english.sqlite  data/c_wuhan.sqlite  data/c_hbpu.sqlite  data/aca_llm.sqlite
      questions / wrong_book / favorites / user_notes / daily_progress / review_log
  data/attempts.sqlite
      attempts / judge_queue （+ 两个索引）
  data/cache.sqlite
      fetched_urls / source_stats
  data/generation_cache.sqlite
      gen_cache

用法:
    python scripts/init_db.py [--verify]

说明:
- 每个库统一设置 PRAGMA journal_mode=WAL / busy_timeout=30000 / foreign_keys=ON
  （WAL 会写进库文件本身，后续连接自动继承；busy_timeout 需每次连接设置）。
- source_stats 是复核新增表：fetch.py 记录抓取量，parse_inbox.py 回写命中数，
  用于"命中率 < 0.2 的源标记为低频源、每周只抓 1 次"。
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SUBJECTS = ["english", "c_wuhan", "c_hbpu", "aca_llm"]

SUBJECT_SCHEMA = """
CREATE TABLE IF NOT EXISTS questions (
  id INTEGER PRIMARY KEY, question_uid TEXT UNIQUE, subject TEXT, school TEXT,
  year INTEGER, textbook TEXT, source_type TEXT, source_url TEXT,
  source_credit TEXT, chapter TEXT, knowledge_point TEXT,
  question_type TEXT, stem TEXT, options TEXT, answer TEXT, explanation TEXT,
  difficulty TEXT, code_template TEXT, test_cases TEXT,
  status TEXT CHECK(status IN ('raw','parsed','pending_review','approved','rejected','archived')) DEFAULT 'raw',
  reviewed_by TEXT, version INTEGER, syllabus_ref TEXT,
  fact_claim TEXT, fact_source TEXT, fact_verified INTEGER DEFAULT 0,
  quality_score REAL DEFAULT 0,
  group_uid TEXT, material_text TEXT, trust_level TEXT, exam_title TEXT
);
CREATE TABLE IF NOT EXISTS wrong_book (
  question_uid TEXT PRIMARY KEY, wrong_count INTEGER DEFAULT 0,
  correct_streak INTEGER DEFAULT 0, last_wrong_at TEXT, next_review_at TEXT,
  mastery INTEGER DEFAULT 0, notes TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS favorites (question_uid TEXT PRIMARY KEY, added_at TEXT);
CREATE TABLE IF NOT EXISTS user_notes (question_uid TEXT PRIMARY KEY, note TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS daily_progress (
  date TEXT PRIMARY KEY, total_done INTEGER DEFAULT 0, correct_count INTEGER DEFAULT 0,
  wrong_count INTEGER DEFAULT 0, subjects TEXT);
CREATE TABLE IF NOT EXISTS review_log (
  id INTEGER PRIMARY KEY, question_uid TEXT, reviewed_at TEXT, result TEXT);
CREATE INDEX IF NOT EXISTS idx_questions_status ON questions(status);
CREATE INDEX IF NOT EXISTS idx_questions_kp ON questions(knowledge_point);
CREATE INDEX IF NOT EXISTS idx_questions_type ON questions(subject, question_type);
"""

ATTEMPTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS attempts (
  attempt_id TEXT PRIMARY KEY, question_uid TEXT, subject TEXT, user_answer TEXT,
  judge_score REAL, judge_model TEXT, judge_reason TEXT, judge_prompt_version TEXT,
  elapsed_ms INTEGER, synced INTEGER DEFAULT 0, source_type TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS judge_queue (
  id INTEGER PRIMARY KEY, attempt_id TEXT, subject TEXT, question_uid TEXT,
  user_answer TEXT, judge_score REAL, judge_model TEXT, judge_reason TEXT,
  judge_status TEXT CHECK(judge_status IN ('pending','submitted','synced','failed')) DEFAULT 'pending',
  batch_id TEXT, submitted_at TEXT, source_type TEXT, created_at TEXT);
CREATE INDEX IF NOT EXISTS idx_judge_created ON judge_queue(created_at);
CREATE INDEX IF NOT EXISTS idx_judge_batch ON judge_queue(batch_id);
CREATE INDEX IF NOT EXISTS idx_judge_status ON judge_queue(judge_status);
CREATE INDEX IF NOT EXISTS idx_attempts_qid ON attempts(question_uid);
"""

# 真实库演进中新增的列（老库没有）。`CREATE TABLE IF NOT EXISTS` **不会**补列，
# 所以老库必须走 ALTER TABLE 迁移；缺了这些列 `/api/questions` 会直接 500
# （被 tests/test_web_ui.py 抓出：`no such column: group_uid`）。
MIGRATIONS = (
    ("questions", "group_uid", "TEXT"),
    ("questions", "material_text", "TEXT"),
    ("questions", "trust_level", "TEXT"),
    ("questions", "exam_title", "TEXT"),
)

CACHE_SCHEMA = """
CREATE TABLE IF NOT EXISTS fetched_urls (url TEXT PRIMARY KEY, fetched_at TEXT, source TEXT);
CREATE TABLE IF NOT EXISTS source_stats (
  subject TEXT, domain TEXT, fetched INTEGER DEFAULT 0, hits INTEGER DEFAULT 0,
  hit_rate REAL DEFAULT 0, last_fetch_at TEXT, low_freq INTEGER DEFAULT 0,
  PRIMARY KEY (subject, domain));
"""

GEN_SCHEMA = """
CREATE TABLE IF NOT EXISTS gen_cache (
  cache_key TEXT PRIMARY KEY, response TEXT, model TEXT,
  created_at TEXT, hit_count INTEGER DEFAULT 0);
"""


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def migrate_questions(conn: sqlite3.Connection) -> list[str]:
    """给老库补 `MIGRATIONS` 里的列（幂等）。返回本次真正补上的列名。"""
    have = {r[1] for r in conn.execute("PRAGMA table_info(questions)")}
    added: list[str] = []
    for table, column, coltype in MIGRATIONS:
        if table != "questions" or column in have:
            continue
        conn.execute(f"ALTER TABLE questions ADD COLUMN {column} {coltype}")
        added.append(column)
    if added:
        conn.commit()
    return added


def main() -> int:
    created: list[tuple[str, int]] = []

    for subject in SUBJECTS:
        p = DATA / f"{subject}.sqlite"
        conn = connect(p)
        conn.executescript(SUBJECT_SCHEMA)
        conn.commit()
        added = migrate_questions(conn)
        if added:
            print(f"  [migrate] {p.name}: 补列 {added}")
        n = conn.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
        conn.close()
        created.append((p.name, n))
        print(f"  [ok] {p.name}: {n} tables")

    for name, schema in [
        ("attempts.sqlite", ATTEMPTS_SCHEMA),
        ("cache.sqlite", CACHE_SCHEMA),
        ("generation_cache.sqlite", GEN_SCHEMA),
    ]:
        p = DATA / name
        conn = connect(p)
        conn.executescript(schema)
        conn.commit()
        n = conn.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
        conn.close()
        created.append((p.name, n))
        print(f"  [ok] {p.name}: {n} tables")

    dbs = sorted(DATA.glob("*.sqlite"))
    print(f"\nDB init done: {len(dbs)} sqlite files")
    for d in dbs:
        print(f"  - {d.name}")

    if "--verify" in sys.argv:
        expected = {"english.sqlite", "c_wuhan.sqlite", "c_hbpu.sqlite", "aca_llm.sqlite",
                    "attempts.sqlite", "cache.sqlite", "generation_cache.sqlite"}
        got = {d.name for d in dbs}
        missing = expected - got
        if missing:
            print(f"VERIFY FAIL: missing {sorted(missing)}")
            return 1
        print("VERIFY OK: 7/7")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
