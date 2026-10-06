import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
import fs from 'node:fs/promises';
const {chromium}=await import(pathToFileURL(process.env.CROWD_TEST_TOOLS+'/node_modules/playwright/index.mjs'));
const browser=await chromium.launch({executablePath:process.env.CROWD_CHROMIUM||'/usr/bin/chromium',headless:true,args:['--no-sandbox','--disable-dev-shm-usage']});
const base=process.env.CROWD_PORTAL_TEST_ORIGIN||'http://127.0.0.1:44123',token='a'.repeat(64);
try {
 const context=await browser.newContext({userAgent:'Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/151.0.0.0 Mobile Safari/537.36',viewport:{width:390,height:844},serviceWorkers:'block'});
 await context.route('**/api/crowd/manifest',r=>r.fulfill({json:{ready:true,origin:'https://crowd.example.test',releases:{android:{channel:'apk',url:'https://crowd.example.test/crowd/releases/crowd-android-v4.0.0-debug.apk',version:'4.0.0',verified:true}}}}));
 const page=await context.newPage();await page.goto(base+'/crowd#invite='+token);
 await assert.doesNotReject(()=>page.getByRole('link',{name:'首次参与：安装客户端'}).waitFor());
 assert.equal(await page.locator('#device').inputValue(),'android');assert.equal(await page.getByRole('link',{name:'首次参与：安装客户端'}).getAttribute('href'),'https://crowd.example.test/crowd/releases/crowd-android-v4.0.0-debug.apk');
 await page.locator('#device').selectOption('ios');await page.getByText('这类设备的安装渠道尚未开放。',{exact:false}).waitFor();assert.equal(await page.getByRole('link',{name:'首次参与：安装客户端'}).count(),0);
 await page.locator('#device').selectOption('android');
 if(process.env.CROWD_PORTAL_PREVIEW)await page.screenshot({path:process.env.CROWD_PORTAL_PREVIEW,fullPage:true});
 await page.goto(base+'/crowd');await page.getByText('请打开邀请人发来的完整链接或扫描二维码。').waitFor();assert.equal(await page.getByRole('link',{name:'首次参与：安装客户端'}).count(),0);
 // A desktop installer is automatically reassembled and verified, never split manually.
 const bytes=Buffer.from('fixture installer bytes'),digest=createHash('sha256').update(bytes).digest('hex'),filename='crowd-windows-x64-v4.0.0.zip';
 await context.unroute('**/api/crowd/manifest');await context.route('**/api/crowd/manifest',r=>r.fulfill({json:{ready:true,origin:base,releases:{windows:{channel:'desktop',url:base+'/crowd/releases/'+filename,version:'4.0.0',sha256:digest,verified:true}}}}));
 let partHash=digest;
 await context.route('**/crowd/releases/*.json',r=>r.fulfill({json:{file:filename,bytes:bytes.length,sha256:digest,parts:[{url:'/crowd/releases/'+filename+'.part0',bytes:bytes.length,sha256:partHash}]}}));
 await context.route('**/crowd/releases/*.part0',r=>r.fulfill({body:bytes,contentType:'application/octet-stream'}));
 await page.goto(base+'/crowd#invite='+token);await page.locator('#device').selectOption('windows');
 const downloaded=page.waitForEvent('download');await page.getByRole('button',{name:'首次参与：安装客户端'}).click();const file=await downloaded;
 assert.equal(file.suggestedFilename(),filename);assert.deepEqual(await fs.readFile(await file.path()),bytes);
 partHash='0'.repeat(64);await page.getByRole('button',{name:'首次参与：安装客户端'}).click();await page.getByText('下载未完成或校验失败，请点安装按钮重试。').waitFor();
 // Publisher stays closed until live readiness; no offline/cached success.
 await context.unroute('**/api/crowd/manifest');await context.route('**/api/crowd/manifest',r=>r.fulfill({status:503,json:{error:'backend_unavailable'}}));
 await page.goto(base+'/crowd/admin');assert.equal(await page.getByRole('button',{name:'生成邀请链接和二维码'}).isDisabled(),true);
 console.log('PASS real portal DOM: automatic Android routing, SMS invitation, direct installation, desktop reassembly/checksum/fault rejection, unready iOS, missing invite and unready publisher blocked');
 console.log('LIMIT: local website + API fixtures; no live deployment or external OS protocol acceptance');
}finally{await browser.close();}
