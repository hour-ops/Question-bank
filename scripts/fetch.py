#!/usr/bin/env python
"""阶段 4a · 抓取脚本（唯一"下载到 inbox"入口；**不写 questions 表**）。

用法:
    python scripts/fetch.py --subject english|c_wuhan|c_hbpu|aca_llm|all [--dry-run] [--max-per-subject N]

设计要点（复核修正，见 .tools/题库项目-决策记录.md 第 6 节第 7 条）:
  1. 只请求**白名单域名**；`excluded_domains` 一律不抓。
  2. **串行 + 间隔 >=2s + 遵守 robots.txt**（本机共享代理，不节流必被风控）。
  3. `cache.sqlite.fetched_urls` 去重；`source_stats` 记抓取量（`hits`/`hit_rate` 由 parse_inbox 回写）。
  4. 失败源写 `logs/failed_sources.log`（JSONL，按 **domain**），**14 天内不重试**。
  5. 命中率 <0.2 的源标 `low_freq=1`，**每周只抓 1 次**。
  6. 连通性探测失败 → 回退**显式代理** `192.168.141.1:7897`（requests 不读 WinINET）。
  7. 文件名 = `sha1(url)[:12] + 原扩展名`（避免中文/非法字符/重名）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
import urllib.parse
import urllib.robotparser
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import chardet
    import requests
    from bs4 import BeautifulSoup
except ImportError as exc:  # pragma: no cover
    print(f"缺少依赖: {exc}\n请用 64 位捆绑 Python 安装: pip install requests beautifulsoup4 chardet")
    raise SystemExit(2)

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "source_whitelist.json"
INBOX = ROOT / "inbox"
CACHE_DB = ROOT / "data" / "cache.sqlite"
FAILED_LOG = ROOT / "logs" / "failed_sources.log"

SUBJECTS = ["english", "c_wuhan", "c_hbpu", "aca_llm"]
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36"
DEFAULT_PROXY = "http://192.168.141.1:7897"
THROTTLE_SECONDS = 2.0          # 串行间隔下限
FAILED_COOLDOWN_DAYS = 14       # 失败源冷却
LOW_FREQ_DAYS = 7               # 低频源重抓间隔
LOW_FREQ_THRESHOLD = 0.2        # 命中率阈值
CONNECT_TIMEOUT = 8
READ_TIMEOUT = 20

BINARY_EXT = {
    "pdf": ".pdf", "doc": ".doc", "docx": ".docx", "xls": ".xls", "xlsx": ".xlsx",
    "ppt": ".ppt", "pptx": ".pptx", "png": ".png", "jpg": ".jpg", "jpeg": ".jpeg",
    "gif": ".gif", "webp": ".webp", "zip": ".zip", "md": ".md", "txt": ".txt",
}
CT_EXT = {
    "application/pdf": ".pdf",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.ms-excel": ".xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif", "image/webp": ".webp",
    "text/markdown": ".md", "text/plain": ".txt",
    "application/zip": ".zip",
}

# --------------------------------------------------------------------------- 工具


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime | None = None) -> str:
    return (dt or now()).isoformat(timespec="seconds")


def domain_of(url: str) -> str:
    return (urllib.parse.urlparse(url).hostname or "").lower()


def dest_ext(url: str, content_type: str) -> str:
    ct = (content_type or "").split(";")[0].strip().lower()
    if ct in CT_EXT:
        return CT_EXT[ct]
    path = urllib.parse.urlparse(url).path
    suffix = Path(path).suffix.lower()
    if suffix and suffix.lstrip(".") in BINARY_EXT:
        return suffix
    if ct.startswith("text/html"):
        return ".html"
    return suffix or ".html"


def dest_name(url: str, ext: str) -> str:
    """sha1(url)[:12] + 扩展名 —— 避免中文/非法字符与重名。"""
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:12] + ext


def domain_ok(url: str, domains: list[str], excluded: list[str]) -> bool:
    d = domain_of(url)
    if not d:
        return False
    if any(d == e or d.endswith("." + e) for e in excluded):
        return False
    return any(d == a or d.endswith("." + a) for a in domains)


def build_search_urls(templates: list[str], keywords: list[str], domains: list[str]) -> list[str]:
    """把 search_templates × keywords × domains 展开成待请求的搜索页 URL。"""
    out: list[str] = []
    for tpl in templates:
        for kw in keywords:
            if "{domain}" in tpl:
                for d in domains:
                    out.append(tpl.replace("{domain}", d).replace("{kw}", urllib.parse.quote(kw)))
            else:
                out.append(tpl.replace("{kw}", urllib.parse.quote(kw)))
    return out


# --------------------------------------------------------------------------- 数据库


def db() -> sqlite3.Connection:
    CACHE_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(CACHE_DB))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS fetched_urls (url TEXT PRIMARY KEY, fetched_at TEXT, source TEXT);
        CREATE TABLE IF NOT EXISTS source_stats (
          subject TEXT, domain TEXT, fetched INTEGER DEFAULT 0, hits INTEGER DEFAULT 0,
          hit_rate REAL DEFAULT 0, last_fetch_at TEXT, low_freq INTEGER DEFAULT 0,
          PRIMARY KEY (subject, domain));
        """
    )
    conn.commit()
    return conn


