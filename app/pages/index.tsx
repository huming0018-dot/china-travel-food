import Head from 'next/head';
import Link from 'next/link';
import { useEffect, useState } from 'react';
import { supabase, Restaurant, Cuisine } from '@/lib/supabase';
import { useAuth } from '@/lib/auth';

const DIMENSIONS = [
  { key: '菜系', label: '按菜系', icon: '🍜' },
  { key: '食材', label: '按食材', icon: '🥩' },
  { key: '形式', label: '按形式', icon: '🍽️' },
];

export default function Home() {
  const [restaurants, setRestaurants] = useState<Restaurant[]>([]);
  const [cuisines, setCuisines] = useState<Cuisine[]>([]);
  const [activeDim, setActiveDim] = useState('菜系');
  const [loading, setLoading] = useState(true);
  const { user, signOut } = useAuth();

  useEffect(() => {
    async function load() {
      // 加载推荐餐厅
      const { data: rest, error: restError } = await supabase
        .from('restaurants')
        .select('*')
        .eq('status', '推荐')
        .order('score_objective', { ascending: false })
        .limit(12);
      if (restError) console.error('restaurants query error:', restError);
      setRestaurants(rest || []);

      // 加载分类
      const { data: cuis, error: cuisError } = await supabase
        .from('cuisines')
        .select('*')
        .order('dimension')
        .order('name');
      if (cuisError) console.error('cuisines query error:', cuisError);
      setCuisines(cuis || []);
      setLoading(false);
    }
    load();
  }, []);

  const filteredCuisines = cuisines.filter((c) => c.dimension === activeDim);

  return (
    <div className="min-h-screen">
      <Head>
        <title>China Travel · 美食地图</title>
        <meta name="description" content="上海美食地图 — 按菜系/食材/形式三维浏览，反软广真实评分" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </Head>

      {/* 顶部导航 */}
      <nav className="bg-white border-b sticky top-0 z-50">
        <div className="max-w-6xl mx-auto px-4 h-14 flex items-center justify-between">
          <Link href="/" className="font-bold text-lg text-primary-700">
            🍜 China Travel
          </Link>
          <div className="flex items-center gap-4 text-sm">
            <Link href="/restaurants" className="text-gray-600 hover:text-primary-600">
              全部餐厅
            </Link>
            <Link href="/map" className="text-gray-600 hover:text-primary-600">
              地图
            </Link>
            {user ? (
              <div className="flex items-center gap-3">
                <span className="text-gray-500 text-xs">{user.email}</span>
                <button
                  onClick={() => signOut()}
                  className="text-gray-600 hover:text-red-600"
                >
                  退出
                </button>
              </div>
            ) : (
              <Link href="/login" className="bg-primary-600 text-white px-3 py-1.5 rounded-lg hover:bg-primary-700">
                登录
              </Link>
            )}
          </div>
        </div>
      </nav>

      {/* Hero */}
      <section className="bg-gradient-to-br from-primary-50 to-white py-12">
        <div className="max-w-6xl mx-auto px-4 text-center">
          <h1 className="text-3xl md:text-4xl font-bold mb-3">上海美食地图</h1>
          <p className="text-gray-600 mb-6">
            按菜系 / 食材 / 形式三维浏览 · 反软广真实评分 · 只认口味
          </p>
          <div className="flex justify-center gap-2">
            {DIMENSIONS.map((d) => (
              <button
                key={d.key}
                onClick={() => setActiveDim(d.key)}
                className={`px-4 py-2 rounded-full text-sm font-medium transition ${
                  activeDim === d.key
                    ? 'bg-primary-600 text-white'
                    : 'bg-white text-gray-600 border hover:border-primary-400'
                }`}
              >
                {d.icon} {d.label}
              </button>
            ))}
          </div>
        </div>
      </section>

      {/* 分类网格 */}
      <section className="max-w-6xl mx-auto px-4 py-8">
        <h2 className="text-xl font-bold mb-4">
          {DIMENSIONS.find((d) => d.key === activeDim)?.label}浏览
        </h2>
        {loading ? (
          <p className="text-gray-400">加载中...</p>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {filteredCuisines.map((c) => (
              <Link
                key={c.id}
                href={`/restaurants?cuisine=${encodeURIComponent(c.name)}`}
                className="card-hover bg-white border rounded-lg p-4 block"
              >
                <div className="font-medium mb-1">{c.name}</div>
                <div className="text-xs text-gray-500">
                  ¥{c.price_low || '?'} ~ ¥{c.price_high || '?'}
                </div>
              </Link>
            ))}
          </div>
        )}
      </section>

      {/* 推荐餐厅 */}
      <section className="max-w-6xl mx-auto px-4 py-8">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-bold">高分推荐</h2>
          <Link href="/restaurants" className="text-sm text-primary-600 hover:underline">
            查看全部 →
          </Link>
        </div>
        {restaurants.length === 0 ? (
          <p className="text-gray-400">暂无推荐餐厅（请先运行数据同步）</p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {restaurants.map((r) => (
              <Link
                key={r.id}
                href={`/restaurants/${r.id}`}
                className="card-hover bg-white border rounded-lg p-4 block"
              >
                <div className="flex items-start justify-between mb-2">
                  <h3 className="font-bold">{r.name}</h3>
                  {r.score_total && (
                    <span className="text-sm font-bold text-amber-600">
                      ★ {r.score_total.toFixed(1)}
                    </span>
                  )}
                </div>
                <div className="text-sm text-gray-600 mb-2">
                  {r.tier} · ¥{r.price_avg || '?'} · {r.district || ''}
                </div>
                {r.signature_dishes && Array.isArray(r.signature_dishes) && (
                  <div className="text-xs text-gray-500">
                    {r.signature_dishes.slice(0, 3).join(' / ')}
                  </div>
                )}
              </Link>
            ))}
          </div>
        )}
      </section>

      {/* 页脚 */}
      <footer className="border-t mt-12 py-6 text-center text-sm text-gray-400">
        <p>China Travel · 美食地图 | 数据来源：飞书表格 + 食客实测 | 反软广评分体系</p>
      </footer>
    </div>
  );
}
