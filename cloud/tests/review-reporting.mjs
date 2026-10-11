import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { resolve } from 'node:path';
import { submitReport } from '../../app/lib/report.ts';
const require = createRequire(resolve(process.env.CROWD_TEST_TOOLS || '.', 'package.json'));
const { PGlite } = require('@electric-sql/pglite');
const db = new PGlite();
const migration = readFileSync(new URL('../supabase/migrations/20261011141634_secure_review_reporting.sql', import.meta.url),'utf8');
const uid = (n) => '00000000-0000-0000-0000-'+String(n).padStart(12,'0');
let checks=0;
async function ok(name, fn) { await fn(); checks++; console.log('PASS '+name); }
async function actor(n, role='authenticated') {
  await db.exec(`reset role; select set_config('request.jwt.claim.sub','${n===null?'':uid(n)}',false); select set_config('request.jwt.claims','{}',false); set role ${role};`);
}
async function report(n) { return (await db.query('select public.increment_report($1::uuid) as result',[uid(n)])).rows[0].result; }
async function count(n) { await db.exec('reset role'); return (await db.query('select report_count from reviews where id=$1',[uid(n)])).rows[0].report_count; }
try {
  await db.exec(`
    create role anon; create role authenticated; create role service_role bypassrls;
    create schema auth;
    create function auth.uid() returns uuid language sql as $$ select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid $$;
    create function auth.jwt() returns jsonb language sql as $$ select coalesce(nullif(current_setting('request.jwt.claims',true),''),'{}')::jsonb $$;
    grant usage on schema auth to anon,authenticated;
    create table reviews(id uuid primary key,user_id uuid,report_count integer default 0,is_hidden boolean default false,content text);
    alter table reviews enable row level security;
    create policy read_reviews on reviews for select using(is_hidden=false);
    create policy own_update on reviews for update to authenticated using(auth.uid()=user_id);
    create policy own_insert on reviews for insert to authenticated with check(auth.uid()=user_id);
    grant all on reviews to anon,authenticated,service_role;
    insert into reviews select ('00000000-0000-0000-0000-'||lpad(n::text,12,'0'))::uuid,
      '00000000-0000-0000-0000-000000000099',7,false,'fixture' from generate_series(1,30) n;
  `);
  await db.exec(`alter table reviews add column restaurant_id integer default 1;
    create table taste_calls (n int); grant insert on taste_calls to authenticated;
    create function public.recalc_taste_for(integer) returns void language sql as $$ insert into taste_calls values(1) $$;
    create function public.trg_reviews_taste() returns trigger language plpgsql as $$ begin perform recalc_taste_for(NEW.restaurant_id); return null; end $$;
    create trigger taste after insert or update or delete on reviews for each row execute function public.trg_reviews_taste();`);
  await db.exec(migration);
  await db.exec(readFileSync(new URL('../supabase/migrations/20261011141825_report_count_skip_taste_recalc.sql', import.meta.url),'utf8'));
  await ok('historical count unchanged',async()=>assert.equal(await count(1),7));
  await ok('anonymous execute denied',async()=>{await actor(null,'anon'); await assert.rejects(report(1),e=>e.code==='42501');});
  await ok('authenticated without UID denied',async()=>{await actor(null); await assert.rejects(report(1),e=>e.code==='42501');});
  await ok('anonymous sign-in denied',async()=>{await actor(50);await db.exec(`select set_config('request.jwt.claims','{"is_anonymous":true}',false)`);await assert.rejects(report(1),e=>e.code==='42501');});
  await ok('atomic increment and duplicate idempotency',async()=>{await actor(50);assert.deepEqual(await report(1),{accepted:true,report_count:8});assert.deepEqual(await report(1),{accepted:false,report_count:8});});
  await ok('second account increments',async()=>{await actor(51);assert.equal((await report(1)).report_count,9);});
  await ok('count-only updates skip taste recalculation',async()=>{await db.exec('reset role');assert.equal((await db.query('select count(*)::int n from taste_calls')).rows[0].n,0);await db.query('update reviews set content=$1 where id=$2',['changed',uid(1)]);assert.equal((await db.query('select count(*)::int n from taste_calls')).rows[0].n,1);});
  await ok('own direct UPDATE count denied',async()=>{await actor(99); await assert.rejects(db.exec(`update reviews set report_count=999 where id='${uid(1)}'`),e=>e.code==='42501');});
  await ok('INSERT count injection denied; normal insert retained',async()=>{await actor(99);await assert.rejects(db.query('insert into reviews(id,user_id,report_count) values($1,$2,100)',[uid(101),uid(99)]),e=>e.code==='42501');await db.query('insert into reviews(id,user_id,content) values($1,$2,$3)',[uid(101),uid(99),'normal']);});
  await ok('ledger direct access denied',async()=>{await actor(99);await assert.rejects(db.exec('select * from report_private.review_reports'),e=>e.code==='42501');});
  await ok('missing and hidden review fail',async()=>{await db.exec('reset role');await db.query('update reviews set is_hidden=true where id=$1',[uid(30)]);await actor(52);await assert.rejects(report(999),e=>e.code==='P0002');await assert.rejects(report(30),e=>e.code==='P0002');});
  await ok('20/hour limit, duplicate retry allowed at limit',async()=>{await actor(53);for(let n=1;n<=20;n++) await report(n);await assert.rejects(report(21),e=>e.code==='P0001');assert.equal((await report(1)).accepted,false);});
  await ok('database failure rolls ledger and count back',async()=>{await db.exec(`reset role; create function fail_update() returns trigger language plpgsql as $$ begin raise exception 'injected failure'; end $$; create trigger fail before update on reviews for each row execute function fail_update();`);await actor(54);await assert.rejects(report(22));await db.exec('reset role; drop trigger fail on reviews');assert.equal(await count(22),7);assert.equal((await db.query('select count(*)::int n from report_private.review_reports where reporter_id=$1',[uid(54)])).rows[0].n,0);await actor(54);assert.equal((await report(22)).accepted,true);});
  for(const code of ['PGRST202','42501','XX000']) await ok('frontend rejects '+code,async()=>{await assert.rejects(submitReport(async()=>({data:null,error:{code}}),uid(1)));});
  await ok('frontend network rejection',async()=>await assert.rejects(submitReport(async()=>{throw new Error('network')},uid(1))));
  await ok('frontend invalid/missing response rejected',async()=>{for(const data of [null,{}, {accepted:true,report_count:-1}, {accepted:true,report_count:1.1}]) await assert.rejects(submitReport(async()=>({data,error:null}),uid(1)));});
  await ok('frontend uses authoritative duplicate result',async()=>assert.deepEqual(await submitReport(async()=>({data:{accepted:false,report_count:42},error:null}),uid(1)),{accepted:false,report_count:42}));
  console.log(checks+' isolated checks passed. PGlite is single-session; real multi-session concurrency requires the separate disposable-database script.');
} finally { await db.close(); }

