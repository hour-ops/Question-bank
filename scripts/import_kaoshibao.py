#!/usr/bin/env python
"""把考试宝抓来的题库预览导入题库（**需求 13**：让 ACA 题目贴合考纲）。

数据来源：`inbox/_ingest/kaoshibao_<bankId>.jsonl`
  （由 `.tools/kaoshibao-scrape.mjs` + 浏览器页面 POST 到 `/api/ingest` 产生，
   每行一道题：`{qid, qtype, type_name, question, options, answer, analysis, difficulty}`）

站点事实（实测）：考试宝的题库预览页 `window.__NUXT__` 里**直接带选项、答案和解析**，
不需要登录、也不用点「查看答案」。所以这批题比之前从 CSDN/网页扒来的"第三方练习题"
（168 条里 130 条根本没有答案）质量高得多，`answer`/`analysis` 齐全。

导入口径（**可追溯、可重跑**）：
  - `question_uid = generate_uid(subject, source_url, stem)`（复用 `scripts/lib/uid.py`，全项目同一套规则）
  - `source_url = https://www.kaoshibao.com/ti/detail/<qid>.html`（逐题可回溯）
  - `trust_level = 'official_exam'`？**不是**：这里给 `third_party`，
    但 `source_credit` 记「考试宝题库预览(用户指定参照)」、`exam_title` 记题库名，
    理由：它是第三方整理稿，不是官方真题；标成 official_exam 会污染"只看真题"筛选。
    （用户要的是"贴合考纲"，这一点由 `knowledge_point` + 内容本身保证。）
  - `status`：默认 `pending_review`（要人工/自动审核过才进刷题池）；
    `--status approved` 可直接入库（答案+解析齐全时可用）。
  - **跨源查重**：`content_fingerprint()` 命中已有题 → 默认跳过，`--update-existing` 只补解析。

用法:
    python scripts/import_kaoshibao.py --file inbox/_ingest/kaoshibao_31210250.jsonl            # dry-run
    python scripts/import_kaoshibao.py --file ... --apply --status approved
    python scripts/import_kaoshibao.py --file ... --apply --update-existing
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SUBJECT = "aca_llm"
DB = DATA / f"{SUBJECT}.sqlite"
sys.path.insert(0, str(ROOT / "scripts"))
from lib.uid import generate_uid, content_fingerprint  # noqa: E402

# 考试宝 qtype → 本项目 question_type
QTYPE_MAP = {
    "1": "single_choice", "2": "multiple_choice", "3": "true_false",
    "14": "multiple_choice", "4": "reading_fill", "5": "reading_qa",
}
DIFFICULTY_MAP = {"1": "易", "2": "中", "3": "难"}
# 解析开头的模型自述（"Deepseek解析…" / "DeepSeek解析…"）→ 去掉，保持解释干净
ANALYSIS_PREFIX = re.compile(r"^\s*Deep\s*seek\s*解析\s*", re.I)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean_html_entities(text: str) -> str:
    """选项/题干里的 HTML 实体（站点把引号存成了 `&quot;` / `&#039;`）。"""
    s = str(text or "")
    for src, dst in (("&quot;", '"'), ("&#039;", "'"), ("&apos;", "'"), ("&amp;", "&"),
                     ("&lt;", "<"), ("&gt;", ">"), ("&nbsp;", " "), ("\\/", "/")):
        s = s.replace(src, dst)
    return s


def parse_options(raw: str) -> list[dict]:
    """考试宝的选项是 JSON 字符串 `[{"Key":"A","Value":"…"}]`。"""
    try:
        arr = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, json.JSONDecodeError):
        return []
    out = []
    for item in arr or []:
        if isinstance(item, dict):
            key = str(item.get("Key") or item.get("key") or "").strip().upper()
            val = clean_html_entities(item.get("Value") or item.get("value") or "").strip()
            if key and val:
                out.append({"key": key, "text": val})
    return out


def normalize_answer(raw: str, options: list[dict], qtype: str) -> str:
    """答案归一化：站点给的是字母（`"D"` / `"ABD"`）。

    多选题按本项目口径排序去重（`"BAD"` → `"ABD"`）。
    """
    s = re.sub(r"[^A-Za-z]", "", str(raw or "")).upper()
    if not s:
        return ""
    letters = sorted({ch for ch in s})
    return "".join(letters) if qtype == "multiple_choice" else "".join(letters)


def load_rows(path: Path) -> list[dict]:
    rows: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        qid = str(rec.get("qid") or "")
        if qid:
            rows[qid] = rec
    return list(rows.values())


def existing_fingerprints(conn: sqlite3.Connection) -> dict[str, str]:
    out: dict[str, str] = {}
    for uid, stem in conn.execute("SELECT question_uid, COALESCE(stem,'') FROM questions"):
        out.setdefault(content_fingerprint(SUBJECT, stem), str(uid))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="导入考试宝抓来的题目（需求 13）")
    ap.add_argument("--file", required=True, help="inbox/_ingest/*.jsonl")
    ap.add_argument("--bank-name", default="阿里云大模型 ACA 认证题库（考试宝预览）")
    ap.add_argument("--status", default="pending_review",
                    choices=["raw", "pending_review", "approved"])
    ap.add_argument("--apply", action="store_true", help="真写库（默认 dry-run）")
    ap.add_argument("--update-existing", action="store_true",
                    help="跨源重复题：只补 explanation（不改答案/选项）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--data-dir", default="", help="导入到指定数据目录（默认 题库项目/data；便携版可传其 data 路径）")
    args = ap.parse_args()

    if args.data_dir:
        global DATA, DB
        DATA = Path(args.data_dir)
        DB = DATA / f"{SUBJECT}.sqlite"
        print(f"[data-dir] {DB}")

    path = Path(args.file)
    if not path.is_absolute():
        path = ROOT / path
    if not path.exists():
        print(f"[error] 找不到 {path}", file=sys.stderr)
        return 2

    rows = load_rows(path)
    print(f"读入 {path.name}：{len(rows)} 题（已按 qid 去重）")

    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    known = existing_fingerprints(conn)

    plan_new, plan_dup, plan_bad = [], [], []
    for rec in rows:
        qid = str(rec.get("qid"))
        stem = clean_html_entities(rec.get("question") or "").strip()
        options = parse_options(rec.get("options"))
        qtype = QTYPE_MAP.get(str(rec.get("qtype") or ""), "")
        answer = normalize_answer(rec.get("answer"), options, qtype)
        expl = ANALYSIS_PREFIX.sub("", clean_html_entities(rec.get("analysis") or "")).strip()
        if not stem or not qtype or not options or not answer:
            plan_bad.append((qid, f"缺 {'题干' if not stem else ''}{'题型' if not qtype else ''}"
                                  f"{'选项' if not options else ''}{'答案' if not answer else ''}"))
            continue
        if len(options) < 2:
            plan_bad.append((qid, f"选项只有 {len(options)} 个"))
            continue
        fp = content_fingerprint(SUBJECT, stem)
        item = {"qid": qid, "stem": stem, "options": options, "answer": answer,
                "qtype": qtype, "explanation": expl,
                "difficulty": DIFFICULTY_MAP.get(str(rec.get("difficulty") or ""), "中"),
                "fingerprint": fp, "existing_uid": known.get(fp, "")}
        (plan_dup if fp in known else plan_new).append(item)

    print(f"  可导入 {len(plan_new)} 题｜跨源重复 {len(plan_dup)} 题｜不合格 {len(plan_bad)} 题")
    print(f"  题型分布：{dict(Counter(i['qtype'] for i in plan_new))}")
    print(f"  有解析：{sum(1 for i in plan_new if i['explanation'])}/{len(plan_new)}")
    for qid, why in plan_bad[:5]:
        print(f"    [跳过] {qid}: {why}")

    if not args.apply:
        print("\n（dry-run：未写库。加 --apply 才写入）")
        for item in plan_new[:2]:
            print(f"  样例：{item['stem'][:50]}… 选项={[o['key'] for o in item['options']]} "
                  f"答案={item['answer']} 解析={item['explanation'][:40]}…")
        if plan_dup:
            print(f"\n  跨源重复样例（命中库内已有题 → 不重复导入）：")
            for item in plan_dup[:4]:
                row = conn.execute("SELECT stem, status, trust_level FROM questions WHERE question_uid=?",
                                   (item["existing_uid"],)).fetchone()
                print(f"    · 抓取: {item['stem'][:44]}…")
                print(f"      库内: {str(row['stem'])[:44] if row else '(找不到?)'}… "
                      f"[{row['status'] if row else '-'}/{row['trust_level'] if row else '-'}]")
        conn.close()
        if args.json:
            print(json.dumps({"new": len(plan_new), "dup": len(plan_dup), "bad": len(plan_bad)},
                             ensure_ascii=False))
        return 0

    ts = now_iso()
    ins = 0
    for item in plan_new:
        uid = generate_uid(SUBJECT, f"https://www.kaoshibao.com/ti/detail/{item['qid']}.html",
                           item["stem"])
        try:
            conn.execute(
                "INSERT INTO questions(question_uid, subject, source_type, source_url, source_credit, "
                "question_type, stem, options, answer, explanation, difficulty, status, reviewed_by, "
                "version, fact_claim, fact_source, fact_verified, quality_score, trust_level, exam_title, "
                "knowledge_point) "
                "VALUES(?,?,'fetch',?,?,?,?,?,?,?,?,'pending_review','import_kaoshibao',1,"
                "'考试宝题库预览（用户指定参照）','https://www.kaoshibao.com/ti/31210250/',0,0,"
                "'third_party',?,'')",
                (uid, SUBJECT, f"https://www.kaoshibao.com/ti/detail/{item['qid']}.html",
                 "考试宝题库预览（用户指定对照）", item["qtype"], item["stem"],
                 json.dumps(item["options"], ensure_ascii=False), item["answer"],
                 item["explanation"], item["difficulty"], args.bank_name))
            ins += 1
        except sqlite3.IntegrityError as exc:
            print(f"  [跳过] {item['qid']}: {exc}")
    # 状态单独写，便于 --status 控制
    if ins and args.status != "pending_review":
        conn.execute("UPDATE questions SET status=? WHERE reviewed_by='import_kaoshibao' AND status='pending_review'",
                     (args.status,))
    upd = 0
    if args.update_existing:
        for item in plan_dup:
            if not item["explanation"]:
                continue
            cur = conn.execute("UPDATE questions SET explanation=? WHERE question_uid=? AND "
                               "(explanation IS NULL OR trim(explanation)='')",
                               (item["explanation"], item["existing_uid"]))
            upd += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
    conn.commit()
    stat = {f"{row[0]}/{row[1]}": row[2] for row in conn.execute(
        "SELECT trust_level, status, count(*) FROM questions "
        "WHERE reviewed_by='import_kaoshibao' GROUP BY 1,2")}
    conn.close()
    print(f"\n[已导入] 新增 {ins} 题（status={args.status}）｜补解析 {upd} 题")
    print(f"  本批入库统计（trust_level/status → 条数）：{stat}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
