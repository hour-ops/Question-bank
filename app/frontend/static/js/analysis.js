/* 题库项目 · 分析页「弱势诊断」（需求 8，纯原生 JS，零 CDN / 零外链）
   数据源：GET /api/weakness（scripts/weakness.py 算出来的，对错口径与全项目一致）
     - totals：我的总作答 / 已判分 / 对 / 错 / 未判分 / 正确率
     - weakest.{subjects,knowledge_points,question_types}：弱势榜（错误数降序，样本太少的标 low_sample）
     - coverage：题库覆盖面（每科做了多少 / 共多少；按知识点的未刷题缺口）
     - trend：近 14 天正确率
   「生成强化方案」按钮走 POST /api/weakness/advice —— **默认只回提示词，不发付费请求**。

   铁律：所有插入 DOM 的文本一律 textContent / TKU.esc()，绝不 innerHTML 拼数据。 */

(function () {
  "use strict";

  var API = "/api/weakness";
  var ADVICE_API = "/api/weakness/advice";

  function byId(id) { return document.getElementById(id); }

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) { node.className = cls; }
    if (text !== undefined && text !== null) { node.textContent = String(text); }
    return node;
  }

  function pct(x) { return Math.round((Number(x) || 0) * 1000) / 10; }

  function clear(node) { while (node && node.firstChild) { node.removeChild(node.firstChild); } }

  /* ---------- 小表格构造器：表头 + 行（单元格可以是文本、节点或 {html 由调用方给节点}） ---------- */
  function table(headers, rows) {
    var t = el("table", "data");
    var thead = el("thead");
    var tr = el("tr");
    headers.forEach(function (h) { tr.appendChild(el("th", null, h)); });
    thead.appendChild(tr);
    t.appendChild(thead);
    var tbody = el("tbody");
    rows.forEach(function (cells) {
      var r = el("tr");
      cells.forEach(function (c) {
        var td = el("td");
        if (c instanceof Node) { td.appendChild(c); } else { td.textContent = String(c); }
        r.appendChild(td);
      });
      tbody.appendChild(r);
    });
    t.appendChild(tbody);
    return t;
  }

  function barCell(ratio, cls) {
    var span = el("span", "bar bar-small" + (cls ? " " + cls : ""));
    var inner = el("span");
    inner.style.width = Math.max(0, Math.min(100, pct(ratio))) + "%";
    span.appendChild(inner);
    return span;
  }

  function accuracyCell(ratio, judged) {
    var td = el("td");
    var strong = el("strong", ratio < 0.6 ? "err-text" : (ratio >= 0.8 ? "ok-text" : null),
                    pct(ratio) + "%");
    td.appendChild(strong);
    if (judged) { td.appendChild(el("span", "muted small", "（" + judged + " 题）")); }
    return td;
  }

  function weakList(title, items, keyLabel, emptyHint) {
    var box = el("div");
    box.appendChild(el("h3", null, title));
    if (!items || !items.length) {
      box.appendChild(el("p", "muted small", emptyHint));
      return box;
    }
    box.appendChild(table([keyLabel, "对 / 判", "错", "正确率", "强度"], items.map(function (x) {
      var name = el("span", null, x.label || x.key);
      if (x.low_sample) {
        name.appendChild(el("span", "muted small", " ⚠样本少"));
      }
      return [
        name,
        (x.correct || 0) + " / " + (x.judged || 0),
        el("span", "err-text", x.wrong || 0),
        accuracyCell(x.accuracy, x.judged),
        barCell(x.accuracy),
      ];
    })));
    return box;
  }

  /* ---------- 渲染整块 ---------- */
  function render(data) {
    var root = byId("weakBox");
    if (!root) { return; }
    clear(root);

    var t = data.totals || {};
    if (!t.attempts) {
      root.appendChild(el("p", "muted",
        "还没有作答记录。去「刷题」或「套卷模拟」做几题后，这里会自动开始分析你的弱势项" +
        "（每做一题都会记录，做得越多越准）。"));
    }

    // KPI
    var kpis = el("div", "kpis");
    [["总作答", t.attempts, ""], ["已判分", t.judged, ""], ["答对", t.correct, "kpi-ok"],
     ["答错", t.wrong, "kpi-err"], ["未判分", t.unjudged, "kpi-due"],
     ["我的正确率", pct(t.accuracy) + "%", t.accuracy < 0.6 ? "kpi-err" : "kpi-ok"]]
      .forEach(function (row) {
        var k = el("div", "kpi " + (row[2] || ""));
        k.appendChild(el("span", "kpi-num", row[1]));
        k.appendChild(el("span", "kpi-label", row[0]));
        kpis.appendChild(k);
      });
    root.appendChild(kpis);
    root.appendChild(el("p", "muted small",
      "口径：对错判定走 update_daily_progress.judge_correct（与首页/进度页完全一致）；" +
      "未判分的作答（写作、整段翻译等）不计入正确率分母。"));

    // 弱势三榜
    var weakest = data.weakest || {};
    var grid = el("div", "grid grid-2");
    grid.appendChild(weakList("弱势科目", weakest.subjects, "科目",
      "暂无样本足够的弱势科目（少于 3 题的维度不列入，避免「做 1 题错 1 题」的假弱势）。"));
    grid.appendChild(weakList("弱势题型", weakest.question_types, "题型",
      "暂无样本足够的弱势题型。"));
    root.appendChild(grid);
    root.appendChild(weakList("弱势知识点（最该先补的排前面）", weakest.knowledge_points, "知识点",
      "暂无样本足够的弱势知识点。"));

    // 覆盖率
    var cov = data.coverage || {};
    var covBox = el("div");
    covBox.appendChild(el("h3", null, "题库覆盖（我做过多少 / 题库有多少）"));
    var covRows = Object.keys(cov).map(function (subj) {
      var c = cov[subj];
      var gap = (c.knowledge_points || []).filter(function (k) { return k.done < k.total; })
        .sort(function (a, b) { return (b.total - b.done) - (a.total - a.done); }).slice(0, 3)
        .map(function (k) { return k.label + "（缺 " + (k.total - k.done) + "）"; }).join("、");
      return [subj, c.done + " / " + c.total, pct(c.ratio) + "%", barCell(c.ratio),
              gap || "已全覆盖"];
    });
    covBox.appendChild(table(["科目", "做过 / 题库", "覆盖", "进度", "未刷题最多的知识点"], covRows));
    root.appendChild(covBox);

    // 趋势
    var trend = data.trend || [];
    if (trend.length) {
      var trBox = el("div");
      trBox.appendChild(el("h3", null, "近 14 天正确率"));
      trBox.appendChild(table(["日期", "作答", "已判分", "答对", "正确率", "走势"],
        trend.slice(-14).map(function (x) {
          return [x.date, x.total, x.judged, x.correct, accuracyCell(x.accuracy, 0), barCell(x.accuracy)];
        })));
      root.appendChild(trBox);
    }

    root.appendChild(el("p", "muted small",
      "快照文件：logs/weakness_history.jsonl（每天一条，越刷越准）。诊断生成时间：" +
      (data.generated_at || "—")));
  }

  function showError(msg) {
    var root = byId("weakBox");
    if (!root) { return; }
    clear(root);
    root.appendChild(el("p", "err-text", "弱势诊断加载失败：" + msg));
  }

  function load() {
    if (!window.TKU || !window.TKU.getJSON) { return; }
    window.TKU.getJSON(API + "?remember=1").then(render).catch(function (err) {
      showError((err && err.message) || String(err));
    });
  }

  /* ---------- 生成强化方案（默认零成本：只拿提示词） ---------- */
  function onAdvice() {
    var btn = byId("btnAdvice");
    var box = byId("adviceBox");
    if (!btn || !box) { return; }
    var original = btn.textContent;
    btn.disabled = true;
    btn.textContent = "生成中…";
    clear(box);
    window.TKU.postJSON(ADVICE_API, {}).then(function (data) {
      var head = el("p", "muted small",
        "已生成给大模型的提示词（" + (data.prompt_chars || 0) + " 字）。" +
        "本机默认**不自动调用付费接口**，请把下面这段复制到任意大模型；" +
        "或在「设置」页配置 API key 后由维护者接通。");
      box.appendChild(head);
      var est = data.estimate || {};
      if (est.cost_cny_est !== undefined) {
        box.appendChild(el("p", "muted small",
          "参考成本（" + (est.note || "") + "）：约 " + est.cost_cny_est + " 元 / " +
          (est.input_tokens_est || 0) + " 输入 token"));
      }
      var pre = el("pre", "json-preview");
      pre.textContent = data.prompt || "";
      box.appendChild(pre);
      var row = el("p", "row");
      var copy = el("button", "btn", "复制提示词");
      copy.type = "button";
      copy.addEventListener("click", function () {
        var text = data.prompt || "";
        var done = function () { window.TKU.toast("已复制，粘贴到大模型即可", "ok"); };
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(text).then(done).catch(function () { selectPre(pre); });
        } else { selectPre(pre); }
      });
      row.appendChild(copy);
      box.appendChild(row);
    }).catch(function (err) {
      var msg = (err && err.data && err.data.error) || (err && err.message) || "生成失败";
      box.appendChild(el("p", "err-text", msg));
      if (err && err.data && err.data.prompt) {
        var pre2 = el("pre", "json-preview");
        pre2.textContent = err.data.prompt;
        box.appendChild(pre2);
      }
    }).then(function () {
      btn.disabled = false;
      btn.textContent = original;
    });
  }

  function selectPre(pre) {
    try {
      var range = document.createRange();
      range.selectNodeContents(pre);
      var sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
      window.TKU.toast("已选中，按 Ctrl+C 复制", "ok");
    } catch (e) { window.TKU.toast("请手动选中提示词复制", "err"); }
  }

  function init() {
    var btn = byId("btnAdvice");
    if (btn) { btn.addEventListener("click", onAdvice); }
    load();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
