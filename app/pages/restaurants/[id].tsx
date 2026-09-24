import { useRouter } from 'next/router';
import { useEffect, useState, useMemo } from 'react';
import Link from 'next/link';
import Head from 'next/head';
import dynamic from 'next/dynamic';
import { supabase, Restaurant, Cuisine, Review } from '@/lib/supabase';
import { parseLngLat, parseLatLng } from '@/lib/geo';
import { safeText } from '@/lib/format';
import { useFavorites } from '@/lib/favorites';
import { useAuth } from '@/lib/auth';

// 内嵌小地图（Leaflet 依赖 window，禁用 SSR）
const MapContainer = dynamic(() => import('react-leaflet').then((m) => m.MapContainer), { ssr: false });
const TileLayer = dynamic(() => import('react-leaflet').then((m) => m.TileLayer), { ssr: false });
const Marker = dynamic(() => import('react-leaflet').then((m) => m.Marker), { ssr: false });

const SCORE_BARS = [
  { key: 'score_objective', label: '客观评分', desc: '平台分×可信度', max: 40 },
  { key: 'score_diner', label: '食客评分', desc: '只计堂食实测', max: 30 },
  { key: 'score_taste', label: '口味评分', desc: '食材/技法/呈现', max: 20 },
  { key: 'score_endorsement', label: '背书评分', desc: '名厨/老店/传承', max: 10 },
];

const tierClass = (t?: string) =>
  ({ 经济: 'tag-budget', 平价: 'tag-value', 中档: 'tag-mid', 高档: 'tag-fine', 奢华: 'tag-luxury' } as Record<string, string>)[t || ''] ||
  'tag-budget';

async function fetchAll<T = any>(table: string, select: string, orderCol: string): Promise<T[]> {
  const step = 1000;
  let start = 0;
  let all: T[] = [];
  for (;;) {
    const { data, error } = await supabase.from(table).select(select).order(orderCol).range(start, start + step - 1);
    if (error) throw error;
    if (!data || data.length === 0) break;
    all = all.concat(data as T[]);
    if (data.length < step) break;
    start += step;
  }
  return all;
}

function StarRating({ value, onChange, size = 'text-lg' }: { value: number; onChange?: (v: number) => void; size?: string }) {
  return (
    <div className="flex gap-1">
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          key={n}
          type="button"
          onClick={() => onChange && onChange(n)}
          disabled={!onChange}
          className={`${size} transition ${n <= value ? 'text-terracotta' : 'text-mocha-faint/30'} ${onChange ? 'hover:scale-110 cursor-pointer' : 'cursor-default'}`}
        >
          ★
        </button>
      ))}
    </div>
  );
}

