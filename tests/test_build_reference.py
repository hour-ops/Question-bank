#!/usr/bin/env python
"""build_reference.py 离线测试 —— **零网络、零 API 花费、只读题库**。

被测对象: `scripts/build_reference.py`（参考库构建：考纲 + 知识点 + 真题样例）
下游契约: `scripts/validate_and_fill.py` 的 `few_shot()` / `load_reference()`

覆盖（按重要性）:
  ① 取样优先级   official_exam > textbook > third_party；**绝不取 ai_generated**（source_type='generate'）
                 与 `status='rejected'`（审核已判不合格）；无解析时才放宽并在 quality_note 说明
  ② 整块题       材料型题按 group_uid 合成**整块**：material 原文 + blanks 全部空，绝不拆开
  ③ 连词成句     `词组 / 词组` 斜杠原格式**零改写**（渲染层才切词卡）
  ④ 取样确定性   同一份库两次构建结果完全一致（不用 ORDER BY RANDOM()）；条数 ≤ k、跨 exam 轮转
  ⑤ 只读         构建前后 sqlite 的 mtime/size/sha256 必须不变
  ⑥ few_shot 集成 参考库存在 → 返回带 exam/trust 的真题样例；不存在 → 回退随机且不报错（向后兼容）

⚠️ 临时目录只用 tests/.tmp/build_reference/<case>/。

运行: python tests/test_build_reference.py
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import build_reference as br  # noqa: E402
import init_db  # noqa: E402
import validate_and_fill as vaf  # noqa: E402

TMPROOT = ROOT / "tests" / ".tmp" / "build_reference_test"
BR_SRC = ROOT / "scripts" / "build_reference.py"

# 真实库的 trust 相关列以前是后续 ALTER 出来的；现在 `init_db.SUBJECT_SCHEMA` 已包含它们
# （2026-10-12 修：`/api/questions` 查 `group_uid` 时老 fixture 缺列会 500）。
# 这里保留"缺哪列补哪列"的写法，**不能**无条件 ALTER（否则 duplicate column name）。
EXTRA_COLS = [("group_uid", "TEXT"), ("material_text", "TEXT"), ("trust_level", "TEXT"),
              ("exam_title", "TEXT")]


def fresh_dir(name: str) -> Path:
    d = TMPROOT / name
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True, exist_ok=True)
    return d


class Env:
    """临时项目根 + 把 br / vaf 的模块级常量重定向过去（monkeypatch 风格）。"""

    BR_PATCHED = ("ROOT", "DATA", "OUT")
    VAF_PATCHED = ("ROOT", "DATA", "REF_NAME")

    def __init__(self, name: str):
        self.root = fresh_dir(name)
        self.data = self.root / "data"
        self.data.mkdir(parents=True, exist_ok=True)
        self._saved: dict = {}

    def __enter__(self) -> "Env":
        self._saved["br"] = {k: getattr(br, k) for k in self.BR_PATCHED}
        self._saved["vaf"] = {k: getattr(vaf, k) for k in self.VAF_PATCHED}
        br.ROOT, br.DATA = self.root, self.data
        br.OUT = self.data / "generation_reference.json"
        vaf.ROOT, vaf.DATA = self.root, self.data
        vaf._REF_CACHE.clear()
        return self

    def __exit__(self, *exc) -> bool:
        for k, v in self._saved["br"].items():
            setattr(br, k, v)
        for k, v in self._saved["vaf"].items():
            setattr(vaf, k, v)
        vaf._REF_CACHE.clear()
        return False


def seed_in(env: "Env", subject: str, rows: list[dict]) -> Path:
    p = env.data / f"{subject}.sqlite"
    conn = sqlite3.connect(str(p))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(init_db.SUBJECT_SCHEMA)
    have = {r[1] for r in conn.execute("PRAGMA table_info(questions)")}
    for col, typ in EXTRA_COLS:
        if col not in have:          # 幂等：schema 里已有就不 ALTER（否则 duplicate column name）
            conn.execute(f"ALTER TABLE questions ADD COLUMN {col} {typ}")
    cols = ("question_uid", "subject", "question_type", "stem", "answer", "explanation", "options",
            "knowledge_point", "status", "source_type", "fact_source", "group_uid", "material_text",
            "trust_level", "exam_title", "version")
    for i, r in enumerate(rows):
        vals = {"question_uid": r.get("uid", f"uid-{subject}-{i}"), "subject": subject,
                "question_type": r.get("qtype", "grammar_fill"), "stem": r.get("stem", f"题干{i}"),
                "answer": r.get("answer", "答案"), "explanation": r.get("explanation", "解析"),
                "options": r.get("options", "[]"), "knowledge_point": r.get("kp", ""),
                "status": r.get("status", "approved"), "source_type": r.get("source_type", "real_exam"),
                "fact_source": r.get("fact_source", ""), "group_uid": r.get("group_uid", ""),
                "material_text": r.get("material", ""), "trust_level": r.get("trust", "official_exam"),
                "exam_title": r.get("exam", "湖北2025"), "version": 1}
        conn.execute(f"INSERT INTO questions({','.join(cols)}) VALUES({','.join('?' * len(cols))})",
                     tuple(vals[c] for c in cols))
    conn.commit()
    conn.close()
    return p


def samples_of(env: "Env", subject: str, k: int = 5) -> dict:
    """跑 build_subject → {qtype: entry}。"""
    debug: list[str] = []
    s = br.build_subject(subject, k, {}, debug)
    return s["by_type"]


def db_fingerprint(env: "Env") -> dict:
    out = {}
    for p in sorted(env.data.glob("*.sqlite")):
        out[p.name] = (p.stat().st_mtime_ns, p.stat().st_size,
                       hashlib.sha256(p.read_bytes()).hexdigest())
    return out


def run_main(env: "Env", k: int = 5) -> dict:
    """跑 main()（走完整落盘路径）→ 读回落盘的 JSON。"""
    argv = sys.argv
    sys.argv = ["build_reference.py", "--k", str(k), "--quiet"]
    try:
        assert br.main() == 0
    finally:
        sys.argv = argv
    return json.loads(br.OUT.read_text(encoding="utf-8-sig"))


# ============================================================== ① 取样优先级


def test_prefers_official_exam_and_never_ai_generated() -> None:
    with Env("tier") as env:
        rows = [dict(uid=f"o{i}", qtype="grammar_fill", stem=f"官方真题题干{i}", answer=f"真题答案{i}",
                     explanation=f"真题解析{i}", exam="湖北2025", trust="official_exam") for i in range(4)]
        rows += [dict(uid=f"t{i}", qtype="grammar_fill", stem=f"教材题干{i}", answer="教材答案",
                      explanation="教材解析", exam="某校真题", trust="textbook") for i in range(3)]
        rows += [dict(uid=f"a{i}", qtype="grammar_fill", stem=f"AI题干{i}", answer="AI答案",
                      explanation="AI解析", trust=None, source_type="generate",
                      fact_source="AI生成-未验证") for i in range(3)]
        rows += [dict(uid="r1", qtype="grammar_fill", stem="被拒真题题干", answer="x",
                      explanation="y", exam="湖北2025", trust="official_exam", status="rejected")]
        seed_in(env, "english", rows)

        t = samples_of(env, "english", k=5)["grammar_fill"]
        got = t["samples"]
        assert t["sample_trust"] == "official_exam", t["sample_trust"]
        assert all(x["trust"] == "official_exam" for x in got), [x["trust"] for x in got]
        assert all(x["stem"].startswith("官方真题题干") for x in got), [x["stem"] for x in got]
        assert all(x["exam"] == "湖北2025" for x in got), "样例必须带考试出处"
        assert t["excluded"]["ai_generated"] == 3, t["excluded"]
        assert t["excluded"]["rejected"] == 1, "被拒题必须排除"
        assert not any("被拒" in x["stem"] for x in got)
        assert t["count"] == 11, f"count 应是本题型总题数，实际 {t['count']}"


def test_falls_back_when_no_official_and_flags_no_explanation() -> None:
    with Env("tier_fallback") as env:
        rows = [dict(uid=f"t{i}", qtype="writing", stem=f"教材写作题干{i}", answer="范文",
                     explanation="", exam="某校真题", trust="textbook") for i in range(4)]
        rows += [dict(uid="p1", qtype="writing", stem="第三方题干", answer="a", explanation="e",
                      trust=None, source_type="fetch")]
        seed_in(env, "english", rows)
        t = samples_of(env, "english", k=5)["writing"]
        assert t["sample_trust"] == "textbook", t["sample_trust"]
        assert len(t["samples"]) == 4, len(t["samples"])
        assert "解析" in t["quality_note"], t["quality_note"]
        assert all(x["trust"] == "textbook" for x in t["samples"])


def test_no_usable_rows_yields_empty_samples() -> None:
    with Env("tier_empty") as env:
        seed_in(env, "english", [dict(uid="a1", qtype="cloze", stem="AI题", answer="a", explanation="e",
                                      trust=None, source_type="generate")])
        t = samples_of(env, "english", k=5)["cloze"]
        assert t["samples"] == [] and t["sample_trust"] == ""
        assert "无可用样例" in t["quality_note"], t["quality_note"]


# ============================================================== ② 整块题


def test_material_block_is_kept_whole() -> None:
    with Env("block") as env:
        passage = "Directions: read the passage.\n\nThe Dong Grand Choir is a unique musical tradition."
        rows = [dict(uid=f"g{i}", qtype="reading_fill", stem="", material=passage,
                     answer=f"ans{i}", explanation=f"解析{i}", group_uid="111-s0", exam="湖北2025",
                     trust="official_exam", kp="文化") for i in range(1, 6)]
        seed_in(env, "english", rows)
        t = samples_of(env, "english", k=5)["reading_fill"]
        assert len(t["samples"]) == 1, "同 group_uid 的 5 行必须合成 1 条整块题"
        s = t["samples"][0]
        assert s["kind"] == "material_block" and s["blanks_total"] == 5
        assert s["material"] == passage, "材料必须原样保留"
        assert [b["answer"] for b in s["blanks"]] == [f"ans{i}" for i in range(1, 6)], s["blanks"]
        assert all(b["explanation"] for b in s["blanks"]), "每个空的解析都要留下"
        assert s["stem_in_material"] is True, "空题干必须打标记，避免被学成『题干可以为空』"
        assert "material_note" in t and "整块" in t["material_note"]
        assert t["material_blocks"] == 1


def test_blocks_do_not_merge_complete_questions() -> None:
    """题干完整的题共用一个 group_uid（同一篇阅读的若干小题）时**不得**被并成一块。"""
    with Env("block_nomerge") as env:
        rows = [dict(uid=f"s{i}", qtype="single_choice", stem=f"完整题干{i}", answer=f"A{i}",
                     explanation="解析", group_uid="114-s0", exam="湖北2022") for i in range(4)]
        seed_in(env, "english", rows)
        t = samples_of(env, "english", k=5)["single_choice"]
        assert len(t["samples"]) == 4, len(t["samples"])
        assert all(s["kind"] == "single" for s in t["samples"])
        assert "material_note" not in t


# ============================================================== ③ 连词成句


def test_sentence_build_slash_format_untouched() -> None:
    with Env("slash") as env:
        stems = ["her homework / she / has completed", "the source of / is / Water / life"]
        seed_in(env, "english", [dict(uid=f"b{i}", qtype="sentence_build", stem=st, answer="A sentence.",
                                      explanation="按语序排列", exam="湖北2025") for i, st in enumerate(stems)])
        t = samples_of(env, "english", k=5)["sentence_build"]
        assert sorted(s["stem"] for s in t["samples"]) == sorted(stems), "斜杠格式必须零改写"
        assert "stem_format" in t and "斜杠" in t["stem_format"]


# ============================================================== ④ 确定性与条数


def test_deterministic_and_rotates_exams() -> None:
    with Env("determinism") as env:
        rows = []
        for exam in ("湖北2025", "湖北2024", "河北专升本英语17"):
            for i in range(4):
                rows.append(dict(uid=f"{exam}-{i}", qtype="grammar_fill", stem=f"{exam}题干{i}",
                                 answer="a", explanation="解析" * (i + 1), exam=exam))
        seed_in(env, "english", rows)
        a = [s["stem"] for s in samples_of(env, "english", k=3)["grammar_fill"]["samples"]]
        b = [s["stem"] for s in samples_of(env, "english", k=3)["grammar_fill"]["samples"]]
        assert a == b, f"同一份库必须给同样的样例：{a} vs {b}"
        assert len(a) == 3, a
        assert len({x.rsplit("题干", 1)[0] for x in a}) == 3, f"应跨 exam 轮转，实际 {a}"
        # 目标考区（湖北）优先：k=2 时两套湖北卷先出
        c = [s["stem"] for s in samples_of(env, "english", k=2)["grammar_fill"]["samples"]]
        assert all(x.startswith("湖北") for x in c), c


def test_main_writes_reference_and_is_read_only() -> None:
    with Env("readonly") as env:
        seed_in(env, "english", [dict(uid="o1", qtype="grammar_fill", stem="真题题干", answer="a",
                                      explanation="e", exam="湖北2025")])
        before = db_fingerprint(env)
        doc = run_main(env, k=3)
        after = db_fingerprint(env)
        assert before == after, "构建脚本绝不能改动题库文件"
        assert doc["built_by"] == "scripts/build_reference.py" and doc["built_at"]
        assert {"rules", "subjects", "knowledge_points", "syllabus", "data_issues"} <= set(doc)
        assert doc["subjects"]["english"]["by_type"]["grammar_fill"]["samples"], "样例不得为空"
        assert doc["rules"]["trust_priority"] == ["official_exam", "textbook", "third_party"]
        # 二次构建结果一致（可重复运行）
        assert json.dumps(run_main(env, k=3)["subjects"], ensure_ascii=False, sort_keys=True) == \
               json.dumps(doc["subjects"], ensure_ascii=False, sort_keys=True)


# ============================================================== ⑥ few_shot 集成


def test_few_shot_uses_reference_then_falls_back() -> None:
    with Env("few_shot_integration") as env:
        rows = [dict(uid=f"o{i}", qtype="grammar_fill", stem=f"官方真题题干{i}", answer="a",
                     explanation="e", exam="湖北2025", trust="official_exam") for i in range(3)]
        rows.append(dict(uid="p1", qtype="grammar_fill", stem="随机池题干", answer="b",
                         explanation="e2", trust=None, source_type="fetch"))
        seed_in(env, "english", rows)
        # ① 没有参考库 → 回退随机（老行为，键只有 3 个、不报错）
        assert vaf.load_reference() == {}
        assert vaf.reference_samples("english", "grammar_fill", 2) == []
        old = vaf.few_shot("english", "grammar_fill", k=2)
        assert len(old) == 2 and all(set(x) == {"stem", "answer", "explanation"} for x in old), old

        # ② 有参考库 → 取真题样例（带 exam / trust）
        run_main(env, k=3)
        got = vaf.few_shot("english", "grammar_fill", k=2)
        assert len(got) == 2, got
        assert all(x["stem"].startswith("官方真题题干") for x in got), got
        assert all(x["exam"] == "湖北2025" and x["trust"] == "official_exam" for x in got), got
        # 参考库里没有的题型 → 仍回退随机（不报错）
        assert vaf.reference_samples("english", "no_such_type", 2) == []


def test_thin_top_tier_mixing_is_flagged() -> None:
    """最高可信度不足 3 条时会混入更低可信度，**必须**在 quality_note 里如实标注。"""
    with Env("tier_thin") as env:
        rows = [dict(uid="o1", qtype="grammar_fill", stem="唯一真题题干", answer="a", explanation="e",
                     exam="湖北2025", trust="official_exam")]
        rows += [dict(uid=f"p{i}", qtype="grammar_fill", stem=f"第三方题干{i}", answer="b",
                      explanation="e2", trust=None, source_type="fetch") for i in range(2)]
        seed_in(env, "english", rows)
        t = samples_of(env, "english", k=5)["grammar_fill"]
        assert t["sample_trust"] == "official_exam", t["sample_trust"]
        assert t["samples"][0]["stem"] == "唯一真题题干", "真题必须排在混入样例之前"
        assert {x["trust"] for x in t["samples"]} == {"official_exam", "third_party"}
        assert "混入更低可信度" in t["quality_note"], t["quality_note"]


def test_prompt_labels_real_exam_examples() -> None:
    ex = [{"stem": "s", "answer": "a", "explanation": "e", "exam": "湖北2025", "trust": "official_exam"},
          {"stem": "s2", "answer": "a2", "explanation": "e2", "material": "PASSAGE", "trust": "official_exam",
           "blanks_total": 5, "blanks": [{"no": 1, "stem": "第1空", "answer": "x", "explanation": "y"}]}]
    p = vaf.build_gen_prompt("english", "grammar_fill", "语法填空", 5, [], "考纲", ex)
    assert "真题样例" in p and "official_exam" in p, p[:200]
    assert '"exam": "湖北2025"' in p.replace('\\"', '"') or '"exam"' in p
    assert "PASSAGE" in p and "不得留空 stem" in p, "材料型样例必须带材料并提醒写完整题干"
    # 非真题样例不得冒充真题
    p2 = vaf.build_gen_prompt("c_hbpu", "programming", "编程", 3, [], "教材",
                              [{"stem": "s", "answer": "a", "explanation": "e", "trust": "textbook"}])
    assert "真题样例" not in p2 and "教材" in p2


def test_compile() -> None:
    import py_compile

    py_compile.compile(str(BR_SRC), doraise=True)


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):  # pragma: no cover
            pass

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
    shutil.rmtree(TMPROOT, ignore_errors=True)
    print(f"{len(fns) - failed}/{len(fns)} passed")
    raise SystemExit(1 if failed else 0)
