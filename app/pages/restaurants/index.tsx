import Head from 'next/head';
import Link from 'next/link';
import { useEffect, useState, useMemo } from 'react';
import { supabase, Restaurant, Cuisine } from '@/lib/supabase';

const TIERS = ['全部', '亲民', '中端', '高端'];
const DIMENSIONS = [
  { key: '菜系', label: '菜系' },
  { key: '食材', label: '食材' },
  { key: '形式', label: '形式' },
];

export default function RestaurantsPage() {
  const [restaurants, setRestaurants] = useState<Restaurant[]>([]);
  const [cuisines, setCuisines] = useState<Cuisine[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [tier, setTier] = useState('全部');
  const [activeDim, setActiveDim] = useState('菜系');
  const [selectedCuisine, setSelectedCuisine] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      const [{ data: rest }, { data: cuis }] = await Promise.all([
        supabase.from('restaurants').select('*').order('name'),
        supabase.from('cuisines').select('*').order('dimension').order('name'),
      ]);
      setRestaurants(rest || []);
      setCuisines(cuis || []);
      setLoading(false);
    }
    load();
  }, []);

  const filtered = useMemo(() => {
    let result = restaurants;
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      result = result.filter(r =>
        r.name.toLowerCase().includes(q) ||
        (r.address && r.address.toLowerCase().includes(q)) ||
        (r.signature_dishes && Array.isArray(r.signature_dishes) && r.signature_dishes.some(d => d.toLowerCase().includes(q)))
      );
    }
    if (tier !== '全部') {
      result = result.filter(r => r.tier === tier);
    }
    return result;
  }, [restaurants, search, tier]);

  const dimCuisines = cuisines.filter(c => c.dimension === activeDim);

  if (loading) return <div className="p-8 text-gray-400">加载中...</div>;

  return (
    <div className="min-h-screen bg-gray-50">
      <Head>
        <title>全部餐厅 · China Travel</title>
      </Head>

      <nav className="bg-white border-b sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
          <Link href="/" className="font-bold text-lg text-primary-700">← 首页</Link>
          <span className="text-gray-600">共 {filtered.length} 家</span>
        </div>
      </nav>

      <div className="max-w-6xl mx-auto px-4 py-6">
        {/* 搜索栏 */}
        <div className="bg-white border rounded-lg p-4 mb-4">
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="搜索店名、地址、特色菜..."
            className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none text-sm"
          />
        </div>

        {/* 筛选栏 */}
        <div className="bg-white border rounded-lg p-4 mb-4 space-y-3">
          {/* 档位筛选 */}
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm text-gray-500 w-12">档位</span>
            {TIERS.map(t => (
              <button
                key={t}
                onClick={() => setTier(t)}
                className={`px-3 py-1 rounded-full text-sm transition ${
                  tier === t
                    ? 'bg-primary-600 text-white'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}
              >
                {t}
              </button>
            ))}
          </div>

          {/* 维度切换 */}
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm text-gray-500 w-12">分类</span>
            {DIMENSIONS.map(d => (
              <button
                key={d.key}
                onClick={() => { setActiveDim(d.key); setSelectedCuisine(null); }}
                className={`px-3 py-1 rounded-full text-sm transition ${
                  activeDim === d.key
                    ? 'bg-amber-500 text-white'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}
              >
                {d.label}
              </button>
            ))}
          </div>

          {/* 具体分类标签 */}
          <div className="flex items-center gap-2 flex-wrap pl-14">
            <button
              onClick={() => setSelectedCuisine(null)}
              className={`px-2.5 py-1 rounded text-xs transition ${
                selectedCuisine === null
                  ? 'bg-primary-100 text-primary-700 font-medium'
                  : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              全部
            </button>
            {dimCuisines.map(c => (
              <button
                key={c.id}
                onClick={() => setSelectedCuisine(selectedCuisine === c.name ? null : c.name)}
                className={`px-2.5 py-1 rounded text-xs transition ${
                  selectedCuisine === c.name
                    ? 'bg-primary-100 text-primary-700 font-medium'
                    : 'text-gray-500 hover:text-gray-700'
                }`}
              >
                {c.name}
              </button>
            ))}
          </div>
        </div>

        {/* 餐厅列表 */}
        {filtered.length === 0 ? (
          <div className="text-center py-16 text-gray-400">
            <p className="text-4xl mb-3">🔍</p>
            <p>没有找到匹配的餐厅</p>
            <p className="text-sm mt-1">试试调整筛选条件</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {filtered.map((r) => (
              <Link
                key={r.id}
                href={`/restaurants/${r.id}`}
                className="bg-white rounded-lg p-4 border hover:border-primary-300 hover:shadow transition"
              >
                <div className="flex justify-between items-start">
                  <div className="flex-1 min-w-0">
                    <h3 className="font-semibold text-gray-800 truncate">{r.name}</h3>
                    <p className="text-sm text-gray-500 mt-1 truncate">{r.address || '地址待补'}</p>
                    {r.signature_dishes && Array.isArray(r.signature_dishes) && r.signature_dishes.length > 0 && (
                      <p className="text-xs text-gray-400 mt-1 truncate">
                        {r.signature_dishes.slice(0, 3).join(' · ')}
                      </p>
                    )}
                  </div>
                  <div className="text-right ml-3 flex-shrink-0">
                    <span className={`text-xs px-2 py-1 rounded ${
                      r.tier === '高端' ? 'bg-amber-100 text-amber-700' :
                      r.tier === '中端' ? 'bg-blue-100 text-blue-700' :
                      'bg-green-100 text-green-700'
                    }`}>{r.tier || '—'}</span>
                    <p className="text-sm font-semibold text-gray-700 mt-1">¥{r.price_avg || '?'}</p>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
