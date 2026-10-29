#!/usr/bin/env python
"""阶段 5b/8 · 数据库备份：一致快照 + 完整性校验 + 保留策略 + 日志轮转。

用法::

    python scripts/backup.py [--keep N] [--verify] [--list]

行为
----
**备份**：把 ``data/*.sqlite`` 做**一致性快照**到 ``data/backup/YYYYMMDD-HHMMSS/``。

* 🔴 **禁止 ``shutil.copy`` 正在被使用的库**。库处于 WAL 模式或有并发写入时，直接拷主库
  文件会得到：① 漏掉尚未 checkpoint 的 ``-wal`` 里已提交的数据；② 拷到写入一半的页面
  （撕裂页）。结果是"能打开但数据是脏的/缺的"，比没有备份更危险。
* ✅ 本脚本用 **``sqlite3.Connection.backup()``（SQLite 在线备份 API）**。选它而不是
  ``VACUUM INTO`` 的理由：
  1. ``backup()`` 就是 SQLite 为"热备份正在被使用的库"设计的接口：逐页复制，中途源库
     被写入会自动从头再来，**不会产生半页**；``VACUUM INTO`` 在全表扫描期间持读事务，
     遇到并发写更容易 ``SQLITE_BUSY`` 失败。
  2. 它走 b-tree 层读取，**自动包含已提交但尚未 checkpoint 的 WAL 内容**（已实测：
     源库保持连接、``-wal`` 里有未合并帧时，副本行数与源库一致）。
  3. 不需要重写整库（大库下省时省临时空间），也不会因"目标文件已存在"而失败
     （``VACUUM INTO`` 要求目标不存在）。
* 副本落盘后再把**副本**切成 ``journal_mode=DELETE``：备份应是**自包含单文件**，
  打开它时不再需要/不会生成 ``-wal`` ``-shm`` 边车文件（实测 WAL 头的副本一旦被打开
  就会在备份目录里生成 ``-shm``/``-wal``，污染归档目录，也让 ``--verify`` 变成"有写入"）。
  源库仍是 WAL，恢复后各脚本的 ``PRAGMA journal_mode=WAL`` 会自动切回。
* **校验**：备份完逐个打开副本跑 ``PRAGMA integrity_check``，必须返回 ``ok``；
  任何一个不是 ``ok``（或快照本身抛错）→ **整体失败、退出码非 0**，且**不执行保留策略清理**
  （坏快照不能挤掉好备份）。

**保留策略**：``data/backup/`` 下按目录名（即时间戳）排序，只保留最近 ``--keep``（默认 7）份。
⚠️ **防误删**：只有当条目**同时**满足下列条件才删 ——
① 是目录；② 名字严格匹配 ``^\\d{8}-\\d{6}$``；③ 父目录就是 ``data/backup`` 本身
（``resolve()`` 后仍在根目录下一层）；④ 不是符号链接/junction。
任何手工命名目录、文件、指向别处的链接都**不会**被删。``--keep`` 下限被夹到 1。

**日志轮转**：``logs/cron.log`` 超过 10 MB → 覆盖式重命名为 ``logs/cron.log.1``
（已存在则覆盖），再新建一个 0 字节的 ``cron.log``；``logs/cron_failures.log``
同样处理（可选：不存在就跳过）。

**只读模式**（不创建任何文件、不改动任何文件）：
``--list`` 列出已有备份（目录名 / 大小 / 库数量，最新在前）；``--verify`` 只校验最近一份。

输出
----
**stdout 只有一行 JSON**（便于被别的脚本 ``json.loads`` 消费）：:

    {"backup_dir":..., "files":[...], "bytes":N, "kept":N,
     "rotated_logs":[...], "integrity":{"english.sqlite":"ok",...}, "pruned":[...]}

人类可读提示与恢复流程一律写 **stderr**。退出码：0 成功 / 1 校验或备份失败 / 2 用法错误。

恢复流程（本脚本**不**实现自动恢复，必须人工按序执行）
------------------------------------------------------
    1. **先停 Flask** —— 它持有库文件句柄，Windows 上覆盖主库必报 ``WinError 32``（文件被占用）；
    2. **删掉 ``data/*.sqlite-wal`` 与 ``data/*.sqlite-shm``** —— 残留 WAL 会在下次打开时
       被重放，把刚恢复的库"追写"成旧数据 → 表现为**恢复成功了但数据是脏的**；
    3. **再**把备份目录里的 ``*.sqlite`` 覆盖回 ``data/``。
    建议恢复前先把当前 ``data/`` 复制一份留底。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
BACKUP_ROOT = DATA / "backup"
LOGS = ROOT / "logs"

TS_FORMAT = "%Y%m%d-%H%M%S"
TS_RE = re.compile(r"^\d{8}-\d{6}$")
DEFAULT_KEEP = 7
LOG_MAX_BYTES = 10 * 1024 * 1024
#: cron_failures.log 是"可选"日志：不存在就跳过，不算错误
LOG_NAMES = ("cron.log", "cron_failures.log")

USAGE = "用法: python scripts/backup.py [--keep N] [--verify] [--list]"

RECOVERY_STEPS = (
    "恢复必须按序执行：",
    "  1) 先停 Flask（它持库句柄，Windows 上覆盖主库会 WinError 32 文件被占用）；",
    "  2) 删掉 data/*.sqlite-wal 与 data/*.sqlite-shm"
    "（残留 WAL 会被重放，把刚恢复的库追写成旧数据 → 恢复'成功'但数据是脏的）；",
    "  3) 再把备份目录里的 *.sqlite 覆盖回 data/（恢复前先给当前 data/ 留一份底）。",
)


# --------------------------------------------------------------------- 输出


def note(msg: str) -> None:
    """人类可读提示走 stderr，保证 stdout 只有 JSON。"""
    sys.stderr.write(msg + "\n")


def emit(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def print_recovery_hint(backup_dir: Path | None = None) -> None:
    note("[backup] ---- 恢复流程（本脚本不自动恢复，请人工执行）----")
    for line in RECOVERY_STEPS:
        note("[backup] " + line)
    if backup_dir is not None:
        note(f"[backup] 本次备份目录：{backup_dir}")


# --------------------------------------------------------------------- 快照


def _open_source(path: Path) -> sqlite3.Connection:
    """打开源库：优先只读（绝不改动正在被使用的库），只读打不开再退回普通连接。"""
    uri = "file:" + quote(path.as_posix(), safe="/:") + "?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True, timeout=30)
    except sqlite3.Error:
        conn = None
    if conn is not None:
        try:
            conn.execute("PRAGMA busy_timeout=30000")
            conn.execute("SELECT count(*) FROM sqlite_master").fetchone()  # 真正触碰文件
            return conn
        except sqlite3.Error:
            conn.close()  # 例如库里有热日志需要恢复 → 只读打不开，退回读写连接
    conn = sqlite3.connect(str(path), timeout=30)
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def snapshot(src: Path, dest: Path) -> int:
    """用在线备份 API 把 src 一致性快照到 dest，返回副本字节数。

    ⚠️ 绝不用 shutil.copy：WAL / 并发写下会丢已提交数据或拷到撕裂页。
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()  # 同一秒内重复运行：覆盖上一份，避免 backup() 撞已有文件
    src_conn = _open_source(src)
    try:
        dst_conn = sqlite3.connect(str(dest), timeout=30)
        try:
            src_conn.backup(dst_conn)  # 逐页复制；源库途中被写会自动重来，绝不半页
            dst_conn.commit()
        finally:
            dst_conn.close()
    finally:
        src_conn.close()

    # 副本切成 rollback journal：备份应为自包含单文件，打开时不再生成 -wal/-shm。
    try:
        conn = sqlite3.connect(str(dest), timeout=30)
        try:
            conn.execute("PRAGMA journal_mode=DELETE")
        finally:
            conn.close()
    except sqlite3.Error as exc:  # 切不动不算致命：后面的 integrity_check 会给出结论
        note(f"[backup] 提示：{dest.name} 未能切回 DELETE journal（{exc}），仍按 WAL 边车文件归档")
    return dest.stat().st_size


