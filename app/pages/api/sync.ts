import type { NextApiRequest, NextApiResponse } from 'next';
import { createClient } from '@supabase/supabase-js';

/**
 * 数据保鲜 / 心跳 API 路由
 *
 * 两种触发方式（都必须带 Authorization: Bearer ${CRON_SECRET}）：
 * 1. Vercel Cron（GET，Vercel 会自动携带 CRON_SECRET 头）
 * 2. 手动触发（GET/POST，手动在 Vercel 设置的 CRON_SECRET）
 *
 * 重要：本路由只做“只读体检 + 写一条心跳”，绝不修改 restaurants.status。
 * - status 只有 active/closed 两态，由数据库 CHECK 约束 ch_rest_status 强制；
 *   “是否超期需要复查”是保鲜视图 v_data_freshness 的派生信息，不应写回 status。
 * - 数据缺口（无坐标/电话空/分类缺失/评分不完整等）由视图 v_audit_gaps 暴露。
 * - 真正的补数据走 food_pipeline（stage1→5），统一经过数据库触发器/约束/幂等 RPC，
 *   不在此路由直接写餐厅数据。
 *
 * sync_log 表结构（001_init.sql / 002_harden.sql 1.5）：id, source, sheet_name,
 * revision, records_synced, status(running/success/failed/skipped), synced_at,
 * started_at, completed_at, records_processed, notes。
 */

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!;
const serviceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY!;

export default async function handler(req: NextApiRequest, res: NextApiResponse) {
  // 鉴权：必须携带 Authorization: Bearer ${CRON_SECRET}；未配置密钥直接拒绝。
  const cronSecret = process.env.CRON_SECRET;
  if (!cronSecret) {
    return res.status(503).json({ success: false, error: 'CRON_SECRET 未配置，拒绝无鉴权巡检' });
  }
  if (req.headers.authorization !== `Bearer ${cronSecret}`) {
    return res.status(401).json({ success: false, error: 'Unauthorized' });
  }

  const startedAt = new Date().toISOString();
  const supabase = createClient(supabaseUrl, serviceRoleKey);
  const finish = async (
    status: 'running' | 'success' | 'failed',
    records: number | null,
    notes?: string,
  ) => {
    await supabase.from('sync_log').insert({
      source: 'vercel-cron',
      sheet_name: 'freshness-check',
      status,
      records_synced: records,
      records_processed: records,
      started_at: startedAt,
      completed_at: status === 'running' ? null : new Date().toISOString(),
      notes: notes ?? null,
    });
  };

  try {
    // 1. 只读体检：超期需复查（视图按 高端180天/大众90天 判定）
    const { count: staleCount } = await supabase
      .from('v_data_freshness')
      .select('id', { count: 'exact', head: true })
      .eq('stale', true);

    const { count: totalCount } = await supabase
      .from('restaurants')
      .select('*', { count: 'exact', head: true });

    const { count: closedCount } = await supabase
      .from('restaurants')
      .select('*', { count: 'exact', head: true })
      .eq('status', 'closed');

    // 缺口按类型聚合（视图一行=一店一问题）
    const { data: gapRows } = await supabase.from('v_audit_gaps').select('issue');
    const gapSummary: Record<string, number> = {};
    for (const row of gapRows ?? []) {
      const k = (row as { issue: string }).issue;
      gapSummary[k] = (gapSummary[k] || 0) + 1;
    }

    await finish(
      'success',
      totalCount || 0,
      `超期需复查 ${staleCount ?? 0}；关店 ${closedCount ?? 0}；缺口 ${JSON.stringify(gapSummary)}`,
    );

    return res.status(200).json({
      success: true,
      total_restaurants: totalCount,
      closed: closedCount,
      stale_needs_review: staleCount,
      gap_summary: gapSummary,
      message: `只读保鲜体检：超期需复查 ${staleCount ?? 0} 家；不修改营业状态；补数据走 food_pipeline。`,
    });
  } catch (error: any) {
    console.error('Sync API error:', error);
    await finish('failed', null, String(error && error.message ? error.message : error));
    return res.status(500).json({ success: false, error: error.message });
  }
}
