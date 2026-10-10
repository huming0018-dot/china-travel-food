// PGlite integration: actual migration and privileges, simulated pg_net transport.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {resolve} from 'node:path';
const require=createRequire(resolve(process.env.CROWD_TEST_TOOLS || '.', 'package.json'));
const {PGlite}=require('@electric-sql/pglite');
const db=new PGlite();
let checks=0;
const check=(a,b)=>{assert.deepEqual(a,b); checks++;};
try {
 await db.exec(`create role anon; create role authenticated; create role service_role bypassrls;
 create schema net;
 create table net._http_response(id bigint,status_code int,content text,timed_out boolean,error_msg text);
 create table public.crowd_private_config(key text primary key,value text);
 revoke all on public.crowd_private_config from public;
 insert into public.crowd_private_config values('ops_secret','ops'),('tg_notify_secret','notify');
 create sequence public.test_requests;
 create function public.crowd_notify_tg(p_text text,p_secret text) returns jsonb language plpgsql as $$
 begin
 if p_secret is distinct from 'ops' or length(coalesce(p_text,''))=0 or length(p_text)>4000 then
 return jsonb_build_object('ok',false); end if;
 return jsonb_build_object('ok',true,'request_id',nextval('public.test_requests'));
 end $$;`);
 const sql=readFileSync(new URL('../supabase/migrations/20261010073742_telegram_notify_receipts.sql',import.meta.url),'utf8');
 await db.exec(sql); await db.exec(sql);
 const query=async(q,params=[])=>(await db.query(q,params)).rows[0];
 const send=async(text,secret)=>(await query('select public.telegram_notify_enqueue($1,$2) as r',[text,secret])).r;
 const receipt=async(id,secret)=>(await query('select public.telegram_notify_receipt($1,$2) as r',[id,secret])).r;
 check((await query("select relrowsecurity as r from pg_class where oid='public.telegram_notify_requests'::regclass")).r,true);
 check((await query("select has_table_privilege('anon','public.telegram_notify_requests','select') as r")).r,false);
 for(const role of ['anon','authenticated']) {
  await db.exec('set role '+role);
  check(await send('message','wrong'),{ok:false,reason:'forbidden'});
  check(await send('message',''),{ok:false,reason:'forbidden'});
  check(await send('','notify'),{ok:false,reason:'relay_rejected'});
  check(await send('x'.repeat(4001),'notify'),{ok:false,reason:'relay_rejected'});
  const queued=await send('message','notify'); check(queued.delivered,false);
  check(await receipt(queued.request_id,'notify'),{delivered:false,pending:true});
  check(await receipt(queued.request_id,'wrong'),{delivered:false,pending:false,reason:'forbidden'});
  check(await receipt(99999,'notify'),{delivered:false,pending:false,reason:'unknown_request'});
  await db.exec('reset role');
  await db.query('insert into net._http_response values($1,200,$2,false,null)',[queued.request_id,'{"ok":true}']);
  check(await receipt(queued.request_id,'notify'),{delivered:true,pending:false});
  for(const [code,content,timedout,error] of [[200,'{"ok":false}',false,null],[403,'{}',false,null],[200,'garbage',false,null],[200,'{"ok":true}',true,null],[null,null,false,'offline']]) {
   await db.query('update net._http_response set status_code=$2,content=$3,timed_out=$4,error_msg=$5 where id=$1',[queued.request_id,code,content,timedout,error]);
   check(await receipt(queued.request_id,'notify'),{delivered:false,pending:false});
  }
 }
 check((await send('legacy app','ops')).ok,true);
 await db.exec("delete from public.crowd_private_config where key='tg_notify_secret'");
 check(await send('message','notify'),{ok:false,reason:'forbidden'});
 check((await send('legacy app','ops')).ok,true);
 console.log(`${checks} SQL/ACL checks passed (pg_net simulated, no production messages)`);
} finally {await db.close();}
