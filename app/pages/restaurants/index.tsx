import Head from 'next/head';
import Link from 'next/link';
import { useEffect, useState, useMemo, useCallback } from 'react';
import { useRouter } from 'next/router';
import { supabase, Restaurant, Cuisine } from '@/lib/supabase';

// 五档价位（上海口径，按人均自动归档）
const TIERS = [
  { key: '经济', range: '< ¥50' },
  { key: '平价', range: '¥50–99' },
  { key: '中档', range: '¥100–199' },
  { key: '高档', range: '¥200–499' },
  { key: '奢华', range: '¥500+' },
];

// 一级根：地图认知顺序（中餐独立；其余按大陆→国家；非正餐为场景；融合菜单列）
const ROOTS = ['中餐', '亚洲', '欧洲', '非洲', '北美洲', '南美洲', '融合菜', '非正餐'];
const PAGE = 120;

const tierClass = (t?: string) =>
  ({ 经济: 'tag-budget', 平价: 'tag-value', 中档: 'tag-mid', 高档: 'tag-fine', 奢华: 'tag-luxury' } as Record<string, string>)[t || ''] ||
  'tag-budget';

// 分页拉全（关联表已超 1000 行，必须分页，否则筛选漏店）
async function fetchAll<T = any>(table: string, select: string, orderCol: string): Promise<T[]> {
  const step = 1000;
  let start = 0;
  let all: T[] = [];
  for (;;) {
    const { data, error } = await supabase
      .from(table)
      .select(select)
      .order(orderCol)
      .range(start, start + step - 1);
    if (error) throw error;
    if (!data || data.length === 0) break;
    all = all.concat(data as T[]);
    if (data.length < step) break;
    start += step;
  }
  return all;
}

