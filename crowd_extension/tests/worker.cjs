'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const src=path.resolve(__dirname,'../src'); let listener, installed, accesses=[],fetches=[];const data={};
const chrome={runtime:{id:'test-extension',getURL:x=>'chrome-extension://test-extension/'+x,
 onMessage:{addListener:fn=>listener=fn},onStartup:{addListener:()=>{}},onInstalled:{addListener:fn=>installed=fn}},
 storage:{local:{get:async key=>({[key]:structuredClone(data[key])}),set:async value=>Object.assign(data,structuredClone(value)),setAccessLevel:async value=>accesses.push(value.accessLevel)}},
 alarms:{create:async()=>{},clear:async()=>{},onAlarm:{addListener:()=>{}}},
 tabs:{onRemoved:{addListener:()=>{}},create:async()=>({id:77}),update:async()=>{},sendMessage:async()=>({ready:false}),remove:async()=>{}}};
const context=vm.createContext({chrome,console,URL,Date,Math,AbortController,crypto:require('node:crypto').webcrypto,setTimeout,clearTimeout,
 fetch:async(url,options)=>{fetches.push({url,options});return {ok:true,json:async()=>({participant:{status:'approved'}})};}});
context.importScripts=(...names)=>{for(const name of names){if(name==='config.js')context.CROWD_CONFIG={url:'https://test.supabase.co',key:'sb_publishable_test'};else vm.runInContext(fs.readFileSync(path.join(src,name),'utf8'),context);}};
vm.runInContext(fs.readFileSync(path.join(src,'background.js'),'utf8'),context);
(async()=>{
 installed();await new Promise(r=>setImmediate(r));assert.equal(fetches.length,0,'installation must not start collection');assert.deepEqual(accesses,['TRUSTED_CONTEXTS']);
 let leaked=false;const result=listener({type:'state'},{id:chrome.runtime.id,url:'https://www.xiaohongshu.com/explore/abcdef0123456789abcdef01',tab:{id:77,url:'https://www.xiaohongshu.com/'}},()=>leaked=true);assert.equal(result,undefined);assert.equal(leaked,false);
 const state=await new Promise(resolve=>listener({type:'state'},{id:chrome.runtime.id,url:chrome.runtime.getURL('src/controller.html')},resolve));assert.equal(state.ok,true);assert.equal(state.data.session,false);assert.equal(state.data.agent.enabled,false);
 // The returned UI status never contains session tokens.
 data.session={user:{id:'one'},access_token:'USER_ACCESS',refresh_token:'USER_REFRESH',expires_at:Date.now()+3600000};
 const signed=await new Promise(resolve=>listener({type:'state'},{id:chrome.runtime.id,url:chrome.runtime.getURL('src/controller.html')},resolve));
 assert.equal(JSON.stringify(signed).includes('USER_ACCESS'),false);assert.equal(fetches[0].options.headers.Authorization,'Bearer USER_ACCESS');
 // Firefox event pages load background.scripts and have neither importScripts nor setAccessLevel.
 const manifest=JSON.parse(fs.readFileSync(path.join(src,'../manifest.json')));
 const firefox={...chrome,runtime:{...chrome.runtime,getURL:x=>'moz-extension://test-extension/'+x},storage:{local:{get:async()=>({}),set:async()=>{}}}};
 const page=vm.createContext({chrome:firefox,console,URL,Date,Math,AbortController,crypto:require('node:crypto').webcrypto,setTimeout,clearTimeout,fetch:()=>{throw new Error('Unexpected anonymous request');}});
 for(const file of manifest.background.scripts) {
  if(file==='src/config.js') page.CROWD_CONFIG={url:'https://test.supabase.co',key:'sb_publishable_test'};
  else vm.runInContext(fs.readFileSync(path.join(src,'../',file),'utf8'),page);
 }
 const idle=await new Promise(resolve=>listener({type:'state'},{id:firefox.runtime.id,url:firefox.runtime.getURL('src/controller.html')},resolve));
 assert.equal(idle.ok,true);assert.equal(idle.data.agent.enabled,false);
 console.log('PASS Firefox event-page source adapter: dependency order, capability checks, idle state without anonymous network access');
 console.log('PASS MV3 source adapter: no auto-start, trusted storage, content-page command denial, authenticated RPC, no UI token exposure');
 console.log('LIMIT: Chrome API mock; native extension-engine installation remains an acceptance item');
})().catch(e=>{console.error(e);process.exitCode=1});
