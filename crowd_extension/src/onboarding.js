/**
 * onboarding.js — 参与协议页逻辑（MV3 合规：独立文件，无内联脚本）
 * 编号 schema 统一：P- + 8 位大写字母数字（与 apply.html / background.js / 服务端一致）
 */
(() => {
  const PID_RE = /^P-[A-Z0-9]{8}$/;

  function bind(id, fn) {
    const el = document.getElementById(id);
    if (el) el.addEventListener("click", fn);
  }

  bind("agree", () => {
    const pid = (document.getElementById("participant").value || "").trim();
    if (!pid) { alert("请填写参与者编号"); return; }
    if (!PID_RE.test(pid)) {
      alert("编号格式不正确：应为 P- 开头 + 8 位大写字母/数字（例如 P-A1B2C3D4）。报名编号需为正式编号。");
      return;
    }
    chrome.storage.local.set({ participant_id: pid, agreed_at: new Date().toISOString() }, () => {
      document.body.innerHTML = "<h1>✅ 已同意</h1><p>参与协议已签署。返回小红书页面，插件将自动开始拉取任务并采集。</p>";
    });
  });

  bind("refuse", () => {
    document.body.innerHTML = "<h1>已退出</h1><p>感谢了解。请在扩展管理中移除本插件。</p>";
  });
})();
