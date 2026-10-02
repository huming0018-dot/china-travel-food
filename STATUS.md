# 当前状态 · STATUS

> 最后更新：2026-10-02 23:20（PM窗口 · 回流tracking报告上线 + Lean Refactor）
> **✅ 回流 tracking 报告上线（2026-10-02 深夜）**：`cloud/crowd_tracking.py` —— 每小时从库实时聚合 crowd_proofs/participants/tasks → 人类可读报告（任务池进度/回流有效·去重·拒收/近24h增量/参与者活跃Top）→ JSONL 落盘（`.data/crowd_tracking.jsonl` 可回溯）→ notifier.info 柔和推送（cadence 3600 不刷屏）。服务器 cron 已挂载（`7 * * * *`），直连 Supabase 已验证推送成功（report #1 已发 TG+飞书）。安全测试 T1-T7 全过（None/恶意输入/超长/除零/缺字段/落盘失败）。Lean Refactor 审计文档：`cloud/CODE_AUDIT_V1/V2/V3_20261002.md`。commit `356c962`。
> **✅ 红队对抗加固完成（2026-10-02 深夜）**：以投机者身份实测攻击 10 类向量（一机一号/URL白名单绕过/垃圾灌库/任务DoS/去重绕过/伪评分/时间伪造/并发竞态/幂等绕过/评分去重混淆）→ 全部修复并回归验证。核心：报名强制 device_salt + 同设备唯一索引（一机一号闭环）；URL 严格正则（仅 `www.xiaohongshu.com/explore/[0-9a-f]{24}`）；note_id 强制 24hex；评分锚定已收录笔记；captured_at 时间窗；参与者行锁防并发超配额；循环内任务状态复查防刷满；dedupe 升级（note 全局 title 归一 / rating 按参与者+笔记）；拒收率>0.6 自动 suspend。报告：`cloud/REDTEAM_REPORT.md`。commit `0132590`，服务器已同步。
> **✅ 自动续领上线（2026-10-02 晚）**：修复「回传后不领新任务」bug——插件端关键词轮转+按关键词累计accepted判定完成+完成自动归档续领；服务端 fetch_tasks 支持 exclude_task_ids（排除已完成包）；popup 新增关键词进度条（可视化）。端到端验证：报名→领#1→排除#1→自动切#2 ✅。线上插件已更新（25KB）。
> **✅ 报名页已托管上线（2026-10-02 晚）**：Supabase Storage public bucket `crowd`，公网可直接访问：
> - 📄 报名页：`https://bdwrhshgdeghgyzwpxnl.supabase.co/storage/v1/object/public/crowd/apply.html`
> - 📦 插件下载：`https://bdwrhshgdeghgyzwpxnl.supabase.co/storage/v1/object/public/crowd/crowd-extension-v2.0.0.zip`
> - 在线报名即得 TMP 编号 → 下载插件（同目录相对路径自动关联）；anon 上传策略已配置
> **✅ 任务包扩容机制上线（2026-10-02 晚）**：`cloud/crowd_scale.py`（seed/db/fill 三源 → 过滤 → 库内+已发布双重去重 → 评分降序 → 切包发布）；机制文档 `CROWD_SCALE.md`。已扩容：奢华档 94 家未覆盖店 → 16 个新包。**当前共 45 个 open 任务包，覆盖 254 家未收录店铺**。扩容后安全回归 R1-R7 全绿。
> **🔑 凭证总表**：明文在 `~/.food_atlas_credentials.md`（权限600）；HANDOFF.md 顶部「凭证与登录信息索引」。

## 🚀 众包采集上线 · 傻瓜式三步（2026-10-02，PM 已跑通）

### 第1步：发插件给参与者
1. `cd /Users/deuce/Doubao/chats/2026-09-29/new-chat/china-travel-food/crowd_extension`
2. 打开 `src/background.js` 顶部，把 `CROWD_API_BASE` / `CROWD_API_KEY` 换成真实值（anon key 在 `~/.food_atlas_credentials.md`）
3. Chrome → `chrome://extensions` → 右上角开「开发者模式」→ 「加载已解压的扩展程序」→ 选 `crowd_extension/` 目录
4. 参与者打开插件选项页（扩展详情→扩展程序选项），读协议、填 **P- 开头正式编号**（需先报名审核）

