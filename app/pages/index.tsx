import Head from 'next/head';
import Link from 'next/link';
import { useEffect, useState, useMemo } from 'react';
import { supabase, Restaurant, Cuisine } from '@/lib/supabase';
import { useAuth } from '@/lib/auth';

// 一级根（地图认知顺序）
const ROOTS = ['中餐', '亚洲', '欧洲', '非洲', '北美洲', '南美洲', '融合菜', '非正餐'];
const ROOT_EN: Record<string, string> = {
  中餐: 'Chinese', 亚洲: 'Asian', 欧洲: 'Europe', 非洲: 'Africa',
  北美洲: 'N. America', 南美洲: 'S. America', 融合菜: 'Fusion', 非正餐: 'Café & Bar',
};

async function fetchAll<T = any>(table: string, select: string, extra?: [string, any], orderBy = 'id'): Promise<T[]> {
  const step = 1000;
  let start = 0;
  let all: T[] = [];
  for (;;) {
    let q = supabase.from(table).select(select).order(orderBy).range(start, start + step - 1);
    if (extra) q = q.eq(extra[0], extra[1]);
    const { data, error } = await q;
    if (error) throw error;
    if (!data || data.length === 0) break;
    all = all.concat(data as T[]);
    if (data.length < step) break;
    start += step;
  }
  return all;
}

