// Use ONLY a disposable PostgreSQL database: this test resets public/auth/report_private.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { resolve } from 'node:path';
const require = createRequire(resolve(process.env.CROWD_TEST_TOOLS || '.', 'package.json'));
const { Client } = require('pg');
if (!process.env.REPORT_TEST_DATABASE_URL || process.env.REPORT_TEST_DISPOSABLE !== 'yes') {
  throw new Error('Set REPORT_TEST_DATABASE_URL to an isolated disposable database and REPORT_TEST_DISPOSABLE=yes');
}
const config={connectionString:process.env.REPORT_TEST_DATABASE_URL};
const admin=new Client(config); await admin.connect();
const uid=(n)=>'00000000-0000-0000-0000-'+String(n).padStart(12,'0');
const migration=readFileSync(new URL('../supabase/migrations/20261011141634_secure_review_reporting.sql',import.meta.url),'utf8');
async function call(actor,review) {
  const db=new Client(config); await db.connect();
  try {
    await db.query('begin');
    await db.query("select set_config('request.jwt.claim.sub',$1,true)",[uid(actor)]);
    await db.query('set local role authenticated');
    const {rows}=await db.query('select public.increment_report($1::uuid) result',[uid(review)]);
    await db.query('commit'); return rows[0].result;
  } catch(e) {await db.query('rollback');throw e;}
  finally {await db.end();}
}
try {
  await admin.query(`
    drop schema if exists report_private cascade;
    drop function if exists public.increment_report(uuid);
    drop table if exists public.reviews cascade;
    drop schema if exists auth cascade;
    do $$ begin if not exists(select from pg_roles where rolname='anon') then create role anon; end if;
      if not exists(select from pg_roles where rolname='authenticated') then create role authenticated; end if; end $$;
    create schema auth;
    create function auth.uid() returns uuid language sql as $$ select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid $$;
    create function auth.jwt() returns jsonb language sql as $$ select '{}'::jsonb $$;
    grant usage on schema auth to authenticated,anon;
    create table public.reviews(id uuid primary key, user_id uuid, report_count integer default 0,is_hidden boolean default false);
    alter table public.reviews enable row level security;
    create policy visible on public.reviews for select using(is_hidden=false);
    grant all on public.reviews to authenticated,anon;
  `);
  await admin.query(migration);
  for(let i=1;i<=30;i++) await admin.query('insert into public.reviews(id,report_count) values($1,7)',[uid(i)]);
  const distinct=await Promise.all(Array.from({length:32},(_,i)=>call(100+i,1)));
  assert.equal(distinct.filter(x=>x.accepted).length,32);
  assert.equal((await admin.query('select report_count from public.reviews where id=$1',[uid(1)])).rows[0].report_count,39);
  console.log('PASS 32 distinct concurrent reporters: no lost increments');
  const duplicates=await Promise.all(Array.from({length:32},()=>call(200,2)));
  assert.equal(duplicates.filter(x=>x.accepted).length,1);
  assert.equal((await admin.query('select report_count from public.reviews where id=$1',[uid(2)])).rows[0].report_count,8);
  console.log('PASS 32 duplicate concurrent requests: exactly one increment');
  const rate=await Promise.allSettled(Array.from({length:25},(_,i)=>call(300,i+3)));
  assert.equal(rate.filter(x=>x.status==='fulfilled').length,20);
  assert.equal(rate.filter(x=>x.status==='rejected'&&x.reason.code==='P0001').length,5);
  console.log('PASS concurrent cross-review rate limit: 20 accepted, 5 denied');
} finally { await admin.end(); }