def already_fetched(conn: sqlite3.Connection, url: str) -> bool:
    return conn.execute("SELECT 1 FROM fetched_urls WHERE url=?", (url,)).fetchone() is not None


def mark_fetched(conn: sqlite3.Connection, url: str, source: str) -> None:
    conn.execute("INSERT OR REPLACE INTO fetched_urls(url, fetched_at, source) VALUES(?,?,?)", (url, iso(), source))
    conn.commit()


def bump_source_stat(conn: sqlite3.Connection, subject: str, domain: str, *, fetched_delta: int = 0) -> None:
    conn.execute(
        """INSERT INTO source_stats(subject, domain, fetched, hits, hit_rate, last_fetch_at, low_freq)
           VALUES(?,?,?,0,0,?,0)
           ON CONFLICT(subject, domain) DO UPDATE SET
             fetched = fetched + ?,
             last_fetch_at = excluded.last_fetch_at""",
        (subject, domain, fetched_delta, iso(), fetched_delta),
    )
    conn.commit()


def load_failed_domains(days: int = FAILED_COOLDOWN_DAYS) -> dict[str, str]:
    """读 failed_sources.log，返回 {domain: 最近失败时间}（窗口内）。"""
    cutoff = now() - timedelta(days=days)
    out: dict[str, str] = {}
    if not FAILED_LOG.exists():
        return out
    for line in FAILED_LOG.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            ts = datetime.fromisoformat(rec["ts"])
        except Exception:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if ts >= cutoff:
            d = rec.get("domain") or domain_of(rec.get("url", ""))
            if d:
                prev = out.get(d)
                out[d] = max(prev, rec["ts"]) if prev else rec["ts"]
    return out


def log_failure(subject: str, domain: str, url: str, reason: str) -> None:
    FAILED_LOG.parent.mkdir(parents=True, exist_ok=True)
    rec = {"ts": iso(), "subject": subject, "domain": domain, "url": url, "reason": reason[:300]}
    with FAILED_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def low_freq_blocked(conn: sqlite3.Connection, subject: str, domain: str) -> bool:
    row = conn.execute(
        "SELECT low_freq, last_fetch_at FROM source_stats WHERE subject=? AND domain=?", (subject, domain)
    ).fetchone()
    if not row or not row[0]:
        return False
    last = row[1]
    if not last:
        return False
    try:
        last_dt = datetime.fromisoformat(last)
    except Exception:
        return False
    if last_dt.tzinfo is None:
        last_dt = last_dt.replace(tzinfo=timezone.utc)
    return (now() - last_dt) < timedelta(days=LOW_FREQ_DAYS)


# --------------------------------------------------------------------------- 会话


