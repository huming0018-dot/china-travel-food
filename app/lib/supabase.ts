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
  chain_type?: string;        // 连锁类型：直营/加盟/单店/工业化
  central_kitchen?: boolean; // 中央厨房
  premade_risk?: string;     // 预制菜风险
  price_position?: string;   // 品类内相对档：入门/主流/进阶/高端/旗舰
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
