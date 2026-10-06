import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const tools=process.env.CROWD_TEST_TOOLS;
const {chromium:playwright}=await import(pathToFileURL(tools+'/node_modules/playwright/index.mjs'));
const executable=process.env.CROWD_CHROMIUM || await (await import(pathToFileURL(tools+'/node_modules/@sparticuz/chromium/build/index.js'))).default.executablePath();
const browser=await playwright.launch({executablePath:executable,args:['--no-sandbox','--no-zygote','--disable-dev-shm-usage'],headless:true});
const src=path.resolve('crowd_extension/src');
const id='abcdef0123456789abcdef01';
const note=`<!doctype html><html><body><section class="note-container"><h1 id="detail-title">测试餐厅清蒸鱼</h1><div id="detail-desc">测试餐厅的清蒸鱼真的好吃，价格合理。\n#清蒸鱼 #上海美食\n排队有些长，但服务很好。</div><span class="date">2026-10-05</span></section><div class="interact-container"><span class="like-wrapper"><span class="count">1.2万</span></span></div></body></html>`;
try {
 const page=await browser.newPage();
 await page.route('https://*.xiaohongshu.com/**',route=>route.fulfill({status:200,contentType:'text/html; charset=utf-8',body:route.request().url().includes('search_result')?`<a href="/explore/${id}?xsec_token=navigation-only">测试餐厅清蒸鱼</a>`:note}));
 await page.goto('https://www.xiaohongshu.com/search_result?keyword=测试餐厅');
 async function inject(){for(const name of ['core','content'])await page.addScriptTag({content:fs.readFileSync(path.join(src,name+'.js'),'utf8')});}
 await inject();let search=await page.evaluate(()=>CrowdPage.probe('search'));assert.equal(search.ready,true);assert.equal(search.links.length,1);
 await page.goto(search.links[0]);await inject();let result=await page.evaluate(()=>CrowdPage.probe('note'));
 assert.equal(result.ready,true);assert.equal(result.record.standard.note_id,id);assert.equal(result.record.standard.url.includes('xsec_token'),false);
 assert.equal(result.record.standard.like_count,12000);assert.equal(result.record.standard.collect_count,null);assert.equal(result.record.extra.hashtags[0],'清蒸鱼');assert.ok(result.record.extra.author_opinion_quotes.every(q=>result.record.evidence.text.includes(q)));
 // Ordinary note discussion about "频繁" must not accidentally trigger rate-limit detection.
 await page.locator('#detail-desc').evaluate(el=>el.innerText+=' 我频繁来吃饭。');assert.equal((await page.evaluate(()=>CrowdPage.probe('note'))).gate,undefined);
 await page.locator('body').evaluate(el=>el.insertAdjacentHTML('beforeend','<div class="error-page">访问频繁，请稍后再试</div>'));
 assert.equal((await page.evaluate(()=>CrowdPage.probe('note'))).gate,'rate_limit');
 await page.locator('.error-page').evaluate(el=>el.innerHTML='<div class="captcha">验证码</div>');assert.equal((await page.evaluate(()=>CrowdPage.probe('note'))).gate,'captcha');
 await page.locator('.error-page').evaluate(el=>el.innerHTML='<div class="login-modal"><input placeholder="手机号"></div>');assert.equal((await page.evaluate(()=>CrowdPage.probe('note'))).gate,'login_required');
 await page.locator('.error-page').evaluate(el=>el.remove());
 await page.goto('https://m.xiaohongshu.com/discovery/item/'+id+'?xsec_token=navigation-only');await inject();
 const mobile=await page.evaluate(()=>CrowdPage.probe('note'));
 assert.equal(mobile.ready,true);assert.equal(mobile.record.standard.url,'https://www.xiaohongshu.com/explore/'+id);
 assert.equal(mobile.record.evidence.text,result.record.evidence.text);
 // Drive the actual shared agent through real navigation + DOM probes, then reload its runtime.
 for(const name of ['core','agent'])await page.addScriptTag({content:fs.readFileSync(path.join(src,name+'.js'),'utf8')});
 let clock=Date.now(),state={},uploads=[],phase='';
 const host=await browser.newPage();
 await host.route('https://www.xiaohongshu.com/**',route=>route.fulfill({status:200,contentType:'text/html; charset=utf-8',body:route.request().url().includes('search_result')?`<a href="/explore/${id}">测试餐厅</a>`:note}));
 const vm=await import('node:vm');
 const context=vm.createContext({console,AbortController,URL,Date,Math,setTimeout,clearTimeout});
 for(const name of ['core','agent'])vm.runInContext(fs.readFileSync(path.join(src,name+'.js'),'utf8'),context);
 const runtime={storage:{get:async k=>structuredClone(state[k]),set:async(k,v)=>state[k]=structuredClone(v)},now:()=>clock,random:()=>0,uuid:()=>crypto.randomUUID(),schedule:async()=>{},cancel:async()=>{},close:async()=>{},open:async url=>{
  await host.goto(url);for(const name of ['core','content'])await host.addScriptTag({content:fs.readFileSync(path.join(src,name+'.js'),'utf8')});
 },probe:async action=>host.evaluate(action=>CrowdPage.probe(action),action)};
 const task={id:1,query:'测试餐厅',received:0,target:1,lease_token:crypto.randomUUID(),lease_until:new Date(clock+1200000).toISOString()};
 const api={rpc:async(name,p)=>name==='claim'?{task}:name==='status'?{participant:{status:'approved'}}:name==='submit'?(uploads.push(p),{inserted:true,task_received:1}):{status:'complete'}};
 state.agent={...context.CrowdCore.initial(),consent:context.CrowdCore.CONSENT};let agent=new context.CrowdAgent(runtime,api);await agent.start();
 for(let i=0;i<10;i++){await agent.tick();clock+=45000;if(i===5)agent=new context.CrowdAgent(runtime,api);}
 assert.equal(uploads.length,1);assert.equal(uploads[0].p_record.extra.hashtags.length,2);assert.equal(state.agent.received,1);
 console.log('PASS Chromium: real DOM, automatic search/navigation/dwell/extraction/upload, reconstructed agent, standard/extra/null fields, gate detection');
 console.log('LIMIT: fixtures, not live Xiaohongshu or Windows/macOS/iOS/Harmony hardware acceptance');
}finally{await browser.close();}
