/* 题库项目 · 套卷模式（需求 6：套卷 / 模拟考试）—— paper.js
   纯原生 JS · 零框架 · 零 CDN / 零外链。

   三个视图（同一个页面内切换，不跳新页）：
     ① 选题视图（默认）：按科目分组的套卷卡片，每张卡如实标注来源（英语=历年真题整卷 /
        C 语言=某校题集 / ACA=认证题库），点「开始模拟考试」进考场。
     ② 考试视图：整卷**按 seq 顺序**一页到底，顶部固定条（卷名 / 已答 N 共 M / 计时器 / 交卷）。
        客观题渲染成 radio（单选）或 checkbox（多选），其余题型给 textarea；**不显示答案**、
        **不能提交单题**，作答只记在内存对象 `S.answers[question_uid]`（不用 localStorage）。
     ③ 成绩报告视图：POST /api/paper/submit 之后展示得分 / 正确率 / 用时 / 分项表 / 逐题结果。

   接口：GET /api/paper/list · GET /api/paper · POST /api/paper/submit（后端已完成，本页不改后端）。
   错误处理：任何失败都把**后端返回的 error 原文**显示在页面的 .err-box 里（不白屏、只留在 console 是不允许的）。

   安全：所有插入 DOM 的题库/用户文本一律经 TKU.esc()；不含任何外部链接。
*/

