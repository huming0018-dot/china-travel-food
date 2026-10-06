'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path'),crypto=require('node:crypto');
const root=path.resolve(__dirname,'../..'),ts=require(path.join(root,'app/node_modules/typescript'));
const portal='https://crowd.example.test',invite='a'.repeat(64),password='b'.repeat(64),user='00000000-0000-4000-8000-000000000001';
const release={channel:'apk',url:portal+'/crowd/releases/crowd-android-v4.0.0-debug.apk',version:'4.0.0',sha256:'c'.repeat(64),verified:true};
const env={NEXT_PUBLIC_SUPABASE_URL:'https://test.supabase.co',SUPABASE_SERVICE_ROLE_KEY:'SERVER_TEST_ONLY',CROWD_PUBLIC_ORIGIN:portal,CROWD_OPERATOR_KEY:'d'.repeat(64),CROWD_RELEASES_JSON:JSON.stringify({android:release})};
let account=null,failCreate=true,creates=0,calls=[];
const client={rpc:async(name,p)=>{calls.push({name,p});return {data:p.p_action==='reserve'?{user_id:user}:p.p_action==='list'?[]:{joined:true},error:null};},auth:{admin:{getUserById:async()=>({data:{user:account}}),createUser:async p=>{creates++;if(!failCreate)account=p;return {data:{user:account}};}}}};
function load(file,imports={}) {
 const module={exports:{}};
 const source=ts.transpileModule(fs.readFileSync(path.join(root,file),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
 vm.runInNewContext(source,{module,exports:module.exports,require:name=>imports[name]||require(name.startsWith('qrcode')?path.join(root,'app/node_modules/qrcode'):name),process:{env},Buffer,URL,Error,console});
 return module.exports;
}
const server=load('app/lib/crowd-server.ts',{'@supabase/supabase-js':{createClient:()=>client},'./crowd-gateway':load('app/lib/crowd-gateway.ts')});
const enroll=load('app/pages/api/crowd/enroll.ts',{'@/lib/crowd-server':server}).default;
const publish=load('app/pages/api/crowd/invite.ts',{'@/lib/crowd-server':server}).default;
const manifest=load('app/pages/api/crowd/manifest.ts',{'@/lib/crowd-server':server}).default;
async function request(handler,body={},headers={origin:'null'},method='POST') {
 const response={code:200,headers:{},status(code){this.code=code;return this;},json(body){this.body=body;return this;},end(){return this;},setHeader(name,value){this.headers[name]=value;}};
 await handler({body,headers,method},response);return response;
}
(async()=>{
 const payload={invite,install_secret:password,consent:'crowd-public-v4',platform:'android'};
 assert.equal((await request(enroll,payload,{origin:'https://attacker.example.test'})).code,403);
 assert.equal(calls.length,0);
 assert.equal((await request(enroll,{...payload,consent:false})).body.error,'consent_required');
 assert.equal((await request(enroll,{...payload,invite:[invite]})).body.error,'invalid_request');
 assert.equal((await request(enroll,{...payload,platform:'ios'})).body.error,'release_not_ready');
 assert.equal((await request(enroll,payload)).code,503,'interrupted Auth creation must not fake success');
 assert.equal(calls.some(x=>x.p.p_action==='complete'),false);
 failCreate=false;const result=await request(enroll,payload);assert.equal(result.code,200);assert.equal(result.body.joined,true);
 assert.equal(account.id,user);assert.equal(account.password,'Cr4!'+password);assert.equal(account.email,result.body.email);assert.equal(account.email,crypto.createHash('sha256').update(password).digest('hex')+'@crowd.invalid');
 const before=creates;await request(enroll,payload);assert.equal(creates,before,'retry must not reset an existing Auth password');
 assert.equal(JSON.stringify(calls).includes(invite),false);assert.equal(JSON.stringify(calls).includes(password),false,'SQL only receives hashes');
 assert.equal((await request(publish,{},{})).code,403);
 assert.equal((await request(publish,{max_people:501},{authorization:'Bearer '+env.CROWD_OPERATOR_KEY})).code,400);
 const minted=await request(publish,{}, {authorization:'Bearer '+env.CROWD_OPERATOR_KEY});assert.equal(minted.code,200);assert.ok(minted.body.link.startsWith(portal+'/crowd#invite='));assert.ok(minted.body.qr.startsWith('data:image/png;base64,'));
 const live=await request(manifest,{}, {},'GET');assert.equal(live.body.ready,true);assert.equal(JSON.stringify(live.body).includes(env.SUPABASE_SERVICE_ROLE_KEY),false);
 env.CROWD_RELEASES_JSON=JSON.stringify({android:{...release,verified:false}});assert.equal((await request(publish,{}, {authorization:'Bearer '+env.CROWD_OPERATOR_KEY})).body.error,'release_not_ready');
 const context=vm.createContext({URL,URLSearchParams,Uint8Array,crypto:crypto.webcrypto,navigator:{userAgent:'Android',platform:'Linux',maxTouchPoints:5}});
 for(const name of ['core','join'])vm.runInContext(fs.readFileSync(path.join(root,'crowd_extension/src/'+name+'.js'),'utf8'),context);
 const J=context.CrowdJoin;assert.equal(J.platform(),'android');assert.equal(J.platform({userAgent:'Macintosh',platform:'MacIntel',maxTouchPoints:5}),'ios');assert.equal(J.platform({userAgent:'HarmonyOS',platform:'',maxTouchPoints:5}),'harmony');assert.equal(J.platform({userAgent:'Windows NT',platform:'Win32'}),'windows');
 assert.equal(J.invite(portal+'/crowd#invite='+invite,portal),invite);assert.equal(J.invite('foodcrowd://join#invite='+invite,portal),invite);assert.throws(()=>J.invite('https://evil.example.test/crowd#invite='+invite,portal));
 let state={},outgoing=[];const storage={get:async k=>state[k],set:async(k,v)=>state[k]=v};
 const api={config:{portal,platform:'android'},enroll:async p=>{outgoing.push(p);return {email:'test@crowd.invalid'};},login:async(email,p)=>{assert.equal(p,'Cr4!'+state.install_secret);}};
 await J.join(api,storage,invite);await J.join(api,storage,invite);assert.equal(outgoing[0].install_secret,outgoing[1].install_secret);assert.equal(state.pending_invite,null);
 console.log('PASS join/API: private origin, explicit consent, release readiness, retryable Auth creation, hashed SQL identity, no token exposure, QR invitation, OS detection, stable installation identity');
})().catch(e=>{console.error(e);process.exitCode=1;});
