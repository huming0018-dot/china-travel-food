import { useEffect, useMemo, useState } from 'react';
import { supabase, FeedEvent } from '@/lib/supabase';
import EventModal, { CAT_META, DEFAULT_META, ACTIVITY_CATS } from "@/components/EventModal";

const PAGE_SIZE = 10;

// —— 筛选标签定义（多标签叠加 = 命中任一即显示）——
type FilterKey = 'all' | 'new_open' | 'chef_new' | 'guest' | 'collab' | 'close_relocate' | 'award' | 'menu';
const FILTERS: { key: FilterKey; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'new_open', label: '新店开业' },
  { key: 'chef_new', label: '主厨新店' },
  { key: 'guest', label: '飞行厨房' },
  { key: 'collab', label: '联名快闪' },
  { key: 'close_relocate', label: '关店搬迁' },
  { key: 'award', label: '获奖' },
  { key: 'menu', label: '新菜单' },
];

function matchFilter(e: FeedEvent, key: FilterKey): boolean {
  switch (key) {
    case 'all': return true;
    case 'new_open': return e.category === 'new_open' || e.category === 'coming_soon';
    case 'chef_new':
      return (e.category === 'new_open' || e.category === 'coming_soon')
        && (!!e.chef_id || /by\s+[A-Z][a-zA-Z'’]*/.test(e.title));
    case 'guest': return e.category === 'guest_kitchen';
    case 'collab': return e.category === 'collaboration' || e.category === 'popup';
    case 'close_relocate': return e.category === 'relocated' || e.category === 'closed';
    case 'award': return e.category === 'award';
    case 'menu': return e.category === 'menu_update';
  }
}

// —— 去重：标题相似度（CJK 二元字组 + 英文/数字词）——
function titleTokens(t: string): Set<string> {
  const tokens = new Set<string>();
  const lower = t.toLowerCase();
  const words = lower.match(/[a-z0-9]+/g) || [];
  words.forEach((w) => tokens.add(w));
  const cjk = lower.match(/[\u4e00-\u9fff]+/g) || [];
  cjk.forEach((seg) => {
    for (let i = 0; i < seg.length - 1; i++) tokens.add(seg.slice(i, i + 2));
    if (seg.length === 1) tokens.add(seg);
  });
  return tokens;
}
function jaccard(a: Set<string>, b: Set<string>): number {
  if (a.size === 0 || b.size === 0) return 0;
  let inter = 0;
  a.forEach((x) => { if (b.has(x)) inter++; });
  return inter / (a.size + b.size - inter);
}
function daysBetween(a?: string, b?: string): number {
  if (!a || !b) return Infinity;
  const d = Math.abs(new Date(a).getTime() - new Date(b).getTime()) / 86400000;
  return isNaN(d) ? Infinity : d;
}
function clusterIds(e: FeedEvent): Set<number> {
  const s = new Set<number>();
  if (e.restaurant_id) s.add(e.restaurant_id);
  if (e.related_restaurant_id) s.add(e.related_restaurant_id);
  return s;
}

/** 合并同源事件：保留信息更全/已验证的那条，拼接 summary，日期取最早。 */
function dedup(events: FeedEvent[]): FeedEvent[] {
  const sorted = [...events].sort((a, b) => daysBetween(a.event_date) - daysBetween(b.event_date));
  const used = new Set<number>();
  const out: FeedEvent[] = [];

  for (const e of sorted) {
    if (used.has(e.id)) continue;
    const group = [e];
    used.add(e.id);
    const ca = clusterIds(e);
    const ta = titleTokens(e.title);

    for (const other of sorted) {
      if (used.has(other.id)) continue;
      const cb = clusterIds(other);
      const tb = titleTokens(other.title);
      const overlap = Array.from(ca).some((x) => cb.has(x));
      const sim = jaccard(ta, tb);
      const dd = daysBetween(e.event_date, other.event_date);

      let merge = false;
      if (overlap && dd <= 90) merge = true;
      else if (ca.size === 0 && cb.size === 0 && sim >= 0.6 && dd <= 45) merge = true;

      if (merge) {
        group.push(other);
        used.add(other.id);
      }
    }

    if (group.length === 1) {
      out.push(e);
    } else {
      // 选主：verified > rumor；confidence high>mid>low；summary 更长；日期更早
      const confRank = (c: string) => (c === 'high' ? 3 : c === 'mid' ? 2 : c === 'low' ? 1 : 0);
      group.sort((a, b) =>
        (Number(b.status === 'verified') - Number(a.status === 'verified'))
        || (confRank(b.confidence) - confRank(a.confidence))
        || ((b.summary?.length || 0) - (a.summary?.length || 0))
        || (daysBetween(a.event_date) - daysBetween(b.event_date))
      );
      const primary = { ...group[0] };
      primary.mergedIds = group.slice(1).map((g) => g.id);
      // 拼接其他 summary（去重、去掉与主 summary 重复的片段）
      const extras = group.slice(1)
        .map((g) => g.summary?.trim())
        .filter((s): s is string => !!s && s.length > 0 && s !== primary.summary?.trim());
      if (extras.length > 0) {
        primary.summary = [primary.summary?.trim(), ...extras].filter(Boolean).join(' ');
      }
      // 日期取最早
      const dates = group.map((g) => g.event_date).filter(Boolean).sort() as string[];
      if (dates.length > 0) primary.event_date = dates[0];
      // expires_on 取最晚（活动档期延展）
      const exps = group.map((g) => g.expires_on).filter(Boolean).sort() as string[];
      if (exps.length > 0 && !primary.expires_on) primary.expires_on = exps[exps.length - 1];
      out.push(primary);
    }
  }
  return out.sort((a, b) => (b.event_date || '').localeCompare(a.event_date || ''));
}

function fmtShort(d?: string) {
  if (!d) return '';
  const [, mm, dd] = d.split('-');
  return `${Number(mm)}/${Number(dd)}`;
}

export default function FeedSection() {
  const [events, setEvents] = useState<FeedEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeFilters, setActiveFilters] = useState<Set<FilterKey>>(new Set<FilterKey>(['all']));
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  const [selected, setSelected] = useState<FeedEvent | null>(null);

  useEffect(() => {
    (async () => {
      // 直接查 food_events 以拿到 expires_on / sources（v_feed_recent 视图未暴露）
      const { data, error } = await supabase
        .from('food_events')
        .select('*')
        .order('event_date', { ascending: false })
        .limit(100);
      if (!error && data) {
        const deduped = dedup(data as FeedEvent[]);
        // 批量补餐厅名
        const ids = new Set<number>();
        deduped.forEach((e) => {
          if (e.restaurant_id) ids.add(e.restaurant_id);
          if (e.related_restaurant_id) ids.add(e.related_restaurant_id);
        });
        const nameMap: Record<number, string> = {};
        if (ids.size > 0) {
          const { data: rests } = await supabase
            .from('restaurants')
            .select('id,name')
            .in('id', Array.from(ids));
          (rests || []).forEach((r: any) => { nameMap[r.id] = r.name; });
        }
        deduped.forEach((e) => {
          if (e.restaurant_id) e.restaurant_name = nameMap[e.restaurant_id];
          if (e.related_restaurant_id) e.related_restaurant_name = nameMap[e.related_restaurant_id];
        });
        setEvents(deduped);
      }
      setLoading(false);
    })();
  }, []);

  const filtered = useMemo(() => {
    const keys = Array.from(activeFilters).filter((k) => k !== 'all');
    if (keys.length === 0) return events;
    return events.filter((e) => keys.some((k) => matchFilter(e, k)));
  }, [events, activeFilters]);

  const visible = filtered.slice(0, visibleCount);

  const toggleFilter = (key: FilterKey) => {
    setVisibleCount(PAGE_SIZE);
    setActiveFilters((prev) => {
      const next: Set<FilterKey> = new Set(prev);
      if (key === 'all') {
        next.clear(); next.add('all');
        return next;
      }
      next.delete('all');
      if (next.has(key)) next.delete(key);
      else next.add(key);
      if (next.size === 0) next.add('all');
      return next;
    });
  };

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
      <div className="flex items-end justify-between mb-6">
        <div>
          <div className="kicker text-terracotta mb-2">WHAT'S NEW / 美食动态</div>
          <h2 className="serif text-3xl font-light">最近<span className="italic text-terracotta">动向</span></h2>
        </div>
        <p className="kicker text-mocha-faint hidden sm:block">点击卡片查看详情 · 来源可溯</p>
      </div>

      {/* 筛选标签栏 */}
      <div className="flex items-center gap-2 overflow-x-auto pb-2 -mx-1 px-1 mb-6">
        {FILTERS.map((f) => {
          const on = activeFilters.has(f.key);
          const count = f.key === 'all' ? events.length : events.filter((e) => matchFilter(e, f.key)).length;
          return (
            <button
              key={f.key}
              onClick={() => toggleFilter(f.key)}
              data-on={on}
              className="flag flex-shrink-0"
            >
              <span>{f.label}</span>
              <span className="n">{count}</span>
            </button>
          );
        })}
      </div>

      <div className="relative">
        <span className="absolute left-[7px] top-2 bottom-2 w-px bg-line" aria-hidden />
        <div className="space-y-2">
          {visible.map((e) => {
            const meta = CAT_META[e.category] || DEFAULT_META;
            const isActivity = ACTIVITY_CATS.has(e.category);
            return (
              <div key={e.id} className="relative pl-8 py-3 pr-3 rounded-2xl transition hover:bg-white cursor-pointer" onClick={() => setSelected(e)}>
                <span className={`absolute left-[3px] top-[22px] w-[9px] h-[9px] rounded-full ring-4 ring-cream-100 ${meta.dot}`} />
                <div className="flex items-center gap-3 mb-1.5 flex-wrap">
                  <span className={`text-[11px] font-medium px-2.5 py-0.5 rounded-full ${meta.cls}`}>{meta.label}</span>
                  {e.status === 'rumor' && (
                    <span className="text-[11px] px-2 py-0.5 rounded-full border border-dashed border-mocha-faint text-mocha-faint">传闻</span>
                  )}
                  {e.confidence === 'low' && <span className="text-[11px] text-mocha-faint">待证实</span>}
                  {e.mergedIds && e.mergedIds.length > 0 && (
                    <span className="text-[11px] text-moss">已合并 {e.mergedIds.length + 1} 条</span>
                  )}
                  <span className="numeral text-xs text-mocha-faint ml-auto flex-shrink-0">{fmtShort(e.event_date)}</span>
                </div>
                <h3 className="text-[15px] font-medium text-mocha group-hover:text-terracotta transition leading-snug">{e.title}</h3>
                {e.summary && <p className="text-[13px] text-mocha-faint mt-1 line-clamp-2 leading-relaxed">{e.summary}</p>}
                <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                  {e.district && <span className="kicker text-mocha-faint">{e.district}</span>}
                  {isActivity && (
                    <span className="text-[11px] text-terracotta-deep bg-terracotta-light/40 px-2 py-0.5 rounded-full">
                      {fmtShort(e.event_date)} 起{e.expires_on ? ` · 至 ${fmtShort(e.expires_on)}` : ''}
                    </span>
                  )}
                  <span className="kicker text-terracotta ml-auto">详情 →</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {visible.length === 0 && (
        <div className="text-center py-10 text-sm text-mocha-faint">该分类下暂无动态</div>
      )}

      {filtered.length > visible.length && (
        <div className="mt-6 text-center">
          <button onClick={() => setVisibleCount((c) => c + PAGE_SIZE)} className="btn btn-outline">
            加载更多（剩余 {filtered.length - visible.length} 条）
          </button>
        </div>
      )}

      {selected && <EventModal event={selected} onClose={() => setSelected(null)} />}
    </section>
  );
}