def integrity_check(path: Path) -> str:
    """打开副本跑 PRAGMA integrity_check；正常返回字符串 'ok'，异常返回 'error: ...'。"""
    try:
        conn = sqlite3.connect(str(path), timeout=30)
        try:
            rows = conn.execute("PRAGMA integrity_check").fetchall()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        return f"error: {type(exc).__name__}: {exc}"
    text = "; ".join(str(r[0]) for r in rows) if rows else "(empty result)"
    return text


# --------------------------------------------------------------------- 保留策略


def _is_link(p: Path) -> bool:
    if p.is_symlink():
        return True
    is_junction = getattr(p, "is_junction", None)  # Python 3.12+
    if callable(is_junction):
        try:
            return bool(is_junction())
        except OSError:
            return True
    return False


def list_backups() -> list[Path]:
    """列出 backup 根目录下的时间戳子目录（名字升序 = 时间升序）。

    只认严格的时间戳目录名；符号链接/junction 一律忽略（防误删的入口过滤）。
    """
    if not BACKUP_ROOT.is_dir():
        return []
    try:
        root = BACKUP_ROOT.resolve()
    except OSError:
        return []
    found: list[Path] = []
    for p in BACKUP_ROOT.iterdir():
        if not TS_RE.match(p.name):  # 防误删①：名字必须是 YYYYMMDD-HHMMSS
            continue
        if _is_link(p):  # 防误删②：不跟进链接/junction
            continue
        if not p.is_dir():  # 防误删③：必须是目录（同名文件不碰）
            continue
        try:
            if p.resolve().parent != root:  # 防误删④：解析后仍在 backup 根目录下一层
                continue
        except OSError:
            continue
        found.append(p)
    return sorted(found, key=lambda x: x.name)


