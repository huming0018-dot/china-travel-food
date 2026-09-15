import { useRouter } from 'next/router';
import { useEffect, useState } from 'react';
import Link from 'next/link';
import Head from 'next/head';
import { supabase, Restaurant } from '@/lib/supabase';
import { useFavorites } from '@/lib/favorites';
import { useAuth } from '@/lib/auth';

export default function RestaurantDetail() {
  const router = useRouter();
  const { id } = router.query;
  const [restaurant, setRestaurant] = useState<Restaurant | null>(null);
  const [loading, setLoading] = useState(true);
  const { isFavorite, toggleFavorite } = useFavorites();
  const { user } = useAuth();

  useEffect(() => {
    if (!id) return;
    async function load() {
      const { data } = await supabase
        .from('restaurants')
        .select('*')
        .eq('id', id)
        .single();
      setRestaurant(data);
      setLoading(false);
    }
    load();
  }, [id]);

  if (loading) return <div className="p-8 text-gray-400">加载中...</div>;
  if (!restaurant) return <div className="p-8 text-gray-400">餐厅不存在</div>;

  const r = restaurant;
  const dataAge = r.data_updated_at
    ? Math.floor((Date.now() - new Date(r.data_updated_at).getTime()) / (1000 * 60 * 60 * 24))
    : null;

  return (
    <div className="min-h-screen bg-gray-50">
      <Head>
        <title>{r.name} · China Travel</title>
      </Head>
      <nav className="bg-white border-b sticky top-0 z-50">
        <div className="max-w-4xl mx-auto px-4 h-14 flex items-center gap-4">
          <Link href="/restaurants" className="font-bold text-primary-700">← 列表</Link>
        </div>
      </nav>

      <div className="max-w-4xl mx-auto px-4 py-6">
        {/* 标题区 */}
        <div className="bg-white border rounded-lg p-6 mb-4">
          <div className="flex items-start justify-between">
            <div>
              <h1 className="text-2xl font-bold">{r.name}</h1>
              {r.name_en && <p className="text-gray-400 text-sm mt-1">{r.name_en}</p>}
              <div className="flex items-center gap-3 mt-3 text-sm">
                <span className="bg-primary-50 text-primary-700 px-2 py-1 rounded">{r.tier}</span>
                <span className="text-gray-600">¥{r.price_avg || '?'} / 人</span>
                <span className="text-gray-600">{r.district || ''}</span>
              </div>
            </div>
            <div className="flex items-start gap-3">
              {user && (
                <button
                  onClick={() => toggleFavorite(r.id)}
                  className={`p-2 rounded-full border transition ${
                    isFavorite(r.id)
                      ? 'bg-red-50 border-red-200 text-red-500'
                      : 'bg-white border-gray-200 text-gray-400 hover:text-red-500 hover:border-red-200'
                  }`}
                  title={isFavorite(r.id) ? '取消收藏' : '收藏'}
                >
                  {isFavorite(r.id) ? '❤️' : '🤍'}
                </button>
              )}
              {r.score_total && (
                <div className="text-center">
                  <div className="text-3xl font-bold text-amber-600">{r.score_total.toFixed(1)}</div>
                  <div className="text-xs text-gray-400">综合评分</div>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* 基本信息 */}
        <div className="bg-white border rounded-lg p-6 mb-4">
          <h2 className="font-bold mb-3">基本信息</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
            <div><span className="text-gray-500">地址：</span>{r.address || '—'}</div>
            <div><span className="text-gray-500">电话：</span>{r.phone || '—'}</div>
            <div><span className="text-gray-500">预订：</span>{r.booking_method || '—'}</div>
            <div><span className="text-gray-500">折扣：</span>{r.discount_info || '—'}</div>
          </div>
          {dataAge !== null && (
            <div className="mt-3 text-xs text-gray-400">
              数据更新于 {dataAge} 天前 {dataAge > 90 ? '· 建议复查' : ''}
            </div>
          )}
        </div>

        {/* 招牌菜 */}
        {r.signature_dishes && Array.isArray(r.signature_dishes) && r.signature_dishes.length > 0 && (
          <div className="bg-white border rounded-lg p-6 mb-4">
            <h2 className="font-bold mb-3">招牌菜</h2>
            <div className="flex flex-wrap gap-2">
              {r.signature_dishes.map((dish, i) => (
                <span key={i} className="bg-amber-50 text-amber-800 px-3 py-1 rounded-full text-sm">
                  {dish}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* 评分明细 */}
        <div className="bg-white border rounded-lg p-6 mb-4">
          <h2 className="font-bold mb-3">反软广评分明细</h2>
          <div className="space-y-2 text-sm">
            {r.score_objective !== undefined && (
              <div className="flex justify-between"><span className="text-gray-500">客观评分（平台分×可信度）</span><span>{r.score_objective?.toFixed(1)}</span></div>
            )}
            {r.score_diner !== undefined && (
              <div className="flex justify-between"><span className="text-gray-500">食客评分（只计堂食）</span><span>{r.score_diner?.toFixed(1)}</span></div>
            )}
            {r.score_taste !== undefined && (
              <div className="flex justify-between"><span className="text-gray-500">口味评分</span><span>{r.score_taste?.toFixed(1)}</span></div>
            )}
            {r.score_endorsement !== undefined && (
              <div className="flex justify-between"><span className="text-gray-500">背书评分</span><span>{r.score_endorsement?.toFixed(1)}</span></div>
            )}
            {r.soft_ad_penalty !== undefined && r.soft_ad_penalty > 0 && (
              <div className="flex justify-between text-red-500"><span>软广嫌疑扣分</span><span>-{r.soft_ad_penalty.toFixed(1)}</span></div>
            )}
          </div>
          {r.evidence_summary && (
            <div className="mt-3 p-3 bg-gray-50 rounded text-sm text-gray-600">
              <span className="font-medium">食客证据：</span>{r.evidence_summary}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
