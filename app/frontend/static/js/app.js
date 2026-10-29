/* 题库项目 · 公共前端脚本（纯原生 JS，零 CDN / 零外链）
   只做：DOM 小工具 / fetch 封装 / toast / 徽标 / 各页只读型初始化。
   答题、队列、审核的交互分别在 quiz.js / queue.js / review.js。 */

(function () {
  "use strict";

  var TKU = {};

  TKU.$ = function (sel, root) { return (root || document).querySelector(sel); };
  TKU.$$ = function (sel, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(sel));
  };

  TKU.esc = function (value) {
    return String(value === null || value === undefined ? "" : value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  };

  TKU.getJSON = function (url) {
    return fetch(url, { headers: { Accept: "application/json" } }).then(function (resp) {
      /* 404/500 时后端可能返回 HTML（例如服务还是旧版本、根本没有这个接口），
         直接 resp.json() 会抛 JSON 解析错误，看不出真因——这里兜住并保留状态码。 */
      return resp.text().then(function (text) {
        var data = null;
        try { data = text ? JSON.parse(text) : null; } catch (e) { data = null; }
        if (!resp.ok) {
          var msg = (data && data.error) || ("HTTP " + resp.status);
          var err = new Error(msg);
          err.status = resp.status;
          throw err;
        }
        if (data === null) { throw new Error("响应不是 JSON（HTTP " + resp.status + "）"); }
        return data;
      });
    });
  };

  TKU.postJSON = function (url, payload) {
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(payload || {})
    }).then(function (resp) {
      return resp.json().then(function (data) {
        if (!resp.ok) {
          var msg = (data && data.error) || ("HTTP " + resp.status);
          var err = new Error(msg);
          err.data = data;
          throw err;
        }
        return data;
      });
    });
  };

  var toastTimer = null;
  TKU.toast = function (message, kind) {
    var el = TKU.$("#tkuToast");
    if (!el) {
      el = document.createElement("div");
      el.id = "tkuToast";
      document.body.appendChild(el);
    }
    el.className = "toast" + (kind ? " " + kind : "");
    el.textContent = String(message);
    el.hidden = false;
    if (toastTimer) { clearTimeout(toastTimer); }
    toastTimer = setTimeout(function () { el.hidden = true; }, 3200);
  };

  TKU.badge = function (status) {
    var s = status || "pending";
    return '<span class="badge badge-' + TKU.esc(s) + '">' + TKU.esc(s) + "</span>";
  };

  /* 答错红色闪烁：#EF4444 闪 2 次（200ms × 2 = 400ms，UI_DESIGN 第 5 节） */
  TKU.flashWrong = function (el) {
    if (!el) { return; }
    el.classList.remove("flash-wrong");
    void el.offsetWidth;           /* 强制重排，保证重复触发 */
    el.classList.add("flash-wrong");
    setTimeout(function () { el.classList.remove("flash-wrong"); }, 420);
  };

  TKU.JSONPreview = function (target, data) {
    if (!target) { return; }
    target.textContent = JSON.stringify(data, null, 2);
  };

  TKU.byId = function (id) { return document.getElementById(id); };

  window.TKU = TKU;

  /* ------------------------------------------------------------ 各页初始化 */

  document.addEventListener("DOMContentLoaded", function () {
    var page = document.body.getAttribute("data-page") || "";

    /* /api/... 链接：拦截成内联预览（不跳走，仍是本地请求） */
    var preview = TKU.$("#rawPreview");
    if (preview) {
      TKU.$$('a[href^="/api/"]').forEach(function (a) {
        a.addEventListener("click", function (ev) {
          ev.preventDefault();
          var url = a.getAttribute("href");
          preview.textContent = "加载 " + url + " …";
          TKU.getJSON(url).then(function (data) {
            TKU.JSONPreview(preview, data);
          }).catch(function (err) {
            preview.textContent = "请求失败：" + err.message;
          });
        });
      });
    }

    if (page === "settings") {
      var out = TKU.byId("apiOut");
      [["btnProgress", "/api/progress?date=today"], ["btnPapers", "/api/papers"],
       ["btnQueue", "/api/queue?limit=20"]].forEach(function (pair) {
        var btn = TKU.byId(pair[0]);
        if (!btn) { return; }
        btn.addEventListener("click", function () {
          out.textContent = "加载 " + pair[1] + " …";
          TKU.getJSON(pair[1]).then(function (data) {
            TKU.JSONPreview(out, data);
          }).catch(function (err) {
            out.textContent = "请求失败：" + err.message;
          });
        });
      });
    }

    /* 首页：判分队列四态每 30s 刷新一次计数（只读接口） */
    if (page === "index") {
      setInterval(function () {
        TKU.getJSON("/api/queue?limit=1").then(function (data) {
          TKU.$$(".badge-row .badge").forEach(function (el) {
            var name = (el.textContent || "").trim().split(" ")[0];
            if (data.counts && name in data.counts) {
              el.textContent = name + " " + data.counts[name];
            }
          });
        }).catch(function () { /* 静默：首页刷新失败不打扰 */ });
      }, 30000);
    }
  });
})();
