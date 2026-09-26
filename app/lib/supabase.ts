import { createClient } from '@supabase/supabase-js';

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!;
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!;

export const supabase = createClient(supabaseUrl, supabaseAnonKey);

// 类型定义
export interface Restaurant {
  id: number;
  name: string;
  name_en?: string;
  tier?: string;
  price_avg?: number;
  price_range?: string;
  address?: string;
  district?: string;
  business_area?: string; // 商圈（文本），如"陆家嘴""古北"
  location?: unknown;     // PostGIS 地理点（地图用），勿存文本
  phone?: string;
  booking_method?: string;
  signature_dishes?: string[];
  discount_info?: string;
  investor_info?: string;
  score_total?: number;
  score_objective?: number;
  score_diner?: number;
  score_taste?: number;
  score_endorsement?: number;
  soft_ad_penalty?: number;
  evidence_summary?: string;
  status?: string;
  data_updated_at?: string;
  created_at?: string;
  updated_at?: string;
  closed_date?: string;
  closed_source?: string;
  chain_type?: string;        // 连锁类型：独立店/小型连锁/大型连锁/资本化连锁
  central_kitchen?: boolean; // 中央厨房
  premade_risk?: string;     // 预制菜风险
  is_chain_standardized?: boolean | null; // 标准化连锁派生列（008），前端隐藏/角标依据
  price_position?: string;   // 品类内相对档（已停用，前端不再展示）
  price_scene?: string;      // 价格场景：正餐/快餐小吃/咖啡茶饮/面包/甜品/酒吧
  price_band?: number | null;// 场景内价格带 1-5（客观，按固定阈值由人均算出）
  // —— 以下字段可能尚未上线，缺失时前端做空值处理 ——
  opening_hours?: Record<string, string> | string | null; // 营业时间 jsonb，如 {"周一":"11:00-22:00"}
  open_days?: string | null;        // 营业日期，如 "周一至周日" / "仅周末"
  semantic_description?: string | null; // 一句话/一段话定性简介
  chef_name?: string | null;        // 主厨名（反范式冗余，如有）
}

export interface PriceThreshold {
  scene: string;
  band: number;
  lo: number | null;
  hi: number | null;
}

/** 价格带 → 客观区间文本（零模糊）。 */
export function bandLabel(t: PriceThreshold): string {
  if (t.lo == null) return `¥<${t.hi}`;
  if (t.hi == null) return `¥${t.lo}+`;
  return `¥${t.lo}–${t.hi}`;
}

let _thCache: PriceThreshold[] | null = null;
export async function fetchThresholds(): Promise<PriceThreshold[]> {
  if (_thCache) return _thCache;
  const { data, error } = await supabase
    .from('price_band_thresholds').select('scene,band,lo,hi').order('band');
  if (error) throw error;
  _thCache = (data as PriceThreshold[]) || [];
  return _thCache;
}

export function thresholdFor(thresholds: PriceThreshold[], scene?: string, band?: number | null): PriceThreshold | undefined {
  return thresholds.find((t) => t.scene === scene && t.band === band);
}

export interface Cuisine {
  id: number;
  name: string;
  dimension: string;
  parent_category?: string;
  flavor_profile?: string;
  signature_dishes?: string;
  price_low?: number;
  price_mid?: number;
  price_high?: number;
  shanghai_format?: string;
}

export interface Review {
  id: string;
  restaurant_id: number;
  user_id: string;
  author_name?: string;
  rating_total?: number;
  rating_taste?: number;
  aspect_taste?: number;
  content?: string;
  visit_date?: string;
  is_hidden: boolean;
  report_count: number;
  created_at: string;
}

export interface FeedEvent {
  id: number;
  scope: string;        // local / overseas / industry
  category: string;     // new_open / relocated / closed / chef_changed / guest_kitchen / collaboration / popup / award / menu_update / coming_soon
  title: string;
  summary?: string;
  event_date?: string;
  expires_on?: string;          // 活动结束日期（popup / guest_kitchen / collaboration）
  restaurant_id?: number | null;
  related_restaurant_id?: number | null;
  chef_id?: number | null;
  district?: string;
  city?: string;
  confidence: string;   // high / mid / low
  status: string;       // verified / rumor
  sources?: string | string[] | null;   // 来源链接（JSON 数组串或数组）
  registration_url?: string | null;    // 报名入口链接（如有）
  registration_info?: string | null;   // 报名方式说明（如有）
  chef_name?: string | null;           // 主厨名（反范式冗余，如有）
  // —— 前端合并/派生字段（不来自表，用于去重与展示）——
  mergedIds?: number[];                // 被合并掉的同源事件 id
  restaurant_name?: string;             // 前端按 restaurant_id 补的餐厅名
  related_restaurant_name?: string;     // 前端按 related_restaurant_id 补的餐厅名
}
