import Head from 'next/head';
import Link from 'next/link';
import { useEffect, useState, useMemo } from 'react';
import { supabase, Restaurant, Cuisine } from '@/lib/supabase';
import { useAuth } from '@/lib/auth';

const CUISINE_GROUPS = [
  { key: '日料·细分品类', label: '日料', en: 'Japanese', color: 'terracotta' },
  { key: '中餐·八大菜系', label: '中餐八大', en: 'Chinese Eight', color: 'mustard' },
  { key: '中餐·地方菜', label: '地方菜', en: 'Regional', color: 'mustard' },
  { key: '国际·亚洲', label: '亚洲', en: 'Asian', color: 'moss' },
  { key: '国际·西餐', label: '西餐', en: 'Western', color: 'mocha' },
  { key: '国际·其他', label: '其他', en: 'Other', color: 'mocha' },
];

export default function Home() {
  const [restaurants, setRestaurants] = useState<Restaurant[]>([]);
  const [cuisines, setCuisines] = useState<Cuisine[]>([]);
  const [restaurantCuisines, setRestaurantCuisines] = useState<{restaurant_id: number, cuisine_id: number}[]>([]);
  const [activeGroup, setActiveGroup] = useState('日料·细分品类');
  const [loading, setLoading] = useState(true);
  const { user, signOut } = useAuth();

  useEffect(() => {
    async function load() {
      const [{ data: rest }, { data: cuis }, { data: rc }] = await Promise.all([
        supabase.from('restaurants').select('*').eq('status', '推荐').order('score_total', { ascending: false }),
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

  const cuisinesByGroup = useMemo(() => {
    const map: Record<string, Cuisine[]> = {};
    for (const c of cuisines) {
      if (c.dimension !== '菜系') continue;
      const key = c.parent_category || '未分类';
      if (!map[key]) map[key] = [];
      map[key].push(c);
    }
    return map;
  }, [cuisines]);

  const getCuisineRestaurants = (cuisineName: string) => {
    return restaurants
      .filter(r => (restaurantCuisineMap[r.id] || []).includes(cuisineName))
      .slice(0, 2);
  };

  const topRestaurants = restaurants.slice(0, 6);

  const stats = useMemo(() => {
    let jp = 0, cn = 0;
    const jpCats = ['咖喱', '天妇罗', '寿司', '寿喜烧', '居酒屋', '怀石', '拉面', '日式甜品', '日料/日本料理', '炉端烧', '烧肉', '烧鸟', '铁板烧', '鳗鱼饭'];
    const cnCats = ['鲁菜', '川菜', '粤菜', '苏菜', '闽菜', '浙菜', '湘菜', '徽菜', '本帮菜', '京菜', '东北菜'];
    for (const r of restaurants) {
      const names = restaurantCuisineMap[r.id] || [];
      if (names.some(n => jpCats.some(j => n.includes(j)))) jp++;
      if (names.some(n => cnCats.some(c => n.includes(c)))) cn++;
    }
    return { total: restaurants.length, japanese: jp, chinese: cn };
  }, [restaurants, restaurantCuisineMap]);

  const activeGroupConfig = CUISINE_GROUPS.find(g => g.key === activeGroup);

  return (
    <div className="min-h-screen bg-cream-100">
      <Head>
        <title>China Travel · 上海美食地图</title>
        <meta name="description" content="上海美食地图 — 日料14类+中餐八大菜系，反软广真实评分，只认口味" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </Head>

      {/* ===== 顶部导航 ===== */}
      <header className="sticky top-0 z-50 bg-cream-100/80 backdrop-blur-md border-b border-line">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2.5">
            <span className="w-2.5 h-2.5 rounded-full bg-terracotta" />
            <span className="serif text-lg font-semibold tracking-tight">China Travel</span>
            <span className="kicker text-mocha-faint hidden sm:block ml-1">FOOD GUIDE</span>
          </Link>
          <nav className="flex items-center gap-7">
            <Link href="/restaurants" className="text-sm text-mocha-soft hover:text-terracotta transition">全部餐厅</Link>
            <Link href="/map" className="text-sm text-mocha-soft hover:text-moss transition">地图</Link>
            <div className="w-px h-4 bg-line" />
            {user ? (
              <div className="flex items-center gap-3">
                <span className="text-xs text-mocha-faint hidden md:block">{user.email}</span>
                <button onClick={() => signOut()} className="text-xs text-mocha-faint hover:text-terracotta transition">退出</button>
              </div>
            ) : (
              <Link href="/login" className="btn btn-primary !py-2 !px-5 !text-xs">登录</Link>
            )}
          </nav>
        </div>
      </header>

      {/* ===== Hero - 超大衬线标题 + 赤陶橙强调 ===== */}
      <section className="max-w-7xl mx-auto px-6 pt-20 pb-16">
        <div className="flex items-center gap-3 mb-8">
          <span className="w-10 h-px bg-terracotta" />
          <span className="kicker text-terracotta">VOL.01 — 上海 / SHANGHAI</span>
        </div>
        <h1 className="serif font-light leading-[0.95] tracking-tight mb-10" style={{ fontSize: 'clamp(3rem, 9vw, 7.5rem)' }}>
          上海
          <span className="italic text-terracotta">美食</span>
          <br />
          <span className="text-mocha-soft">地图</span>
        </h1>
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-10 mt-12">
          <div className="lg:col-span-5">
            <p className="text-mocha-soft text-base leading-relaxed">
              日料十四类细分 · 中餐八大菜系 · 反软广真实评分体系。
              只认口味，不看性价比与环境。每一家店都经过食客实测与多维度交叉验证。
            </p>
            <div className="flex gap-4 mt-8">
              <Link href="/restaurants" className="btn btn-primary">
                开始探索 →
              </Link>
              <Link href="/map" className="btn btn-outline">
                地图模式
              </Link>
            </div>
          </div>
          <div className="lg:col-span-7 flex items-end gap-12">
            <div>
              <div className="serif text-6xl font-light text-terracotta">{stats.total}</div>
              <div className="kicker text-mocha-faint mt-2">家餐厅</div>
            </div>
            <div>
              <div className="serif text-6xl font-light text-moss">{stats.japanese}</div>
              <div className="kicker text-mocha-faint mt-2">日料</div>
            </div>
            <div>
              <div className="serif text-6xl font-light text-mustard">{stats.chinese}</div>
              <div className="kicker text-mocha-faint mt-2">中餐</div>
            </div>
          </div>
        </div>
      </section>

      {/* ===== 菜系大类 - 胶囊导航 ===== */}
      <section className="max-w-7xl mx-auto px-6 pb-8">
        <div className="flex items-center gap-2 overflow-x-auto pb-2 -mx-1 px-1">
          {CUISINE_GROUPS.map((g) => {
            const count = cuisinesByGroup[g.key]?.length || 0;
            if (count === 0) return null;
            const isActive = activeGroup === g.key;
            return (
              <button
                key={g.key}
                onClick={() => setActiveGroup(g.key)}
                className={`flex items-center gap-2 px-5 py-2.5 rounded-full whitespace-nowrap transition-all flex-shrink-0 text-sm ${
                  isActive
                    ? `bg-${g.color} text-white shadow-soft`
                    : 'bg-white text-mocha-soft hover:bg-cream-200 border border-line'
                }`}
              >
                <span className={`w-1.5 h-1.5 rounded-full ${isActive ? 'bg-white/60' : `bg-cuisine-${g.color}`}`} />
                <span className="font-medium">{g.label}</span>
                <span className={`text-xs ${isActive ? 'text-white/60' : 'text-mocha-faint'}`}>{count}</span>
              </button>
            );
          })}
        </div>
      </section>

      {/* ===== 细分品类 - Bento Grid ===== */}
      <section className="max-w-7xl mx-auto px-6 py-10">
        <div className="flex items-end justify-between mb-8">
          <div>
            <div className="kicker text-mocha-faint mb-2">CATEGORY / 分类</div>
            <h2 className="serif text-3xl font-light">
              {activeGroupConfig?.label}
              <span className="text-mocha-faint text-xl ml-3 italic font-light">{activeGroupConfig?.en}</span>
            </h2>
          </div>
        </div>

        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {[...Array(6)].map((_, i) => (
              <div key={i} className="skeleton h-44" />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {(cuisinesByGroup[activeGroup] || []).map((c, idx) => {
              const reps = getCuisineRestaurants(c.name);
              // Bento 大小变化：每第1、4个大一点
              const isLarge = idx % 4 === 0;
              return (
                <Link
                  key={c.id}
                  href={`/restaurants?cuisine=${encodeURIComponent(c.name)}`}
                  className={`bento-item bg-white p-6 flex flex-col ${isLarge ? 'md:col-span-2 lg:col-span-1' : ''}`}
                >
                  <div className="flex items-start justify-between mb-4">
                    <h3 className="serif text-xl font-medium">{c.name}</h3>
                    {c.price_low && c.price_high && (
                      <span className="kicker text-mocha-faint">¥{c.price_low}–{c.price_high}</span>
                    )}
                  </div>
                  {c.flavor_profile && (
                    <p className="text-xs text-mocha-faint italic mb-4">{c.flavor_profile}</p>
                  )}
                  <div className="mt-auto space-y-2 pt-4 border-t border-line">
                    {reps.length > 0 ? reps.map((r, i) => (
                      <div key={i} className="flex items-center justify-between text-sm">
                        <span className="text-mocha-soft truncate flex-1">{r.name}</span>
                        <span className="text-mocha-faint ml-2 flex-shrink-0 text-xs">¥{r.price_avg || '—'}</span>
                      </div>
                    )) : (
                      <p className="text-xs text-mocha-faint italic">暂无收录</p>
                    )}
                  </div>
                </Link>
              );
            })}
          </div>
        )}
      </section>

      {/* ===== 高分推荐 - 卡片式 ===== */}
      <section className="bg-white border-y border-line">
        <div className="max-w-7xl mx-auto px-6 py-16">
          <div className="flex items-end justify-between mb-10">
            <div>
              <div className="kicker text-terracotta mb-2">EDITOR'S PICK / 编辑推荐</div>
              <h2 className="serif text-3xl font-light">高分推荐</h2>
            </div>
            <Link href="/restaurants" className="text-sm text-moss hover:text-terracotta link-underline">查看全部 →</Link>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {topRestaurants.map((r, idx) => {
              const cuisineNames = restaurantCuisineMap[r.id] || [];
              return (
                <Link
                  key={r.id}
                  href={`/restaurants/${r.id}`}
                  className="card p-6 flex flex-col group"
                >
                  <div className="flex items-start justify-between mb-4">
                    <span className="numeral text-4xl text-terracotta/30 font-light">
                      {String(idx + 1).padStart(2, '0')}
                    </span>
                    {r.score_total && (
                      <div className="text-right">
                        <span className="serif text-2xl font-medium text-moss">{r.score_total.toFixed(1)}</span>
                        <div className="kicker text-mocha-faint">评分</div>
                      </div>
                    )}
                  </div>
                  <h3 className="serif text-xl font-medium mb-2 group-hover:text-terracotta transition">{r.name}</h3>
                  <div className="flex items-center gap-2 mb-4">
                    {cuisineNames.slice(0, 2).map((cn, i) => (
                      <span key={i} className={`tag tag-${cn.includes('日') || ['咖喱','寿司','拉面','烧鸟','烧肉','天妇罗','居酒屋','怀石','炉端烧','铁板烧','鳗鱼饭','寿喜烧','日式甜品'].some(c => cn.includes(c)) ? 'japanese' : 'chinese'}`}>{cn}</span>
                    ))}
                  </div>
                  {r.signature_dishes && Array.isArray(r.signature_dishes) && r.signature_dishes.length > 0 && (
                    <p className="text-sm text-mocha-soft mb-4 line-clamp-2">{r.signature_dishes.slice(0, 3).join(' · ')}</p>
                  )}
                  <div className="mt-auto flex items-center justify-between pt-4 border-t border-line">
                    <span className="text-xs text-mocha-faint">{r.district || '—'}</span>
                    <span className="serif text-lg font-medium text-terracotta">¥{r.price_avg || '—'}</span>
                  </div>
                </Link>
              );
            })}
          </div>
        </div>
      </section>

      {/* ===== 评分体系 - 简洁说明 ===== */}
      <section className="max-w-7xl mx-auto px-6 py-20">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-12">
          <div className="lg:col-span-4">
            <div className="kicker text-mocha-faint mb-3">METHODOLOGY / 方法论</div>
            <h2 className="serif text-3xl font-light mb-6">反软广<br />评分体系</h2>
            <p className="text-mocha-soft text-sm leading-relaxed mb-6">
              拒绝平台标注人均与媒体榜单。每一家店的评分都来自客观数据、食客实测、口味权重与行业背书的综合计算，并对软广嫌疑进行扣分。
            </p>
            <Link href="/restaurants" className="btn btn-outline !text-xs">查看完整榜单</Link>
          </div>
          <div className="lg:col-span-8">
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
              {[
                { label: '客观评分', weight: '40', desc: '平台分×可信度', color: 'bg-terracotta text-white' },
                { label: '食客实测', weight: '30', desc: '只计堂食点评', color: 'bg-moss text-white' },
                { label: '口味权重', weight: '20', desc: '食材/技法/呈现', color: 'bg-mustard text-mocha' },
                { label: '行业背书', weight: '10', desc: '名厨/老店/传承', color: 'bg-cream-200 text-mocha' },
                { label: '软广扣分', weight: '−30', desc: '营销痕迹/水军', color: 'bg-mocha text-terracotta-soft' },
              ].map((item, i) => (
                <div key={i} className={`${item.color} rounded-2xl p-5`}>
                  <div className="serif text-3xl font-light mb-2">{item.weight}<span className="text-sm opacity-60">%</span></div>
                  <div className="text-xs font-medium mb-1">{item.label}</div>
                  <div className="text-xs opacity-60">{item.desc}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ===== 页脚 ===== */}
      <footer className="border-t border-line bg-cream-200/50">
        <div className="max-w-7xl mx-auto px-6 py-10">
          <div className="flex flex-col md:flex-row items-center justify-between gap-4">
            <div className="flex items-center gap-2.5">
              <span className="w-2.5 h-2.5 rounded-full bg-terracotta" />
              <span className="serif text-base font-semibold">China Travel</span>
              <span className="kicker text-mocha-faint">FOOD GUIDE</span>
            </div>
            <p className="text-xs text-mocha-faint">
              数据来源：飞书表格 + 食客实测 · 反软广评分体系 · 仅作参考，以实际到店为准
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}
