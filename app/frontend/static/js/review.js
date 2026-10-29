/* 题库项目 · 人工审核页（review.js）
   一屏一题 + 三按钮（通过 / 拒绝 / 修改）+ 快捷键 A / R / E / ← / →。
   ⚠️ 拒绝必须选原因（下拉 7 项）；原因由后端写 logs/review_rejects.jsonl，
      绝不写 config/distractors.json。 */

(function () {
  "use strict";
  if (document.body.getAttribute("data-page") !== "review") { return; }

  var INFO = window.TKU_REVIEW || {};
  var elMsg = TKU.byId("reviewMsg");
  var elReason = TKU.byId("rejectReason");
  var elEditArea = TKU.byId("editArea");
  var busy = false;

  function msg(text) { if (elMsg) { elMsg.textContent = text || ""; } }

  function goto(idx) {
    var d = document.body.dataset;
    var parts = [];
    if (d.subject) { parts.push("subject=" + encodeURIComponent(d.subject)); }
    parts.push("idx=" + Math.max(0, idx));
    window.location.href = "/review?" + parts.join("&");
  }

  function reloadSame() { goto(INFO.index || 0); }

  function act(payload, okText) {
    if (busy) { return; }
    busy = true;
    msg("提交中…");
    TKU.postJSON("/review/action", payload).then(function (data) {
      busy = false;
      msg(okText + "（status=" + data.status + "，version=" + data.version + "）");
      TKU.toast(okText + "：" + payload.question_uid, "ok");
      setTimeout(reloadSame, 500);
    }).catch(function (err) {
      busy = false;
      msg("失败：" + err.message);
      TKU.toast("审核动作失败：" + err.message, "err");
    });
  }

  function approve() {
    if (!INFO.question_uid) { return; }
    act({ question_uid: INFO.question_uid, subject: INFO.subject, decision: "通过" }, "已通过（approved）");
  }

  function reject() {
    if (!INFO.question_uid) { return; }
    var reason = elReason ? elReason.value : "";
    if (!reason) {
      msg("拒绝必须选择原因");
      TKU.toast("拒绝必须选择原因（下拉 7 项）", "err");
      if (elReason) { elReason.focus(); }
      return;
    }
    act({
      question_uid: INFO.question_uid, subject: INFO.subject,
      decision: "拒绝", reason: reason
    }, "已拒绝（rejected）");
  }

  function toggleEdit() {
    if (!elEditArea) { return; }
    elEditArea.hidden = !elEditArea.hidden;
    if (!elEditArea.hidden) {
      var first = TKU.byId("editStem");
      if (first) { first.focus(); }
    }
    msg(elEditArea.hidden ? "" : "编辑模式：保存后仍为 pending_review");
  }

  function saveEdit() {
    if (!INFO.question_uid) { return; }
    act({
      question_uid: INFO.question_uid,
      subject: INFO.subject,
      decision: "修改",
      stem: TKU.byId("editStem").value,
      answer: TKU.byId("editAnswer").value,
      explanation: TKU.byId("editExplanation").value
    }, "已保存修改（仍待审核）");
  }

  var b = TKU.byId("btnApprove"); if (b) { b.addEventListener("click", approve); }
  b = TKU.byId("btnReject"); if (b) { b.addEventListener("click", reject); }
  b = TKU.byId("btnEdit"); if (b) { b.addEventListener("click", toggleEdit); }
  b = TKU.byId("btnSaveEdit"); if (b) { b.addEventListener("click", saveEdit); }
  b = TKU.byId("btnCancelEdit"); if (b) { b.addEventListener("click", toggleEdit); }
  b = TKU.byId("btnPrev"); if (b) { b.addEventListener("click", function () { goto((INFO.index || 0) - 1); }); }
  b = TKU.byId("btnNext"); if (b) { b.addEventListener("click", function () { goto((INFO.index || 0) + 1); }); }

  document.addEventListener("keydown", function (ev) {
    if (ev.ctrlKey || ev.altKey || ev.metaKey) { return; }
    var tag = ev.target && ev.target.tagName;
    if (tag === "TEXTAREA" || tag === "SELECT" || tag === "INPUT") { return; }
    if (ev.key === "a" || ev.key === "A") { ev.preventDefault(); approve(); }
    else if (ev.key === "r" || ev.key === "R") { ev.preventDefault(); reject(); }
    else if (ev.key === "e" || ev.key === "E") { ev.preventDefault(); toggleEdit(); }
    else if (ev.key === "ArrowLeft") { ev.preventDefault(); goto((INFO.index || 0) - 1); }
    else if (ev.key === "ArrowRight") { ev.preventDefault(); goto((INFO.index || 0) + 1); }
  });
})();