export default function Home() {
  const [restaurants, setRestaurants] = useState<Restaurant[]>([]);
  const [cuisines, setCuisines] = useState<Cuisine[]>([]);
  const [rc, setRc] = useState<{ restaurant_id: number; cuisine_id: number }[]>([]);
  const [activeRoot, setActiveRoot] = useState('中餐');
  const [loading, setLoading] = useState(true);
  const { user, signOut } = useAuth();

  useEffect(() => {
    (async () => {
      const [rest, cuis, links] = await Promise.all([
        fetchAll<Restaurant>('restaurants', '*', ['status', 'active']),
        fetchAll<Cuisine>('cuisines', '*'),
        fetchAll<{ restaurant_id: number; cuisine_id: number }>('restaurant_cuisines', 'restaurant_id,cuisine_id', undefined, 'restaurant_id'),
      ]);
      setRestaurants(rest);
      setCuisines(cuis);
      setRc(links);
      setLoading(false);
    })();
  }, []);

  const id2cuisine = useMemo(() => {
    const m: Record<number, Cuisine> = {};
    cuisines.forEach((c) => { m[c.id] = c; });
    return m;
  }, [cuisines]);

  const rTags = useMemo(() => {
    const m: Record<number, Set<number>> = {};
    rc.forEach((x) => {
      if (!m[x.restaurant_id]) m[x.restaurant_id] = new Set();
      m[x.restaurant_id].add(x.cuisine_id);
    });
    return m;
  }, [rc]);

  // 递归收集菜系子孙 id
  const subtreeIds = (name: string): Set<number> => {
    const ids = new Set<number>();
    const visit = (nm: string) => {
      cuisines.filter((c) => c.dimension === '菜系' && (c.name === nm || c.parent_category === nm))
        .forEach((o) => { if (!ids.has(o.id)) { ids.add(o.id); visit(o.name); } });
    };
    visit(name);
    return ids;
  };
  const subtreeCount = (name: string) => {
    const ids = subtreeIds(name);
    const rs = new Set<number>();
    rc.forEach((x) => { if (ids.has(x.cuisine_id)) rs.add(x.restaurant_id); });
    // 只计在营
    return restaurants.filter((r) => rs.has(r.id)).length;
  };

  const rCuisineNames = (rid: number) =>
    Array.from(rTags[rid] || [])
      .map((cid) => id2cuisine[cid])
      .filter((c) => c && c.dimension === '菜系')
      .map((c) => c!.name);

  const rootChildren = useMemo(
    () => cuisines.filter((c) => c.dimension === '菜系' && c.parent_category === activeRoot),
    [cuisines, activeRoot]
  );

  const getCuisineRestaurants = (cuisineName: string) => {
    const cid = cuisines.find((c) => c.name === cuisineName && c.dimension === '菜系')?.id;
    if (!cid) return [];
    return restaurants
      .filter((r) => rTags[r.id]?.has(cid))
      .sort((a, b) => (b.score_total || 0) - (a.score_total || 0))
      .slice(0, 2);
  };

  const topRestaurants = useMemo(
    () => [...restaurants].sort((a, b) => (b.score_total || 0) - (a.score_total || 0)).slice(0, 6),
    [restaurants]
  );

  return (
    <div className="min-h-screen bg-cream-100">
      <Head>
        <title>China Travel · 上海美食地图</title>
        <meta name="description" content="上海美食地图 — 中餐八大菜系·各国料理·咖啡酒吧，反软广真实评分，只认口味" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </Head>

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
              中餐八大菜系 · 各国大陆料理 · 咖啡面包甜品酒吧。
              只认口味，不看性价比与环境。每一家都源自食客堂食实测与多维度交叉验证，主动剔除软广与预制菜。
            </p>
            <div className="flex gap-4 mt-8">
              <Link href="/restaurants" className="btn btn-primary">开始探索 →</Link>
              <Link href="/map" className="btn btn-outline">地图模式</Link>
            </div>
          </div>
          <div className="lg:col-span-7 flex items-end gap-10 flex-wrap">
            <div>
              <div className="serif text-6xl font-light text-terracotta">{restaurants.length}</div>
              <div className="kicker text-mocha-faint mt-2">家餐厅</div>
            </div>
            <div>
              <div className="serif text-6xl font-light text-mustard">{subtreeCount('中餐')}</div>
              <div className="kicker text-mocha-faint mt-2">中餐</div>
            </div>
            <div>
              <div className="serif text-6xl font-light text-moss">{subtreeCount('日料/日本料理')}</div>
              <div className="kicker text-mocha-faint mt-2">日料</div>
            </div>
            <div>
              <div className="serif text-6xl font-light text-mocha">{subtreeCount('非正餐')}</div>
              <div className="kicker text-mocha-faint mt-2">咖啡酒吧</div>
            </div>
          </div>
        </div>
      </section>

      {/* 根胶囊导航 */}
      <section className="max-w-7xl mx-auto px-6 pb-8">
        <div className="flex items-center gap-2 overflow-x-auto pb-2 -mx-1 px-1">
          {ROOTS.map((rname) => {
            const isActive = activeRoot === rname;
            return (
              <button key={rname} onClick={() => setActiveRoot(rname)}
                className={`flex items-center gap-2 px-5 py-2.5 rounded-full whitespace-nowrap transition-all flex-shrink-0 text-sm ${
                  isActive ? 'bg-terracotta text-white shadow-soft' : 'bg-white text-mocha-soft hover:bg-cream-200 border border-line'
                }`}>
                <span className={`w-1.5 h-1.5 rounded-full ${isActive ? 'bg-white/60' : 'bg-terracotta'}`} />
                <span className="font-medium">{rname}</span>
                <span className={`text-xs ${isActive ? 'text-white/60' : 'text-mocha-faint'}`}>{subtreeCount(rname)}</span>
              </button>
            );
          })}
        </div>
      </section>

      <section className="max-w-7xl mx-auto px-6 py-10">
        <div className="flex items-end justify-between mb-8">
          <div>
            <div className="kicker text-mocha-faint mb-2">CATEGORY / 分类</div>
            <h2 className="serif text-3xl font-light">
              {activeRoot}<span className="text-mocha-faint text-xl ml-3 italic font-light">{ROOT_EN[activeRoot]}</span>
            </h2>
          </div>
          <Link href={`/restaurants`} className="text-sm text-mocha-faint hover:text-terracotta">查看全部 →</Link>
        </div>

        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {[...Array(6)].map((_, i) => <div key={i} className="skeleton h-44" />)}
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {rootChildren.map((c, idx) => {
              const reps = getCuisineRestaurants(c.name);
              const isLarge = idx % 4 === 0;
              return (
                <Link key={c.id} href={`/restaurants?cuisine=${encodeURIComponent(c.name)}`}
                  className={`bento-item bg-white p-6 flex flex-col ${isLarge ? 'md:col-span-2 lg:col-span-1' : ''}`}>
                  <div className="flex items-start justify-between mb-4">
                    <h3 className="serif text-xl font-medium">{c.name}</h3>
                    {c.price_low && c.price_high && (
                      <span className="kicker text-mocha-faint">¥{c.price_low}–{c.price_high}</span>
                    )}
                  </div>
                  {c.flavor_profile && <p className="text-xs text-mocha-faint italic mb-4">{c.flavor_profile}</p>}
                  <div className="mt-auto space-y-2 pt-4 border-t border-line">
                    {reps.length > 0 ? reps.map((r, i) => (
                      <div key={i} className="flex items-center justify-between text-sm">
                        <span className="text-mocha-soft truncate flex-1">{r.name}</span>
                        <span className="text-mocha-faint ml-2 flex-shrink-0 text-xs">¥{r.price_avg || '—'}</span>
                      </div>
                    )) : <p className="text-xs text-mocha-faint italic">暂无收录</p>}
                  </div>
                </Link>
              );
            })}
          </div>
        )}
      </section>

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
              const names = rCuisineNames(r.id);
              return (
                <Link key={r.id} href={`/restaurants/${r.id}`} className="card p-6 flex flex-col group">
                  <div className="flex items-start justify-between mb-4">
                    <span className="numeral text-4xl text-terracotta/30 font-light">{String(idx + 1).padStart(2, '0')}</span>
                    {r.score_total && (
                      <div className="text-right">
                        <span className="serif text-2xl font-medium text-moss">{r.score_total.toFixed(1)}</span>
                        <div className="kicker text-mocha-faint">评分</div>
                      </div>
                    )}
                  </div>
                  <h3 className="serif text-xl font-medium mb-2 group-hover:text-terracotta transition">{r.name}</h3>
                  <div className="flex items-center gap-2 mb-4 flex-wrap">
                    {names.slice(0, 2).map((cn, i) => (
                      <span key={i} className="tag tag-value">{cn}</span>
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

      <section className="max-w-7xl mx-auto px-6 py-20">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-12">
          <div className="lg:col-span-4">
            <div className="kicker text-mocha-faint mb-3">METHODOLOGY / 方法论</div>
            <h2 className="serif text-3xl font-light mb-6">反软广<br />评分体系</h2>
            <p className="text-mocha-soft text-sm leading-relaxed mb-6">
              拒绝平台标注人均与媒体榜单。评分来自客观数据、食客堂食实测、口味权重与行业背书，并对软广嫌疑扣分；预制菜、连锁工业化店标注但不进精选。
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
