#!/usr/bin/env python
"""uid 模块自检（零第三方依赖，直接运行：python tests/test_uid.py）"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from lib.uid import content_fingerprint, generate_uid, normalize_stem  # noqa: E402


def test_uid_deterministic() -> None:
    a = generate_uid("english", "https://a.com/x", "题目内容" * 30)
    b = generate_uid("english", "https://a.com/x", "题目内容" * 30)
    assert a == b, "同一输入必须得到同一 uid"
    assert len(a) == 16, f"uid 应为 16 位 hex，实际 {len(a)}"


def test_uid_differs_by_source() -> None:
    a = generate_uid("english", "https://a.com/x", "同一题干")
    b = generate_uid("english", "https://b.com/y", "同一题干")
    assert a != b, "源内 uid 含 source_url，不同源应不同（这正是需要二级指纹的原因）"


def test_uid_truncates_stem_at_50() -> None:
    s1 = "A" * 50 + "tail1"
    s2 = "A" * 50 + "tail2"
    assert generate_uid("c_wuhan", "u", s1) == generate_uid("c_wuhan", "u", s2), "仅前 50 字符参与哈希"


def test_fingerprint_matches_across_punctuation() -> None:
    a = content_fingerprint("english", "同一道题干！")
    b = content_fingerprint("english", "同一道题干!")
    assert a == b, "归一化后全角/半角标点差异应被抹平"


def test_fingerprint_differs_by_subject() -> None:
    assert content_fingerprint("english", "x") != content_fingerprint("c_hbpu", "x")


def test_normalize_stem() -> None:
    assert normalize_stem("Hello，World。") == "helloworld"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS {fn.__name__}")
        except AssertionError as exc:  # noqa: PERF203
            failed += 1
            print(f"  FAIL {fn.__name__}: {exc}")
    print(f"{len(fns) - failed}/{len(fns)} passed")
    raise SystemExit(1 if failed else 0)
