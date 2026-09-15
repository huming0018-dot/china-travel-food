import type { NextApiRequest, NextApiResponse } from 'next';
import { createClient } from '@supabase/supabase-js';

/**
 * 数据同步 API 路由
 * 
 * 两种触发方式：
 * 1. Vercel Cron（每天凌晨 3 点，GET 请求，无需认证）
 * 2. 手动触发（POST 请求，需要 CRON_SECRET 认证）
 * 
 * 注意：完整的飞书→Supabase 同步需要 lark-cli，在 Vercel serverless 环境中不可用。
 * 此 API 路由主要用于：
 * - 记录同步心跳到 sync_log 表
 * - 触发数据保鲜检查（标记超期数据为"待复查"）
 * - 完整同步请使用 GitHub Actions（.github/workflows/sync.yml）或本地运行 Python 脚本
 */

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!;
const serviceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY!;

export default async function handler(req: NextApiRequest, res: NextApiResponse) {
  // 认证：POST 请求需要 CRON_SECRET，GET 请求（Vercel Cron）允许
  if (req.method === 'POST') {
    const authHeader = req.headers.authorization;
    const cronSecret = process.env.CRON_SECRET;
    if (cronSecret && authHeader !== `Bearer ${cronSecret}`) {
      return res.status(401).json({ error: 'Unauthorized' });
    }
  }

  try {
    const supabase = createClient(supabaseUrl, serviceRoleKey);

    // 1. 记录同步心跳
    const { data: logData, error: logError } = await supabase
      .from('sync_log')
      .insert({
        source: 'vercel-cron',
        status: 'running',
        started_at: new Date().toISOString(),
      })
      .select()
      .single();

    if (logError) throw logError;

    // 2. 数据保鲜检查：标记超期餐厅
    // 平价店 >90天、高端店 >180天、新店 >30天 标记为"待复查"
    const now = new Date();
    const ninetyDaysAgo = new Date(now.getTime() - 90 * 24 * 60 * 60 * 1000).toISOString();
    const oneEightyDaysAgo = new Date(now.getTime() - 180 * 24 * 60 * 60 * 1000).toISOString();

    // 平价店超期
    await supabase
      .from('restaurants')
      .update({ status: '待复查' })
      .eq('tier', '亲民')
      .lt('data_updated_at', ninetyDaysAgo)
      .eq('status', '推荐');

    // 高端店超期
    await supabase
      .from('restaurants')
      .update({ status: '待复查' })
      .eq('tier', '高端')
      .lt('data_updated_at', oneEightyDaysAgo)
      .eq('status', '推荐');

    // 3. 统计当前数据状态
    const { count: totalCount } = await supabase
      .from('restaurants')
      .select('*', { count: 'exact', head: true });

    const { count: reviewCount } = await supabase
      .from('restaurants')
      .select('*', { count: 'exact', head: true })
      .eq('status', '待复查');

    // 4. 更新同步日志为完成
    await supabase
      .from('sync_log')
      .update({
        status: 'success',
        completed_at: new Date().toISOString(),
        records_processed: totalCount || 0,
        notes: `数据保鲜检查完成，${reviewCount || 0} 家标记为待复查。完整飞书同步请使用 GitHub Actions。`,
      })
      .eq('id', logData.id);

    return res.status(200).json({
      success: true,
      total_restaurants: totalCount,
      needs_review: reviewCount,
      message: '数据保鲜检查完成。完整飞书→Supabase 同步请运行 Python 脚本或 GitHub Actions。',
    });
  } catch (error: any) {
    console.error('Sync API error:', error);
    return res.status(500).json({ success: false, error: error.message });
  }
}
