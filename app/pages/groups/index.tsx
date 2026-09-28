import Head from 'next/head';
import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import { supabase, RestaurantGroup, GroupMember, Chef } from '@/lib/supabase';

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

export default function GroupsIndex() {
  const [groups, setGroups] = useState<RestaurantGroup[]>([]);
  const [members, setMembers] = useState<GroupMember[]>([]);
  const [chefs, setChefs] = useState<Chef[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      const [g, m, c] = await Promise.all([
        fetchAll<RestaurantGroup>('restaurant_groups', '*', 'id'),
        fetchAll<GroupMember>('restaurant_group_members', '*', 'group_id'),
        fetchAll<Chef>('chefs', 'id,name,group_id', 'id'),
      ]);
      setGroups(g);
      setMembers(m);
      setChefs(c);
      setLoading(false);
    })();
  }, []);

  const restCount = useMemo(() => {
    const m: Record<number, number> = {};
    members.forEach((x) => { if (x.is_current !== false) m[x.group_id] = (m[x.group_id] || 0) + 1; });
    return m;
  }, [members]);

  const chefCount = useMemo(() => {
    const m: Record<number, number> = {};
    chefs.forEach((c) => { if (c.group_id) m[c.group_id] = (m[c.group_id] || 0) + 1; });
    return m;
  }, [chefs]);

  if (loading) return (
    <div className="min-h-screen bg-cream-50 flex items-center justify-center"><div className="spinner" /></div>
  );

  return (
    <div className="min-h-screen bg-cream-50">
      <Head><title>集团 · China Travel</title></Head>

      <header className="border-b border-line sticky top-0 z-50 bg-cream-50/90 backdrop-blur-sm">
        <div className="max-w-4xl mx-auto px-6 h-14 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2 text-mocha hover:text-terracotta transition">
            <span>←</span><span className="serif text-base font-medium">首页</span>
          </Link>
          <div className="flex items-center gap-4">
            <span className="kicker text-mocha-faint">{groups.length} 个集团/品牌矩阵</span>
            <Link href="/chefs" className="kicker text-mocha-soft hover:text-terracotta transition">主厨</Link>
            <Link href="/restaurants" className="kicker text-mocha-soft hover:text-mocha transition">餐厅</Link>
          </div>
        </div>
      </header>

      <div className="max-w-4xl mx-auto px-6 py-10">
        <div className="flex items-center gap-3 mb-4">
          <span className="w-8 h-px bg-terracotta" />
          <span className="kicker text-terracotta">GROUPS / 集团与品牌矩阵</span>
        </div>
        <h1 className="serif text-4xl font-medium mb-3">餐饮集团</h1>
        <p className="text-mocha-soft text-sm leading-relaxed mb-8">
          从集团、品牌、主厨反向看门店：同一家集团的供应链与风格互相参照。旗下品牌与在营门店见详情。
        </p>

        <div className="space-y-4">
          {groups.map((g) => (
            <Link key={g.id} href={`/groups/${g.id}`}
              className="card block p-6 hover:border-terracotta transition">
              <div className="flex items-start justify-between gap-4 mb-2">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <h3 className="serif text-xl font-medium group-hover:italic">{g.name}</h3>
                    {g.group_type && <span className="tag tag-chinese">{g.group_type}</span>}
                  </div>
                  {g.name_en && <p className="text-xs text-mocha-faint italic mt-0.5">{g.name_en}</p>}
                </div>
                <div className="flex-shrink-0 text-right">
                  <div className="serif text-2xl font-medium tabular-nums">{restCount[g.id] || 0}</div>
                  <div className="kicker text-mocha-faint text-2xs">在营门店</div>
                </div>
              </div>
              {g.description && (
                <p className="text-sm text-mocha-soft leading-relaxed line-clamp-2 mb-3">{g.description}</p>
              )}
              <div className="flex items-center gap-3 text-2xs text-mocha-faint">
                {g.founder && g.founder !== '——' && <span>创始人：{g.founder}</span>}
                {g.founded_year && <span>· {g.founded_year} 年创立</span>}
                {(chefCount[g.id] || 0) > 0 && <span>· {chefCount[g.id]} 位主厨</span>}
              </div>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
