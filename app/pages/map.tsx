import { useEffect, useState } from 'react';
import dynamic from 'next/dynamic';
import Link from 'next/link';
import Head from 'next/head';
import { supabase, Restaurant } from '@/lib/supabase';

// 动态导入 Leaflet 组件，禁用 SSR（Leaflet 依赖 window）
const MapContainer = dynamic(() => import('react-leaflet').then(m => m.MapContainer), { ssr: false });
const TileLayer = dynamic(() => import('react-leaflet').then(m => m.TileLayer), { ssr: false });
const Marker = dynamic(() => import('react-leaflet').then(m => m.Marker), { ssr: false });
const Popup = dynamic(() => import('react-leaflet').then(m => m.Popup), { ssr: false });

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

// 已知餐厅的近似坐标
const KNOWN_COORDS: Record<string, [number, number]> = {
  '晴川sushi（午市）': [31.2450, 121.4480],
  '鮨水月（午市）': [31.2350, 121.5200],
  '岩田割烹鮨': [31.1900, 121.3800],
  'Sushi Oyama 鮨大山': [31.2150, 121.4650],
  '吉兆 KITCHO': [31.2250, 121.4450],
  '披头士烧鸟居酒屋': [31.2400, 121.5700],
  '宫鸠（华山路）': [31.2150, 121.4350],
  '海宫': [31.2250, 121.4500],
  '炉端一番': [31.2280, 121.4520],
  '金宗咖喱': [31.2500, 121.3500],
  '伽喱博士 Dr.CURRY': [31.2050, 121.4400],
  '一风堂': [31.2350, 121.5050],
  '满吉': [31.2200, 121.4400],
  '哲平鳗满': [31.2350, 121.5200],
  '鳗重': [31.2200, 121.4350],
  '大志/king大志': [31.2150, 121.4100],
  '三川烧肉Mikawa': [31.2150, 121.4600],
  'AJIYA味屋': [31.2150, 121.4450],
  'motoya寿喜烧': [31.1900, 121.3800],
  '日和寿喜烧': [31.2100, 121.4000],
  '大牛寿喜烧（自助顶配）': [31.2300, 121.4700],
  '山茶花铁板烧': [31.2150, 121.4550],
  '天吉': [31.2200, 121.4500],
  '天天天妇罗': [31.2500, 121.5200],
  '丸龟制面': [31.2800, 121.5700],
  '平成屋': [31.2250, 121.4500],
  '咕咕': [31.1950, 121.3850],
  '尚膳天焱': [31.2200, 121.4100],
  '小景门（仇师傅）': [31.2300, 121.4600],
  '御千代（王雷师傅）': [31.2150, 121.4200],
  '酉町·烧鸟专门店': [31.2100, 121.4300],
  '板前炉端烧omakase': [31.2250, 121.4500],
  '流心鳗鱼饭': [31.2200, 121.4500],
  '晚餐馆咖喱饭': [31.1950, 121.3850],
  '环七·土佐子': [31.2250, 121.4500],
  '特制厚切猪排咖喱蛋包饭': [31.2200, 121.4500],
  '一滨炸猪排': [31.2200, 121.4500],
  '池袋背脂拉面套餐': [31.2200, 121.4500],
  '竿屋': [31.2200, 121.4500],
  '天嘉': [31.2200, 121.4500],
  // 中餐头部餐厅近似坐标
  '鲁采LU STYLE(环宇荟店)': [31.2200, 121.4700],
  '南兴园': [31.2150, 121.4550],
  '利苑(国金中心店)': [31.2350, 121.5050],
  '遇外滩': [31.2400, 121.4900],
  '甬府(锦江饭店店)': [31.2150, 121.4650],
  '湘翁': [31.2500, 121.4900],
  '皖宴(龙柏饭店店)': [31.1900, 121.3800],
  '逸道(外滩源店)': [31.2400, 121.4850],
};

export default function MapPage() {
  const [restaurants, setRestaurants] = useState<Restaurant[]>([]);
  const [loading, setLoading] = useState(true);
  const [iconFixed, setIconFixed] = useState(false);

  useEffect(() => {
    fixLeafletIcon();
    setIconFixed(true);
    async function load() {
      const { data } = await supabase.from('restaurants').select('*').order('name');
      setRestaurants(data || []);
      setLoading(false);
    }
    load();
  }, []);

  const restaurantsWithCoords = restaurants.filter(r => KNOWN_COORDS[r.name]);

  return (
    <div className="min-h-screen bg-gray-50">
      <Head>
        <title>地图 · China Travel</title>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css" />
      </Head>

      <nav className="bg-white border-b sticky top-0 z-[1000]">
        <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
          <Link href="/" className="font-bold text-lg text-primary-700">← 首页</Link>
          <span className="text-gray-600 text-sm">
            {restaurantsWithCoords.length} / {restaurants.length} 家已定位
          </span>
        </div>
      </nav>

      <div className="h-[calc(100vh-57px)]">
        {iconFixed && !loading && (
          <MapContainer
            center={SHANGHAI_CENTER}
            zoom={12}
            style={{ height: '100%', width: '100%' }}
          >
            <TileLayer
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />
            {restaurantsWithCoords.map((r) => (
              <Marker key={r.id} position={KNOWN_COORDS[r.name]}>
                <Popup>
                  <div className="min-w-[160px]">
                    <h3 className="font-bold text-sm">{r.name}</h3>
                    <p className="text-xs text-gray-500 mt-1">
                      {r.tier} · ¥{r.price_avg || '?'}/人
                    </p>
                    {r.address && <p className="text-xs text-gray-400 mt-1">{r.address}</p>}
                    <Link
                      href={`/restaurants/${r.id}`}
                      className="text-xs text-primary-600 hover:underline mt-2 inline-block"
                    >
                      查看详情 →
                    </Link>
                  </div>
                </Popup>
              </Marker>
            ))}
          </MapContainer>
        )}
        {loading && <div className="p-8 text-gray-400 text-center">加载地图中...</div>}
      </div>

      <div className="fixed bottom-4 left-4 bg-white/90 backdrop-blur rounded-lg px-3 py-2 text-xs text-gray-500 shadow z-[1000]">
        坐标为近似值，后续将通过地址解析精确化
      </div>
    </div>
  );
}
