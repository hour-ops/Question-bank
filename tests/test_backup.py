#!/usr/bin/env python
"""backup.py 离线测试 —— **不联网**，全部在 tests/.tmp/backup/ 下造临时项目树。

覆盖：
  ① 备份成功：副本可打开、PRAGMA integrity_check=ok、**行数与源库一致**
     （源库保持 WAL 连接、-wal 里有未 checkpoint 的帧 —— 这正是 shutil.copy 会出错、
      在线备份 API 必须正确的场景）
  ② 保留策略：>=9 份时只保留最近 --keep 份，且删的是最旧的；非时间戳目录/同名文件不删
  ③ 日志轮转：>10MB 的 cron.log / cron_failures.log → 覆盖式改名 .1 + 新建空日志
  ④ --list / --verify 只读：文件清单与目录/文件 mtime 完全不变（含"没有备份时"的空态）
  ⑤ 快照的表结构与逐行数据完全一致
  ⑥ --verify 能发现被损坏的备份（退出码非 0）
  ⑦ 真实命令行（复制到临时项目树后跑 __main__）

⚠️ 临时目录只用 tests/.tmp/backup/ 下**自己的子目录**：tests/.tmp 是多个测试文件共享的，
   整目录清空会删掉别的测试的现场。
⚠️ 不用 tempfile.TemporaryDirectory()：本机沙箱拒绝对系统临时目录做删除（WinError 5）。

运行: python tests/test_backup.py
"""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import backup  # noqa: E402

PY = sys.executable
TMPROOT = ROOT / "tests" / ".tmp" / "backup"


# --------------------------------------------------------------------- 工具


def fresh_env(name: str) -> tuple[Path, Path, Path]:
    """造一个干净的最小项目树 <TMPROOT>/<name>/{data,logs}，返回 (root, data, logs)。"""
    root = TMPROOT / name
    shutil.rmtree(root, ignore_errors=True)
    data = root / "data"
    logs = root / "logs"
    data.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)
    return root, data, logs


