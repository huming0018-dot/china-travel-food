import { useRouter } from 'next/router';
import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import Head from 'next/head';
import { supabase, RestaurantGroup, GroupMember, Chef, Restaurant } from '@/lib/supabase';
import { safeText } from '@/lib/format';

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

export default function GroupDetail() {
  const router = useRouter();
  const { id } = router.query;
  const [group, setGroup] = useState<RestaurantGroup | null>(null);
  const [members, setMembers] = useState<(GroupMember & { restaurant?: Restaurant })[]>([]);
  const [chefs, setChefs] = useState<Chef[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    (async () => {
      const { data: g } = await supabase.from('restaurant_groups').select('*').eq('id', id).single();
      const ms = await fetchAll<GroupMember>('restaurant_group_members', '*', 'group_id');
      const mine = ms.filter((m) => m.group_id === Number(id));
      const rids = mine.map((m) => m.restaurant_id);
      let restMap: Record<number, Restaurant> = {};
      if (rids.length) {
        const allRest = await fetchAll<Restaurant>('restaurants', 'id,name,district,business_area,status,price_avg,score_total', 'id');
        allRest.forEach((r) => { restMap[r.id] = r; });
      }
      const allChefs = await fetchAll<Chef>('chefs', '*', 'id');
      setGroup(g as RestaurantGroup);
      setMembers(mine.map((m) => ({ ...m, restaurant: restMap[m.restaurant_id] })));
      setChefs(allChefs.filter((c) => c.group_id === Number(id)));
      setLoading(false);
    })();
  }, [id]);

  // 按品牌名分组（同一品牌下的分店排在一起）
  const byBrand = useMemo(() => {
    const m: Record<string, (GroupMember & { restaurant?: Restaurant })[]> = {};
    members.forEach((x) => {
      if (x.is_current === false || !x.restaurant || x.restaurant.status === 'closed') return;
      const brand = x.brand_name || '其他';
      if (!m[brand]) m[brand] = [];
      m[brand].push(x);
    });
    return m;
  }, [members]);

  if (loading) return (
    <div className="min-h-screen bg-cream-50 flex items-center justify-center"><div className="spinner" /></div>
  );
  if (!group) return <div className="min-h-screen bg-cream-50 flex items-center justify-center text-mocha-faint">集团不存在</div>;

  const g = group;

  return (
    <div className="min-h-screen bg-cream-50">
      <Head><title>{g.name} · 集团 · China Travel</title></Head>

      <header className="border-b border-line sticky top-0 z-50 bg-cream-50/90 backdrop-blur-sm">
        <div className="max-w-4xl mx-auto px-6 h-14 flex items-center justify-between">
          <Link href="/groups" className="flex items-center gap-2 text-mocha hover:text-mocha-soft transition">
            <span>←</span><span className="serif text-base font-medium">集团列表</span>
          </Link>
          <div className="flex items-center gap-4">
            <Link href="/chefs" className="kicker text-mocha-soft hover:text-terracotta transition">主厨</Link>
            <Link href="/restaurants" className="kicker text-mocha-soft hover:text-mocha transition">餐厅</Link>
          </div>
        </div>
      </header>

      <div className="max-w-4xl mx-auto px-6 py-10">
        {/* 标题区 */}
        <div className="mb-8">
          <div className="flex items-center gap-3 mb-4 flex-wrap">
            <span className="w-8 h-px bg-mocha" />
            {g.group_type && <span className="kicker text-mocha-faint">{g.group_type}</span>}
            {g.founded_year && <span className="kicker text-mocha-faint">创立于 {g.founded_year}</span>}
          </div>
          <h1 className="serif text-4xl md:text-5xl font-medium leading-tight mb-2">{g.name}</h1>
          {g.name_en && <p className="text-mocha-faint italic text-sm mb-3">{g.name_en}</p>}
          {(g.founder && g.founder !== '——') && (
            <p className="text-sm text-mocha-soft">
              {g.founder_role ? `${g.founder_role}：` : ''}{g.founder}
            </p>
          )}
        </div>

        {g.description && (
          <p className="serif text-lg font-light leading-relaxed text-mocha-soft mb-8">{g.description}</p>
        )}

        {/* 旗下门店（按品牌分组） */}
        <section className="border-t border-line pt-8 mb-8">
          <h2 className="kicker text-mocha-faint mb-5">BRANDS &amp; VENUES / 旗下品牌与门店</h2>
          {Object.keys(byBrand).length === 0 ? (
            <p className="text-sm text-mocha-faint">暂无在营门店</p>
          ) : (
            <div className="space-y-6">
              {Object.entries(byBrand).map(([brand, rows]) => (
                <div key={brand}>
                  <div className="flex items-center gap-2 mb-2">
                    <span className="kicker text-terracotta">{brand}</span>
                    <span className="text-2xs text-mocha-faint">{rows.length} 店</span>
                    <span className="flex-1 h-px bg-line" />
                  </div>
                  <div className="space-y-2">
                    {rows.map((l) => (
                      <Link key={l.restaurant_id} href={`/restaurants/${l.restaurant_id}`}
                        className="flex items-center gap-4 p-3 bg-white border border-line rounded-lg hover:border-terracotta transition group">
                        <div className="flex-1 min-w-0">
                          <h3 className="serif text-base font-medium group-hover:italic truncate">{l.restaurant!.name}</h3>
                          <div className="flex items-center gap-2 mt-0.5">
                            {l.role && l.role !== brand && <span className="kicker text-mocha-faint">{l.role}</span>}
                            {(l.restaurant!.business_area || l.restaurant!.district) && (
                              <span className="kicker text-mocha-mute">· {[safeText(l.restaurant!.business_area), l.restaurant!.district].filter(Boolean).join(' · ')}</span>
                            )}
                          </div>
                        </div>
                        {l.restaurant!.price_avg != null && (
                          <span className="serif text-base font-medium flex-shrink-0">¥{l.restaurant!.price_avg}</span>
                        )}
                        {l.restaurant!.score_total != null && (
                          <span className="serif text-base font-medium flex-shrink-0 w-12 text-right tabular-nums">{l.restaurant!.score_total.toFixed(1)}</span>
                        )}
                      </Link>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* 旗下主厨 */}
        {chefs.length > 0 && (
          <section className="border-t border-line pt-8 mb-8">
            <h2 className="kicker text-mocha-faint mb-5">CHEFS / 旗下主厨</h2>
            <div className="space-y-2">
              {chefs.map((c) => (
                <Link key={c.id} href={`/chefs/${c.id}`}
                  className="flex items-center gap-3 p-3 bg-white border border-line rounded-lg hover:border-terracotta transition">
                  <span className="serif text-base font-medium">{c.name}</span>
                  {c.title && <span className="kicker text-mocha-faint truncate">· {c.title}</span>}
                </Link>
              ))}
            </div>
          </section>
        )}

        <div className="pt-6 border-t border-line">
          <Link href="/groups" className="btn btn-outline">← 集团列表</Link>
        </div>
      </div>
    </div>
  );
}
