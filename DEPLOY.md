# 部署教程 · Vercel

## 前置准备

- [ ] GitHub 账号
- [ ] Vercel 账号（可用 GitHub 登录）
- [ ] Supabase 项目已创建，schema 已执行
- [ ] 飞书表格数据已同步到 Supabase

## 第一步：推送到 GitHub

```bash
cd china-travel-food/app

# 初始化 git（如果还没有）
git init
git add .
git commit -m "init: china travel food map"

# 在 GitHub 创建新仓库，然后推送
git remote add origin https://github.com/<your-username>/china-travel-food.git
git branch -M main
git push -u origin main
```

**重要**: 确保 `.env.local` 在 `.gitignore` 中（不要提交密钥）。

## 第二步：在 Vercel 导入项目

1. 打开 https://vercel.com/new
2. 选择刚才推送的 GitHub 仓库
3. 配置项目：
   - **Framework Preset**: Next.js
   - **Root Directory**: `app`（如果 package.json 在 app 子目录下）
   - **Build Command**: `next build`
   - **Output Directory**: `.next`

## 第三步：配置环境变量

在 Vercel 项目设置 → Environment Variables 中添加：

| 变量名 | 值 | 环境 |
|--------|-----|------|
| `NEXT_PUBLIC_SUPABASE_URL` | `https://xxx.supabase.co` | Production + Preview |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | `eyJ...`（anon key） | Production + Preview |

> 注意：`SUPABASE_SERVICE_ROLE_KEY` 不需要配置在前端，它只用于数据同步脚本。

## 第四步：部署

点击 "Deploy"，等待 1-2 分钟。部署完成后会得到一个 `https://xxx.vercel.app` 的域名。

## 第五步：配置定时数据同步

### 方案 A：Vercel Cron（推荐）

在 `app/` 目录下创建 `vercel.json`：

```json
{
  "crons": [
    {
      "path": "/api/sync",
      "schedule": "0 3 * * *"
    }
  ]
}
```

然后创建 `app/pages/api/sync.ts` API 路由，调用同步逻辑。

### 方案 B：GitHub Actions

在 `.github/workflows/sync.yml` 中配置每天凌晨运行同步脚本。

### 方案 C：本地手动同步

```bash
python3 scripts/sync_feishu_to_supabase.py --full
```

## 第六步：绑定自定义域名（可选）

Vercel 项目设置 → Domains → 添加自定义域名 → 按提示配置 DNS。

## 常见问题

### Q: 部署后页面空白或数据不显示？
A: 检查环境变量是否正确配置，特别是 `NEXT_PUBLIC_` 前缀。在浏览器控制台检查是否有 Supabase 相关错误。

### Q: Hydration 错误？
A: 避免在组件渲染时直接使用 `Date.now()`、`Math.random()`、`window` 等浏览器端 API。这些应该放在 `useEffect` 或 `useState` 的初始化函数中。

### Q: 如何更新数据？
A: 在飞书表格中编辑数据，然后运行同步脚本。同步脚本基于飞书 revision 号做增量判断。

### Q: 如何添加新餐厅？
A: 在飞书表格的"01 档次推荐"表中添加新行，然后运行同步脚本。确保 `status` 列设为"推荐"才会在首页显示。
