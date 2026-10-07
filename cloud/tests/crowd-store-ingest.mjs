// Run with an existing PGlite install: CROWD_TEST_TOOLS=/path/to/tools node cloud/tests/crowd-store-ingest.mjs
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { createRequire } from 'node:module';
import { resolve } from 'node:path';
const require = createRequire(resolve(process.env.CROWD_TEST_TOOLS || '.', 'package.json'));
const { PGlite } = require('@electric-sql/pglite');
const db = new PGlite();
try {
  await db.exec(`
    create role anon; create role authenticated; create role service_role bypassrls;
    create table public.restaurants (id integer primary key, name text, score_diner numeric);
    create table public.crowd_proofs (
      matched_store text, kind text, rating numeric, participant_id text,
      created_at timestamptz default now(), note_id text, gate_status text
    );
    insert into public.restaurants values
      (1,'唯一店（分店）',1), (2,'重名店（甲）',1), (3,'重名店(乙)',2), (4,'不足三条',1);
    insert into public.crowd_proofs (matched_store,kind,rating,participant_id,note_id,gate_status) values
      ('唯一店','note',null,'p1','note1','accepted'),
      ('唯一店','rating',3,'p1',null,'accepted'),
      ('唯一店','rating',4,'p2',null,'accepted'),
      ('唯一店','rating',5,'p3',null,'accepted'),
      ('唯一店','rating',1,'p4',null,'rejected'),
      ('重名店','note',null,'p1','note2','accepted'),
      ('重名店','rating',5,'p1',null,'accepted'),
      ('重名店','rating',5,'p2',null,'accepted'),
      ('重名店','rating',5,'p3',null,'accepted'),
      ('无匹配店','note',null,'p1','note3','accepted'),
      ('不足三条','rating',5,'p1',null,'accepted'),
      ('不足三条','rating',5,'p2',null,'accepted'),
      ('  ','note',null,'p1','blank','accepted');
  `);
  const schema = readFileSync(new URL('../sql/crowd_migration_v3.2_05_store_ingest.sql', import.meta.url), 'utf8');
  await db.exec(schema);
  const migrationsDir = new URL('../supabase/migrations/', import.meta.url);
  const migration = readdirSync(migrationsDir).find(n => n.endsWith('_crowd_ingest_unique_store_match.sql'));
  await db.exec(readFileSync(new URL(migration, migrationsDir), 'utf8'));
  const permissionsMigration = readdirSync(migrationsDir).find(n => n.endsWith('_crowd_store_tables_service_only.sql'));
  await db.exec(readFileSync(new URL(permissionsMigration, migrationsDir), 'utf8'));
  const call = async dry => (await db.query(`select public.crowd_ingest_stores(${dry}) as result`)).rows[0].result;
  assert.equal((await call(true)).evidence.length, 4);
  assert.equal((await db.query('select count(*)::int as n from public.crowd_store_evidence')).rows[0].n, 0);
  assert.deepEqual(await call(false), { ok: true, dry_run: false, evidence_count: 4, updated_restaurants: 1, candidates: 2 });
  const rows = (await db.query('select store_name, matched_restaurant_id, note_count, rating_count, rating_avg from public.crowd_store_evidence')).rows;
  assert.equal(rows.find(r => r.store_name === '重名店').matched_restaurant_id, null);
  assert.equal(rows.find(r => r.store_name === '唯一店').matched_restaurant_id, 1);
  assert.equal(rows.find(r => r.store_name === '唯一店').rating_count, 3);
  assert.equal(Number(rows.find(r => r.store_name === '唯一店').rating_avg), 4);
  assert.deepEqual((await db.query('select score_diner from public.restaurants order by id')).rows.map(r => Number(r.score_diner)), [4, 1, 2, 1]);
  const candidates = (await db.query('select id,store_name from public.crowd_store_candidates order by id')).rows;
  assert.deepEqual(candidates.map(r => r.store_name).sort(), ['无匹配店', '重名店'].sort());
  assert.equal((await call(false)).updated_restaurants, 0);
  assert.deepEqual((await db.query('select id,store_name from public.crowd_store_candidates order by id')).rows, candidates);
  for (const role of ['anon', 'authenticated']) {
    await db.exec(`set role ${role}`);
    await assert.rejects(call(false), e => e.code === '42501');
    await assert.rejects(db.query('select * from public.crowd_store_evidence'), e => e.code === '42501');
    await assert.rejects(db.query("insert into public.crowd_store_candidates(store_name) values ('unauthorized')"), e => e.code === '42501');
    await db.exec('reset role');
  }
  await db.exec('set role service_role');
  assert.equal((await call(false)).ok, true);
  assert.equal((await db.query('select count(*)::int as n from public.crowd_store_evidence')).rows[0].n, 4);
  console.log('PASS: unique/ambiguous/missing matches, rating threshold, replay, dry-run and service-only permissions');
} finally {
  await db.close();
}
