-- 019_seed_labels_minimal.sql — 极简种子标注（模块A·收录机制），取代 018 重表
-- 在 Supabase SQL Editor 执行一次（REST 不能 DDL）。幂等可重跑。
-- 用户只提供：评级 tier（必吃/值得）为必填；口味分、最近到店年份、证据均可选。
-- 旧 018 diner_expert_labels 为四维+精确日期的重表、无数据，按“精益/不过度”由本表取代。

DROP TABLE IF EXISTS diner_expert_labels;

CREATE TABLE IF NOT EXISTS diner_seed_labels (
    id            BIGSERIAL PRIMARY KEY,
    restaurant_id BIGINT NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
    labeler       TEXT   NOT NULL DEFAULT 'expert',
    tier          TEXT   NOT NULL CHECK (tier IN ('must_eat','worth_eating')),  -- 必吃 / 值得
    taste         SMALLINT CHECK (taste BETWEEN 1 AND 5),                       -- 可选总体口味
    visit_year    INT      CHECK (visit_year BETWEEN 2000 AND 2035),            -- 最近一次到店大概年份
    evidence      TEXT,                                                         -- 可选：印象深的菜/备注
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (restaurant_id, labeler)                                             -- 每店每标注人一条
);

CREATE INDEX IF NOT EXISTS idx_seed_labels_rid ON diner_seed_labels(restaurant_id);
