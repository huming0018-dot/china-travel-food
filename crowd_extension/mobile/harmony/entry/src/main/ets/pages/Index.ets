import { webview } from '@kit.ArkWeb';
import { common, wantAgent } from '@kit.AbilityKit';
import { preferences } from '@kit.ArkData';
import { backgroundTaskManager } from '@kit.BackgroundTasksKit';
import { asset } from '@kit.AssetStoreKit';
import { util } from '@kit.ArkTS';
import { BusinessError } from '@kit.BasicServicesKit';
import { fileIo, picker } from '@kit.CoreFileKit';

interface Params { key?: string; value?: Object; when?: number; url?: string; action?: string; text?: string; pending?: number }
interface Request { id: string; method: string; params: Params }
interface Reply { ok: boolean; data?: Object | null; error?: string }

@Entry
@Component
struct Index {
  private isPublicPage(value: string): boolean {
    return /^https:\/\/(?:www|m)\.xiaohongshu\.com\//.test(value);
  }
  @StorageLink('crowdInvite') @Watch('receiveIncoming') private incoming: string = '';
  private controlReady: boolean = false;
  private receiveIncoming(): void {
    if (this.controlReady && this.incoming) { this.control.runJavaScript(`CrowdNative.receiveInvite(${JSON.stringify(this.incoming)})`); this.incoming = ''; }
  }
  private control: webview.WebviewController = new webview.WebviewController();
  private browser: webview.WebviewController = new webview.WebviewController();
  private running: boolean = false;
  private timer: number = -1;
  private expiry: number = -1;
  private suspended: number = -1;
  private transfer: boolean = false;
  private encoder: util.TextEncoder = new util.TextEncoder();
  private proxy: Host = new Host(this);

