import { useEffect } from 'react';
import { FeedEvent } from '@/lib/supabase';

// 与 FeedSection 保持一致的分类元数据（单例导出，避免两处漂移）
export const CAT_META: Record<string, { label: string; cls: string; dot: string }> = {
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
export const DEFAULT_META = { label: '美食动态', cls: 'bg-cream-200 text-mocha border border-line', dot: 'bg-mocha-faint' };

export const ACTIVITY_CATS = new Set(['popup', 'guest_kitchen', 'collaboration']);

/** 解析 sources 字段（可能是 JSON 串、数组或 null）→ string[] */
export function parseSources(s?: string | string[] | null): string[] {
  if (!s) return [];
  if (Array.isArray(s)) return s.filter((x): x is string => typeof x === 'string' && !!x.trim());
  const t = String(s).trim();
  if (!t) return [];
  if (t.startsWith('[')) {
    try {
      const arr = JSON.parse(t);
      if (Array.isArray(arr)) return arr.filter((x): x is string => typeof x === 'string' && !!x.trim());
    } catch { /* fallthrough */ }
  }
  return [t];
}

function fmtFull(d?: string | null) {
  if (!d) return '';
  const [y, m, dd] = d.split('-');
  return `${y}年${Number(m)}月${Number(dd)}日`;
}

export default function EventModal({ event, onClose }: { event: FeedEvent; onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', onKey);
      document.body.style.overflow = '';
    };
  }, [onClose]);

  const meta = CAT_META[event.category] || DEFAULT_META;
  const rid = event.restaurant_id || event.related_restaurant_id;
  const rname = event.restaurant_name || (event.restaurant_id ? undefined : event.related_restaurant_name);
  const sources = parseSources(event.sources);
  const isActivity = ACTIVITY_CATS.has(event.category);
  const bookingUrl = event.registration_url;
  const bookingInfo = event.registration_info;

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center p-4 sm:p-6"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
    >
      <div className="absolute inset-0 bg-mocha/45 backdrop-blur-sm" />
      <div
        className="relative w-full max-w-lg bg-cream-50 rounded-2xl shadow-lift border border-line max-h-[86vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 顶部色条 */}
        <div className={`h-1.5 w-full ${meta.dot}`} />
        <button
          onClick={onClose}
          aria-label="关闭"
          className="absolute top-4 right-4 w-8 h-8 rounded-full bg-white border border-line text-mocha-soft hover:text-terracotta hover:border-terracotta transition flex items-center justify-center text-sm"
        >
          ✕
        </button>

        <div className="p-7 sm:p-8">
          {/* 标签行 */}
          <div className="flex items-center gap-2 mb-4 flex-wrap">
            <span className={`text-[11px] font-medium px-2.5 py-0.5 rounded-full ${meta.cls}`}>{meta.label}</span>
            {event.status === 'rumor' && (
              <span className="text-[11px] px-2 py-0.5 rounded-full border border-dashed border-mocha-faint text-mocha-faint">传闻待证实</span>
            )}
            {event.confidence === 'low' && <span className="text-[11px] text-mocha-faint">低置信</span>}
            {event.district && <span className="kicker text-mocha-faint ml-auto">{event.district}</span>}
          </div>

          {/* 标题 */}
          <h3 className="serif text-2xl font-medium leading-snug text-mocha mb-4">{event.title}</h3>

          {/* 日期 / 活动档期 */}
          <div className="flex flex-wrap items-center gap-x-5 gap-y-1.5 mb-5 text-sm">
            {event.event_date && (
              <span className="text-mocha-soft">
                <span className="kicker text-mocha-faint mr-1.5">发生</span>{fmtFull(event.event_date)}
              </span>
            )}
            {isActivity && event.expires_on && (
              <span className="text-terracotta-deep">
                <span className="kicker text-mocha-faint mr-1.5">档期</span>
                {fmtFull(event.event_date)} 起 至 {fmtFull(event.expires_on)}
              </span>
            )}
          </div>

          {/* 完整 summary */}
          {event.summary && (
            <p className="text-sm text-mocha-soft leading-relaxed whitespace-pre-line mb-5">{event.summary}</p>
          )}

          {/* 报名入口（活动类） */}
          {isActivity && (
            <div className="mb-5 p-4 bg-moss-light/50 border border-moss/20 rounded-xl">
              <div className="kicker text-moss-deep mb-1.5">RESERVATION / 参与方式</div>
              {bookingUrl ? (
                <a href={bookingUrl} target="_blank" rel="noopener noreferrer" className="text-sm text-terracotta hover:underline break-all">
                  → {bookingUrl}
                </a>
              ) : bookingInfo ? (
                <p className="text-sm text-mocha-soft">{bookingInfo}</p>
              ) : (
                <p className="text-sm text-mocha-soft">需电话 / 私信预约，以餐厅官方渠道为准</p>
              )}
            </div>
          )}

          {/* 关联餐厅 */}
          {rid && (
            <div className="mb-5 flex items-center justify-between gap-4 p-4 bg-white border border-line rounded-xl">
              <div>
                <div className="kicker text-mocha-faint mb-1">RELATED / 关联餐厅</div>
                <div className="serif text-base font-medium text-mocha">{rname || `#${rid}`}</div>
              </div>
              <a href={`/restaurants/${rid}`} target="_blank" rel="noopener noreferrer" className="btn btn-primary !py-2 !px-4 !text-xs flex-shrink-0">
                查看餐厅 →
              </a>
            </div>
          )}

          {/* 关联主厨 */}
          {event.chef_name && (
            <div className="mb-5">
              <span className="kicker text-mocha-faint mr-2">主厨</span>
              <span className="text-sm text-mocha-soft">{event.chef_name}</span>
            </div>
          )}

          {/* 来源 */}
          {sources.length > 0 && (
            <div className="pt-4 border-t border-line">
              <div className="kicker text-mocha-faint mb-2">SOURCES / 信息来源</div>
              <ul className="space-y-1">
                {sources.map((u, i) => (
                  <li key={i}>
                    <a href={u} target="_blank" rel="noopener noreferrer" className="text-xs text-terracotta hover:underline break-all">
                      {u}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
