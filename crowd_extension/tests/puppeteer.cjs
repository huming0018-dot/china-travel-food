'use strict';
// Real controller/portal DOM; native OS, backend and XHS are explicit fixtures.
const assert=require('node:assert/strict'),fs=require('node:fs/promises');
const path=require('node:path'),{createHash,randomUUID}=require('node:crypto');
const root=path.resolve(__dirname,'../..');
const puppeteer=require(path.join(process.env.CROWD_PUPPETEER_TOOLS||path.join(root,'crowd-test-harness'),'node_modules/puppeteer-core'));
const base=process.env.CROWD_PORTAL_TEST_ORIGIN||'http://127.0.0.1:44127';
const output=process.env.CROWD_PUPPETEER_OUTPUT||path.join(root,'crowd-test-harness/results/puppeteer-v4');
const invite='a'.repeat(64),id='abcdef0123456789abcdef01',user='00000000-0000-4000-8000-000000000001';
const backend='https://test.supabase.co',portal='https://crowd.example.test',client='https://client.example.test';
const config={url:backend,key:'sb_publishable_TEST_ONLY',portal,platform:'android'};
const passes=[],failures=[],unexpected=[],calls=[],submissions=[];
const note='<section class="note-container"><h1 id="detail-title">测试餐厅清蒸鱼</h1><div id="detail-desc">测试餐厅清蒸鱼好吃，价格合理。\n#清蒸鱼 #上海美食\n排队有点长，服务很好。</div><span class="date">2026-10-05</span></section><div class="interact-container"><span class="like-wrapper"><span class="count">1.2万</span></span></div>';
let browser,clock=Date.now(),state={},enrollRelease,enrollEntered,holdEnroll=true,mode='notes',ackLost=true,taskDone=false;
const enrollmentStarted=new Promise(r=>enrollEntered=r),enrollmentBlocked=new Promise(r=>enrollRelease=r);
const task={id:1,query:'测试餐厅',received:0,target:1,lease_token:randomUUID(),lease_until:new Date(clock+3600000).toISOString()};
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
const wait=async fn=>{for(let i=0;i<100;i++){if(await fn())return;await new Promise(r=>setTimeout(r,50));}throw new Error('condition timed out');};
async function test(name,fn){await fn();passes.push(name);console.log('PASS '+name);}
function response(body,status=200){return {status,contentType:'application/json',headers:{'access-control-allow-origin':client,'access-control-allow-headers':'apikey,authorization,content-type','access-control-allow-methods':'POST,OPTIONS'},body:JSON.stringify(body)};}
async function intercept(page,handler){
 await page.setRequestInterception(true);
 page.on('request',req=>{Promise.resolve(handler(req)).catch(error=>{failures.push(error.message);if(!req.isInterceptResolutionHandled())req.abort().catch(()=>{});});});
 page.on('pageerror',error=>failures.push(error.message));
}
(async()=>{
 await fs.mkdir(output,{recursive:true});
 browser=await puppeteer.launch({executablePath:process.env.CROWD_CHROMIUM||'/usr/bin/chromium',headless:true,args:['--no-sandbox','--disable-dev-shm-usage']});
 const context=await browser.createBrowserContext(),page=await context.newPage();
 await page.setBypassServiceWorker(true);
 await page.setUserAgent('Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/151.0.0.0 Mobile Safari/537.36');
 await page.setViewport({width:390,height:844});
 const bytes=Buffer.from('Puppeteer fixture installer'),filename='crowd-windows-x64-v4.0.0-setup.exe';
 let ready=true,badHash=false,platform='android';
 await intercept(page,req=>{
  const u=new URL(req.url());
  if(u.origin===base){
   if(u.pathname==='/api/crowd/manifest')return req.respond(response(ready?{ready:true,origin:base,releases:{[platform]:{channel:platform==='android'?'apk':'desktop',url:base+'/crowd/releases/'+(platform==='android'?'crowd-android-v4.0.0-debug.apk':filename),version:'4.0.0',sha256:hash(bytes),verified:true}}}:{error:'backend_unavailable'},ready?200:503));
   if(u.pathname==='/api/crowd/invite')return req.respond(response({link:base+'/crowd#invite='+invite,qr:'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jWZkAAAAASUVORK5CYII=',expires_at:'2026-10-13T12:00:00Z'}));
   if(u.pathname.endsWith('.exe.json'))return req.respond(response({file:filename,bytes:bytes.length,sha256:hash(bytes),parts:[{url:'/crowd/releases/'+filename+'.part0',bytes:bytes.length,sha256:badHash?'0'.repeat(64):hash(bytes)}]}));
   if(u.pathname.endsWith('.part0'))return req.respond({status:200,contentType:'application/octet-stream',body:bytes});
   return req.continue();
  }
  if(req.url().startsWith('data:')||req.url().startsWith('blob:'))return req.continue();
  return req.respond({status:404,body:''});
 });
 await test('Puppeteer portal: SMS invite, Android auto-detection and installation link',async()=>{
  await page.goto(base+'/crowd#invite='+invite);await page.waitForSelector('a[href$="debug.apk"]');
  assert.equal(await page.$eval('#device',el=>el.value),'android');
  assert.equal(await page.$eval('a[href$="debug.apk"]',el=>el.textContent),'首次参与：安装客户端');
  await page.screenshot({path:path.join(output,'portal-android.png'),fullPage:true});
 });
 await test('Puppeteer portal: unavailable Apple channel and missing invite stay closed',async()=>{
  await page.click('details:has(#device) > summary');await page.select('#device','ios');await page.waitForFunction(()=>document.body.innerText.includes('这类设备的安装渠道尚未开放'));
  assert.equal(await page.$('a[href$="debug.apk"]'),null);
  await page.goto(base+'/crowd');await page.waitForFunction(()=>document.body.innerText.includes('请打开邀请人发来的完整链接'));
  assert.equal(await page.$('a[href$="debug.apk"]'),null);
 });
 await test('Puppeteer portal: desktop download bytes verified; corrupted part rejected',async()=>{
  platform='windows';await page.goto(base+'/crowd#invite='+invite);await page.click('details:has(#device) > summary');await page.select('#device','windows');
  await page.waitForFunction(()=>[...document.querySelectorAll('button')].some(b=>b.textContent==='首次参与：安装客户端'&&!b.disabled));
  const cdp=await browser.target().createCDPSession();await cdp.send('Browser.setDownloadBehavior',{behavior:'allow',downloadPath:output,browserContextId:context.id});
  await page.evaluate(()=>[...document.querySelectorAll('button')].find(b=>b.textContent==='首次参与：安装客户端').click());
  await wait(async()=>{try{return (await fs.readFile(path.join(output,filename))).equals(bytes);}catch{return false;}});
  await page.waitForFunction(()=>document.body.innerText.includes('下载完成。'));
  assert.ok((await page.evaluate(()=>document.body.innerText)).includes('无需解压或输入命令'));
  badHash=true;await page.evaluate(()=>[...document.querySelectorAll('button')].find(b=>b.textContent==='重新下载安装包').click());
  await page.waitForFunction(()=>document.body.innerText.includes('下载未完成或校验失败'));
 });
 await test('Puppeteer embedded browser: explains system-browser path and blocks APK handoff',async()=>{
  platform='android';await page.setUserAgent('Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 MicroMessenger/8.0');
  await page.goto(base+'/crowd#invite='+invite);await page.reload();await page.waitForFunction(()=>document.body.innerText.includes('微信、QQ 等内置浏览器'));
  await page.click('a[href$="debug.apk"]');await page.waitForFunction(()=>document.body.innerText.includes('请先用系统浏览器打开邀请链接'));
  assert.ok(page.url().includes('/crowd#invite='));
  assert.equal(await page.evaluate(()=>[...document.querySelectorAll('button')].find(b=>b.textContent==='已安装，继续参与').disabled),true);
 });
 await test('Puppeteer publisher: unready backend prevents invitation creation',async()=>{
  ready=false;await page.goto(base+'/crowd/admin');await page.waitForFunction(()=>document.body.innerText.includes('入口尚未完成部署'));
  await page.type('input[type="password"]','TEST_ONLY_OPERATOR_KEY_32_CHARACTERS');
  assert.equal(await page.$eval('button',el=>el.disabled),true);
 });
 await test('Puppeteer publisher: copy/select one complete SMS without leaking publisher identity',async()=>{
  ready=true;await page.goto(base+'/crowd/admin');await page.type('input[type="password"]','TEST_ONLY_OPERATOR_KEY_32_CHARACTERS');
  await page.waitForFunction(()=>!document.querySelector('button').disabled);await page.click('button');await page.waitForSelector('textarea[aria-label="分发短信"]');
  const sms=await page.$eval('textarea',el=>el.value);assert.ok(sms.includes(base+'/crowd#invite='+invite));assert.ok(sms.includes('可随时停止'));assert.equal(sms.includes('TEST_ONLY_OPERATOR'),false);
  await context.overridePermissions(base,['clipboard-read','clipboard-write']);await page.bringToFront();
  await page.click('text/复制整条短信');
  await page.waitForFunction(()=>document.body.innerText.includes('整条短信已复制')||document.body.innerText.includes('短信已选中'));
  const copied=await page.evaluate(()=>document.body.innerText.includes('整条短信已复制'));
  if(copied)assert.equal(await page.evaluate(()=>navigator.clipboard.readText()),sms);
  else assert.deepEqual(await page.$eval('textarea',el=>[el.selectionStart,el.selectionEnd]),[0,sms.length]);
  const smsURL=await page.$eval('a[href^="sms:"]',el=>el.getAttribute('href'));assert.equal(new URLSearchParams(smsURL.split('?')[1]).get('body'),sms);
  await page.screenshot({path:path.join(output,'publisher-share.png'),fullPage:true});
 });
 const work=await context.newPage(),control=await context.newPage();
 await intercept(work,req=>{
  const u=new URL(req.url());
  if(['www.xiaohongshu.com','m.xiaohongshu.com'].includes(u.hostname)){
   assert.equal(req.headers().authorization,undefined);assert.equal(req.headers().apikey,undefined);
   const html=mode==='captcha'?'<div class="captcha">验证码</div>':u.pathname==='/search_result'?'<a href="/explore/'+id+'?xsec_token=local-only">测试餐厅清蒸鱼</a>':note;
   return req.respond({status:200,contentType:'text/html; charset=utf-8',body:'<!doctype html><html><body>'+html+'</body></html>'});
  }
  unexpected.push(u.origin+u.pathname);return req.respond({status:403,body:''});
 });
 async function hostCall({method,params:p}){
  calls.push(method);
  if(method==='get')return structuredClone(state[p.key]??null);
  if(method==='set'){state[p.key]=structuredClone(p.value);return null;}
  if(method==='background')return {collect_allowed:true};
  if(method==='open'){
   await work.goto(p.url);for(const name of ['core','content'])await work.addScriptTag({path:path.join(root,'crowd_extension/src',name+'.js')});return null;
  }
  if(method==='probe')return work.evaluate(action=>CrowdPage.probe(action),p.action);
  return null;
 }
 await control.exposeFunction('__host',hostCall);
 await control.exposeFunction('__clock',()=>clock);
 await control.evaluateOnNewDocument(()=>{
  let now=Date.now();Date.now=()=>now;window.__advance=async()=>{now=await window.__clock();};Math.random=()=>0;
  window.CrowdHost={postMessage:text=>{const request=JSON.parse(text);window.__host(request).then(data=>window.CrowdBridgeReply(request.id,{ok:true,data})).catch(e=>window.CrowdBridgeReply(request.id,{ok:false,error:e.message}));}};
 });
 await intercept(control,async req=>{
  const u=new URL(req.url());
  if(u.origin===client){
   const name=path.basename(u.pathname);
   if(name==='config.js')return req.respond({status:200,contentType:'application/javascript',body:'globalThis.CROWD_CONFIG='+JSON.stringify(config)+';'});
   if(!['controller.html','controller.css','controller.js','core.js','api.js','agent.js','join.js','native-runtime.js'].includes(name))return req.respond({status:404,body:''});
   let body=await fs.readFile(path.join(root,'crowd_extension/src',name));
   if(name==='controller.html')body=body.toString().replace('connect-src https://*.supabase.co;','connect-src '+backend+' '+portal+';');
   return req.respond({status:200,contentType:name.endsWith('.html')?'text/html':name.endsWith('.css')?'text/css':'application/javascript',body});
  }
  if(u.origin===backend||u.origin===portal){
   if(req.method()==='OPTIONS')return req.respond(response({}));
   const body=JSON.parse(req.postData()||'{}');
   if(u.pathname==='/api/crowd/enroll'){
    assert.equal(body.consent,'crowd-public-v4');assert.equal(body.invite,invite);enrollEntered();if(holdEnroll)await enrollmentBlocked;
    return req.respond(response({email:'fixture@crowd.invalid',joined:true}));
   }
   if(u.pathname==='/auth/v1/token')return req.respond(response({user:{id:user},access_token:'TEST_ACCESS',refresh_token:'TEST_REFRESH',expires_in:3600}));
   assert.equal(req.headers().authorization,'Bearer TEST_ACCESS');
   if(u.pathname.endsWith('_status'))return req.respond(response({participant:{status:'approved'},received:task.received,verified:0,reward_fen:0,remainder:0}));
   if(u.pathname.endsWith('_claim'))return req.respond(response({task:taskDone?null:task}));
   if(u.pathname.endsWith('_submit')){
    submissions.push(body);assert.equal(body.p_record.standard.url,'https://www.xiaohongshu.com/explore/'+id);
    task.received=1;
    if(ackLost){ackLost=false;return req.respond(response({message:'fixture_lost_ack'},503));}
    return req.respond(response({inserted:true,task_received:1}));
   }
   if(u.pathname.endsWith('_finish')){taskDone=true;return req.respond(response({status:'complete'}));}
   if(u.pathname.endsWith('_register'))return req.respond(response({registered:true}));
  }
  unexpected.push(u.origin+u.pathname);return req.respond(response({error:'unexpected_request'},403));
 });
 const current=()=>control.evaluate(()=>CrowdNative.command('state',{})).then(r=>r.data);
 const refresh=async()=>{
  if(!await control.$eval('#status',el=>el.closest('details').open))await control.click('details:has(#status) > summary');
  await control.click('#refresh');await control.waitForFunction(()=>!document.querySelector('#refresh').disabled);
 };
 await control.goto(client+'/controller.html');await control.waitForFunction(()=>typeof CrowdNative!=='undefined');
 await control.evaluate(token=>CrowdNative.receiveInvite('foodcrowd://join#invite='+token),invite);await refresh();
 await test('Puppeteer client UI: explicit consent required, no silent start',async()=>{
  await control.click('#consent');await control.waitForFunction(()=>document.querySelector('#message').textContent.includes('请先确认自愿参与'));
  assert.equal(calls.includes('begin'),false);assert.equal((await current()).agent.enabled,false);
 });
 await test('Puppeteer client UI: stop during registration prevents deferred start',async()=>{
  await control.click('#agree');await control.click('#consent');
  await Promise.race([enrollmentStarted,new Promise((_,reject)=>setTimeout(()=>reject(new Error('Enrollment did not reach backend; inspect client UI')),8000))]);
  assert.equal(await control.$eval('#stop',el=>el.disabled),false);await control.click('#stop');
  enrollRelease();holdEnroll=false;await control.waitForFunction(()=>!document.querySelector('#consent').disabled);
  assert.equal(calls.includes('begin'),false);assert.equal((await current()).agent.enabled,false);
 });
 await test('Puppeteer client UI: consent starts actual shared native runtime',async()=>{
  await control.evaluate(token=>CrowdNative.receiveInvite(token),invite);await refresh();
  if(!await control.$eval('#agree',el=>el.checked))await control.click('#agree');await control.click('#consent');
  await control.waitForFunction(()=>!document.querySelector('#consent').disabled);
  assert.equal((await current()).agent.enabled,true);assert.equal(calls.includes('begin'),true);
 });
 async function wake(){clock+=45000;await control.evaluate(async()=>{await __advance();await CrowdNative.wake();});}
 await test('Puppeteer collection: search/details/scroll/standard and extra fields; lost ack retained',async()=>{
  for(let i=0;i<12&&submissions.length===0;i++)await wake();
  assert.equal(submissions.length,1);const record=submissions[0].p_record;
  assert.equal(record.standard.like_count,12000);assert.equal(record.standard.collect_count,null);assert.equal(record.standard.author_display,null);
  assert.deepEqual(record.extra.hashtags,['清蒸鱼','上海美食']);assert.ok(record.extra.author_opinion_quotes.every(q=>record.evidence.text.includes(q)));
  assert.equal((await current()).agent.outbox.length,1);assert.equal(task.received,1);
 });
 await test('Puppeteer restart: evidence survives, explicit resume reuses the same receipt UUID',async()=>{
  await control.reload();await control.waitForFunction(()=>typeof CrowdNative!=='undefined');await refresh();
  assert.equal((await current()).agent.enabled,false);assert.equal((await current()).agent.outbox.length,1);
  await control.click('#start');await control.waitForFunction(()=>!document.querySelector('#start').disabled);
  clock+=120000;await wake();assert.equal(submissions.length,2);assert.equal(submissions[0].p_request,submissions[1].p_request);
  assert.equal((await current()).agent.outbox.length,0);assert.equal((await current()).agent.received,1);
  await refresh();assert.equal((await control.$eval('#status',el=>el.textContent)).includes('TEST_ACCESS'),false);
  await control.screenshot({path:path.join(output,'client-delivered.png'),fullPage:true});
  await wake();assert.equal((await current()).agent.task,null);
 });
 await test('Puppeteer safety: CAPTCHA pauses the batch and the UI; stop remains effective',async()=>{
  await control.click('#stop');await control.waitForFunction(()=>!document.querySelector('#stop').disabled);
  assert.equal((await current()).agent.enabled,false);
  const opens=calls.filter(x=>x==='open').length;await wake();assert.equal(calls.filter(x=>x==='open').length,opens);
  taskDone=false;task.received=0;task.id=2;mode='captcha';
  const ended=calls.filter(x=>x==='end').length;
  await control.click('#start');await control.waitForFunction(()=>!document.querySelector('#start').disabled);
  for(let i=0;i<7&&(await current()).agent.enabled;i++)await wake();
  assert.equal((await current()).agent.last_error,'captcha');assert.equal((await current()).agent.enabled,false);
  await refresh();assert.ok((await control.$eval('#welcome',el=>el.textContent)).includes('遇到验证'));
  assert.ok(calls.filter(x=>x==='end').length>ended,'CAPTCHA must end the active native batch');assert.equal(submissions.length,2);
  await control.screenshot({path:path.join(output,'client-paused.png'),fullPage:true});
 });
 assert.deepEqual(unexpected,[]);assert.deepEqual(failures,[]);
 console.log('LIMIT local production portal and actual shared controller/runtime; synthetic API/XHS/native-host fixtures, accelerated scheduling clock. No live XHS, native installation, phone or lock-screen acceptance.');
})().catch(e=>{failures.push(e.stack||e.message);console.error(e);process.exitCode=1;}).finally(async()=>{
 await fs.mkdir(output,{recursive:true});await fs.writeFile(path.join(output,'report.json'),JSON.stringify({passed:passes,failures,unexpected,submission_attempts:submissions.length,limits:['Synthetic backend and XHS responses','Mocked native OS bridge','Accelerated scheduling clock','No production writes or live platform/hardware acceptance']},null,2));
 if(browser)await browser.close();
});
