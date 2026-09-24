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
  restaurant_id?: number;
  related_restaurant_id?: number;
  chef_id?: number;
  district?: string;
  confidence: string;   // high / mid / low
  status: string;       // verified / rumor
}
