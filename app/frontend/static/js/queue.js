/* 题库项目 · 判分队列页（queue.js）
   四态徽标（pending / submitted / synced / failed）由模板服务端渲染保证；
   本脚本负责：failed → 手动重投、mock 判分同步、刷新列表。 */

(function () {
  "use strict";
  if (document.body.getAttribute("data-page") !== "queue") { return; }

  var elResult = TKU.byId("syncResult");

  TKU.$$(".requeue").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var attemptId = btn.getAttribute("data-attempt-id");
      if (!attemptId) { return; }
      if (!window.confirm("确认手动重投该失败任务？\n" + attemptId)) { return; }
      btn.disabled = true;
      TKU.postJSON("/api/requeue", { attempt_id: attemptId }).then(function (data) {
        TKU.toast("已重投：" + data.attempt_id + " → " + data.status, "ok");
        setTimeout(function () { window.location.reload(); }, 500);
      }).catch(function (err) {
        btn.disabled = false;
        TKU.toast("重投失败：" + err.message, "err");
      });
    });
  });

  var btnRefresh = TKU.byId("btnRefresh");
  if (btnRefresh) {
    btnRefresh.addEventListener("click", function () { window.location.reload(); });
  }

  var btnSync = TKU.byId("btnSync");
  if (btnSync) {
    btnSync.addEventListener("click", function () {
      var mock = TKU.byId("syncMock").checked;
      btnSync.disabled = true;
      elResult.textContent = "正在运行 sync_outbox.py（mock=" + mock + "）…";
      /* 本页只走 mock：真实判分需付费，必须在 /api/sync 显式带 confirm_paid=true */
      TKU.postJSON("/api/sync", { mock: mock }).then(function (data) {
        btnSync.disabled = false;
        TKU.JSONPreview(elResult, data);
        var r = data.result || {};
        TKU.toast("同步完成：pending=" + (r.pending || 0) + " synced=" + (r.synced || 0) +
                  " failed=" + (r.failed || 0), "ok");
        setTimeout(function () { window.location.reload(); }, 1200);
      }).catch(function (err) {
        btnSync.disabled = false;
        elResult.textContent = "同步失败：" + err.message;
        TKU.toast("同步失败：" + err.message, "err");
      });
    });
  }
})();
