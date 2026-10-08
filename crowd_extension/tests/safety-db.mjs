import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);
const {PGlite}=require(path.join(process.env.CROWD_TEST_TOOLS,'node_modules/@electric-sql/pglite'));
const db=new PGlite();
const users=['00000000-0000-4000-8000-000000000001','00000000-0000-4000-8000-000000000002'];
const migrations='cloud/supabase/migrations';
try {
 await db.exec(`create role anon;create role authenticated;create role service_role;create schema auth;
 create table auth.users(id uuid primary key);
 create function auth.uid() returns uuid language sql as $$select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid$$;
 create function auth.role() returns text language sql as $$select current_setting('request.jwt.claim.role',true)$$;
 grant usage on schema auth to authenticated,service_role;grant execute on function auth.uid(),auth.role() to authenticated,service_role;`);
 for(const suffix of ['20261006145016_crowd_v4.sql','_crowd_v4_diagnostics.sql','_crowd_v4_navigation_diagnostics.sql','_crowd_v4_safety.sql']) await db.exec(fs.readFileSync(path.join(migrations,fs.readdirSync(migrations).find(n=>n.endsWith(suffix))),'utf8'));
 for(const u of users){await db.query('insert into auth.users values($1)',[u]);await db.query("insert into crowd_v4.participants(user_id,status,consent) values($1,'approved','crowd-public-v4')",[u]);}
 async function call(u,action='control',note=null,task=1){
  await db.query("select set_config('request.jwt.claim.sub',$1,false)",[u]);
  await db.exec('set role authenticated');
  try{return (await db.query('select public.crowd_v4_guard($1,$2,$3) as r',[action,task,note])).rows[0].r;}finally{await db.exec('reset role');}
 }
 async function admin(payload){
  await db.exec("set role service_role;select set_config('request.jwt.claim.role','service_role',false)");
  try{return (await db.query("select public.crowd_v4_admin('control',$1::jsonb) as r",[JSON.stringify(payload)])).rows[0].r;}finally{await db.exec('reset role');}
 }
 await db.query("insert into crowd_v4.tasks(source_key,query,anchor_terms,status,claimed_by,lease_until) values('one','测试餐厅','[\"测试餐厅\"]','leased',$1,now()+interval '1 hour'),('two','测试餐厅','[\"测试餐厅\"]','leased',$2,now()+interval '1 hour')",users);
 const first=await call(users[0]);assert.deepEqual(first.caps,{search:6,detail:12,comment:24,scroll:24});assert.equal(first.paused,false);
 await db.query("update crowd_v4.participants set joined_at=now()+interval '1 day' where user_id=$1",[users[0]]);
 assert.equal((await call(users[0])).caps.search,6,'future enrollment is conservative');
 await db.query("update crowd_v4.participants set joined_at=now()-interval '7 days'");
 assert.equal((await call(users[0])).caps.search,30);
 assert.equal((await call(users[0],'search')).allowed,true);
 assert.equal((await call(users[0],'search')).reason,'action_gap');
 assert.equal((await call(users[0])).counts.search,1,'failed navigation stays charged; polls do not redraw wait');
 await db.exec("update crowd_v4.safety set next_action=now()-interval '1 second'");
 const note='abcdef0123456789abcdef01';
 assert.equal((await call(users[0],'detail',note)).allowed,true);
 assert.equal((await call(users[1],'detail',note,2)).reason,'note_busy');
 assert.equal((await call(users[1])).counts.detail,0,'skipped duplicate costs no visit');
 await db.exec("update crowd_v4.note_reservations set expires_at=now()-interval '1 second'");
 assert.equal((await call(users[1],'detail',note,2)).allowed,true,'expired reservation is recoverable');
 await db.query("insert into crowd_v4.proofs(note_id,user_id,task_id,record) values($1,$2,1,'{}')",[note,users[0]]);
 await db.exec("update crowd_v4.safety set next_action=now()-interval '1 second'");
 assert.equal((await call(users[0],'detail',note)).reason,'known_note');
 await assert.rejects(call(users[0],'detail','invalid'),/invalid_note/);
 assert.equal((await call(users[0],'search',null,2)).error,'lease_expired','cannot spend against someone else\'s task');
 await db.exec("update crowd_v4.safety set counts=jsonb_set(counts,'{search}','30')");
 assert.equal((await call(users[0],'search')).reason,'action_budget');
 await db.exec("update crowd_v4.safety set day=(now() at time zone 'Asia/Shanghai')::date-1");
 assert.equal((await call(users[0],'search')).allowed,true,'Shanghai day rollover resets attempts');
 await db.exec("update crowd_v4.safety set next_action=now(),session_count=20");
 const rest=await call(users[0],'scroll');assert.equal(rest.reason,'session_rest');assert.ok(rest.wait_ms>=1799000);
 const risk=await call(users[0],'rate_limit');assert.equal(risk.reason,'rate_limit');assert.ok(risk.wait_ms>=86399000);
 // Fetching control or using a different task does not clear a hard cooldown.
 assert.equal((await call(users[0],'search')).reason,'rate_limit');
 assert.equal((await call(users[0])).reason,'rate_limit');
 await db.exec("update crowd_v4.safety set cooldown_until=now()-interval '1 second',next_action=now()-interval '1 second'");
 const paused=await admin({paused:true,search_cap:10});assert.equal(paused.version,2);
 assert.equal((await call(users[0])).paused,true);assert.equal((await call(users[0],'search')).reason,'global_pause');
 const resumed=await admin({paused:false});assert.equal(resumed.version,3);assert.equal((await call(users[0])).paused,false,'control remains available while paused');
 await assert.rejects(admin({search_cap:31}),/check constraint/);
 await assert.rejects(admin({gap_seconds:1}),/check constraint/);
 await assert.rejects(admin({evil:'execute'}),/invalid_control/);
 assert.equal((await call(users[0])).caps.search,10,'failed policy transaction cannot loosen caps');
 const permissions=(await db.query("select has_function_privilege('anon','public.crowd_v4_guard(text,bigint,text)','execute') as anon,has_table_privilege('authenticated','crowd_v4.safety','update') as edit,has_function_privilege('authenticated','public.crowd_v4_admin(text,jsonb)','execute') as admin")).rows[0];
 assert.deepEqual(permissions,{anon:false,edit:false,admin:false});
 await db.query("update crowd_v4.participants set status='suspended' where user_id=$1",[users[0]]);
 await assert.rejects(call(users[0]),/approval_required/);
 console.log('PASS isolated PostgreSQL safety: pre-debit, persistent gap/cooldown, warmup, Shanghai daily cap, session rest, duplicate reservations, expired recovery, pause/resume policy, hard ceilings and privileges');
} finally {await db.close();}
