import { useRouter } from 'next/router';
import { useEffect, useState } from 'react';
import Link from 'next/link';
import Head from 'next/head';
import { supabase, Chef, ChefRestaurant, RestaurantGroup, Restaurant } from '@/lib/supabase';
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

export default function ChefDetail() {
  const router = useRouter();
  const { id } = router.query;
  const [chef, setChef] = useState<Chef | null>(null);
  const [group, setGroup] = useState<RestaurantGroup | null>(null);
  const [links, setLinks] = useState<(ChefRestaurant & { restaurant?: Restaurant })[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    (async () => {
      const { data: c } = await supabase.from('chefs').select('*').eq('id', id).single();
      let g: RestaurantGroup | null = null;
      if (c && c.group_id) {
        const { data: gdata } = await supabase.from('restaurant_groups').select('*').eq('id', c.group_id).maybeSingle();
        g = (gdata as RestaurantGroup) || null;
      }
      const rc = await fetchAll<ChefRestaurant>('restaurant_chefs', '*', 'restaurant_id');
      const mine = rc.filter((r) => r.chef_id === Number(id));
      const rids = mine.map((r) => r.restaurant_id);
      let restMap: Record<number, Restaurant> = {};
      if (rids.length) {
        const allRest = await fetchAll<Restaurant>('restaurants', 'id,name,district,business_area,status,price_avg,score_total', 'id');
        allRest.forEach((r) => { restMap[r.id] = r; });
      }
      setChef(c as Chef);
      setGroup(g);
      setLinks(mine.map((m) => ({ ...m, restaurant: restMap[m.restaurant_id] })));
      setLoading(false);
    })();
  }, [id]);

  if (loading) return (
    <div className="min-h-screen bg-cream-50 flex items-center justify-center"><div className="spinner" /></div>
  );
  if (!chef) return <div className="min-h-screen bg-cream-50 flex items-center justify-center text-mocha-faint">主厨不存在</div>;

  const c = chef;
  const current = links.filter((l) => l.is_current !== false && l.restaurant && l.restaurant.status !== 'closed');
  const past = links.filter((l) => !(l.is_current !== false && l.restaurant && l.restaurant.status !== 'closed'));

  return (
    <div className="min-h-screen bg-cream-50">
      <Head><title>{c.name} · 主厨 · China Travel</title></Head>

      <header className="border-b border-line sticky top-0 z-50 bg-cream-50/90 backdrop-blur-sm">
        <div className="max-w-4xl mx-auto px-6 h-14 flex items-center justify-between">
          <Link href="/chefs" className="flex items-center gap-2 text-mocha hover:text-mocha-soft transition">
            <span>←</span><span className="serif text-base font-medium">主厨列表</span>
          </Link>
          <div className="flex items-center gap-4">
            <Link href="/groups" className="kicker text-mocha-soft hover:text-terracotta transition">集团</Link>
            <Link href="/restaurants" className="kicker text-mocha-soft hover:text-mocha transition">餐厅</Link>
          </div>
        </div>
      </header>

      <div className="max-w-4xl mx-auto px-6 py-10">
        {/* 标题区 */}
        <div className="mb-8">
          <div className="flex items-center gap-3 mb-4 flex-wrap">
            <span className="w-8 h-px bg-mocha" />
            {c.origin && <span className="kicker text-mocha-faint">{c.origin}</span>}
            {group && (
              <Link href={`/groups/${group.id}`}>
                <span className="kicker text-terracotta hover:underline cursor-pointer">{group.name}</span>
              </Link>
            )}
          </div>
          <h1 className="serif text-4xl md:text-5xl font-medium leading-tight mb-2">{c.name}</h1>
          {c.name_en && <p className="text-mocha-faint italic text-sm mb-3">{c.name_en}</p>}
          {c.title && <p className="serif text-lg text-mocha-soft">{c.title}</p>}
        </div>

        {c.bio && (
          <p className="serif text-lg font-light leading-relaxed text-mocha-soft mb-8">{c.bio}</p>
        )}

        {/* 在营门店 */}
        {current.length > 0 && (
          <section className="border-t border-line pt-8 mb-8">
            <h2 className="kicker text-mocha-faint mb-5">RESTAURANTS / 在营门店</h2>
            <div className="space-y-3">
              {current.map((l) => (
                <Link key={l.restaurant_id} href={`/restaurants/${l.restaurant_id}`}
                  className="flex items-center gap-4 p-4 bg-white border border-line rounded-xl hover:border-terracotta transition group">
                  <div className="flex-1 min-w-0">
                    <h3 className="serif text-base font-medium group-hover:italic truncate">{l.restaurant!.name}</h3>
                    <div className="flex items-center gap-2 mt-1">
                      {l.role && <span className="kicker text-mocha-faint">{l.role}</span>}
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
          </section>
        )}

        {/* 履历 / 风格 */}
        {c.culinary_background && (
          <section className="border-t border-line pt-8 mb-8">
            <h2 className="kicker text-mocha-faint mb-3">BACKGROUND / 厨艺履历</h2>
            <p className="text-sm text-mocha-soft leading-relaxed whitespace-pre-line">{safeText(c.culinary_background)}</p>
          </section>
        )}

        {c.signature_style && (
          <section className="border-t border-line pt-8 mb-8">
            <h2 className="kicker text-mocha-faint mb-3">STYLE / 招牌风格</h2>
            <p className="text-sm text-mocha-soft leading-relaxed whitespace-pre-line">{safeText(c.signature_style)}</p>
          </section>
        )}

        {c.reputation && (
          <section className="border-t border-line pt-8 mb-8">
            <h2 className="kicker text-mocha-faint mb-3">REPUTATION / 荣誉与认可</h2>
            <p className="text-sm text-mocha-soft leading-relaxed whitespace-pre-line">{safeText(c.reputation)}</p>
          </section>
        )}

        {/* 已结业/过往 */}
        {past.length > 0 && (
          <section className="border-t border-line pt-8 mb-8 opacity-80">
            <h2 className="kicker text-mocha-faint mb-3">PAST / 过往门店</h2>
            <div className="space-y-2">
              {past.map((l) => (
                <div key={l.restaurant_id} className="flex items-center gap-3 text-sm text-mocha-mute">
                  <span className="serif">{l.restaurant?.name || `#${l.restaurant_id}`}</span>
                  {l.role && <span className="kicker text-mocha-faint">· {l.role}</span>}
                  {l.restaurant?.status === 'closed' && <span className="kicker text-mocha-faint">· 已关店</span>}
                </div>
              ))}
            </div>
          </section>
        )}

        <div className="pt-6 border-t border-line">
          <Link href="/chefs" className="btn btn-outline">← 主厨列表</Link>
        </div>
      </div>
    </div>
  );
}
