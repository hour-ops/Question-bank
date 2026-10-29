#!/usr/bin/env python
"""按科目隔离的知识库（RAG 底座）：一个科目 = 一个独立 sqlite 文件，**物理不串**。

为什么这么设计（用户明确要求）：
  - 「生成 C 语言时不要检索到 ACA/英语」→ 不用 subject 字段过滤，而是**每科一个库文件**
    （`data/kb/<subject>.sqlite`），检索函数只接受一个科目，物理上不可能跨科召回。
  - 「知识点可以随时添加」→ `kb.py add` 一条命令即可增量入库；同文件重复入库按 sha 去重。
  - 「每个知识点单独一页」→ `kp` 表 + `kp_chunk` 关联，Web 端 `/kb?subject=..&kp=..`。

检索实现：jieba 分词 → FTS5(bm25)。不用向量库（本机 CPU 跑 embedding 慢，且专业术语的关键词
命中率已经很高）；以后要加向量，只需在同一文件里加一张 `vec` 表，隔离性质不变。

表结构（每科目文件相同）：
  docs(id, title, kind, source, url, sha, chars, created_at)
  chunks(id, doc_id, ord, heading, text, seg, chars)
  chunks_fts(chunk_id UNINDEXED, seg, heading)        -- FTS5，seg 是 jieba 分好的词
  kp(id, name, parent, weight, aliases, notes)         -- 知识点（考纲/考点/章节）
  kp_chunk(kp_id, chunk_id)                            -- 知识点 ↔ 材料块

用法:
    python scripts/kb.py init                        # 建 4 个科目的空库
    python scripts/kb.py add --subject aca_llm --file inbox/aca_llm/lessons/1_大模型概念.md --title "考点1 大模型概念" --kind guide
    python scripts/kb.py add --subject aca_llm --dir inbox/aca_llm/lessons --kind guide
    python scripts/kb.py search --subject c_wuhan "指针 数组"
    python scripts/kb.py kp --subject aca_llm       # 列知识点
    python scripts/kb.py stats
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
KB_DIR = DATA / "kb"
SUBJECTS = ("english", "c_wuhan", "c_hbpu", "aca_llm")

# 领域词典：不加的话 jieba 会把「提示词」切成「提示/词」，检索质量明显下降
DOMAIN_WORDS = [
    "大模型", "大语言模型", "提示词", "提示词工程", "思维链", "少样本", "零样本", "角色设定",
    "检索增强生成", "知识库", "向量数据库", "切片", "召回", "重排", "嵌入", "语义检索",
    "监督微调", "全参数微调", "低秩适配", "强化学习", "人类反馈", "对齐", "预训练",
    "幻觉", "上下文窗口", "温度", "采样", "解码", "分词", "词元", "混合专家", "参数量",
    "智能体", "工具调用", "函数调用", "工作流", "记忆", "规划", "反思", "自检闭环",
    "百炼", "通义千问", "千问", "弹性容器实例", "模型服务", "模型评测", "模型蒸馏", "模型量化",
    "推理加速", "并发", "算力", "安全合规", "内容审核", "数据脱敏", "版权", "水印",
    "指针", "数组", "结构体", "共用体", "枚举", "链表", "二叉树", "递归", "宏定义", "预处理",
    "文件操作", "动态内存", "函数指针", "排序算法", "时间复杂度", "字符串",
    "定语从句", "非谓语动词", "虚拟语气", "被动语态", "完形填空", "阅读理解", "翻译",
    "连词成句", "语法填空", "词汇", "音标", "重音", "词性", "时态", "主谓一致",
]

_FTS_TOKEN = re.compile(r"[\w\u4e00-\u9fff]+", re.U)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _jieba():
    import jieba
    for w in DOMAIN_WORDS:
        jieba.add_word(w, freq=20000)
    return jieba


def _naive_segment(text: str) -> str:
    """没有 jieba 时的兜底分词：ASCII 词 + 中文按 2-gram 切开。

    为什么要兜底：`jieba` 是可选依赖，若没装（例如用户只跑 `安装依赖.bat` 的老版本），
    检索会抛 ModuleNotFoundError → 知识库页直接 500。宁可粗一点，也不能整页崩。
    """
    out: list[str] = []
    for tok in _FTS_TOKEN.findall(str(text or "")):
        if tok.isascii():
            out.append(tok.lower())
            continue
        for i in range(len(tok) - 1):
            out.append(tok[i:i + 2])
        if len(tok) == 1:
            out.append(tok)
    return " ".join(out)


def segment(text: str) -> str:
    """jieba 精确分词后空格拼接（FTS5 的 unicode61 按空格切，中文才能命中）。"""
    try:
        jb = _jieba()
    except Exception:  # noqa: BLE001  缺 jieba → 用 2-gram 兜底，别让整页 500
        return _naive_segment(text)
    return " ".join(t for t in jb.cut(str(text or "")) if t.strip())


def db_path(subject: str) -> Path:
    if subject not in SUBJECTS:
        raise SystemExit(f"未知科目 {subject!r}，可选：{SUBJECTS}")
    return KB_DIR / f"{subject}.sqlite"


SCHEMA = """
CREATE TABLE IF NOT EXISTS docs(
  id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, kind TEXT DEFAULT '',
  source TEXT DEFAULT '', url TEXT DEFAULT '', sha TEXT UNIQUE, chars INTEGER DEFAULT 0,
  created_at TEXT);
