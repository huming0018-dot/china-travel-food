import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import fs from 'node:fs';
import vm from 'node:vm';
import { handleAccess } from '../../cloud/supabase/functions/crowd-access/core.mjs';
import { digest } from '../../cloud/supabase/functions/crowd-gateway/core.mjs';
const require=createRequire(import.meta.url),owner='1'.repeat(64),expected=await digest(owner),invite='2'.repeat(64),secret='3'.repeat(64);
const id='00000000-0000-4000-8000-000000000001',origin='https://crowd.example.test';
const configuration={origin,releases:{},previewOrigins:['https://preview.example.test']};
let calls=[],account=null,creates=0,expired=false;
const proof={proof_id:7,record:{standard:{note_id:'a'.repeat(24)},extra:{custom_field:'保留非标字段'},evidence:{text:'保留原文证据'}}};
const backend={rpc:async(name,args)=>{calls.push({name,args});return expired&&args.p_action==='reserve'?{data:null,error:{message:'invite_expired'}}:{data:args.p_action==='reserve'?{user_id:id}:name==='crowd_v4_admin'?[proof]:[],error:null};},auth:{admin:{getUserById:async()=>({data:{user:account},error:null}),createUser:async(user)=>{
  if ((user.user_metadata?.username ?? user.email).length > 50) return {data:{user:null},error:{message:'value too long for type character varying(50)'}};
  creates++;account=user;return {data:{user},error:null};}}}};
async function request(route,input,headers={}) {
  return handleAccess(new Request('https://test.supabase.co/functions/v1/crowd-access/'+route,{method:input===undefined?'GET':'POST',headers:{'Content-Type':'application/json',...headers},...(input===undefined?{}:{body:JSON.stringify(input)})}),backend,configuration,expected);
}
assert.equal((await request('manifest')).status,200);
assert.equal((await (await request('manifest')).json()).ready,false);
assert.equal((await request('manifest',undefined,{Origin:'https://attacker.example.test'})).status,403);
assert.equal((await request('invite',{})).status,403);assert.equal((await request('operations',{action:'export'})).status,403);
assert.equal((await request('invite',{}, {Authorization:'Bearer '+owner})).status,400,'closed channels cannot issue invitations');
assert.equal((await request('operations',{action:'pay'}, {Authorization:'Bearer '+owner})).status,400);
assert.equal((await request('operations',{action:'admin',name:'unrelated_rpc'}, {Authorization:'Bearer '+owner})).status,400);
const exported=await (await request('operations',{action:'export',payload:{after_id:0}},{Authorization:'Bearer '+owner})).json();
assert.deepEqual(exported.data,[proof]);assert.equal(JSON.stringify(exported).includes(owner),false);
assert.equal((await request('enroll',{invite,install_secret:secret,consent:'wrong',platform:'android'})).status,400);
const trialPayload={invite,install_secret:secret,consent:'crowd-public-v4',platform:'macos'};
configuration.macTrial={token_hash:await digest(invite),expires_at:new Date(Date.now()+60000).toISOString()};
const extensionId='a'.repeat(32),extensionOrigin='chrome-extension://'+extensionId;
assert.equal((await request('enroll',trialPayload,{Origin:extensionOrigin})).status,403,'unconfigured extensions cannot enroll');
configuration.macTrial.channel='extension';configuration.macTrial.extension_id=extensionId;
trialPayload.client='extension';trialPayload.extension_id=extensionId;
const preflight=await handleAccess(new Request('https://test.supabase.co/functions/v1/crowd-access/enroll',{method:'OPTIONS',headers:{Origin:extensionOrigin}}),backend,configuration,expected);
assert.equal(preflight.status,204);assert.equal(preflight.headers.get('Access-Control-Allow-Origin'),extensionOrigin);
assert.equal((await request('enroll',{...trialPayload,client:'desktop'})).status,400,'old desktop kit cannot consume the extension trial');
assert.equal((await request('enroll',{...trialPayload,extension_id:'b'.repeat(32)})).status,400);
assert.equal((await request('enroll',trialPayload,{Origin:'chrome-extension://'+'b'.repeat(32)})).status,403);
assert.equal((await (await request('manifest')).json()).ready,false,'internal trial never opens the formal manifest');
assert.equal((await request('enroll',{...trialPayload,invite:'9'.repeat(64)})).status,400);
assert.equal((await request('enroll',{...trialPayload,platform:'windows'})).status,400);
expired=true;assert.equal((await request('enroll',trialPayload)).status,400,'trial still checks the database invitation');expired=false;
assert.equal((await request('enroll',trialPayload,{Origin:extensionOrigin})).status,200);
configuration.macTrial.expires_at=new Date(Date.now()-1000).toISOString();
assert.equal((await request('enroll',trialPayload)).status,400);
assert.equal((await request('enroll',trialPayload,{Origin:extensionOrigin})).status,403,'expired trial no longer grants its extension origin');
assert.equal((await request('invite',{}, {Authorization:'Bearer '+owner})).status,400,'trial never permits formal invitation minting');
delete configuration.macTrial;

