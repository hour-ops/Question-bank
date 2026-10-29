#!/usr/bin/env python
"""需求 9 · API key 配置接口离线测试（**不联网、不烧钱、不碰真实 .env**）。

覆盖:
  ① `GET /api/settings`：形状正确；**只回掩码，绝不回完整 key**
  ② `POST /api/settings/api_key`：写 `.env`、保留其余行与注释、重复保存是覆盖而非追加
  ③ 清空（空字符串）→ **删除该行**，且 `api_key_configured=False`
  ④ 非法输入被挡：含中文 / 含空格 / 含换行 / 太短 / 过长 → 400 且**文件不被改动**
  ⑤ `_env_flags()` / `mask_secret()` 单元：掩码规则与"空值不算配置"
  ⑥ 设置页 HTML 含可点击的配置入口（输入框 + 保存按钮），且**没有自动保存**的钩子

⚠️ 全程把 `webapp.ROOT` 指到临时目录，绝不动项目真实 `.env`。

运行: python tests/test_settings_api.py
"""

from __future__ import annotations

import contextlib
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app" / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

import app as webapp  # noqa: E402

TMPROOT = ROOT / "tests" / ".tmp" / "settings_api"
FAKE_KEY = "sk-abcdefghijklmnopqrstuvwxyz0123456789"


@contextlib.contextmanager
def env(name: str):
    """临时"项目根"：只需要 `.env`（其余数据目录一并指过去，避免误读真实库）。"""
    base = TMPROOT / name
    shutil.rmtree(base, ignore_errors=True)
    base.mkdir(parents=True, exist_ok=True)
    saved = (webapp.ROOT, webapp.DATA_DIR, webapp.LOGS_DIR, webapp.OUTPUT_DIR)
    webapp.ROOT = base
    webapp.DATA_DIR = base / "data"
    webapp.LOGS_DIR = base / "logs"
    webapp.OUTPUT_DIR = base / "output"
    webapp.app.config["TESTING"] = True
    try:
        yield base
    finally:
        webapp.ROOT, webapp.DATA_DIR, webapp.LOGS_DIR, webapp.OUTPUT_DIR = saved
        webapp.app.config["TESTING"] = False


def client():
    return webapp.app.test_client()


# --------------------------------------------------------------------- ⑤ 单元


def test_mask_secret() -> None:
    assert webapp.mask_secret("") is None
    assert webapp.mask_secret(None) is None
    assert webapp.mask_secret("short") == "…rt"
    masked = webapp.mask_secret(FAKE_KEY)
    assert masked == "sk-…6789", masked
    assert FAKE_KEY not in masked, "掩码里绝不能出现完整 key"


def test_write_env_preserves_other_lines() -> None:
    with env("write") as base:
        (base / ".env").write_text(
            "# 注释要保留\nDEEPSEEK_BASE_URL=https://api.deepseek.com\nOTHER=x\n", encoding="utf-8")
        webapp.write_env_value("DEEPSEEK_API_KEY", FAKE_KEY)
        text = (base / ".env").read_text(encoding="utf-8")
        assert "# 注释要保留" in text and "OTHER=x" in text, text
        assert f"DEEPSEEK_API_KEY={FAKE_KEY}" in text, text
        # 覆盖而不是追加
        webapp.write_env_value("DEEPSEEK_API_KEY", "sk-second-key-0001")
        text2 = (base / ".env").read_text(encoding="utf-8")
        assert text2.count("DEEPSEEK_API_KEY=") == 1, text2
        assert "sk-second-key-0001" in text2 and FAKE_KEY not in text2, text2
        # 清空 = 删行，其余行仍在
        webapp.write_env_value("DEEPSEEK_API_KEY", "")
        text3 = (base / ".env").read_text(encoding="utf-8")
        assert "DEEPSEEK_API_KEY" not in text3, text3
        assert "OTHER=x" in text3 and "DEEPSEEK_BASE_URL" in text3, text3


def test_write_env_rejects_injection() -> None:
    with env("inject") as base:
        for bad_key in ("BAD KEY", "1ABC", "", "A-B"):
            try:
                webapp.write_env_value(bad_key, "x")
            except ValueError:
                continue
            raise AssertionError(f"非法键名竟然被接受: {bad_key!r}")
        for bad_val in ("a\nb", "a\rb", "a\x00b"):
            try:
                webapp.write_env_value("DEEPSEEK_API_KEY", bad_val)
            except ValueError:
                continue
            raise AssertionError(f"含换行/NUL 的值竟然被接受: {bad_val!r}")
        assert not (base / ".env").exists() or "DEEPSEEK_API_KEY" not in (base / ".env").read_text(
            encoding="utf-8")


