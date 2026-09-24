import Head from 'next/head';
import Link from 'next/link';
import { useEffect, useState, useMemo, useCallback, useRef } from 'react';
import { useRouter } from 'next/router';
import { supabase, Restaurant, Cuisine, fetchThresholds, PriceThreshold, bandLabel, thresholdFor } from '@/lib/supabase';
import { safeText } from '@/lib/format';

// 预算筛选：客观的绝对人均区间（全库统一，用于"按预算找店"）。
// 边界取自正餐真实价格分位数并取整（P25=95→100 / P50=133→150 / P75=268→300 / P90=629→600），不拍脑袋。
const BUDGETS = [
  { key: 'b1', lo: null as number | null, hi: 100, label: '<¥100' },
  { key: 'b2', lo: 100, hi: 150, label: '¥100–150' },
  { key: 'b3', lo: 150, hi: 300, label: '¥150–300' },
  { key: 'b4', lo: 300, hi: 600, label: '¥300–600' },
  { key: 'b5', lo: 600, hi: null as number | null, label: '¥600+' },
];

// 一级根：地图认知顺序（中餐独立；其余按大陆→国家；非正餐为场景；融合菜单列）
const ROOTS = ['中餐', '亚洲', '欧洲', '非洲', '北美洲', '南美洲', '融合菜', '非正餐'];
const PAGE = 120;
// 详情页返回时恢复筛选与滚动位置的快照键（sessionStorage）
const RETURN_KEY = 'restaurants:returnState';

// 卡片价格带颜色：按客观 price_band（1-5）由浅到深，仅反映价格高低、不暗示品质。
const BAND_CLASSES = ['tag-budget', 'tag-value', 'tag-mid', 'tag-fine', 'tag-luxury'];
const bandClass = (band?: number | null) => BAND_CLASSES[(band || 1) - 1] || 'tag-mid';

