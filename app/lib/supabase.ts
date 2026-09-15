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
  location?: string;
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