def prune_backups(keep: int) -> list[str]:
    """只保留最近 keep 份时间戳备份，返回被删除的目录名列表。"""
    if keep < 1:
        note(f"[backup] 提示：--keep {keep} 不安全，已夹到 1（至少留一份）")
        keep = 1
    backups = list_backups()
    if len(backups) <= keep:
        return []
    doomed = backups[: len(backups) - keep]

    root = BACKUP_ROOT.resolve()
    removed: list[str] = []
    for p in doomed:
        # 删除前二次确认：仍是 backup 根目录下、名字合法的时间戳目录
        try:
            if not TS_RE.match(p.name) or _is_link(p) or p.resolve().parent != root:
                note(f"[backup] 跳过可疑条目（不删）：{p}")
                continue
        except OSError as exc:
            note(f"[backup] 跳过无法解析的条目（不删）：{p}（{exc}）")
            continue
        try:
            shutil.rmtree(p)
            removed.append(p.name)
        except OSError as exc:
            note(f"[backup] 删除失败（保留）：{p.name}（{exc}）")
    return removed


# --------------------------------------------------------------------- 日志轮转


def rotate_logs() -> list[str]:
    """超过 10 MB 的日志 → 覆盖式重命名为 <name>.1，并新建空 <name>。"""
    rotated: list[str] = []
    for name in LOG_NAMES:
        p = LOGS / name
        try:
            if not p.is_file():
                continue  # cron_failures.log 可选：不存在就跳过
            size = p.stat().st_size
        except OSError as exc:
            note(f"[backup] 提示：无法读取日志 {p}（{exc}）")
            continue
        if size <= LOG_MAX_BYTES:
            continue
        target = p.with_name(p.name + ".1")
        try:
            os.replace(str(p), str(target))  # 覆盖式重命名（Windows 上 os.replace 可覆盖）
            p.write_bytes(b"")  # 重建空日志，保证 cron 追加写入不会失败
        except OSError as exc:
            note(f"[backup] 日志轮转失败 {name}（{exc}）")
            continue
        rotated.append(name)
        note(f"[backup] 日志轮转：{name}（{size} bytes > {LOG_MAX_BYTES}）→ {target.name}")
    return rotated


# --------------------------------------------------------------------- 三种模式


def run_backup(keep: int) -> int:
    dbs = sorted(p for p in DATA.glob("*.sqlite") if p.is_file())
    if not dbs:
        note(f"[backup] 错误：{DATA} 下没有 *.sqlite，无可备份")
        emit({
            "backup_dir": None, "files": [], "bytes": 0, "kept": len(list_backups()),
            "rotated_logs": [], "pruned": [], "integrity": {},
            "error": f"no source database under {DATA}",
        })
        return 2

    ts = datetime.now().strftime(TS_FORMAT)
    dest_dir = BACKUP_ROOT / ts
    if dest_dir.exists():
        note(f"[backup] 注意：{dest_dir.name} 已存在（同一秒内重复运行），覆盖其中的快照")
    dest_dir.mkdir(parents=True, exist_ok=True)

    integrity: dict[str, str] = {}
    files: list[str] = []
    total = 0
    for src in dbs:
        dest = dest_dir / src.name
        try:
            size = snapshot(src, dest)
        except Exception as exc:  # noqa: BLE001 - 单个库失败不阻断其余库的快照与报告
            integrity[src.name] = f"backup-failed: {type(exc).__name__}: {exc}"
            note(f"[backup] !! 快照失败 {src.name}：{integrity[src.name]}")
            continue
        files.append(str(dest))
        total += size
        integrity[src.name] = integrity_check(dest)
        note(f"[backup]   {src.name} → {dest.name}  {size} bytes  integrity={integrity[src.name]}")

    rotated = rotate_logs()
    bad = {k: v for k, v in integrity.items() if v != "ok"}

    if bad:
        note(f"[backup] 校验失败（{len(bad)}/{len(integrity)}）：{bad}")
        note("[backup] 本次**不执行**保留策略清理：坏快照不能挤掉好备份")
        print_recovery_hint(dest_dir)
        emit({
            "backup_dir": str(dest_dir), "files": files, "bytes": total,
            "kept": len(list_backups()), "rotated_logs": rotated, "pruned": [],
            "integrity": integrity, "error": "integrity_check failed",
        })
        return 1

    pruned = prune_backups(keep)
    kept = len(list_backups())
    note(f"[backup] 完成：{len(files)} 个库 / {total} bytes → {dest_dir}")
    note(f"[backup] 保留策略：现存 {kept} 份（--keep {keep}），本次删除 {len(pruned)} 份 {pruned}")
    if not rotated:
        note("[backup] 日志未达轮转阈值，未轮转")
    print_recovery_hint(dest_dir)
    emit({
        "backup_dir": str(dest_dir), "files": files, "bytes": total, "kept": kept,
        "rotated_logs": rotated, "pruned": pruned, "integrity": integrity,
    })
    return 0