(function () {
  "use strict";
  if (document.body.getAttribute("data-page") !== "paper") { return; }

  /* ------------------------------------------------------------------ 状态 */
  var S = {
    groups: {},          /* subject -> [paper, ...]（来自 /api/paper/list） */
    labels: {},          /* subject -> 中文名 */
    subjects: [],        /* 科目顺序（后端给） */
    note: "",            /* 后端对"这些套卷到底是什么"的说明 */
    subject: "english",  /* 当前标签页科目（默认英语） */
    paper: null,         /* 当前套卷（list 项：subject/title/count/exam_kind…） */
    paperMeta: null,     /* 当前套卷的 /api/paper 元信息（total_score / seq_source…） */
    subjectOfExam: "",
    questions: [],       /* 按 seq 排好序的整卷题目 */
    answers: {},         /* question_uid -> 作答字符串（**只在内存**，刷新即丢，符合"模拟考试"语义） */
    started: 0,          /* 进考场时刻（Date.now()） */
    elapsedMs: 0,
    timer: null,
    busy: false,         /* 交卷中：防重复提交 */
    typeNames: {},       /* question_type -> 中文名（优先用后端 /api/paper 给的 type_name） */
    showDone: false      /* 是否展开"已完成的卷子"折叠区（默认收起，省屏） */
  };

  /* 题型中文名兜底表：来源 config/display.json 的 types（后端 /api/paper 每题会给 type_name，
     有服务端值就用服务端的，这张表只在**选题视图**里把 question_types 的 key 显示成人话）。
     未知 key 一律原样显示，绝不编造。 */
  var TYPE_NAMES = {
    grammar_fill: "语法填空", sentence_build: "连词成句", translation_fill: "翻译填空",
    reading_fill: "阅读填空", reading_qa: "阅读理解", writing: "写作",
    sentence_completion: "完成句子", cloze: "完形填空", word_fill: "选词填空",
    single_choice: "单选题", multiple_choice: "多选题", true_false: "判断题",
    phonetics: "语音题", dialogue: "情景对话", translation_choice: "英译汉选择",
    translation: "翻译（英译汉）", outline_fill: "提纲填空", program_fill: "程序填空",
    code_correction: "程序改错", programming: "编程题"
  };

  function typeName(key) {
    if (!key) { return "未标题型"; }
    return S.typeNames[key] || TYPE_NAMES[key] || key;
  }

  /* ------------------------------------------------------------------ 工具 */
  function round1(x) {
    var n = Number(x);
    if (!isFinite(n)) { return 0; }
    return Math.round(n * 10) / 10;      /* 分数只保留 1 位小数，避免 7.999999 */
  }
  function fmtNum(x) { return String(round1(x)); }

  function fmtTime(ms) {
    var sec = Math.max(0, Math.floor((Number(ms) || 0) / 1000));
    var m = Math.floor(sec / 60), s = sec % 60;
    return (m < 10 ? "0" + m : String(m)) + ":" + (s < 10 ? "0" + s : String(s));
  }

  /* 与 TKU.getJSON / TKU.postJSON 同口径，只多一件事：**把后端的 error 原文留下来**。
     非 JSON 响应（例如 404 的 HTML、500 的堆栈页）也要能显示给用户，所以先取 text 再解析。 */
  function req(method, url, body) {
    var init = { method: method, headers: { Accept: "application/json" } };
    if (body !== undefined && body !== null) {
      init.headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(body);
    }
    return fetch(url, init).then(function (resp) {
      return resp.text().then(function (text) {
        var data = null;
        try { data = text ? JSON.parse(text) : null; } catch (e) { data = null; }
        if (!resp.ok) {
          var msg = (data && data.error) ? String(data.error)
            : ("HTTP " + resp.status + (data ? "" : "（非 JSON 响应）") +
               "：" + String(text || "").slice(0, 300));
          var err = new Error(msg);
          err.status = resp.status;
          err.data = data;
          throw err;
        }
        if (data === null) { throw new Error("响应不是合法 JSON：" + String(text || "").slice(0, 200)); }
        return data;
      });
    });
  }

  var api = {
    get: function (url) { return req("GET", url, null); },
    post: function (url, body) { return req("POST", url, body); }
  };

  function showError(boxId, msg) {
    var box = TKU.byId(boxId);
    if (!box) { return; }
    box.hidden = false;
    box.textContent = String(msg);          /* textContent：错误原文原样显示，不解析 HTML */
  }
  function clearError(boxId) {
    var box = TKU.byId(boxId);
    if (box) { box.hidden = true; box.textContent = ""; }
  }

  /* ------------------------------------------------------------------ 视图切换 */
  function setView(name) {
    TKU.byId("viewPick").hidden = (name !== "pick");
    TKU.byId("viewExam").hidden = (name !== "exam");
    TKU.byId("viewReport").hidden = (name !== "report");
    /* 考试视图里把顶栏改成 static，好让「考试固定条」sticky 到窗口顶部（不被顶栏盖住） */
    document.body.classList.toggle("exam-mode", name === "exam");
    if (name !== "exam") { stopTimer(); }
    try { window.scrollTo(0, 0); } catch (e) { /* 忽略 */ }
    return name;
  }

  /* ------------------------------------------------------------------ 计时器 */
  function paintTimer() {
    var el = TKU.byId("exTimer");
    if (el) { el.textContent = fmtTime(Date.now() - S.started); }
  }
  function stopTimer() {
    if (S.timer) { window.clearInterval(S.timer); S.timer = null; }
  }
  function beginTimer() {                    /* 不重置起点（交卷失败后继续跑） */
    stopTimer();
    paintTimer();
    S.timer = window.setInterval(paintTimer, 1000);
  }
  function resetTimer() { S.started = Date.now(); beginTimer(); }

  /* ------------------------------------------------------------------ 来源标注
     用户明确要求「不要谎称真题」：英语 = 历年真题整卷（按原卷顺序）；
     C 语言 = 某校/某教材**题集**（不是一张卷子）；ACA = 认证题库。 */
  function subjectSourceInfo(subject, paper) {
    var kind = (paper && paper.exam_kind) || "来源未标注";
    if (subject === "english") {
      return kind === "真题卷"
        ? { badge: kind, note: "历年真题整卷 · 按原卷顺序（题目顺序 = 原卷顺序）" }
        : { badge: kind, note: "英语混合来源套卷（含非真题，参考时请注意）" };
    }
    if (subject === "c_wuhan" || subject === "c_hbpu") {
      return { badge: kind, note: "校/教材题集（不是一张卷子，是该校题集，按入库顺序）" };
    }
    if (subject === "aca_llm") {
      return { badge: kind, note: "认证题库（阿里云 ACA 大模型工程师方向）" };
    }
    return { badge: kind, note: "来源混合，请注意甄别" };
  }

  function typeBrief(paper) {
    var qt = (paper && paper.question_types) || {};
    var keys = Object.keys(qt);
    if (!keys.length) { return ""; }
    return keys.map(function (k) { return typeName(k) + " " + qt[k]; }).join(" · ");
  }

  /* ------------------------------------------------------------------ ① 选题视图 */
  function loadList() {
    clearError("errBox");
    TKU.byId("pickNote").textContent = "正在加载套卷清单…";
    return api.get("/api/paper/list").then(function (data) {
      S.groups = data.groups || {};
      S.labels = data.subject_labels || {};
      S.subjects = data.subjects || Object.keys(S.groups);
      S.note = data.note || "";
      var total = Number(data.count || 0);
      TKU.byId("pickCount").textContent = total ? "（共 " + total + " 套）" : "";
      TKU.byId("pickNote").textContent = S.note;
      var want = document.body.getAttribute("data-subject") || "";
      if (want && Object.prototype.hasOwnProperty.call(S.groups, want)) { S.subject = want; }
      renderTabs();
      renderCards();
      return data;
    }).catch(function (err) {
      TKU.byId("pickNote").textContent = "";
      TKU.byId("paperCards").innerHTML = "";
      showError("errBox", "套卷清单加载失败：" + err.message);
      TKU.toast("套卷清单加载失败：" + err.message, "err");
    });
  }

  function renderTabs() {
    var box = TKU.byId("paperTabs");
    box.innerHTML = "";
    S.subjects.forEach(function (key) {
      var n = (S.groups[key] || []).length;
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "paper-tab" + (key === S.subject ? " active" : "");
      btn.setAttribute("data-subject", key);
      btn.textContent = (S.labels[key] || key) + "（" + n + "）";
      box.appendChild(btn);
    });
  }

  function renderCards() {
    var box = TKU.byId("paperCards");
    var msg = TKU.byId("pickMsg");
    var kindNote = TKU.byId("pickKindNote");
    var list = S.groups[S.subject] || [];
    var info = subjectSourceInfo(S.subject, list[0] || {});
    kindNote.hidden = false;
    kindNote.textContent = "本页来源口径：" + info.note;
    if (!list.length) {
      box.innerHTML = "";
      msg.hidden = false;
      msg.textContent = "该科目暂无套卷（/api/paper/list 的 groups 里为空）。";
      return;
    }
    msg.hidden = true;
    /* 已做完的卷子灰显 + 折叠（用户要求：方便辨认，又不想一直占屏） */
    var open = list.filter(function (p) { return !p.done; });
    var done = list.filter(function (p) { return p.done; });
    var html = open.map(function (p) { return cardHTML(p, list.indexOf(p)); }).join("");
    if (done.length) {
      html += '<div class="done-head">' +
        '<button class="btn btn-small" id="btnToggleDone" type="button">' +
        (S.showDone ? '▾ 收起' : '▸ 展开') + ' 已完成的卷子（' + done.length + '）</button>' +
        '</div>';
      if (S.showDone) {
        html += done.map(function (p) { return cardHTML(p, list.indexOf(p)); }).join("");
      }
    }
    box.innerHTML = html;
    var tg = TKU.byId("btnToggleDone");
    if (tg) {
      tg.onclick = function () { S.showDone = !S.showDone; renderCards(); };
    }
    /* 「标记完成 / 取消完成」：手动把做过的卷子变灰并折叠起来 */
    TKU.$$(".flag-btn", box).forEach(function (btn) {
      btn.onclick = function (ev) {
        ev.stopPropagation();
        var i = Number(btn.getAttribute("data-flag-idx"));
        var p = list[i];
        if (!p) { return; }
        var willDone = !p.done;
        api.post("/api/paper/flag", { subject: p.subject || S.subject, title: p.title, done: willDone })
          .then(function () {
            p.manual_done = willDone;
            p.done = willDone || p.auto_done;
            renderCards();
            TKU.toast(willDone ? "已标记为完成（灰显并折叠）" : "已取消完成标记", "ok");
          })
          .catch(function (err) { TKU.toast("标记失败：" + err.message, "err"); });
      };
    });
  }

  function cardHTML(paper, idx) {
    var info = subjectSourceInfo(paper.subject, paper);
    var count = Number(paper.count || 0);
    var real = (paper.real_count === null || paper.real_count === undefined) ? null : Number(paper.real_count);
    var mixed = (real !== null && isFinite(real) && real > 0 && real < count);
    return '<div class="card paper-card' + (paper.done ? ' paper-done' : '') + '">' +
      '<h3 class="paper-card-title">' + TKU.esc(paper.title || "(未命名套卷)") + '</h3>' +
      '<p class="paper-card-meta">' +
        '<span class="kind-badge">' + TKU.esc(paper.exam_kind || info.badge) + '</span>' +
        '<span class="pill">' + TKU.esc(String(count)) + ' 题</span>' +
        (mixed ? '<span class="pill">含真题 ' + TKU.esc(String(real)) + ' 题</span>' : '') +
        (paper.done ? '<span class="pill done-tag">✓ 已完成</span>' : '') +
        '<button class="btn btn-small flag-btn" type="button" data-flag-idx="' + TKU.esc(String(idx)) + '">' +
          (paper.done ? '取消完成' : '标记完成') + '</button>' +
      '</p>' +
      '<p class="paper-src">' + TKU.esc(info.note) + '</p>' +
      '<p class="muted small">题型分布：' + TKU.esc(typeBrief(paper) || "未标注") +
        (paper.done ? '　·　已做 ' + TKU.esc(String(paper.attempted || 0)) + '/' + TKU.esc(String(count)) + ' 题' : '') +
      '</p>' +
      '<div class="row">' +
        '<button class="btn ' + (paper.done ? 'btn-small' : 'btn-primary btn-wide') +
          '" type="button" data-idx="' + TKU.esc(String(idx)) + '">' +
          (paper.done ? '再做一次' : '开始模拟考试') + '</button>' +
      '</div>' +
    '</div>';
  }

  /* ------------------------------------------------------------------ ② 考试视图 */
  function startExam(paper) {
    if (!paper) { return; }
    S.paper = paper;
    S.subjectOfExam = paper.subject || S.subject;
    S.questions = [];
    S.answers = {};
    clearError("examMsg");
    TKU.byId("exTitle").textContent = paper.title || "（未命名套卷）";
    TKU.byId("exKind").textContent = paper.exam_kind || "—";
    TKU.byId("exProgress").textContent = "已答 0 / 共 0";
    TKU.byId("examList").innerHTML = '<div class="card muted">正在加载「' + TKU.esc(paper.title || "") + '」…</div>';
    TKU.byId("examFoot").textContent = "";
    setView("exam");
    var qs = "?subject=" + encodeURIComponent(S.subjectOfExam) +
             "&title=" + encodeURIComponent(paper.title || "");
    return api.get("/api/paper" + qs).then(function (data) {
      var list = (data.questions || []).slice();
      list.sort(function (a, b) { return (Number(a.seq) || 0) - (Number(b.seq) || 0); });  /* 严格按卷面 seq */
      S.questions = list;
      S.paperMeta = data;
      if (data.title) { S.paper = { subject: data.subject || S.subjectOfExam, title: data.title,
                                    exam_kind: (paper.exam_kind || ""),
                                    /* ⚠️ 用**清单里声明的题数**（后端单次最多返回 300 题，
                                       大套卷会被截断），供 renderExam 如实提示"只考到前 N 题" */
                                    count: Number(paper.count || list.length) }; }
      list.forEach(function (q) {
        if (q.question_type && q.type_name) { S.typeNames[q.question_type] = q.type_name; }
      });
      renderExam(data);
      resetTimer();                     /* 从进考场开始计时 */
      TKU.toast("开始考试：" + (data.title || "") + " 共 " + list.length + " 题", "ok");
      return data;
    }).catch(function (err) {
      TKU.byId("examList").innerHTML = "";
      showError("examMsg", "套卷加载失败：" + err.message);
      TKU.toast("套卷加载失败：" + err.message, "err");
    });
  }

  /* 来源徽标：用户要求「套卷里把考试宝真题标出来」，好逐题核对是否符合 ACA 考纲。
     四色区分：考试宝·有原答案=绿、考试宝·答案AI推断=青、用户提供/其它=灰、AI 生成=橙。 */
  function originPill(q) {
    var name = String(q.origin || "");
    if (!name) { return ""; }
    var cls = "src-other";
    if (name.indexOf("\u6709\u539f\u7b54\u6848") >= 0) { cls = "src-kb"; }
    else if (name.indexOf("\u63a8\u65ad") >= 0) { cls = "src-kbai"; }
    else if (name.indexOf("AI") >= 0) { cls = "src-ai"; }
    return '<span class="pill origin-badge ' + cls + '">' + TKU.esc(name) + '</span>';
  }

  function questionHTML(q, i) {
    var uid = q.question_uid || ("idx-" + i);
    var seq = (q.seq === null || q.seq === undefined) ? (i + 1) : q.seq;
    var head = '<div class="paper-q-head">' +
        '<span class="paper-seq">第 ' + TKU.esc(String(seq)) + ' 题</span>' +
        '<span class="pill">' + TKU.esc(q.type_name || typeName(q.question_type)) + '</span>' +
        originPill(q) +
      '</div>';
    /* 阅读材料整块显示（题干里的 {{__BLANK_1__}} 这类模板标记照原样显示，不做解析） */
    var mat = q.material_text
      ? '<div class="paper-material">' + TKU.esc(q.material_text) + '</div>' : "";
    var stem = '<p class="paper-stem">' + TKU.esc(q.stem || "(题干为空)") + '</p>';
    var opts = q.options_parsed || [];
    var body;
    if (q.objective === true && opts.length >= 2) {
      var multi = (q.question_type === "multiple_choice");
      body = '<div class="paper-opts" data-uid="' + TKU.esc(uid) + '" data-multi="' + (multi ? "1" : "0") + '">' +
        opts.map(function (o) {
          return '<label class="paper-opt">' +
            '<input type="' + (multi ? "checkbox" : "radio") + '" name="pq-' + TKU.esc(uid) + '" value="' + TKU.esc(o.key) + '">' +
            '<span class="opt-key">' + TKU.esc(o.key) + '</span>' +
            '<span class="opt-text">' + TKU.esc(o.text) + '</span>' +
          '</label>';
        }).join("") + '</div>';
    } else {
      body = '<textarea class="paper-ans" rows="5" data-uid="' + TKU.esc(uid) +
        '" placeholder="在此作答（写作 / 翻译 / 完形 / 填空 / 编程题）"></textarea>';
    }
    return '<div class="card paper-q" id="pq-' + TKU.esc(String(seq)) + '">' + head + mat + stem + body + '</div>';
  }

  /* ACA 考纲 V2.4 的六大考点与权重（官方试卷结构：50 题 / 100 分 / 60 分钟 / 80 分及格） */
  var ACA_MODULES = ["大模型概念", "提示词工程", "增强大模型应用的能力",
                     "大模型微调", "大模型 Agent", "安全合规"];
  var ACA_WEIGHTS = {"大模型概念": 0.18, "提示词工程": 0.20, "增强大模型应用的能力": 0.22,
                     "大模型微调": 0.12, "大模型 Agent": 0.16, "安全合规": 0.12};

  /* 考点分布条：只有题目带 `chapter`（形如「大模型微调·4.5」）时才显示，
     这样"这套卷按没按考纲权重出"在考场里一眼可验，不用翻文档。 */
  function distText(meta) {
    var groups = {}, seen = 0;
    S.questions.forEach(function (q) {
      var mod = "";
      var ch = String(q.chapter || "");
      var i = ch.indexOf("\u00b7");                 /* '·' */
      if (i > 0) { mod = ch.slice(0, i).trim(); }
      /* 兜底：老数据的 chapter 为空，但知识库题的 knowledge_point 形如「考点·大模型微调」 */
      if (!mod) {
        var kp = String(q.knowledge_point || "");
        if (kp.indexOf("\u8003\u70b9\u00b7") === 0) { mod = kp.slice(3).trim(); }
      }
      if (!mod) { return; }
      seen += 1;
      groups[mod] = (groups[mod] || 0) + 1;
    });
    if (!seen) { return ""; }
    var parts = ACA_MODULES.map(function (name) {
      var n = groups[name] || 0;
      return name + " " + n + " 题（" + Math.round((ACA_WEIGHTS[name] || 0) * 100) + "%）";
    });
    var extra = [];
    var score = Number(meta.total_score || 0);
    if (score) { extra.push("满分 " + score + " 分"); }
    var total = S.questions.length;
    if (total === 50) { extra.push("限时 60 分钟", "80 分及格（答对 40 题）"); }
    var origins = {};
    S.questions.forEach(function (q) { if (q.origin) { origins[q.origin] = (origins[q.origin] || 0) + 1; } });
    var okeys = Object.keys(origins);
    if (okeys.length) {
      extra.push("来源：" + okeys.map(function (k) { return k + " " + origins[k] + " 题"; }).join(" / "));
    }
    return "考点分布：" + parts.join("｜") + (extra.length ? "　·　" + extra.join("　·　") : "");
  }

  function renderExam(data) {
    var box = TKU.byId("examList");
    var meta = data || {};
    var shown = S.questions.length;
    var declared = Number((S.paper && S.paper.count) || 0);
    TKU.byId("examFoot").textContent = "共 " + shown + " 题 · " +
      (meta.seq_source ? "顺序：" + meta.seq_source : "按卷面顺序") +
      " · 交卷前不显示答案";
    /* 如实说明"为什么只考到 300 题"：后端单次最多返回 300 题（大套卷列表里 400+ 题） */
    var trunc = TKU.byId("examTrunc");
    if (trunc) {
      if (declared > shown) {
        trunc.hidden = false;
        trunc.textContent = "⚠ 这套卷在清单里共 " + declared + " 题，本次只取回前 " + shown +
          " 题（后端单次最多返回 " + shown + " 题）——本页只考、只交这 " + shown + " 题。";
      } else {
        trunc.hidden = true;
        trunc.textContent = "";
      }
    }
    box.innerHTML = S.questions.map(questionHTML).join("");
    var dist = TKU.byId("examDist");
    if (dist) {
      var text = distText(meta);
      dist.hidden = !text;
      dist.textContent = text;
    }
    updateAnswered();
  }

  function countAnswered() {
    var n = 0;
    S.questions.forEach(function (q) {
      var a = S.answers[q.question_uid || ""];
      if (a !== undefined && a !== null && String(a).trim() !== "") { n += 1; }
    });
    return n;
  }
  function countUnanswered() { return Math.max(0, S.questions.length - countAnswered()); }

  function updateAnswered() {
    var n = countAnswered(), total = S.questions.length;
    TKU.byId("exProgress").textContent = "已答 " + n + " / 共 " + total;
    var foot = TKU.byId("examFoot");
    if (foot && total) {
      foot.textContent = "共 " + total + " 题 · 已答 " + n + " 题 · 未答 " + (total - n) +
        " 题 · 顺序：" + ((S.paperMeta && S.paperMeta.seq_source) || "按卷面顺序");
    }
  }

  /* 只记录选择，不提交单题：客观题 change、主观题 input 都写进内存 S.answers */
  function bindExamInputs() {
    var box = TKU.byId("examList");
    box.addEventListener("change", function (ev) {
      var t = ev.target;
      if (!t || t.tagName !== "INPUT") { return; }
      var wrap = t.closest ? t.closest(".paper-opts") : null;
      if (!wrap) { return; }
      var uid = wrap.getAttribute("data-uid") || "";
      if (wrap.getAttribute("data-multi") === "1") {
        var picked = TKU.$$("input:checked", wrap).map(function (n) { return n.value; });
        picked.sort();
        S.answers[uid] = picked.join("");
        TKU.$$(".paper-opt", wrap).forEach(function (lab) {
          var b = lab.querySelector("input");
          lab.classList.toggle("selected", !!(b && b.checked));
        });
      } else {
        S.answers[uid] = t.value;
        TKU.$$(".paper-opt", wrap).forEach(function (lab) {
          lab.classList.toggle("selected", !!(lab.querySelector("input") === t));
        });
      }
      updateAnswered();
    });
    box.addEventListener("input", function (ev) {
      var t = ev.target;
      if (!t || t.tagName !== "TEXTAREA") { return; }
      S.answers[t.getAttribute("data-uid") || ""] = t.value;
      updateAnswered();
    });
  }

  function setSubmitting(on) {
    var b1 = TKU.byId("btnSubmitPaper"), b2 = TKU.byId("btnSubmitPaper2");
    if (b1) { b1.disabled = !!on; b1.textContent = on ? "交卷中…" : "交卷"; }
    if (b2) { b2.disabled = !!on; b2.textContent = on ? "交卷中…" : "交卷并看成绩"; }
  }

  function submitPaper() {
    if (S.busy) { return; }
    if (!S.questions.length) {
      showError("examMsg", "还没有加载到题目，无法交卷（请先选一套卷进入考场）。");
      return;
    }
    var unanswered = countUnanswered();
    if (unanswered > 0) {
      if (!window.confirm("还有 " + unanswered + " 题没答，确定交卷？")) { return; }
    }
    S.busy = true;
    setSubmitting(true);
    clearError("examMsg");
    S.elapsedMs = Date.now() - S.started;
    stopTimer();
    var payload = {
      subject: S.subjectOfExam,
      title: (S.paper && S.paper.title) || (S.paperMeta && S.paperMeta.title) || "",
      answers: S.answers,
      elapsed_ms: S.elapsedMs
    };
    return api.post("/api/paper/submit", payload).then(function (data) {
      S.busy = false;
      setSubmitting(false);
      S.report = data;
      if (!S.elapsedMs && data && data.elapsed_ms) { S.elapsedMs = Number(data.elapsed_ms) || 0; }
      renderReport(data, S.elapsedMs);
      setView("report");
      TKU.toast("交卷完成：得分 " + fmtNum(data.score) + " / " + fmtNum(data.total_score), "ok");
      return data;
    }).catch(function (err) {
      S.busy = false;
      setSubmitting(false);
      beginTimer();                       /* 交卷失败：留在考场，计时继续（不能让用户以为停表了） */
      showError("examMsg", "交卷失败：" + err.message);
      TKU.toast("交卷失败：" + err.message, "err");
    });
  }

  /* ------------------------------------------------------------------ ③ 成绩报告 */
  function renderReport(data, elapsedMs) {
    data = data || {};
    var total = Number(data.total_score || 0);
    var score = Number(data.score || 0);
    var acc = Number(data.accuracy || 0);
    var used = (elapsedMs === undefined || elapsedMs === null) ? S.elapsedMs : Number(elapsedMs);
    var pending = Number(data.pending || 0);
    var results = data.results || [];

    var head =
      '<h1>成绩报告 · ' + TKU.esc(data.title || (S.paper && S.paper.title) || "") + '</h1>' +
      '<p class="report-score">得分 <span class="score-good">' + TKU.esc(fmtNum(score)) + '</span>' +
        ' / 满分 ' + TKU.esc(fmtNum(total)) + '</p>' +
      '<div class="kpis">' +
        kpi(String(data.correct || 0), "答对", "kpi-ok") +
        kpi(String(data.wrong || 0), "答错", "kpi-err") +
        kpi(String(pending), "待 AI 判分", "kpi-due") +
        kpi(String(data.unanswered || 0), "未作答", "") +
        kpi((Math.round(acc * 1000) / 10) + "%", "正确率", "") +
        kpi(fmtTime(used), "用时", "") +
      '</div>' +
      (pending > 0
        ? '<p class="pending-tip">⏳ 有 ' + TKU.esc(String(pending)) + ' 题需要 AI 判分（写作 / 翻译）——' +
          '可在<a href="/settings">设置页</a>配置 API key 后，到<a href="/queue">『判分队列』</a>处理。</p>'
        : '') +
      (data.note ? '<p class="muted small">' + TKU.esc(data.note) + '</p>' : '') +
      /* 如实说明"为什么报告里的题数比考卷少"：交卷接口一次最多处理 200 题 */
      ((S.questions.length > results.length && results.length > 0)
        ? '<p class="pending-tip">⚠ 本次只拿到前 ' + TKU.esc(String(results.length)) + ' 题的判分结果（考卷共 ' +
          TKU.esc(String(S.questions.length)) + ' 题，交卷接口单次最多处理 200 题）。</p>'
        : '');
    TKU.byId("reportHead").innerHTML = head;

    /* 分项表（per_type）：题型 / 题数 / 对 / 待判 / 得分 / 满分 */
    var per = data.per_type || {};
    var keys = Object.keys(per);
    TKU.byId("reportPerType").innerHTML = keys.length
      ? '<table class="data"><thead><tr><th>题型</th><th>题数</th><th>对</th><th>待判</th>' +
        '<th>得分</th><th>满分</th></tr></thead><tbody>' +
        keys.map(function (k) {
          var b = per[k] || {};
          return '<tr><td>' + TKU.esc(b.name || typeName(k)) + '</td>' +
            '<td>' + TKU.esc(String(b.count || 0)) + '</td>' +
            '<td>' + TKU.esc(String(b.correct || 0)) + '</td>' +
            '<td>' + TKU.esc(String(b.pending || 0)) + '</td>' +
            '<td>' + TKU.esc(fmtNum(b.score)) + '</td>' +
            '<td>' + TKU.esc(fmtNum(b.full)) + '</td></tr>';
        }).join("") + '</tbody></table>'
      : '<p class="muted">后端未返回分项数据。</p>';

    /* 逐题结果 */
    TKU.byId("reportListCount").textContent = results.length ? "（" + results.length + " 题）" : "";
    TKU.byId("reportList").innerHTML = results.length
      ? results.map(resultHTML).join("")
      : '<p class="muted">后端未返回逐题结果。</p>';
    clearError("reportMsg");
  }

  function kpi(num, label, cls) {
    return '<div class="kpi ' + (cls || "") + '"><span class="kpi-num">' + TKU.esc(num) +
      '</span><span class="kpi-label">' + TKU.esc(label) + '</span></div>';
  }

  /* 结果里的选项：标出「正确项」和「你选的项」，否则只有 `A、B、D` 这种字母，
     用户根本没法对照看自己错在哪（用户明确要求）。 */
  function resOptions(r) {
    var opts = r.options_parsed || [];
    if (!opts.length) { return ""; }
    var keys = String(r.answer_keys || "").toUpperCase();
    var mine = String(r.user_answer || "").toUpperCase().replace(/[^A-H]/g, "");
    var html = '<ul class="res-opts">';
    opts.forEach(function (o) {
      var k = String(o.key || "").toUpperCase();
      var isKey = keys.indexOf(k) >= 0;
      var isMine = mine.indexOf(k) >= 0;
      var cls = isKey ? " opt-correct" : (isMine ? " opt-wrong" : "");
      html += '<li class="res-opt' + cls + '"><b>' + TKU.esc(k) + '</b> ' + TKU.esc(o.text || "");
      if (isKey) { html += ' <span class="opt-tag">正确</span>'; }
      if (isMine) { html += ' <span class="opt-tag mine">你选的</span>'; }
      html += '</li>';
    });
    return html + '</ul>';
  }

  function resultHTML(r) {
    r = r || {};
    var pending = (r.status !== "synced");
    var mark = pending ? "⏳ 待判" : (r.correct ? "✅ 答对" : "❌ 答错");
    var cls = pending ? "pending" : (r.correct ? "ok" : "err");
    var my = (r.user_answer === undefined || r.user_answer === null || String(r.user_answer).trim() === "")
      ? "（未作答）" : String(r.user_answer);
    var scorePill = (r.judge_score === undefined || r.judge_score === null)
      ? '<span class="pill">满分 ' + TKU.esc(fmtNum(r.full_score)) + '</span>'
      : '<span class="pill">得分 ' + TKU.esc(fmtNum(r.judge_score)) + ' / ' + TKU.esc(fmtNum(r.full_score)) + '</span>';
    var html = '<div class="paper-res">' +
      '<p class="res-line">' +
        '<span class="res-head">第 ' + TKU.esc(String(r.seq === undefined || r.seq === null ? "?" : r.seq)) + ' 题</span>' +
        '<span class="res-mark ' + cls + '">' + mark + '</span>' +
        '<span class="pill">' + TKU.esc(r.type_name || typeName(r.question_type)) + '</span>' +
        scorePill +
        (r.judged_by ? '<span class="muted small">判分来源：' + TKU.esc(r.judged_by) + '</span>' : '') +
      '</p>';
    if (r.stem) {
      html += '<p class="res-stem">' + TKU.esc(String(r.stem)) + '</p>';
    }
    html += resOptions(r);
    html += '<p class="res-my">你的作答：' + TKU.esc(my) + '</p>';
    if (r.answer !== undefined && r.answer !== null && String(r.answer) !== "") {
      html += '<p class="res-key">正确答案：' + TKU.esc(String(r.answer)) + '</p>';
    }
    if (r.judge_reason) {
      html += '<p class="res-reason muted small">判分依据：' + TKU.esc(String(r.judge_reason)) + '</p>';
    }
    if (pending) {
      html += '<p class="pending-tip">⏳ 需要 AI 判分（写作/翻译）——可在<a href="/settings">设置页</a>' +
        '配置 API key 后到<a href="/queue">『判分队列』</a>处理。</p>';
    }
    return html + '</div>';
  }

  /* ------------------------------------------------------------------ 重做 / 换卷 */
  function redoPaper() {
    if (!S.questions.length) { TKU.toast("没有可重做的题目（请重新选一套卷）", "err"); return; }
    S.answers = {};                       /* 清空作答 */
    renderExam(S.paperMeta || {});         /* 重绘 → 选项/输入框全空 */
    setView("exam");
    resetTimer();                          /* 重新计时 */
    TKU.toast("已清空作答并重新计时", "ok");
  }

  function backToPick() {
    if (!TKU.byId("viewExam").hidden && countAnswered() > 0) {
      if (!window.confirm("放弃本次作答并返回选题？作答不会保存。")) { return; }
    }
    stopTimer();
    setView("pick");
    renderCards();
  }

  /* ------------------------------------------------------------------ 事件绑定 */
  TKU.byId("paperTabs").addEventListener("click", function (ev) {
    var btn = (ev.target && ev.target.closest) ? ev.target.closest("button[data-subject]") : null;
    if (!btn) { return; }
    S.subject = btn.getAttribute("data-subject") || S.subject;
    renderTabs();
    renderCards();
  });

  TKU.byId("paperCards").addEventListener("click", function (ev) {
    var btn = (ev.target && ev.target.closest) ? ev.target.closest("button[data-idx]") : null;
    if (!btn) { return; }
    var idx = parseInt(btn.getAttribute("data-idx"), 10);
    var list = S.groups[S.subject] || [];
    if (isNaN(idx) || idx < 0 || idx >= list.length) { return; }
    btn.disabled = true;
    startExam(list[idx]);
  });

  bindExamInputs();
  if (TKU.byId("btnSubmitPaper")) { TKU.byId("btnSubmitPaper").addEventListener("click", submitPaper); }
  if (TKU.byId("btnSubmitPaper2")) { TKU.byId("btnSubmitPaper2").addEventListener("click", submitPaper); }
  if (TKU.byId("btnBackPick")) { TKU.byId("btnBackPick").addEventListener("click", backToPick); }
  if (TKU.byId("btnRedoPaper")) { TKU.byId("btnRedoPaper").addEventListener("click", redoPaper); }
  if (TKU.byId("btnAnotherPaper")) { TKU.byId("btnAnotherPaper").addEventListener("click", function () { setView("pick"); }); }

  /* 交卷失败重试入口：错误框旁边点一下就能再交（不用重新答题） */
  TKU.byId("examMsg").addEventListener("click", function (ev) {
    if (ev.target && ev.target.tagName === "BUTTON") { submitPaper(); }
  });

  /* ------------------------------------------------------------------ 启动
     支持 /paper?subject=english&title=xxx 直接进考场（刷新不丢"我在考哪套卷"）；
     没有参数就是默认的选题视图。 */
  var initTitle = document.body.getAttribute("data-title") || "";
  var initSubject = document.body.getAttribute("data-subject") || "";
  loadList().then(function () {
    if (!initTitle) { return; }
    var list = S.groups[initSubject] || [];
    var found = null;
    for (var i = 0; i < list.length; i++) { if (list[i].title === initTitle) { found = list[i]; break; } }
    if (found) { S.subject = initSubject; renderTabs(); renderCards(); startExam(found); }
    else {
      showError("errBox", "URL 指定的套卷不存在：" + initSubject + " / " + initTitle +
        "（已回到选题视图，请从下方卡片选择）");
    }
  });

  /* 给自查 / 桩验证留的口子：可替换 api.post 后用假响应走完整交卷渲染路径 */
  window.TKU_PAPER = {
    state: S,
    api: api,
    loadList: loadList,
    renderCards: renderCards,
    startExam: startExam,
    renderExam: renderExam,
    submitPaper: submitPaper,
    setView: setView,
    redoPaper: redoPaper,
    renderReport: function (data, elapsedMs) { renderReport(data, elapsedMs); setView("report"); },
    round1: round1,
    fmtTime: fmtTime,
    typeNames: TYPE_NAMES
  };
})();