class Fetcher:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"})
        self.proxy_mode = False
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self._last_request = 0.0

    # --- 连通性：先直连，失败则显式走代理 ---
    def probe(self) -> bool:
        for use_proxy in (False, True):
            proxies = {"http": DEFAULT_PROXY, "https": DEFAULT_PROXY} if use_proxy else None
            try:
                r = self.session.get("https://www.bing.com/", timeout=(CONNECT_TIMEOUT, READ_TIMEOUT), proxies=proxies)
                if r.status_code < 500:
                    self.proxy_mode = use_proxy
                    if use_proxy:
                        self.session.proxies = {"http": DEFAULT_PROXY, "https": DEFAULT_PROXY}
                    print(f"[net] 连通性 OK（{'显式代理 ' + DEFAULT_PROXY if use_proxy else '直连'}）")
                    return True
            except Exception as exc:  # noqa: BLE001
                print(f"[net] {'代理' if use_proxy else '直连'}失败: {exc}")
        print("[net] 连通性探测全部失败 —— 请检查代理设置")
        return False

    def _throttle(self) -> None:
        delta = time.time() - self._last_request
        if delta < THROTTLE_SECONDS:
            time.sleep(THROTTLE_SECONDS - delta)
        self._last_request = time.time()

    def robots_allowed(self, url: str) -> bool:
        d = domain_of(url)
        if d not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            rp.set_url(f"{urllib.parse.urlparse(url).scheme}://{d}/robots.txt")
            try:
                self._throttle()
                r = self.session.get(rp.url, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
                if r.status_code == 200:
                    rp.parse(r.text.splitlines())
                else:
                    rp = None  # 无 robots.txt → 视为允许
            except Exception:  # noqa: BLE001
                rp = None
            self._robots[d] = rp
        rp = self._robots[d]
        if rp is None:
            return True
        try:
            return rp.can_fetch(UA, url)
        except Exception:  # noqa: BLE001
            return True

    def get(self, url: str):
        self._throttle()
        return self.session.get(url, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT), allow_redirects=True)

    def discover(self, subject_cfg: dict) -> list[str]:
        """请求搜索页 → 抽取白名单域名内的链接。搜索页失败不致命。"""
        domains = subject_cfg.get("domains", [])
        excluded = subject_cfg.get("_excluded", [])
        found: list[str] = []
        for surl in build_search_urls(subject_cfg.get("search_templates", []), subject_cfg.get("keywords", []), domains):
            try:
                r = self.get(surl)
            except Exception as exc:  # noqa: BLE001
                print(f"  [search-fail] {surl} :: {exc}")
                continue
            if r.status_code != 200:
                print(f"  [search-{r.status_code}] {surl}")
                continue
            if "验证" in r.text[:4000] or "captcha" in r.text[:4000].lower():
                print(f"  [search-captcha] {surl}")
                log_failure(subject_cfg["_subject"], domain_of(surl), surl, "search-captcha")
                continue
            soup = BeautifulSoup(r.text, "lxml")
            for a in soup.find_all("a", href=True):
                href = urllib.parse.urljoin(surl, a["href"])
                if domain_ok(href, domains, excluded):
                    found.append(href.split("#")[0])
            print(f"  [search-ok] {surl} → 累计候选 {len(set(found))}")
        # 保序去重
        seen, out = set(), []
        for u in found:
            if u not in seen:
                seen.add(u)
                out.append(u)
        return out


# --------------------------------------------------------------------------- 主流程


def detect_reason(resp) -> str | None:
    if resp.status_code in (401, 403):
        return f"http-{resp.status_code}-需登录或被拒"
    if resp.status_code == 429:
        return "http-429-限流"
    head = resp.text[:4000].lower()
    for kw, reason in (("captcha", "captcha"), ("验证码", "验证码"), ("滑块", "滑块"), ("安全验证", "安全验证"),
                       ("登录后查看", "需登录"), ("请先登录", "需登录")):
        if kw in head:
            return reason
    return None