export default function RestaurantsPage() {
  const router = useRouter();
  const [restaurants, setRestaurants] = useState<Restaurant[]>([]);
  const [cuisines, setCuisines] = useState<Cuisine[]>([]);
  const [rc, setRc] = useState<{ restaurant_id: number; cuisine_id: number }[]>([]);
  const [loading, setLoading] = useState(true);

  const [search, setSearch] = useState('');
  const [sortBy, setSortBy] = useState<'score' | 'price_asc' | 'price_desc'>('score');
  const [root, setRoot] = useState('中餐');          // 一级根 Tab
  const [flavor, setFlavor] = useState<string | null>(null); // 选中的菜系 name（叶子或中间层）
  const [tiers, setTiers] = useState<Set<string>>(new Set());
  const [district, setDistrict] = useState<string | null>(null);
  const [location, setLocation] = useState<string | null>(null);
  const [tagSel, setTagSel] = useState<Set<number>>(new Set()); // 业态/认证/标签/食材 多选
  const [showFilters, setShowFilters] = useState(false);
  const [shown, setShown] = useState(PAGE);

  useEffect(() => {
    (async () => {
      const [rest, cuis, links] = await Promise.all([
        fetchAll<Restaurant>('restaurants', '*', 'id'),
        fetchAll<Cuisine>('cuisines', '*', 'id'),
        fetchAll<{ restaurant_id: number; cuisine_id: number }>('restaurant_cuisines', 'restaurant_id,cuisine_id', 'restaurant_id'),
      ]);
      setRestaurants(rest);
      setCuisines(cuis);
      setRc(links);
      setLoading(false);
    })();
  }, []);

  // ---- 树索引 ----
  const childrenOf = useCallback(
    (parent: string) => cuisines.filter((c) => c.dimension === '菜系' && c.parent_category === parent),
    [cuisines]
  );

  // URL ?cuisine= 自动定位
  useEffect(() => {
    if (router.query.cuisine && cuisines.length) {
      const name = decodeURIComponent(router.query.cuisine as string);
      const c = cuisines.find((x) => x.name === name && x.dimension === '菜系');
      if (c) {
        setFlavor(name);
        setRoot(topLevel(c, cuisines));
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router.query, cuisines]);

  // ---- 派生索引 ----
  const tagCount = useMemo(() => {
    const m: Record<number, number> = {};
    rc.forEach((x) => { m[x.cuisine_id] = (m[x.cuisine_id] || 0) + 1; });
    return m;
  }, [rc]);

  const rTagIds = useMemo(() => {
    const m: Record<number, Set<number>> = {};
    rc.forEach((x) => {
      if (!m[x.restaurant_id]) m[x.restaurant_id] = new Set();
      m[x.restaurant_id].add(x.cuisine_id);
    });
    return m;
  }, [rc]);

  const rCuisineNames = useMemo(() => {
    const id2name: Record<number, string> = {};
    cuisines.forEach((c) => { id2name[c.id] = c.name; });
    const m: Record<number, string[]> = {};
    rc.forEach((x) => {
      const c = cuisines.find((z) => z.id === x.cuisine_id);
      if (c && c.dimension === '菜系') {
        if (!m[x.restaurant_id]) m[x.restaurant_id] = [];
        if (!m[x.restaurant_id].includes(c.name)) m[x.restaurant_id].push(c.name);
      }
    });
    return m;
  }, [rc, cuisines]);

  const byDim = useCallback((dim: string) => cuisines.filter((c) => c.dimension === dim), [cuisines]);

  // 递归收集菜系子孙 id
  const collectFlavorIds = useCallback((name: string): Set<number> => {
    const ids = new Set<number>();
    const visit = (nm: string) => {
      cuisines
        .filter((c) => c.dimension === '菜系' && (c.name === nm || c.parent_category === nm))
        .forEach((obj) => {
          if (!ids.has(obj.id)) {
            ids.add(obj.id);
            visit(obj.name);
          }
        });
    };
    visit(name);
    return ids;
  }, [cuisines]);

  // 选中某菜系：同步根 Tab + 地址栏；再次点同一标签则取消
  const selectFlavor = useCallback((name: string) => {
    const c = cuisines.find((x) => x.name === name && x.dimension === '菜系');
    const next = flavor === name ? null : name;
    setFlavor(next);
    if (c) setRoot(topLevel(c, cuisines));
    if (next) router.replace(`/restaurants?cuisine=${encodeURIComponent(next)}`, undefined, { shallow: true });
    else router.replace('/restaurants', undefined, { shallow: true });
  }, [cuisines, flavor, router]);

  // 切换一级根：立即按该根筛选（虚拟根同样可由 collectFlavorIds 收集子孙）
  const selectRoot = useCallback((rname: string) => {
    setRoot(rname);
    setFlavor(rname);
    router.replace(`/restaurants?cuisine=${encodeURIComponent(rname)}`, undefined, { shallow: true });
  }, [router]);

  // 关店店 id
  const closedIds = useMemo(
    () => new Set(restaurants.filter((r) => r.status === 'closed' || r.status === '关店').map((r) => r.id)),
    [restaurants]
  );

  // 某菜系（含全部子孙）关联的【在营】餐厅去重数
  const subtreeCount = useCallback((name: string): number => {
    const ids = collectFlavorIds(name);
    const rs = new Set<number>();
    rc.forEach((x) => { if (ids.has(x.cuisine_id) && !closedIds.has(x.restaurant_id)) rs.add(x.restaurant_id); });
    return rs.size;
  }, [collectFlavorIds, rc, closedIds]);

  // 当前根的二级菜系（按店数排序）
  const rootChildren = useMemo(
    () => childrenOf(root).sort((a, b) => subtreeCount(b.name) - subtreeCount(a.name)),
    [childrenOf, root, subtreeCount]
  );

  // 选中菜系的三级子流派（flavor 为虚拟根时不展开，避免与二级重复）
  const flavorChildren = useMemo(() => {
    if (!flavor || ROOTS.includes(flavor)) return [];
    return childrenOf(flavor).sort((a, b) => subtreeCount(b.name) - subtreeCount(a.name));
  }, [flavor, childrenOf, subtreeCount]);

  // 行政区 / 商圈
  const districts = useMemo(() => {
    const s = new Set<string>();
    restaurants.forEach((r) => { if (r.district && r.district !== '待确认' && r.district !== '多区连锁') s.add(r.district); });
    const main = Array.from(s).sort((a, b) => a.localeCompare(b, 'zh'));
    ['多区连锁', '待确认'].forEach((x) => { if (restaurants.some((r) => r.district === x)) main.push(x); });
    return main;
  }, [restaurants]);
  const locations = useMemo(() => {
    const m: Record<string, number> = {};
    restaurants.forEach((r) => {
      if (district && r.district === district && r.business_area) m[r.business_area] = (m[r.business_area] || 0) + 1;
    });
    return Object.entries(m).sort((a, b) => b[1] - a[1]).map((x) => x[0]);
  }, [restaurants, district]);

  // 形式标签（有店的，按店数排序）
  const formatTags = useMemo(
    () => byDim('形式').filter((c) => (tagCount[c.id] || 0) > 0)
      .sort((a, b) => tagCount[b.id] - tagCount[a.id]),
    [byDim, tagCount]
  );
  const awardTags = useMemo(() => byDim('认证'), [byDim]);
  const specialTags = useMemo(() => byDim('标签'), [byDim]);
  // 常驻亮点快捷标签
  const quickTags = useMemo(
    () => [159, 160, 323, 45, 46].map((id) => cuisines.find((c) => c.id === id)).filter(Boolean) as Cuisine[],
    [cuisines]
  );
  const ingredientTags = useMemo(() => {
    const seen = new Set<string>();
    return byDim('食材').filter((c) => {
      if (seen.has(c.name) || (tagCount[c.id] || 0) === 0) return false;
      seen.add(c.name); return true;
    }).sort((a, b) => (tagCount[b.id] || 0) - (tagCount[a.id] || 0));
  }, [byDim, tagCount]);

  // 选中 tag 按维度分组（同组 OR，跨组 AND）
  const tagGroups = useMemo(() => {
    const g: Record<string, Set<number>> = {};
    tagSel.forEach((id) => {
      const c = cuisines.find((z) => z.id === id);
      if (!c) return;
      if (!g[c.dimension]) g[c.dimension] = new Set();
      g[c.dimension].add(id);
    });
    return g;
  }, [tagSel, cuisines]);

  const activeFilterCount =
    tiers.size + (district ? 1 : 0) + (location ? 1 : 0) + tagSel.size + (flavor ? 1 : 0) + (search ? 1 : 0);

  // ---- 筛选 ----
  const filtered = useMemo(() => {
    let result = [...restaurants];
    result = result.filter((r) => r.status !== 'closed' && r.status !== '关店');
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      result = result.filter((r) =>
        r.name.toLowerCase().includes(q) ||
        (r.address || '').toLowerCase().includes(q) ||
        (r.business_area || '').toLowerCase().includes(q) ||
        (Array.isArray(r.signature_dishes) && r.signature_dishes.some((d) => d.toLowerCase().includes(q)))
      );
    }
    if (flavor) {
      const ids = collectFlavorIds(flavor);
      result = result.filter((r) => rTagIds[r.id] && Array.from(ids).some((id) => rTagIds[r.id].has(id)));
    }
    if (tiers.size) result = result.filter((r) => r.tier && tiers.has(r.tier));
    if (district) result = result.filter((r) => r.district === district);
    if (location) result = result.filter((r) => r.business_area === location);
    Object.values(tagGroups).forEach((group) => {
      result = result.filter((r) => rTagIds[r.id] && Array.from(group).some((id) => rTagIds[r.id].has(id)));
    });
    if (sortBy === 'score') result.sort((a, b) => (b.score_total || 0) - (a.score_total || 0));
    else if (sortBy === 'price_asc') result.sort((a, b) => (a.price_avg || 9999) - (b.price_avg || 9999));
    else result.sort((a, b) => (b.price_avg || 0) - (a.price_avg || 0));
    return result;
  }, [restaurants, search, flavor, tiers, district, location, tagGroups, sortBy, rTagIds, collectFlavorIds]);

  useEffect(() => { setShown(PAGE); }, [search, flavor, tiers, district, location, tagSel, sortBy]);

  const toggleTier = (k: string) => setTiers((prev) => {
    const n = new Set(prev);
    if (n.has(k)) n.delete(k); else n.add(k);
    return n;
  });
  const toggleTag = (id: number) => setTagSel((prev) => {
    const n = new Set(prev);
    if (n.has(id)) n.delete(id); else n.add(id);
    return n;
  });
  const tagName = (id: number) => cuisines.find((c) => c.id === id)?.name || '';

  const clearAll = () => {
    setSearch(''); setFlavor(null); setTiers(new Set()); setDistrict(null);
    setLocation(null); setTagSel(new Set());
    router.replace('/restaurants', undefined, { shallow: true });
  };

  const renderFlavorTag = (c: Cuisine) => {
    const n = subtreeCount(c.name);
    const active = flavor === c.name;
    const empty = n === 0;
    return (
      <button
        key={c.id}
        disabled={empty}
        onClick={() => !empty && selectFlavor(c.name)}
        className={`px-3 py-1.5 rounded-full text-xs whitespace-nowrap transition-all border ${
          active
            ? 'bg-terracotta text-white border-terracotta'
            : empty
            ? 'bg-white text-mocha-faint border-line opacity-40 cursor-not-allowed'
            : 'bg-white text-mocha-soft border-line hover:border-terracotta-soft hover:text-terracotta'
        }`}
      >
        {c.name}
        {n > 0 && <span className={`ml-1 text-2xs ${active ? 'text-white/70' : 'text-mocha-faint'}`}>{n}</span>}
      </button>
    );
  };

  const renderFlag = (c: Cuisine) => {
    const on = tagSel.has(c.id);
    return (
      <button key={c.id} className="flag" data-on={on} onClick={() => toggleTag(c.id)}>
        {c.name}<span className="n">{tagCount[c.id] || 0}</span>
      </button>
    );
  };

  if (loading) return (
    <div className="min-h-screen bg-cream-50 flex items-center justify-center"><div className="spinner" /></div>
  );

  return (
    <div className="min-h-screen bg-cream-50">
      <Head><title>全部餐厅 · China Travel</title></Head>

      <header className="border-b border-line sticky top-0 z-50 bg-cream-50/90 backdrop-blur-sm">
        <div className="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2 text-mocha hover:text-terracotta transition">
            <span>←</span><span className="serif text-base font-medium">首页</span>
          </Link>
          <div className="flex items-center gap-4">
            <span className="kicker text-mocha-faint">{filtered.length} 家餐厅</span>
            <Link href="/map" className="kicker text-mocha-soft hover:text-mocha transition">地图</Link>
          </div>
        </div>
      </header>

      <div className="max-w-6xl mx-auto px-6 py-6">
        {/* 搜索 + 排序 + 筛选 */}
        <div className="flex flex-wrap items-center gap-3 mb-4">
          <div className="relative flex-1 min-w-[220px]">
            <input
              type="text" value={search} onChange={(e) => setSearch(e.target.value)}
              placeholder="搜索店名、商圈、地址、招牌菜…"
              className="w-full py-2 bg-transparent border-b border-line text-sm focus:outline-none placeholder:text-mocha-faint focus:border-terracotta"
            />
            {search && (
              <button onClick={() => setSearch('')} className="absolute right-0 top-1/2 -translate-y-1/2 text-mocha-faint hover:text-mocha text-sm">✕</button>
            )}
          </div>
          <button className="filter-trigger" data-on={showFilters || activeFilterCount - (flavor ? 1 : 0) - (search ? 1 : 0) > 0}
            onClick={() => setShowFilters((v) => !v)}>
            <span>筛选</span>
            {tiers.size + (district ? 1 : 0) + (location ? 1 : 0) + tagSel.size > 0 && (
              <span className="badge">{tiers.size + (district ? 1 : 0) + (location ? 1 : 0) + tagSel.size}</span>
            )}
            <span className="text-2xs">{showFilters ? '▲' : '▼'}</span>
          </button>
          <select value={sortBy} onChange={(e) => setSortBy(e.target.value as any)}
            className="px-2 py-2 bg-transparent border-b border-line text-xs outline-none cursor-pointer text-mocha-soft">
            <option value="score">评分最高</option>
            <option value="price_asc">人均从低到高</option>
            <option value="price_desc">人均从高到低</option>
          </select>
        </div>

        {/* 价位条 */}
        <div className="flex items-center gap-2 mb-4 flex-wrap">
          <span className="kicker text-mocha-faint mr-1">价位</span>
          {TIERS.map((t) => {
            const on = tiers.has(t.key);
            return (
              <button key={t.key} className="price-chip px-3.5 py-1.5 rounded-full text-xs border transition-all whitespace-nowrap"
                data-active={on} data-tier={t.key}
                style={on ? {} : { background: '#fff', borderColor: '#E0D5C8', color: '#5C4A3E' }}
                onClick={() => toggleTier(t.key)}>
                {t.key}<span className={`ml-1 text-2xs ${on ? 'opacity-70' : 'text-mocha-faint'}`}>{t.range}</span>
              </button>
            );
          })}
        </div>

        {/* 亮点快捷筛选 */}
        <div className="flex items-center gap-2 mb-4 flex-wrap">
          <span className="kicker text-mocha-faint mr-1">亮点</span>
          {quickTags.map((c) => {
            const on = tagSel.has(c.id);
            return (
              <button key={c.id} onClick={() => toggleTag(c.id)}
                className={`px-3.5 py-1.5 rounded-full text-xs border transition-all whitespace-nowrap ${
                  on ? 'bg-mocha text-cream-50 border-mocha' : 'bg-white border-line text-mocha-soft hover:border-terracotta hover:text-terracotta'
                }`}>
                {c.name}<span className={`ml-1 text-2xs ${on ? 'text-cream-50/70' : 'text-mocha-faint'}`}>{tagCount[c.id] || 0}</span>
              </button>
            );
          })}
        </div>

        {/* 菜系树主导航 */}
        <div className="bg-white border border-line rounded-2xl p-4 mb-4 space-y-3 shadow-soft">
          {/* 一级根 Tab */}
          <div className="flex gap-1 border-b border-line pb-2 flex-wrap">
            {ROOTS.map((rname) => {
              const active = root === rname;
              return (
                <button key={rname} onClick={() => selectRoot(rname)}
                  className={`px-3.5 py-1.5 text-sm transition ${
                    active ? 'text-terracotta font-medium border-b-2 border-terracotta -mb-[9px]' : 'text-mocha-faint hover:text-mocha'
                  }`}>
                  {rname}<span className={`ml-1 text-2xs ${active ? 'text-terracotta/70' : 'text-mocha-faint/70'}`}>{subtreeCount(rname)}</span>
                </button>
              );
            })}
          </div>

          {/* 二级菜系 */}
          <div className="flex flex-wrap gap-1.5">
            {rootChildren.length ? rootChildren.map(renderFlavorTag) : (
              <span className="text-xs text-mocha-faint py-1">该分类正在补充中</span>
            )}
          </div>

          {/* 三级子流派 */}
          {flavorChildren.length > 0 && (
            <div className="flex items-start gap-3 flex-wrap pt-3 border-t border-dashed border-line">
              <span className="kicker text-mocha-faint shrink-0 pt-1.5">{flavor}</span>
              <div className="flex flex-wrap gap-1.5 flex-1">
                <button onClick={() => selectFlavor(flavor!)}
                  className="px-2.5 py-1 text-xs rounded-full bg-terracotta/10 text-terracotta border border-terracotta/30">
                  全部{flavor}
                </button>
                {flavorChildren.map((c) => (
                  <button key={c.id} onClick={() => selectFlavor(c.name)}
                    className={`px-2.5 py-1 text-xs rounded-full transition ${
                      flavor === c.name ? 'bg-terracotta text-white' : 'bg-cream-100 text-mocha-soft hover:text-terracotta'
                    }`}>
                    {c.name}{subtreeCount(c.name) > 0 && <span className="ml-1 text-2xs text-mocha-faint">{subtreeCount(c.name)}</span>}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* 筛选抽屉 */}
        {showFilters && (
          <div className="filter-panel bg-white border border-line rounded-2xl p-5 mb-4 space-y-4 shadow-card">
            <div className="space-y-2">
              <span className="kicker text-mocha-faint">位置 · 行政区</span>
              <div className="flex flex-wrap gap-1.5">
                <button className="flag" data-on={!district} onClick={() => { setDistrict(null); setLocation(null); }}>全部</button>
                {districts.map((d) => (
                  <button key={d} className="flag" data-on={district === d} onClick={() => { setDistrict(d === district ? null : d); setLocation(null); }}>{d}</button>
                ))}
              </div>
              {district && locations.length > 0 && (
                <>
                  <span className="kicker text-mocha-faint block pt-1">商圈 · {district}</span>
                  <div className="flex flex-wrap gap-1.5">
                    <button className="flag" data-on={!location} onClick={() => setLocation(null)}>全部商圈</button>
                    {locations.map((l) => (
                      <button key={l} className="flag" data-on={location === l} onClick={() => setLocation(l === location ? null : l)}>
                        {l}
                      </button>
                    ))}
                  </div>
                </>
              )}
            </div>

            {formatTags.length > 0 && (
              <div className="space-y-2">
                <span className="kicker text-mocha-faint">业态 · 形式</span>
                <div className="flex flex-wrap gap-1.5">{formatTags.map(renderFlag)}</div>
              </div>
            )}

            <div className="space-y-2">
              <span className="kicker text-mocha-faint">权威认证</span>
              <div className="flex flex-wrap gap-1.5">{awardTags.map(renderFlag)}</div>
            </div>

            {ingredientTags.length > 0 && (
              <div className="space-y-2">
                <span className="kicker text-mocha-faint">食材 · 吃什么</span>
                <div className="flex flex-wrap gap-1.5">{ingredientTags.map(renderFlag)}</div>
              </div>
            )}

            <div className="space-y-2">
              <span className="kicker text-mocha-faint">特别标签</span>
              <div className="flex flex-wrap gap-1.5">{specialTags.map(renderFlag)}</div>
            </div>
          </div>
        )}

        {/* 已选条件 */}
        {activeFilterCount > 0 && (
          <div className="flex items-center gap-2 mb-4 flex-wrap">
            <span className="kicker text-mocha-faint">已选</span>
            {flavor && (
              <span className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-terracotta text-white text-xs rounded-full">
                {flavor}<button onClick={() => setFlavor(null)}>✕</button>
              </span>
            )}
            {Array.from(tiers).map((t) => (
              <span key={t} className="inline-flex items-center gap-1.5 px-2.5 py-1 border border-line text-xs rounded-full bg-white">
                {t}<button onClick={() => toggleTier(t)}>✕</button>
              </span>
            ))}
            {district && (
              <span className="inline-flex items-center gap-1.5 px-2.5 py-1 border border-line text-xs rounded-full bg-white">
                {district}{location ? ` · ${location}` : ''}<button onClick={() => { setDistrict(null); setLocation(null); }}>✕</button>
              </span>
            )}
            {!district && location && (
              <span className="inline-flex items-center gap-1.5 px-2.5 py-1 border border-line text-xs rounded-full bg-white">
                {location}<button onClick={() => setLocation(null)}>✕</button>
              </span>
            )}
            {Array.from(tagSel).map((id) => (
              <span key={id} className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-mocha text-cream-50 text-xs rounded-full">
                {tagName(id)}<button onClick={() => toggleTag(id)}>✕</button>
              </span>
            ))}
            {search && (
              <span className="inline-flex items-center gap-1.5 px-2.5 py-1 border border-line text-xs rounded-full bg-white">
                “{search}”<button onClick={() => setSearch('')}>✕</button>
              </span>
            )}
            <button onClick={clearAll} className="text-2xs text-terracotta underline ml-1">全部清除</button>
          </div>
        )}

        {/* 餐厅列表 */}
        {filtered.length === 0 ? (
          <div className="text-center py-20">
            <p className="serif text-2xl text-mocha-faint mb-2">没有找到</p>
            <p className="text-sm text-mocha-faint">试试调整筛选条件</p>
            <button onClick={clearAll} className="mt-6 btn btn-outline">清除筛选</button>
          </div>
        ) : (
          <>
            <div className="border-t border-line">
              {filtered.slice(0, shown).map((r, idx) => {
                const names = rCuisineNames[r.id] || [];
                const tags = rTagIds[r.id];
                const isMichelin = tags?.has(159);
                const isBlackPearl = tags?.has(160);
                return (
                  <Link key={r.id} href={`/restaurants/${r.id}`}
                    className="group flex items-center gap-4 md:gap-6 py-4 border-b border-line hover:bg-white transition -mx-6 px-6">
                    <span className="numeral text-xl text-mocha-faint w-8 flex-shrink-0 hidden sm:block">{String(idx + 1).padStart(2, '0')}</span>
                    <div className="flex-1 min-w-0">
                      <h3 className="serif text-base font-medium group-hover:italic transition truncate flex items-center gap-2">
                        <span className="truncate">{r.name}</span>
                        {isMichelin && <span title="米其林星级" className="text-2xs font-sans not-italic bg-mocha text-mustard-soft px-1.5 py-0.5 rounded shrink-0">★ 米其林</span>}
                        {isBlackPearl && <span title="黑珍珠餐厅" className="text-2xs font-sans not-italic bg-[#3a2a24] text-[#D8B98E] px-1.5 py-0.5 rounded shrink-0">◆ 黑珍珠</span>}
                      </h3>
                      <div className="flex items-center gap-2 mt-1 flex-wrap">
                        {names.slice(0, 2).map((cn, i) => (
                          <span key={i} className="kicker text-mocha-faint">{cn}</span>
                        ))}
                        {(r.business_area || r.district) && (
                          <span className="kicker text-mocha-mute">· {r.business_area ? `${r.business_area} · ` : ''}{r.district}</span>
                        )}
                      </div>
                    </div>
                    <div className="hidden lg:block flex-1 min-w-0">
                      {Array.isArray(r.signature_dishes) && r.signature_dishes.length > 0 && (
                        <p className="text-xs text-mocha-soft truncate">{r.signature_dishes.slice(0, 3).join(' · ')}</p>
                      )}
                    </div>
                    <span className={`tag ${tierClass(r.tier)} flex-shrink-0`}>{r.tier || '—'}</span>
                    <span className="serif text-base font-medium w-16 text-right flex-shrink-0 tabular-nums">
                      {r.price_avg ? `¥${r.price_avg}` : '—'}
                    </span>
                    <div className="w-12 text-right flex-shrink-0">
                      {r.score_total ? <span className="serif text-base font-medium tabular-nums">{r.score_total.toFixed(1)}</span>
                        : <span className="text-mocha-faint text-xs">—</span>}
                    </div>
                  </Link>
                );
              })}
            </div>
            {filtered.length > shown && (
              <div className="text-center py-8">
                <button onClick={() => setShown((s) => s + PAGE)} className="btn btn-outline">
                  加载更多（还有 {filtered.length - shown} 家）
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

// 沿 parent 链找到一级根
function topLevel(c: Cuisine, all: Cuisine[]): string {
  let cur: Cuisine | undefined = c;
  let guard = 0;
  while (cur && cur.parent_category && !ROOTS.includes(cur.parent_category) && guard < 8) {
    cur = all.find((x) => x.name === cur!.parent_category && x.dimension === '菜系');
    guard++;
  }
  return cur?.parent_category && ROOTS.includes(cur.parent_category) ? cur.parent_category : '中餐';
}
