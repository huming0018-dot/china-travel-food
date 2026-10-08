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
  const schema = readFileSync(process.env.CROWD_TEST_SCHEMA || new URL('../sql/crowd_migration_v3.2_05_store_ingest.sql', import.meta.url), 'utf8');
  await db.exec(schema);
  const migrationsDir = new URL('../supabase/migrations/', import.meta.url);
  if (!process.env.CROWD_TEST_SCHEMA_ONLY) {
    const migration = readdirSync(migrationsDir).find(n => n.endsWith('_crowd_ingest_unique_store_match.sql'));
    await db.exec(readFileSync(new URL(migration, migrationsDir), 'utf8'));
    await db.exec(readFileSync(new URL(migration, migrationsDir), 'utf8'));
    const permissionsMigration = readdirSync(migrationsDir).find(n => n.endsWith('_crowd_store_tables_service_only.sql'));
    await db.exec(readFileSync(new URL(permissionsMigration, migrationsDir), 'utf8'));
    const followup = readdirSync(migrationsDir).find(n => n.endsWith('_crowd_ingest_current_safe_scores.sql'));
    if (followup && !process.env.CROWD_TEST_DEPLOYED_ONLY) {
      await db.exec(readFileSync(new URL(followup, migrationsDir), 'utf8'));
      await db.exec(readFileSync(new URL(followup, migrationsDir), 'utf8'));
      const refresh = readdirSync(migrationsDir).find(n => n.endsWith('_crowd_ingest_refresh_old_aggregates.sql'));
      await db.exec(readFileSync(new URL(refresh, migrationsDir), 'utf8'));
      await db.exec(readFileSync(new URL(refresh, migrationsDir), 'utf8'));
    }
    // Reapplication must preserve the definition and service-only grants.
    await db.exec(readFileSync(new URL(permissionsMigration, migrationsDir), 'utf8'));
  }
  assert.deepEqual((await db.query(`select relrowsecurity from pg_class
    where oid in ('public.crowd_store_evidence'::regclass, 'public.crowd_store_candidates'::regclass)`)).rows.map(r => r.relrowsecurity), [true, true]);
  assert.equal((await db.query(`select proconfig from pg_proc
    where oid = 'public.crowd_ingest_stores(boolean)'::regprocedure`)).rows[0].proconfig[0], 'search_path=""');
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
  // Test RLS separately from ACLs: even a temporary SELECT grant exposes no rows.
  await db.exec('begin; grant select on public.crowd_store_evidence, public.crowd_store_candidates to anon, authenticated;');
  for (const role of ['anon', 'authenticated']) {
    await db.exec(`set local role ${role}`);
    for (const table of ['crowd_store_evidence', 'crowd_store_candidates']) {
      assert.equal((await db.query(`select count(*)::int as n from public.${table}`)).rows[0].n, 0);
    }
    await db.exec('reset role');
  }
  await db.exec('rollback');
  await db.exec('set role service_role');
  assert.equal((await call(false)).ok, true);
  assert.equal((await db.query('select count(*)::int as n from public.crowd_store_evidence')).rows[0].n, 4);
  await db.exec('reset role');
  // When every proof is withdrawn, the old aggregate must never write a score again.
  await db.exec(`update public.crowd_proofs set gate_status='rejected' where matched_store='唯一店';
    update public.restaurants set score_diner=2 where id=1;`);
  assert.equal((await call(false)).updated_restaurants, 0, 'withdrawn evidence must not rewrite scores');
  assert.equal(Number((await db.query('select score_diner from public.restaurants where id=1')).rows[0].score_diner), 2);
  const withdrawn = (await db.query("select note_count,rating_count,rating_avg,participant_count,sample_note_ids,matched_restaurant_id from public.crowd_store_evidence where store_name='唯一店'")).rows[0];
  assert.deepEqual({ ...withdrawn, rating_avg: Number(withdrawn.rating_avg) }, {
    note_count: 0, rating_count: 0, rating_avg: 0, participant_count: 0,
    sample_note_ids: [], matched_restaurant_id: null
  }, 'withdrawn aggregate must be invalidated, not merely skipped for scoring');
  // Stale unique match also becomes unsafe when a namesake is added to the master.
  await db.exec(`insert into public.restaurants values (5,'唯一店（新分店）',1);`);
  assert.equal((await call(false)).updated_restaurants, 0);
  // Multiple raw aliases map to one restaurant: never pick an arbitrary source average.
  await db.exec(`insert into public.restaurants values (6,'别名店',2);
    insert into public.crowd_proofs(matched_store,kind,rating,participant_id,gate_status)
    select alias,'rating',rating,'p'||n,'accepted'
    from (values ('别名店',3),('别名店（分店）',5)) a(alias,rating), generate_series(1,3) n;`);
  assert.equal((await call(false)).updated_restaurants, 0, 'multiple score sources must fail closed');
  assert.equal(Number((await db.query('select score_diner from public.restaurants where id=6')).rows[0].score_diner), 2);
  await db.exec(`insert into public.restaurants values (7,'零评分',2), (8,'（空名称）',2);
    insert into public.crowd_proofs(matched_store,kind,rating,participant_id,gate_status)
    select alias,'rating',rating,'p'||n,'accepted'
    from (values ('零评分',0),('（另一空名称）',5)) a(alias,rating), generate_series(1,3) n;`);
  assert.equal((await call(false)).updated_restaurants, 0);
  assert.deepEqual((await db.query('select score_diner from public.restaurants where id in (7,8) order by id')).rows.map(r => Number(r.score_diner)), [2,2]);
  // Remove a withdrawn open candidate, but preserve human decisions unchanged.
  await db.exec(`insert into public.crowd_store_candidates(store_name,status,note_count)
    values ('无匹配店','ignored',7), ('无匹配店','adopted',8);
    update public.crowd_proofs set gate_status='rejected' where matched_store='无匹配店';`);
  const beforeDry = (await db.query("select to_jsonb(e) as row from public.crowd_store_evidence e where store_name='无匹配店'")).rows;
  await call(true);
  assert.deepEqual((await db.query("select to_jsonb(e) as row from public.crowd_store_evidence e where store_name='无匹配店'")).rows, beforeDry, 'dry-run must not invalidate aggregates');
  assert.equal((await db.query("select count(*)::int as n from public.crowd_store_candidates where store_name='无匹配店' and status='open'")).rows[0].n, 1);
  await call(false);
  assert.deepEqual((await db.query("select status,note_count from public.crowd_store_candidates where store_name='无匹配店' order by status")).rows, [
    { status: 'adopted', note_count: 8 }, { status: 'ignored', note_count: 7 }
  ]);
  assert.equal((await db.query("select note_count from public.crowd_store_evidence where store_name='无匹配店'")).rows[0].note_count, 0);
  // Partial withdrawal recomputes the surviving count and sample IDs.
  await db.exec(`insert into public.crowd_proofs(matched_store,kind,participant_id,note_id,gate_status,created_at)
    values ('部分撤回','note','p1','part1','accepted','2026-01-01'),
           ('部分撤回','note','p2','part2','accepted','2026-01-02');`);
  await call(false);
  await db.exec("update public.crowd_proofs set gate_status='rejected' where note_id='part1'");
  await call(false);
  const partial = (await db.query("select note_count,participant_count,sample_note_ids,first_seen::text from public.crowd_store_evidence where store_name='部分撤回'")).rows[0];
  assert.equal(partial.note_count, 1);
  assert.equal(partial.participant_count, 1);
  assert.deepEqual(partial.sample_note_ids, ['part2']);
  assert.ok(partial.first_seen.startsWith('2026-01-02'));
  // A previously ambiguous master match must be refreshed to unique and its open candidate removed.
  await db.exec('delete from public.restaurants where id=3');
  assert.equal((await call(false)).updated_restaurants, 1);
  assert.equal((await db.query("select matched_restaurant_id from public.crowd_store_evidence where store_name='重名店'")).rows[0].matched_restaurant_id, 2);
  assert.equal((await db.query("select count(*)::int as n from public.crowd_store_candidates where store_name='重名店' and status='open'")).rows[0].n, 0);
  await db.exec("insert into public.restaurants values (3,'重名店(乙)',2)");
  assert.equal((await call(false)).updated_restaurants, 0);
  assert.equal((await db.query("select matched_restaurant_id from public.crowd_store_evidence where store_name='重名店'")).rows[0].matched_restaurant_id, null);
  assert.equal((await db.query("select count(*)::int as n from public.crowd_store_candidates where store_name='重名店' and status='open'")).rows[0].n, 1);
  // Empty accepted snapshot invalidates every aggregate and clears only open work items.
  await db.exec("update public.crowd_proofs set gate_status='rejected'");
  assert.equal((await call(false)).evidence_count, 0);
  assert.equal((await db.query('select count(*)::int as n from public.crowd_store_evidence where note_count<>0 or rating_count<>0 or participant_count<>0 or rating_avg<>0 or matched_restaurant_id is not null or sample_note_ids<>\'[]\'::jsonb')).rows[0].n, 0);
  assert.equal((await db.query("select count(*)::int as n from public.crowd_store_candidates where status='open'")).rows[0].n, 0);
  assert.equal((await call(false)).updated_restaurants, 0);
  console.log('PASS: unique/ambiguous/missing matches, threshold, replay, dry-run, service-only permissions, migration reapplication, withdrawn evidence, stale matches, alias collisions, old aggregate refresh, open candidate cleanup, human decision retention, partial withdrawal and empty accepted snapshot');
} finally {
  await db.close();
}
