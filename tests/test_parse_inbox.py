#!/usr/bin/env python
"""parse_inbox.py 离线 smoke test（不联网；临时目录只用 tests/.tmp/parse_inbox/）。

运行: python tests/test_parse_inbox.py
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import parse_inbox as pi  # noqa: E402
import init_db  # noqa: E402

TMPROOT = ROOT / "tests" / ".tmp" / "parse_inbox"

SAMPLE = """# 样题
> 来源：某处
`fact_claim`: "示例断言"
`fact_source`: "https://example.com/a"

---

数据预处理中，法律问题通常涉及以下哪项？
A、数据的收集方法
B、数据的存储安全
C、数据的共享与转让
D、数据的分析技术
答案：C
知识点：法律，合规

第一个开创性的将Transformer应用于计算机视觉领域。
A、ERNIE-ViL
B、VisionTransformer
C、ViLBERT
D、CLIP
答案：B
知识点：Transformer，视觉
"""

PROSE = """# 考纲解读
> 这是站点自撰的备考解读

本考试没有选择题。
同学们要注意语法填空的答题技巧，先把句子结构看清楚。
"""


def fresh() -> Path:
    shutil.rmtree(TMPROOT, ignore_errors=True)
    TMPROOT.mkdir(parents=True, exist_ok=True)
    return TMPROOT


def cleanup() -> None:
    shutil.rmtree(TMPROOT, ignore_errors=True)


# ---------------------------------------------------------------- 纯函数


def test_strip_leading_metadata() -> None:
    out = pi.strip_leading_metadata(SAMPLE)
    assert out.startswith("数据预处理中"), f"应剥掉元数据，实际开头：{out[:40]!r}"
    assert "fact_source" not in out.splitlines()[0]


def test_parse_questions_recall_and_fields() -> None:
    qs = pi.parse_questions(SAMPLE)
    assert len(qs) == 2, f"应解析出 2 题，实际 {len(qs)}"
    assert qs[0]["stem"].startswith("数据预处理中")
    assert len(qs[0]["options"]) == 4 and qs[0]["answer"] == "C"
    assert qs[0]["knowledge_point"] == "法律，合规"
    # 第二题不带问号且以中文结尾 —— 必须仍被识别为新题（回归：曾被当成上题知识点续行吞掉）
    assert qs[1]["stem"].startswith("第一个开创性的"), f"第二题题干错误：{qs[1]['stem'][:40]!r}"
    assert qs[1]["answer"] == "B"


def test_prose_yields_no_questions() -> None:
    assert pi.parse_questions(PROSE) == [], "纯散文不得产出题目（质量闸门）"


def test_infer_type() -> None:
    assert pi.infer_type("aca_llm", {"answer": "C", "options": [1, 2, 3, 4]}) == "single_choice"
    assert pi.infer_type("aca_llm", {"answer": "ABC", "options": [1, 2, 3, 4]}) == "multiple_choice"
    assert pi.infer_type("english", {"answer": "", "stem": "请完成下面的语法填空"}) == "grammar_fill"
    assert pi.infer_type("c_wuhan", {"answer": "", "stem": "指出下面程序的编程错误"}) in {"programming", "code_correction"}


def test_infer_difficulty() -> None:
    assert pi.infer_difficulty("c_wuhan", {"stem": "短题", "options": []}) == "易"
    assert pi.infer_difficulty("c_wuhan", {"stem": "涉及指针与递归的题", "options": []}) == "难"
    assert pi.infer_difficulty("english", {"stem": "x" * 100, "options": []}) == "中"


# ---------------------------------------------------------------- 端到端（临时库）


def _mk_subject_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.executescript(init_db.SUBJECT_SCHEMA)
    conn.commit()
    conn.close()


def _fake_patches(tmp: Path):
    inbox = tmp / "inbox"
    data = tmp / "data"
    subjects = tmp / "subjects"
    for d in (inbox / "aca_llm", data, subjects / "aca_llm"):
        d.mkdir(parents=True, exist_ok=True)
    return inbox, data, subjects


def test_end_to_end_insert_dedup_and_syllabus_index() -> None:
    tmp = fresh()
    inbox, data, subjects = _fake_patches(tmp)
    _mk_subject_db(data / "aca_llm.sqlite")

    (inbox / "aca_llm" / "a_samples.md").write_text(SAMPLE, encoding="utf-8")
    # 同一道题换个来源再放一份 → 必须合并（不新增行），且 source_credit 记录两个来源
    dup = SAMPLE.replace("https://example.com/a", "https://example.com/b")
    (inbox / "aca_llm" / "b_samples.md").write_text(dup, encoding="utf-8")
    # 素材类文件必须被跳过
    (inbox / "aca_llm" / "aca_v24_knowledge_points.md").write_text(SAMPLE, encoding="utf-8")

    origin = (pi.INBOX, pi.DATA, pi.SUBJECTS_DIR, pi.CACHE_DB)
    pi.INBOX, pi.DATA, pi.SUBJECTS_DIR, pi.CACHE_DB = inbox, data, subjects, data / "cache.sqlite"
    try:
        stats = pi.run("aca_llm", dry_run=False, limit=None)
        conn = sqlite3.connect(str(data / "aca_llm.sqlite"))
        rows = conn.execute("SELECT question_uid, status, answer, options, fact_claim, source_credit FROM questions").fetchall()
        conn.close()

        assert len(rows) == 2, f"同题跨源应合并为 2 行，实际 {len(rows)}"
        assert all(r[1] == "parsed" for r in rows), "status 必须是 parsed"
        assert all(json.loads(r[3]) for r in rows), "options 必须是可解析 JSON"
        assert any(r[4] == "示例断言" for r in rows), "fact_claim 应来自文件头显式标注"
        credits = " ".join(r[5] or "" for r in rows)
        assert "example.com/b" in credits, "跨源来源应被追加进 source_credit"
        assert stats["subjects"]["aca_llm"]["merged"] >= 1, "应记录 merged"
        # 素材文件被跳过：处理文件数应只算 a_samples/b_samples
        assert stats["subjects"]["aca_llm"]["files"] == 2, f"素材文件未被跳过：{stats['subjects']['aca_llm']}"
        # 考纲索引
        idx = json.loads((subjects / "aca_llm" / "syllabus_index.json").read_text(encoding="utf-8"))
        assert "modules" in idx and "generated_at" in idx
    finally:
        pi.INBOX, pi.DATA, pi.SUBJECTS_DIR, pi.CACHE_DB = origin
        cleanup()


def test_dry_run_writes_nothing() -> None:
    tmp = fresh()
    inbox, data, subjects = _fake_patches(tmp)
    db = data / "aca_llm.sqlite"
    _mk_subject_db(db)
    (inbox / "aca_llm" / "a_samples.md").write_text(SAMPLE, encoding="utf-8")

    origin = (pi.INBOX, pi.DATA, pi.SUBJECTS_DIR, pi.CACHE_DB)
    pi.INBOX, pi.DATA, pi.SUBJECTS_DIR, pi.CACHE_DB = inbox, data, subjects, data / "cache.sqlite"
    try:
        stats = pi.run("aca_llm", dry_run=True, limit=None)
        conn = sqlite3.connect(str(db))
        n = conn.execute("SELECT count(*) FROM questions").fetchone()[0]
        conn.close()
        assert n == 0, "dry-run 不得写入"
        assert stats["subjects"]["aca_llm"]["inserted"] == 2
        assert not (subjects / "aca_llm" / "syllabus_index.json").exists(), "dry-run 不写索引"
    finally:
        pi.INBOX, pi.DATA, pi.SUBJECTS_DIR, pi.CACHE_DB = origin
        cleanup()


def test_compile() -> None:
    import py_compile

    py_compile.compile(str(ROOT / "scripts" / "parse_inbox.py"), doraise=True)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS {fn.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"  FAIL {fn.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  ERROR {fn.__name__}: {type(exc).__name__}: {exc}")
    print(f"{len(fns) - failed}/{len(fns)} passed")
    raise SystemExit(1 if failed else 0)
