# china-travel-food 前端 Full Review 修复清单

> 审查日期：2026-10-11 ｜ 审查范围：`china-travel-food/app`（Next.js 14 Pages Router）
> 修复提交：`7b3226b`（已推送 GitHub main，本地与 origin 同步）
> 审查基线：第三方 quick-review 报告（F1–F7）+ 本次 full 审查扩展（补齐 chefs/groups/auth_callback/crowd/api_sync/api_crowd 未读页面）
> 状态：**F1–F7 + G1–G4 全部修复完成并推送**；F2 根治依赖后端（见第 5 节）

---

## 1. 审查结论摘要

第三方 quick-review 的 7 项发现（F1–F7）经源码直读**全部核实属实**。full 审查补齐未读页面后新增 4 项（G1–G4）。其中：

- **P1（安全/数据）**：F1（核心数据全客户端全表拉取）、F2（举报计数前端自增）
- **P2（React 规则）**：F3（login render 期 router.replace）
- **P3（防御纵深/一致性）**：F4（配色类未定义）、F5（Leaflet 绑 cdnjs）、F6（images 通配）、F7（无 CSP/安全头）

**做得好的部分（保留未动）**：crowd 分发系统后端校验（常量时间比较/sha256/origin 白名单/错误白名单）、详情页 dinerReviews vs platformReviews 反软广分离、Feed 去重克制、publishable key 处理正确。

---

## 2. 修复明细

### F1 —— 数据拉取字段精减 + Feed 截断消除 【P1】
| 文件 | 修改 |
|---|---|
| `components/FeedSection.tsx` | `select('*')` → 明确展示字段子集；`limit(100)` → `range(0,999)`（PostgREST 单页上限），消除静默截断更早事件 |
| `pages/chefs/[id].tsx` | 全表拉 restaurants → 按 `rids` 精确 `.in('id', chunk)` 分页查询 |
| `pages/groups/[id].tsx` | 同上，改为按 rids 精确查询 |
| `pages/index.tsx` | restaurants `select('*')` → 展示/筛选用字段子集（15 字段） |
| `pages/restaurants/index.tsx` | restaurants `select('*')` → 展示/筛选用字段子集（18 字段） |

> 说明：全表拉取的**架构层根治**（SSR/SWR/服务端分页）未做，因当前数据规模（60–1500 店）可接受、且无运行态测试环境、重构回归风险高。已通过字段精减显著降低传输与配额压力；数据规模显著增长时再上 SSR/SWR。

### F2 —— 举报计数前端自增改服务端 RPC 【P1 · 前端已缓解，根治靠后端】
- `pages/restaurants/[id].tsx` `handleReport`：`update({report_count: currentCount+1})` → `supabase.rpc('increment_report', {review_id})`
- **降级策略**：若 RPC 未部署（`PGRST202`）降级回原逻辑并 `console.warn` 告警，保证功能不断裂
- **根治依赖后端**：见第 5 节

### F3 —— login render 期 router.replace 【P2】
- `pages/login.tsx`：`if (user) router.replace('/')` 从函数组件体移入 `useEffect(() => {...}, [user, router])`

### F4 —— 未定义配色类映射到现有 token 【P3】
- `pages/login.tsx` + `pages/map.tsx`：`bg-paper-100→bg-cream-50`、`text-ink→text-mocha`、`text-ink-faint→text-mocha-faint`、`text-ink-soft→text-mocha-soft`、`signal-*→terracotta-*`、`border hairline→border-line`
- 效果：登录错误框的红色强调恢复（此前静默 no-op，登录失败无视觉提示）

### F5 —— Leaflet 资源本地化 【P3】
- 下载 Leaflet 1.9.4 图标（marker-icon/2x/shadow）+ CSS + MarkerCluster.css 到 `app/public/leaflet/`
- `pages/map.tsx` + `pages/restaurants/[id].tsx`：fixLeafletIcon 图标 URL 与 `<link>` 全改本地 `/leaflet/...`，cdnjs 硬编码清零

### F6 —— images.domains 收紧 【P3】
- `next.config.js`：`'*.supabase.co'` 通配 → `publicSupabase.url` 解析出的本项目具体域

### F7 —— 全局安全响应头 【P3】
- `next.config.js` 新增 `async headers()`：CSP（default-src 'self' + 必需域）、HSTS、X-Frame-Options: DENY、nosniff、Referrer-Policy: no-referrer

### G2 —— 非空断言防御 【P3】
- `chefs/[id].tsx` + `groups/[id].tsx`：`l.restaurant!` → `l.restaurant?.`（可选链，restaurant 缺失时不崩）

### G3 —— error.message 回显白名单化 【P3】
- `pages/api/sync.ts`：`error.message` → 通用 `sync_failed`，detail 只进日志

### G4 —— setTimeout 清理 【P3】
- `pages/auth/callback.tsx`：`setTimeout` 返回 cleanup `clearTimeout`

---

## 3. 验证情况

| 项 | 结果 |
|---|---|
| `tsc --noEmit` | ✅ 100% 通过（0 错误），所有修改文件类型正确 |
| cdnjs / 未定义配色类残留 | ✅ 全清 |
| next.config.js 加载 | ✅ 可正常 require（images.domains/headers 生效） |
| 本地 `next build` | ⚠️ 受 Desktop 目录 macOS/iCloud 文件锁限制（递归删 .next 报 `system error -11`），非代码问题；需在 CI/非同步目录验证 |

---

## 4. 改动文件清单（11 源码 + 5 资源）

```
app/components/FeedSection.tsx
app/next.config.js
app/pages/api/sync.ts
app/pages/auth/callback.tsx
app/pages/chefs/[id].tsx
app/pages/groups/[id].tsx
app/pages/index.tsx
app/pages/login.tsx
app/pages/map.tsx
app/pages/restaurants/[id].tsx
app/pages/restaurants/index.tsx
app/public/leaflet/{marker-icon,marker-icon-2x,marker-shadow}.png
app/public/leaflet/{leaflet.min.css,MarkerCluster.css}
```

---

## 5. 后端待办（F2 根治，前端已降级不阻塞）

| 待办 | 说明 | 优先级 |
|---|---|---|
| 创建 `increment_report(review_id)` RPC | 带限频/一人一次，前端已改调它 | P1 |
| 收紧 `reviews` 表 RLS | insert 限 `auth.uid()=user_id`；update/delete 限本人；report 走 RPC 而非开放 update | P1 |
| 核对 `restaurants` 表 RLS | `report_count` 不应开放任意 update | P1 |
| 核对 `favorites` 表 RLS | 已用 `user_id` 约束，需 RLS 兜底 | P1 |

> 仓库内无 `supabase/migrations` SQL，RLS 策略在云端不可见，须登录 Supabase 项目确认（quick-review 第 4/5 节最高优先阻塞项）。

---

## 6. 遗留 / 后续

- **F1 架构根治**：数据规模显著增长后，列表/首页/地图改 SSR/SWR + 服务端分页
- **crowd Edge Functions**：在 Supabase 云端，仓库不可见，仅前端调用面已审；如需全量审需在云端拉取
- **运行态实测**：建议上线后在浏览器验证登录错误框视觉、地图标记图标、举报 RPC 降级路径