def _dir_bytes(d: Path) -> int:
    total = 0
    for f in sorted(d.rglob("*")):
        try:
            if f.is_file():
                total += f.stat().st_size
        except OSError:
            continue
    return total


def run_list() -> int:
    """列出已有备份（只读：不创建、不修改任何文件）。"""
    backups = list_backups()
    rows = []
    for d in reversed(backups):  # 最新在前，便于人看
        dbs = sorted(f.name for f in d.glob("*.sqlite") if f.is_file())
        rows.append({"dir": d.name, "bytes": _dir_bytes(d), "databases": len(dbs), "files": dbs})
    emit({"backups": rows, "count": len(rows), "latest": rows[0]["dir"] if rows else None,
          "backup_root": str(BACKUP_ROOT)})
    note(f"[backup] --list：{len(rows)} 份备份（{BACKUP_ROOT}），未写入任何文件")
    return 0


def run_verify() -> int:
    """只校验最近一份备份（只读：不创建、不修改任何文件）。"""
    backups = list_backups()
    if not backups:
        note(f"[backup] --verify：{BACKUP_ROOT} 下没有备份目录")
        emit({"backup_dir": None, "files": [], "bytes": 0, "integrity": {}, "ok": False,
              "error": "no backup found"})
        return 1
    latest = backups[-1]
    dbs = sorted(f for f in latest.glob("*.sqlite") if f.is_file())
    integrity = {f.name: integrity_check(f) for f in dbs}
    ok = bool(integrity) and all(v == "ok" for v in integrity.values())
    total = 0
    for f in dbs:
        try:
            total += f.stat().st_size
        except OSError:
            pass
    bad = {k: v for k, v in integrity.items() if v != "ok"}
    note(f"[backup] --verify：{latest} → {'ok' if ok else 'FAILED'}"
         + (f"，问题：{bad}" if bad else f"（{len(integrity)} 个库全部 integrity_check=ok）"))
    if ok:
        print_recovery_hint(latest)
    emit({"backup_dir": str(latest), "files": [str(f) for f in dbs], "bytes": total,
          "integrity": integrity, "ok": ok})
    return 0 if ok else 1


# --------------------------------------------------------------------- 入口


def parse_args(argv: list[str]) -> tuple[int, str] | int:
    """返回 (keep, mode)，或直接返回一个退出码表示用法错误。"""
    keep = DEFAULT_KEEP
    mode = "backup"
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("-h", "--help"):
            print(USAGE)
            print("  --keep N   保留最近 N 份备份（默认 7）")
            print("  --list     列出已有备份（只读）")
            print("  --verify   只校验最近一份备份（只读）")
            return 0
        if a == "--keep":
            i += 1
            if i >= len(argv):
                note(f"[backup] 错误：--keep 缺少取值\n{USAGE}")
                return 2
            a = f"--keep={argv[i]}"
        if a.startswith("--keep="):
            raw = a.split("=", 1)[1]
            try:
                keep = int(raw)
            except ValueError:
                note(f"[backup] 错误：--keep 需要整数，收到 {raw!r}\n{USAGE}")
                return 2
        elif a == "--list":
            mode = "list" if mode == "backup" else "conflict"
        elif a == "--verify":
            mode = "verify" if mode == "backup" else "conflict"
        else:
            note(f"[backup] 错误：未知参数 {a!r}\n{USAGE}")
            return 2
        i += 1
    if mode == "conflict":
        note(f"[backup] 错误：--list 与 --verify 不能同时使用\n{USAGE}")
        return 2
    return keep, mode


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    parsed = parse_args(args)
    if isinstance(parsed, int):
        return parsed
    keep, mode = parsed
    if mode == "list":
        return run_list()
    if mode == "verify":
        return run_verify()
    return run_backup(keep)


if __name__ == "__main__":
    raise SystemExit(main())
