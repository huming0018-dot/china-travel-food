-- =====================================================================
-- 015_lead_hypotheses.sql — HAE / L0.5 假设层（Hypothesis & Association Engine）
-- ---------------------------------------------------------------------
-- 为什么缺：Phase0 过度偏确定性，模型只用于生成关键词，没有
--   「自由回忆/联想 → 假设 → 证伪」阶段，也没把假设与事实分层。
-- 本 migration 只建【假设账本】一张表，与事实表（restaurants/chefs/
--   restaurant_chefs/restaurant_groups/...）物理隔离、权限隔离。
--
-- 护栏（与 north-star / mechanism-master 对齐）：
--   * LLM/AI 输出【绝不直写事实表】，一律先落本表，status 默认 hypothesized。
--   * 模型自标 知道/推断/不知道；无记忆留空（宁空不假），禁编造。
--   * 只有 confirmed 且过既有闸门（事实=权威源或≥2独立声音；
--     沿革/持股/关系=≥1 可信文档：官方/新闻/工商）才允许晋升写事实表。
--   * 每条假设必带 confirm_queries + 强制 falsify_queries（关店/离职/
--     辟谣/难吃/预制）。
--   * 幂等：hid = 确定性哈希，重跑 ON CONFLICT 更新不产生新行。
--   * 权限：service_role 才可读写；anon/authenticated 完全不可见
--     （假设是内部未证实线索，不向前端暴露）。
--
-- 幂等：全部 CREATE/ALTER IF NOT EXISTS、DO $$ 守卫、ON CONFLICT，可重复跑。
-- DDL 只能在 Supabase SQL Editor 执行（REST 做不了）；执行后用文件末尾
--   的独立 SELECT 核对，再让 HAE 脚本以 service role 写入。
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. 枚举取值（CHECK 约束固化，应用层保证取值一致）
-- ---------------------------------------------------------------------
-- subject_type:  chef(主厨) / owner(老板/主理人) / restaurant(店铺) /
--                blogger(美食博主/家) / list(官方榜单/节目) / brand(品牌) /
--                group(餐饮集团)
-- relation:      worked_at(曾任职于) / career_period(任职时段) /
--                teacher(师承) / founded(创立) / owns(拥有) /
--                related_to(疑似关联) / award(获奖/荣誉) /
--                show_appearance(综艺/节目出镜) / signature_dish(招牌菜) /
--                reviewed_by(被谁点评/背书) / list_member(榜单/节目成员)
-- known_vs_inferred: 知道(模型确有记忆/直接读过原文) / 推断(联想/推测) / 不知道(留空)
-- status:        hypothesized(待证) / confirmed(正向+反向均过闸) /
--                contradicted(被证伪，留痕驳回) / unverified(多轮仍无结论)
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS lead_hypotheses (
  hid           text PRIMARY KEY,          -- sha1(subject_type|subject_name|relation|object|prompt_hash)，确定性幂等
  subject_type  text NOT NULL,
  subject_name  text NOT NULL,
  relation      text NOT NULL,
  object        text,                       -- 关系另一端（店/人/品牌/菜/节目），可空
  "when"        text,                       -- 年份/时段，原文照录；不确定留空不猜（when 为 PG 保留字，须双引号）
  claim_text    text NOT NULL,              -- 一句话主张（逐字，不改写事实）
  confidence    numeric(3,2) NOT NULL DEFAULT 0.30,  -- 0.00–1.00，先验置信（ensemble 一致度上调）

  known_vs_inferred text NOT NULL DEFAULT '推断'
                CHECK (known_vs_inferred IN ('知道','推断','不知道')),

  proposed_by   jsonb NOT NULL,             -- {model, version, prompt_hash, date, ensemble:[...]}，可复现
  status        text NOT NULL DEFAULT 'hypothesized'
                CHECK (status IN ('hypothesized','confirmed','contradicted','unverified')),

  evidence      jsonb NOT NULL DEFAULT '[]'::jsonb,        -- [{source,title,url,snippet,kind,voice_date}]
  confirm_queries  jsonb NOT NULL DEFAULT '[]'::jsonb,     -- 正向取证查询词
  falsify_queries   jsonb NOT NULL DEFAULT '[]'::jsonb,     -- 强制反向证伪查询（关店/离职/辟谣/难吃/预制）

  -- 收敛结果（过闸前一律留空；confirmed 才填）
  confirm_voices    integer NOT NULL DEFAULT 0,            -- 独立声音数（≥2 才够事实门槛）
  confirmed_source_urls jsonb NOT NULL DEFAULT '[]'::jsonb,-- 正向取证命中的原始 URL（AI 总结必须 fetch 到原文）
  verdict_notes  text,                       -- 收敛结论说明（为何 confirm/reject，含反向证伪结果）
  promoted_to    text,                       -- 晋升落点，如 'chefs:12' / 'restaurant_chefs(r=101,c=12)' / 'restaurant_groups:3'；未晋升 NULL

  -- 图扩散（沿节点继续发散：节目→主厨、老板→品牌→主厨/门店、榜单→成员）
  parent_hid    text,                        -- 由哪条假设/种子扩散而来（种子为 NULL/is_seed）
  is_seed       boolean NOT NULL DEFAULT false,
  expands_to    jsonb NOT NULL DEFAULT '[]'::jsonb,        -- 本节点扩散出的下游 subject 名单

  model_consensus text DEFAULT 'single',     -- ensemble 一致度：unanimous(全一致)/split(有分歧存疑)/single(单模型)
  rounds        integer NOT NULL DEFAULT 0,  -- 收敛轮次（跑到无新确认边/frontier 清空）

  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now()
);

