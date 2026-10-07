import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);
if(!process.env.CROWD_TEST_TOOLS) throw new Error('Set CROWD_TEST_TOOLS to the existing development tools directory');
const {PGlite}=require(path.join(process.env.CROWD_TEST_TOOLS,'node_modules/@electric-sql/pglite'));
const db=new PGlite();
const user='00000000-0000-4000-8000-000000000001',other='00000000-0000-4000-8000-000000000002';
await db.exec(`create role anon;create role authenticated;create role service_role;create schema auth;create schema crowd_v4;
create function auth.uid() returns uuid language sql as $$select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid$$;
create table crowd_v4.participants(user_id uuid primary key,status text,consent text);
insert into crowd_v4.participants values('${user}','approved','crowd-public-v4'),('${other}','approved','crowd-public-v4');`);
const migrations=path.resolve(new URL('../../cloud/supabase/migrations',import.meta.url).pathname);
const migration=fs.readdirSync(migrations).find(n=>n.endsWith('_crowd_v4_diagnostics.sql'));
await db.exec(fs.readFileSync(path.join(migrations,migration),'utf8'));
await db.exec(fs.readFileSync(path.join(migrations,fs.readdirSync(migrations).find(n=>n.endsWith('_crowd_v4_navigation_diagnostics.sql'))),'utf8'));
async function call(uid,action,revision,state=null) {
  await db.query("select set_config('request.jwt.claim.sub',$1,false)",[uid||'']);
  return (await db.query('select public.crowd_v4_diagnostics($1,$2,$3::jsonb) as result',[action,revision,state===null?null:JSON.stringify(state)])).rows[0].result;
}
const snapshot={version:'4.0.0',enabled:true,phase:'search',error:'page_timeout',task_id:1,queued:0,rejected:0,page_kind:'search',tab_status:'complete',document:'complete',gate:null,links:0,search_note_links:4,body_chars:0,visible:false};
await assert.rejects(call(null,'enable',1),/login_required/);
await assert.rejects(call(user,'report',1,snapshot),/stale_diagnostics/);
await call(user,'enable',1);await call(user,'report',1,snapshot);
await call(user,'report',1,{...snapshot,links:1});
const navigation={...snapshot,version:'4.0.3',error:'page_loading',nav_stage:'failed',nav_error:'ERR_NAME_NOT_RESOLVED',nav_age_s:4,probe_status:'no_receiver'};
await call(user,'report',1,navigation);
assert.deepEqual((await db.query('select state from crowd_v4.diagnostics')).rows[0].state,navigation);
for(const invalid of [{nav_error:'https://secret.test/token'}, {nav_stage:null}, {probe_status:'raw exception'}, {nav_age_s:86401}, {nav_age_s:-1}, {nav_age_s:'1'}, {nav_url:'private'}]) await assert.rejects(call(user,'report',1,{...navigation,...invalid}),/invalid_diagnostics/);
await call(user,'report',1,{...navigation,nav_error:null,nav_age_s:null,nav_stage:'unknown'});
await call(user,'report',1,snapshot); // Already-installed 4.0.1 remains compatible.

assert.equal((await db.query('select count(*)::int as n from crowd_v4.diagnostics')).rows[0].n,1,'only the latest snapshot is kept');
await assert.rejects(call(user,'report',1,{...snapshot,cookie:'secret'}),/invalid_diagnostics/);
await assert.rejects(call(user,'report',1,{...snapshot,error:'PRIVATE_VALUE'}),/invalid_diagnostics/);
await assert.rejects(call(user,'report',1,{...snapshot,links:-1}),/invalid_diagnostics/);
await call(other,'enable',1);await call(other,'report',1,{...snapshot,error:null});
await call(user,'disable',2);
await assert.rejects(call(user,'report',1,snapshot),/stale_diagnostics/);
await assert.rejects(call(user,'enable',1),/stale_diagnostics/,'delayed enables cannot reverse opt-out');
const rows=(await db.query('select user_id,state from crowd_v4.diagnostics order by user_id')).rows;
assert.equal(rows[0].state,null);assert.equal(rows[1].state.error,null,'one user cannot clear another snapshot');
const grants=(await db.query("select has_function_privilege('anon','public.crowd_v4_diagnostics(text,bigint,jsonb)','EXECUTE') as anon,has_function_privilege('authenticated','public.crowd_v4_diagnostics(text,bigint,jsonb)','EXECUTE') as auth,has_table_privilege('authenticated','crowd_v4.diagnostics','SELECT') as direct")).rows[0];
assert.deepEqual(grants,{anon:false,auth:true,direct:false});
await db.exec(`update crowd_v4.participants set status='suspended' where user_id='${user}'`);
await assert.rejects(call(user,'enable',3),/approval_required/);await call(user,'disable',3);
await db.close();
console.log('PASS isolated PostgreSQL diagnostics: ownership, opt-in, strict field/type allowlist, latest-only state, delayed report/enable rejected after opt-out, suspended-user clear, no anonymous/direct access');