export default function RestaurantDetail() {
  const router = useRouter();
  const { id } = router.query;
  const [restaurant, setRestaurant] = useState<Restaurant | null>(null);
  const [cuisines, setCuisines] = useState<Cuisine[]>([]);
  const [rc, setRc] = useState<{ restaurant_id: number; cuisine_id: number }[]>([]);
  const [loading, setLoading] = useState(true);
  const { isFavorite, toggleFavorite } = useFavorites();
  const { user } = useAuth();

  // UGC 评价状态
  const [reviews, setReviews] = useState<Review[]>([]);
  const [reviewsLoading, setReviewsLoading] = useState(true);
  const [formRating, setFormRating] = useState(0);
  const [formTaste, setFormTaste] = useState(0);
  const [formContent, setFormContent] = useState('');
  const [formDate, setFormDate] = useState('');
  const [formSubmitting, setFormSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [formSuccess, setFormSuccess] = useState(false);

  useEffect(() => {
    if (!id) return;
    (async () => {
      const { data: rest } = await supabase.from('restaurants').select('*').eq('id', id).single();
      const [cuis, links] = await Promise.all([
        fetchAll<Cuisine>('cuisines', '*', 'id'),
        fetchAll<{ restaurant_id: number; cuisine_id: number }>('restaurant_cuisines', 'restaurant_id,cuisine_id', 'restaurant_id'),
      ]);
      setRestaurant(rest);
      setCuisines(cuis);
      setRc(links);
      setLoading(false);
    })();
  }, [id]);

  // 拉取食客评价
  useEffect(() => {
    if (!id) return;
    (async () => {
      const { data } = await supabase
        .from('reviews')
        .select('*')
        .eq('restaurant_id', id)
        .eq('is_hidden', false)
        .order('created_at', { ascending: false });
      setReviews((data as Review[]) || []);
      setReviewsLoading(false);
    })();
  }, [id]);

  // 修复 Leaflet 默认图标路径
  useEffect(() => {
    if (typeof window === 'undefined') return;
    import('leaflet').then((L) => {
      delete (L.Icon.Default.prototype as any)._getIconUrl;
      L.Icon.Default.mergeOptions({
        iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon-2x.png',
        iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon.png',
        shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png',
      });
    });
  }, []);

  const tagsById = useMemo(() => {
    const m: Record<number, Cuisine> = {};
    cuisines.forEach((c) => { m[c.id] = c; });
    return m;
  }, [cuisines]);

  const namesByDim = useMemo(() => {
    if (!restaurant) return { 菜系: [] as string[], 认证: [] as string[], 形式: [] as string[], 标签: [] as string[] };
    const out: Record<string, string[]> = { 菜系: [], 认证: [], 形式: [], 标签: [] };
    rc.filter((x) => x.restaurant_id === restaurant.id).forEach((x) => {
      const c = tagsById[x.cuisine_id];
      if (c && out[c.dimension]) out[c.dimension].push(c.name);
    });
    return out;
  }, [restaurant, rc, tagsById]);

  // 食客均分
  const dinerAvg = useMemo(() => {
    if (reviews.length === 0) return null;
    const rated = reviews
      .map((r) => (typeof r.rating_total === 'number' ? r.rating_total : r.aspect_taste))
      .filter((v): v is number => typeof v === 'number');
    if (rated.length === 0) return null;
    return rated.reduce((acc, v) => acc + v, 0) / rated.length;
  }, [reviews]);

  if (loading) return (
    <div className="min-h-screen bg-cream-50 flex items-center justify-center"><div className="spinner" /></div>
  );
  if (!restaurant) return <div className="min-h-screen bg-cream-50 flex items-center justify-center text-mocha-faint">餐厅不存在</div>;

  const r = restaurant;
  const isClosed = r.status === 'closed' || r.status === '关店';
  const dataAge = r.data_updated_at
    ? Math.floor((Date.now() - new Date(r.data_updated_at).getTime()) / (1000 * 60 * 60 * 24))
    : null;
  const lngLat = parseLngLat(r.location);
  const pos = parseLatLng(r.location);

  // 提交评价
  const handleSubmitReview = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    setFormSuccess(false);
    if (!user) { setFormError('请先登录'); return; }
    if (formRating < 1) { setFormError('请选择总体评分'); return; }
    setFormSubmitting(true);
    const { error } = await supabase.from('reviews').insert({
      restaurant_id: r.id,
      user_id: user.id,
      author_name: user.email?.split('@')[0] || '食客',
      rating_total: formRating,
      rating_taste: formTaste || null,
      content: formContent || null,
      visit_date: formDate || null,
    });
    setFormSubmitting(false);
    if (error) {
      setFormError(error.message);
    } else {
      setFormSuccess(true);
      setFormRating(0); setFormTaste(0); setFormContent(''); setFormDate('');
      // 重新拉取评价
      const { data } = await supabase
        .from('reviews')
        .select('*')
        .eq('restaurant_id', r.id)
        .eq('is_hidden', false)
        .order('created_at', { ascending: false });
      setReviews((data as Review[]) || []);
    }
  };

  // 举报评价
  const handleReport = async (reviewId: string, currentCount: number) => {
    await supabase.from('reviews').update({ report_count: currentCount + 1 }).eq('id', reviewId);
    setReviews((prev) => prev.map((rv) => rv.id === reviewId ? { ...rv, report_count: rv.report_count + 1 } : rv));
  };

  // 删除本人评价
  const handleDelete = async (reviewId: string) => {
    await supabase.from('reviews').delete().eq('id', reviewId);
    setReviews((prev) => prev.filter((rv) => rv.id !== reviewId));
  };

  return (
    <div className={`min-h-screen bg-cream-50 ${isClosed ? 'grayscale opacity-70' : ''}`}>
      <Head>
        <title>{r.name} · China Travel</title>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css" />
      </Head>

      <header className="border-b border-line sticky top-0 z-50 bg-cream-50/90 backdrop-blur-sm">
        <div className="max-w-4xl mx-auto px-6 h-14 flex items-center justify-between">
          <Link href="/restaurants" className="flex items-center gap-2 text-mocha hover:text-mocha-soft transition">
            <span>←</span><span className="serif text-base font-medium">返回列表</span>
          </Link>
          {user && (
            <button onClick={() => toggleFavorite(r.id)}
              className={`flex items-center gap-2 px-3 py-1.5 text-xs transition border rounded-full ${
                isFavorite(r.id) ? 'bg-mocha text-cream-50 border-mocha' : 'border-line text-mocha-soft hover:border-mocha hover:text-mocha'
              }`}>
              {isFavorite(r.id) ? '♥' : '♡'}<span>{isFavorite(r.id) ? '已收藏' : '收藏'}</span>
            </button>
          )}
        </div>
      </header>

      <div className="max-w-4xl mx-auto px-6 py-10">
        {/* 关店标记 */}
        {isClosed && (
          <div className="mb-6 p-3 bg-mocha/10 border border-mocha/20 text-center text-sm text-mocha rounded">
            已关店
          </div>
        )}

        {/* 标题区 */}
        <div className="mb-10">
          <div className="flex items-center gap-3 mb-4 flex-wrap">
            <span className="w-8 h-px bg-mocha" />
            {namesByDim.菜系.map((cn, i) => (
              <Link key={i} href={`/restaurants?cuisine=${encodeURIComponent(cn)}`}>
                <span className="kicker text-mocha-faint hover:text-terracotta transition cursor-pointer">{cn}</span>
              </Link>
            ))}
            {namesByDim.认证.map((a) => (
              <span key={a} className="kicker bg-mocha text-mustard-soft px-2 py-0.5 rounded">{a}</span>
            ))}
          </div>
          <h1 className="serif text-4xl md:text-5xl font-medium leading-tight mb-3">{r.name}</h1>
          {r.name_en && <p className="text-mocha-faint italic text-sm">{r.name_en}</p>}
          <div className="flex items-center gap-4 md:gap-6 mt-6 flex-wrap">
            <span title="绝对价位档" className={`tag ${tierClass(r.tier)}`}>{r.tier || '—'}</span>
            {r.price_position && (
              <span title="品类内相对档" className="text-xs text-mocha-soft">本品类档 · <span className="font-medium text-mocha">{r.price_position}</span></span>
            )}
            <div className="serif text-xl font-medium">
              {r.price_avg ? `¥${r.price_avg}` : '—'}<span className="text-sm text-mocha-faint"> / 人</span>
            </div>
            {(r.business_area || r.district) && (
              <div className="text-sm text-mocha-soft">📍 {[safeText(r.business_area), r.district].filter(Boolean).join(' · ')}</div>
            )}
            {lngLat && (
              <a
                href={`https://uri.amap.com/marker?position=${lngLat[0]},${lngLat[1]}&name=${encodeURIComponent(r.name)}`}
                target="_blank" rel="noopener noreferrer"
                className="text-sm text-terracotta hover:underline"
              >
                🧭 高德导航
              </a>
            )}
            {r.score_total && (
              <div className="ml-auto text-right">
                <div className="serif text-3xl font-medium">{r.score_total.toFixed(1)}</div>
                <div className="kicker text-mocha-faint">综合评分</div>
              </div>
            )}
          </div>
        </div>

        {/* 基本信息 */}
        <section className="border-t border-line pt-8 mb-10">
          <h2 className="kicker text-mocha-faint mb-6">INFORMATION / 基本信息</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-x-12 gap-y-5">
            <InfoRow label="地址" value={r.address} />
            <InfoRow label="电话" value={r.phone} />
            <InfoRow label="预订方式" value={r.booking_method} />
            <InfoRow label="折扣/团购" value={r.discount_info} />
            {namesByDim.形式.length > 0 && <InfoRow label="业态" value={namesByDim.形式.join('、')} />}
            {r.investor_info && <InfoRow label="投资人/公司" value={r.investor_info} />}
            {r.chain_type && <InfoRow label="连锁类型" value={r.chain_type} />}
            {r.central_kitchen && <InfoRow label="中央厨房" value={r.central_kitchen} />}
            {r.premade_risk && <InfoRow label="预制菜风险" value={r.premade_risk} />}
          </div>
          {dataAge !== null && (
            <div className="mt-6 pt-5 border-t border-line flex items-center gap-2">
              <span className="kicker text-mocha-faint">
                数据更新于 {dataAge} 天前{isClosed ? '' : '，营业状态以商家为准'}
              </span>
              {dataAge > 90 && <span className="kicker text-terracotta-deep">· 建议复查</span>}
            </div>
          )}
        </section>

        {/* 内嵌地图定位 */}
        {pos && (
          <section className="border-t border-line pt-8 mb-10">
            <h2 className="kicker text-mocha-faint mb-6">MAP / 地图定位</h2>
            <div className="h-64 rounded-xl overflow-hidden border border-line">
              <MapContainer center={pos} zoom={16} style={{ height: '100%', width: '100%' }}>
                <TileLayer
                  attribution="&copy; 高德地图 AutoNavi"
                  url="https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}"
                  subdomains={['1', '2', '3', '4']}
                />
                <Marker position={pos} />
              </MapContainer>
            </div>
          </section>
        )}

        {/* 招牌菜 */}
        {r.signature_dishes && Array.isArray(r.signature_dishes) && r.signature_dishes.length > 0 && (
          <section className="border-t border-line pt-8 mb-10">
            <h2 className="kicker text-mocha-faint mb-6">SIGNATURE / 招牌菜</h2>
            <div className="flex flex-wrap gap-2">
              {r.signature_dishes.map((dish, i) => (
                <span key={i} className="px-4 py-2 bg-white border border-line text-sm serif italic rounded-lg">{dish}</span>
              ))}
            </div>
          </section>
        )}

        {/* 官方反软广评分明细 */}
        <section className="border-t border-line pt-8 mb-10">
          <h2 className="kicker text-mocha-faint mb-6">OFFICIAL SCORE / 官方反软广评分明细</h2>
          <div className="space-y-5">
            {SCORE_BARS.map((item) => {
              const value = (r as any)[item.key] as number | undefined;
              if (value === undefined || value === null) return null;
              const pct = Math.min(100, (value / item.max) * 100);
              return (
                <div key={item.key}>
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-3">
                      <span className="serif text-base font-medium">{item.label}</span>
                      <span className="kicker text-mocha-faint">{item.desc}</span>
                    </div>
                    <span className="serif text-base font-medium tabular-nums">
                      {value.toFixed(1)}<span className="text-sm text-mocha-faint"> / {item.max}</span>
                    </span>
                  </div>
                  <div className="h-px bg-line relative">
                    <div className="absolute top-0 left-0 h-px bg-terracotta" style={{ width: `${pct}%` }} />
                  </div>
                </div>
              );
            })}
            {r.soft_ad_penalty !== undefined && r.soft_ad_penalty > 0 && (
              <div className="flex items-center justify-between pt-4 border-t border-line">
                <span className="kicker text-terracotta-deep">⚠️ 软广嫌疑扣分</span>
                <span className="serif text-base font-medium text-terracotta-deep">−{r.soft_ad_penalty.toFixed(1)}</span>
              </div>
            )}
          </div>

          {r.evidence_summary && (
            <div className="mt-8 p-5 bg-white border border-line rounded-xl">
              <div className="kicker text-mocha-faint mb-2">EVIDENCE / 食客证据</div>
              <p className="text-sm text-mocha-soft leading-relaxed whitespace-pre-line">{safeText(r.evidence_summary)}</p>
            </div>
          )}
        </section>

        {/* UGC 食客评价区 */}
        <section className="border-t border-line pt-8 mb-10">
          <div className="flex items-baseline justify-between mb-6 flex-wrap gap-2">
            <h2 className="kicker text-mocha-faint">DINER REVIEWS / 食客评价</h2>
            <div className="flex items-center gap-4">
              {dinerAvg !== null && (
                <span className="serif text-lg font-medium">
                  {dinerAvg.toFixed(1)}<span className="text-sm text-mocha-faint"> / 5</span>
                </span>
              )}
              <span className="text-xs text-mocha-faint">{reviews.length} 条评价</span>
            </div>
          </div>

          {/* 评价表单 */}
          {user ? (
            <form onSubmit={handleSubmitReview} className="mb-8 p-5 bg-white border border-line rounded-xl space-y-4">
              <div className="flex items-center gap-4 flex-wrap">
                <span className="kicker text-mocha-faint w-20">总体评分</span>
                <StarRating value={formRating} onChange={setFormRating} />
              </div>
              <div className="flex items-center gap-4 flex-wrap">
                <span className="kicker text-mocha-faint w-20">口味评分</span>
                <StarRating value={formTaste} onChange={setFormTaste} />
              </div>
              <div>
                <label className="kicker text-mocha-faint block mb-2">短评</label>
                <textarea
                  value={formContent}
                  onChange={(e) => setFormContent(e.target.value)}
                  rows={3}
                  maxLength={500}
                  placeholder="说说你的就餐体验…"
                  className="w-full px-3 py-2 bg-cream-50 border border-line rounded text-sm focus:outline-none focus:border-terracotta resize-none"
                />
              </div>
              <div className="flex items-center gap-4 flex-wrap">
                <span className="kicker text-mocha-faint">就餐日期</span>
                <input
                  type="date"
                  value={formDate}
                  onChange={(e) => setFormDate(e.target.value)}
                  className="px-3 py-1.5 bg-cream-50 border border-line rounded text-sm focus:outline-none focus:border-terracotta"
                />
              </div>
              {formError && <div className="text-xs text-terracotta-deep">⚠️ {formError}</div>}
              {formSuccess && <div className="text-xs text-green-700">✓ 评价已发布，感谢分享！</div>}
              <button type="submit" disabled={formSubmitting} className="btn btn-primary">
                {formSubmitting ? '提交中…' : '发布评价'}
              </button>
            </form>
          ) : (
            <div className="mb-8 p-5 bg-white border border-line rounded-xl text-center">
              <p className="text-sm text-mocha-soft mb-3">登录后即可打卡评价</p>
              <Link href="/login" className="btn btn-outline">登录 / 注册</Link>
            </div>
          )}

          {/* 评价列表 */}
          {reviewsLoading ? (
            <div className="text-center py-8 text-mocha-faint text-sm">加载评价中…</div>
          ) : reviews.length === 0 ? (
            <div className="text-center py-8 text-mocha-faint text-sm">还没有食客评价，来抢沙发吧</div>
          ) : (
            <div className="space-y-4">
              {reviews.map((rv) => (
                <div key={rv.id} className="p-4 bg-white border border-line rounded-xl">
                  <div className="flex items-center justify-between mb-2 flex-wrap gap-2">
                    <div className="flex items-center gap-3">
                      <span className="serif text-sm font-medium">{rv.author_name || '食客'}</span>
                      {typeof rv.rating_total === 'number' ? (
                        <StarRating value={rv.rating_total} size="text-sm" />
                      ) : typeof rv.aspect_taste === 'number' ? (
                        <span className="text-sm text-terracotta tracking-tight">
                          {'★'.repeat(rv.aspect_taste)}
                          <span className="text-2xs text-mocha-faint ml-1">口味 {rv.aspect_taste}/5</span>
                        </span>
                      ) : null}
                    </div>
                    <div className="flex items-center gap-3 text-2xs text-mocha-faint">
                      {rv.visit_date && <span>📅 {rv.visit_date}</span>}
                      <span>{new Date(rv.created_at).toLocaleDateString('zh-CN')}</span>
                      {user?.id === rv.user_id ? (
                        <button onClick={() => handleDelete(rv.id)} className="text-terracotta hover:underline">删除</button>
                      ) : (
                        <button onClick={() => handleReport(rv.id, rv.report_count)} className="hover:text-terracotta">
                          举报{rv.report_count > 0 ? ` (${rv.report_count})` : ''}
                        </button>
                      )}
                    </div>
                  </div>
                  {rv.content && <p className="text-sm text-mocha-soft leading-relaxed">{rv.content}</p>}
                </div>
              ))}
            </div>
          )}
        </section>

        <div className="flex gap-4 pt-8 border-t border-line">
          <Link href="/restaurants" className="btn btn-outline flex-1">← 更多餐厅</Link>
          <Link href="/map" className="btn btn-primary flex-1">地图查看</Link>
        </div>
      </div>
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value?: any }) {
  const text = safeText(value);
  return (
    <div className="flex items-start gap-4">
      <span className="kicker text-mocha-faint w-16 flex-shrink-0 pt-0.5">{label}</span>
      <span className="text-sm text-mocha-soft break-words">{text && text !== '—' ? text : '—'}</span>
    </div>
  );
}
