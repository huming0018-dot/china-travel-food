import { useEffect, useState } from 'react';
import Link from 'next/link';
import { supabase, FeedEvent } from '@/lib/supabase';

const CAT_META: Record<string, { label: string; cls: string; dot: string }> = {
  new_open: { label: '新店开业', cls: 'bg-terracotta text-white', dot: 'bg-terracotta' },
  relocated: { label: '搬迁', cls: 'bg-mustard text-mocha', dot: 'bg-mustard' },
  closed: { label: '关店', cls: 'bg-mocha text-cream-100', dot: 'bg-mocha' },
  chef_changed: { label: '主厨变动', cls: 'bg-moss text-white', dot: 'bg-moss' },
  guest_kitchen: { label: '飞行厨房', cls: 'bg-moss text-white', dot: 'bg-moss' },
  collaboration: { label: '跨界联名', cls: 'bg-terracotta text-white', dot: 'bg-terracotta' },
  popup: { label: '快闪', cls: 'bg-mustard text-mocha', dot: 'bg-mustard' },
  award: { label: '获奖', cls: 'bg-moss text-white', dot: 'bg-moss' },
  menu_update: { label: '新菜单', cls: 'bg-cream-200 text-mocha border border-line', dot: 'bg-mocha-faint' },
  coming_soon: { label: '即将开业', cls: 'bg-terracotta text-white', dot: 'bg-terracotta' },
};
const DEFAULT_META = { label: '美食动态', cls: 'bg-cream-200 text-mocha border border-line', dot: 'bg-mocha-faint' };

function fmtDate(d?: string) {
  if (!d) return '';
  const [, mm, dd] = d.split('-');
  return `${mm}/${dd}`;
}

export default function FeedSection() {
  const [events, setEvents] = useState<FeedEvent[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      const { data, error } = await supabase.from('v_feed_recent').select('*').limit(7);
      if (!error && data) setEvents(data as FeedEvent[]);
      setLoading(false);
    })();
  }, []);

  if (loading) {
    return (
      <section className="max-w-7xl mx-auto px-6 py-12">
        <div className="kicker text-terracotta mb-2">WHAT'S NEW / 美食动态</div>
        <div className="space-y-3">{[...Array(4)].map((_, i) => <div key={i} className="skeleton h-16" />)}</div>
      </section>
    );
  }
  if (events.length === 0) return null;

  return (
    <section className="max-w-7xl mx-auto px-6 py-12">
      <div className="flex items-end justify-between mb-8">
        <div>
          <div className="kicker text-terracotta mb-2">WHAT'S NEW / 美食动态</div>
          <h2 className="serif text-3xl font-light">最近<span className="italic text-terracotta">动向</span></h2>
        </div>
        <p className="kicker text-mocha-faint hidden sm:block">主厨新店 · 飞行厨房 · 联名快闪</p>
      </div>

      <div className="relative">
        <span className="absolute left-[7px] top-2 bottom-2 w-px bg-line" aria-hidden />
        <div className="space-y-2">
          {events.map((e) => {
            const meta = CAT_META[e.category] || DEFAULT_META;
            const rid = e.restaurant_id || e.related_restaurant_id;
            const inner = (
              <div className="group relative pl-8 py-3 pr-3 rounded-2xl transition hover:bg-white">
                <span className={`absolute left-[3px] top-[22px] w-[9px] h-[9px] rounded-full ring-4 ring-cream-100 ${meta.dot}`} />
                <div className="flex items-center gap-3 mb-1.5 flex-wrap">
                  <span className={`text-[11px] font-medium px-2.5 py-0.5 rounded-full ${meta.cls}`}>{meta.label}</span>
                  {e.status === 'rumor' && (
                    <span className="text-[11px] px-2 py-0.5 rounded-full border border-dashed border-mocha-faint text-mocha-faint">传闻</span>
                  )}
                  {e.confidence === 'low' && (
                    <span className="text-[11px] text-mocha-faint">待证实</span>
                  )}
                  <span className="numeral text-xs text-mocha-faint ml-auto flex-shrink-0">{fmtDate(e.event_date)}</span>
                </div>
                <h3 className="text-[15px] font-medium text-mocha group-hover:text-terracotta transition leading-snug">{e.title}</h3>
                {e.summary && <p className="text-[13px] text-mocha-faint mt-1 line-clamp-2 leading-relaxed">{e.summary}</p>}
                <div className="flex items-center gap-2 mt-1.5">
                  {e.district && <span className="kicker text-mocha-faint">{e.district}</span>}
                  {rid && <span className="kicker text-terracotta opacity-0 group-hover:opacity-100 transition">查看餐厅 →</span>}
                </div>
              </div>
            );
            return rid ? (
              <Link key={e.id} href={`/restaurants/${rid}`} className="block">{inner}</Link>
            ) : (
              <div key={e.id}>{inner}</div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
