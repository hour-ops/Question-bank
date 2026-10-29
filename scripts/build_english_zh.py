#!/usr/bin/env python
"""给英语题库预生成「中文译文」和「单词词表」，落到本地库，之后点词/看译文都是 0 元。

为什么是预生成而不是实时调 API：
  全库题干 + 阅读材料共 21.7 万字符（4,658 个不同单词），一次性翻完约 ¥1.5，
  之后每次点击只读本地 sqlite —— 毫秒级、断网可用。实时调 API 每题要 2–5 秒
  且按次计费，刷一年下来是预生成的上百倍。

产物 `data/english_zh.sqlite`：
  translations(doc_key PK, kind, source, zh, model, created_at)
      doc_key = "m:<材料 sha1 前 16 位>" 或 "s:<question_uid>"
      （材料被同一篇短文的多个小题共享，所以按内容哈希存，天然复用）
  glossary(word PK, pos, zh)
      只收录题库里**实际出现过的**词（4,658 个），不是整本词典

用法:
    python scripts/build_english_zh.py --materials            # dry-run 看要翻多少
    python scripts/build_english_zh.py --materials --apply    # 真跑（写 cost_ledger）
    python scripts/build_english_zh.py --all --apply --cap-cny 3
    python scripts/build_english_zh.py --glossary --apply --limit-batches 1   # 先试 1 批
断点续跑：已存在的 doc_key 直接跳过，中断后重跑即可。
"""

from __future__ import annotations

import argparse
import hashlib
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
OUT_DB = DATA / "english_zh.sqlite"
MODEL = "deepseek-flash"
# CNY / 1M token（中转站 $0.30/$1.20 按 7.2 折算，峰时再 ×2 上浮）
PRICE = {"in": 4.4, "out": 17.3}

SYS_TRANSLATE = (
    "你是英语教学翻译。把用户给的英文逐条译成通顺、忠实的中文。要求：\n"
    "1. 保留原意与语气，不要增删信息，不要写解释；\n"
    "2. 段落之间用 \\n 保留原分段；\n"
    "3. 人名/地名/机构名用通行译名，没有通行的保留原文；\n"
    "4. 只输出 JSON：{\"items\": [{\"id\": \"<原样返回>\", \"zh\": \"<中文译文>\"}]}，不要别的文字。"
)

SYS_GLOSSARY = (
    "你是英汉词典编者。用户给一批英文单词，逐个给出**词性 + 简明中文释义**。要求：\n"
    "1. 释义 2–20 字，按常用义项优先，最多 3 个义项，用「；」分隔；\n"
    "2. 词性用缩写 n. / v. / adj. / adv. / prep. / conj. / pron. / num. 等；\n"
    "3. 只输出 JSON：{\"items\": [{\"w\": \"<原样返回的单词>\", \"pos\": \"n.\", \"zh\": \"树木\"}]}。"
)

CJK_RE = re.compile(r"[\u4e00-\u9fff]")
WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]*")


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