### 第2步：报名入口（让参与者自己报名）
1. 打开 `crowd_extension/apply.html`，把文件里 `REPLACE_WITH_SUPABASE_ANON_KEY` 换成 anon key（同上）
2. 用任意方式给参与者看这个页面（本地打开/发给别人/放静态托管都行）
3. 参与者填昵称+联系方式提交 → 得到 **TMP-** 报名编号

### 第3步：审核发编号（PM 操作，一条命令）
```bash
cd /Users/deuce/Doubao/chats/2026-09-29/new-chat/china-travel-food
export HTTPS_PROXY=http://127.0.0.1:7897 && export FOOD_APP_DIR="$(pwd)/app"
python3 cloud/crowd_admin.py list --status pending        # 看待审报名
python3 cloud/crowd_admin.py approve TMP-XXXXXX --quota 20 # 批准，发放 P- 编号
python3 cloud/crowd_admin.py stats                          # 看全局状态
```
把 **P- 编号**发给参与者 → 插件里填上 → 自动开始采集。

### 任务包已就绪（正式表 crowd_tasks）
- #1：新荣记/荣小馆/利苑/西塔老太太/甬府/外滩壹号（6店）
- #2：雍福会/福1015/逸龙阁（3店）
- 插件拉取→采集→回传→ingest校验→落库→进度回写，全链路已端到端验证通过

