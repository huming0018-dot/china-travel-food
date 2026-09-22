-- =====================================================================
-- 002_harden.sql — 美食图鉴数据库硬化：把数据正确性下沉到数据库
-- ---------------------------------------------------------------------
-- 目标（根治"靠模型手写库、无约束、派生列可错、重复/过时无防护"）：
--   1) 数据修复：招牌菜双重编码字符串 -> 真数组；半残评分补可推定项
--   2) 归一函数：店名/地址归一，数据库与管线共用同一口径（防重索引）
--   3) CHECK 约束：status/tier/价格/评分值域与完整性/坐标边界/关店三要素/招牌菜数组
--   4) 派生触发器：tier、score_total、search_vector、updated_at 由数据库计算，无法手填错
--   5) 唯一索引：同名同址餐厅不可重复；同名同维度同 parent 标签不可重复
--   6) 审计/保鲜/富信息视图：任何时候 SELECT 即得数据缺口，不必跑脚本拉全量
--   7) 幂等写入口 RPC upsert_restaurant：裸写也走约束，推荐统一调用
--
-- 幂等：可重复执行（IF NOT EXISTS / DROP ... IF EXISTS / DO 判存）。
-- 执行环境：Supabase -> SQL Editor；PostgreSQL 17 / PostGIS。
-- 评分口径：score_total = round(0.4o+0.3d+0.2t+0.1e - penalty,1)，clamp[0,100]。
-- =====================================================================

-- =====================================================================
-- BATCH 1 — 数据修复 + 归一/分档函数
-- =====================================================================

