/* 题库项目 · 刷题页（quiz.js）
   交互规范（docs/UI_DESIGN.md 第 5 节）：
   - 单选即跳：选中即提交并自动进入下一题
   - 多选手动提交：勾选后点「提交本题」
   - 答错红色闪烁 #EF4444 闪 2 次（≤400ms）
   - 提交后禁用重复提交；失败给出提示与重试
   客观题（single_choice / multiple_choice）本地即时判对错（用 reveal=1 取回的答案），
   主观题提交后进入 judge_queue(pending)，答案与解析另行展示。 */

(function () {
  "use strict";
  if (document.body.getAttribute("data-page") !== "quiz") { return; }

  var S = {
    questions: [],
    idx: 0,
    busy: false,
    started: 0,
    selected: [],
    log: [],
    typeNames: window.TKU_TYPE_NAMES || {},
    typeMeta: window.TKU_TYPE_META || {},     /* 题型说明（"这题要干嘛"） */
    showExplain: true,                        /* 需求 7：用户开关（默认开），与后端来源策略取交集 */
    lastExplain: null,                        /* 最近一次出过的解析载荷，供开关切换时就地重绘 */
    zhCache: {},                              /* uid → {material_zh, stem_zh}（英语译文，本地接口） */
    zhOn: false                               /* 当前是否展开着译文 */
  };

  var elCard = TKU.byId("quizCard");
  var elIndex = TKU.byId("qIndex");
  var elMeta = TKU.byId("qMeta");
  var elDue = TKU.byId("qDue");
  var elStem = TKU.byId("qStem");
  var elHow = TKU.byId("qHow");
  var elWords = TKU.byId("qWords");
  var elMaterial = TKU.byId("qMaterial");
  var elOptions = TKU.byId("qOptions");
  var elSubjective = TKU.byId("qSubjective");
  var elAnswer = TKU.byId("qAnswer");
  var elFeedback = TKU.byId("qFeedback");
  var elExplain = TKU.byId("qExplain");
  var elProgress = TKU.byId("qProgress");
  var elStatus = TKU.byId("qStatus");
  var elLog = TKU.byId("attemptLog");

  function typeName(key) { return S.typeNames[key] || key || "未知题型"; }

  /* 来源徽标：让用户一眼看出"这题是真题需要重点看"还是生成题/模拟题（用户明确要求） */
  var TRUST_BADGE = {
    official_exam: "✅ 真题",
    textbook: "📘 教材/校考题",
    third_party: "📗 模拟题",
    ai_generated: "🤖 生成题",
    acp: "🎓 ACP（高级）"
  };
  function trustBadge(q) {
    var t = q.trust_level || "";
    if (!t) {
      if (q.source_type === "real_exam") { t = "official_exam"; }
      else if (q.source_type === "generate") { t = "ai_generated"; }
      else if (q.source_type === "fetch") { t = "third_party"; }
    }
    var label = TRUST_BADGE[t];
    if (!label) { return ""; }
    return '<span class="pill trust-' + TKU.esc(t) + '">' + TKU.esc(label) + '</span>';
  }

  /* 需求 5：来源徽标「显示 / 隐藏」开关（默认显示，选择记在 localStorage）。
     徽标**始终**照样渲染进 meta，只是给 <body> 切一个 hide-badges 类由 CSS 隐藏，
     所以不会动既有渲染（科目/题型/难度/知识点仍照常显示）。 */
  var BADGE_KEY = "tku.showTrustBadge";

  function badgePref() {
    try {
      var v = window.localStorage.getItem(BADGE_KEY);
      return (v === null || v === undefined) ? true : v === "1";   /* 没存过 → 默认显示 */
    } catch (e) { return true; }                                   /* 读不到（隐私模式）→ 按默认 */
  }

  function applyBadgePref(show) {
    document.body.classList.toggle("hide-badges", !show);
    var box = TKU.byId("chkShowBadge");
    if (box) { box.checked = !!show; }
  }

  function saveBadgePref(show) {
    try { window.localStorage.setItem(BADGE_KEY, show ? "1" : "0"); } catch (e) { /* 存不了就只影响本次 */ }
  }

  /* ---------------------------------------------------------- 需求 7：解释显示策略
     用户原话：「刷 aca 的题目的时候，有一些题有解释这点做得很好，我希望其他也有
     （全部都有的话花费太高了，所以**只在真题显示解释**，一定确保解释的正确）」。

     口径分两层，**取交集**（任一为"不显示"就不显示解析）：
       ① 来源层：后端给的 `show_explanation`（official_exam / textbook 才是 true，
          third_party / ai_generated / acp / 来源未标注 → false）；字段缺失=旧接口 → 按 true。
       ② 用户层：题目 meta 行的「显示解释（仅真题有）」勾选框（`chkShowExplain`，
          默认勾选，状态存 localStorage `tku.showExplanation`）。取消勾选只**收紧**，
          不会把非真题的解析放出来 —— 与"来源徽标开关"（chkShowBadge）完全独立。

     ⚠️ 参考答案**永远照常显示**（做题必需品），只有解析部分受上面两层控制。 */
  var EXPLAIN_KEY = "tku.showExplanation";

  function explainPref() {
    try {
      var v = window.localStorage.getItem(EXPLAIN_KEY);
      return (v === null || v === undefined) ? true : v === "1";   /* 没存过 → 默认显示 */
    } catch (e) { return true; }                                   /* 读不到（隐私模式）→ 按默认 */
  }

  function applyExplainPref(show) {
    S.showExplain = !!show;
    var box = TKU.byId("chkShowExplain");
    if (box) { box.checked = !!show; }
  }

  function saveExplainPref(show) {
    try { window.localStorage.setItem(EXPLAIN_KEY, show ? "1" : "0"); } catch (e) { /* 忽略 */ }
  }

  /* 后端字段容错：真布尔 / "true" / 1 / 0 都认；**字段缺失返回 null** —— 调用方据此
     走"旧接口 → 照旧显示"的降级路径（后端还没上线也不许报错或白屏）。 */
  function triBool(v) {
    if (v === true || v === false) { return v; }
    if (typeof v === "string") {
      var s = v.trim().toLowerCase();
      if (s === "true" || s === "1" || s === "yes") { return true; }
      if (s === "false" || s === "0" || s === "no" || s === "") { return false; }
    }
    if (v === 1 || v === 0) { return v === 1; }
    return null;                                                   /* 认不出来 → 当缺失 */
  }

  /* 字段取值：顶层优先，其次容错地看一眼 question / meta / local_judge（后端实现细节变化也不崩） */
  function explainField(src, key) {
    src = src || {};
    var holders = [src, src.question, src.meta, src.local_judge];
    for (var i = 0; i < holders.length; i++) {
      var h = holders[i];
      if (h && typeof h === "object" && h[key] !== undefined && h[key] !== null) { return h[key]; }
    }
    return undefined;
  }

  /* 把任意接口返回（/api/reveal、/api/judge_one、/api/submit）规整成 showExplain() 认的载荷 */
  function explainPayload(src) {
    return {
      answer: explainField(src, "answer"),
      explanation: explainField(src, "explanation"),
      show_explanation: explainField(src, "show_explanation"),
      explanation_source: explainField(src, "explanation_source"),
      explanation_hidden_reason: explainField(src, "explanation_hidden_reason")
    };
  }

  /* 阅读材料**整块显示**：同一篇短文的若干小题共享 material_text，
     用户明确要求这类题"本身就是整块，不要分开"，所以材料固定显示在题目上方。 */
  function renderMaterial(q) {
    if (!elMaterial) { return; }
    var mat = q.material_text || "";
    if (!mat) { elMaterial.hidden = true; elMaterial.innerHTML = ""; return; }
    var g = q.group_uid || "";
    var sib = S.questions.filter(function (x) { return g && x.group_uid === g; });
    var pos = 0;
    for (var i = 0; i < sib.length; i++) { if (sib[i].question_uid === q.question_uid) { pos = i + 1; break; } }
    var info = sib.length > 1
      ? "📄 本组共 " + sib.length + " 题（同一篇材料），当前第 " + pos + " 题"
      : "📄 阅读材料";
    elMaterial.hidden = false;
    elMaterial.innerHTML = '<div class="material-head">' + TKU.esc(info) +
      (q.exam_title ? '<span>来源：' + TKU.esc(q.exam_title) + '</span>' : "") +
      '</div><div class="material-body">' + (isEnglish(q) ? wrapWords(mat) : TKU.esc(mat)) + '</div>';
  }

  /* ================= 英语：点词查义 + 整段译文 =================
     数据全部来自本地 sqlite（scripts/build_english_zh.py 预生成），点击不联网、不计费。 */
  var WORD_RE = /[A-Za-z][A-Za-z'-]*/g;
  var NO_WRAP_TYPES = { sentence_build: 1, program_fill: 1, programming: 1, code_correction: 1 };
  var elZh = null;
  var elDict = null;

  function isEnglish(q) {
    var s = (q && q.subject) || (document.body && document.body.dataset.subject) || "";
    return s === "english";
  }

  /* 把英文正文里的每个单词包成可点的 span（其余字符照常转义） */
  function wrapWords(text) {
    var src = String(text || "");
    var out = "";
    var last = 0;
    var m;
    WORD_RE.lastIndex = 0;
    while ((m = WORD_RE.exec(src)) !== null) {
      out += TKU.esc(src.slice(last, m.index));
      if (m[0].length >= 2) {
        out += '<span class="w" data-w="' + TKU.esc(m[0]) + '" title="点一下看释义">' + TKU.esc(m[0]) + '</span>';
      } else {
        out += TKU.esc(m[0]);
      }
      last = m.index + m[0].length;
    }
    out += TKU.esc(src.slice(last));
    /* 题干/材料里也可能带 <u> 划线标记（音标题），转义后单独放行 */
    return allowUnderline(out);
  }

  function renderZhBar(q) {
    if (!elZh) { elZh = TKU.byId("qZh"); }
    var btn = TKU.byId("btnZh");
    if (!elZh || !btn) { return; }
    var english = isEnglish(q);
    btn.hidden = !english;
    btn.textContent = "显示译文";
    elZh.hidden = true;
    elZh.innerHTML = "";
    S.zhOn = false;
    S.zhCurrent = null;
  }

  function zhSection(title, text) {
    if (!text) { return ""; }
    return '<div class="zh-part"><b>' + TKU.esc(title) + '</b><p>' + TKU.esc(text) + '</p></div>';
  }

  function toggleZh() {
    var q = current();
    var btn = TKU.byId("btnZh");
    if (!q || !elZh || !btn) { return; }
    if (S.zhOn) {
      S.zhOn = false;
      elZh.hidden = true;
      btn.textContent = "显示译文";
      return;
    }
    var paint = function (data) {
      var html = zhSection("材料译文", data.material_zh) + zhSection("题干译文", data.stem_zh);
      elZh.innerHTML = html || '<p class="muted small">这道题还没有预生成译文。</p>';
      elZh.hidden = false;
      btn.textContent = "隐藏译文";
      S.zhOn = true;
    };
    if (S.zhCache && S.zhCache[q.question_uid]) { paint(S.zhCache[q.question_uid]); return; }
    btn.disabled = true;
    TKU.getJSON("/api/translate?subject=english&uid=" + encodeURIComponent(q.question_uid))
      .then(function (data) {
        S.zhCache = S.zhCache || {};
        S.zhCache[q.question_uid] = data || {};
        paint(data || {});
      })
      .catch(function (err) {
        var hint = (err && err.status === 404)
          ? "译文接口不可用（HTTP 404）——服务还在跑旧代码，请重启「启动.bat」"
          : "译文加载失败：" + ((err && err.message) || "未知错误");
        TKU.toast(hint, "err");
      })
      .then(function () { btn.disabled = false; });
  }

  /* 点词弹小卡片：词性 + 中文释义 + 发音（浏览器内置 TTS，不花钱） */
  function dictCard() {
    if (elDict) { return elDict; }
    elDict = document.createElement("div");
    elDict.className = "dict-card";
    elDict.hidden = true;
    document.body.appendChild(elDict);
    document.addEventListener("click", function (e) {
      if (elDict.hidden) { return; }
      if (elDict.contains(e.target) || (e.target.closest && e.target.closest(".w"))) { return; }
      elDict.hidden = true;
    }, true);
    return elDict;
  }

  function showDict(word, ev) {
    var card = dictCard();
    card.hidden = false;
    card.innerHTML = '<div class="dict-head"><b>' + TKU.esc(word) + '</b>' +
      '<span class="dict-tts" title="朗读">🔊</span></div><div class="dict-body">查询中…</div>';
    var rect = (ev && ev.target) ? ev.target.getBoundingClientRect() : { left: 100, top: 100, bottom: 120 };
    card.style.left = Math.max(8, Math.min(window.innerWidth - 280, rect.left + window.scrollX - 10)) + "px";
    card.style.top = (rect.bottom + window.scrollY + 6) + "px";
    card.querySelector(".dict-tts").addEventListener("click", function () { speak(word); });

    TKU.getJSON("/api/dict?w=" + encodeURIComponent(word))
      .then(function (d) {
        if (!d || !d.found) {
          card.querySelector(".dict-body").innerHTML =
            '<span class="muted small">词表里没收录这个单词（' + TKU.esc(word) + '）</span>';
          return;
        }
        card.querySelector(".dict-body").innerHTML =
          '<span class="dict-pos">' + TKU.esc(d.pos || "") + '</span> ' + TKU.esc(d.zh || "");
      })
      .catch(function (err) {
        var hint = (err && err.status === 404)
          ? "翻译接口不可用（HTTP 404）——服务还在跑旧代码，请关掉控制台重新双击「启动.bat」"
          : "查询失败：" + ((err && err.message) || "未知错误");
        card.querySelector(".dict-body").innerHTML = '<span class="muted small">' + TKU.esc(hint) + '</span>';
      });
  }

  function speak(word) {
    try {
      if (!window.speechSynthesis) { return; }
      window.speechSynthesis.cancel();
      var u = new SpeechSynthesisUtterance(word);
      u.lang = "en-US";
      u.rate = 0.9;
      window.speechSynthesis.speak(u);
    } catch (e) { /* 浏览器不支持就算了，不影响查义 */ }
  }

  /* 「这题要干嘛」：每题都显示该题型的作答指引（用户反馈连词成句看不懂要干什么） */
  var READ_QA_NOTE = "本大题含两部分：根据文章作答的简答题 + 句子英译汉。" +
    "简答题请用英文完整句子作答；翻译题按中文习惯译出即可。";

  function renderHow(q) {
    if (!elHow) { return; }
    /* 题型说明以题目自带 how 优先，其次用 /api/questions 附带的题型目录（type_meta） */
    var how = q.how || ((S.typeMeta || {})[q.question_type] || {}).how || "";
    /* 需求 11：湖北专升本 2024+ 的 Part IV 就叫「阅读理解」，但卷面同时含简短问答与英译汉，
       用户问过"这不是翻译吗" —— 在作答说明里写清两部分（纯前端兜底，不动后端/数据库）。 */
    if (q.question_type === "reading_qa") {
      how = how ? (how + " " + READ_QA_NOTE) : READ_QA_NOTE;
    }
    elHow.hidden = !how;
    /* config/display.json 的题型说明里用 `**加粗**` 强调重点；这里先转义再还原成 <b>，
       否则星号会原样显示（用户看到的是「选出**唯一正确**的答案」）。 */
    elHow.innerHTML = how ? "📌 " + TKU.esc(how).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>") : "";
  }

  /* 连词成句：源站把单词用**逗号/分号/斜杠**连成一串（`the, are, preparing, …` + 一长串下划线），
     既不符合英语书写规范、也看不出要干什么。这里把分隔符拆掉，渲染成**词卡**。
     ⚠️ 曾经的坑（用户反馈"有的题点不了、只能选中文字"）：
        ① 只认 `,，/`，不认 `;；`；② 单个词块超过 26 字符就整个放弃（如
        `"Made in China 2025"`、`China's technology industries`）→ 退回纯文本，词卡没了。
     现在放宽到 40 字符，并额外认 `;；`；仍拆不出就按空格兜底。 */
  function splitWords(stem) {
    if (!stem) { return null; }
    var s = String(stem).replace(/_{2,}/g, " ").replace(/[，,、;；\s]+$/, "").trim();
    if (!s || s.length > 320) { return null; }
    var parts = s.split(/[,，/／;；]/).map(function (p) {
      return p.replace(/[（(][^）)]{1,6}[）)]$/, "").replace(/^[.\s]+|[.\s]+$/g, "").trim();
    }).filter(Boolean);
    /* 兜底：分隔符没拆出 2 块以上时按空格拆（有些源站直接给了乱序单词串） */
    if (parts.length < 2) {
      parts = s.split(/\s+/).filter(Boolean);
    }
    if (parts.length < 2 || parts.length > 30) { return null; }
    for (var i = 0; i < parts.length; i++) { if (parts[i].length > 40) { return null; } }
    return parts;
  }

  /* 用题干做种子的确定性洗牌：同一个题每次打开词卡顺序都一样（不会"这次能拼下次乱"），
     但**保证不是答案顺序** —— 用户反馈"有的题根本没打乱，照着念就行"。 */
  function seededShuffle(arr, seedText) {
    var seed = 2166136261;
    var s = String(seedText || "");
    for (var i = 0; i < s.length; i++) {
      seed ^= s.charCodeAt(i);
      seed = (seed * 16777619) >>> 0;
    }
    var out = arr.slice();
    for (var j = out.length - 1; j > 0; j--) {
      seed = (seed * 1103515245 + 12345) >>> 0;
      var k = seed % (j + 1);
      var t = out[j]; out[j] = out[k]; out[k] = t;
    }
    return out;
  }

  function renderStem(q) {
    var words = (q.question_type === "sentence_build") ? splitWords(q.stem) : null;
    if (words) { words = seededShuffle(words, q.question_uid || q.stem); }
    if (!words) {
      if (elWords) { elWords.hidden = true; elWords.innerHTML = ""; }
      elStem.hidden = false;
      /* 英语题干也做成可点词：只在散文类题型上包词，代码/词块类保持纯文本 */
      if (isEnglish(q) && !NO_WRAP_TYPES[q.question_type]) {
        elStem.innerHTML = wrapWords(q.stem || "(题干为空)");
      } else {
        elStem.textContent = q.stem || "(题干为空)";
      }
      return;
    }
    elStem.hidden = true;
    elWords.hidden = false;
    // ⑤ **点击词块直接放进作答框**（用户要求：不用每个单词都手打），同时保留键盘输入
    elWords.innerHTML = words.map(function (w) {
      return '<span class="chip" role="button" tabindex="0" data-w="' + TKU.esc(w) + '">' + TKU.esc(w) + '</span>';
    }).join("") + '<span class="blank">↑ 点词块自动填入作答框（也可以直接手打）· 注意首字母大写与句末标点</span>';
    elWords.onclick = function (ev) {
      var chip = ev.target && ev.target.closest ? ev.target.closest(".chip") : null;
      if (!chip) { return; }
      insertWord(chip.getAttribute("data-w") || "");
      chip.classList.add("used");
    };
    elWords.onkeydown = function (ev) {
      if (ev.key !== "Enter" && ev.key !== " ") { return; }
      var chip = ev.target && ev.target.closest ? ev.target.closest(".chip") : null;
      if (!chip) { return; }
      ev.preventDefault();
      insertWord(chip.getAttribute("data-w") || "");
      chip.classList.add("used");
    };
  }

  /* 把单词接到作答框末尾（自动补空格；光标落到末尾，可继续手打或再点词块） */
  function insertWord(w) {
    if (!w) { return; }
    if (elSubjective.hidden) { return; }
    var cur = elAnswer.value || "";
    var needSpace = cur.length > 0 && !/[\s]$/.test(cur);
    elAnswer.value = cur + (needSpace ? " " : "") + w;
    try {
      elAnswer.focus();
      elAnswer.setSelectionRange(elAnswer.value.length, elAnswer.value.length);
    } catch (e) { /* 忽略 */ }
  }

  /* 需求 4：每次打开/刷新都要换一批题。服务端 shuffle=1 已经是 ORDER BY RANDOM()，
     但固定 limit=50 时题库几千题也只会反复看到"随机的那 50 道"，
     所以把 limit 每次随机在 50–120 之间（服务端 MAX_PAGE_LIMIT=500，不越界、不加后端参数）。 */
  function randomLimit() {
    return 50 + Math.floor(Math.random() * 71);   /* 50 ~ 120（含两端） */
  }

  function query() {
    var d = document.body.dataset;
    // shuffle=1：用户要求"每次打开可以随机"，否则永远从第一题开始
    // limit 每次随机：让每次打开/刷新（含筛选重新拉取、"再来一轮"）取到的题更分散
    var parts = ["limit=" + randomLimit(), "reveal=1", "shuffle=1"];
    if (d.subject) { parts.push("subject=" + encodeURIComponent(d.subject)); }
    if (d.type) { parts.push("type=" + encodeURIComponent(d.type)); }
    if (d.difficulty) { parts.push("difficulty=" + encodeURIComponent(d.difficulty)); }
    if (d.status) { parts.push("status=" + encodeURIComponent(d.status)); }
    if (d.trust) { parts.push("trust=" + encodeURIComponent(d.trust)); }
    if (d.kp) { parts.push("kp=" + encodeURIComponent(d.kp)); }
    /* 首页「模拟题」卡片进来时带 exam=考试宝预览：只出那份题库的题 */
    if (d.exam) { parts.push("exam=" + encodeURIComponent(d.exam)); }
    /* 判分记录页「刷错题」进来时带 wrong=1：只出判分记录里判错的题 */
    if (d.wrong) { parts.push("wrong=1"); }
    return "/api/questions?" + parts.join("&");
  }

  function load() {
    elStatus.textContent = "加载题目…";
    TKU.getJSON(query()).then(function (data) {
      S.questions = data.questions || [];
      S.idx = 0;
      elStatus.textContent = "共 " + S.questions.length + " 题";
      render();
    }).catch(function (err) {
      elStem.textContent = "题目加载失败：" + err.message;
      elStatus.textContent = "加载失败";
      TKU.toast("题目加载失败：" + err.message, "err");
    });
  }

  function current() { return S.questions[S.idx]; }

  function render() {
    var q = current();
    elFeedback.hidden = true;
    elFeedback.className = "feedback";
    elExplain.hidden = true;
    elExplain.className = "explain";
    elExplain.textContent = "";
    S.lastExplain = null;            /* 换题了，上一题的解析载荷作废 */
    elOptions.innerHTML = "";
    elSubjective.hidden = true;
    S.selected = [];
    S.started = Date.now();

    if (!q) {
      elIndex.textContent = "—";
      elMeta.textContent = "已完成";
      elStem.textContent = "没有符合条件的题目。可调整上方筛选条件，或先导入 / 生成题目。";
      elProgress.textContent = "";
      elStatus.textContent = "无题";
      return;
    }

    elIndex.textContent = "第 " + (S.idx + 1) + " / " + S.questions.length + " 题";
    // 来源徽标（用户要求：真题/模拟题/生成题一眼可辨，好知道哪些要重点看）
    // 每项包一层 .meta-item，分隔符由 CSS ::before 生成：这样徽标被 hide-badges 隐藏时，
    // 连它自带的分隔符一起消失，meta 行不会留下多余的「·」。
    var srcBadge = trustBadge(q);
    elMeta.innerHTML = [
      ["", TKU.esc(q.subject)],
      ["", TKU.esc(typeName(q.question_type))],
      [" src-badge", srcBadge],                       /* 开关按 .src-badge 隐藏（需求 5） */
      ["", TKU.esc(q.difficulty || "难度未标")],
      ["", q.knowledge_point ? "知识点：" + TKU.esc(q.knowledge_point) : ""]
    ].filter(function (b) { return !!b[1]; }).map(function (b) {
      return '<span class="meta-item' + b[0] + '">' + b[1] + '</span>';
    }).join("");
    // 「上一题」按钮：答错的题要能回头查看（用户要求）
    var btnPrev = TKU.byId("btnPrev");
    if (btnPrev) { btnPrev.disabled = S.idx <= 0; }
    elDue.hidden = !q.due;
    if (q.due) { elDue.textContent = "待复习（错 " + (q.wrong_count || 0) + " 次）"; }
    renderMaterial(q);
    renderHow(q);
    renderStem(q);
    renderZhBar(q);
    S.awaitingNext = false;          /* ③ 新题开始时不允许"回车下一题" */
    updateProgress();
    renderWrongList();               /* 需求 3：切题/重做/跳回后同步「本轮错题」 */

    /* 用后端算好的 `objective`（=有选项且答案能解析成字母）决定渲染方式。
       ⚠️ 曾经写死 `question_type === "single_choice"`，结果 phonetics / cloze /
       translation_choice / reading_qa 这些**有选项**的题被渲染成文本框，用户看到
       「比较划线部分读音…」却连单词都没有。 */
    if (q.objective) {
      if ((q.answer_keys || "").length > 1) { renderMultiple(q); }
      else { renderSingle(q); }
    } else {
      renderSubjective(q);
    }
  }

  function optionNode(q, opt, isMulti) {
    var tag = isMulti ? "label" : "button";
    var node = document.createElement(tag);
    node.className = "opt";
    node.setAttribute("data-key", opt.key);
    if (!isMulti) {
      node.type = "button";
    } else {
      var box = document.createElement("input");
      box.type = "checkbox";
      box.value = opt.key;
      node.appendChild(box);
    }
    var key = document.createElement("span");
    key.className = "opt-key";
    key.textContent = opt.key;
    node.appendChild(key);
    var text = document.createElement("span");
    text.className = "opt-text";
    /* 音标题的选项里带 `<u>ow</u>` 这种「划线部分」标记（源站就是这么存的），
       直接用 textContent 会把标签当文字显示成 `b<u>ow</u>l`。
       这里先转义再只还原 <u>/</u> 两个标签（其余标签一律不还原，避免 XSS）。 */
    text.innerHTML = allowUnderline(TKU.esc(opt.text || ""));
    node.appendChild(text);
    return node;
  }

  /* 只放行 <u> 与 </u>：题库里的「划线部分」标记用的是它们 */
  function allowUnderline(escapedHtml) {
    return String(escapedHtml || "")
      .replace(/&lt;u&gt;/gi, "<u>")
      .replace(/&lt;\/u&gt;/gi, "</u>");
  }

  function renderSingle(q) {
    (q.options_parsed || []).forEach(function (opt) {
      var node = optionNode(q, opt, false);
      node.addEventListener("click", function () {
        if (S.busy) { return; }
        S.selected = [opt.key];
        TKU.$$(".opt", elOptions).forEach(function (n) { n.classList.remove("selected"); });
        node.classList.add("selected");
        submit(q, opt.key, { autoAdvance: true });
      });
      elOptions.appendChild(node);
    });
    if (!(q.options_parsed || []).length) {
      elOptions.innerHTML = '<p class="muted">该题没有选项数据（options 为空）。</p>';
    }
  }

  function renderMultiple(q) {
    (q.options_parsed || []).forEach(function (opt) {
      var node = optionNode(q, opt, true);
      node.addEventListener("change", function (ev) {
        var val = ev.target.value;
        var i = S.selected.indexOf(val);
        if (ev.target.checked && i < 0) { S.selected.push(val); }
        if (!ev.target.checked && i >= 0) { S.selected.splice(i, 1); }
        node.classList.toggle("selected", ev.target.checked);
      });
      elOptions.appendChild(node);
    });
    var row = document.createElement("p");
    row.className = "row";
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "btn btn-primary btn-wide";
    btn.textContent = "提交本题";
    btn.addEventListener("click", function () {
      if (!S.selected.length) { TKU.toast("请先勾选至少一个选项", "err"); return; }
      submit(q, S.selected.slice().sort().join(""), { autoAdvance: false });
    });
    row.appendChild(btn);
    elOptions.appendChild(row);
  }

  function renderSubjective(q) {
    elSubjective.hidden = false;
    elAnswer.value = "";
    elAnswer.disabled = false;
    var btn = TKU.byId("btnSubmitText");
    btn.disabled = false;
    // ① 自动聚焦：做 20 道主观题就省掉 20 次"先用鼠标点一下输入框"
    window.setTimeout(function () {
      try { elAnswer.focus(); } catch (e) { /* 忽略 */ }
    }, 30);
  }

  // ④ 进度：位置感（第几题 / 共几题 + 进度条）
  function updateProgress() {
    var n = S.questions.length;
    var fill = TKU.byId("qProgBarFill");
    if (fill) { fill.style.width = (n ? Math.round(100 * (S.idx + 1) / n) : 0) + "%"; }
    elProgress.textContent = "已提交 " + S.log.length + " 题" + (n ? "（进度 " + (S.idx + 1) + "/" + n + "）" : "");
  }

  function disableOptions() {
    TKU.$$(".opt", elOptions).forEach(function (n) {
      n.classList.add("disabled");
      n.disabled = true;
      var box = n.querySelector("input");
      if (box) { box.disabled = true; }
    });
    TKU.$$("button", elOptions).forEach(function (b) { b.disabled = true; });
    elAnswer.disabled = true;
    var btn = TKU.byId("btnSubmitText");
    if (btn) { btn.disabled = true; }
  }

  function retryButton(q, userAnswer, opts) {
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "btn btn-small";
    btn.textContent = "重试提交";
    btn.addEventListener("click", function () {
      btn.disabled = true;
      submit(q, userAnswer, opts);
    });
    return btn;
  }

  function submit(q, userAnswer, opts) {
    if (S.busy) { return; }
    S.busy = true;
    var elapsed = Date.now() - S.started;
    TKU.postJSON("/api/submit", {
      question_uid: q.question_uid,
      subject: q.subject,
      user_answer: userAnswer,
      elapsed_ms: elapsed
    }).then(function (data) {
      S.busy = false;
      var localCorrect = null;
      // 需求 2：有明确答案的题**由服务端规则判分**，当场出分，不花 AI 的钱。
      // 服务端已在 /api/submit 里就地判分（`local_judge.gradeable`），这里直接用它的结论，
      // 避免前端再各写一套判分口径（以前 `q.objective` 那套只在浏览器里算，答错也进不了库）。
      if (data.local_judge && data.local_judge.gradeable) {
        localCorrect = !!data.correct;
        paintServer(q, userAnswer, data);
      } else {
        disableOptions();
        // 主观题（写作/整段翻译）才走 AI 判分，保持原行为
        showFeedback("pending", "AI 判分中…（通常几秒）");
        judgeLocalAndFallback(q, data.attempt_id, true, userAnswer);
      }
      pushLog(q, userAnswer, data.status || "pending");
      /* 需求 3：错题列表要靠下标定位（S.questions 里可能有同 uid 重复），所以在 log 里存下 idx */
      S.log.push({ question_uid: q.question_uid, correct: localCorrect, idx: S.idx });
      updateProgress();
      renderWrongList();                /* 答错当场出现在「本轮错题」里 */
      if (opts && opts.autoAdvance && localCorrect === true) {
        setTimeout(next, 900);        /* 单选即跳 */
      }
      // 用户要求：**答错停留**（让用户看清错在哪），答对才自动跳
      if (opts && opts.autoAdvance && localCorrect === false) {
        // 需求 7：解析未必显示（非真题 / 用户关了开关），所以这里只说"看答案"，不承诺有解析
        elStatus.textContent = "答错了 —— 看清参考答案再点「下一题」";
      }
      if (data.warning) { TKU.toast(data.warning, "err"); }
    }).catch(function (err) {
      S.busy = false;
      showFeedback("err", "提交失败：" + err.message + " ");
      var retry = retryButton(q, userAnswer, opts);
      elFeedback.appendChild(retry);
      elStatus.textContent = "提交失败";
    });
  }

  /* 规则判分出分后的展示（含正确答案与解析）。`data` 是 /api/submit 或 /api/judge_local 的返回 */
  function paintServer(q, userAnswer, data) {
    disableOptions();
    var score = data.judge_score;
    var head = (data.correct ? "✔ 正确" : "✘ 错误") + "　得分 " +
      (score != null ? score : "—") + " / " + (data.full_score != null ? data.full_score : "—") +
      "　（规则判分，本地即时）";
    showFeedback(data.correct ? "ok" : "err", head);
    if (!data.correct) { TKU.flashWrong(elCard); elStatus.textContent = "答错（可加入 SM-2 复习）"; }
    if (data.judge_reason) {
      var p = document.createElement("p");
      p.className = "muted small";
      p.textContent = "判分依据：" + data.judge_reason;
      elFeedback.appendChild(p);
    }
    // 客观题把正确选项/错选项标出来
    var keys = String(q.answer_keys || "");
    if (keys) {
      TKU.$$(".opt", elOptions).forEach(function (node) {
        var key = node.getAttribute("data-key");
        if (keys.indexOf(key) >= 0) { node.classList.add("correct"); }
        else if (String(userAnswer).indexOf(key) >= 0) { node.classList.add("wrong"); }
      });
    }
    // 规则判分不带答案/解析 → 单题拉一次 /api/reveal（只读、零成本）
    // 需求 7：连 `show_explanation` / `explanation_source` / `explanation_hidden_reason`
    // 一起交给 showExplain()；旧接口没有这三个字段时它会按"照旧显示"降级。
    TKU.getJSON("/api/reveal?subject=" + encodeURIComponent(q.subject) +
                "&question_uid=" + encodeURIComponent(q.question_uid)).then(function (r) {
      showExplain(explainPayload(r));
    }).catch(function () { /* 拉不到解析不影响判分 */ });
    addNextButton();
  }

  /* 先问本地规则判分；`allowAi` 为真且本地判不了时才走付费 AI 通道 */
  function judgeLocalAndFallback(q, attemptId, allowAi, userAnswer) {
    if (!attemptId) { afterJudged(q, null); return; }
    TKU.postJSON("/api/judge_local", { attempt_id: attemptId }).then(function (r) {
      var item = (r && r.results && r.results[0]) || {};
      if (item.gradeable && item.judge_score != null) {
        paintServer(q, userAnswer || "", item);
        afterJudged(q, !!item.correct);
        return;
      }
      if (allowAi) { judgeOne(q, attemptId); }
      else {
        showFeedback("pending", "已提交，判分未完成（可稍后在「判分记录」查看）");
        afterJudged(q, null);
      }
    }).catch(function () {
      if (allowAi) { judgeOne(q, attemptId); }
      else { afterJudged(q, null); }
    });
  }

  /* 单题即时判分：调用 /api/judge_one（真实付费 API，闸门在服务端） */
  function judgeOne(q, attemptId) {
    if (!attemptId) { afterJudged(q, null); return; }
    var t0 = Date.now();
    TKU.postJSON("/api/judge_one", { attempt_id: attemptId, confirm_paid: true }).then(function (r) {
      var secs = ((Date.now() - t0) / 1000).toFixed(1);
      var score = r.judge_score;
      if (score === null || score === undefined) {
        showFeedback("pending", "已提交，判分未完成（可稍后在「判分记录」查看）");
        afterJudged(q, null);
        return;
      }
      var head = (r.correct ? "✔ 正确" : "✘ 错误") + "　得分 " + score + " / " + (r.full_score != null ? r.full_score : "—")
        + "　（" + (r.type_name || "") + " · " + secs + "s）";
      showFeedback(r.correct ? "ok" : "err", head);
      if (!r.correct) { TKU.flashWrong(elCard); }
      if (r.judge_reason) {
        var p = document.createElement("p");
        p.className = "muted small";
        p.textContent = "判分理由：" + r.judge_reason;
        elFeedback.appendChild(p);
      }
      // 需求 7：付费 AI 判分的返回同样带三个新字段 → 走同一套策略（旧接口缺字段则照旧显示）
      if (r.answer || r.explanation) { showExplain(explainPayload(r)); }
      afterJudged(q, !!r.correct);
    }).catch(function (err) {
      showFeedback("err", "即时判分失败：" + err.message + "（作答已保存，可在「判分记录」查看）");
      afterJudged(q, null);
    });
  }

  /* 判分结束后：更新战果、显示「下一题」、允许回车进入下一题 */
  function afterJudged(q, correct) {
    var last = S.log[S.log.length - 1];
    if (last && last.question_uid === q.question_uid && correct !== null) { last.correct = correct; }
    renderWrongList();              /* 需求 3：AI 判分出结果后再同步一次错题列表 */
    S.awaitingNext = true;          /* ③ 现在按回车就能下一题 */
    addNextButton();
    elStatus.textContent = "就绪";
  }

  /* 解释展示（需求 7）。四种情形：
       - 有解释且 `show_explanation === true` → "参考答案：… 解析（来源）：…"；
       - 有解释但 `show_explanation === false` → 参考答案照常显示，解析换成一行浅色小字
         「解析已隐藏（来源：…，原因…）」；
       - **本来就没有解释** → **一个字都不提解析**（只显示参考答案）。
         ⚠️ 不能显示"已隐藏"：题库里 692 条英语第三方题根本没解析，说"已隐藏"等于告诉用户
         "我们藏了东西"，是误导（后端报告的实际问题）。
       - 字段缺失（旧接口）→ 按 true 处理，绝不报错/白屏（优雅降级）。
     另外用户取消「显示解释（仅真题有）」后，即便是真题也只显示参考答案。 */
  function showExplain(q) {
    q = explainPayload(q);
    if (!q.explanation && !q.answer) { return; }        /* 与改动前的早退条件一致 */
    S.lastExplain = q;                                   /* 记住最近一份，开关切换时就地重绘 */
    var src = String(q.explanation_source || "");
    var reason = String(q.explanation_hidden_reason || "");
    var flag = triBool(q.show_explanation);
    var bySource = (flag === null) ? true : flag;        /* 缺失 → 旧接口，照旧显示 */
    var byUser = (S.showExplain !== false);
    var hasExpl = !!(q.explanation && String(q.explanation).trim());
    var showExp = hasExpl && bySource && byUser;

    var text = "参考答案：" + (q.answer || "—");
    if (showExp) {
      text += "\n\n" + "解析" + (src ? "（" + src + "）" : "") + "：" + q.explanation;
    } else if (hasExpl) {
      var why = reason || (bySource ? "已在题目上方取消勾选「显示解释（仅真题有）」"
                                    : "非真题 —— 解释可能不可靠");
      text += "\n\n" + "解析已隐藏（来源：" + (src || "来源未标注") + "，" + why + "）";
    }
    /* 没有解释的题：text 就只有"参考答案：…"，不再画蛇添足 */
    elExplain.hidden = false;
    elExplain.className = showExp ? "explain" : "explain explain-hidden";
    elExplain.textContent = text;
  }

  function showFeedback(kind, text) {
    elFeedback.hidden = false;
    elFeedback.className = "feedback " + kind;
    elFeedback.textContent = text;
  }

  function addNextButton() {
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "btn btn-primary btn-wide";
    btn.textContent = "下一题";
    btn.addEventListener("click", next);
    var row = document.createElement("p");
    row.className = "row";
    row.appendChild(btn);
    elFeedback.appendChild(row);
  }

  function next() {
    if (S.idx + 1 < S.questions.length) {
      S.idx += 1;
      render();
    } else {
      elStem.textContent = "本轮题目已答完。";
      elOptions.innerHTML = "";
      elSubjective.hidden = true;
      elFeedback.hidden = true;
      elExplain.hidden = true;
      elIndex.textContent = "—";
      elStatus.textContent = "本轮结束";
      var fill = TKU.byId("qProgBarFill");
      if (fill) { fill.style.width = "100%"; }
      TKU.toast("本轮完成，共提交 " + S.log.length + " 题", "ok");
      showRoundSummary();          /* ⑥ 累了要能看到战果 */
    }
  }

  /* ⑥ 战果卡：做了几题 / 对几道 / 错几道 / 正确率 + 一键重做错题 */
  function showRoundSummary() {
    var box = TKU.byId("roundSummary");
    var body = TKU.byId("roundSummaryBody");
    if (!box || !body) { return; }
    var judged = S.log.filter(function (x) { return x.correct === true || x.correct === false; });
    var right = judged.filter(function (x) { return x.correct; }).length;
    var wrong = judged.length - right;
    var rate = judged.length ? Math.round(100 * right / judged.length) : 0;
    var pending = S.log.length - judged.length;
    body.innerHTML =
      '<p class="score-big">做了 ' + S.log.length + ' 题：<span class="ok">对 ' + right +
      '</span>　<span class="bad">错 ' + wrong + '</span>' +
      (judged.length ? '　正确率 ' + rate + '%' : '') +
      (pending ? '　<span class="muted">（' + pending + ' 题未判出分）</span>' : '') + '</p>' +
      (wrong ? '<p class="muted small">错题可在下方一键重做；长期复习请看 <a href="/history">判分记录</a>。</p>'
             : '<p class="muted small">全对，漂亮。</p>');
    box.hidden = false;
    box.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function redoWrong() {
    var wrongUids = {};
    var n = 0;
    S.log.forEach(function (x) {
      if (x.correct === false) { wrongUids[x.question_uid] = true; n += 1; }
    });
    if (!n) { TKU.toast("本轮没有错题", "ok"); return; }
    var keep = S.questions.filter(function (q) { return wrongUids[q.question_uid]; });
    if (!keep.length) { TKU.toast("错题已不在本轮题目里", "err"); return; }
    S.questions = keep;
    S.idx = 0;
    S.log = [];
    elLog.innerHTML = '<tr><td colspan="5" class="muted">尚无</td></tr>';
    var box = TKU.byId("roundSummary");
    if (box) { box.hidden = true; }
    render();
    TKU.toast("开始重做 " + keep.length + " 道错题", "ok");
  }

  /* ---------------------------------------------------------- 需求 3：本轮错题列表
     用户原话"页面没有返回上一题的操作，我无法回头查看我答错的题目"：
     「← 上一题」只能一题一题退，错题一多就找不到，所以这里直接列出本轮错题并支持一键跳回。
     定位方式：S.log 每条里存了当时的 S.idx（同 uid 重复也不怕），跳回只改 S.idx 再 render()，
     完全复用既有渲染与「← 上一题 / 答对才自动跳、答错停留」的行为。 */
  var elWrongList = TKU.byId("wrongList");

  /* 题干前 N 字（做列表摘要用；TKU.esc 在渲染时再做转义） */
  function briefStem(stem, n) {
    var s = String(stem || "").replace(/\s+/g, " ").trim();
    if (!s) { return "(题干为空)"; }
    return s.length > n ? s.slice(0, n) + "…" : s;
  }

  /* 按 log 里"最后一次作答结果"统计：跳回去改对了会自动从列表消失，重复作答也不会出现重复行 */
  function wrongEntries() {
    var last = {}, seen = [];
    S.log.forEach(function (x) {
      var i = (typeof x.idx === "number") ? x.idx : -1;
      if (i < 0 || i >= S.questions.length) { return; }
      if (!Object.prototype.hasOwnProperty.call(last, i)) { seen.push(i); }
      last[i] = x.correct;
    });
    return seen.filter(function (i) { return last[i] === false; })
               .sort(function (a, b) { return a - b; })
               .map(function (i) { return { idx: i, q: S.questions[i] || {} }; });
  }

  function renderWrongList() {
    if (!elWrongList) { return; }
    var items = wrongEntries();
    var cnt = TKU.byId("wrongListCount");
    if (cnt) { cnt.textContent = items.length ? "（" + items.length + " 题）" : ""; }
    if (!items.length) {
      elWrongList.innerHTML = '<li class="muted small">本轮暂无错题</li>';
      return;
    }
    elWrongList.innerHTML = items.map(function (it) {
      return '<li><span class="wrong-no">第 ' + (it.idx + 1) + ' 题</span>' +
        '<span class="muted small">' + TKU.esc(typeName(it.q.question_type)) + '</span>' +
        '<span class="wrong-stem">' + TKU.esc(briefStem(it.q.stem, 30)) + '</span>' +
        '<button class="btn btn-small" type="button" data-idx="' + it.idx + '">跳回</button></li>';
    }).join("");
  }

  function pushLog(q, userAnswer, status) {
    if (S.log.length === 0) { elLog.innerHTML = ""; }
    var tr = document.createElement("tr");
    tr.innerHTML = "<td class=\"mono small\">" + TKU.esc(q.question_uid) + "</td>" +
      "<td class=\"small\">" + TKU.esc(q.subject) + "</td>" +
      "<td class=\"answer-cell\">" + TKU.esc(userAnswer) + "</td>" +
      "<td>" + TKU.badge(status) + "</td>" +
      "<td class=\"small muted\">" + new Date().toLocaleTimeString() + "</td>";
    elLog.insertBefore(tr, elLog.firstChild);
  }

  /* ---------------------------------------------------------- 事件绑定 */
  var btnSubmitText = TKU.byId("btnSubmitText");
  if (btnSubmitText) {
    btnSubmitText.addEventListener("click", function () {
      var q = current();
      if (!q) { return; }
      var text = (elAnswer.value || "").trim();
      if (!text) { TKU.toast("请先作答再提交", "err"); return; }
      submit(q, text, { autoAdvance: false });
    });
  }
  var btnSkip = TKU.byId("btnSkip");
  if (btnSkip) { btnSkip.addEventListener("click", next); }

  /* 英语：整段译文开关 + 点词查义（数据本地读，零成本） */
  var btnZh = TKU.byId("btnZh");
  if (btnZh) { btnZh.addEventListener("click", toggleZh); }
  document.addEventListener("click", function (e) {
    var t = e.target && e.target.closest ? e.target.closest(".w") : null;
    if (!t) { return; }
    e.preventDefault();
    showDict(t.getAttribute("data-w") || t.textContent, e);
  });
  // 「上一题」：用户要求能回头查看（尤其答错的题）
  var btnPrev = TKU.byId("btnPrev");
  if (btnPrev) {
    btnPrev.addEventListener("click", function () {
      if (S.idx > 0) { S.idx -= 1; render(); }
    });
  }
  var btnRedo = TKU.byId("btnRedoWrong");
  if (btnRedo) { btnRedo.addEventListener("click", redoWrong); }
  var btnNew = TKU.byId("btnNewRound");
  if (btnNew) { btnNew.addEventListener("click", function () { location.reload(); }); }

  /* 需求 5：来源徽标开关（勾选=显示徽标；取消勾选只是隐藏徽标，其余 meta 照旧） */
  var chkBadge = TKU.byId("chkShowBadge");
  if (chkBadge) {
    chkBadge.addEventListener("change", function () {
      applyBadgePref(chkBadge.checked);
      saveBadgePref(chkBadge.checked);
    });
  }
  applyBadgePref(badgePref());          /* 打开页面就沿用上次的选择（首次默认勾选） */

  /* 需求 7：解释显示开关（勾选=显示解析；取消勾选**只留参考答案**，真题也不展开）。
     与上面的来源徽标开关互不影响：键不同（tku.showExplanation）、元素不同（chkShowExplain）。 */
  var chkExplain = TKU.byId("chkShowExplain");
  if (chkExplain) {
    chkExplain.addEventListener("change", function () {
      applyExplainPref(chkExplain.checked);
      saveExplainPref(chkExplain.checked);
      // 当前这题已经出过解析 → 当场重绘，不必重新提交一次
      if (S.lastExplain) { showExplain(S.lastExplain); }
      else { elExplain.hidden = true; elExplain.className = "explain"; elExplain.textContent = ""; }
    });
  }
  applyExplainPref(explainPref());      /* 打开页面就沿用上次的选择（首次默认勾选） */

  /* 需求 3：「跳回」——只改下标再 render()，复用既有渲染 */
  if (elWrongList) {
    elWrongList.addEventListener("click", function (ev) {
      var btn = (ev.target && ev.target.closest) ? ev.target.closest("button[data-idx]") : null;
      if (!btn) { return; }
      var i = parseInt(btn.getAttribute("data-idx"), 10);
      if (isNaN(i) || i < 0 || i >= S.questions.length) { return; }
      S.idx = i;
      render();
      if (elCard && elCard.scrollIntoView) { elCard.scrollIntoView({ behavior: "smooth", block: "nearest" }); }
    });
  }

  // ② 在输入框里 **Ctrl+Enter 提交**（普通回车保留换行，避免写作时误提交）
  if (elAnswer) {
    elAnswer.addEventListener("keydown", function (ev) {
      if (ev.key === "Enter" && (ev.ctrlKey || ev.metaKey)) {
        ev.preventDefault();
        var b = TKU.byId("btnSubmitText");
        if (b && !b.disabled) { b.click(); }
      }
    });
  }

  document.addEventListener("keydown", function (ev) {
    // ③ 判分完成后，回车直接下一题（这是刷题时最想要的那个键）
    if (ev.key === "Enter" && S.awaitingNext &&
        !/^(INPUT|TEXTAREA|SELECT)$/.test(ev.target && ev.target.tagName || "")) {
      ev.preventDefault();
      next();
      return;
    }
    if (ev.target && /^(INPUT|TEXTAREA|SELECT)$/.test(ev.target.tagName)) { return; }
    var q = current();
    if (!q) { return; }
    if (q.question_type === "single_choice" && /^[1-9]$/.test(ev.key)) {
      var nodes = TKU.$$(".opt", elOptions);
      var node = nodes[parseInt(ev.key, 10) - 1];
      if (node) { node.click(); }
    } else if (ev.key === "Enter" && !elSubjective.hidden) {
      btnSubmitText.click();
    }
  });

  renderWrongList();          /* 需求 3：进页面先给「本轮暂无错题」，不留空白 */
  load();
})();