  reply(id: string, data: Object | null, error?: string): void {
    const value: Reply = { ok: !error, data: data, error: error };
    this.control.runJavaScript(`CrowdBridgeReply(${JSON.stringify(id)},${JSON.stringify(value)})`);
  }
  async storage(key: string, write: boolean, value?: Object): Promise<Object | null> {
    if (!/^[a-zA-Z0-9:_-]{1,120}$/.test(key)) throw new Error('invalid_key');
    if (key === 'session' || key === 'install_secret' || key === 'pending_invite') {
      const query: asset.AssetMap = new Map(); query.set(asset.Tag.ALIAS, this.encoder.encodeInto('crowd-' + key));
      if (write) {
        const attrs: asset.AssetMap = new Map(); attrs.set(asset.Tag.SECRET, this.encoder.encodeInto(JSON.stringify(value)));
        try { await asset.update(query, attrs); }
        catch (e) {
          if ((e as BusinessError).code !== 24000002) throw e;
          attrs.set(asset.Tag.ALIAS, this.encoder.encodeInto('crowd-' + key)); attrs.set(asset.Tag.ACCESSIBILITY, asset.Accessibility.DEVICE_FIRST_UNLOCKED);
          await asset.add(attrs);
        }
        return null;
      }
      query.set(asset.Tag.RETURN_TYPE, asset.ReturnType.ALL);
      try {
        const results = await asset.query(query);
        if (!results.length) return null;
        return JSON.parse(util.TextDecoder.create('utf-8').decodeToString(results[0].get(asset.Tag.SECRET) as Uint8Array)) as Object;
      } catch (e) { if ((e as BusinessError).code === 24000002) return null; throw e; }
    }
    const context = getContext(this) as common.UIAbilityContext;
    const store = await preferences.getPreferences(context, { name: 'crowd-state' });
    if (write) { await store.put(key, JSON.stringify(value)); await store.flush(); return null; }
    const result = await store.get(key, 'null'); return JSON.parse(result as string) as Object | null;
  }
  async dispatch(text: string): Promise<void> {
    // Only the bundled Web receives this proxy; never register it on the XHS Web.
    const location = this.control.getUrl();
    if (!location.endsWith('/assets/controller.html') || (!location.startsWith('file:') && !location.startsWith('resource:'))) return;
    let id = '';
    try {
      const m = JSON.parse(text) as Request; id = m.id; const p = m.params;
      if (!id || !p) throw new Error('invalid_request');
      switch (m.method) {
        case 'get': this.reply(id, await this.storage(p.key!, false)); return;
        case 'set': await this.storage(p.key!, true, p.value); break;
        case 'begin':
          this.running = true;
          clearTimeout(this.expiry);
          this.expiry = setTimeout(() => this.suspend(), 10 * 60 * 1000); break;
        case 'end': await this.end(); break;
        case 'background': await this.background(p.pending || 0); this.reply(id, { collect_allowed: false }); return;
        case 'schedule':
          clearTimeout(this.timer);
          if (this.running) this.timer = setTimeout(() => this.control.runJavaScript('CrowdNative.wake()'), Math.max(1000, p.when! - Date.now())); break;
        case 'cancel': clearTimeout(this.timer); break;
        case 'open':
          if (!p.url || !this.isPublicPage(p.url)) throw new Error('unsupported_origin');
          this.browser.loadUrl(p.url); break;
        case 'probe': {
          if (!this.isPublicPage(this.browser.getUrl())) { this.reply(id, { ready: false }); return; }
          const context = getContext(this) as common.UIAbilityContext;
          const core = util.TextDecoder.create('utf-8').decodeToString(await context.resourceManager.getRawFileContent('assets/core.js'));
          const parser = util.TextDecoder.create('utf-8').decodeToString(await context.resourceManager.getRawFileContent('assets/content.js'));
          const raw = await this.browser.runJavaScript(core + parser + `;JSON.stringify(CrowdPage.probe(${JSON.stringify(p.action)}))`);
          const result = JSON.parse(raw) as Object; this.reply(id, typeof result === 'string' ? JSON.parse(result) as Object : result); return;
        }
        case 'close': this.browser.loadUrl('about:blank'); break;
        case 'showBrowser': this.browser.loadUrl('https://www.xiaohongshu.com/'); break;
        case 'export': {
          const context = getContext(this) as common.UIAbilityContext;
          const dialog = new picker.DocumentViewPicker(context);
          const paths = await dialog.save({ newFileNames: ['crowd-pending-evidence.json'] });
          if (paths.length) { const file = fileIo.openSync(paths[0], fileIo.OpenMode.WRITE_ONLY | fileIo.OpenMode.CREATE); try { fileIo.writeSync(file.fd, p.text!); } finally { fileIo.closeSync(file); } }
          break;
        }
        default: throw new Error('unknown_method');
      }
      this.reply(id, null);
    } catch (e) { this.reply(id, null, (e as Error).message || 'native_error'); }
  }
  suspend(): void { this.control.runJavaScript('CrowdNative.suspend()'); this.end(); }
  async end(): Promise<void> {
    this.running = false; clearTimeout(this.timer); clearTimeout(this.expiry);
    if (this.transfer) { await backgroundTaskManager.stopBackgroundRunning(getContext(this) as common.UIAbilityContext); this.transfer = false; }
    if (this.suspended !== -1) { backgroundTaskManager.cancelSuspendDelay(this.suspended); this.suspended = -1; }
  }
  onPageHide(): void { if (this.running) this.control.runJavaScript('CrowdNative.background()'); }
  async background(pending: number): Promise<void> {
    if (!this.running) return;
    const context = getContext(this) as common.UIAbilityContext;
    const delay = backgroundTaskManager.requestSuspendDelay('公开笔记采集保存与回传', () => this.suspend()); this.suspended = delay.requestId;
    if (pending > 0 && !this.transfer) {
      const agent = await wantAgent.getWantAgent({ wants: [{ bundleName: 'org.foodresearch.crowd', abilityName: 'EntryAbility' }],
        operationType: wantAgent.OperationType.START_ABILITY, requestCode: 0, wantAgentFlags: [wantAgent.WantAgentFlags.UPDATE_PRESENT_FLAG] });
      await backgroundTaskManager.startBackgroundRunning(context, backgroundTaskManager.BackgroundMode.DATA_TRANSFER, agent);
      this.transfer = true;
    }
    // ArkWeb collection stops in background; permitted DATA_TRANSFER only drains actual evidence.
  }
  build() {
    Column() {
      Web({ src: $rawfile('assets/controller.html'), controller: this.control })
        .javaScriptAccess(true).domStorageAccess(true).height('55%')
        .javaScriptProxy({ object: this.proxy, name: 'CrowdHost', methodList: ['postMessage'], controller: this.control })
        .onOverrideUrlLoading((request) => !request.getRequestUrl().endsWith('/assets/controller.html'))
        .onPageEnd(() => { this.controlReady = true; this.receiveIncoming(); })
      Web({ src: 'https://www.xiaohongshu.com/', controller: this.browser })
        .javaScriptAccess(true).domStorageAccess(true).height('45%')
        .onOverrideUrlLoading((request) => !this.isPublicPage(request.getRequestUrl()))
        .onPageEnd(() => { if (this.running) this.control.runJavaScript('CrowdNative.wake()'); })
    }.width('100%').height('100%')
  }
}
class Host {
  private page: Index;
  constructor(page: Index) { this.page = page; }
  postMessage(text: string): void { this.page.dispatch(text); }
}
