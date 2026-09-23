import { createElementObject, createLayerComponent, extendContext } from '@react-leaflet/core';
import L from 'leaflet';
// 仅引入 markercluster 主 JS（不含 CSS，CSS 由页面 <Head> 的 CDN link 加载，避免 webpack 处理 node_modules 内 CSS 报错）
import 'leaflet.markercluster';

// 聚合容器：等价于 react-leaflet 的 LayerGroup，只是内部图层换成 markerClusterGroup。
// 子 Marker 通过 extendContext 注入的 layerContainer 自动 addLayer 到聚合组。
const ClusterGroup = createLayerComponent(function createCluster(
  { children: _c, ...options }: any,
  ctx: any
) {
  const cluster = L.markerClusterGroup(options);
  return createElementObject(cluster, extendContext(ctx, { layerContainer: cluster }));
});

export default ClusterGroup;
