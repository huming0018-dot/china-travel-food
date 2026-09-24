import { useEffect, useState } from 'react';
import dynamic from 'next/dynamic';
import Link from 'next/link';
import Head from 'next/head';
import { supabase, Restaurant } from '@/lib/supabase';
import { parseLatLng } from '@/lib/geo';

// 动态导入 Leaflet 组件，禁用 SSR（Leaflet 依赖 window）
const MapContainer = dynamic(() => import('react-leaflet').then(m => m.MapContainer), { ssr: false });
const TileLayer = dynamic(() => import('react-leaflet').then(m => m.TileLayer), { ssr: false });
const Marker = dynamic(() => import('react-leaflet').then(m => m.Marker), { ssr: false });
const Popup = dynamic(() => import('react-leaflet').then(m => m.Popup), { ssr: false });
// 聚合图层（上千点位必须聚合，否则平移卡顿、远视图重叠）；本地组件，CSS 由 Head CDN 加载
const ClusterGroup = dynamic(() => import('@/components/ClusterGroup'), { ssr: false });

// 修复 Leaflet 默认图标路径
const fixLeafletIcon = () => {
  if (typeof window === 'undefined') return;
  import('leaflet').then(L => {
    delete (L.Icon.Default.prototype as any)._getIconUrl;
    L.Icon.Default.mergeOptions({
      iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon-2x.png',
      iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon.png',
      shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png',
    });
  });
};

// 上海中心坐标
const SHANGHAI_CENTER: [number, number] = [31.2304, 121.4737];

// 分页拉全（PostgREST 单页 ≤1000，必须分页，否则漏店）
async function fetchAllRestaurants(): Promise<Restaurant[]> {
  const cols = 'id,name,name_en,price_scene,price_band,price_avg,address,district,status,location';
  const step = 1000;
  let start = 0;
  const all: Restaurant[] = [];
  for (;;) {
    const { data, error } = await supabase.from('restaurants').select(cols).order('id').range(start, start + step - 1);
    if (error) throw error;
    if (!data || data.length === 0) break;
    all.push(...(data as Restaurant[]));
    if (data.length < step) break;
    start += step;
  }
  return all;
}

// 聚合点样式（按数量分级，品牌 terracotta 色系）
function clusterIcon(L: any, count: number) {
  let size = 34, bg = '#C2684A';
  if (count >= 50) { size = 48; bg = '#7A3B26'; }
  else if (count >= 10) { size = 40; bg = '#A85034'; }
  return L.divIcon({
    className: 'cluster-badge',
    iconSize: [size, size],
    html: `<div class="cb" style="width:${size}px;height:${size}px;background:${bg}">${count}</div>`,
  });
}

export default function MapPage() {
  const [points, setPoints] = useState<{ r: Restaurant; pos: [number, number] }[]>([]);
  const [activeTotal, setActiveTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [ready, setReady] = useState(false);
  const [L, setLeaflet] = useState<any>(null);

  useEffect(() => {
    fixLeafletIcon();
    setReady(true);
    import('leaflet').then(setLeaflet);
    (async () => {
      const all = await fetchAllRestaurants();
      const active = all.filter((r) => r.status !== 'closed' && r.status !== '关店');
      setActiveTotal(active.length);
      const withCoords = active
        .map((r) => ({ r, pos: parseLatLng(r.location) }))
        .filter((x): x is { r: Restaurant; pos: [number, number] } => x.pos !== null);
      setPoints(withCoords);
      setLoading(false);
    })();
  }, []);

  return (
    <div className="min-h-screen bg-paper-100">
      <Head>
        <title>地图 · China Travel</title>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css" />
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet.markercluster/1.5.3/MarkerCluster.css" />
        <style>{`
          .cluster-badge{background:none!important;border:none!important;}
          .cluster-badge .cb{display:flex;align-items:center;justify-content:center;border-radius:50%;
            color:#fff;font-weight:600;font-size:13px;border:2px solid rgba(255,255,255,.85);
            box-shadow:0 2px 8px rgba(120,60,40,.35);}
        `}</style>
      </Head>

      <header className="border-b hairline sticky top-0 z-[1000] bg-paper-100/90 backdrop-blur-sm">
        <div className="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2 text-ink hover:text-ink-soft transition">
            <span>←</span>
            <span className="serif text-base font-medium">首页</span>
          </Link>
          <span className="kicker text-ink-faint">{points.length} / {activeTotal} 家已定位</span>
        </div>
      </header>

      <div className="h-[calc(100vh-57px)]">
        {ready && !loading && L && (
          <MapContainer center={SHANGHAI_CENTER} zoom={12} style={{ height: '100%', width: '100%' }}>
            {/* 高德道路瓦片（GCJ-02，与库内火星坐标对齐；OSM 瓦片国内被墙且坐标系不符）*/}
            <TileLayer
              attribution='&copy; 高德地图 AutoNavi'
              url="https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}"
              subdomains={['1', '2', '3', '4']}
            />
            <ClusterGroup
              chunkedLoading
              maxClusterRadius={45}
              iconCreateFunction={(cluster: any) => clusterIcon(L, cluster.getChildCount())}
            >
              {points.map(({ r, pos }) => (
                <Marker key={r.id} position={pos}>
                  <Popup>
                    <div className="min-w-[160px]">
                      <h3 className="serif text-sm font-medium">{r.name}</h3>
                      <p className="text-2xs text-ink-faint mt-1 kicker">
                        {r.price_scene ? `${r.price_scene}` : ''}{r.price_avg ? ` · ¥${r.price_avg}/人` : ''}
                      </p>
                      {r.address && <p className="text-2xs text-ink-faint mt-1">{r.address}</p>}
                      <Link href={`/restaurants/${r.id}`} className="text-2xs text-ink hover:underline mt-2 inline-block kicker">
                        查看详情 →
                      </Link>
                    </div>
                  </Popup>
                </Marker>
              ))}
            </ClusterGroup>
          </MapContainer>
        )}
        {loading && <div className="p-8 text-ink-faint text-center"><div className="spinner mx-auto" /></div>}
      </div>

      <div className="fixed bottom-4 left-4 bg-white/90 backdrop-blur border hairline px-4 py-2.5 text-2xs text-ink-faint z-[1000]">
        📍 坐标基于高德/腾讯 GCJ-02，底图为高德道路图
      </div>
    </div>
  );
}