// Use the shipped browser API, not a hand-crafted enrollment request.
configuration.macTrial={channel:'extension',extension_id:extensionId,token_hash:await digest(invite),expires_at:new Date(Date.now()+60000).toISOString()};
const browser=vm.createContext({URL,AbortController,setTimeout,clearTimeout,chrome:{runtime:{id:extensionId,getURL:name=>extensionOrigin+'/'+name}},fetch:async(url,options)=>{
  assert.equal(url,'https://test.supabase.co/functions/v1/crowd-access/enroll');
  assert.equal(options.headers.apikey,'sb_publishable_TEST_ONLY');
  assert.equal(options.credentials,'omit');
  assert.equal(options.headers.Authorization,undefined);
  return handleAccess(new Request(url,{...options,headers:{...options.headers,Origin:extensionOrigin}}),backend,configuration,expected);
}});
vm.runInContext(fs.readFileSync(new URL('../src/api.js',import.meta.url),'utf8'),browser);
const actualAPI=new browser.CrowdAPI({url:'https://test.supabase.co',key:'sb_publishable_TEST_ONLY',portal:origin},{get:async()=>null,set:async()=>{}});
assert.equal((await actualAPI.enroll({invite,install_secret:secret,consent:'crowd-public-v4',platform:'macos'})).joined,true);
delete configuration.macTrial;
configuration.releases.android={channel:'apk',version:'4.0.0',verified:true,url:origin+'/crowd/releases/crowd-android-v4.0.0-debug.apk',sha256:'a'.repeat(64)};
configuration.releases.ios={channel:'apk',version:'4.0.0',verified:true,url:origin+'/crowd/releases/fake.ipa',sha256:'a'.repeat(64)};
assert.deepEqual(Object.keys((await (await request('manifest')).json()).releases),['android'],'unsupported channels remain closed');
const minted=await (await request('invite',{}, {Authorization:'Bearer '+owner})).json();
assert.ok(minted.link.startsWith(origin+'/crowd#invite='));
const mintedToken=new URLSearchParams(new URL(minted.link).hash.slice(1)).get('invite');
assert.equal(JSON.stringify(calls).includes(mintedToken),false);
const payload={invite,install_secret:secret,consent:'crowd-public-v4',platform:'android'};
const joined=await (await request('enroll',payload,{Origin:'https://crowd.local'})).json();assert.equal(joined.joined,true);
assert.equal(joined.email,await digest(secret)+'@crowd.invalid');assert.equal(creates,1);
assert.equal((await request('enroll',payload)).status,200);assert.equal(creates,1,'retry never resets an existing password');
assert.equal(JSON.stringify(calls).includes(secret),false);assert.equal(JSON.stringify(calls).includes(invite),false);
expired=true;assert.equal((await request('enroll',payload)).status,400);expired=false;
assert.equal((await request('invite',{padding:'x'.repeat(5000)}, {Authorization:'Bearer '+owner})).status,400);

// Exercise the actual Next server adapter against the handler. No private
// deployment environment is configured; only the public project key is used.
const ts=require('../../app/node_modules/typescript'),module={exports:{}};
const environment={NEXT_PUBLIC_SUPABASE_URL:'https://test.supabase.co',NEXT_PUBLIC_SUPABASE_ANON_KEY:'sb_publishable_TEST_ONLY',SUPABASE_SERVICE_ROLE_KEY:'UNRELATED_SERVER_CREDENTIAL_TEST_ONLY'};
const source=ts.transpileModule(fs.readFileSync(new URL('../../app/lib/crowd-access.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
vm.runInNewContext(source,{module,exports:module.exports,process:{env:environment},URL,AbortSignal,fetch:(url,options)=>handleAccess(new Request(url,options),backend,configuration,expected)});
assert.equal(module.exports.privateBackendConfigured(),false);
environment.CROWD_DIRECT_BACKEND='1';assert.equal(module.exports.privateBackendConfigured(),true);delete environment.CROWD_DIRECT_BACKEND;
assert.equal((await module.exports.accessRequest('manifest')).ready,true);
await assert.rejects(module.exports.accessRequest('operations',{action:'export'}),/operator_required/);
assert.deepEqual((await module.exports.accessRequest('operations',{action:'export'},'Bearer '+owner)).data,[proof]);

// The optional direct-backend Next route must also survive the same profile trigger.
account=null;
const enrollment={exports:{}};
const directHashes={[invite]:await digest(invite),[secret]:await digest(secret)};
vm.runInNewContext(ts.transpileModule(fs.readFileSync(new URL('../../app/pages/api/crowd/enroll.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,{
  module:enrollment,exports:enrollment.exports,
  require:name=>name==='@/lib/crowd-access'?{privateBackendConfigured:()=>true}:{
    adminClient:()=>backend,cors:()=>{},failure:(res,e)=>res.status(503).json({error:e.message}),
    hash:value=>directHashes[value],platforms:['android'],
    releases:()=>({android:{}}),inviteRPC:async(client,action,data)=>(await client.rpc('crowd_v4_invite',{p_action:action,p_payload:data})).data
  }
});
let directStatus=200,directBody;
const res={status:n=>{directStatus=n;return res;},json:data=>{directBody=data;return res;}};
await enrollment.exports.default({method:'POST',body:payload},res);
assert.equal(directStatus,200);assert.equal(directBody.joined,true);
assert.equal(directBody.email,await digest(secret)+'@crowd.invalid');
assert.equal(account.user_metadata.username,'crowd-'+id);
console.log('PASS public access: invitation-bound enrollment, owner-only operations, closed unverified channels, strict release URLs, stable Auth retry, source-field export, no private deployment env, actual Next adapter');