---
> **🌙 夜间执行报告（06:00）**：工单37 | todo 22 | 进行中 6 | done 9。
> - ✅ **整夜完成9项**：dev三组件(#11/#12/#13)+Apify开发侧(#15)+搜索校准(#28)；collector证据机制(#24/#25)
> - 🔄 **进行中6项**：#1 Apify实跑 / #9 SSH / #23 舰队catchup / #27 findings / #29 三段式cron / **#44 Apify方案(新认领)**
> - ⏳ **待唤醒22项**：P0 #14 SOP/#26 方舟key 待认领；用户点名P1 #32-38/#45(collector) #36/#37/#39-43(dev)
> - 📊 调度器整夜正常：多次4/13条批量认领提醒，账本控制不刷屏；notifier TG+飞书已送达
> - 🔴 **今晨重点：#44 Apify耗速方案已认领执行**（2天烧$39.95铁证，part3_apify_cost_plan.md止血措施）
> **✅ 夜间执行计划已部署（2026-10-01 23:46，用户已审阅确认）**：
> - 3个定时任务已创建：00:00夜间盘点 / 02:00二次盘点 / 06:00夜间执行报告（TG+飞书推送）
> - C类12项窗口执行指令已写入 INBOX/collector.md + INBOX/dev.md（窗口唤醒即执行）
> - PM调度器（pm_dispatch.py + launchd 每15分钟）持续运行：P0/用户点名未认领自动推送+有界提醒
> - 用户入睡，夜间由PM自动调度监督；07:30后窗口执行，早间验收
> **✅ PM主动调度器上线（2026-10-01晚）**：`cloud/pm_dispatch.py` + launchd每15分钟自动扫描task_queue，发现P0/用户点名工单超SLA未认领 → 自动推送TG+飞书（已验证TG+飞书双通道真实送达）+写INBOX双保险。**用户无需去窗口喊话**，PM系统自动调度唤醒窗口。见 ROLE_SYNC.md「提醒机制」。
> **✅ Apify已充值成功+限额解锁（2026-10-01晚）**：Starter $19/月已生效（预付$19额度+64GB RAM/32并发/30数据中心代理/Bronze折扣），Mastercard 4395已绑定Primary。**平台限额已从$19调到$40（Update successful已验证）**：$19超额空间按量自动扣卡（$0.20/CU，超额达$20提前结算），opspilot 402已解除，采集可端到端实跑。task_queue #1 已解除blocked→todo。
> **✅ 方案B（2026-10-01）：四窗口→三窗口**：QA职责并入PM，原QA窗口停用。用户只在PM窗口说话。见 ROLE_SYNC.md / WINDOWS.md / role-task-allocation.md。
> **✅ sync.sh v3**：开工强制渲染统一状态卡（数据/任务/账号/配额+过时事实校验），三窗口看同一张卡。
> 各窗口开始工作时运行 `bash sync.sh <角色>`，结束时运行 `bash sync.sh push "说明"`
> 任务唯一真源：task_queue（Supabase）。窗口无独立待办文档。

## ⚠️ 服务器状态（2026-10-01 已查明，Q-013）
- **主机健康**：经香港节点SSH登录成功（HK_SSH_OK），sshd正常，容器food-cloud正常运行
- **真实原因**：deuce 本机运营商到腾讯IP（49.234.35.92）的直连路径/NAT 被拦（全端口refused），会自行恢复
- **作业方式**：经 Clash 代理（127.0.0.1:7897）或强制境外节点通道可正常 SSH/部署
- 影响：容器内 cron 任务暂停，需恢复后确认
- **下一步**：collector 窗口负责排查恢复；QA 跟踪状态

## 采集（CTFS_登录）
- 账号：A=cookie在服务器IP上被失效（probe=-100）/ B=parked
- 采集状态：**停摆**，已决定切换Apify云采集方案，不再用本地账号+IP
- 地图API：高德key#1正常（月配额765/4500），高德key#0月配额超限，腾讯key日配额超限（明天0点重置）
- 数据：1473家在营餐厅，电话空196家，营业时间空547家

## 开发（CTFS_开发）
- 已完成：前端P0修复、后端采集P0修复、提醒机制整顿、角色同步机制、公共状态模块、sync.sh v2
- 最近commit：1f37712（8逻辑角色→4窗口职责分配）
- 待做：由PM分配（见任务队列）
- 部署：腾讯云容器food-cloud运行中（当前SSH不可达待排查）

## QA（CTFS_QA · 本窗口）
- 问题台账：QUALITY_ISSUES.md（18条：open 7 / verifying 2 / closed 9）
- 本次完成：8逻辑角色→4窗口职责分配、task_queue归属核对修正
- 机制：qa_broadcast.py统一播报（TG唯一通道，飞书已关）
- 风险：采集停摆导致口味分无法补全（1152家空，78%）

## PM（CTFS_PM · 新增）
- 职责：项目总调度、任务分配、优先级管理、验收交付、进度推动
- 章程：`ROLE_PM.md`，职责分配：`role-task-allocation.md`
- 开工：`bash sync.sh pm`

## 任务队列（已按新分配修正归属）
| ID | 优先级 | 分配给 | 状态 | 任务 | issue |
|----|--------|--------|------|------|-------|
| 1 | P0 | **collector** | todo | Apify集成（原dev，已改） | Q-012 |
| 2 | P1 | collector | todo | 新腾讯地图key | Q-011 |
| 3 | P1 | **collector** | todo | 高德评论清理（原dev，已改） | Q-004 |
| 4 | P1 | collector | todo | frontier污染验证 | Q-010 |
| 5 | P1 | collector | todo | 口味分补全 | Q-005 |
| 8 | P1 | pm | todo | PM建立项目推进机制 | - |
| 6 | P2 | collector | todo | 营业时间补全 | Q-006 |

## 四窗口职责速览（详见 role-task-allocation.md）
- **collector** = CR爬虫 + OPS运维：信源/反爬/解析/深覆盖/质量门 + 账号/配额/IP/看门狗
- **dev** = ARCH + ALG + FE：表/迁移/部署 + 评分/算法 + 界面（冻结）
- **pm** = PM产品 + 验收口径：方向/优先级/验收/推进
- **qa** = QA测试 + 跨角色协调：A–H审计/回归/红队 + 播报/台账/机制
- **用户** = 付款/扫码/密钥/最终拍板
- **云端自动工人** = cron 19条 + 机械扫描，无人值守

## 下一步（由PM推进）
1. 【collector】排查服务器SSH不可达（P0，阻塞一切）
2. 【collector】Apify集成（P0，恢复采集的唯一路径）
3. 【collector】提供新腾讯key做轮换
4. 【pm】建立任务推进机制并分配本轮迭代
5. 【qa】Apify集成后验证采集恢复+口味分补全
