#!/usr/bin/env python
"""把「选项写在 stem 里、`options` 列却是空」的客观题**补出真正的选项**。

为什么需要（2026-10-24 用户报障）：
  刷题页拿 `/api/questions` 的 `options_parsed` 渲染单选/多选按钮，
  该字段来自 `app.py:runtime_options()` → `judge_local.options_from_stem()`。
  后者有一道**关键词黑名单**闸门（正确/错误/不是/不包括/不依赖/不需要/不能/无法/not/true/false/选出/选择），
  本意是防"题面被吞进选项"，但选项正文里出现「不需要/无法/不能」是**完全正常的表述**：
      A. 软件仅指计算机程序本身,不包括文档        ← 被 `不包括` 误杀
      B. …弥补模型知识截止和无法直接操作外部系统的局限  ← 被 `无法` 误杀
  结果这些题 `objective=False`，前端退化成纯文本框，**点不了选项、交不了卷**。
  实测全库 2,343 道题干内嵌选项的客观题里，有 **541 道**这样被误杀
  （c_wuhan 522 / aca_llm 12 / c_hbpu 7）。

本脚本的口径（**结构化校验，不用关键词黑名单**）：
  1. 解析出的字母必须从 A 起连续，且 2–8 个；
  2. 每个选项正文 1–`--max-body` 字（默认 200，比渲染闸门的 60 宽，因为选项本来就长）；
  3. **题面（第一个标记之前的文字）末尾的 20 个非空白字不得出现在任何选项正文里**
     —— 这才是"题面被吞进选项"的真正特征；
  4. 选项正文里不得再出现 ≥2 个「字母+分隔符」标记（说明吞并了后续选项）；
  5. 选项正文不得以「字母+分隔符」开头。
  不满足任一 → 不写，只报告（**宁可不改，也不写错选项**）。

写库契约（项目硬性约束）：
  - 只写 `questions` 的 `options` / `reviewed_by` / `version`；
  - 不碰 `wrong_book` / `review_log` / `daily_progress`；
  - 默认 dry-run，`--apply` 才写；写前自动备份到 `data/backup/`。

用法:
    python scripts/fix_stem_options.py                       # dry-run，四个库都体检
    python scripts/fix_stem_options.py --subject aca_llm      # 只看 ACA
    python scripts/fix_stem_options.py --dump data/backup/stem-options-props.json
    python scripts/fix_stem_options.py --apply                # 真写库（先备份）
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
BACKUP = DATA / "backup"
SUBJECTS = ("english", "c_wuhan", "c_hbpu", "aca_llm")
TARGET_TYPES = ("single_choice", "multiple_choice")

sys.path.insert(0, str(ROOT / "scripts"))
import judge_local as JL  # noqa: E402

# 选项标记：「A.」/「A、」/「A)」/「A．」（NFKC 后全角转半角，但仍保留中文顿号）
MARKER_RE = re.compile(r"(?<![A-Za-z0-9_])([A-H])\s*[.、)．:：]\s*")
_LETTERS = "ABCDEFGH"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def opt_count(raw) -> int:
    try:
        arr = json.loads(raw) if isinstance(raw, str) else raw
        return len(arr) if isinstance(arr, list) else 0
    except (TypeError, ValueError):
        return 0


def squash(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def robust_parse(stem: str) -> dict[str, str]:
    """比 `judge_local.parse_embedded_options` 更宽容的标记切分（只给本脚本用）。

    修两类实测坏法（`judge_local` 的正则都不吃）：
      ① **标记重复**：`A. A. 比较 $a$ 和 $b$…`（采集时字母被写了两遍）
         → 后一个标记才是真正的选项开头，前一个当噪声丢掉；
      ② **选项挤在一行**：`…机制是什么？A. 循环连接 B. 卷积操作 C. 自注意力机制 D. 池化操作`
         → 不要求标记前有换行，按标记位置切。
    切完交给 `validate()` 做结构化校验，校验不过照样不写。
    """
    text = unicodedata.normalize("NFKC", stem or "")
    marks = [m for m in MARKER_RE.finditer(text) if m.group(1) in _LETTERS]
    if len(marks) < 2:
        return {}

    # ① 把"紧跟着同字母、且中间没有正文"的重复标记合并成一组：
    #    选项**边界的起点**用组里第一个标记，**正文的起点**用组里最后一个标记之后
    #    （先出现的那个是噪声，但边界必须从它算起，否则会吞掉下一个选项的 "B."）
    groups: list[dict] = []
    for m in marks:
        if groups:
            g = groups[-1]
            between = text[g["last"].end(): m.start()].strip()
            if not between and g["letter"] == m.group(1):
                g["last"] = m
                continue
        groups.append({"letter": m.group(1), "first": m, "last": m})

    out: dict[str, str] = {}
    for i, g in enumerate(groups):
        body_start = g["last"].end()
        body_end = groups[i + 1]["first"].start() if i + 1 < len(groups) else len(text)
        body = re.sub(r"\s+", " ", text[body_start:body_end]).strip()
        # ② 正文里如果又把同字母标记写了一遍，剥掉
        body = re.sub(rf"^{re.escape(g['letter'])}\s*[.、)．:：]\s*", "", body).strip()
        if body and not out.get(g["letter"]):
            out[g["letter"]] = body
    return out if len(out) >= 2 else {}


def validate(stem: str, opts: dict[str, str], max_body: int) -> tuple[bool, str]:
    keys = sorted(opts)
    expected = list(_LETTERS[: len(keys)])
    if keys != expected:
        return False, f"字母不连续 {keys}"
    if not 2 <= len(keys) <= 8:
        return False, f"选项数 {len(keys)}"

    # 题面 = 第一个标记之前的文字
    text = unicodedata.normalize("NFKC", stem or "")
    first = MARKER_RE.search(text)
    if not first:
        return False, "找不到首个标记"
    face = text[: first.start()]
    face_tail = squash(face)[-20:]
    if len(face_tail) >= 8:
        for key, body in opts.items():
            if face_tail in squash(body):
                return False, f"{key} 吞进了题面"

    for key, body in opts.items():
        if not 1 <= len(body) <= max_body:
            return False, f"{key} 正文长度 {len(body)}"
        if len(MARKER_RE.findall(body)) >= 2:
            return False, f"{key} 里还有多个选项标记（吞并）"
        if MARKER_RE.match(body):
            return False, f"{key} 以标记开头"
    return True, "ok"


def plan_subject(subj: str, max_body: int):
    path = DATA / f"{subj}.sqlite"
    if not path.exists():
        return {"subject": subj, "skipped": "库不存在"}, [], []
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = list(con.execute(
        "SELECT id, question_uid, question_type, COALESCE(stem,'') AS stem, "
        "COALESCE(options,'') AS options, COALESCE(answer,'') AS answer, COALESCE(status,'') AS status "
        "FROM questions WHERE status<>'archived' ORDER BY id"))
    con.close()

    todo, rejected, stats = [], [], {
        "subject": subj, "scanned": len(rows), "candidates": 0,
        "ok": 0, "already": 0,
    }
    for r in rows:
        if r["question_type"] not in TARGET_TYPES:
            continue
        if opt_count(r["options"]) >= 2:
            stats["already"] += 1
            continue
        stats["candidates"] += 1
        parsed = robust_parse(r["stem"]) or JL.parse_embedded_options(r["stem"])
        if len(parsed) < 2:
            rejected.append({"id": r["id"], "reason": "题干里解析不出 2 个以上选项"})
            continue
        ok, reason = validate(r["stem"], parsed, max_body)
        if not ok:
            rejected.append({"id": r["id"], "reason": reason,
                             "opts": {k: v[:60] for k, v in parsed.items()}})
            continue
        todo.append({
            "id": int(r["id"]), "question_uid": r["question_uid"], "answer": r["answer"],
            "options": [{"key": k, "text": parsed[k]} for k in sorted(parsed)],
        })
        stats["ok"] += 1
    return stats, todo, rejected


def load_proposals(path: Path) -> list[dict]:
    """`--from-json` 读入的提案：`[{"id": 82, "options": [{"key":"A","text":"…"}, …]}]`。

    只做形状校验（字母从 A 起连续、正文非空），**内容对不对是提案方的事**，
    调用方（如 `scripts/fill_missing_options_ai.py`）负责在生成端把好关。
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for item in data:
        opts = item.get("options") or []
        keys = [str(o.get("key") or "").strip().upper() for o in opts]
        if len(opts) < 2 or keys != list(_LETTERS[: len(keys)]):
            raise SystemExit(f"提案 id={item.get('id')} 选项字母不合法: {keys}")
        cleaned = [{"key": k, "text": str(o.get("text") or "").strip()} for k, o in zip(keys, opts)]
        if any(not o["text"] for o in cleaned):
            raise SystemExit(f"提案 id={item.get('id')} 有空的选项正文")
        out.append({"id": int(item["id"]), "options": cleaned})
    return out