def cleanup(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


@contextlib.contextmanager
def patched(root: Path):
    """把 backup.py 的三个路径常量指到临时项目树，退出时还原。"""
    saved = (backup.DATA, backup.BACKUP_ROOT, backup.LOGS)
    backup.DATA = root / "data"
    backup.BACKUP_ROOT = backup.DATA / "backup"
    backup.LOGS = root / "logs"
    try:
        yield backup.DATA, backup.BACKUP_ROOT, backup.LOGS
    finally:
        backup.DATA, backup.BACKUP_ROOT, backup.LOGS = saved


def make_db(path: Path, rows: int, table: str = "items", keep_open: bool = False):
    """建一个 WAL 模式、有数据的库。

    keep_open=True 时**不关闭**连接并返回它：这样提交的数据停在 -wal 里没有 checkpoint，
    模拟"Flask 正在使用中的库"。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(f"CREATE TABLE {table}(id INTEGER PRIMARY KEY, name TEXT, score REAL)")
    conn.execute(f"CREATE INDEX idx_{table}_name ON {table}(name)")
    conn.executemany(
        f"INSERT INTO {table}(name, score) VALUES(?,?)",
        [(f"题目-{i}", i * 1.5) for i in range(rows)],
    )
    conn.commit()
    if keep_open:
        return conn
    conn.close()
    return None


def rows_of(path: Path, table: str = "items") -> list[tuple]:
    conn = sqlite3.connect(str(path))
    try:
        return conn.execute(f"SELECT id, name, score FROM {table} ORDER BY id").fetchall()
    finally:
        conn.close()


def schema_of(path: Path) -> list[tuple]:
    conn = sqlite3.connect(str(path))
    try:
        return conn.execute(
            "SELECT type,name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
        ).fetchall()
    finally:
        conn.close()


def run_cli(*argv) -> tuple[int, dict, str]:
    """进程内跑 main()，捕获 stdout(JSON) 与 stderr，返回 (退出码, payload, stderr)。"""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = backup.main(list(argv))
    text = out.getvalue().strip()
    payload = json.loads(text) if text else {}
    return code, payload, err.getvalue()


def tree_snapshot(root: Path) -> list[tuple]:
    """(相对路径, 是否目录, 字节数, mtime_ns) —— 用于断言"没有改动任何文件"。"""
    items = []
    for p in sorted(root.rglob("*")):
        st = p.stat()
        items.append((str(p.relative_to(root)), p.is_dir(), 0 if p.is_dir() else st.st_size, st.st_mtime_ns))
    return items


# --------------------------------------------------------------------- ① 一致快照


def test_backup_consistent_snapshot_with_pending_wal() -> None:
    root, data, logs = fresh_env("snapshot_wal")
    try:
        with patched(root):
            w1 = make_db(data / "english.sqlite", 200, keep_open=True)
            w2 = make_db(data / "attempts.sqlite", 7, keep_open=True)
            try:
                wal = data / "english.sqlite-wal"
                assert wal.exists() and wal.stat().st_size > 0, "前置条件失败：-wal 里应有未 checkpoint 的帧"

                code, payload, err = run_cli()
                assert code == 0, f"备份应成功，实际退出码 {code}\n{err}"
                assert payload["integrity"] == {"english.sqlite": "ok", "attempts.sqlite": "ok"}
                assert len(payload["files"]) == 2, f"应有 2 个快照，实际 {payload['files']}"
                assert payload["bytes"] > 0

                bdir = Path(payload["backup_dir"])
                assert backup.TS_RE.match(bdir.name), f"备份目录名应为 YYYYMMDD-HHMMSS，实际 {bdir.name}"
                for src in sorted(p for p in data.glob("*.sqlite") if p.is_file()):
                    dst = bdir / src.name
                    assert dst.is_file(), f"缺少副本 {dst}"
                    assert backup.integrity_check(dst) == "ok", f"{src.name} 副本 integrity_check 不是 ok"
                    assert rows_of(dst) == rows_of(src), f"{src.name} 副本行数与源库不一致"
                # 副本必须是自包含单文件：不该在备份目录里留下 -wal/-shm 边车
                assert not list(bdir.glob("*.sqlite-wal")), "备份目录里不该有 -wal"
                assert not list(bdir.glob("*.sqlite-shm")), "备份目录里不该有 -shm"
                # 源库仍原封不动
                assert rows_of(data / "english.sqlite") == rows_of(bdir / "english.sqlite")
            finally:
                if w1 is not None:
                    w1.close()
                if w2 is not None:
                    w2.close()
    finally:
        cleanup(root)


# --------------------------------------------------------------------- ② 保留策略


def test_retention_keeps_newest_and_spares_foreign_entries() -> None:
    root, data, logs = fresh_env("retention")
    try:
        with patched(root):
            make_db(data / "english.sqlite", 3)
            broot = backup.BACKUP_ROOT
            broot.mkdir(parents=True, exist_ok=True)

            now = datetime.now()
            fabricated = []
            for k in range(9, 0, -1):  # 9 份"旧备份"：9 天前 … 1 天前
                name = (now - timedelta(days=k)).strftime(backup.TS_FORMAT)
                d = broot / name
                d.mkdir(parents=True, exist_ok=True)
                (d / "english.sqlite").write_bytes(b"old")
                fabricated.append(name)

            manual = broot / "manual-keepme"  # 非时间戳目录 → 绝不许删
            manual.mkdir()
            (manual / "note.txt").write_text("手工目录", encoding="utf-8")
            fake_file = broot / "20000101-000000"  # 时间戳样式的**文件** → 绝不许删
            fake_file.write_bytes(b"i am a file, not a dir")
            stray = broot / "readme.txt"
            stray.write_text("x", encoding="utf-8")

            code, payload, err = run_cli("--keep", "7")
            assert code == 0, f"退出码 {code}\n{err}"

            dirs = [p.name for p in backup.list_backups()]
            assert len(dirs) == 7, f"--keep 7 后应剩 7 份，实际 {len(dirs)}：{dirs}"
            new_name = Path(payload["backup_dir"]).name
            assert new_name in dirs, "本次新建的最新一份必须保留"
            assert payload["kept"] == 7, f"kept 应为 7，实际 {payload['kept']}"

            deleted = sorted(set(fabricated) - set(dirs))
            assert deleted == sorted(fabricated[:3]), f"应删最旧的 3 份 {fabricated[:3]}，实际删了 {deleted}"
            assert sorted(payload["pruned"]) == sorted(fabricated[:3])

            # 防误删
            assert manual.is_dir() and (manual / "note.txt").exists(), "非时间戳目录被误删！"
            assert fake_file.is_file(), "时间戳同名的文件被误删！"
            assert stray.is_file(), "普通文件被误删！"
            # 保留的就是按名字排序最新的 7 份
            assert dirs == sorted(dirs), "list_backups 应按名字升序"
            assert dirs[-1] == new_name
    finally:
        cleanup(root)


# --------------------------------------------------------------------- ③ 日志轮转


def test_log_rotation_over_10mb() -> None:
    root, data, logs = fresh_env("log_rotation")
    try:
        with patched(root):
            make_db(data / "english.sqlite", 2)
            (logs / "cron.log").write_bytes(b"x" * (backup.LOG_MAX_BYTES + 1))
            (logs / "cron.log.1").write_bytes(b"STALE")  # 已存在 → 必须被覆盖
            (logs / "cron_failures.log").write_bytes(b"y" * (backup.LOG_MAX_BYTES + 5))
            outsider = logs / "failed_sources.log"  # 不在轮转名单 → 不动
            outsider.write_bytes(b"z" * (backup.LOG_MAX_BYTES + 9))

            code, payload, err = run_cli()
            assert code == 0, f"退出码 {code}\n{err}"
            assert sorted(payload["rotated_logs"]) == ["cron.log", "cron_failures.log"]

            assert (logs / "cron.log").is_file(), "应新建空 cron.log"
            assert (logs / "cron.log").stat().st_size == 0, "轮转后 cron.log 必须是空的"
            assert (logs / "cron.log.1").stat().st_size == backup.LOG_MAX_BYTES + 1, "cron.log.1 应被覆盖为旧内容"
            assert (logs / "cron_failures.log").stat().st_size == 0
            assert (logs / "cron_failures.log.1").stat().st_size == backup.LOG_MAX_BYTES + 5
            assert outsider.stat().st_size == backup.LOG_MAX_BYTES + 9, "不在名单里的日志不该被动"
            assert not (logs / "failed_sources.log.1").exists()
    finally:
        cleanup(root)


def test_log_rotation_skipped_below_threshold() -> None:
    root, data, logs = fresh_env("log_no_rotation")
    try:
        with patched(root):
            make_db(data / "english.sqlite", 2)
            (logs / "cron.log").write_bytes(b"a" * (backup.LOG_MAX_BYTES - 1))
            code, payload, err = run_cli()
            assert code == 0, f"退出码 {code}\n{err}"
            assert payload["rotated_logs"] == [], f"未超阈值不该轮转，实际 {payload['rotated_logs']}"
            assert (logs / "cron.log").stat().st_size == backup.LOG_MAX_BYTES - 1
            assert not (logs / "cron.log.1").exists()
            assert not (logs / "cron_failures.log").exists(), "可选日志不存在时不该被创建"
    finally:
        cleanup(root)


# --------------------------------------------------------------------- ④ 只读模式


def test_list_and_verify_are_read_only() -> None:
    root, data, logs = fresh_env("readonly_modes")
    try:
        with patched(root):
            make_db(data / "english.sqlite", 5)
            code, payload, err = run_cli()
            assert code == 0, f"首次备份失败：{code}\n{err}"
            latest = Path(payload["backup_dir"]).name

            before = tree_snapshot(root)

            c1, p1, _ = run_cli("--list")
            assert c1 == 0, f"--list 退出码 {c1}"
            assert p1["count"] == 1, f"--list 应看到 1 份，实际 {p1['count']}"
            assert p1["latest"] == latest and p1["backups"][0]["dir"] == latest
            assert p1["backups"][0]["databases"] == 1
            assert p1["backups"][0]["files"] == ["english.sqlite"]
            assert p1["backups"][0]["bytes"] > 0

            c2, p2, _ = run_cli("--verify")
            assert c2 == 0, f"--verify 退出码 {c2}"
            assert p2["ok"] is True
            assert p2["integrity"] == {"english.sqlite": "ok"}
            assert Path(p2["backup_dir"]).name == latest

            after = tree_snapshot(root)
            assert after == before, (
                "--list/--verify 不得改动任何文件；差异："
                f"{[x for x in after if x not in before][:3]} / 丢失 {[x for x in before if x not in after][:3]}"
            )
            # 尤其不能校验校验着就生成 WAL 边车
            bdir = backup.BACKUP_ROOT / latest
            assert sorted(p.name for p in bdir.iterdir()) == ["english.sqlite"], (
                f"备份目录被写入了额外文件：{sorted(p.name for p in bdir.iterdir())}"
            )
    finally:
        cleanup(root)


def test_list_and_verify_on_empty_state_write_nothing() -> None:
    root, data, logs = fresh_env("readonly_empty")
    try:
        with patched(root):
            make_db(data / "english.sqlite", 1)
            before = tree_snapshot(root)

            c1, p1, _ = run_cli("--list")
            assert c1 == 0 and p1["count"] == 0 and p1["latest"] is None
            c2, p2, _ = run_cli("--verify")
            assert c2 == 1, "--verify 在没有任何备份时必须非 0 退出"
            assert p2["ok"] is False and "error" in p2

            assert tree_snapshot(root) == before, "--list/--verify 不该创建任何文件（含 backup 根目录）"
            assert not backup.BACKUP_ROOT.exists(), "只读模式不得创建 data/backup"
    finally:
        cleanup(root)


# --------------------------------------------------------------------- ⑤ 结构与数据


def test_snapshot_preserves_schema_and_rows() -> None:
    root, data, logs = fresh_env("schema_rows")
    try:
        with patched(root):
            src = data / "aca_llm.sqlite"
            w = make_db(src, 120, keep_open=True)
            try:
                # 提交后再改一行：这次改动只存在于 -wal 里，副本必须跟上
                w.execute("UPDATE items SET name='中文·NULL 边界' WHERE id=1")
                w.execute("INSERT INTO items(id, name, score) VALUES(999, NULL, NULL)")
                w.commit()

                code, payload, err = run_cli()
                assert code == 0, f"退出码 {code}\n{err}"
                dst = Path(payload["backup_dir"]) / "aca_llm.sqlite"

                assert schema_of(dst) == schema_of(src), "表结构（含索引）应逐字一致"
                src_rows, dst_rows = rows_of(src), rows_of(dst)
                assert dst_rows == src_rows, "逐行数据应完全一致"
                assert len(dst_rows) == 121, f"应有 121 行，实际 {len(dst_rows)}"
                assert dst_rows[0][1] == "中文·NULL 边界", "只存在于 -wal 的 UPDATE 丢失了"
                assert dst_rows[-1] == (999, None, None), "NULL 值应原样保留"
            finally:
                if w is not None:
                    w.close()
    finally:
        cleanup(root)


# --------------------------------------------------------------------- ⑥ 坏备份可发现


def test_verify_detects_corrupted_backup() -> None:
    root, data, logs = fresh_env("verify_corrupt")
    try:
        with patched(root):
            make_db(data / "english.sqlite", 200)
            code, payload, _ = run_cli()
            assert code == 0
            copy = Path(payload["backup_dir"]) / "english.sqlite"
            assert backup.integrity_check(copy) == "ok"

            raw = bytearray(copy.read_bytes())  # 保留第 1 页（头部），破坏其后的数据页
            assert len(raw) > 4096, "测试需要多页的库"
            raw[4096:] = b"\xff" * (len(raw) - 4096)
            copy.write_bytes(bytes(raw))

            c2, p2, _ = run_cli("--verify")
            assert c2 != 0, "损坏的备份必须让 --verify 非 0 退出"
            assert p2["ok"] is False and p2["integrity"]["english.sqlite"] != "ok"
    finally:
        cleanup(root)


# --------------------------------------------------------------------- ⑦ 真实命令行


def test_cli_subprocess_end_to_end() -> None:
    """把 backup.py 复制进临时项目树的 scripts/ 下，用真实命令行跑一遍。"""
    root, data, logs = fresh_env("cli_e2e")
    try:
        scripts = root / "scripts"
        scripts.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / "scripts" / "backup.py", scripts / "backup.py")
        make_db(data / "c_wuhan.sqlite", 11)

        proc = subprocess.run(
            [PY, str(scripts / "backup.py")],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=120, cwd=str(root),
        )
        assert proc.returncode == 0, f"退出码 {proc.returncode}\n{proc.stderr[-800:]}"
        payload = json.loads(proc.stdout.strip())
        assert Path(payload["backup_dir"]).parent == data / "backup"
        assert payload["integrity"] == {"c_wuhan.sqlite": "ok"}
        assert payload["kept"] == 1 and payload["rotated_logs"] == []
        assert "恢复必须按序执行" in proc.stderr, "stderr 必须给出恢复流程提示"
        assert "-wal" in proc.stderr and "WinError 32" in proc.stderr
        copy = Path(payload["backup_dir"]) / "c_wuhan.sqlite"
        assert rows_of(copy) == rows_of(data / "c_wuhan.sqlite")
    finally:
        cleanup(root)


def test_arg_errors() -> None:
    root, data, logs = fresh_env("arg_errors")
    try:
        with patched(root):
            make_db(data / "english.sqlite", 1)
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                assert backup.main(["--bogus"]) == 2
                assert backup.main(["--keep", "abc"]) == 2
                assert backup.main(["--keep"]) == 2
                assert backup.main(["--list", "--verify"]) == 2
                assert backup.main(["--keep", "1"]) == 0, "合法参数应正常备份"
            assert len(backup.list_backups()) == 1
    finally:
        cleanup(root)


def test_compile() -> None:
    import py_compile

    py_compile.compile(str(ROOT / "scripts" / "backup.py"), doraise=True)


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
    shutil.rmtree(TMPROOT, ignore_errors=True)  # 只清自己的子树 tests/.tmp/backup
    print(f"{len(fns) - failed}/{len(fns)} passed")
    raise SystemExit(1 if failed else 0)
