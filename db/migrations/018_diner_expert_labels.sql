-- 018_diner_expert_labels.sql — 食客/专家四维两层标注表（模块A·收录机制）
-- 在 Supabase SQL Editor 中执行一次即可（REST 不能 DDL）。幂等可重跑、可回滚。
-- 认识论：专家标注是高质量 ground truth，只作权重学习/监督信号，不直接覆盖在跑 score_*（DB 触发器算）。
-- 四维：口味 taste / 氛围 ambience / 创新 innovation / 出品稳定性 consistency（1–5）；
-- 两层 tier：不可不吃 must_eat / 值得一吃 worth_eating。

CREATE TABLE IF NOT EXISTS diner_expert_labels (
    id            BIGSERIAL PRIMARY KEY,
    restaurant_id BIGINT NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
    labeler       TEXT   NOT NULL,                 -- 标注人（专家/用户名）
    taste         NUMERIC NOT NULL CHECK (taste         BETWEEN 1 AND 5),
    ambience      NUMERIC NOT NULL CHECK (ambience      BETWEEN 1 AND 5),
    innovation    NUMERIC NOT NULL CHECK (innovation    BETWEEN 1 AND 5),
    consistency   NUMERIC NOT NULL CHECK (consistency   BETWEEN 1 AND 5),
    tier          TEXT   NOT NULL CHECK (tier IN ('must_eat','worth_eating')),
    evidence      TEXT,                            -- 堂食证据/具体菜名
    evidence_url  TEXT,
    experienced_at DATE NOT NULL,                 -- 实际到店日（唯一键一部分）
    notes         TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (restaurant_id, labeler, experienced_at)
);

CREATE INDEX IF NOT EXISTS idx_diner_expert_labels_rid  ON diner_expert_labels(restaurant_id);
CREATE INDEX IF NOT EXISTS idx_diner_expert_labels_lblr ON diner_expert_labels(labeler);

-- 与 lead_hypotheses 一致：对 anon/authenticated 只读之外不开放写（写仅 service role）。
-- 视 RLS 策略与现有事实表保持一致；本迁移只建表+约束+索引。
