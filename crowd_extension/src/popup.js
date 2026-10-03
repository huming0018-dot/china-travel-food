/**
 * popup.js — 状态面板逻辑（MV3 合规：独立文件，无内联脚本）
 */
(() => {
  const $ = (id) => document.getElementById(id);
  if (!$) return;

  function render(status) {
    if (!status) { $("s_state").textContent = "未就绪(需参与协议)"; return; }
    $("s_state").textContent = "运行中";
    $("s_state").className = "val status-ok";
    const d = status.day || {};
    $("s_searches").textContent = (d.searches || 0) + " 次";
    if (status.cooldown && status.cooldown.active) {
      $("s_cooldown").textContent = "冷却 " + status.cooldown.leftMin + "min";
      $("s_cooldown").className = "val status-warn";
    } else {
      $("s_cooldown").textContent = "无";
      $("s_cooldown").className = "val status-ok";
    }
    $("s_queue").textContent = (status.queueLen || 0) + " 条";
    // v3 回流健康：服务端确认次数（lastOkAgoSec）+ 连续零有效计数
    const f = status.flow || {};
    const lastOk = f.lastOkAgoSec != null ? (f.lastOkAgoSec < 3600 ? "最近确认" : f.lastOkAgoSec + "s前") : "未回传";
    $("s_flow").textContent = f.stalled ? ("异常·连续" + (f.zeroCount || 0) + "次零有效") : (lastOk + (f.zeroCount ? " ·零有效" + f.zeroCount + "次" : ""));
    $("s_flow").className = f.stalled ? "val status-bad" : "val status-ok";
    $("s_task").textContent = status.activeTask ? "#" + status.activeTask.task_id + "(" + status.activeTask.pack_len + "项, KPI " + status.activeTask.kpi_min + ")" : "无";
    $("s_done").textContent = status.doneCount ? status.doneCount + " 个包" : "0";
    // 关键词进度条
    const kwBox = $("kw_box");
    kwBox.innerHTML = "";
    if (status.activeTask && status.activeTask.kwProgress) {
      status.activeTask.kwProgress.forEach((p, i) => {
        const bar = document.createElement("div");
        bar.style.cssText = "margin:3px 0;font-size:12px;";
        const pct = Math.min(100, Math.round((p.accepted / status.activeTask.kpi_min) * 100));
        const color = p.done ? "#059669" : (pct > 0 ? "#b45309" : "#e5e7eb");
        bar.innerHTML = '<span style="color:#6b7280">' + (i + 1) + ".</span> <span style='max-width:130px;display:inline-block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;vertical-align:middle'>" + p.kw + "</span> " +
          '<span style="float:right;color:' + color + '">' + p.accepted + "/" + status.activeTask.kpi_min + (p.done ? " ✓" : "") + "</span>" +
          '<div style="height:4px;background:#f0f0f0;border-radius:2px;margin-top:2px"><div style="height:100%;width:' + pct + '%;background:' + color + ';border-radius:2px"></div></div>';
        kwBox.appendChild(bar);
      });
    }
    $("s_pid").textContent = status.participantId || "未填写";
    const gate = status.gateBlockReason || "";
    $("s_gate").textContent = gate || "正常";
    $("s_gate").className = gate ? "val status-bad" : "val status-ok";
  }

  chrome.runtime.sendMessage({ type: "CROWD_STATUS" }, render);
  $("start").addEventListener("click", () => {
    chrome.runtime.sendMessage({ type: "CROWD_START" }, () => {
      chrome.runtime.sendMessage({ type: "CROWD_STATUS" }, render);
    });
  });
  $("stop").addEventListener("click", () => {
    chrome.runtime.sendMessage({ type: "CROWD_STOP" }, () => {
      $("s_state").textContent = "已停止"; $("s_state").className = "val status-warn";
    });
  });
})();
