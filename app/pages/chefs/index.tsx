import Head from 'next/head';
import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import { supabase, Chef, ChefRestaurant, RestaurantGroup } from '@/lib/supabase';

// 小表全量拉取（chefs 56 / rchefs 75 / groups 10，远低于 1000 页上限）
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

export default function ChefsIndex() {
  const [chefs, setChefs] = useState<Chef[]>([]);
  const [rchefs, setRchefs] = useState<ChefRestaurant[]>([]);
  const [groups, setGroups] = useState<RestaurantGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');

  useEffect(() => {
    (async () => {
      const [c, rc, g] = await Promise.all([
        fetchAll<Chef>('chefs', '*', 'id'),
        fetchAll<ChefRestaurant>('restaurant_chefs', 'restaurant_id,chef_id,role,is_current', 'restaurant_id'),
        fetchAll<RestaurantGroup>('restaurant_groups', '*', 'id'),
      ]);
      setChefs(c);
      setRchefs(rc);
      setGroups(g);
      setLoading(false);
    })();
  }, []);

  const groupName = useMemo(() => {
    const m: Record<number, string> = {};
    groups.forEach((g) => { m[g.id] = g.name; });
    return m;
  }, [groups]);

  // 每位主厨当前在营餐厅数（用于排序）
  const restCount = useMemo(() => {
    const m: Record<number, number> = {};
    rchefs.forEach((r) => { if (r.is_current !== false) m[r.chef_id] = (m[r.chef_id] || 0) + 1; });
    return m;
  }, [rchefs]);

  const rows = useMemo(() => {
    let list = [...chefs];
    const q = search.trim().toLowerCase();
    if (q) {
      list = list.filter((c) =>
        c.name.toLowerCase().includes(q) ||
        (c.name_en || '').toLowerCase().includes(q) ||
        (c.title || '').toLowerCase().includes(q) ||
        (c.signature_style || '').toLowerCase().includes(q));
    }
    // 有店的主厨排前面，再按名字
    list.sort((a, b) => (restCount[b.id] || 0) - (restCount[a.id] || 0) || a.name.localeCompare(b.name, 'zh'));
    return list;
  }, [chefs, search, restCount]);

  if (loading) return (
    <div className="min-h-screen bg-cream-50 flex items-center justify-center"><div className="spinner" /></div>
  );

  return (
    <div className="min-h-screen bg-cream-50">
      <Head><title>主厨 · China Travel</title></Head>

      <header className="border-b border-line sticky top-0 z-50 bg-cream-50/90 backdrop-blur-sm">
        <div className="max-w-4xl mx-auto px-6 h-14 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2 text-mocha hover:text-terracotta transition">
            <span>←</span><span className="serif text-base font-medium">首页</span>
          </Link>
          <div className="flex items-center gap-4">
            <span className="kicker text-mocha-faint">{rows.length} 位主厨</span>
            <Link href="/groups" className="kicker text-mocha-soft hover:text-terracotta transition">集团</Link>
            <Link href="/restaurants" className="kicker text-mocha-soft hover:text-mocha transition">餐厅</Link>
          </div>
        </div>
      </header>

      <div className="max-w-4xl mx-auto px-6 py-10">
        <div className="flex items-center gap-3 mb-4">
          <span className="w-8 h-px bg-terracotta" />
          <span className="kicker text-terracotta">CHEFS / 主厨谱系</span>
        </div>
        <h1 className="serif text-4xl font-medium mb-3">主厨</h1>
        <p className="text-mocha-soft text-sm leading-relaxed mb-8">
          主理人与主厨：履历、招牌风格与他们在上海的门店。口味最终落在人身上——同一位主厨换了店，风格往往跟着走。
        </p>

        <div className="relative mb-6">
          <input
            type="text" value={search} onChange={(e) => setSearch(e.target.value)}
            placeholder="搜索主厨姓名、头衔、风格…"
            className="w-full py-2 bg-transparent border-b border-line text-sm focus:outline-none placeholder:text-mocha-faint focus:border-terracotta"
          />
          {search && (
            <button onClick={() => setSearch('')} className="absolute right-0 top-1/2 -translate-y-1/2 text-mocha-faint hover:text-mocha text-sm">✕</button>
          )}
        </div>

        <div className="border-t border-line">
          {rows.map((c) => (
            <Link key={c.id} href={`/chefs/${c.id}`}
              className="group flex items-center gap-4 py-4 border-b border-line hover:bg-white transition -mx-6 px-6">
              <div className="flex-1 min-w-0">
                <h3 className="serif text-base font-medium group-hover:italic transition truncate flex items-center gap-2">
                  <span className="truncate">{c.name}</span>
                  {c.name_en && <span className="text-xs text-mocha-faint font-sans italic">{c.name_en}</span>}
                </h3>
                <div className="flex items-center gap-2 mt-1 flex-wrap">
                  {c.title && <span className="kicker text-mocha-faint truncate">{c.title}</span>}
                  {c.group_id ? (
                    <span className="kicker text-terracotta">· {groupName[c.group_id]}</span>
                  ) : null}
                </div>
              </div>
              <div className="flex-shrink-0 text-right">
                <div className="serif text-lg font-medium tabular-nums">{restCount[c.id] || 0}</div>
                <div className="kicker text-mocha-faint text-2xs">在营门店</div>
              </div>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
