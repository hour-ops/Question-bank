/* 题库项目 · 设置页：AI 判分 / API key 卡片（需求 9）
   纯原生 JS，零框架 / 零 CDN / 零外链。

   对接的后端接口（由主会话实现，前端只按形状消费）：
     GET  /api/settings           -> {api_key_configured, api_key_hint, base_url, base_url_configured, env_file}
     POST /api/settings/api_key   -> body {api_key: "sk-..."} 保存；body {api_key: ""} 清空

   铁律：
     1. 只有用户点「保存 API key」/「清空」才发请求 —— 没有 oninput / onblur 自动保存；
     2. 接口未就绪（404 / 非 JSON / 网络失败）时保留服务端渲染的状态，不白屏、不抛未捕获异常；
     3. 绝不回显完整 key：只用后端给的掩码（api_key_hint），且一律走 textContent（不 innerHTML）。 */

(function () {
  "use strict";

  var GET_URL = "/api/settings";
  var POST_URL = "/api/settings/api_key";

  /* 最近一次已知的服务端状态：true / false / null（null = 接口还没读到，状态未知） */
  var configured = null;
  var sending = false;

  function byId(id) { return document.getElementById(id); }

  function eachButton(fn) {
    [byId("btnSaveApiKey"), byId("btnClearApiKey")].forEach(function (b) {
      if (b) { fn(b); }
    });
  }

  function setNote(text) {
    var el = byId("apiKeySyncNote");
    if (el) { el.textContent = text || ""; }
  }

  /* 就地更新状态文字（不刷新整页） */
  function setState(isConfigured, hintText) {
    configured = !!isConfigured;
    var state = byId("apiKeyState");
    if (state) {
      state.textContent = configured ? "已配置（不回显内容）" : "未配置";
      state.className = configured ? "ok-text" : "err-text";
    }
    var hint = byId("apiKeyHint");
    if (hint) {
      var mask = (hintText === null || hintText === undefined) ? "" : String(hintText);
      hint.textContent = (configured && mask) ? "（当前 key：" + mask + "）" : "";
    }
  }

  /* 把后端返回的字段应用到页面 */
  function applySettings(data) {
    if (!data || typeof data !== "object") { return; }
    if (typeof data.api_key_configured === "boolean") {
      setState(data.api_key_configured, data.api_key_hint);
    } else if (data.api_key_hint) {
      var hint = byId("apiKeyHint");
      if (hint) { hint.textContent = "（当前 key：" + String(data.api_key_hint) + "）"; }
    }
    var envFile = byId("apiKeyEnvFile");
    if (envFile && data.env_file) { envFile.textContent = String(data.env_file); }
  }

  /* 页面加载：拉一次实时状态；失败就优雅降级到服务端渲染的快照 */
  function loadSettings() {
    if (!window.TKU || !window.TKU.getJSON) { return; }
    window.TKU.getJSON(GET_URL).then(function (data) {
      applySettings(data);
      setNote("");
    }).catch(function () {
      /* 静默降级：404 / 非 JSON / 网络错误都走这里，保留 {% if %} 渲染出的状态 */
      setNote("（实时状态读取失败，上面显示的是页面快照；此时保存也可能失败）");
    });
  }

  /* 唯一的提交出口：value 为空字符串 = 清空 */
  function send(apiKey, btn, busyText) {
    if (sending) { return; }
    if (!window.TKU || !window.TKU.postJSON) { return; }
    sending = true;

    var original = btn ? btn.textContent : "";
    eachButton(function (b) { b.disabled = true; });
    if (btn) { btn.textContent = busyText; }

    window.TKU.postJSON(POST_URL, { api_key: apiKey }).then(function (data) {
      var okc = (data && typeof data.api_key_configured === "boolean")
        ? data.api_key_configured
        : (apiKey !== "");
      setState(okc, data ? data.api_key_hint : null);
      setNote("");
      var input = byId("apiKeyInput");
      if (input) { input.value = ""; }   /* 存完立刻清空，不在 DOM 里留明文 key */
      window.TKU.toast(apiKey === "" ? "已清空 API key" : "已保存", "ok");
    }).catch(function (err) {
      /* 失败时把后端返回的 error 原文显示出来 */
      var msg = (err && err.data && err.data.error) || (err && err.message) || "保存失败";
      window.TKU.toast(String(msg), "err");
    }).then(function () {
      sending = false;
      eachButton(function (b) { b.disabled = false; });
      if (btn) { btn.textContent = original; }
    });
  }

  function onSave() {
    var input = byId("apiKeyInput");
    var value = input ? String(input.value === null || input.value === undefined ? "" : input.value).trim() : "";

    if (value === "") {
      if (configured === false) {
        window.TKU.toast("输入框是空的：请先粘贴 API key 再点「保存 API key」", "err");
        return;
      }
      /* 空值 = 清空（后端约定）。防止误点把已配置的 key 清掉，这里必须二次确认 */
      if (!window.confirm("输入框为空。点「确定」＝清空已保存的 API key，点「取消」＝不做任何改动。")) {
        window.TKU.toast("已取消，未做任何改动");
        return;
      }
    }
    send(value, byId("btnSaveApiKey"), "保存中…");
  }

  function onClear() {
    if (configured === false) {
      window.TKU.toast("当前未配置 API key，无需清空", "err");
      return;
    }
    if (!window.confirm("确定清空已保存的 API key？清空后主观题不能送 AI 判分（客观题不受影响）。")) {
      window.TKU.toast("已取消，未做任何改动");
      return;
    }
    var input = byId("apiKeyInput");
    if (input) { input.value = ""; }
    send("", byId("btnClearApiKey"), "清空中…");
  }

  function init() {
    var save = byId("btnSaveApiKey");
    var clear = byId("btnClearApiKey");
    var input = byId("apiKeyInput");

    if (save) { save.addEventListener("click", onSave); }
    if (clear) { clear.addEventListener("click", onClear); }
    if (input) {
      /* 回车＝用户显式触发保存（等价于点按钮）；没有 input/blur 监听，绝不自动保存 */
      input.addEventListener("keydown", function (ev) {
        if (ev.key === "Enter") { ev.preventDefault(); onSave(); }
      });
    }
    loadSettings();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
