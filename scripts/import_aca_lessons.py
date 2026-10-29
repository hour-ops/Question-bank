#!/usr/bin/env python
"""把阿里云 edu 的 ACA 课时 JSON 导入为可解析的 Markdown（**不写数据库**）。

背景：`https://edu.aliyun.com/apiv3/course/getLessonContent?courseId=3139400&lessonId=<id>`
**需要登录态**（403 NEED_LOGIN），所以先用浏览器会话 `browser_download` 下载原始 JSON 到本地，
再由本脚本转成文本。这样既保住完整原文，又不把大段文本塞进模型上下文。

用法:
    python scripts/import_aca_lessons.py [--src <含 aca_lesson_*.json 的目录>]

产出:
    inbox/aca_llm/lessons/<序号>_<考点>.md     # 每课时一个文件
    inbox/aca_llm/aca_v24_lessons.md           # 合并版（含来源 URL 与标题）
    inbox/aca_llm/lessons/raw/<lessonId>.json  # 原始 JSON（可追溯）
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
OUTDIR = ROOT / "inbox" / "aca_llm" / "lessons"
RAWDIR = OUTDIR / "raw"
COMBINED = ROOT / "inbox" / "aca_llm" / "aca_v24_lessons.md"
COURSE_ID = "3139400"

# 课时顺序与考点标题（来自 listCourseLessons / 课程页）
LESSONS = [
    (1, "344950088", "考点1：大模型概念"),
    (2, "344950108", "考点2：提示词工程"),
    (3, "344950190", "考点3：增强大模型应用的能力"),
    (4, "344950255", "考点4：大模型微调"),
    (5, "344950305", "考点5：大模型 Agent"),
    (6, "344950376", "考点6：安全合规"),
]


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text("\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def pick_content(data: dict) -> tuple[str, str]:
    """在 data 里找最像正文的字段，返回 (text, used_key)。"""
    best, best_key = "", ""
    for key, val in data.items():
        if isinstance(val, str) and len(val) > len(best):
            best, best_key = val, key
    if not best:
        return "", ""
    looks_html = bool(re.search(r"<(p|div|br|h[1-6]|li|span)\b", best, re.I))
    return (html_to_text(best) if looks_html else best.strip()), best_key


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(Path.home() / "Downloads"))
    args = ap.parse_args()
    src = Path(args.src)

    OUTDIR.mkdir(parents=True, exist_ok=True)
    RAWDIR.mkdir(parents=True, exist_ok=True)

    parts: list[str] = []
    total = 0
    missing: list[str] = []

    for idx, lesson_id, title in LESSONS:
        f = src / f"aca_lesson_{lesson_id}.json"
        if not f.exists():
            missing.append(lesson_id)
            print(f"  [MISS] {f}")
            continue
        shutil.copy2(f, RAWDIR / f"{lesson_id}.json")
        payload = json.loads(f.read_text(encoding="utf-8"))
        if payload.get("code") != "00000":
            print(f"  [BAD ] {lesson_id}: code={payload.get('code')} msg={payload.get('message')}")
            missing.append(lesson_id)
            continue
        data = payload.get("data") or {}
        text, key = pick_content(data)
        url = f"https://edu.aliyun.com/course/{COURSE_ID}/lesson/{lesson_id}"
        body = (
            f"# {title}\n\n"
            f"> 来源：`{url}`（页面标题：阿里云大模型工程师ACA认证备考指南_学习资源库_阿里云培训中心-阿里云）\n"
            f"> 接口：`/apiv3/course/getLessonContent?courseId={COURSE_ID}&lessonId={lesson_id}`（需登录态）\n"
            f"> 原始字段：`{key}`；原始 JSON：`inbox/aca_llm/lessons/raw/{lesson_id}.json`\n"
            f"`fact_source`: \"{url}\"\n\n"
            f"{text}\n"
        )
        (OUTDIR / f"{idx}_{title.split('：')[-1]}.md").write_text(body, encoding="utf-8")
        parts.append(body)
        total += len(text)
        print(f"  [ok  ] {title}  字段={key}  字符={len(text)}")

    if parts:
        COMBINED.write_text(
            "# 阿里云大模型工程师 ACA · 官方课程「考点指导」6 课时原文\n\n"
            "> 来源课程：`https://edu.aliyun.com/course/3139400/`（阿里云大模型工程师ACA认证备考指南）\n"
            "> 抓取方式：`browser_download`（浏览器会话，接口需登录态）→ 本地 JSON → 本脚本转文本\n"
            "> ⚠️ 这是**官方课程页原文**，优先级高于第三方转载样题；知识点抽取以本文件为准\n\n"
            + "\n\n---\n\n".join(parts),
            encoding="utf-8",
        )

    print(f"\n合并文件: {COMBINED}  总字符={total}")
    if missing:
        print(f"缺失/失败课时: {missing}")
        return 1
    print("RESULT: OK 6/6")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
