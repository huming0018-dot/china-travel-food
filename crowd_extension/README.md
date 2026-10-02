# 众包采集插件（Crowd Extension）

> PM 窗口独立开发 · 2026-10-02 · 契约 CROWD-CONTRACT-001
> 上海美食图鉴「任务发放 + 众包采集」的插件载体：参与者自有账号/设备/网络，全自动采集，直接回传 Supabase。

## 目录
```
crowd_extension/
├── manifest.json          # Chrome 扩展 manifest v3
├── CROWD_CONTRACT.md      # 数据契约（格式/获取/回传/同步一致性铁律）
├── apply.html             # ⭐ 报名入口（参与者自助报名，无需预发名单）
└── src/
    ├── background.js      # Service Worker：任务拉取/管控闸门/调度/回传
    ├── content.js         # 页面注入：搜索结果/笔记详情采集
    ├── safety_engine.js   # 安全线引擎（硬编码不可调）
    ├── popup.html         # 状态面板（含参与编号/拦截原因）
    └── onboarding.html    # 知情同意书 + 正式编号填写

cloud/
├── sql/crowd_tables.sql   # ⭐ 建表SQL（5张表，Supabase SQL Editor 执行）
├── crowd_ingest.py        # 回传校验+落库+状态回写（含参与者管控闸门）
├── crowd_pack.py          # 任务包生成发布（店铺池→crowd工单）
└── crowd_admin.py         # ⭐ 管控CLI（报名审核/暂停/拉黑/统计）
```

---

## 🚀 快速启动（三步）

### ① 建表（PM 执行）
在 Supabase → SQL Editor 执行 `cloud/sql/crowd_tables.sql`（幂等，可重复执行）。建表顺序：participants → tasks → proofs → reviews → settlements。验证：`select count(*) from crowd_tasks;` 返回 0。

### ② 发布任务包（PM 执行）
```bash
export HTTPS_PROXY=http://127.0.0.1:7897 && export FOOD_APP_DIR="$(pwd)/app"
python3 cloud/crowd_pack.py --stores stores.json --pack-size 6   # 5-8店/包
```
说明：crowd_tasks 表未建时会自动回退发布为 task_queue 中 `[CROWD]` 前缀工单（assignee=pm），插件拉取端两者都兼容。

### ③ 打包插件（PM 执行）
1. `cd crowd_extension`
2. 构建时在 `background.js` 顶部替换 `CROWD_API_BASE` / `CROWD_API_KEY`（Supabase anon key 或 service_role key，最小权限）。
3. Chrome → `chrome://extensions` → 开发者模式 → 加载已解压的扩展程序 → 选择本目录。
4. 部署报名入口：将 `apply.html` 放任意静态托管（或本地打开），替换其中 `REPLACE_WITH_SUPABASE_ANON_KEY`。

---

## 📋 报名与管控机制（灵活报名闭环）

```
参与者                    PM                         服务端
  │ ① apply.html 提交报名
  ├────────────────────────────────────────▶ POST /crowd_participants (pending, TMP-编号)
  │
  │ ② 审核：crowd_admin.py approve
  │◀───────────────────────────────────────── 发放正式编号 P-XXXXXX + quota_day
  │
  │ ③ onboarding 填 P-编号，同意协议 → 插件自动拉任务
  │ ④ 采集回传 → ingest 复查 approved + 累计有效条数
  │ ⑤ 违规 → suspend/blacklist → 插件不再派任务 + 服务端拒回传
```

### 报名（参与者）
打开 `apply.html` → 填昵称/联系方式 → 提交 → 获得 **TMP-** 报名编号 → 等待 PM 审核（1-2 工作日）。

### 审核（PM 用 crowd_admin.py）
```bash
python3 cloud/crowd_admin.py list --status pending          # 看待审报名
python3 cloud/crowd_admin.py approve TMP-LX3K8A --quota 20 --note "熟人推荐"  # 批准发编号
python3 cloud/crowd_admin.py suspend P-A1B2C3 --note "拒收率超阈值"   # 暂停
python3 cloud/crowd_admin.py blacklist P-A1B2C3 --note "转借账号"     # 拉黑
python3 cloud/crowd_admin.py stats                           # 全局统计
```

### 管控规则
- **双层拦截**：插件发任务前查参与者状态；服务端回传时再查（防绕过插件直发）。
- **配额**：quota_day 审核时设定（默认20/日），安全线引擎只降不升。
- **一机一号**：device_salt 首次回传绑定，禁止多账号切换。
- **风控**：拒收率高/转借账号 → suspend；情节严重 → blacklist（不可逆）。
- **计酬**：只认 gate_status=accepted 的有效条数（笔记默认 ¥0.5、评分 ¥1.0，单价以当期公告为准，未锁定）。

---

## 数据一致性（格式/获取/回传/同步）

| 环节 | 机制 |
|---|---|
| 格式 | 契约001统一schema：信封(participant_id/task_id/proof_seq/sync_version/items)+proof字段，插件=服务端=库表逐字一致 |
| 获取 | 插件从 crowd_tasks 拉 status=open 任务包；未建表回退拉 task_queue `[CROWD]` 工单 |
| 回传 | POST /crowd/proof → crowd_ingest 校验（sync_version 不符拒/schema拒/评分空话拒/URL域名拒/note_id长度拒/参与者状态拒）→ 落 crowd_proofs → 回写 progress/total_effective |
| 同步 | task_id 原样回传 · proof_seq 幂等 · dedupe_key 防重 · 一机一号 · 断点续传 |

## 安全线（插件硬编码，不可调）

| 动作 | 阈值 |
|---|---|
| 日搜索 | ≤ quota_day（默认20，max 30） |
| 搜索间隔 | 随机 60-120s |
| 单次会话 | ≤15min 后强制冷却 30min |
| 浏览停留 | ≥30s/篇 |
| 触发"访问频繁" | 立即停 15min |
| 一机一号 | 绑定 device salt，禁止多账号切换 |

## 参与协议要点（onboarding.html 完整版）
采集范围仅限小红书**公开展示**笔记；不采集私信/设置/隐私字段；账号风险自负（限流/降权/封禁自担）；数据回传项目云端，按有效条数计酬。
