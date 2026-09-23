// 统一坐标解析。
// 库内 restaurants.location 是 PostGIS geography(Point,4326)，PostgREST 默认返回 hex EWKB 字符串，
// supabase-js 不会自动转成 GeoJSON。因此所有用到坐标的页面（地图/详情/导航）都必须经这里解析，
// 兼容 hex EWKB / WKB、GeoJSON Point、WKT 三种形态。

// hex EWKB/WKB → [lat, lng]（仅 Point）
export function parseHexWKB(hex: string): [number, number] | null {
  try {
    const clean = hex.trim();
    const bytes = new Uint8Array(clean.length / 2);
    for (let i = 0; i < bytes.length; i++) bytes[i] = parseInt(clean.substr(i * 2, 2), 16);
    const dv = new DataView(bytes.buffer);
    const littleEndian = bytes[0] === 1;
    let off = 1;
    const type = dv.getUint32(off, littleEndian);
    off += 4;
    const hasSRID = (type & 0x20000000) !== 0;
    const gtype = type & 0x0fffffff;
    if (gtype !== 1) return null; // 非 Point
    if (hasSRID) off += 4; // 跳过 SRID
    const x = dv.getFloat64(off, littleEndian); off += 8; // lng
    const y = dv.getFloat64(off, littleEndian); // lat
    if (!Number.isFinite(x) || !Number.isFinite(y) || x === 0 || y === 0) return null;
    return [y, x];
  } catch {
    return null;
  }
}

// 统一入口 → [lat, lng]，失败返回 null
export function parseLatLng(loc: unknown): [number, number] | null {
  if (!loc) return null;
  if (typeof loc === 'object') {
    const geo = loc as { type?: string; coordinates?: number[] };
    if (geo.type === 'Point' && Array.isArray(geo.coordinates) && geo.coordinates.length >= 2) {
      const [lng, lat] = geo.coordinates;
      if (typeof lng === 'number' && typeof lat === 'number' && lng !== 0 && lat !== 0) return [lat, lng];
    }
    return null;
  }
  if (typeof loc === 'string') {
    const s = loc.trim();
    if (/^[0-9a-f]+$/i.test(s)) return parseHexWKB(s);
    const m = s.match(/POINT\s*\(\s*([-+\d.]+)\s+([-+\d.]+)\s*\)/i);
    if (m) return [parseFloat(m[2]), parseFloat(m[1])];
  }
  return null;
}

// → [lng, lat]（高德导航链接 / Leaflet 之外需要经度在前的场景）
export function parseLngLat(loc: unknown): [number, number] | null {
  const p = parseLatLng(loc);
  return p ? [p[1], p[0]] : null;
}
