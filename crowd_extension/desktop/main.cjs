'use strict';
const {app, BrowserWindow, WebContentsView, ipcMain, safeStorage, dialog, Tray, Menu} = require('electron');
const fs = require('node:fs/promises'), path = require('node:path'), {pathToFileURL} = require('node:url');
const assets = path.join(__dirname, 'assets'), controlURL = pathToFileURL(path.join(assets, 'controller.html')).href;
let window, control, browser, tray, data = {}, running = false, quitting = false, timer, incoming, disk = Promise.resolve();
const file = () => path.join(app.getPath('userData'), 'state.enc');
const trusted = event => event.sender === control?.webContents && event.senderFrame === control.webContents.mainFrame && control.webContents.getURL() === controlURL;
function invite(value) {
  try { const u = new URL(value); if (u.protocol === 'foodcrowd:' && u.host === 'join' && /^invite=[a-f0-9]{64}$/.test(u.hash.slice(1))) return u.hash.slice(8); } catch (_) {}
  return null;
}
async function save(key, value) {
  disk = disk.catch(() => {}).then(async () => {
    const next = {...data, [key]: value}, temporary = file() + '.tmp';
    await fs.writeFile(temporary, safeStorage.encryptString(JSON.stringify(next)), {mode: 0o600});
    const handle = await fs.open(temporary, 'r+'); try { await handle.sync(); } finally { await handle.close(); }
    await fs.rename(temporary, file()); data = next;
  });
  return disk;
}
async function receive(value) {
  const token = invite(value); if (!token) return;
  incoming = token;
  if (control) {
    await save('pending_invite', token); incoming = null;
    if (!control.webContents.isLoadingMainFrame()) control.webContents.executeJavaScript("window.dispatchEvent(new Event('crowd_invite'))");
    window.show();
  }
}
function validateRemote(value) {
  const u = new URL(value); if (u.protocol !== 'https:' || !['www.xiaohongshu.com','m.xiaohongshu.com'].includes(u.hostname) || u.username || u.password || u.port) throw new Error('unsupported_origin'); return u.href;
}
function layout() {
  const [width, height] = window.getContentSize(), left = Math.min(420, Math.floor(width * .45));
  control.setBounds({x: 0, y: 0, width: left, height}); browser.setBounds({x: left, y: 0, width: width - left, height});
}
async function dispatch(message) {
  const {id, method, params: p} = JSON.parse(message);
  if (typeof id !== 'string' || !p || typeof p !== 'object') throw new Error('invalid_request');
  let value = null;
  switch (method) {
    case 'get': if (!/^[a-zA-Z0-9:_-]{1,120}$/.test(p.key)) throw new Error('invalid_key'); value = data[p.key] ?? null; break;
    case 'set': if (!/^[a-zA-Z0-9:_-]{1,120}$/.test(p.key)) throw new Error('invalid_key'); await save(p.key, p.value); break;
    case 'begin': running = true; tray.setToolTip('众包自动采集中，可随时停止'); break;
    case 'end': running = false; clearTimeout(timer); tray.setToolTip('众包采集已暂停'); break;
    case 'background': value = {collect_allowed: running}; break;
    case 'schedule': clearTimeout(timer); if (running) timer = setTimeout(() => control.webContents.executeJavaScript('CrowdNative.wake()'), Math.max(1000, p.when - Date.now())); break;
    case 'cancel': clearTimeout(timer); break;
    case 'open': await browser.webContents.loadURL(validateRemote(p.url)); break;
    case 'close': await browser.webContents.loadURL('about:blank'); break;
    case 'showBrowser': await browser.webContents.loadURL('https://www.xiaohongshu.com/'); break;
    case 'probe': {
      try { validateRemote(browser.webContents.getURL()); } catch (_) { value = {ready: false}; break; }
      if (!['note', 'search', 'scroll'].includes(p.action)) throw new Error('invalid_action');
      const code = await fs.readFile(path.join(assets, 'core.js'), 'utf8') + await fs.readFile(path.join(assets, 'content.js'), 'utf8');
      value = JSON.parse(await browser.webContents.executeJavaScript(code + ';JSON.stringify(CrowdPage.probe(' + JSON.stringify(p.action) + '))')); break;
    }
    case 'export': { const result = await dialog.showSaveDialog(window, {defaultPath: 'crowd-pending-evidence.json'}); if (!result.canceled) await fs.writeFile(result.filePath, p.text, {mode: 0o600}); break; }
    default: throw new Error('unknown_method');
  }
  return {id, reply: {ok: true, data: value}};
}
if (!app.requestSingleInstanceLock()) app.quit();
else {
  app.on('second-instance', (_, argv) => { argv.forEach(value => receive(value)); if (window) window.show(); });
  app.on('open-url', (event, value) => { event.preventDefault(); receive(value); });
  incoming = process.argv.map(invite).find(Boolean) || null;
  app.whenReady().then(async () => {
    if (!safeStorage.isEncryptionAvailable() || (process.platform === 'linux' && safeStorage.getSelectedStorageBackend() === 'basic_text')) throw new Error('secure_storage_unavailable');
    try { data = JSON.parse(safeStorage.decryptString(await fs.readFile(file()))); } catch (e) { if (e.code !== 'ENOENT') throw e; }
    if (incoming) { await save('pending_invite', incoming); incoming = null; }
    if (process.defaultApp) app.setAsDefaultProtocolClient('foodcrowd', process.execPath, [path.resolve(process.argv[1])]); else app.setAsDefaultProtocolClient('foodcrowd');
    window = new BrowserWindow({width: 1100, height: 800, minWidth: 800, title: '众包公开笔记采集'});
    const base = {contextIsolation: true, sandbox: true, nodeIntegration: false, backgroundThrottling: false};
    control = new WebContentsView({webPreferences: {...base, preload: path.join(__dirname, 'preload.cjs')}});
    browser = new WebContentsView({webPreferences: {...base, partition: 'persist:crowd-xhs'}});
    window.contentView.addChildView(control); window.contentView.addChildView(browser); layout(); window.on('resize', layout);
    for (const name of ['will-navigate','will-redirect']) {
      control.webContents.on(name, (event, url) => { if (url !== controlURL) event.preventDefault(); });
      browser.webContents.on(name, (event, url) => { try { validateRemote(url); } catch (_) { event.preventDefault(); } });
    }
    for (const view of [control, browser]) { view.webContents.setWindowOpenHandler(() => ({action: 'deny'})); view.webContents.session.setPermissionRequestHandler((_, __, callback) => callback(false)); }
    ipcMain.handle('crowd', async (event, text) => {
      if (!trusted(event) || typeof text !== 'string' || text.length > 3000000) return null;
      try { return await dispatch(text); } catch (e) { try { return {id: JSON.parse(text).id, reply: {ok: false, error: e.message}}; } catch (_) { return null; } }
    });
    ipcMain.on('crowd-reply', (event, value) => { if (trusted(event)) control.webContents.executeJavaScript('CrowdBridgeReply(' + JSON.stringify(value.id) + ',' + JSON.stringify(value.reply) + ')'); });
    tray = new Tray(path.join(assets, 'icon128.png')); tray.setToolTip('众包采集已暂停');
    tray.setContextMenu(Menu.buildFromTemplate([{label: '打开', click: () => window.show()}, {label: '停止', click: () => control.webContents.executeJavaScript("CrowdNative.command('stop',{})")}, {label: '退出', click: () => { running = false; app.quit(); }}]));
    tray.on('click', () => window.show());
    window.on('close', event => { if (running) { event.preventDefault(); window.hide(); } else app.quit(); });
    await control.webContents.loadURL(controlURL); await browser.webContents.loadURL('https://www.xiaohongshu.com/');
  }).catch(() => { dialog.showErrorBox('无法启动', '安全存储或本地状态暂不可用。已有证据没有删除，请联系邀请人。'); app.quit(); });
  app.on('before-quit', event => {
    running = false; clearTimeout(timer); if (quitting) return;
    event.preventDefault(); quitting = true;
    Promise.resolve(control?.webContents.executeJavaScript('CrowdNative.suspend()')).catch(() => {})
      .then(() => disk).finally(() => app.quit());
  });
}
