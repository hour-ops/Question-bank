#!/usr/bin/env python
"""补齐 `questions.trust_level` 为空的题（**需求 5 的前提**：没有来源就画不出徽标）。

实测缺口（2026-10-13）：
  english 707 条 trust_level 为 NULL（其中 692 条连解释都没有）
  c_wuhan 64 条 / c_hbpu 64 条 / aca_llm 84 条

推断顺序（**只认有证据的，拿不准就留空并计数**）：
  1. `source_type='generate'` 或 `fact_source` 含「AI生成」 → `ai_generated`
  2. `source_type='real_exam'`，或 `exam_title` 里有年份/省份/「真题」→ `official_exam`
  3. `source_url` 命中第三方练习题域名白名单（zsbzt.cn / aihaoti.com 等）→ `third_party`
  4. `source_type='fetch'` 且有 `source_url` → `third_party`
  其余 → **保持 NULL**（不猜；页面显示「来源未标注」）

用法:
    python scripts/fix_trust_level.py                 # dry-run：只报告会怎么改
    python scripts/fix_trust_level.py --apply         # 写库（先自动备份）
    python scripts/fix_trust_level.py --subject english --apply
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
BACKUP = DATA / "backup"
SUBJECTS = ("english", "c_wuhan", "c_hbpu", "aca_llm")

# 已核实过的"第三方练习题"站点（来自 inbox/ 与源码注释；只用于**标注来源**，不影响正确性判断）
THIRD_PARTY_HOSTS = ("zsbzt.cn", "aihaoti.com", "csdn.net", "blog.csdn.net", "kaoshibao.com",
                     "examcoo.com", "zaixiankaoshi.com", "hbzsb.com", "zsb.hbzsb.com")
EXAM_HINTS = re.compile(r"真题|专升本|湖北|河北|武汉|理工学院|20\d\d\s*年|20\d\d[-—]\s*20\d\d")
AI_HINTS = re.compile(r"ai\s*生成|AI生成|gpt|大模型生成", re.I)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def infer(source_type: str, source_url: str, source_credit: str, exam_title: str,
          fact_source: str) -> str | None:
    """推断 trust_level；返回 None 表示"证据不足，保持未标注"。"""
    st = (source_type or "").strip().lower()
    fs = f"{fact_source or ''} {source_credit or ''}"
    url = (source_url or "").strip().lower()
    exam = (exam_title or "").strip()

    if st == "generate" or AI_HINTS.search(fs):
        return "ai_generated"
    if st == "real_exam" or EXAM_HINTS.search(exam):
        return "official_exam"
    if url and any(host in url for host in THIRD_PARTY_HOSTS):
        return "third_party"
    if st == "fetch" and url:
        return "third_party"
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="补齐 trust_level（默认 dry-run）")
    ap.add_argument("--subject", default=None, choices=list(SUBJECTS))
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    subjects = [args.subject] if args.subject else list(SUBJECTS)
    report: dict = {}
    for subj in subjects:
        path = DATA / f"{subj}.sqlite"
        if not path.exists():
            continue
        conn = sqlite3.connect(str(path))
        conn.execute("PRAGMA busy_timeout=30000")
        rows = conn.execute(
            "SELECT question_uid, COALESCE(source_type,''), COALESCE(source_url,''), "
            "COALESCE(source_credit,''), COALESCE(exam_title,''), COALESCE(fact_source,'') "
            "FROM questions WHERE trust_level IS NULL OR trim(trust_level)=''").fetchall()
        plan: list[tuple[str, str]] = []
        unknown = 0
        for uid, st, url, credit, exam, fs in rows:
            got = infer(st, url, credit, exam, fs)
            if got:
                plan.append((uid, got))
            else:
                unknown += 1
        by_kind: dict[str, int] = {}
        for _uid, kind in plan:
            by_kind[kind] = by_kind.get(kind, 0) + 1
        report[subj] = {"unlabeled": len(rows), "inferred": len(plan), "by_kind": by_kind,
                        "still_unknown": unknown}
        print(f"===== {subj}：未标注 {len(rows)} 条 → 可推断 {len(plan)} 条 {by_kind}，证据不足 {unknown} 条")
        if args.apply and plan:
            BACKUP.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            bak = BACKUP / f"{path.stem}-{stamp}{path.suffix}"
            shutil.copy2(path, bak)
            print(f"  [备份] {bak.name}")
            ts = now_iso()
            for uid, kind in plan:
                conn.execute("UPDATE questions SET trust_level=? WHERE question_uid=?",
                             (kind, uid))
            conn.commit()
            print(f"  [已改库] 标注 {len(plan)} 条（来源标记，非内容改动）")
        conn.close()

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    if not args.apply:
        print("\n（dry-run：未改库。加 --apply 才写入，写入前自动备份到 data/backup/）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
