import Head from 'next/head';
import Link from 'next/link';
import { useEffect, useState, useMemo } from 'react';
import { useRouter } from 'next/router';
import { supabase, Restaurant, Cuisine } from '@/lib/supabase';

const TIERS = ['全部', '亲民', '中端', '高端'];
const DIMENSIONS = [
  { key: '菜系', label: '菜系', en: 'Cuisine' },
  { key: '食材', label: '食材', en: 'Ingredient' },
  { key: '形式', label: '形式', en: 'Style' },
];

export default function RestaurantsPage() {
  const router = useRouter();
  const [restaurants, setRestaurants] = useState<Restaurant[]>([]);
  const [cuisines, setCuisines] = useState<Cuisine[]>([]);
  const [restaurantCuisines, setRestaurantCuisines] = useState<{restaurant_id: number, cuisine_id: number}[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [tier, setTier] = useState('全部');
  const [activeDim, setActiveDim] = useState('菜系');
  const [selectedCuisine, setSelectedCuisine] = useState<string | null>(null);
  const [sortBy, setSortBy] = useState<'score' | 'price_asc' | 'price_desc'>('score');

  useEffect(() => {
    if (router.query.cuisine) {
      setSelectedCuisine(decodeURIComponent(router.query.cuisine as string));
    }
  }, [router.query]);

  useEffect(() => {
    async function load() {
      const [{ data: rest }, { data: cuis }, { data: rc }] = await Promise.all([
        supabase.from('restaurants').select('*').order('name'),
        supabase.from('cuisines').select('*').order('dimension').order('name'),
        supabase.from('restaurant_cuisines').select('restaurant_id,cuisine_id'),
      ]);
      setRestaurants(rest || []);
      setCuisines(cuis || []);
      setRestaurantCuisines(rc || []);
      setLoading(false);
    }
    load();
  }, []);

  const cuisineMap = useMemo(() => {
    const map: Record<number, string> = {};
    for (const c of cuisines) map[c.id] = c.name;
    return map;
  }, [cuisines]);

  const restaurantCuisineMap = useMemo(() => {
    const map: Record<number, string[]> = {};
    for (const rc of restaurantCuisines) {
      if (!map[rc.restaurant_id]) map[rc.restaurant_id] = [];
      const name = cuisineMap[rc.cuisine_id];
      if (name) map[rc.restaurant_id].push(name);
    }
    return map;
  }, [restaurantCuisines, cuisineMap]);

  // 修复后的过滤逻辑
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
    if (selectedCuisine) {
      result = result.filter(r => (restaurantCuisineMap[r.id] || []).includes(selectedCuisine));
    }
    if (sortBy === 'score') {
      result = [...result].sort((a, b) => (b.score_total || 0) - (a.score_total || 0));
    } else if (sortBy === 'price_asc') {
      result = [...result].sort((a, b) => (a.price_avg || 9999) - (b.price_avg || 9999));
    } else if (sortBy === 'price_desc') {
      result = [...result].sort((a, b) => (b.price_avg || 0) - (a.price_avg || 0));
    }
    return result;
  }, [restaurants, search, tier, selectedCuisine, sortBy, restaurantCuisineMap]);

  const dimCuisines = cuisines.filter(c => c.dimension === activeDim);

  // 按 parent_category 分组
  const cuisineGroups = useMemo(() => {
    const groups: Record<string, Cuisine[]> = {};
    for (const c of dimCuisines) {
      const parent = c.parent_category || '其他';
      if (!groups[parent]) groups[parent] = [];
      groups[parent].push(c);
    }
    return groups;
  }, [dimCuisines]);

  const [expandedGroup, setExpandedGroup] = useState<string | null>(null);

  if (loading) return (
    <div className="min-h-screen bg-paper-100 flex items-center justify-center">
      <div className="spinner" />
    </div>
  );

  return (
    <div className="min-h-screen bg-paper-100">
      <Head>
        <title>全部餐厅 · China Travel</title>
      </Head>

      {/* 顶部导航 */}
      <header className="border-b hairline sticky top-0 z-50 bg-paper-100/90 backdrop-blur-sm">
        <div className="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2 text-ink hover:text-ink-soft transition">
            <span>←</span>
            <span className="serif text-base font-medium">首页</span>
          </Link>
          <div className="flex items-center gap-4">
            <span className="kicker text-ink-faint">{filtered.length} 家餐厅</span>
            <Link href="/map" className="kicker text-ink-soft hover:text-ink transition">地图</Link>
          </div>
        </div>
      </header>

      <div className="max-w-6xl mx-auto px-6 py-8">
        {/* 页面标题 */}
        <div className="flex items-end justify-between mb-8">
          <div>
            <div className="kicker text-ink-faint mb-2">INDEX / 索引</div>
            <h1 className="serif text-3xl font-medium">全部餐厅</h1>
          </div>
        </div>

        {/* 搜索 */}
        <div className="mb-6">
          <div className="relative">
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="搜索店名、地址、特色菜..."
              className="w-full px-0 py-3 bg-transparent border-b hairline text-sm focus:outline-none placeholder:text-ink-faint"
            />
            {search && (
              <button
                onClick={() => setSearch('')}
                className="absolute right-0 top-1/2 -translate-y-1/2 text-ink-faint hover:text-ink text-sm"
              >
                ✕
              </button>
            )}
          </div>
        </div>

        {/* 筛选面板 */}
        <div className="border hairline bg-white p-6 mb-8">
          {/* 档位 + 排序 */}
          <div className="flex flex-wrap items-center gap-6 mb-5 pb-5 border-b hairline">
            <div className="flex items-center gap-3">
              <span className="kicker text-ink-faint w-10">档位</span>
              <div className="flex gap-1">
                {TIERS.map(t => (
                  <button
                    key={t}
                    onClick={() => setTier(t)}
                    className={`px-3 py-1.5 text-xs transition ${
                      tier === t
                        ? 'bg-terracotta text-white'
                        : 'text-ink-soft hover:bg-paper-100'
                    }`}
                  >
                    {t}
                  </button>
                ))}
              </div>
            </div>
            <div className="w-px h-4 bg-line" />
            <div className="flex items-center gap-3">
              <span className="kicker text-ink-faint">排序</span>
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as any)}
                className="px-2 py-1.5 bg-transparent border-b hairline text-xs outline-none focus:border-ink cursor-pointer"
              >
                <option value="score">评分最高</option>
                <option value="price_asc">人均从低到高</option>
                <option value="price_desc">人均从高到低</option>
              </select>
            </div>
          </div>

          {/* 维度 */}
          <div className="flex items-center gap-3 mb-4">
            <span className="kicker text-ink-faint w-10">维度</span>
            <div className="flex gap-1">
              {DIMENSIONS.map(d => (
                <button
                  key={d.key}
                  onClick={() => { setActiveDim(d.key); setSelectedCuisine(null); setExpandedGroup(null); }}
                  className={`px-3 py-1.5 text-xs transition ${
                    activeDim === d.key
                      ? 'bg-terracotta text-white'
                      : 'text-ink-soft hover:bg-paper-100'
                  }`}
                >
                  {d.label}
                </button>
              ))}
            </div>
          </div>

          {/* 分类标签 - 二级菜单 */}
          <div className="pl-13">
            {/* 全部按钮 */}
            <div className="mb-3">
              <button
                onClick={() => { setSelectedCuisine(null); setExpandedGroup(null); }}
                className={`px-3 py-1.5 text-xs transition font-medium ${
                  selectedCuisine === null
                    ? 'bg-terracotta text-white'
                    : 'text-ink-soft hover:bg-paper-100'
                }`}
              >
                全部
              </button>
            </div>

            {/* 一级分类列表 */}
            <div className="space-y-2">
              {Object.entries(cuisineGroups).map(([groupName, items]) => {
                const isExpanded = expandedGroup === groupName;
                const hasSelected = items.some(c => c.name === selectedCuisine);

                return (
                  <div key={groupName}>
                    {/* 一级分类按钮 */}
                    <button
                      onClick={() => setExpandedGroup(isExpanded ? null : groupName)}
                      className={`flex items-center gap-2 px-3 py-1.5 text-xs transition w-full text-left ${
                        hasSelected
                          ? 'text-terracotta font-medium'
                          : 'text-ink hover:bg-paper-100'
                      }`}
                    >
                      <span className="text-[10px] transition-transform" style={{
                        transform: isExpanded ? 'rotate(90deg)' : 'rotate(0deg)'
                      }}>›</span>
                      <span className="font-medium">{groupName}</span>
                      <span className="text-ink-faint text-[10px]">({items.length})</span>
                    </button>

                    {/* 二级分类（展开时显示） */}
                    {isExpanded && (
                      <div className="flex flex-wrap gap-1.5 pl-8 py-2">
                        {items.map(c => (
                          <button
                            key={c.id}
                            onClick={() => setSelectedCuisine(selectedCuisine === c.name ? null : c.name)}
                            className={`px-2.5 py-1 text-xs transition rounded ${
                              selectedCuisine === c.name
                                ? 'bg-terracotta text-white'
                                : 'text-ink-faint hover:text-ink hover:bg-paper-100'
                            }`}
                          >
                            {c.name}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* 已选条件 */}
        {(selectedCuisine || tier !== '全部' || search) && (
          <div className="flex items-center gap-2 mb-6 flex-wrap">
            <span className="kicker text-ink-faint">已选：</span>
            {selectedCuisine && (
              <span className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-terracotta text-white text-xs">
                {selectedCuisine}
                <button onClick={() => setSelectedCuisine(null)} className="hover:text-signal">✕</button>
              </span>
            )}
            {tier !== '全部' && (
              <span className="inline-flex items-center gap-1.5 px-2.5 py-1 border hairline text-xs">
                {tier}
                <button onClick={() => setTier('全部')} className="hover:text-ink">✕</button>
              </span>
            )}
            {search && (
              <span className="inline-flex items-center gap-1.5 px-2.5 py-1 border hairline text-xs">
                "{search}"
                <button onClick={() => setSearch('')} className="hover:text-ink">✕</button>
              </span>
            )}
          </div>
        )}

        {/* 餐厅列表 - 编辑式 */}
        {filtered.length === 0 ? (
          <div className="text-center py-20">
            <p className="serif text-2xl text-ink-faint mb-2">没有找到</p>
            <p className="text-sm text-ink-faint">试试调整筛选条件</p>
            <button
              onClick={() => { setSearch(''); setTier('全部'); setSelectedCuisine(null); }}
              className="mt-6 btn btn-outline"
            >
              清除筛选
            </button>
          </div>
        ) : (
          <div className="border-t hairline">
            {filtered.map((r, idx) => {
              const cuisineNames = restaurantCuisineMap[r.id] || [];
              return (
                <Link
                  key={r.id}
                  href={`/restaurants/${r.id}`}
                  className="group flex items-center gap-6 py-5 border-b hairline hover:bg-white transition -mx-6 px-6"
                >
                  <span className="numeral text-xl text-ink-faint w-8 flex-shrink-0">
                    {String(idx + 1).padStart(2, '0')}
                  </span>
                  <div className="flex-1 min-w-0">
                    <h3 className="serif text-base font-medium group-hover:italic transition truncate">{r.name}</h3>
                    <div className="flex items-center gap-2 mt-1">
                      {cuisineNames.slice(0, 2).map((cn, i) => (
                        <span key={i} className="kicker text-ink-faint">{cn}</span>
                      ))}
                    </div>
                  </div>
                  <div className="hidden md:block flex-1 min-w-0">
                    {r.signature_dishes && Array.isArray(r.signature_dishes) && r.signature_dishes.length > 0 && (
                      <p className="text-xs text-ink-soft truncate">{r.signature_dishes.slice(0, 3).join(' · ')}</p>
                    )}
                  </div>
                  <span className="hidden sm:block text-xs text-ink-faint w-16 flex-shrink-0 truncate">{r.district || '—'}</span>
                  <span className={`tag tag-${r.tier === '亲民' ? 'casual' : r.tier === '中端' ? 'mid' : 'premium'} flex-shrink-0`}>
                    {r.tier || '—'}
                  </span>
                  <span className="serif text-base font-medium w-14 text-right flex-shrink-0">¥{r.price_avg || '—'}</span>
                  <div className="w-12 text-right flex-shrink-0">
                    {r.score_total ? (
                      <span className="serif text-base font-medium">{r.score_total.toFixed(1)}</span>
                    ) : (
                      <span className="text-ink-faint text-xs">—</span>
                    )}
                  </div>
                </Link>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