-- 取值域守卫（DO 守卫，幂等；已存在则跳过）
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ch_hyp_subject_type') THEN
    ALTER TABLE lead_hypotheses ADD CONSTRAINT ch_hyp_subject_type CHECK (
      subject_type IN ('chef','owner','restaurant','blogger','list','brand','group')); END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ch_hyp_relation') THEN
    ALTER TABLE lead_hypotheses ADD CONSTRAINT ch_hyp_relation CHECK (
      relation IN ('worked_at','career_period','teacher','founded','owns','related_to',
                   'award','show_appearance','signature_dish','reviewed_by','list_member')); END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ch_hyp_confidence') THEN
    ALTER TABLE lead_hypotheses ADD CONSTRAINT ch_hyp_confidence CHECK (
      confidence BETWEEN 0 AND 1); END IF;
END $$;

-- 检索索引（按状态收敛、按主体遍历图、按关系扩 frontier）
CREATE INDEX IF NOT EXISTS idx_hyp_status   ON lead_hypotheses(status);
CREATE INDEX IF NOT EXISTS idx_hyp_subject  ON lead_hypotheses(subject_type, subject_name);
CREATE INDEX IF NOT EXISTS idx_hyp_rel     ON lead_hypotheses(relation);
CREATE INDEX IF NOT EXISTS idx_hyp_parent  ON lead_hypotheses(parent_hid);
CREATE INDEX IF NOT EXISTS idx_hyp_seed     ON lead_hypotheses(is_seed) WHERE is_seed;

-- updated_at 自动刷新
DROP TRIGGER IF EXISTS trg_hyp_updated ON lead_hypotheses;
CREATE TRIGGER trg_hyp_updated BEFORE UPDATE ON lead_hypotheses
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ---------------------------------------------------------------------
-- 2. 权限：假设账本是内部未证实线索，service_role 才可读写；
--    anon/authenticated 不授任何策略（RLS 启用即默认拒绝一切）。
--    这样与公开事实表（restaurants/chefs 等公开 SELECT）形成权限隔离。
-- ---------------------------------------------------------------------
ALTER TABLE lead_hypotheses ENABLE ROW LEVEL SECURITY;
-- 刻意【不】创建任何 SELECT/INSERT/UPDATE policy：
--   service_role 绕过 RLS 可读写；anon/authenticated 无任何策略 = 完全不可见。

-- ---------------------------------------------------------------------
-- 3. 回滚/可回滚说明：
--    本表与事实表无外键耦合（不 REFERENCES restaurants(id)，因为假设对象
--    常是尚未入库的人/品牌/节目），DROP TABLE lead_hypotheses CASCADE;
--    即可整体回滚，不影响任何事实表。晋升是【复制】到事实表，非移动，
--    驳回(contradicted)仅改状态留痕，永不 DELETE。
-- ---------------------------------------------------------------------

-- =====================================================================
-- 验证（独立 SELECT，确认批次生效；在 SQL Editor 跑完后另开查询核对）
-- =====================================================================
-- SELECT column_name, data_type FROM information_schema.columns
--   WHERE table_name='lead_hypotheses' ORDER BY ordinal_position;
-- SELECT status, count(*) FROM lead_hypotheses GROUP BY status;  -- 初始 0 行
-- -- anon 应读不到（42501 / 0 行）：
-- -- SELECT * FROM lead_hypotheses;  -- 用 anon key 测，应失败或空