-- 1.1 招牌菜：历史上 519 家被存成“内容为数组 JSON 的字符串”（双重编码）或纯文本，统一成 jsonb 数组
DO $$
DECLARE r RECORD; txt text; v jsonb; arr jsonb;
BEGIN
  FOR r IN SELECT id, signature_dishes FROM restaurants
           WHERE signature_dishes IS NOT NULL AND jsonb_typeof(signature_dishes) = 'string'
  LOOP
    txt := btrim(r.signature_dishes #>> '{}');
    arr := NULL;
    BEGIN
      v := txt::jsonb;                       -- 字符串内容本身是 JSON
      IF jsonb_typeof(v) = 'array' THEN arr := v; END IF;
    EXCEPTION WHEN others THEN arr := NULL; END;
    IF arr IS NULL THEN                      -- 退化：按常见分隔符切成数组
      SELECT jsonb_agg(to_jsonb(btrim(x))) INTO arr
      FROM unnest(regexp_split_to_array(txt, '[,，、;；/]+')) x
      WHERE btrim(x) <> '';
    END IF;
    IF arr IS NOT NULL AND jsonb_typeof(arr) = 'array' AND jsonb_array_length(arr) > 0 THEN
      UPDATE restaurants SET signature_dishes = arr WHERE id = r.id;
    ELSE
      UPDATE restaurants SET signature_dishes = NULL WHERE id = r.id;  -- 解析不了进审计待补
    END IF;
  END LOOP;
END $$;

-- 1.2 评分：可推定的缺项补齐（无背书=0、无软广扣分=0）；缺 objective/diner/taste 的不臆造，留给审计回填
UPDATE restaurants SET score_endorsement = 0
  WHERE score_endorsement IS NULL
    AND NOT (score_objective IS NULL AND score_diner IS NULL AND score_taste IS NULL);
UPDATE restaurants SET soft_ad_penalty = 0 WHERE soft_ad_penalty IS NULL;

-- 1.3 归一函数（IMMUTABLE，供唯一索引与 RPC 共用；管线 stage2 应保持同口径）
CREATE OR REPLACE FUNCTION norm_shop_name(text) RETURNS text
LANGUAGE sql IMMUTABLE AS $$
  SELECT lower(regexp_replace(btrim(coalesce($1,'')), '\s+', '', 'g'))
$$;

CREATE OR REPLACE FUNCTION norm_addr(text) RETURNS text
LANGUAGE sql IMMUTABLE AS $$
  SELECT lower(regexp_replace(btrim(coalesce($1,'')), '\s+', '', 'g'))
$$;

-- 1.4 人均 -> 五档（唯一口径）
CREATE OR REPLACE FUNCTION tier_for_price(price_avg integer) RETURNS text
LANGUAGE sql IMMUTABLE AS $$
  SELECT CASE
    WHEN price_avg IS NULL THEN NULL
    WHEN price_avg < 50  THEN '经济'
    WHEN price_avg < 100 THEN '平价'
    WHEN price_avg < 200 THEN '中档'
    WHEN price_avg < 500 THEN '高档'
    ELSE '奢华' END
$$;

-- 1.5 sync_log 补齐 /api/sync 保鲜巡检心跳所需列（旧库增量；001 新库已含，IF NOT EXISTS 幂等）
ALTER TABLE sync_log
  ADD COLUMN IF NOT EXISTS started_at        timestamptz,
  ADD COLUMN IF NOT EXISTS completed_at      timestamptz,
  ADD COLUMN IF NOT EXISTS records_processed integer,
  ADD COLUMN IF NOT EXISTS notes             text;

-- =====================================================================
-- BATCH 2 — CHECK 约束 + 列默认
-- =====================================================================

-- 2.1 status 归一为枚举、非空、默认 active（存量已全为 active/closed）
ALTER TABLE restaurants ALTER COLUMN status SET DEFAULT 'active';
UPDATE restaurants SET status = 'active' WHERE status IS NULL;
ALTER TABLE restaurants ALTER COLUMN status SET NOT NULL;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ch_rest_status') THEN
    ALTER TABLE restaurants ADD CONSTRAINT ch_rest_status
      CHECK (status IN ('active','closed'));
  END IF;
END $$;

-- 2.2 tier 值域（具体档位由触发器按 price 强制一致）
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ch_rest_tier_value') THEN
    ALTER TABLE restaurants ADD CONSTRAINT ch_rest_tier_value
      CHECK (tier IS NULL OR tier IN ('经济','平价','中档','高档','奢华'));
  END IF;
END $$;

-- 2.3 人均合理范围
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ch_rest_price') THEN
    ALTER TABLE restaurants ADD CONSTRAINT ch_rest_price
      CHECK (price_avg IS NULL OR (price_avg BETWEEN 0 AND 99999));
  END IF;
END $$;

-- 2.4 评分值域（四项 0-100、penalty 0-30、total 0-100）
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ch_rest_score_range') THEN
    ALTER TABLE restaurants ADD CONSTRAINT ch_rest_score_range CHECK (
      (score_objective   IS NULL OR score_objective   BETWEEN 0 AND 100) AND
      (score_diner       IS NULL OR score_diner       BETWEEN 0 AND 100) AND
      (score_taste       IS NULL OR score_taste       BETWEEN 0 AND 100) AND
      (score_endorsement IS NULL OR score_endorsement BETWEEN 0 AND 100) AND
      (soft_ad_penalty   IS NULL OR soft_ad_penalty   BETWEEN 0 AND 30)  AND
      (score_total       IS NULL OR score_total       BETWEEN 0 AND 100)
    );
  END IF;
END $$;

-- 2.5 评分完整性：四项要么全有、要么全空（NOT VALID：不拦存量 17 家缺 diner，只拦新增/更新；回填后 VALIDATE）
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ch_rest_score_complete') THEN
    ALTER TABLE restaurants ADD CONSTRAINT ch_rest_score_complete CHECK (
      (score_objective IS NULL AND score_diner IS NULL AND score_taste IS NULL AND score_endorsement IS NULL)
      OR
      (score_objective IS NOT NULL AND score_diner IS NOT NULL AND score_taste IS NOT NULL AND score_endorsement IS NOT NULL)
    ) NOT VALID;
  END IF;
END $$;

-- 2.6 坐标：要么空，要么 SRID4326 且落在上海 bbox
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ch_rest_coord_shanghai') THEN
    ALTER TABLE restaurants ADD CONSTRAINT ch_rest_coord_shanghai CHECK (
      location IS NULL OR (
        ST_SRID(location) = 4326 AND
        ST_X(location::geometry) BETWEEN 120.80 AND 122.20 AND
        ST_Y(location::geometry) BETWEEN 30.65 AND 31.95
      )
    );
  END IF;
END $$;

-- 2.7 关店三要素：closed 必须有关店日期与来源
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ch_rest_closed_triple') THEN
    ALTER TABLE restaurants ADD CONSTRAINT ch_rest_closed_triple CHECK (
      status <> 'closed' OR (closed_date IS NOT NULL AND closed_source IS NOT NULL)
    );
  END IF;
END $$;

-- 2.8 招牌菜：若填必须是 JSON 数组
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ch_rest_dishes_array') THEN
    ALTER TABLE restaurants ADD CONSTRAINT ch_rest_dishes_array CHECK (
      signature_dishes IS NULL OR jsonb_typeof(signature_dishes) = 'array'
    );
  END IF;
END $$;

-- 2.9 店名非空
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ch_rest_name_nonempty') THEN
    ALTER TABLE restaurants ADD CONSTRAINT ch_rest_name_nonempty CHECK (btrim(name) <> '');
  END IF;
END $$;

-- 2.10 标签维度枚举
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ch_cuis_dimension') THEN
    ALTER TABLE cuisines ADD CONSTRAINT ch_cuis_dimension
      CHECK (dimension IN ('菜系','食材','形式','标签','时段','认证'));
  END IF;
END $$;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ch_cuis_name_nonempty') THEN
    ALTER TABLE cuisines ADD CONSTRAINT ch_cuis_name_nonempty CHECK (btrim(name) <> '');
  END IF;
END $$;

-- =====================================================================
-- BATCH 3 — 派生触发器（tier / score_total / updated_at）
-- ---------------------------------------------------------------------
-- search_vector 是 GENERATED ALWAYS STORED 列（001 定义，数据库强制自动维护，
-- 比触发器更强：任何角色都无法手填）。旧库若生成表达式不含 business_area，
-- 在此幂等重建（需先摘下依赖它的 v_restaurant_enriched，Batch5 会重建）。
-- =====================================================================
DROP VIEW IF EXISTS v_restaurant_enriched;
DO $$
DECLARE need boolean;
BEGIN
  SELECT (a.attgenerated='s' AND coalesce(pg_get_expr(d.adbin,d.adrelid),'') NOT LIKE '%business_area%')
  INTO need
  FROM pg_attribute a
  LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum
  WHERE a.attrelid='restaurants'::regclass AND a.attname='search_vector';
  IF need THEN
    ALTER TABLE restaurants DROP COLUMN search_vector;
    EXECUTE $q$ALTER TABLE restaurants ADD COLUMN search_vector tsvector GENERATED ALWAYS AS (
      setweight(to_tsvector('simple',coalesce(name,'')),'A') ||
      setweight(to_tsvector('simple',coalesce(name_en,'')),'A') ||
      setweight(to_tsvector('simple',coalesce(business_area,'')),'B') ||
      setweight(to_tsvector('simple',coalesce(district,'')),'B') ||
      setweight(to_tsvector('simple',coalesce(address,'')),'C')
    ) STORED$q$;
  END IF;
END $$;
CREATE INDEX IF NOT EXISTS idx_restaurants_search ON restaurants USING GIN(search_vector);

CREATE OR REPLACE FUNCTION derive_restaurant() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.status IS NULL THEN NEW.status := 'active'; END IF;
  NEW.updated_at := now();

  -- tier 只由人均决定
  IF NEW.price_avg IS NOT NULL THEN
    NEW.tier := tier_for_price(NEW.price_avg);
  END IF;

  -- score_total 只由四项子分 + penalty 决定，无法手填
  IF NEW.score_objective IS NULL OR NEW.score_diner IS NULL
     OR NEW.score_taste IS NULL OR NEW.score_endorsement IS NULL THEN
    NEW.score_total := NULL;  -- 不完整不展示官方分，进审计回填
  ELSE
    NEW.score_total := greatest(0, least(100,
      round(0.4*NEW.score_objective + 0.3*NEW.score_diner
            + 0.2*NEW.score_taste + 0.1*NEW.score_endorsement
            - coalesce(NEW.soft_ad_penalty,0), 1)));
  END IF;

  -- search_vector 为 GENERATED ALWAYS 列，数据库在触发器之后自动生成；
  -- BEFORE 触发器对其赋值会被忽略，故此处不写（见 001 与本文件 Batch3 说明）。

  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS trg_restaurants_derive ON restaurants;
CREATE TRIGGER trg_restaurants_derive
  BEFORE INSERT OR UPDATE ON restaurants
  FOR EACH ROW EXECUTE FUNCTION derive_restaurant();

-- 3.1 全量重算一次，让存量 tier/score_total/search_vector 立即按数据库口径归一
UPDATE restaurants SET id = id;

-- =====================================================================
-- BATCH 4 — 防重唯一索引
-- =====================================================================

-- 4.1 同名同址不可重复（连锁同名异址，地址不同 => 允许）；仅约束有地址的店
CREATE UNIQUE INDEX IF NOT EXISTS uq_rest_name_addr
  ON restaurants (norm_shop_name(name), norm_addr(address))
  WHERE address IS NOT NULL AND btrim(address) <> '';

-- 4.2 标签：同名 + 同维度 + 同 parent 不可重复（面/饭等同维度按 parent 风味细分仍允许）
CREATE UNIQUE INDEX IF NOT EXISTS uq_cuis_name_dim_parent
  ON cuisines (name, dimension, COALESCE(parent_category,''));

-- =====================================================================
-- BATCH 5 — 审计 / 保鲜 / 富信息视图（security_invoker，遵循 RLS，不放大权限）
-- =====================================================================

-- 5.1 标签挂店覆盖（含 0 店标签，一眼看出素食/分子/团购是否漏挂）
CREATE OR REPLACE VIEW v_tag_coverage
WITH (security_invoker=on) AS
SELECT c.id, c.name, c.dimension, c.parent_category,
       count(rc.restaurant_id) AS n
FROM cuisines c
LEFT JOIN restaurant_cuisines rc ON rc.cuisine_id = c.id
GROUP BY c.id;

-- 5.2 全库数据缺口：一行 = 一家店的一个问题（stage4 的 SQL 化，随时可查）
CREATE OR REPLACE VIEW v_audit_gaps
WITH (security_invoker=on) AS
WITH tag AS (
  SELECT rc.restaurant_id, c.dimension, c.id AS cid
  FROM restaurant_cuisines rc JOIN cuisines c ON c.id = rc.cuisine_id
), agg AS (
  SELECT restaurant_id,
         bool_or(dimension='菜系') AS has_cuisine,
         bool_or(dimension='形式') AS has_form,
         bool_or(cid IN (162,163))  AS has_meal,
         bool_or(cid = 71)          AS has_finedining
  FROM tag GROUP BY restaurant_id
), issues AS (
  SELECT r.id, r.name, g.issue
  FROM restaurants r
  LEFT JOIN agg a ON a.restaurant_id = r.id
  CROSS JOIN LATERAL (VALUES
    ('无坐标',        CASE WHEN r.status='active' AND r.location IS NULL THEN 1 END),
    ('地址空',        CASE WHEN nullif(btrim(coalesce(r.address,'')),'') IS NULL THEN 1 END),
    ('电话空',        CASE WHEN nullif(btrim(coalesce(r.phone,'')),'') IS NULL THEN 1 END),
    ('证据过短',      CASE WHEN r.evidence_summary IS NULL OR length(r.evidence_summary) < 30 THEN 1 END),
    ('招牌菜空',      CASE WHEN r.signature_dishes IS NULL
                            OR jsonb_typeof(r.signature_dishes)<>'array'
                            OR jsonb_array_length(r.signature_dishes)=0 THEN 1 END),
    ('缺菜系叶子',    CASE WHEN NOT coalesce(a.has_cuisine,false) THEN 1 END),
    ('缺形式',        CASE WHEN NOT coalesce(a.has_form,false) THEN 1 END),
    ('缺午晚餐',      CASE WHEN NOT coalesce(a.has_meal,false) THEN 1 END),
    ('评分不完整',    CASE WHEN r.score_objective IS NULL OR r.score_diner IS NULL
                            OR r.score_taste IS NULL OR r.score_endorsement IS NULL THEN 1 END),
    ('FineDining越档',CASE WHEN coalesce(a.has_finedining,false)
                            AND (r.price_avg IS NULL OR r.price_avg < 250) THEN 1 END),
    ('关店三要素缺',  CASE WHEN r.status='closed'
                            AND (r.closed_date IS NULL OR r.closed_source IS NULL) THEN 1 END),
    ('坐标越界',      CASE WHEN r.location IS NOT NULL AND
                            (ST_SRID(r.location)<>4326
                             OR ST_X(r.location::geometry) NOT BETWEEN 120.80 AND 122.20
                             OR ST_Y(r.location::geometry) NOT BETWEEN 30.65 AND 31.95) THEN 1 END),
    ('采集日期空',    CASE WHEN r.data_updated_at IS NULL THEN 1 END)
  ) AS g(issue, flag)
  WHERE g.flag IS NOT NULL
)
SELECT * FROM issues;

-- 5.3 保鲜：是否超过复查周期（新店30/高端180/大众90；此处无开业日期，按高端180、其余90）
CREATE OR REPLACE VIEW v_data_freshness
WITH (security_invoker=on) AS
SELECT id, name, tier, status, data_updated_at,
       CASE WHEN tier IN ('奢华','高档') THEN 180 ELSE 90 END AS fresh_days,
       (current_date - data_updated_at) AS age_days,
       CASE WHEN data_updated_at IS NULL THEN true
            WHEN (current_date - data_updated_at) >
                 CASE WHEN tier IN ('奢华','高档') THEN 180 ELSE 90 END
            THEN true ELSE false END AS stale
FROM restaurants;

-- 5.4 富信息：经纬度 + 菜系/形式聚合 + UGC 条数与均分（前端/分析直接用）
CREATE OR REPLACE VIEW v_restaurant_enriched
WITH (security_invoker=on) AS
SELECT r.*,
       ST_X(r.location::geometry) AS lng,
       ST_Y(r.location::geometry) AS lat,
       (SELECT array_agg(c.name ORDER BY c.name)
          FROM restaurant_cuisines rc JOIN cuisines c ON c.id=rc.cuisine_id
         WHERE rc.restaurant_id=r.id AND c.dimension='菜系')              AS cuisine_arr,
       (SELECT array_agg(c.name ORDER BY c.name)
          FROM restaurant_cuisines rc JOIN cuisines c ON c.id=rc.cuisine_id
         WHERE rc.restaurant_id=r.id AND c.dimension='形式')              AS form_arr,
       (SELECT count(*) FROM reviews rv
         WHERE rv.restaurant_id=r.id AND rv.is_hidden=false)              AS ugc_count,
       (SELECT round(avg(rv.rating_total)::numeric,2) FROM reviews rv
         WHERE rv.restaurant_id=r.id AND rv.is_hidden=false)              AS ugc_avg
FROM restaurants r;

-- 5.5 视图最小权限：审计/保鲜视图仅 service_role（不向前端暴露数据缺口）；
--     标签覆盖/富信息视图对匿名与登录用户只读。
REVOKE SELECT ON v_audit_gaps     FROM PUBLIC, anon, authenticated;
REVOKE SELECT ON v_data_freshness FROM PUBLIC, anon, authenticated;
GRANT  SELECT ON v_audit_gaps, v_data_freshness, v_tag_coverage, v_restaurant_enriched TO service_role;
GRANT  SELECT ON v_tag_coverage, v_restaurant_enriched TO anon, authenticated;

-- =====================================================================
-- BATCH 6 — 幂等写入口 RPC（坐标传 lng/lat；内部触发器/约束全部生效）
-- =====================================================================
CREATE OR REPLACE FUNCTION upsert_restaurant(p jsonb) RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE
  v_id integer; v_name text; v_addr text;
  loc geography(Point,4326);
BEGIN
  v_name := btrim(p->>'name');
  v_addr := btrim(p->>'address');
  IF v_name = '' OR v_name IS NULL THEN
    RAISE EXCEPTION 'name 必填';
  END IF;

  IF p->>'lng' IS NOT NULL AND p->>'lat' IS NOT NULL THEN
    loc := ST_SetSRID(ST_MakePoint((p->>'lng')::float8, (p->>'lat')::float8), 4326);
  END IF;

  SELECT id INTO v_id FROM restaurants
   WHERE norm_shop_name(name) = norm_shop_name(v_name)
     AND address IS NOT NULL AND btrim(address)<>''
     AND norm_addr(address) = norm_addr(v_addr)
   LIMIT 1;

  IF v_id IS NULL THEN
    INSERT INTO restaurants (
      name,name_en,price_avg,price_range,address,district,business_area,location,
      phone,booking_method,signature_dishes,discount_info,investor_info,
      score_objective,score_diner,score_taste,score_endorsement,soft_ad_penalty,
      evidence_summary,status,data_updated_at,closed_date,closed_source)
    VALUES (
      v_name, p->>'name_en',
      nullif(p->>'price_avg','')::int, p->>'price_range', v_addr,
      p->>'district', p->>'business_area', loc,
      p->>'phone', p->>'booking_method',
      CASE WHEN p->'signature_dishes' IS NULL THEN NULL ELSE (p->'signature_dishes')::jsonb END,
      p->>'discount_info', p->>'investor_info',
      nullif(p->>'score_objective','')::numeric, nullif(p->>'score_diner','')::numeric,
      nullif(p->>'score_taste','')::numeric, nullif(p->>'score_endorsement','')::numeric,
      coalesce(nullif(p->>'soft_ad_penalty','')::numeric,0),
      p->>'evidence_summary', coalesce(p->>'status','active'),
      nullif(p->>'data_updated_at','')::date,
      nullif(p->>'closed_date','')::date, p->>'closed_source')
    RETURNING id INTO v_id;
  ELSE
    UPDATE restaurants SET
      name_en          = p->>'name_en',
      price_avg        = nullif(p->>'price_avg','')::int,
      price_range      = p->>'price_range',
      address          = v_addr,
      district         = p->>'district',
      business_area    = p->>'business_area',
      location         = coalesce(loc, location),
      phone            = p->>'phone',
      booking_method   = p->>'booking_method',
      signature_dishes = CASE WHEN p->'signature_dishes' IS NULL THEN signature_dishes
                              ELSE (p->'signature_dishes')::jsonb END,
      discount_info    = p->>'discount_info',
      investor_info    = p->>'investor_info',
      score_objective   = nullif(p->>'score_objective','')::numeric,
      score_diner       = nullif(p->>'score_diner','')::numeric,
      score_taste       = nullif(p->>'score_taste','')::numeric,
      score_endorsement = nullif(p->>'score_endorsement','')::numeric,
      soft_ad_penalty   = coalesce(nullif(p->>'soft_ad_penalty','')::numeric,0),
      evidence_summary  = p->>'evidence_summary',
      status            = coalesce(p->>'status','active'),
      data_updated_at   = nullif(p->>'data_updated_at','')::date,
      closed_date       = nullif(p->>'closed_date','')::date,
      closed_source     = p->>'closed_source'
    WHERE id = v_id;
  END IF;
  RETURN v_id;
END $$;

-- 仅服务端密钥可调用，匿名/登录用户不可通过 RPC 直写
REVOKE EXECUTE ON FUNCTION upsert_restaurant(jsonb) FROM PUBLIC, anon, authenticated;
GRANT  EXECUTE ON FUNCTION upsert_restaurant(jsonb) TO service_role;

-- =====================================================================
-- 完成后验证（单独运行，应全部符合预期）：
--   SELECT conname FROM pg_constraint WHERE conrelid='restaurants'::regclass;
--   SELECT issue, count(*) FROM v_audit_gaps GROUP BY issue ORDER BY 2 DESC;
--   SELECT count(*) stale FROM v_data_freshness WHERE stale;
--   SELECT * FROM v_tag_coverage WHERE n=0 ORDER BY dimension,name;
--   SELECT count(*) FROM restaurants WHERE score_total IS NOT NULL AND
--     abs(score_total - greatest(0,least(100,round(0.4*score_objective+0.3*score_diner+0.2*score_taste+0.1*score_endorsement-coalesce(soft_ad_penalty,0),1))))>0.1;
--   -- 回填 17 家缺 diner 后：ALTER TABLE restaurants VALIDATE CONSTRAINT ch_rest_score_complete;
-- =====================================================================
