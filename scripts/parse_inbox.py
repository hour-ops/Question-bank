#!/usr/bin/env python
"""阶段 5a · 解析入库脚本 —— **唯一允许写 `questions` 表的入口**。

用法:
    python scripts/parse_inbox.py [--subject english|c_wuhan|c_hbpu|aca_llm|all] [--dry-run] [--limit N]

输入:  inbox/{subject}/ 下的 *.md *.html *.htm *.txt *.pdf *.docx *.png|jpg
输出:  data/{subject}.sqlite 的 questions 表（status='parsed'）
       subjects/aca_llm/syllabus_index.json（ACA 考纲索引）

关键口径（见 DESIGN.md 与 .tools/题库项目-决策记录.md）:
  1. **ACA 解析优先级 md > html > pdf**（按扩展名排序 + 指纹去重天然实现）。
  2. `fact_claim` / `fact_source` **只来自文件头部的显式标注**（`fact_claim: "..."`），
     不做"事实声明推断"；没有就留空。
  3. 图片（png/jpg）**不做 OCR**（本机无 tesseract）→ 只登记文件名并标 `未获取`，绝不生成知识点。
  4. 去重：源内用 `uid.generate_uid`；跨源用 `uid.content_fingerprint`；模糊兜底 `rapidfuzz > 0.9`。
     命中则**不新建**，把新来源追加进既有题的 `source_credit`（保留最早 uid）。
  5. 入库前回写 `cache.sqlite.source_stats.hits / hit_rate`（4a 约定的命中率闭环）。
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from lib.uid import content_fingerprint, generate_uid  # noqa: E402

INBOX = ROOT / "inbox"
DATA = ROOT / "data"
SUBJECTS_DIR = ROOT / "subjects"
CACHE_DB = DATA / "cache.sqlite"
SUBJECTS = ["english", "c_wuhan", "c_hbpu", "aca_llm"]

# ACA 解析优先级（越小越先解析；同名内容重复时保留先解析的）
EXT_PRIORITY = {".md": 0, ".html": 1, ".htm": 1, ".txt": 2, ".pdf": 3, ".docx": 4}
IMG_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}

# 只作「知识点/素材」用、不参与题目解析的文件（防止把散文误当题目）
SKIP_FILES = {"aca_v24_syllabus.md", "aca_v24_lessons.md", "aca_v24_knowledge_points.md"}
SKIP_DIR_PARTS = {"lessons", "raw"}

# 越界科目：英语题库里实测混入了这些他科文章（来自 hbzsb 的"其他专业"系列）
OFFTOPIC_HINTS: dict[str, tuple[str, ...]] = {
    "english": ("教育学", "教育理论", "教育心理", "管理学", "生理学", "护理学", "酒店管理",
                "临床医学", "高等数学", "大学语文", "经济学", "法学", "计算机基础", "C语言", "C 语言"),
    "c_wuhan": ("教育学", "管理学", "护理学", "酒店管理", "临床医学", "生理学"),
    "c_hbpu": ("教育学", "管理学", "护理学", "酒店管理", "临床医学", "生理学"),
    "aca_llm": (),
}


def load_forbidden_types() -> dict[str, set[str]]:
    """从 config/taxonomy.json 读每个科目的 forbidden_types（英语/C 禁选择题与判断题）。"""
    out: dict[str, set[str]] = {}
    p = ROOT / "config" / "taxonomy.json"
    if not p.exists():
        return out
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        for subj, cfg in (data.get("subjects") or {}).items():
            ft = cfg.get("forbidden_types") or []
            if ft:
                out[subj] = set(ft)
    except Exception:  # noqa: BLE001
        pass
    return out

OPTION_RE = re.compile(r"^\s*([A-H])\s*[.、．)）]\s*(.+?)\s*$")
QNUM_RE = re.compile(r"^\s*(?:第\s*)?(\d{1,3})\s*[.、．)）]\s*(.+?)\s*$")
ANSWER_RE = re.compile(r"^\s*(?:参考)?答案\s*[:：]\s*(.+?)\s*$")
EXPLAIN_RE = re.compile(r"^\s*(?:解析|答案解析)\s*[:：]\s*(.+?)\s*$")
KP_RE = re.compile(r"^\s*(?:知识点|考点|标签)\s*[:：]\s*(.+?)\s*$")
# 允许 markdown 引用前缀（`> `）、列表符号、反引号/引号/粗体装饰
FACT_CLAIM_RE = re.compile(r"(?m)^[\s>*\-]*[`\"']*fact_claim[`\"']*[\s*]*[:：]\s*(.+?)\s*$")
FACT_SOURCE_RE = re.compile(r"(?m)^[\s>*\-]*[`\"']*fact_source[`\"']*[\s*]*[:：]\s*(.+?)\s*$")
MODULE_RE = re.compile(r"^##\s*模块\s*(\d+)\s*[·:：]\s*(.+?)\s*$")
KP_ROW_RE = re.compile(r"^\|\s*([0-9]+\.[0-9]+)\s*\|\s*(.+?)\s*\|\s*(.*?)\s*\|\s*$")
UNKNOWN = "未获取"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def strip_quotes(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'“”":
        s = s[1:-1]
    return s.strip()


# ------------------------------------------------------------------ 读取各格式


# HTML 正文容器候选（**按优先级**，命中第一个足够长的就用它）；避免导航/侧栏/页脚污染
MAIN_SELECTORS = (
    "article", ".article-content", ".article_content", ".art-content", ".art_content",
    ".news-content", ".news_content", ".content-detail", ".detail-content", ".entry-content",
    ".post-content", ".rich_media_content", ".article-box", ".detail", "main",
)
CHROME_TAGS = ("script", "style", "noscript", "nav", "header", "footer", "aside", "form", "iframe")
# 按 class/id 关键字剔除页面模板块（导航/面包屑/侧栏/页脚/广告）——比过宽容器选择器可靠
CHROME_ATTR_RE = re.compile(r"nav|menu|header|footer|crumb|sidebar|aside|banner|advert|toolbar|topbar|breadcrumb", re.I)


# 题目/答案类行必须保留（即使很短），否则 "答案：C"、"A、xxx" 会被剪掉
KEEP_LINE_RE = re.compile(
    r"^(?:[A-H]\s*[.、．)）]|答案|参考答案|解析|答案解析|知识点|考点|标签|参考|第\s*\d+|\(\d+\)|（\d+）|\d{1,3}\s*[.、．)）])"
)
NAV_MIN_LEN = 12  # 短于该长度且非题目标记行 → 判为导航/栏目名，丢弃


def _prune_nav_lines(text: str) -> str:
    """按行剪枝剔除导航：导航项都是短词（首页/考试大纲/…），正文都是长句。

    hbzsb 使用**混淆 class**（b-1/f-2/f-9）反爬，选择器方案不可用，
    只能靠"行长 + 题目标记"这种与类名无关的结构特征来分离正文。
    """
    keep: list[str] = []
    for raw_line in text.splitlines():
        s = raw_line.strip()
        if not s:
            keep.append("")
            continue
        if len(s) >= NAV_MIN_LEN or KEEP_LINE_RE.match(s):
            keep.append(s)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(keep))


def html_main_text(raw: str) -> str:
    """提取 HTML 正文：先按标签/类名剔除模板块，再按行长剪枝。"""
    soup = BeautifulSoup(raw, "lxml")
    for tag in soup(CHROME_TAGS):
        tag.decompose()
    for el in soup.find_all(attrs={"class": CHROME_ATTR_RE}):
        el.decompose()
    for el in soup.find_all(attrs={"id": CHROME_ATTR_RE}):
        el.decompose()
    node = soup.body if soup.body is not None else soup
    return _prune_nav_lines(node.get_text("\n"))


def read_text(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in {".md", ".txt"}:
        return path.read_text(encoding="utf-8", errors="replace")
    if ext in {".html", ".htm"}:
        raw = path.read_text(encoding="utf-8", errors="replace")
        return html_main_text(raw)
    if ext == ".pdf":
        try:
            import pdfplumber

            parts: list[str] = []
            with pdfplumber.open(str(path)) as pdf:
                for page in pdf.pages:
                    parts.append(page.extract_text() or "")
            return "\n".join(parts)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"pdf 解析失败: {exc}") from exc
    if ext == ".docx":
        import docx

        d = docx.Document(str(path))
        return "\n".join(p.text for p in d.paragraphs)
    raise RuntimeError(f"不支持的扩展名: {ext}")


# ------------------------------------------------------------------ 题目解析


def strip_leading_metadata(text: str) -> str:
    """剥离文件**前导元数据块**（标题/引用/表格/分隔线/注释），否则会被并进第一题的题干。

    只剥离开头连续的元数据行；遇到第一行普通正文即停止。
    """
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        if s == "" or s.startswith(("#", ">", "`", "---", "|", "- ", "* ", "//")):
            i += 1
            continue
        break
    return "\n".join(lines[i:])


def parse_questions(text: str) -> list[dict[str, Any]]:
    """状态机解析：题干 → 选项 → 答案 → 解析 → 知识点。

    兼容两种排版：
      A) ACA 样题式：题干行 + `A、…` + `答案：X` + `知识点：…`
      B) 编号式：`1. 题干…` + `答案：…`
    """
    lines = [ln.rstrip() for ln in strip_leading_metadata(text).splitlines()]
    out: list[dict[str, Any]] = []
    cur: dict[str, Any] = {}
    mode: str | None = None

    def flush() -> None:
        """质量闸门：只有「有答案」或「≥2 个选项」的块才算题；纯散文一律丢弃。"""
        nonlocal cur, mode
        stem = (cur.get("stem") or "").strip()
        opts = cur.get("options") or []
        answer = (cur.get("answer") or "").strip()
        if stem and (answer or len(opts) >= 2):
            cur.setdefault("options", [])
            cur.setdefault("answer", "")
            cur.setdefault("explanation", "")
            cur.setdefault("knowledge_point", "")
            out.append(cur)
        cur = {}
        mode = None

    for raw in lines:
        line = raw.strip()
        if not line:
            continue

        m_ans = ANSWER_RE.match(line)
        m_exp = EXPLAIN_RE.match(line)
        m_kp = KP_RE.match(line)
        m_opt = OPTION_RE.match(line)
        m_q = QNUM_RE.match(line)

        if m_ans:
            cur["answer"] = m_ans.group(1).strip()
            mode = "answer"
            continue
        if m_exp:
            cur["explanation"] = m_exp.group(1).strip()
            mode = "explain"
            continue
        if m_kp:
            cur["knowledge_point"] = m_kp.group(1).strip()
            mode = "kp"
            continue
        if m_opt:
            cur.setdefault("options", []).append({"label": m_opt.group(1), "text": m_opt.group(2).strip()})
            mode = "options"
            continue
        if m_q:
            # 编号行 → 新题
            flush()
            cur["stem"] = m_q.group(2).strip()
            mode = "stem"
            continue
        # 「像新题」的句子，且本题已有答案/选项 → 判定为新题（**必须在续行判断之前**，
        # 否则下一题的题干会被当成上一题知识点的续行吞掉——实测 80 道样题只解析出 17 道就是此因）
        looks_new_q = (
            "？" in line or "?" in line or line.endswith(("（）", "()"))
            or re.match(r"^[A-Z][A-Za-z0-9 ,\-]+(的|是|指|通常|主要|以下)", line) is not None
        )
        if (looks_new_q or (cur.get("answer") and cur.get("knowledge_point"))) and cur.get("stem") and (
            cur.get("answer") or cur.get("options")
        ):
            flush()
            cur["stem"] = line
            mode = "stem"
            continue
        if mode in {"explain", "answer", "kp"} and cur.get("stem"):
            # 续行
            key = {"explain": "explanation", "answer": "answer", "kp": "knowledge_point"}[mode]
            cur[key] = (cur.get(key, "") + " " + line).strip()
            continue
        if cur.get("stem") and cur.get("options") and mode != "stem":
            # 已经收完选项又出现普通文本 → 视为新题题干
            flush()
            cur["stem"] = line
            mode = "stem"
            continue
        if cur.get("stem") and mode == "stem":
            cur["stem"] = (cur["stem"] + " " + line).strip()
            continue
        cur["stem"] = line
        mode = "stem"

    flush()
    return out


NUM_ITEM_RE = re.compile(r"^\s*(\d{1,3})\s*[.、．)）]\s*(.*)$")
ANSWER_SECTION_RE = re.compile(r"^[【\[]?\s*(?:参考)?答案(?:与解析|及解析|解析)?\s*[】\]]?\s*[:：]?\s*$")


def _collect_numbered(lines: list[str]) -> dict[int, str]:
    """把 `N. xxx` 形式的条目按序号聚成 {n: 文本}（含续行）。"""
    items: dict[int, str] = {}
    cur: int | None = None
    for ln in lines:
        m = NUM_ITEM_RE.match(ln)
        if m:
            cur = int(m.group(1))
            items[cur] = m.group(2).strip()
        elif cur is not None and ln.strip():
            items[cur] = (items[cur] + " " + ln.strip()).strip()
    return items


def parse_answer_key_format(text: str) -> list[dict[str, Any]]:
    """解析「题目在前、答案集中在后」的排版（模拟卷/真题卷主流格式）。

    实测：hbzsb 的《英语专项练习题（含答案详细解析）》《C语言程序设计模拟卷》等
    都是这种排版——题干按 1./2./3. 排列，正文中途出现单独一行的「参考答案：」，
    之后才是 1./2./3. 的答案。原状态机（答案紧跟题干）对这类文件产出为 0。
    """
    lines = strip_leading_metadata(text).splitlines()
    ans_idx = None
    for i, ln in enumerate(lines):
        if ANSWER_SECTION_RE.match(ln.strip()):
            ans_idx = i
            break
    if ans_idx is None:
        return []

    q_items = _collect_numbered(lines[:ans_idx])
    a_items = _collect_numbered(lines[ans_idx + 1:])
    if not q_items or not a_items:
        return []

    out: list[dict[str, Any]] = []
    for n, stem in q_items.items():
        answer = a_items.get(n, "").strip()
        if not answer or len(stem) < 6:
            continue
        out.append({"stem": stem, "options": [], "answer": answer,
                    "explanation": "", "knowledge_point": ""})
    return out


def infer_type(subject: str, q: dict[str, Any], hint: str = "") -> str:
    """题型推断。`hint` = 文件标题/正文首段——实测**必须靠标题**才能判准：
    如《2026年湖北专升本英语翻译填空练习（三）》里的题干本身并不含"翻译"二字。
    """
    answer = (q.get("answer") or "").strip()
    opts = q.get("options") or []
    letters = re.findall(r"[A-H]", answer.upper())
    if opts:
        return "multiple_choice" if len(letters) > 1 else "single_choice"
    if subject == "aca_llm":
        return "multiple_choice" if len(letters) > 1 else "single_choice"

    hay = f"{hint}\n{q.get('knowledge_point') or ''}\n{q.get('stem') or ''}"
    # 顺序很关键：具体题型必须排在其上位概念之前（"语法填空" 不能先被 "填空" 命中）
    rules = (
        ("连词成句", "sentence_build"),
        ("语法填空", "grammar_fill"),
        ("翻译填空", "translation_fill"),
        ("阅读填空", "reading_fill"),
        ("阅读理解", "reading_qa"),
        ("写作", "writing"), ("作文", "writing"), ("书面表达", "writing"),
        ("改错", "code_correction"),
        ("程序填空", "program_fill"),
        ("编程", "programming"), ("程序设计", "programming"),
        ("翻译", "translation_fill"),
        ("语法", "grammar_fill"),
        ("连词", "sentence_build"),
        ("阅读", "reading_fill"),
    )
    for key, name in rules:
        if key in hay:
            return name
    if "填空" in hay:
        return "reading_fill" if subject == "english" else "program_fill"
    return {"english": "reading_fill", "c_wuhan": "program_fill", "c_hbpu": "program_fill"}.get(subject, "single_choice")


def infer_difficulty(subject: str, q: dict[str, Any]) -> str:
    """DESIGN.md 第 13 节的机械代理指标（简化版：长度 + 关键词）。"""
    stem = q.get("stem") or ""
    opts = q.get("options") or []
    n = len(stem)
    hard_kw = ("指针", "递归", "文件", "结构体", "虚拟语气", "倒装", "从句", "综合")
    if any(k in stem for k in hard_kw) or n >= 200:
        return "难"
    if n >= 80 or len(opts) >= 4:
        return "中"
    return "易"


# ------------------------------------------------------------------ ACA 考纲索引


def build_syllabus_index() -> dict[str, Any]:
    """从 ACA 知识点 md 与官方课时 md 构建考纲索引；每条必须带 source，缺则标 未获取。"""
    kp_file = INBOX / "aca_llm" / "aca_v24_knowledge_points.md"
    lessons = INBOX / "aca_llm" / "aca_v24_lessons.md"
    index: dict[str, Any] = {"generated_at": now_iso(), "modules": [], "source_files": []}
    if kp_file.exists():
        index["source_files"].append(str(kp_file.relative_to(ROOT)))
    if lessons.exists():
        index["source_files"].append(str(lessons.relative_to(ROOT)))

    if not kp_file.exists():
        index["note"] = f"{UNKNOWN}（未找到 aca_v24_knowledge_points.md）"
        return index

    cur_mod: dict[str, Any] | None = None
    for line in kp_file.read_text(encoding="utf-8").splitlines():
        m = MODULE_RE.match(line)
        if m:
            cur_mod = {"no": int(m.group(1)), "name": m.group(2).strip(), "weight": None, "points": []}
            wm = re.search(r"(\d{1,2})\s*%", line)
            if wm:
                cur_mod["weight"] = f"{wm.group(1)}%"
            index["modules"].append(cur_mod)
            continue
        mr = KP_ROW_RE.match(line)
        if mr and cur_mod is not None:
            code, point, basis = mr.group(1), mr.group(2), mr.group(3)
            if point in {"知识点", "---"} or point.startswith("---"):
                continue
            source = basis.strip() if basis.strip() else UNKNOWN
            cur_mod["points"].append({
                "code": code,
                "knowledge_point": point,
                "syllabus_ref": cur_mod["name"],
                "source": source if source != "" else UNKNOWN,
            })

    total = sum(len(m["points"]) for m in index["modules"])
    index["total_points"] = total
    if total == 0:
        index["note"] = f"{UNKNOWN}（知识点 md 未解析出条目）"
    return index


# ------------------------------------------------------------------ 数据库


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def load_url_index() -> dict[str, str]:
    """从 cache.sqlite.fetched_urls 反查「本地文件名前缀 -> 原始 URL」（与 fetch.py 命名规则一致）。"""
    idx: dict[str, str] = {}
    if not CACHE_DB.exists():
        return idx
    import hashlib

    try:
        conn = connect(CACHE_DB)
        for (url,) in conn.execute("SELECT url FROM fetched_urls"):
            idx[hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]] = url
        conn.close()
    except Exception:  # noqa: BLE001
        pass
    return idx


def backfill_source_stats(per_domain: dict[tuple[str, str], int], parsed_by_domain: dict[tuple[str, str], int]) -> None:
    if not CACHE_DB.exists():
        return
    conn = connect(CACHE_DB)
    conn.executescript(
        """CREATE TABLE IF NOT EXISTS source_stats (
             subject TEXT, domain TEXT, fetched INTEGER DEFAULT 0, hits INTEGER DEFAULT 0,
             hit_rate REAL DEFAULT 0, last_fetch_at TEXT, low_freq INTEGER DEFAULT 0,
             PRIMARY KEY (subject, domain));"""
    )
    for (subject, domain), hits in parsed_by_domain.items():
        fetched = per_domain.get((subject, domain), 0)
        rate = (hits / fetched) if fetched else 0.0
        conn.execute(
            """INSERT INTO source_stats(subject, domain, fetched, hits, hit_rate, low_freq)
               VALUES(?,?,?,?,?,?)
               ON CONFLICT(subject, domain) DO UPDATE SET
                 hits=excluded.hits, hit_rate=excluded.hit_rate, low_freq=excluded.low_freq""",
            (subject, domain, fetched, hits, rate, 1 if (fetched >= 3 and rate < 0.2) else 0),
        )
    conn.commit()
    conn.close()


# ------------------------------------------------------------------ 主流程


def run(subject: str, dry_run: bool, limit: int | None) -> dict[str, Any]:
    from rapidfuzz import fuzz

    stats: dict[str, Any] = {"subjects": {}, "dry_run": dry_run, "images_skipped": [], "errors": []}
    url_index = load_url_index()
    forbidden_by_subject = load_forbidden_types()
    subjects = SUBJECTS if subject == "all" else [subject]

    for subj in subjects:
        inbox_dir = INBOX / subj
        db_path = DATA / f"{subj}.sqlite"
        sub_stat = {"files": 0, "questions": 0, "duplicates": 0, "merged": 0, "inserted": 0}
        if not inbox_dir.exists() or not db_path.exists():
            stats["subjects"][subj] = {**sub_stat, "note": "inbox 或库不存在"}
            continue
        if not dry_run and SUBJECTS_DIR.joinpath(subj).exists() is False:
            SUBJECTS_DIR.joinpath(subj).mkdir(parents=True, exist_ok=True)

        conn = connect(db_path)
        forbidden = forbidden_by_subject.get(subj, set())
        # 既有题：指纹 -> uid（跨源查重用）
        existing = conn.execute("SELECT question_uid, stem, source_credit FROM questions").fetchall()
        fp_map: dict[str, tuple[str, str]] = {}
        for uid, stem, credit in existing:
            if stem:
                fp_map[content_fingerprint(subj, stem)] = (uid, credit or "")
        uid_set = {uid for uid, _, _ in existing}

        files = sorted(
            [p for p in inbox_dir.rglob("*") if p.is_file()],
            key=lambda p: (EXT_PRIORITY.get(p.suffix.lower(), 99), str(p)),
        )
        parsed_here: dict[str, int] = {}
        for path in files:
            if limit and sub_stat["files"] >= limit:
                break
            ext = path.suffix.lower()
            if ext in IMG_EXT:
                stats["images_skipped"].append(str(path.relative_to(ROOT)))
                continue
            if ext not in EXT_PRIORITY and ext not in {".docx"}:
                continue
            if path.name.startswith(".") or path.name.startswith("_"):
                continue  # 以 . / _ 开头的辅助文件不解析
            if path.name in SKIP_FILES or any(part in SKIP_DIR_PARTS for part in path.parts):
                continue  # ACA 考纲/课时/知识点属「素材」，不当作题目解析
            sub_stat["files"] += 1
            try:
                text = read_text(path)
            except Exception as exc:  # noqa: BLE001
                stats["errors"].append({"file": str(path.relative_to(ROOT)), "error": str(exc)})
                continue

            fact_claim = strip_quotes(FACT_CLAIM_RE.search(text).group(1)) if FACT_CLAIM_RE.search(text) else ""
            fact_source = strip_quotes(FACT_SOURCE_RE.search(text).group(1)) if FACT_SOURCE_RE.search(text) else ""
            src_url = fact_source
            if not src_url:
                src_url = url_index.get(path.stem, "")

            # 标题提示：正文首段含文章标题（如「…英语翻译填空练习及答案（三）」），题型推断必须用它
            hint = text[:400]

            # 越界科目过滤：英语资料里混进了教育学/管理学等他科文章（实测来源）
            offtopic = OFFTOPIC_HINTS.get(subj, ())
            if offtopic and any(k in hint for k in offtopic):
                stats.setdefault("offtopic_skipped", []).append(str(path.relative_to(ROOT)))
                continue

            blocks = parse_questions(text)
            if not blocks:
                # 回退策略：模拟卷式「题目在前、答案集中在后」
                blocks = parse_answer_key_format(text)

            for q in blocks:
                qtype = infer_type(subj, q, hint)
                if qtype in forbidden:
                    # DESIGN.md 第 3/4 节：英语与 C 语言**不得出现选择题/判断题**
                    sub_stat["forbidden_dropped"] = sub_stat.get("forbidden_dropped", 0) + 1
                    continue
                sub_stat["questions"] += 1
                stem = q["stem"]
                fp = content_fingerprint(subj, stem)

                # 1) 跨源同题 → 合并来源
                if fp in fp_map:
                    sub_stat["duplicates"] += 1
                    old_uid, old_credit = fp_map[fp]
                    new_credit = old_credit
                    if src_url and src_url not in old_credit:
                        new_credit = (old_credit + " | " + src_url).strip(" |")
                        sub_stat["merged"] += 1
                        if not dry_run:
                            conn.execute("UPDATE questions SET source_credit=? WHERE question_uid=?", (new_credit, old_uid))
                    fp_map[fp] = (old_uid, new_credit)
                    continue

                # 2) 模糊兜底：与既有题相似度 > 0.9（rapidfuzz）
                dup_hit = None
                for uid, stem2, credit in conn.execute(
                    "SELECT question_uid, stem, source_credit FROM questions WHERE subject=?", (subj,)
                ):
                    if stem2 and fuzz.token_set_ratio(stem, stem2) > 90:
                        dup_hit = (uid, credit or "")
                        break
                if dup_hit:
                    sub_stat["duplicates"] += 1
                    old_uid, old_credit = dup_hit
                    if src_url and src_url not in old_credit:
                        sub_stat["merged"] += 1
                        if not dry_run:
                            conn.execute(
                                "UPDATE questions SET source_credit=? WHERE question_uid=?",
                                ((old_credit + " | " + src_url).strip(" |"), old_uid),
                            )
                    continue

                uid = generate_uid(subj, src_url or path.name, stem)
                if uid in uid_set:
                    sub_stat["duplicates"] += 1
                    continue
                uid_set.add(uid)
                fp_map[fp] = (uid, src_url)

                if dry_run:
                    sub_stat["inserted"] += 1
                    continue

                conn.execute(
                    """INSERT OR IGNORE INTO questions
                       (question_uid, subject, source_type, source_url, source_credit,
                        question_type, stem, options, answer, explanation, knowledge_point,
                        difficulty, status, version, fact_claim, fact_source, fact_verified)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?, 'parsed', 1, ?, ?, 0)""",
                    (
                        uid, subj, "fetch", src_url or UNKNOWN, src_url or "",
                        qtype, stem,
                        json.dumps(q.get("options") or [], ensure_ascii=False),
                        q.get("answer") or "", q.get("explanation") or "", q.get("knowledge_point") or "",
                        infer_difficulty(subj, q),
                        fact_claim, fact_source or src_url or UNKNOWN,
                    ),
                )
                sub_stat["inserted"] += 1
                parsed_here[src_url] = parsed_here.get(src_url, 0) + 1

        if not dry_run:
            conn.commit()
        total = conn.execute("SELECT count(*) FROM questions").fetchone()[0]
        sub_stat["db_total"] = total
        conn.close()
        stats["subjects"][subj] = sub_stat

    # ACA 考纲索引（无论 dry-run 都生成，便于查看）
    index = build_syllabus_index()
    if not dry_run:
        idx_path = SUBJECTS_DIR / "aca_llm" / "syllabus_index.json"
        idx_path.parent.mkdir(parents=True, exist_ok=True)
        idx_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
        stats["syllabus_index"] = {"path": str(idx_path.relative_to(ROOT)), "modules": len(index["modules"]),
                                   "points": index.get("total_points", 0)}
    else:
        stats["syllabus_index"] = {"modules": len(index["modules"]), "points": index.get("total_points", 0), "dry_run": True}

    if not dry_run:
        backfill_source_stats({}, {})
    return stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="解析 inbox 并入库（唯一写 questions 表的入口）")
    ap.add_argument("--subject", default="all", choices=SUBJECTS + ["all"])
    ap.add_argument("--dry-run", action="store_true", help="只统计与解析，不写库")
    ap.add_argument("--limit", type=int, default=None, help="每科目最多处理的文件数")
    args = ap.parse_args(argv)

    stats = run(args.subject, args.dry_run, args.limit)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
