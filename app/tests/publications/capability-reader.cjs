// Run: node app/tests/publications/capability-reader.cjs [app-root] [dependency-app-root]
const fs=require('fs'),path=require('path'),vm=require('vm'),assert=require('assert/strict'),crypto=require('crypto');
const ROOT=__dirname, APP=path.resolve(process.argv[2]||path.join(ROOT,'../..')), DEP=path.join(path.resolve(process.argv[3]||APP),'node_modules');
const ts=require(DEP+'/typescript');const bodies={json:Buffer.from(JSON.stringify({project_id:'shanghai-existing-six-domain',as_of:'controlled',items:[{draft:{subject_name:'真实形状合成候选'},scope:{kind:'discovery_candidate'},unknowns:['taste_unknown'],refs:{raw:'retained'}}]})),html:Buffer.from('<html>原字节</html>'),jsonl:Buffer.from('{"test":true}\n'),csv:Buffer.from('name\n受控\n')};
const hash=b=>crypto.createHash('sha256').update(b).digest('hex'),rid=hash(bodies.json);const now=Date.now();
const delivery={schema:'crowd-publication-links-v1',owner_scope:'crowd-owner-main',report_hash:rid,project_id:'shanghai-existing-six-domain',issued_at:new Date(now).toISOString(),expires_at:new Date(now+900000).toISOString(),expires_in:900,formats:{},media_bytes_included:false};
const mimes={json:'application/json; charset=utf-8',html:'text/html; charset=utf-8',jsonl:'application/x-ndjson; charset=utf-8',csv:'text/csv; charset=utf-8'};
for(const f of Object.keys(bodies))delivery.formats[f]={sha256:hash(bodies[f]),bytes:bodies[f].length,mime:mimes[f],signed_url:`https://bdwrhshgdeghgyzwpxnl.supabase.co/storage/v1/object/sign/crowd-publication-snapshots/publications/crowd-owner-main/${rid}/report.${f}?token=controlled.not-real.token&download=`};
let calls=[], mode='normal';const fakeFetch=async(url,o)=>{calls.push(url);assert.equal(o.credentials,'omit');assert.equal(o.referrerPolicy,'no-referrer');assert.equal(o.redirect,'error');assert.equal(o.cache,'no-store');assert(!o.headers);const f=new URL(url).pathname.split('.').pop();return new Response(mode==='tamper'?Buffer.alloc(bodies[f].length):mode==='long'?Buffer.alloc(bodies[f].length+1):bodies[f],{status:mode==='http'?403:200});};
const m={exports:{}};const code=ts.transpileModule(fs.readFileSync(APP+'/lib/publication-capability.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES5}}).outputText;
vm.runInNewContext('(function(exports){'+code+'})',{URL,TextDecoder,Uint8Array,AbortController,atob,fetch:fakeFetch,crypto:crypto.webcrypto})(m.exports);
const api=m.exports,copy=()=>JSON.parse(JSON.stringify(delivery)); const fragment='#publication='+Buffer.from(JSON.stringify(delivery)).toString('base64url');
(async()=>{
 assert.equal(api.parseFragment(fragment).report_hash,rid);const c=new AbortController();for(const f of Object.keys(bodies))assert.deepEqual(Buffer.from(await api.verifiedBytes(api.parseFragment(fragment),f,c.signal,()=>true)),bodies[f]);
 assert.equal(api.reportFromBytes(bodies.json,delivery).items.length,1);
 for(const mutate of [x=>x.expires_in=901,x=>x.formats.json.bytes=true,x=>x.formats.json.signed_url=x.formats.json.signed_url.replace('bdwrhshgdeghgyzwpxnl.supabase.co','evil.invalid'),x=>x.formats.html.signed_url=x.formats.html.signed_url.replace('/report.html','/report.json'),x=>x.formats.csv.signed_url+='&other=x',x=>x.media_bytes_included=true,x=>x.report_hash='0'.repeat(64)]){let v=copy();mutate(v);assert.throws(()=>api.parseFragment('#publication='+Buffer.from(JSON.stringify(v)).toString('base64url')));}
 assert.throws(()=>api.parseFragment(fragment,now+900001),/link_expired/);assert.throws(()=>api.parseFragment('#publication=%%%%'));
 for(mode of ['tamper','long','http'])await assert.rejects(api.verifiedBytes(api.parseFragment(fragment),'json',c.signal,()=>true));
 mode='normal';const before=calls.length;await assert.rejects(api.verifiedBytes(api.parseFragment(fragment),'json',c.signal,()=>false),/link_changed/);assert.equal(calls.length,before);
 const inf=Buffer.from('{"project_id":"shanghai-existing-six-domain","items":[],"value":1e999}');assert.throws(()=>api.reportFromBytes(inf,delivery));
 console.log('PASS synthetic strict 9-key/4-path/TTL + four exact bytes/hash + corruption/size/HTTP/stale/no-fetch/finite JSON');
})().catch(e=>{console.error(e);process.exitCode=1;});
module.exports={delivery,fragment,bodies,DEP,APP,api};