def run(subject: str, dry_run: bool, max_per_subject: int, urls_file: str | None = None) -> dict:
    cfg_all = json.loads(CONFIG.read_text(encoding="utf-8"))
    excluded = cfg_all.get("excluded_domains", [])
    subjects = SUBJECTS if subject == "all" else [subject]
    conn = db()
    failed = load_failed_domains()
    throttle_note = f"{THROTTLE_SECONDS}s/请求"
    stats = {"subject": subject, "dry_run": dry_run, "urls": 0, "files": 0, "failed": 0, "skipped": 0, "per_subject": {}}

    if dry_run:
        print(f"[dry-run] 不发起任何下载；节流 {throttle_note}；失败源冷却 {FAILED_COOLDOWN_DAYS} 天")
        for subj in subjects:
            scfg = cfg_all["subjects"].get(subj)
            if not scfg:
                print(f"  [skip] 配置里没有科目 {subj}")
                continue
            planned = build_search_urls(scfg.get("search_templates", []), scfg.get("keywords", []), scfg.get("domains", []))
            cached = conn.execute("SELECT count(*) FROM fetched_urls").fetchone()[0]
            cool = [d for d in scfg.get("domains", []) if d in failed]
            print(f"\n[{subj}]")
            print(f"  白名单域名 : {', '.join(scfg.get('domains', []))}")
            print(f"  keywords   : {len(scfg.get('keywords', []))} 个")
            print(f"  将请求搜索页: {len(planned)} 个")
            for u in planned[:6]:
                print(f"    - {u}")
            if len(planned) > 6:
                print(f"    … 其余 {len(planned) - 6} 个")
            print(f"  预估入库文件数: 上限 {max_per_subject}（--max-per-subject）")
            print(f"  全局已缓存跳过: {cached} 条 fetch 记录")
            print(f"  冷却中域名  : {cool or '无'}")
            stats["per_subject"][subj] = {"planned_search": len(planned), "cooldown_domains": cool,
                                          "max_files": max_per_subject}
        conn.close()
        return stats

    fetcher = Fetcher()
    if not fetcher.probe():
        stats["blocker"] = "network"
        conn.close()
        return stats

    for subj in subjects:
        scfg = cfg_all["subjects"].get(subj)
        if not scfg:
            print(f"[skip] 配置里没有科目 {subj}")
            continue
        subj_stats = {"candidates": 0, "downloaded": 0, "failed": 0, "skipped": 0}
        print(f"\n=== [{subj}] 开始 ===")
        scfg["_subject"] = subj  # type: ignore[index]
        scfg["_excluded"] = excluded  # type: ignore[index]

        if urls_file:
            raw = Path(urls_file).read_text(encoding="utf-8").splitlines()
            candidates = [u.strip() for u in raw if u.strip() and not u.strip().startswith("#")]
            candidates = [u for u in candidates if domain_ok(u, scfg.get("domains", []), excluded)]
            print(f"  从清单 {urls_file} 读入候选 URL: {len(candidates)}")
        else:
            candidates = fetcher.discover(scfg)
        print(f"  候选 URL: {len(candidates)}")

        for url in candidates:
            if subj_stats["downloaded"] >= max_per_subject:
                print(f"  达到上限 {max_per_subject}，停止本批")
                break
            d = domain_of(url)
            subj_stats["candidates"] += 1

            if already_fetched(conn, url):
                subj_stats["skipped"] += 1
                continue
            if d in failed:
                subj_stats["skipped"] += 1
                continue
            if low_freq_blocked(conn, subj, d):
                subj_stats["skipped"] += 1
                print(f"  [low-freq-skip] {d}（命中率<{LOW_FREQ_THRESHOLD}，{LOW_FREQ_DAYS} 天内只抓一次）")
                continue
            if not fetcher.robots_allowed(url):
                subj_stats["skipped"] += 1
                print(f"  [robots-skip] {url}")
                continue

            try:
                resp = fetcher.get(url)
            except Exception as exc:  # noqa: BLE001
                subj_stats["failed"] += 1
                log_failure(subj, d, url, f"exception: {exc}")
                mark_fetched(conn, url, subj)
                print(f"  [err] {url} :: {exc}")
                continue

            reason = detect_reason(resp)
            if reason:
                subj_stats["failed"] += 1
                log_failure(subj, d, url, reason)
                mark_fetched(conn, url, subj)
                print(f"  [blocked:{reason}] {url}")
                continue

            if resp.status_code != 200:
                subj_stats["failed"] += 1
                log_failure(subj, d, url, f"http-{resp.status_code}")
                mark_fetched(conn, url, subj)
                continue

            ext = dest_ext(url, resp.headers.get("Content-Type", ""))
            outdir = INBOX / subj
            outdir.mkdir(parents=True, exist_ok=True)
            out = outdir / dest_name(url, ext)
            if ext in (".html", ".md", ".txt"):
                enc = chardet.detect(resp.content[:20000]).get("encoding") or "utf-8"
                try:
                    text = resp.content.decode(enc, errors="replace")
                except LookupError:
                    text = resp.content.decode("utf-8", errors="replace")
                out.write_text(text, encoding="utf-8")
            else:
                out.write_bytes(resp.content)

            mark_fetched(conn, url, subj)
            bump_source_stat(conn, subj, d, fetched_delta=1)
            subj_stats["downloaded"] += 1
            stats["files"] += 1
            print(f"  [ok] {out.name} ← {url}")

        stats["failed"] += subj_stats["failed"]
        stats["skipped"] += subj_stats["skipped"]
        stats["per_subject"][subj] = subj_stats

    stats["urls"] = sum(v["candidates"] for v in stats["per_subject"].values() if isinstance(v, dict) and "candidates" in v)
    conn.close()
    return stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="抓取白名单站点的题目素材到 inbox/（不写 questions 表）")
    ap.add_argument("--subject", required=True, choices=SUBJECTS + ["all"])
    ap.add_argument("--dry-run", action="store_true", help="只打印将请求的 URL 与预估文件数，不实际下载")
    ap.add_argument("--max-per-subject", type=int, default=50, help="每科目最多下载文件数（默认 50）")
    ap.add_argument("--urls-file", default=None,
                    help="从清单文件按行读取待下载 URL（浏览器发现后使用；# 开头为注释）")
    args = ap.parse_args(argv)

    t0 = time.time()
    stats = run(args.subject, args.dry_run, args.max_per_subject, args.urls_file)
    stats["elapsed_s"] = round(time.time() - t0, 1)
    print("\n=== 汇总 ===")
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    if stats.get("blocker") == "network":
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