def apply_proposals(subj: str, proposals: list[dict], tag: str) -> int:
    path = DATA / f"{subj}.sqlite"
    if not proposals:
        return 0
    bak = backup_db(path)
    print(f"  [备份] {bak.name}")
    ts = now_iso()
    con = sqlite3.connect(str(path))
    con.execute("PRAGMA busy_timeout=30000")
    try:
        for item in proposals:
            con.execute(
                "UPDATE questions SET options=?, reviewed_by=?, version=COALESCE(version,1)+1 WHERE id=?",
                (json.dumps(item["options"], ensure_ascii=False), f"{tag}@{ts}", item["id"]),
            )
        con.commit()
    finally:
        con.close()
    print(f"  [已改库] {tag} 补选项 {len(proposals)} 题")
    return len(proposals)


def backup_db(path: Path) -> Path:
    BACKUP.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = BACKUP / f"{path.stem}-{stamp}{path.suffix}"
    src = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    dst = sqlite3.connect(str(target))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return target


def main() -> int:
    ap = argparse.ArgumentParser(description="给「选项写在题干里」的客观题补 options 列（默认 dry-run）")
    ap.add_argument("--subject", default="all", help="科目名，或 all")
    ap.add_argument("--max-body", type=int, default=200, help="选项正文最大字数（默认 200）")
    ap.add_argument("--apply", action="store_true", help="真写库（先自动备份）")
    ap.add_argument("--dump", default="", help="把「将被写入的选项」导出成 JSON，便于人工抽查")
    ap.add_argument("--from-json", default="", help="不再从题干解析，直接执行该 JSON 提案（见 load_proposals）")
    ap.add_argument("--data-dir", default="", help="只改这个数据目录下的库（默认 题库项目/data；便携版可传其 data 路径）")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.data_dir:
        global DATA, BACKUP
        DATA = Path(args.data_dir)
        BACKUP = DATA / "backup"
        print(f"[data-dir] {DATA}")

    if args.from_json:
        path = Path(args.from_json)
        if not path.is_absolute():
            path = ROOT / path
        proposals = load_proposals(path)
        print(f"[from-json] {path.name} 共 {len(proposals)} 条提案")
        if args.apply:
            apply_proposals(args.subject, proposals, "auto:fix_stem_options:json")
        else:
            for item in proposals[:3]:
                print(f"   · id={item['id']} " + " / ".join(
                    f"{o['key']}. {o['text'][:40]}" for o in item["options"]))
            print("\n（dry-run：未改库。加 --apply 才写入）")
        return 0

    subjects = list(SUBJECTS) if args.subject == "all" else [args.subject]
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    report: dict = {"applied_at": None if not args.apply else now_iso(), "subjects": {}}
    dump_all: dict = {}

    for subj in subjects:
        stats, todo, rejected = plan_subject(subj, args.max_body)
        report["subjects"][subj] = {**stats, "rejected": len(rejected),
                                    "rejected_samples": rejected[:5]}
        print(f"===== {subj}")
        if stats.get("skipped"):
            print(f"  跳过：{stats['skipped']}")
            continue
        print(f"  客观题中 options 已有值的：{stats['already']}")
        print(f"  需要补选项的候选：{stats['candidates']}")
        print(f"  ✅ 通过结构化校验、可写入：{stats['ok']}")
        print(f"  ⛔ 不写（解析不出/校验不过）：{len(rejected)}")
        for rj in rejected[:4]:
            print(f"      · id={rj['id']} {rj['reason']}")
            for k, v in (rj.get("opts") or {}).items():
                print(f"          {k}. {v}")
        if todo:
            print("  写入样例：")
            for item in todo[:2]:
                print(f"      · id={item['id']} ans={item['answer']}")
                for o in item["options"]:
                    print(f"          {o['key']}. {o['text'][:64]}")
        dump_all[subj] = todo

        if not args.apply or not todo:
            continue
        path = DATA / f"{subj}.sqlite"
        bak = backup_db(path)
        print(f"  [备份] {bak.name}")
        ts = now_iso()
        con = sqlite3.connect(str(path))
        con.execute("PRAGMA busy_timeout=30000")
        try:
            for item in todo:
                con.execute(
                    "UPDATE questions SET options=?, reviewed_by=?, "
                    "version=COALESCE(version,1)+1 WHERE id=?",
                    (json.dumps(item["options"], ensure_ascii=False),
                     f"auto:fix_stem_options@{ts}", item["id"]),
                )
            con.commit()
        finally:
            con.close()
        print(f"  [已改库] 补选项 {len(todo)} 题")

    if args.dump:
        out = Path(args.dump)
        if not out.is_absolute():
            out = ROOT / out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(dump_all, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n[抽查文件] {out}")

    if args.apply:
        log = BACKUP / f"fix-stem-options-{stamp}.json"
        log.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[报告] {log}")
    else:
        print("\n（dry-run：未改库。加 --apply 才写入，写前自动备份到 data/backup/）")
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
