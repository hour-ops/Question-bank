#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""data/exam_samples 样板库的回归测试（纯本地、只读）。

跑法：
    python tests/test_export_exam_samples.py

校验四件事：
  ① 结构：每条 sample 都有 stem/answer/explanation/exam/trust/knowledge_point/material；
     答案与解析非空。
  ② 材料型整组：material_blanks_total == len(material_blanks)，且 material 非空。
  ③ **零改写**：把 sample 的题干/材料去掉 `{{__BLANK_n__}}` 标记后，必须能在原始
     `inbox/real_exams/*.json` 里逐字找到（连词成句的 `词组 / 词组` 斜杠格式必须原样保留）。
  ④ 索引一致：_index.json 的统计与各题型文件实际内容对得上。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# 中文 Windows 控制台默认 GBK：把无法编码的字符替换掉，别让打印把测试搞崩
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(errors="replace")
    except Exception:  # noqa: BLE001
        pass

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "exam_samples"
SRC = ROOT / "inbox" / "real_exams"

REQ = ["stem", "answer", "explanation", "exam", "trust", "knowledge_point", "material"]
PH = re.compile(r"\{\{__[A-Z]+_\d+__\}\}")
WS = re.compile(r"\s+")
failures: list[str] = []


def load(p: Path):
    return json.loads(p.read_text(encoding="utf-8-sig"))


def plain(node) -> str:
    """只取非 blank 块的原文值（用于零改写比对）。"""
    if isinstance(node, str):
        return node
    if not isinstance(node, dict):
        return ""
    bs = node.get("blocks")
    if isinstance(bs, list):
        return "".join(str(b.get("value") or "") for b in bs
                       if isinstance(b, dict) and b.get("type") != "blank")
    return str(node.get("value") or "")


def raw_texts(path: Path):
    """原始卷里所有「题干类」文字。注意 section.directions 也算：
    语音题的源 item.stem 是空块，提问实际写在 directions 里，构建时原样提上来当题干。"""
    d = load(path)
    stems, mats = [], []
    for sec in (d.get("exam") or {}).get("sections") or []:
        mats.append("".join(plain(m) for m in (sec.get("materials") or [])))
        stems.append(plain(sec.get("directions")))
        for it in sec.get("items") or []:
            stems.append(plain(it.get("stem")))
    for q in (d.get("exam") or {}).get("questions") or []:
        mats.append(plain(q.get("content")))
        stems.append(plain(q.get("content")))
        for s in q.get("subQuestions") or []:
            stems.append(plain(s.get("content")))
    return [x for x in stems if x.strip()], [x for x in mats if x.strip()]


def check(cond: bool, msg: str) -> None:
    if not cond:
        failures.append(msg)


def main() -> int:
    type_files = [p for p in sorted(OUT.rglob("*.json")) if not p.name.startswith("_")]
    check(bool(type_files), "没有找到任何题型文件，先跑 scripts/export_exam_samples.py")
    if not type_files:
        print("\n".join(failures))
        return 1

    n_samples = 0
    cache: dict[Path, tuple] = {}
    seen_types = set()
    for p in type_files:
        doc = load(p)
        subj, t = doc.get("subject"), doc.get("type")
        if subj == "aca_llm":
            check(not (doc.get("samples") or []), f"{p.name}: ACA 应为空")
            continue
        check(bool(subj and t), f"{p.name}: 缺 subject/type")
        check(p.name == f"{t}.json" and p.parent.name == subj,
              f"{p.name}: 文件名/目录与 subject/type 不一致（{subj}/{t}）")
        seen_types.add((subj, t))
        samples = doc.get("samples") or []
        n_samples += len(samples)
        for i, s in enumerate(samples):
            tag = f"{subj}/{t}[{i}]"
            for k in REQ:
                check(k in s, f"{tag}: 缺字段 {k}")
            check(bool(str(s.get("answer") or "").strip()), f"{tag}: 答案为空")
            check(bool(str(s.get("explanation") or "").strip()), f"{tag}: 解析为空")
            check(bool(str(s.get("exam") or "").strip()), f"{tag}: exam 为空")
            check(bool(str(s.get("trust") or "").strip()), f"{tag}: trust 为空")
            check(bool(s.get("knowledge_point_ids")) or "unmapped" in str(s.get("knowledge_point_how")),
                  f"{tag}: 既无知识点又没记 unmapped 原因")
            if s.get("kind") == "material":
                bl = s.get("material_blanks") or []
                check(bool(str(s.get("material") or "").strip()), f"{tag}: 材料型但 material 为空")
                check(s.get("material_blanks_total") == len(bl),
                      f"{tag}: material_blanks_total={s.get('material_blanks_total')} != len={len(bl)}")
                check(bool(bl), f"{tag}: 材料型但没有空")
                for b in bl:
                    check(bool(str(b.get("answer") or "").strip()), f"{tag}: 空 #{b.get('no')} 无答案")
            else:
                check(bool(str(s.get("stem") or "").strip()), f"{tag}: 单题但题干为空")

            # ---- 零改写 ----
            f = SRC / str(s["exam"])
            check(f.exists(), f"{tag}: 原始卷不存在 {s['exam']}")
            if not f.exists():
                continue
            if f not in cache:
                cache[f] = raw_texts(f)
            stems, mats = cache[f]
            if s.get("kind") == "material":
                mine = WS.sub("", PH.sub("", str(s["material"])))
                check(any(mine in WS.sub("", PH.sub("", r)) for r in mats),
                      f"{tag}: 材料文字在原始卷里找不到（可能被改写）")
            else:
                mine = WS.sub("", PH.sub("", str(s["stem"])))
                ok = any(mine == WS.sub("", PH.sub("", r)) or mine in WS.sub("", PH.sub("", r))
                         or WS.sub("", PH.sub("", r)) in mine for r in stems)
                check(ok, f"{tag}: 题干在原始卷里找不到（可能被改写）")

    # ---- 连词成句斜杠格式 ----
    sb = OUT / "english" / "sentence_build.json"
    if sb.exists():
        for i, s in enumerate(load(sb).get("samples") or []):
            check("/" in str(s.get("stem") or ""), f"sentence_build[{i}]: 丢掉 `/` 词组格式")

    # ---- 索引一致 ----
    idx = load(OUT / "_index.json")
    check(idx["totals"]["samples"] == n_samples,
          f"_index.totals.samples={idx['totals']['samples']} != 实际 {n_samples}")
    for subj, types in (idx.get("by_subject_type") or {}).items():
        for t, meta in types.items():
            if subj == "aca_llm":
                continue
            check((subj, t) in seen_types, f"_index 里有 {subj}/{t} 但文件不存在")
            check(meta["samples"] == len(load(OUT / subj / f"{t}.json")["samples"]),
                  f"_index 的 {subj}/{t} 样例数与文件不符")

    print(f"检查了 {len(type_files)} 个题型文件 / {n_samples} 条样例")
    if failures:
        print(f"\n失败 {len(failures)} 项：")
        for x in failures[:40]:
            print("  - " + x)
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