// 食材「主营专门店」判定：食材名 -> 匹配"主营该食材的菜系叶子名"的正则。
// 选食材后，命中且菜系主营匹配 = 主营(main)；命中食材但菜系主营是别的 = 菜单含有(secondary 折叠)。
// 关键：分区依据是"该食材是否为店的主营品类"，不是"正餐 vs 非正餐"（否则面馆被折叠、咖啡店反进主营）。
// 陷阱：面 ≠ 面包（用 面(?!包)）；新增食材需在此补主营词。详见 skill cuisine-classification-engine。
const INGREDIENT_SPECIALTY: Record<string, RegExp> = {
  '面': /面(?!包)|拉面|荞麦|乌冬|河粉|米粉|粿条|叻沙|意面|pho|ramen|soba|udon|pasta|noodle/i,
  '饺子/馄饨': /饺子|水饺|煎饺|锅贴|馄饨|烧麦|烧卖|dumpling|gyoza|wonton/i,
  '包子/馒头': /包子|馒头|生煎|小笼|灌汤包|肉包|菜包|花卷|蒸包|baozi|xiaolongbao/i,
  '饼': /饼|披萨|比萨|pizza|抓饼|葱油饼|可丽饼|crepe|naan|馕|飞饼|flatbread/i,
  '饭': /饭|丼|烩饭|抓饭|焗饭|炒饭|risotto|donburi|nasi|biryani/i,
  '粥/泡饭': /粥|泡饭|congee|porridge/i,
  '汤/煲': /汤|煲|soup|broth|potage/i,
  '火锅/锅物': /火锅|锅物|打边炉|寿喜烧|hot\s?pot|shabu|sukiyaki/i,
  '烧烤/烤串': /烧烤|烤串|烧鸟|烧肉|烤肉|串烧|bbq|grill|yakitori|yakiniku|kebab|churrasco|巴西烤/i,
  '海鲜': /海鲜|鱼生|刺身|生蚝|龙虾|蟹|鱼鲜|寿司|seafood|sashimi|oyster|lobster|sushi|nigiri/i,
  '肉禽': /牛排|猪排|炸鸡|烤鸭|烧鹅|白切鸡|盐焗鸡|烧鸟|烧肉|烤肉|火腿|羊肉|牛肉|steak|chop|rotisserie|charcuterie|churrasco|佛罗伦萨/i,
  '蔬菜/素食': /素食|素菜|沙拉|轻食|植物肉|vegan|vegetarian|salad/i,
  '甜品/点心': /甜品|甜点|甜汤|糖水|蛋糕|冰淇淋|布丁|提拉米苏|马卡龙|和果子|刨冰|芭菲|松饼|dessert|gelato|ice\s?cream|parfait|sorbet|pastry/i,
  '面包/烘焙': /面包|烘焙|可颂|贝果|酸种|法棍|吐司|bakery|bread|croissant|bagel|sourdough/i,
  '饮品': /咖啡|奶茶|茶饮|茶馆|特调|手冲|酒吧|鸡尾酒|威士忌|精酿|葡萄酒|清酒|果汁|coffee|tea|bar|cocktail|whisk|wine|sake|juice|brew/i,
  '小吃/街头': /小吃|街头|臭豆腐|烤冷面|章鱼小丸子|鸡蛋仔|盐酥鸡|炸串|关东煮|串串香|麻辣烫|street|snack/i,
  '河鲜': /河鲜|河鱼|江湖鱼/i,
  '菌菇/山珍': /菌菇|山珍|野菌/i,
  '豆制品/豆花': /豆制品|豆花|豆腐|tofu/i,
  '烧腊/卤味': /烧腊|卤味|烧鹅|叉烧|卤水|char\s?siu|roast/i,
};

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
  const [root, setRoot] = useState('中餐');              // 一级根 Tab
  const [flavor, setFlavor] = useState<string | null>(null); // 二级菜系 name
  const [subFlavor, setSubFlavor] = useState<string | null>(null); // 三级子流派 name（在二级基础上再筛）
  const [budgets, setBudgets] = useState<Set<string>>(new Set()); // 预算区间 key（BUDGETS）
  const [thresholds, setThresholds] = useState<PriceThreshold[]>([]); // 各场景价格带阈值
  const [district, setDistrict] = useState<string | null>(null);
  const [location, setLocation] = useState<string | null>(null);
  const [tagSel, setTagSel] = useState<Set<number>>(new Set()); // 业态/认证/标签/食材 多选
  const [showFilters, setShowFilters] = useState(false);
  const [showSecondary, setShowSecondary] = useState(false);   // 展开"菜单含该食材的正餐大店"
  const [hideChain, setHideChain] = useState(false);           // 隐藏工业化连锁/预制菜
  const [shown, setShown] = useState(PAGE);

  useEffect(() => {
    (async () => {
      const [rest, cuis, links, th] = await Promise.all([
        fetchAll<Restaurant>('restaurants', '*', 'id'),
        fetchAll<Cuisine>('cuisines', '*', 'id'),
        fetchAll<{ restaurant_id: number; cuisine_id: number }>('restaurant_cuisines', 'restaurant_id,cuisine_id', 'restaurant_id'),
        fetchThresholds(),
      ]);
      setRestaurants(rest);
      setCuisines(cuis);
      setRc(links);
      setThresholds(th);
      setLoading(false);
    })();
  }, []);

  // ---- 树索引 ----
  const childrenOf = useCallback(
    (parent: string) => cuisines.filter((c) => c.dimension === '菜系' && c.parent_category === parent),
    [cuisines]
  );

  // URL ?cuisine=&sub= 自动定位（虚拟根或具体菜系）
  useEffect(() => {
    if (router.query.cuisine && cuisines.length) {
      const name = decodeURIComponent(router.query.cuisine as string);
      const sub = router.query.sub ? decodeURIComponent(router.query.sub as string) : null;
      if (ROOTS.includes(name)) { setRoot(name); setFlavor(name); }
      else {
        const c = cuisines.find((x) => x.name === name && x.dimension === '菜系');
        if (c) { setFlavor(name); setRoot(topLevel(c, cuisines)); }
      }
      if (sub) setSubFlavor(sub);
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

  // 非正餐（咖啡/面包/甜品/Bar/茶饮 全部子孙）id：连锁是这些业态的常态，隐藏连锁时豁免。
  const nonDinerIds = useMemo(() => collectFlavorIds('非正餐'), [collectFlavorIds]);
  const isNonDiner = useCallback((r: Restaurant): boolean => {
    const t = rTagIds[r.id];
    return !!t && Array.from(nonDinerIds).some((id) => t.has(id));
  }, [rTagIds, nonDinerIds]);

  // 食材主营判定见模块级 INGREDIENT_SPECIALTY：分区依据是"该食材是否为店的主营菜系"。

  // 选中二级菜系：同步根 Tab + 地址栏；再点同一二级（且无三级）则取消
  const selectFlavor = useCallback((name: string) => {
    const c = cuisines.find((x) => x.name === name && x.dimension === '菜系');
    if (flavor === name && !subFlavor) {
      setFlavor(null); setSubFlavor(null);
      router.replace('/restaurants', undefined, { shallow: true });
      return;
    }
    setFlavor(name); setSubFlavor(null);
    if (c) setRoot(topLevel(c, cuisines));
    router.replace(`/restaurants?cuisine=${encodeURIComponent(name)}`, undefined, { shallow: true });
  }, [cuisines, flavor, subFlavor, router]);

  // 选中三级子流派：再点同一三级即撤销（回到只筛二级），二级与三级行不消失
  const selectSub = useCallback((name: string) => {
    const next = subFlavor === name ? null : name;
    setSubFlavor(next);
    if (flavor) {
      const base = `/restaurants?cuisine=${encodeURIComponent(flavor)}`;
      router.replace(next ? `${base}&sub=${encodeURIComponent(next)}` : base, undefined, { shallow: true });
    }
  }, [subFlavor, flavor, router]);

  // 切换一级根：立即按该根筛选（虚拟根同样可由 collectFlavorIds 收集子孙）
  const selectRoot = useCallback((rname: string) => {
    setRoot(rname);
    setFlavor(rname);
    setSubFlavor(null);
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

  // 二级菜系的三级子流派（flavor 为虚拟根时不展开；选中三级叶子后 flavor 不变、本行不消失）
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
    budgets.size + (district ? 1 : 0) + (location ? 1 : 0) + tagSel.size + (flavor ? 1 : 0) + (search ? 1 : 0);

  const doSort = (arr: Restaurant[]) => {
    if (sortBy === 'score') arr.sort((a, b) => (b.score_total || 0) - (a.score_total || 0));
    else if (sortBy === 'price_asc') arr.sort((a, b) => (a.price_avg ?? 9999) - (b.price_avg ?? 9999));
    else arr.sort((a, b) => (b.price_avg ?? 0) - (a.price_avg ?? 0));
    return arr;
  };

  // ---- 筛选 + 排序：返回主营结果 main 与"菜单含食材的正餐大店" secondary ----
  const view = useMemo(() => {
    let result = [...restaurants];
    result = result.filter((r) => r.status !== 'closed' && r.status !== '关店');
    if (hideChain) result = result.filter((r) => !r.is_chain_standardized || isNonDiner(r));
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      result = result.filter((r) =>
        r.name.toLowerCase().includes(q) ||
        safeText(r.address).toLowerCase().includes(q) ||
        safeText(r.business_area).toLowerCase().includes(q) ||
        (Array.isArray(r.signature_dishes) && r.signature_dishes.some((d) => d.toLowerCase().includes(q)))
      );
    }
    // 菜系：三级优先，否则二级/根
    const activeFlavor = subFlavor || flavor;
    if (activeFlavor) {
      const ids = collectFlavorIds(activeFlavor);
      result = result.filter((r) => rTagIds[r.id] && Array.from(ids).some((id) => rTagIds[r.id].has(id)));
    }
    if (budgets.size) result = result.filter((r) => {
      const p = r.price_avg;
      if (p == null) return false;
      return BUDGETS.some((b) => budgets.has(b.key) &&
        (b.lo == null || p >= b.lo) && (b.hi == null || p < b.hi));
    });
    if (district) result = result.filter((r) => r.district === district);
    if (location) result = result.filter((r) => r.business_area === location);
    // 标签组（食材组单独处理）
    let ingredientGroup: Set<number> | null = null;
    Object.entries(tagGroups).forEach(([dim, group]) => {
      if (dim === '食材') { ingredientGroup = group; return; }
      result = result.filter((r) => rTagIds[r.id] && Array.from(group).some((id) => rTagIds[r.id].has(id)));
    });
    // 食材：主营该食材的专门店进 main；菜单含此食材但主营是别的菜系 -> secondary 折叠
    let secondary: Restaurant[] = [];
    if (ingredientGroup) {
      const g = Array.from(ingredientGroup) as number[];
      result = result.filter((r) => rTagIds[r.id] && g.some((id) => rTagIds[r.id].has(id)));
      // 主营：命中的食材中，有任一食材的"主营菜系正则"命中该店菜系名
      const isMain = (r: Restaurant) => {
        const names = rCuisineNames[r.id] || [];
        return g.some((id) => {
          const ingName = cuisines.find((c) => c.id === id)?.name || '';
          const re = INGREDIENT_SPECIALTY[ingName];
          return !!re && names.some((n) => re.test(n));
        });
      };
      secondary = result.filter((r) => !isMain(r));
      result = result.filter((r) => isMain(r));
    }
    doSort(result); doSort(secondary);
    return { main: result, secondary };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [restaurants, search, hideChain, flavor, subFlavor, budgets, district, location, tagGroups, sortBy, rTagIds, rCuisineNames, cuisines, collectFlavorIds, isNonDiner]);

  const filtered = view.main;
  const secondaryList = view.secondary;
  const hasIngredient = !!tagGroups['食材'];

  useEffect(() => { setShown(PAGE); setShowSecondary(false); },
    [search, hideChain, flavor, subFlavor, budgets, district, location, tagSel, sortBy]);

  // 详情页"更多餐厅"带 ?return=1 返回：恢复筛选快照与滚动位置
  const restoredRef = useRef(false);
  useEffect(() => {
    if (restoredRef.current) return;
    if (router.query.return !== '1' || loading || !restaurants.length) return;
    restoredRef.current = true;
    let snap: any = null;
    try { snap = JSON.parse(sessionStorage.getItem(RETURN_KEY) || 'null'); } catch { snap = null; }
    if (snap) {
      setSearch(snap.search || '');
      setSortBy(snap.sortBy || 'score');
      setRoot(snap.root || '中餐');
      setFlavor(snap.flavor || null);
      setSubFlavor(snap.subFlavor || null);
      setBudgets(new Set(snap.budgets || snap.tiers || []));
      setDistrict(snap.district || null);
      setLocation(snap.location || null);
      setTagSel(new Set(snap.tagSel || []));
      setHideChain(!!snap.hideChain);
      const y = Number(snap.scrollY) || 0;
      // 列表行高约 73px，先展开足够条数再恢复滚动，避免被"加载更多"截断
      setShown(Math.max(PAGE, Math.ceil(y / 73) + 12));
      // 列表首次渲染 + Next.js 内置滚动恢复（导航后会把页面拉回顶部）都会干扰：
      // 在约 4 秒内持续纠正到目标位置；用户一旦手动滚轮/触摸则立即停止，尊重用户操作。
      let tries = 0;
      let userInterrupted = false;
      const onInterrupt = () => { userInterrupted = true; };
      window.addEventListener('wheel', onInterrupt, { passive: true });
      window.addEventListener('touchstart', onInterrupt, { passive: true });
      const cleanup = () => {
        window.removeEventListener('wheel', onInterrupt);
        window.removeEventListener('touchstart', onInterrupt);
      };
      const tryScroll = () => {
        if (userInterrupted) { cleanup(); return; }
        const enough = document.documentElement.scrollHeight >= y + window.innerHeight * 0.5;
        if (enough && Math.abs(window.scrollY - y) > 6) {
          window.scrollTo({ top: y, behavior: 'auto' });
        }
        tries += 1;
        if (tries < 20) setTimeout(tryScroll, 200);
        else cleanup();
      };
      setTimeout(tryScroll, 120);
    }
    router.replace('/restaurants', undefined, { shallow: true });
  }, [router.query.return, loading, restaurants.length, router]);

  const toggleBudget = (k: string) => setBudgets((prev) => {
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

  // 进详情前保存完整筛选快照 + 滚动位置（供"更多餐厅"返回恢复）
  const saveReturn = useCallback(() => {
    try {
      sessionStorage.setItem(RETURN_KEY, JSON.stringify({
        v: 2, search, sortBy, root, flavor, subFlavor,
        budgets: Array.from(budgets), district, location,
        tagSel: Array.from(tagSel), hideChain, scrollY: window.scrollY,
      }));
    } catch { /* 隐私模式等忽略 */ }
  }, [search, sortBy, root, flavor, subFlavor, budgets, district, location, tagSel, hideChain]);

  const clearAll = () => {
    setSearch(''); setFlavor(null); setSubFlavor(null); setBudgets(new Set()); setDistrict(null);
    setLocation(null); setTagSel(new Set());
    router.replace('/restaurants', undefined, { shallow: true });
  };

  const renderFlavorTag = (c: Cuisine) => {
    const n = subtreeCount(c.name);
    const active = flavor === c.name && !subFlavor;
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

  const SORTS = [
    { key: 'score', label: '评分最高' },
    { key: 'price_asc', label: '人均低→高' },
    { key: 'price_desc', label: '人均高→低' },
  ] as const;

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
            <span className="kicker text-mocha-faint">{filtered.length + secondaryList.length} 家餐厅</span>
            <Link href="/map" className="kicker text-mocha-soft hover:text-mocha transition">地图</Link>
          </div>
        </div>
      </header>

      <div className="max-w-6xl mx-auto px-6 py-6">
        {/* 搜索 + 筛选 */}
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
            {budgets.size + (district ? 1 : 0) + (location ? 1 : 0) + tagSel.size > 0 && (
              <span className="badge">{budgets.size + (district ? 1 : 0) + (location ? 1 : 0) + tagSel.size}</span>
            )}
            <span className="text-2xs">{showFilters ? '▲' : '▼'}</span>
          </button>
        </div>

        {/* 排序：分段按钮，明确可见可点 */}
        <div className="flex items-center gap-2 mb-4 flex-wrap">
          <span className="kicker text-mocha-faint mr-1">排序</span>
          {SORTS.map((s) => (
            <button key={s.key} onClick={() => setSortBy(s.key)}
              data-active={sortBy === s.key}
              className="sort-seg px-3 py-1.5 rounded-full text-xs border transition-all whitespace-nowrap">
              {s.label}
            </button>
          ))}
          <button onClick={() => setHideChain((v) => !v)} data-active={hideChain}
            className="sort-seg px-3 py-1.5 rounded-full text-xs border transition-all whitespace-nowrap ml-2">
            隐藏连锁/预制
          </button>
        </div>

        {/* 价位条 */}
        <div className="flex items-center gap-2 mb-4 flex-wrap">
          <span className="kicker text-mocha-faint mr-1">价位</span>
          {BUDGETS.map((b) => {
            const on = budgets.has(b.key);
            return (
              <button key={b.key} className="price-chip px-3.5 py-1.5 rounded-full text-xs border transition-all whitespace-nowrap"
                data-active={on}
                style={on ? {} : { background: '#fff', borderColor: '#E0D5C8', color: '#5C4A3E' }}
                onClick={() => toggleBudget(b.key)}>
                {b.label}
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

          {/* 三级子流派（选中三级叶子后本行仍在；"全部"与各三级均可再点撤销） */}
          {flavorChildren.length > 0 && (
            <div className="flex items-start gap-3 flex-wrap pt-3 border-t border-dashed border-line">
              <span className="kicker text-mocha-faint shrink-0 pt-1.5">{flavor}</span>
              <div className="flex flex-wrap gap-1.5 flex-1">
                <button onClick={() => subFlavor && selectSub(subFlavor)}
                  data-active={!subFlavor}
                  className="sub-seg px-2.5 py-1 text-xs rounded-full border transition">
                  全部{flavor}
                </button>
                {flavorChildren.map((c) => (
                  <button key={c.id} onClick={() => selectSub(c.name)}
                    data-active={subFlavor === c.name}
                    className="sub-seg px-2.5 py-1 text-xs rounded-full border transition">
                    {c.name}{subtreeCount(c.name) > 0 && <span className="ml-1 text-2xs opacity-70">{subtreeCount(c.name)}</span>}
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
                        {safeText(l)}
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
                <span className="kicker text-mocha-faint">食材 · 吃什么（默认只看主营专门店）</span>
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
                {flavor}{subFlavor ? ` · ${subFlavor}` : ''}
                <button onClick={() => { if (subFlavor) selectSub(subFlavor); else { setFlavor(null); } }}>✕</button>
              </span>
            )}
            {Array.from(budgets).map((bk) => {
              const b = BUDGETS.find((x) => x.key === bk);
              return (
                <span key={bk} className="inline-flex items-center gap-1.5 px-2.5 py-1 border border-line text-xs rounded-full bg-white">
                  {b?.label}<button onClick={() => toggleBudget(bk)}>✕</button>
                </span>
              );
            })}
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

        {/* 餐厅列表（主营） */}
        {filtered.length === 0 && secondaryList.length === 0 ? (
          <div className="text-center py-20">
            <p className="serif text-2xl text-mocha-faint mb-2">没有找到</p>
            <p className="text-sm text-mocha-faint">试试调整筛选条件</p>
            <button onClick={clearAll} className="mt-6 btn btn-outline">清除筛选</button>
          </div>
        ) : (
          <>
            <RestaurantRows rows={filtered.slice(0, shown)} rCuisineNames={rCuisineNames} rTagIds={rTagIds} startIdx={0} isNonDiner={isNonDiner} onOpen={saveReturn} thresholds={thresholds} />

            {/* 食材：菜单含该食材的正餐大店（折叠） */}
            {hasIngredient && secondaryList.length > 0 && (
              <div className="border-t border-line pt-6 mt-2">
                {showSecondary ? (
                  <>
                    <p className="kicker text-mocha-faint mb-2">另有 {secondaryList.length} 家菜单含此食材的餐厅</p>
                    <RestaurantRows rows={secondaryList} rCuisineNames={rCuisineNames} rTagIds={rTagIds} startIdx={filtered.length} isNonDiner={isNonDiner} onOpen={saveReturn} thresholds={thresholds} />
                    <div className="text-center pt-4">
                      <button onClick={() => setShowSecondary(false)} className="text-2xs text-mocha-faint underline">收起</button>
                    </div>
                  </>
                ) : (
                  <div className="text-center">
                    <button onClick={() => setShowSecondary(true)} className="btn btn-outline">
                      另有 {secondaryList.length} 家菜单含此食材的餐厅（非主营）
                    </button>
                  </div>
                )}
              </div>
            )}

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

function RestaurantRows({ rows, rCuisineNames, rTagIds, startIdx, isNonDiner, onOpen, thresholds }: {
  rows: Restaurant[];
  rCuisineNames: Record<number, string[]>;
  rTagIds: Record<number, Set<number>>;
  startIdx: number;
  isNonDiner: (r: Restaurant) => boolean;
  onOpen: () => void;
  thresholds: PriceThreshold[];
}) {
  return (
    <div className="border-t border-line">
      {rows.map((r, i) => {
        const idx = startIdx + i;
        const names = rCuisineNames[r.id] || [];
        const tags = rTagIds[r.id];
        const isMichelin = tags?.has(159);
        const isBlackPearl = tags?.has(160);
        return (
          <Link key={r.id} href={`/restaurants/${r.id}`} onClick={onOpen}
            className="group flex items-center gap-4 md:gap-6 py-4 border-b border-line hover:bg-white transition -mx-6 px-6">
            <span className="numeral text-xl text-mocha-faint w-8 flex-shrink-0 hidden sm:block">{String(idx + 1).padStart(2, '0')}</span>
            <div className="flex-1 min-w-0">
              <h3 className="serif text-base font-medium group-hover:italic transition truncate flex items-center gap-2">
                <span className="truncate">{r.name}</span>
                {isMichelin && <span title="米其林星级" className="text-2xs font-sans not-italic bg-mocha text-mustard-soft px-1.5 py-0.5 rounded shrink-0">★ 米其林</span>}
                {isBlackPearl && <span title="黑珍珠餐厅" className="text-2xs font-sans not-italic bg-[#3a2a24] text-[#D8B98E] px-1.5 py-0.5 rounded shrink-0">◆ 黑珍珠</span>}
                {r.premade_risk === '高' && <span title="预制菜高风险，不进宝藏精选" className="text-2xs font-sans not-italic bg-[#F6D9C8] text-[#BC4B1E] px-1.5 py-0.5 rounded shrink-0">预制菜</span>}
                {r.is_chain_standardized && !isNonDiner(r) && <span title="标准化连锁，可在上方一键隐藏" className="text-2xs font-sans not-italic bg-[#E7E0D8] text-[#7A6A5C] px-1.5 py-0.5 rounded shrink-0">连锁</span>}
              </h3>
              <div className="flex items-center gap-2 mt-1 flex-wrap">
                {names.slice(0, 2).map((cn, k) => (
                  <span key={k} className="kicker text-mocha-faint">{cn}</span>
                ))}
                {(safeText(r.business_area) || r.district) && (
                  <span className="kicker text-mocha-mute">· {safeText(r.business_area) ? `${safeText(r.business_area)} · ` : ''}{r.district}</span>
                )}
              </div>
            </div>
            <div className="hidden lg:block flex-1 min-w-0">
              {Array.isArray(r.signature_dishes) && r.signature_dishes.length > 0 && (
                <p className="text-xs text-mocha-soft truncate">{r.signature_dishes.slice(0, 3).join(' · ')}</p>
              )}
            </div>
            {(() => {
              const t = thresholdFor(thresholds, r.price_scene, r.price_band);
              return t ? (
                <span title={`${r.price_scene} · 价格带 ${r.price_band}/5（客观区间，不代表品质）`}
                  className={`tag ${bandClass(r.price_band)} flex-shrink-0`}>{bandLabel(t)}</span>
              ) : <span className="tag tag-mid flex-shrink-0">—</span>;
            })()}
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