# --------------------------------------------------------------------- ①②③④ 接口


def test_get_settings_shape_and_no_leak() -> None:
    with env("get"):
        c = client()
        body = c.get("/api/settings").get_json()
        for key in ("api_key_configured", "api_key_hint", "base_url_configured", "env_file"):
            assert key in body, (key, body)
        assert body["api_key_configured"] is False and body["api_key_hint"] is None, body

        c.post("/api/settings/api_key", json={"api_key": FAKE_KEY})
        body2 = c.get("/api/settings").get_json()
        assert body2["api_key_configured"] is True, body2
        assert body2["api_key_hint"] == "sk-…6789", body2
        assert FAKE_KEY not in str(body2), "响应里泄露了完整 key！"


def test_post_saves_and_clears() -> None:
    with env("post") as base:
        c = client()
        resp = c.post("/api/settings/api_key", json={"api_key": FAKE_KEY})
        assert resp.status_code == 200, resp.data[:300]
        body = resp.get_json()
        assert body["ok"] is True and body["api_key_configured"] is True, body
        assert FAKE_KEY not in resp.get_data(as_text=True), "响应里泄露了完整 key！"
        text = (base / ".env").read_text(encoding="utf-8")
        assert f"DEEPSEEK_API_KEY={FAKE_KEY}" in text, text

        # 清空
        resp2 = c.post("/api/settings/api_key", json={"api_key": ""})
        assert resp2.status_code == 200 and resp2.get_json()["api_key_configured"] is False, resp2.data[:300]
        assert "DEEPSEEK_API_KEY" not in (base / ".env").read_text(encoding="utf-8")
        assert c.get("/api/settings").get_json()["api_key_configured"] is False

        # 缺字段 → 400（而不是静默清空）
        assert c.post("/api/settings/api_key", json={}).status_code == 400


def test_post_rejects_bad_keys_without_touching_file() -> None:
    with env("bad") as base:
        c = client()
        c.post("/api/settings/api_key", json={"api_key": FAKE_KEY})
        before = (base / ".env").read_text(encoding="utf-8")
        bads = ["这是说明文字不是key", "sk-abc def", "sk-abc\ndef", "short", "x" * 201]
        for bad in bads:
            resp = c.post("/api/settings/api_key", json={"api_key": bad})
            assert resp.status_code == 400, (bad, resp.status_code, resp.data[:200])
            assert resp.get_json().get("error"), (bad, resp.data[:200])
        after = (base / ".env").read_text(encoding="utf-8")
        assert before == after, "非法输入竟然改动了 .env"


def test_base_url_endpoint() -> None:
    with env("base") as base:
        c = client()
        assert c.post("/api/settings/base_url", json={"base_url": "ftp://x"}).status_code == 400
        ok = c.post("/api/settings/base_url", json={"base_url": "https://relay.example.com/v1/"})
        assert ok.status_code == 200, ok.data[:200]
        text = (base / ".env").read_text(encoding="utf-8")
        assert "DEEPSEEK_BASE_URL=https://relay.example.com/v1" in text, text   # 尾部斜杠被去掉
        c.post("/api/settings/base_url", json={"base_url": ""})
        assert "DEEPSEEK_BASE_URL" not in (base / ".env").read_text(encoding="utf-8")


# --------------------------------------------------------------------- ⑥ 页面入口


def test_settings_page_has_manual_save_entry() -> None:
    with env("page"):
        html = client().get("/settings").get_data(as_text=True)
        assert 'id="apiKeyInput"' in html, "设置页没有 API key 输入框"
        assert 'type="password"' in html, "输入框应是 password 类型（不显示明文）"
        assert 'id="btnSaveApiKey"' in html, "缺少显眼的保存按钮"
        assert 'id="apiKeyState"' in html, "缺少状态显示"
        # 必须由用户点击才保存：不得出现 oninput/onblur 自动提交
        for hook in ("oninput=", "onblur=", "onchange="):
            assert hook not in html, f"页面出现了自动保存钩子: {hook}"
        # 说明文案要能让人看懂"判分同步"是干什么的
        assert "判分" in html, "缺少判分相关说明"
        # 零外链（与 test_web_ui.py 同一道闸门）
        assert "http://" not in html and "https://" not in html, "设置页出现了外链资源"


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
            print(f"  FAIL {fn.__name__}: {type(exc).__name__}: {exc}")
    print(f"[test_settings_api] {len(fns) - failed}/{len(fns)} passed")
    raise SystemExit(1 if failed else 0)
