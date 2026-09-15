# China Travel · 上海美食地图

基于 Next.js + Supabase + 飞书表格的城市美食地图应用。

## 技术栈

- **前端**: Next.js 14 (Pages Router) + TypeScript + Tailwind CSS
- **数据库**: Supabase (PostgreSQL)
- **编辑源**: 飞书表格（Source of Truth）
- **数据同步**: Python 脚本（lark-cli 导出 → 清洗 → upsert）
- **部署**: Vercel
- **PWA**: 待配置（next-pwa）

## 项目结构

```
china-travel-food/
├── app/                          # Next.js 项目根目录
│   ├── pages/
│   │   ├── _app.tsx             # 全局布局
│   │   ├── index.tsx            # 首页（三维分类 + 推荐餐厅）
│   │   ├── restaurants/
│   │   │   ├── index.tsx        # 餐厅列表页
│   │   │   └── [id].tsx         # 餐厅详情页
│   │   └── map.tsx              # 按区域分布页
│   ├── lib/
│   │   └── supabase.ts          # Supabase client + 类型定义
│   ├── styles/
│   │   └── globals.css           # Tailwind 全局样式
│   ├── public/                   # 静态资源
│   ├── .env.local                # 环境变量（不提交到 git）
│   ├── next.config.js
│   ├── tailwind.config.js
│   ├── postcss.config.js
│   ├── tsconfig.json
│   └── package.json
├── db/
│   └── migrations/
│       └── 001_init.sql          # 数据库 schema（9 张表）
├── scripts/
│   └── sync_feishu_to_supabase.py  # 飞书→Supabase 数据同步脚本
└── DEPLOY.md                      # 部署教程
```

## 快速开始

### 1. 安装依赖

```bash
cd app
npm install
```

### 2. 配置环境变量

复制 `.env.local.example` 为 `.env.local`，填入：

```
NEXT_PUBLIC_SUPABASE_URL=https://xxx.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_ROLE_KEY=eyJ...
```

### 3. 初始化数据库

在 Supabase Dashboard → SQL Editor 中执行 `db/migrations/001_init.sql`。

### 4. 同步数据

```bash
cd ..
python3 scripts/sync_feishu_to_supabase.py --full
```

### 5. 启动开发服务器

```bash
cd app
npm run dev
```

访问 http://localhost:3000

## 数据库表结构

| 表名 | 说明 |
|------|------|
| `cuisines` | 三维分类字典（菜系/食材/形式） |
| `restaurants` | 餐厅核心信息（含反软广评分各维度） |
| `restaurant_cuisines` | 餐厅-分类多对多关联 |
| `reviews` | 食客点评（只计堂食） |
| `negotiations` | 议价记录 |
| `price_benchmarks` | 单品价格锚点 |
| `sync_log` | 同步日志 |
| `profiles` | 用户扩展信息 |
| `favorites` | 用户收藏 |

## 数据同步流程

```
飞书表格（编辑层）
    ↓ lark-cli 导出 CSV
Python 同步脚本（清洗 + 校验 + upsert）
    ↓
Supabase PostgreSQL（数据层）
    ↓ REST API
Next.js 前端（展示层）
```

- 全量同步：`python3 scripts/sync_feishu_to_supabase.py --full`
- 增量同步：`python3 scripts/sync_feishu_to_supabase.py`（基于飞书 revision 号）
- 试运行：加 `--dry-run` 参数

## 部署

详见 [DEPLOY.md](./DEPLOY.md)。

## 待完成

- [ ] PWA 配置（next-pwa + manifest.json + service worker）
- [ ] 用户系统（Supabase Auth + 登录/注册页）
- [ ] 交互式地图（Leaflet + PostGIS 地理坐标）
- [ ] 餐厅筛选/搜索（按品类、档位、区域）
- [ ] 议价看板页面
- [ ] Vercel Cron 定时同步