CREATE TABLE IF NOT EXISTS chunks(
  id INTEGER PRIMARY KEY AUTOINCREMENT, doc_id INTEGER NOT NULL, ord INTEGER DEFAULT 0,
  heading TEXT DEFAULT '', text TEXT NOT NULL, seg TEXT NOT NULL, chars INTEGER DEFAULT 0);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
  chunk_id UNINDEXED, seg, heading, tokenize='unicode61');
CREATE TABLE IF NOT EXISTS kp(
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, parent TEXT DEFAULT '',
  weight REAL DEFAULT 0, aliases TEXT DEFAULT '', notes TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS kp_chunk(
  kp_id INTEGER NOT NULL, chunk_id INTEGER NOT NULL, PRIMARY KEY(kp_id, chunk_id));
"""


def open_db(subject: str, create: bool = True) -> sqlite3.Connection:
    path = db_path(subject)
    if not path.exists() and not create:
        raise SystemExit(f"知识库还不存在：{path}（先跑 kb.py init）")
    KB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    return conn


# ---------------------------------------------------------------- 切块

_HEAD = re.compile(r"^(#{1,4})\s+(.+)$", re.M)


def split_chunks(text: str, max_chars: int = 700) -> list[tuple[str, str]]:
    """按 Markdown 标题切；每块超过 max_chars 再按句号切。返回 [(heading, 正文)]。

    会丢掉文件头的「来源/接口/原始 JSON」元信息块——那是采集痕迹，不是知识点，
    留着会抢占检索头部（实测第一条命中就是它）。
    """
    text = str(text or "").replace("\r\n", "\n").strip()
    if not text:
        return []
    # 剥掉开头的 `> 来源：…` 引用块（连续以 > 开头的行）
    lines = text.split("\n")
    i = 0
    while i < len(lines) and (lines[i].startswith(">") or lines[i].startswith("`fact_source`")):
        i += 1
    text = "\n".join(lines[i:]).strip()
    marks = list(_HEAD.finditer(text))
    out: list[tuple[str, str]] = []
    if not marks:
        blocks = [(("", text))]
    else:
        blocks = []
        if marks[0].start() > 0:
            blocks.append(("", text[: marks[0].start()]))
        for i, m in enumerate(marks):
            end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
            blocks.append((m.group(2).strip(), text[m.end():end].strip()))

    for head, body in blocks:
        body = body.strip()
        if not body:
            # 只有标题没有正文（典型：教材目录「8.3 通过指针引用数组」）——
            # 标题本身就是要检索的内容，不能丢
            if head:
                out.append((head, head))
            continue
        if len(body) <= max_chars:
            out.append((head, body))
            continue
        # 长块按句切，句子累积到 max_chars
        buf = ""
        for sent in re.split(r"(?<=[。！？；\n])", body):
            if not sent.strip():
                continue
            if len(buf) + len(sent) > max_chars and buf:
                out.append((head, buf.strip()))
                buf = ""
            buf += sent
        if buf.strip():
            out.append((head, buf.strip()))
    return out


def add_document(conn: sqlite3.Connection, *, title: str, text: str, kind: str = "",
                 source: str = "", url: str = "", kp_name: str = "") -> dict:
    sha = hashlib.sha1(f"{title}\n{text}".encode("utf-8")).hexdigest()
    row = conn.execute("SELECT id FROM docs WHERE sha=?", (sha,)).fetchone()
    if row:
        return {"doc_id": row["id"], "chunks": 0, "skipped": True}
    cur = conn.execute(
        "INSERT INTO docs(title,kind,source,url,sha,chars,created_at) VALUES (?,?,?,?,?,?,?)",
        (title, kind, source, url, sha, len(text), now_iso()))
    doc_id = cur.lastrowid
    parts = split_chunks(text)
    kp_id = None
    if kp_name:
        kp_id = upsert_kp(conn, kp_name)
    for i, (head, body) in enumerate(parts):
        seg = segment(f"{head} {body}" if head else body)
        c = conn.execute(
            "INSERT INTO chunks(doc_id, ord, heading, text, seg, chars) VALUES (?,?,?,?,?,?)",
            (doc_id, i, head, body, seg, len(body)))
        cid = c.lastrowid
        conn.execute("INSERT INTO chunks_fts(chunk_id, seg, heading) VALUES (?,?,?)",
                     (cid, seg, segment(head) if head else ""))
        if kp_id:
            conn.execute("INSERT OR IGNORE INTO kp_chunk(kp_id, chunk_id) VALUES (?,?)", (kp_id, cid))
    conn.commit()
    return {"doc_id": doc_id, "chunks": len(parts), "skipped": False}


def upsert_kp(conn: sqlite3.Connection, name: str, parent: str = "", weight: float = 0,
              aliases: str = "", notes: str = "") -> int:
    name = str(name or "").strip()
    if not name:
        raise ValueError("知识点名不能为空")
    row = conn.execute("SELECT id FROM kp WHERE name=?", (name,)).fetchone()
    if row:
        if parent or weight or aliases or notes:
            conn.execute("UPDATE kp SET parent=COALESCE(NULLIF(?,''),parent), "
                         "weight=CASE WHEN ?>0 THEN ? ELSE weight END, "
                         "aliases=COALESCE(NULLIF(?,''),aliases), "
                         "notes=COALESCE(NULLIF(?,''),notes) WHERE id=?",
                         (parent, weight, weight, aliases, notes, row["id"]))
        return int(row["id"])
    cur = conn.execute("INSERT INTO kp(name,parent,weight,aliases,notes) VALUES (?,?,?,?,?)",
                       (name, parent, weight, aliases, notes))
    return int(cur.lastrowid)


# ---------------------------------------------------------------- 检索

STOPWORDS = {"的", "了", "和", "与", "及", "或", "是", "在", "有", "怎么", "如何", "什么",
             "哪些", "哪个", "为什么", "请问", "一下", "可以", "需要", "关于", "区别", "关系"}


def search(subject: str, query: str, k: int = 5) -> list[dict]:
    """**只在指定科目库里检索**（物理隔离）。返回按 bm25 排序的块。

    召回策略：先 AND（所有实词都要命中，精度优先）；命中为 0 再退回 OR（宽松）。
    实测 AND 能挡掉「指针和数组的关系」被「关系运算符」抢走的问题。
    """
    conn = open_db(subject, create=False)
    try:
        seg = segment(query)
        terms = [t for t in seg.split() if t.strip() and t not in STOPWORDS]
        if not terms:
            terms = [t for t in seg.split() if t.strip()]
        if not terms:
            return []
        terms = terms[:20]

        def run(expr: str) -> list[dict]:
            return [dict(r) for r in conn.execute(
                "SELECT f.chunk_id, bm25(chunks_fts) AS score, c.text, c.heading, c.doc_id, "
                "d.title, d.kind, c.chars FROM chunks_fts f "
                "JOIN chunks c ON c.id = f.chunk_id JOIN docs d ON d.id = c.doc_id "
                "WHERE chunks_fts MATCH ? ORDER BY score LIMIT ?", (expr, k)).fetchall()]

        rows = run(" AND ".join(f'"{t}"' for t in terms))
        if not rows and len(terms) > 1:
            rows = run(" OR ".join(f'"{t}"' for t in terms))
        return rows
    finally:
        conn.close()


# ---------------------------------------------------------------- CLI

def cmd_init(args) -> int:
    for s in (SUBJECTS if args.subject == "all" else [args.subject]):
        conn = open_db(s)
        conn.close()
        print(f"  [init] {db_path(s)}")
    return 0


def _iter_files(p: Path):
    if p.is_file():
        yield p
    else:
        for f in sorted(p.rglob("*")):
            if f.is_file() and f.suffix.lower() in (".md", ".txt", ".jsonl", ".json"):
                yield f


def cmd_add(args) -> int:
    conn = open_db(args.subject)
    targets = []
    if args.file:
        targets.append(Path(args.file) if Path(args.file).is_absolute() else ROOT / args.file)
    if args.dir:
        targets.append(Path(args.dir) if Path(args.dir).is_absolute() else ROOT / args.dir)
    if not targets:
        print("需要 --file 或 --dir")
        return 2
    total_docs = total_chunks = 0
    for t in targets:
        for f in _iter_files(t):
            text = f.read_text(encoding="utf-8-sig", errors="ignore")
            title = args.title or f.stem
            if len(targets) == 1 and t.is_dir():
                title = f.stem
            r = add_document(conn, title=title, text=text, kind=args.kind,
                             source=str(f.relative_to(ROOT)) if f.is_relative_to(ROOT) else str(f),
                             url=args.url, kp_name=args.kp or "")
            if not r["skipped"]:
                total_docs += 1
                total_chunks += r["chunks"]
                print(f"  + {f.name}: {r['chunks']} 块")
            else:
                print(f"  = {f.name}: 已存在，跳过")
    print(f"[{args.subject}] 新增 {total_docs} 文档 / {total_chunks} 块")
    return 0


def cmd_search(args) -> int:
    rows = search(args.subject, args.query, args.k)
    print(f"[{args.subject}] 「{args.query}」命中 {len(rows)} 块")
    for r in rows:
        print(f"\n  score={r['score']:.3f}  《{r['title']}》  {r['heading']}")
        print("   " + r["text"][:220].replace("\n", " "))
    return 0


def cmd_kp(args) -> int:
    conn = open_db(args.subject)
    try:
        if args.add:
            kid = upsert_kp(conn, args.add, parent=args.parent or "", weight=args.weight or 0,
                            aliases=args.aliases or "", notes=args.notes or "")
            conn.commit()
            print(f"  + 知识点 #{kid} {args.add}")
            return 0
        rows = conn.execute(
            "SELECT k.id, k.name, k.parent, k.weight, COUNT(kc.chunk_id) AS chunks "
            "FROM kp k LEFT JOIN kp_chunk kc ON kc.kp_id=k.id GROUP BY k.id ORDER BY k.id").fetchall()
        print(f"[{args.subject}] 知识点 {len(rows)} 个")
        for r in rows:
            print(f"  #{r['id']:3d} {r['name'][:36]:38s} 材料 {r['chunks']:3d} 块")
        return 0
    finally:
        conn.close()


def cmd_reset(args) -> int:
    """清空某科目库的文档/块（保留知识点定义）。用于重新切块后重建索引。"""
    conn = open_db(args.subject)
    try:
        if args.keep_kp:
            conn.execute("DELETE FROM kp_chunk")
        else:
            conn.execute("DELETE FROM kp_chunk")
            conn.execute("DELETE FROM kp")
        conn.execute("DELETE FROM chunks_fts")
        conn.execute("DELETE FROM chunks")
        conn.execute("DELETE FROM docs")
        conn.commit()
        print(f"[{args.subject}] 已清空文档与索引（keep_kp={args.keep_kp}）")
        return 0
    finally:
        conn.close()


def cmd_stats(args) -> int:
    print(f"{'科目':10s} {'文档':>5s} {'块':>6s} {'字数':>9s} {'知识点':>6s}")
    for s in SUBJECTS:
        p = db_path(s)
        if not p.exists():
            print(f"{s:10s} {'(未建库)':>10s}")
            continue
        conn = open_db(s)
        try:
            d = conn.execute("SELECT COUNT(*) c FROM docs").fetchone()
            c = conn.execute("SELECT COUNT(*) c, COALESCE(SUM(chars),0) n FROM chunks").fetchone()
            k = conn.execute("SELECT COUNT(*) c FROM kp").fetchone()
            print(f"{s:10s} {d['c']:5d} {c['c']:6d} {c['n']:9d} {k['c']:6d}")
        finally:
            conn.close()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="按科目隔离的知识库（RAG 底座）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init"); p.add_argument("--subject", default="all"); p.set_defaults(func=cmd_init)

    p = sub.add_parser("add")
    p.add_argument("--subject", required=True)
    p.add_argument("--file"); p.add_argument("--dir")
    p.add_argument("--title"); p.add_argument("--kind", default="")
    p.add_argument("--url", default=""); p.add_argument("--kp", default="")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("search")
    p.add_argument("--subject", required=True); p.add_argument("query")
    p.add_argument("-k", type=int, default=5); p.set_defaults(func=cmd_search)

    p = sub.add_parser("kp")
    p.add_argument("--subject", required=True)
    p.add_argument("--add"); p.add_argument("--parent", default="")
    p.add_argument("--weight", type=float, default=0)
    p.add_argument("--aliases", default=""); p.add_argument("--notes", default="")
    p.set_defaults(func=cmd_kp)

    p = sub.add_parser("reset")
    p.add_argument("--subject", required=True)
    p.add_argument("--keep-kp", action="store_true", help="保留 kp 定义，只清文档与索引")
    p.set_defaults(func=cmd_reset)

    p = sub.add_parser("stats"); p.set_defaults(func=cmd_stats)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