def doc_key_material(text: str) -> str:
    return "m:" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def ensure_db() -> sqlite3.Connection:
    DATA.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(OUT_DB))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""CREATE TABLE IF NOT EXISTS translations (
        doc_key TEXT PRIMARY KEY, kind TEXT, source TEXT, zh TEXT,
        model TEXT, created_at TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS glossary (
        word TEXT PRIMARY KEY, pos TEXT, zh TEXT, model TEXT, created_at TEXT)""")
    conn.commit()
    return conn


def collect(subject: str = "english", min_stem: int = 0, skip_types: str = ""):
    """从科目库取出要翻译的材料块与题干（只读）。"""
    db = DATA / f"{subject}.sqlite"
    if not db.exists():
        sys.exit(f"找不到 {db}")
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = list(con.execute(
        "SELECT question_uid, question_type, COALESCE(stem,'') AS stem, "
        "COALESCE(material_text,'') AS material FROM questions WHERE status<>'archived'"))
    con.close()

    materials: dict[str, str] = {}
    stems: dict[str, str] = {}
    skipped = {s.strip() for s in skip_types.split(",") if s.strip()}
    for r in rows:
        mat = r["material"].strip()
        if mat:
            materials.setdefault(doc_key_material(mat), mat)
        stem = r["stem"].strip()
        # 连词成句的题干是打乱的词串、太短的是「21. ____」这种占位、指定题型整体跳过
        if (stem and r["question_type"] != "sentence_build"
                and r["question_type"] not in skipped and len(stem) >= min_stem):
            stems.setdefault("s:" + r["question_uid"], stem)
    words: dict[str, str] = {}
    for text in list(materials.values()) + list(stems.values()):
        for w in WORD_RE.findall(text):
            lw = w.lower()
            if len(lw) >= 2:
                words.setdefault(lw, lw)
    return materials, stems, words


def call(client, sys_prompt: str, payload: dict, reasoning: str = "none") -> tuple[list[dict], dict]:
    """一次模型调用。

    ⚠️ 实测（2026-10-24，同一段材料各试一次）：
       不传 reasoning_effort → completion 95，其中 reasoning 70
       "minimal" / "low"     → reasoning 85~88（照样思考）
       "off"                 → 422（不是合法取值）
       "none"                → completion 23，**不产生 reasoning** ✅
    不关思考时，单批 4 段材料烧过 8,453 个 completion token（其中 7,327 是 reasoning），
    占总花费 87%。翻译不需要推理，必须显式 "none"。
    """
    kwargs = dict(model=MODEL,
                  messages=[{"role": "system", "content": sys_prompt},
                            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
                  response_format={"type": "json_object"},
                  temperature=0)
    if reasoning:
        kwargs["reasoning_effort"] = reasoning
    try:
        resp = client.chat.completions.create(**kwargs)
    except Exception as exc:  # noqa: BLE001
        if reasoning and "reasoning" in str(exc).lower():
            kwargs.pop("reasoning_effort", None)
            resp = client.chat.completions.create(**kwargs)
        else:
            raise
    usage = resp.usage.model_dump() if getattr(resp, "usage", None) else {}
    try:
        data = json.loads(resp.choices[0].message.content or "{}")
    except Exception:  # noqa: BLE001
        data = {}
    return (data.get("items") or []), usage


def ledger(task: str, usage: dict, cost: float, extra: dict) -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    with (LOGS / "cost_ledger.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"at": now_iso(), "task": task, "model": MODEL,
                             "usage": usage, "cost_cny": round(cost, 6), **extra},
                            ensure_ascii=False) + "\n")


def batches(items: list[tuple[str, str]], size: int):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def main() -> int:
    ap = argparse.ArgumentParser(description="预生成英语译文与单词词表（默认 dry-run）")
    ap.add_argument("--materials", action="store_true", help="翻阅读材料")
    ap.add_argument("--stems", action="store_true", help="翻题干")
    ap.add_argument("--glossary", action="store_true", help="生成单词词表")
    ap.add_argument("--all", action="store_true", help="以上全做")
    ap.add_argument("--apply", action="store_true", help="真调用模型（默认只统计）")
    ap.add_argument("--cap-cny", type=float, default=3.0, help="预估花费上限（元）")
    ap.add_argument("--batch", type=int, default=0, help="每批条数（默认按类型自动）")
    ap.add_argument("--limit-batches", type=int, default=0, help="只跑前 N 批（调试）")
    ap.add_argument("--reasoning", default="none", help="思考档位（默认 none；翻译不需要推理，只有 none 才真关掉）")
    ap.add_argument("--min-stem", type=int, default=0, help="只翻长度 ≥ 该值的题干（默认 0=全翻；「21. ____」这种编号建议设 25）")
    ap.add_argument("--skip-types", default="", help="不翻这些题型的题干，逗号分隔，如 reading_fill,reading_qa")
    args = ap.parse_args()

    do_mat = args.all or args.materials
    do_stem = args.all or args.stems
    do_gloss = args.all or args.glossary
    if not (do_mat or do_stem or do_gloss):
        print("至少给一个 --materials / --stems / --glossary / --all")
        return 2

    materials, stems, words = collect(min_stem=args.min_stem, skip_types=args.skip_types)
    conn = ensure_db()
    have = {r[0] for r in conn.execute("SELECT doc_key FROM translations")}
    have_words = {r[0] for r in conn.execute("SELECT word FROM glossary")}
    conn.close()

    mat_todo = [(k, v) for k, v in materials.items() if k not in have] if do_mat else []
    stem_todo = [(k, v) for k, v in stems.items() if k not in have] if do_stem else []
    word_todo = [w for w in words if w not in have_words] if do_gloss else []

    b_mat = args.batch or 4
    b_stem = args.batch or 20
    b_word = args.batch or 120
    n_calls = (len(mat_todo) + b_mat - 1) // b_mat + (len(stem_todo) + b_stem - 1) // b_stem \
        + (len(word_todo) + b_word - 1) // b_word
    mat_chars = sum(len(t) for _, t in mat_todo)
    stem_chars = sum(len(t) for _, t in stem_todo)
    # 粗估：英文 4 字符/token，中文输出约 1.2 倍字符、1.6 字符/token
    est_in = (mat_chars + stem_chars) / 4 + len(word_todo) * 2 + n_calls * 260
    est_out = (mat_chars + stem_chars) * 0.75 / 1.6 * 1.4 + len(word_todo) * 8
    est = (est_in * PRICE["in"] + est_out * PRICE["out"]) / 1_000_000
    print(f"待翻：材料 {len(mat_todo)} 块（{mat_chars} 字符）、题干 {len(stem_todo)} 条"
          f"（{stem_chars} 字符）、词表 {len(word_todo)} 词；共 {n_calls} 次调用，预估 ¥{est:.3f}")
    if est > args.cap_cny:
        print(f"拒绝执行：预估 ¥{est:.3f} > 上限 ¥{args.cap_cny}")
        return 2
    if not args.apply:
        for k, v in (mat_todo[:2] + stem_todo[:3]):
            print(f"   · {k}  {v[:70]!r}")
        print(f"   · 词表示例: {word_todo[:12]}")
        print("dry-run：未发起请求。")
        return 0

    from openai import OpenAI

    env = load_env()
    if "DEEPSEEK_API_KEY" not in env:
        print("缺 DEEPSEEK_API_KEY（.env）")
        return 3
    client = OpenAI(api_key=env["DEEPSEEK_API_KEY"],
                    base_url=env.get("DEEPSEEK_BASE_URL") or "https://api.deepseek.com", timeout=180)

    conn = ensure_db()
    spent = 0.0
    calls = 0
    saved = 0

    def run(task: str, sys_prompt: str, todo: list, size: int, key_field: str, text_field: str,
            table: str, cols: str, on_row) -> None:
        nonlocal spent, calls, saved
        for chunk in batches(todo, size):
            if args.limit_batches and calls >= args.limit_batches:
                return
            payload = {"items": [{key_field: k, text_field: t} for k, t in chunk]}
            items, usage = call(client, sys_prompt, payload, args.reasoning)
            cost = ((usage.get("prompt_tokens", 0) or 0) * PRICE["in"]
                    + (usage.get("completion_tokens", 0) or 0) * PRICE["out"]) / 1_000_000
            spent += cost
            calls += 1
            ledger(task, usage, cost, {"batch": len(chunk)})
            rows = []
            for it in items:
                row = on_row(it)
                if row:
                    rows.append(row)
            if rows:
                conn.executemany(f"INSERT OR REPLACE INTO {table} ({cols}) VALUES "
                                 f"({','.join('?' * len(rows[0]))})", rows)
                conn.commit()
                saved += len(rows)
            print(f"  [{task}] 批次 {calls}：返回 {len(items)}/{len(chunk)} 条，累计实花 ¥{spent:.4f}")

    if mat_todo:
        def on_mat(it):
            zh = str(it.get("zh") or "").strip()
            k = str(it.get("id") or "")
            if not zh or not CJK_RE.search(zh) or k not in materials:
                return None
            return (k, "material", materials[k], zh, MODEL, now_iso())
        run("translate_material", SYS_TRANSLATE, mat_todo, b_mat, "id", "text",
            "translations", "doc_key,kind,source,zh,model,created_at", on_mat)

    if stem_todo:
        def on_stem(it):
            zh = str(it.get("zh") or "").strip()
            k = str(it.get("id") or "")
            if not zh or not CJK_RE.search(zh) or k not in stems:
                return None
            return (k, "stem", stems[k], zh, MODEL, now_iso())
        run("translate_stem", SYS_TRANSLATE, stem_todo, b_stem, "id", "text",
            "translations", "doc_key,kind,source,zh,model,created_at", on_stem)

    if word_todo:
        def on_word(it):
            w = str(it.get("w") or "").strip().lower()
            zh = str(it.get("zh") or "").strip()
            pos = str(it.get("pos") or "").strip()
            if not w or not zh or not CJK_RE.search(zh):
                return None
            return (w, pos, zh, MODEL, now_iso())
        run("glossary", SYS_GLOSSARY, [(w, w) for w in word_todo], b_word, "w", "text",
            "glossary", "word,pos,zh,model,created_at", on_word)

    conn.close()
    print(f"\n完成：{calls} 次调用，写入 {saved} 行，实花 ¥{spent:.4f}")
    print(f"库：{OUT_DB}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

