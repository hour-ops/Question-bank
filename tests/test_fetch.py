#!/usr/bin/env python
"""fetch.py 离线 smoke test —— **不联网**（纯函数 + 工作区临时 DB/日志 + dry-run 子进程）。

⚠️ 不使用 tempfile.TemporaryDirectory()：本机沙箱拒绝对系统临时目录做删除（WinError 5），
   因此临时文件统一放在工作区内的 tests/.tmp/ 下。

运行: python tests/test_fetch.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import fetch  # noqa: E402

PY = sys.executable
# ⚠️ tests/.tmp 是多个测试文件共享的目录；每个测试必须只用**自己的子目录**并只清自己，
#    否则并发跑测试时会互相删掉现场（子代理实测踩过）。
TMPROOT = ROOT / "tests" / ".tmp" / "test_fetch"


def fresh_dir(name: str) -> Path:
    """在工作区内创建干净的临时目录（可被沙箱删除）。"""
    d = TMPROOT / name
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True, exist_ok=True)
    return d


def cleanup(d: Path) -> None:
    shutil.rmtree(d, ignore_errors=True)


# --------------------------------------------------------------------- 纯函数


def test_dest_name_is_stable_and_short() -> None:
    a = fetch.dest_name("https://a.com/x.pdf", ".pdf")
    b = fetch.dest_name("https://a.com/x.pdf", ".pdf")
    assert a == b
    assert len(a) == 12 + len(".pdf"), f"应为 sha1[:12]+ext，实际 {a}"
    assert fetch.dest_name("https://a.com/中文 名.pdf", ".pdf") == fetch.dest_name("https://a.com/中文 名.pdf", ".pdf")


def test_dest_ext_prefers_content_type() -> None:
    assert fetch.dest_ext("https://a.com/x", "application/pdf") == ".pdf"
    assert fetch.dest_ext("https://a.com/x", "text/html; charset=utf-8") == ".html"
    assert fetch.dest_ext("https://a.com/x.docx", "") == ".docx"
    assert fetch.dest_ext("https://a.com/x", "") == ".html"


def test_domain_ok_whitelist_and_exclude() -> None:
    assert fetch.domain_ok("https://hbzsb.com/a", ["hbzsb.com"], [])
    assert fetch.domain_ok("https://www.hbzsb.com/a", ["hbzsb.com"], [])       # 子域允许
    assert not fetch.domain_ok("https://evil.com/a", ["hbzsb.com"], [])
    assert not fetch.domain_ok("https://renrendoc.com/a", ["renrendoc.com"], ["renrendoc.com"])  # 排除优先
    assert not fetch.domain_ok("not-a-url", ["hbzsb.com"], [])


def test_build_search_urls_expands_domain_and_keyword() -> None:
    urls = fetch.build_search_urls(["https://b.com/s?q=site:{domain}+{kw}"], ["湖北专升本", "真题"], ["d.com"])
    assert len(urls) == 2
    assert all("site:d.com" in u for u in urls)
    assert any("%E6%B9%96%E5%8C%97" in u for u in urls), "关键词应被 URL 编码"
    assert len(fetch.build_search_urls(["https://b.com/s?q={kw}"], ["x"], ["d.com"])) == 1


def test_failed_cooldown_window() -> None:
    """14 天内失败 → 冷却；30 天前失败 → 不再冷却。"""
    d = fresh_dir("failed_cooldown")
    try:
        log = d / "failed_sources.log"
        recent = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat(timespec="seconds")
        old = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat(timespec="seconds")
        log.write_text(
            json.dumps({"ts": recent, "subject": "english", "domain": "hot.com", "url": "https://hot.com/a", "reason": "captcha"}) + "\n"
            + json.dumps({"ts": old, "subject": "english", "domain": "cold.com", "url": "https://cold.com/b", "reason": "captcha"}) + "\n"
            + "这不是 JSON\n",
            encoding="utf-8",
        )
        original = fetch.FAILED_LOG
        fetch.FAILED_LOG = log
        try:
            failed = fetch.load_failed_domains()
            assert "hot.com" in failed, "3 天前的失败应仍在 14 天冷却窗口内"
            assert "cold.com" not in failed, "30 天前的失败应已出窗口"
        finally:
            fetch.FAILED_LOG = original
    finally:
        cleanup(d)


def test_low_freq_blocks_within_7_days() -> None:
    d = fresh_dir("low_freq")
    original = fetch.CACHE_DB
    fetch.CACHE_DB = d / "cache.sqlite"
    try:
        conn = fetch.db()
        fresh = datetime.now(timezone.utc).isoformat(timespec="seconds")
        stale = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat(timespec="seconds")
        for subj_domain, last, low in (("low.com", fresh, 1), ("due.com", stale, 1), ("normal.com", fresh, 0)):
            conn.execute(
                "INSERT INTO source_stats(subject,domain,fetched,hits,hit_rate,last_fetch_at,low_freq) VALUES(?,?,?,?,?,?,?)",
                ("english", subj_domain, 10, 1, 0.1, last, low),
            )
        conn.commit()
        assert fetch.low_freq_blocked(conn, "english", "low.com") is True, "低频源 + 1 天内抓过 → 应拦"
        assert fetch.low_freq_blocked(conn, "english", "due.com") is False, "低频源 + 8 天前 → 应放行"
        assert fetch.low_freq_blocked(conn, "english", "normal.com") is False, "非低频源不受周限"
        conn.close()
    finally:
        fetch.CACHE_DB = original
        cleanup(d)


def test_mark_fetched_and_source_stat() -> None:
    d = fresh_dir("mark_fetched")
    original = fetch.CACHE_DB
    fetch.CACHE_DB = d / "cache.sqlite"
    try:
        conn = fetch.db()
        url = "https://hbzsb.com/x"
        assert not fetch.already_fetched(conn, url)
        fetch.mark_fetched(conn, url, "english")
        assert fetch.already_fetched(conn, url)
        fetch.bump_source_stat(conn, "english", "hbzsb.com", fetched_delta=1)
        fetch.bump_source_stat(conn, "english", "hbzsb.com", fetched_delta=1)
        row = conn.execute("SELECT fetched FROM source_stats WHERE subject='english' AND domain='hbzsb.com'").fetchone()
        assert row and row[0] == 2, f"fetched 应累加到 2，实际 {row}"
        conn.close()
    finally:
        fetch.CACHE_DB = original
        cleanup(d)


def test_log_failure_shape() -> None:
    d = fresh_dir("log_failure")
    original = fetch.FAILED_LOG
    fetch.FAILED_LOG = d / "failed_sources.log"
    try:
        fetch.log_failure("aca_llm", "edu.aliyun.com", "https://edu.aliyun.com/x", "需登录")
        rec = json.loads(fetch.FAILED_LOG.read_text(encoding="utf-8").strip())
        assert rec["domain"] == "edu.aliyun.com" and rec["subject"] == "aca_llm" and rec["reason"] == "需登录"
        assert "ts" in rec
    finally:
        fetch.FAILED_LOG = original
        cleanup(d)


# --------------------------------------------------------------------- 端到端（不联网）


def test_dry_run_subprocess_no_network() -> None:
    """dry-run 必须零网络请求且退出码 0。"""
    proc = subprocess.run(
        [PY, str(ROOT / "scripts" / "fetch.py"), "--subject", "english", "--dry-run"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120, cwd=str(ROOT),
    )
    assert proc.returncode == 0, f"dry-run 退出码 {proc.returncode}\n{proc.stderr[-800:]}"
    assert "[dry-run]" in proc.stdout
    assert '"dry_run": true' in proc.stdout
    assert "将请求搜索页" in proc.stdout


def test_compile() -> None:
    import py_compile

    py_compile.compile(str(ROOT / "scripts" / "fetch.py"), doraise=True)


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
    shutil.rmtree(TMPROOT, ignore_errors=True)
    print(f"{len(fns) - failed}/{len(fns)} passed")
    raise SystemExit(1 if failed else 0)
