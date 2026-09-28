# HANDOFF・上海美食图鉴（china-travel-food）交接文档

> 版本：2026-09-26 ｜ 本文档目标：让另一个 AI bot 
>
> **仅凭本文档 + 代码**
>
>  即可审阅、复现、继续推进本项目。
> 所有命令均在本机（macOS）实测过；所有数字均为当日对 Supabase 现网实测拉取。
> **严禁**
>
> 在任何提交 / 截图 / 产物中出现明文密钥；本文档只写变量名与读取位置。

- **【进度播报已上线】每 10 分钟双通道推送**：新建 `cloud/progress_broadcast.py`（只读 ledger/pool_logs/cookie_state/frontier/阻塞标记，直接调 health._telegram/_feishu_app 绕过冷却），crontab 第11条 `3,13,23,33,43,53 * * * *`（错峰）。手动执行验证 **telegram=True、feishu_app=True**；容器 /usr/sbin/cron 在跑、crontab 已安装，离线照常推。日志 /app/data/progress_broadcast.log。当前实况：account_a=dead、account_b=restricted(300011)，池待自动复检。

- **【看门狗账号自动修复已上线】**：新建 `cloud/account_repair.py` 并由 watchdog 每轮调用。修复阶梯 R0 守护/自动拉起 gap_pool；R1 签名通道复核（权威），浏览器误判 dead/restricted 但签名 code=0 → 自动改判 ok；R2 默认出口软封/失败→经广州代理换独立 IP 再探；R3 仅双出口都 -100（web_session 过期）才一次性告警叫人扫码。实测两账号此前被误标 dead/restricted，复核均 code=0，**已自动改判 ok**、pool_alive=True。状态写回 xhs_cookie_pool，router 与 progress_broadcast 随之自愈。

- **【P1 数据驱动分母已落地】poi_counts.py**：每叶子 1 次高德 text(offset=1 读 count)，多 key 轮换/断点续跑，291 叶子全采集（中位≈16、53 个=0；key#0 撞日限换 key#1 完成）。喂账本后 **supply_source 全转 poi**：供给档 scarce133/normal40/rich118，**达标 17/291=6%、未达标 274、总缺口 867**（比启发式更双峰）。播报新增「开发进度」区块（work_progress.py + /app/data/work_progress.json，agent 持续写入）。

### 2026-09-28 细叶分发（招牌菜联动归类）：39 高置信入库（已写库/提交 a7196bb）

**分工**：用户明确「细叶分发由本对话框（纯 DB、不依赖小红书登录），social listening 交开发」。背景：candidate_apply 收录只挂菜系根，细叶 n_active 恒 0。

**产物 `cloud/subtype_distributor.py`（数据驱动，非逐店枚举）**：
- 复用 gap_runner.category_worklist/category_supply（LCA 根+细叶）；指示词 = `LEAF_KW`（leaf_id→风格/概念同义词，含英/罗马字/假名，覆盖 ramen8+soba3+udon3+stuffed5+dessert4+french2+tea3=28 叶）＋叶名自动派生 `_auto_terms` 兜底。新增细叶/风格只改词典。
- **两道关键防线（dry-run 抓出 bug，先修后写）**：
  1. **distinct-dish 计数 + 头名词**：一道菜只计一次、取最高分，杜绝「小笼/小笼包」「汤包/灌汤包」在同一道菜重复计数把正餐大店（园有桃/夏宫/随堂里/上海餐厅/Hoxa/罗宋娃娃）误抬过主营门槛；强形式词（蘸面/二郎/家系/松饼…）只有在菜名头位（去括号注释后以该词结尾）才记 3 分，作修饰（后接拉面/面）降 1 分 → 满吉正确归蘸面、七豚（鸡白汤 vs 二郎并列）正确 hold。
  2. **NAME_WEIGHT=4**：店名命中（横滨家系/无锡小笼/bistro 品牌词）压过泛汤头词次 → 鲤久正确归横滨家系（曾被泛豚骨误判博多）、丸龟归赞岐；`LEAF_EXCLUDE`（锅贴排除「地锅/贴饼」）→ 徐州老灶台（贴饼子）正确 hold。
- 判定（precision-first）：必须 support 严格领先；形式叶（stuffed/bing/tea_drink）要求店名命中或 ≥2 道不同菜；风格叶还允许强头名单菜。并列/弱/负向语境一律 hold。只 POST restaurant_cuisines（幂等加法，不删根、不动其它字段）。
- **结果：39 入库** = ramen5 + udon1 + stuffed16（汤包15、汤圆宁波汤团店1）+ dessert5（可丽饼 La Creperie、松饼 AL'S/米仓/Flipper's/FINE）+ french7（Bistro：LE VERRE/Sip/Polux/Le Saleya/Cuivre/Nuits三期/Coquille）+ tea5（新中式茶饮）。其余多叶 category（hubei/korean/thai/vietnamese/indian/spanish/russian/american/sichuan/beijing/mongolian/henan/mexican/bread）**0 入库、371 hold**。
- **hold 两类根因（交开发/social 侧，勿手补）**：①候选是正餐大店、仅单道菜沾边（正确不挂）；②**分类法缺口**——缺细叶：烤肉/韩式烤肉、美式/西式牛排、gelato、蛋糕/西点、糖水、饺子、馄饨、生煎、抹茶、越南 pho 等，同类店无叶可挂；需补 discovery_plan 叶后重跑本分发器（幂等）。
- 复跑：容器内 `python3 /app/cloud/subtype_distributor.py [--category X] [--commit]`（common 在 /app/pipeline；当前经 stdin 落 /tmp 跑，下次 build 由 `COPY *.py` 收进镜像）。

### 2026-09-28 看门狗通知合并（digest）+ 重复标题修复（已部署/验证）

**用户反馈（附刷屏截图）**：看门狗一次盘点发出 3 条独立消息（tencent/search、tencent/geocode、amap/search 各一条），且每条标题「自动处理中…」重复出现两行。要求同一轮所有信息合并成一条一次性发完。

**两个根因 + 修复**：
1. **重复标题**：`notifier.format` 把 head 拼进正文，health 发送原语（`_telegram/_feishu/_feishu_app`）又在最前面拼一次 head → 标题两行。修复：`format` 正文不再含 head（只返回「分隔线+正文+结尾」），由原语统一在最前拼一次；实测最终文本 head 计数=1。
2. **多条刷屏**：`map_key_repair.run` 旧实现对 4 个 provider×interface 各调一次 `notifier.warn`（key 各不同）→ 多条。修复：合并盘点，**有接口全尽则单条 WARN（统一 key=`map:quota`，逐行列接口+key数+最早解封）；全部恢复则单条 RESOLVED**。内容哈希不变且在 cooldown(3600) 内由 notifier 自动折叠。实测：首跑发 1 条合并消息，立即再跑同内容被折叠（不发第二条）。

**容器重建（并行会话操作，已确认恢复）**：期间 food-cloud 容器/镜像被一次 `docker build -t food-cloud:local`（新增 Playwright/Chromium，国内源）重建，随机名容器是构建中间步骤；构建完成后经 `docker-compose.yml` 以 `container_name=food-cloud、restart=always` 起回，fooddata 卷与挂载不变。已重新热部署 notifier.py / map_key_repair.py；验收 gap_pool 在跑、cron 在跑（13 条有效 crontab）、采集恢复。

### 2026-09-28 覆盖采集粒度对齐：细叶 → category 原生（已落盘/部署/验证）

**根因（粒度错配）**：`candidate_apply.py` 对每条 admit 新店只 `tag_cuisine(rid, 菜系根id)`（root 名取 `K.CUISINE_ROOT[cat]`），**不分发到 discovery_plan 的细叶**。故细叶（拉面·博多/蘸面…）`n_active` 恒为 0，若按细叶判据，每个细叶都跑 2 轮加深后 gap_remaining、空转。采集单元本就应是 category（引擎/门/写库都以 category 路由）。

**已落地（category 原生 gap_runner，重写）**：
- `category_worklist()`：129 bundle 经 resolver 映射后**按 category 聚合**为 **58 个工作单元、覆盖 126 叶**（3 个标签节点 257/258/259 正确不采集）；每单元 `{leaves,names,seeds=并集xhs词}`。
- `category_supply(cat)`：root 由本单元细叶父链的**最近公共祖先 LCA** 推出（不依赖 CUISINE_ROOT 显示名，修掉「越南菜 vs 越餐」「地中海菜 vs 地中海/希腊菜」漂移）；`n_active`=root 聚合在营店数（账本父节点根直挂+子树去重）；`target`=本单元计划叶 target_n 之和。
- `claim_next_category`：认领即**整类占用全部细叶**，整类 met / gap 冷却中 / 已被认领则跳过；`release_category`。`run_category` 仅全新引擎注入「frontier名+并集种子」，饱和→gate+apply→按 category_supply 判整类达标；未达标走 reseed_deep 假饱和重开（MAX_DEEP_ROUNDS=2）→ gap_remaining（6h 冷却）。
- 修了一个会让 account_b 启动即崩的 bug：`_claimed_categories` 误对 dict 迭代键（str）→ 改为 `claims.values()`。

**target 校准（coverage_ledger 两处修复）**：
- 旧 gap_runner 调 `coverage_ledger --save` 不带 `--poi-counts`，叶子全落到**名字启发式**：每个拉面子叶名含「拉面」→ 误判 rich=5（ramen target 虚高到 40）。
- 修复：ledger **默认自动加载 `/app/data/coverage/poi_counts.json`**（291 叶分母来源全转 poi）；复合子叶（「拉面·蘸面」）启发式只看「·」后子类型词。结果：供给档 scarce133/normal40/rich118；**ramen target 40→17、sichuan 56→17（n=111 met）、sushi target=5（n=21 met）**；category 发现达标 27/58。
- 口径分离：**发现完成 = n_active ≥ target**（本判据）；`n_verified≥target`（17/291=6%）是下游真实评价管线，不阻塞发现。

**验收（实测）**：单一真实 gap_pool（重启前先清旧 pool/worker、claims 重置 {}）；2 worker 存活、**分采不同 category**（account_a→ramen / account_b→soba），raw 真实增长；软限流时退避 120s 自恢复、stalled 不入库。全量 category_supply 自检 **err=0**。

**仍未做（下一步）**：细叶 subtype 分发（把根下餐厅按招牌菜归到子叶）是独立下游 pass，未建；深覆盖名店回归（佐佐/福寿司/肉屋kita、ministry of crab、8by8、望庐等）依赖 social listening 进一步升级。

### 2026-09-28 角色确立 + 看门狗「假死号」根因修复（已部署/提交）

- **角色确立**：本对话框被正式赋权为「采集运维与效率负责人」，宪章见 skill `references/collection-ops-charter.md`（已在 SKILL.md 开工读取与 References 中挂载）。五要点：①负责采集（小红书/B站等）运转与提效，边界自动从上下文获取；②聚合看门狗+语义判断+方案自治；③自主开发/现成skill/资料查询→回到自主开发；④解决问题最高、非高难任务节约 token；⑤逐日复盘、每日 02:00 自进化。
- **02:00 自进化 cron 已建**：「美食图鉴·02:00自进化复盘」，表达式 `0 2 * * *`，首次 2026-09-29 02:00；复盘采集/告警/配额/登录态→归纳通识→固化机制→核查 cron/采集进程→更新 HANDOFF→notifier 双通道推复盘摘要。
- **★ 假死号根因（两账号刚登录即被标 dead -100）**：`account_repair.probe()` 旧实现用搜索 POST（`/api/sns/web/v1/search/notes`）且调用 `sign.get_search_id()`；实测 xhshow 0.1.9 已移除 get_search_id（AttributeError），且搜索受速率软限流、返回值在 `0(有数据)/0(空)/-100` 间漂移，快速探测（min_gap=3s）时把活账号误判 -100 → mark_dead。
- **修复**：probe 改为 GET `/api/sns/web/v2/user/me`，code==0 且 guest==false 才判活（低风险、不碰搜索限流）；-100/游客→死，其余风控码→软封。部署后运行 account_repair，两账号自动 dead→ok，`_cookie_pool_state.json` 均 ok、pool_alive=True。
- **核实**：容器无 pgrep（报 pgrep:not found），cron 存活以 /proc comm 扫描为准——实测 /usr/sbin/cron 在跑（crontab 39 行），「cron-stopped」是工具缺失的假阴性。

### 2026-09-28 采集空转诊断与恢复（已修复/部署/提交）

**起因：用户问「采集任务是不是在跑」。结论：守护进程与账号都在，但实际没在采（空转）。** 三个确定性卡点：
1. **陈旧认领**：worker 崩溃 / gap_pool 重启后 `coverage/claims.json` 残留（无活 gap_runner 持有），claim_next_leaf 见 lid 被占永不重领 → 8 个叶子被卡死（4 个 engine 卡 running、4 个未建引擎）。
2. **xhshow 0.1.9 移除 `get_search_id`**：`gap_pool.classify()` 与 `gap_runner._probe_account()` 仍调 `api.sign.get_search_id()` → AttributeError。在跑的旧进程内存里是旧签名才没暴露，**一旦容器重启将再也拉不起 worker / worker 一启动即崩**。
3. **假饱和**：其余 40 个可映射叶子全被标 saturated（搜索 frontier 跑干）但覆盖未达标（达标仅 17/291、缺口 867）——弱关键词/限流搜不到≠没有好店，缺「未达标即重开+更深信源」。

**已落地修复**：
- 新增 `cloud/reap_claims.py`：扫 /proc，仅当存在含 `gap_runner --account <name>` 的活进程才保留该 claim，否则在锁内删除；**gap_pool 启动时调用 + 运行中每 5 分钟周期 reap**，自愈。
- `gap_pool.classify()` 与 `gap_runner._probe_account()` 全部改用 **GET `/api/sns/web/v2/user/me`（code=0 且 guest=false 才健康）**，与 account_repair 同一口径；搜索软限流自恢复、不再卡住 worker 派发。
- 已重启 gap_pool 加载新代码。**验收：2 个 worker 存活、各认领叶子并真实采集**（leaf 272 荞麦 raw 7 条、leaf 275 乌冬 raw 11 条并持续增长）；b 偶发速率软限流（间隔退避 120s）后自恢复。

**遗留、下一步机制缺口（未修，属覆盖深水区）**：
- 「假饱和」重开：saturated 但 ledger 未达标叶子应自动重开、换更深 social listening 信源，而非以 frontier-dry 收尾。
- `map_category` 路由过窄：discovery_plan 129 bundle 中 **81 个映射不到 category**（智利/烧卖/烧饼/汤包/包子/葱油饼/手抓饼/薄饼等），从未进入采集；需扩 routing 或改由 cuisines 表直接解析 category。

### 2026-09-28 飞书看门狗暂停 + 播报信号-模块对齐精简（已部署/提交）

- **暂停飞书看门狗**：看门狗在容器内（非 Doubao cron）。新增通道级总开关 `health.channel_enabled(name)`，判定顺序 NOTIFY_* 环境变量 → `/app/data/notify_channels.json` → 默认开；三个通道原语 `_telegram/_feishu_app/_feishu` 与 `health.alert` 全部先过此闸。当前 `/app/data/notify_channels.json = {"telegram":true,"feishu_app":false,"feishu":false}`——**飞书两通道全暂停、TG 保留**。一处覆盖看门狗/心跳/登录工单/地图配额/各补齐脚本的全部外发。恢复：把该文件对应项改 true（或对我说「恢复飞书」）。
- **信号→模块目录（已固化进 notifier.py docstring，无登记不得推送）**：
  - `heartbeat` ← progress_broadcast，每 10 分钟，INFO，cadence 600；
  - `watchdog:killed` ← watchdog，强杀卡死进程(runtime>30m)，WARN，cooldown 3600；
  - `login:account_x` ← warning_handler，双出口 user/me 均 -100，ACTION→RESOLVED，有界 nudge；
  - `map:quota` ← map_key_repair，地图 key 全尽/恢复，WARN→RESOLVED；
  - `pool_autostart` ← account_repair，gap_pool 缺失已拉起，WARN once。
- **心跳正文精简（build_compact，固定 3~4 行）**：覆盖 / 账号(合并候选·阻塞) / 开发；DB 计数失败时该行静默（不再印「计数跳过」）；账号均 ok 时残留 SEARCH_RESTRICTED/COOKIE_INVALID 标记视为过期、不显示阻塞（修掉「账号 ok 却报搜索风控」的信号矛盾）。实测：TG send True、feishu_app/feishu 均 None。

### 2026-09-28 两个真正独立的小红书账号已登录部署（实测双账号搜索均 22 条）

- **背景**：此前 account_a/account_b 的 web_session 身份段相同，取证发现是同一台设备登了同一账号（单会话策略，第二个设备登录会顶掉前一个）。用户确认有第二个号，本轮在本机真实 Chrome 分别扫码完成。
- **关键坑：同端口 IPv4/IPv6 被两个 Chrome 同时占用**。旧的卡住 Chrome（profile `/tmp/food_real_a2`）占着 `127.0.0.1:9222`（IPv4），新窗口（profile `/tmp/food_real_a3`）退而绑定 `[::1]:9222`（IPv6）。Playwright 连 `http://127.0.0.1:9222` 一直读到旧窗口、且报 `Browser context management is not supported`；改用 `http://[::1]:9222` 才连到新窗口。排查：`lsof -Pan -p <主进程PID> -iTCP -sTCP:LISTEN`。
- **最终两账号（容器签名 user/me 权威核实，均 guest=false）**：
  - account_a：实际昵称 **LANCE**（用户口头称 ahuhu），小红书号 **668317783**，uid **`5e1175c9000000000100804c`**；profile `/tmp/food_real_a3`，CDP `[::1]:9222`；搜索实测 22 条。
  - account_b：昵称 **猪蛤蛤**，小红书号 **6353478662**，uid **`6972702800000000370282a7`**；profile `/tmp/food_real_b2`，CDP `127.0.0.1:9223`；搜索 22 条，采集走广州独立出口。
  - 两账号 uid 不同 = 真正独立。cookie 已部署宿主机 `/home/ubuntu/food-cloud/xhs_accounts/account_{a,b}.json`（600，旧文件已 .bak 备份），只读挂容器 `/secrets/xhs_accounts`。
- **身份判据（务必遵守）**：昵称可随意改，user_id / 小红书号永久不变；判断账号是否独立只看 user_id，不看昵称。权威登录判据 = `user/me guest=false`。身份账本 `cloud/account_identities.json` 已回填并部署 /app/data 与 /app/cloud。
- SOP 已在 `references/xhs-login-runbook.md`（真实 Chrome + CDP 只读，安全速率 ≤2 次搜索/分钟、间隔 28s；云端 headless 扫码确认必 fail 是死路）。

### 2026-09-28 地图配额根治 P1：池化仲裁 + 持久账本 + POI 缓存（已部署/提交/推送，实测通过）

- **根因（均取证）**：①高德「搜索」个人开发者 **5,000/月**（infocode 10044=账号级月限，同账号多 key 不叠加，只有独立实名账号才叠加），非脚本误写的 5,000/日；②最重的 `cloud_amap_fill`（全字段、3次/时、1433 候选）走单 key 绕开池、吃光月配额，电话被饿死；③腾讯单 key 无池、且值含 `&+=#%` 时 111；④一个兜底挂就整轮判 quota，不跨 key/出口重试；⑤电话/坐标/营业时间/全字段对同一 POI 各调一次、无共享缓存；⑥无持久账本/看门狗，重启先打同一把 key。
- **新建 `cloud/map_quota.py`（配额仲裁核心）**：
  - 持久账本 `/app/data/map_quota_ledger.json`（原子 tmp+replace），按 `provider:idx` 存每 key 的 daily/monthly 窗口用量；本地日切换重置日桶、月初重置月桶并清对应 dead。
  - 软上限取官方值 90%（可 env 覆盖）：腾讯 search/geocode 各 9,000/日；高德 search 4,500/**月**、geocode 4,500/日。
  - `acquire(consumer,provider,interface)`：消费者优先级 phone=0 > coord=1 > hours=2 > full=3；search 接口在池剩余 ≤ 电话预留（腾讯 3,000 / 高德 800）时低优先任务让路 → reserved。
  - `report()` 按真实返回码标 dead：腾讯 121→dead 到次日0点、111→sign_error 不 dead；高德 10044→dead 到下月1号、10003→dead 到次日0点。
  - 统一签名：腾讯/高德 sig 均小写 md5；值清洗 `&+=#%`；统一 `call()`（每次新建 MapQuota 保证跨进程账本新鲜；单 call 只试一把 key，rate 由 wrapper 循环轮换）。
  - `PoiCache`：持久 JSON、容量 4000、LRU；`make_key`（有 provider poi_id 用 `provider:id`，否则 md5(name|address)），默认 ttl 30 天。
- **`cloud/map_helpers.py` 接线**：新增 `_map_call`（逐把 key 尝试、rate/error/sign_error 自动换下一把、no_budget/reserved→quota）；腾讯 suggestion/search/geocode/detail 与高德全部走池；`amap_geocode` 修正为 interface=geocode/consumer=coord（原误挂 search 月桶）；`resolve_poi` 接入 PoiCache **只正缓存**（found 判定=有 title/坐标/tel，quota/未找到不缓存）。
- **`cloud/cloud_amap_fill.py` 重写**：`amap_text` 走池 consumer=full；返回 QUOTA（真耗尽）/YIELD（为电话预留让路，安静停、不告警）；main 守卫改为池里有 key；**单轮默认 100→40**；月配额告警文案改为「月初重置」。
- **实测（容器内真实调用）**：高德 key#0 首打 10044 → 持久标 dead 到月初、monthly_used=[1,0]；第二次自动跳过 key#0、用 key#1 返回 ok（infocode 10000、3 POI），跨账号轮换通过；腾讯修复一个空 SK 回退 bug（`_split_csv("")` 返回 `[""]` truthy 致 SK 回退没生效）后 MQ.call 与 wrapper 均 status=0；resolve_poi 同店第二次调用 **零搜索（缓存命中）**。账本 search_remaining：腾讯 8,991、高德 4,499。
- **提交**："feat(map): 地图配额池化仲裁+持久账本+POI缓存，全字段任务给电话让路"（已 push main）。
- **P3 地图看门狗（已完成/部署/提交）**：新建 `cloud/map_key_repair.py` 并由 `watchdog.py` 每 20min 调用。按 provider×接口（腾讯/高德 × search/geocode）盘点可用 key：amap search 月桶、其余日桶，月配额 dead 不影响 geocode；全尽才经 notifier 告警一次并带【最早解封时刻】，恢复自动收尾。实测：`tencent/search=ok(1/1)、tencent/geocode=ok(1/1)、amap/search=ok(1/2)、amap/geocode=ok(2/2)`。提交 "feat(watchdog): 地图key看门狗接入20min巡检"。
- **L0 免配额电话源：取证确认【keyless 批量不可行】（2026-09-28）**。实测：①Bing 摘要几乎不含电话（严格 021/手机正则在全库已知电话店召回≈0，偶现手机号与真值不符）；②Bing 云出口搜索质量失效（KIINA→新疆新闻、凌珑→字典页，发现不了正确官网）；③SmartShanghai 首页超时/search 404，TimeOut search 仅 446B 空壳。结论：真实电话只在地图配额或登录墙平台（点评/美团/微信小程序），不存在可精确批量的免 key 源；强做会写错号、违反宁空不假，故不做。
- **缺电话 197 家处置**：大量为预约制私房菜/私宴（本就无公开号，正确留空）；少数高端酒店餐厅（La Jade/凌珑/金轩）号码在墙内，需【登录态点评会话】（类比小红书账号）做账号辅助定向采集，属独立连接器、非 keyless 批量，待用户决定是否提供点评登录。
- **P2 扩容（可选，需用户操作）**：再注册 2–3 个独立实名高德/腾讯账号并做免费企业认证（搜索 5千→5万/月），key 只进 gitignored deploy.env。

### 2026-09-28 warning_handler 二维码专项：根因链全部修复（已部署/提交/推送，等用户扫码）

- **现象**：看门狗虽有 warning_handler，但推送到 TG/飞书的「二维码」要么是登录遮罩文字、要么 50s 不产码；account_a 双出口签名探测 -100 一直无法恢复。
- **逐层坐实的根因与修复（均在 `cloud/xhs_qr_login.py` + `cloud/warning_handler.py`）**：
  1. **飞书缺图片权限**：自建应用缺 `im:resource`（错误码 99991672）→ 已在飞书开放平台开通 `im:resource:upload` 并发布，fs_photo=True。
  2. **TG multipart 被 Deno 反代损坏**（sendPhoto 400 IMAGE_PROCESS_FAILED；官方被墙、广州代理超时）→ 改上传 Supabase Storage 公共桶 `qrcode`（public，对象 `qr/<stem>_<ts>.jpg`），sendPhoto 按公共 URL 以 JSON 发送，实测 ok。
  3. **元素截图把遮罩截入**：`img.qrcode-img` 上有绝对定位遮罩（扫码登录/请在手机确认/重新 + Please/Didn't），element.screenshot 会合成遮罩 → capture_qr 改为**直接 base64 解码 `img.qrcode-img` 的 src 写原始字节，完全不截图**，PNG 签名校验。
  4. **占位图/过期图混入**：新增 `looks_like_qr(raw)`（PIL：正方形且≥100px；采样像素彩色<1%、中间灰<20%）。实测真 QR（128×128）colored=0/mid=0/dark=52.8%/light=47.2% 通过；128×129 双语占位图因非正方形被拒。
  5. **刷新误判死循环**：`_refresh_if_expired` 曾用宽泛词（失效/重新加载）匹配 `.code-area`，正常态也每秒点击 `.qrcode` 反复刷新、二维码无法稳定 → 收紧为 innerText 强短语（二维码已失效/点击刷新/QR code expired…）才点，且只在当前 src 非有效 QR 时按 8s 节流。
  6. **★ 决定性根因：worker 假存活死锁**：worker 退出后 pid 文件里的 **pid 被别的进程复用**，`is_running` 仅凭 `/proc/<pid>` 存在就判 True（实测 killall 扫到 0 个 chrome/worker、但 running=True），`Q.start` 永久拒绝拉新、request_login 还误杀无关进程。→ 重写存活判定：`_worker_pid` 校验 `/proc/<pid>/cmdline` 同时含 `xhs_qr_login`+`--worker`+本账号，pid 文件失效则**全量扫描 /proc 兜底**；`start` 遇陈旧 pid 文件直接覆盖拉起；`stop` 只杀真 worker 并清 pid 文件。
  7. **worker 自愈重载**：新增 `_goto_login`（/login→首页容错）+ `ensure_qr`（当前页抓不到就重新打开登录页再抓，最多 3 次）；主循环二维码缺失立即修、每 100s 强制换新（像素无法判断过期）。
- **验证（2026-09-28）**：修复后 `_worker_pid` 正确识别 None → request_login 真正拉起 worker、running=True、二维码双通道推送成功（last_qr_push 有值）；最终 `/app/data/qr/account_a.png` = **128×128 RGBA 干净二维码（目视三角定位块清晰、无遮罩）**。
- **当前等待**：用户需在二维码有效期内（小红书 App 扫一扫）扫码；宿主机 `/root/food-qr-installer.py`（root cron 每分钟）校验 `qr/account_a_new.json`（JSON 数组、含 web_session+id_token）后搬到 `/home/ubuntu/food-cloud/xhs_accounts/account_a.json`（600），warning_handler `_verify_installed` 探测 code=0 即关单并推「✅已重登」。
- 提交："fix(watchdog): 修复二维码worker假存活死锁——cmdline校验+全量扫描兜底+自愈重载+base64解码干净二维码"（已 push main）。权威最新源即项目 `cloud/warning_handler.py`、`cloud/xhs_qr_login.py`。

### 2026-09-28 元层：北极星宪法 + 机制总纲 v4（治「世界观被遗忘」与六大根因，已锚定）

- **元问题定位**：缺陷不是缺文档，而是 ①世界观没被锚定成「每次必读、可机械执行」的契约（散落多文档、会被忘）；②机制写在纸上但没全部落成在跑代码（容器曾是旧版 gap_runner 即例证），缺「原则→模块→状态留痕」绑定。
- **`references/north-star-constitution.md`（每次开工第一读，最高优先级）**：唯一使命=为真实食客做「真正好吃」的图鉴，入选唯一充分理由=真实可验证的好吃；去软广是护城河不是目的。六条公理 A1 口味唯一最高 / A2 真实可溯宁空不假 / A3 机制优先不补单店 / A4 信源要沉淀 / A5 账号是最后手段 / A6 闭环自检；含会话启动强制动作。
- **`references/mechanism-master-v4.md`（六大根因完整方案 + 绑定表）**：
  - P1 缺失→**宇宙定义（叶子×expected_supply×target_n）+ 6 个独立抽样框（地理/权威/集团主厨树/社交/地图POI/滚雪球）+ 缺口可量化**；密度升级（每叶子语义词≥10、每词≥4篇、必采评论区）。
  - P2 错漏重复过时→**规范实体 + 事实主张 claims(provenance/confidence) + 字段 last_verified 保鲜 + 变更留 history**。
  - P3 良莠不齐→**出品定类 is(主营) vs serves(含有) + admission gate 证据准入 + 持续复评**。
  - P4 账号依赖→**L0 公开/L1 匿名签名/L2 只读/L3 登录兜底 降级阶梯**；需登录请求占比逐版本下降。
  - P5 一次性源→**source registry（kind/auth_level/covers/reliability/cadence/health/connector）+ 连接器定时化 + 源质量评分淘汰**。
  - P6 去软广太窄→**区分软广 astroturf / 硬广 paid / 工业化 industrial；评论级 p_softad 多信号（语言模板分布+行为网络+商业标记+平台操纵）+ 店铺级扣罚；自学正常/非正常分布**。
  - **spec→code binding 强约束**：每条原则须同时绑定 ①确定性模块 ②状态/账本留痕 ③被闸门调用，才算已实现；只写文档=未实现。绑定表逐项标 已建/部分/待建。
- **SKILL.md 已更新**：标题下加「开工第一步读宪法+机制绑定表」强制项；修复文档漂移（原引用不存在的 `references/architecture-v3-master.md`，实际 v3 在项目 `research/design/`，已改正路径）；登记两份新文档。
- **实施顺序（L0→L3）**：①本轮锚定 → ②P1 扩 ledger(expected/target)+建 group/chef tree(F3) → ③P5 source registry+连接器(douyin/wechat→weibo/zhihu) → ④P2 field claims/保鲜/history → ⑤P3 出品定类联动+审计+复评 → ⑥P6 软广 v2 → ⑦P4 迁移源到 L0/L1 → 每步 release_audit A–H 全绿、回读、更新 HANDOFF。
- **【P1 第一步已落地】coverage_ledger 扩展分母**：新增 expected_supply(scarce95/normal151/rich45)、target_n(2/3/5)、gap_n、met、supply_source；分母优先级 override>地图POI>根路径启发式。实跑 291 叶子：**达标仅 15/291=5%、未达标 276、总缺口 757 家 verified 好店**；当前分母全为 heuristic。已存 /app/data/coverage/ledger.json 并提交。**下一步**：deep_discovery 全叶子跑地图 POI 计数喂 --poi-counts（数据驱动分母）+ 建 group/chef tree(F3)。

### 2026-09-28 P2 地基：覆盖账本 + 地毯搜索计划器（已建模块、容器内跑通）

- **`pipeline/coverage_ledger.py`（四维覆盖账本）**：对 291 个叶子节点量化 n_active / n_real（有真实食客）/ n_verified。结果：**empty 30、shallow 99、thin 54、ok 47、rich 61；缺口(empty+shallow)=129**；全库真实食客仅覆盖 **62/1472**。落盘 `/app/data/coverage/ledger.json`。`--gaps` 列缺口喂引擎。
- **`pipeline/discovery_planner.py`（标准地毯搜索 + 可定制词根）**：把 129 个缺口叶子展开为按平台路由的 **5302 条**查询（xhs/douyin/bili/weibo/wechat/map），每个社交 bundle 标 `mine_comments=true`（必采评论区、评论提及新店进 frontier 做图遍历）。子风格叶子自动转真实词形（博多豚骨拉面/赞岐乌冬/十割二八荞麦），高频项补英文。落盘 `/app/data/coverage/discovery_plan.json`；`--sample <id>` 可审阅。
- **下一步 = 多平台执行器**：消费 discovery_plan，按平台跑（bili/amap 已可用；xhs 走 browser+账号池；douyin/weibo/wechat 接 cloud browser），统一"正文+评论区→抽店名→聚合独立声音→admission_gate→candidate_apply"，并按账本回写饱和状态。migration 013（KOL posts/mentions）与执行器同期落地。
- **执行器 `pipeline/deep_discovery.py`（map 通道已跑通）**：复用 `map_helpers.amap_search`（多 key 池），把缺口叶子 POI 汇聚进统一 **frontier 池** `/app/data/coverage/frontier.json`（key=cjk_norm 名；含 aliases/地址/电话/坐标/sources/hits/候选菜系/matched_rid/status/chain_suspect）。与在营店做名称/基础名(去分店)/地址匹配。加菜系相关性过滤（日料叶子剔兰州/河南/牛肉拉面等非日式面）。首跑前 12 叶子：**frontier 65、new 59（非连锁 55）、matched 3**。地图仅 1 平台声音→**只建池不收录**；待社交/评论 collector 进同一池补足独立声音才 admit。
- **下一步（执行器社交半）**：xhs（account_b）→ 后续 douyin/weibo/wechat，跑密集词 + **打开正文扫评论区抽新店名做图遍历**（治望庐类漏收），把真实声音与评论提及写入同一 frontier；随后 resolver 路由 + admission_gate + candidate_apply，并重跑 ledger 看饱和。
- **统一驱动 `cloud/gap_runner.py`（零侵入，已实跑验证）**：账本缺口叶子 → 计划器 xhs 密集词束 + map frontier 新候选店名（leaf264 共 19 种子）→ cookie 池选可用账号启动 CloudBrowser → 构造 DiscoveryEngine 到独立目录 `discovery/gap<id>` 并覆盖其 frontier_high → 引擎原有图遍历（正文+评论）。leaf264 实跑 6 查询/18 笔记：brands 4、库外 3、frontier 剩 16。
- **抽名精度修复（runner 层注入 `DE.GENERIC_WORDS`）**：评论/正文常见非店名短词（地址/适合/环境/人均/口感/排队/附近…约 60 个）一律拦截、不耗浏览器；已无浏览器验证：垃圾词 blocked=true、真实店名（一风堂/面屋武藏/博多一幸舍）不误杀。残留：RE_REC 捕获的单句片段（如"蘭姐却说"，单次无店铺后缀）应只进 oral 不 enqueue——需在引擎源码把"评论推荐片段→anchor"改为要求店铺后缀或重复≥2（Edit 工具对该文件读取态异常，待恢复后折叠；blocklist 同步沉淀进源码）。
- **下一步**：①gap_runner 饱和后接 gate/apply（按 leaf cuisine 挂载）并自动滚动全部 129 叶子；②cloud_discover 固定 QUEUE 路径与 gap_runner 收敛（后者为账本驱动，前者退役或转调）；③抖音/微博/公众号 collector 进同一引擎。
- **【2026-09-28 11:20 已闭环并验证，当前卡在账号】**
  - 修复 router rc=127：`run_script` 裸用 `python` → 改 `{sys.executable}`（/usr/local/bin/python）；已验证 router 现以 **rc=0** 拉起 gap_runner，不再静默失败。
  - router 偶数轮决策改为 **`gap_runner.py --next --queries 8`**（账本驱动）；`pick_next_leaf` 已验证选中 (264, ramen)。
  - gap_runner 升级为**全自动闭环**：自动选下一个未饱和缺口叶子 → 店名优先取证（map frontier 名）+ 泛发现词垫后 → 引擎图遍历；叶子饱和后**自动** admission_gate（--out 顶层 candidates_<cat>）→ candidate_apply --commit → 再选下一叶。启动时清掉历史垃圾品牌（GENERIC_WORDS 已扩到约 70 词）。
  - **当前阻塞**：11:20 健康检查 account_b 仍 ok，但 gap_runner 启动瞬间 account_b 跳 `restricted`（搜索风控 300011，连续搜索触发，见教训 #67）；现 account_a dead / account_b restricted，**双号不可用**。gap_runner 正确走 AllAccountsBlocked 分支跳过、不硬刷；系统每 3h 自动复检并经 TG/飞书告警。
  - **解除方式**：等 3h 冷却自动复检，或往服务器 `food-cloud/xhs_accounts/` 丢第三个账号 `<id>.json`。账号恢复后 cron（*/20）自动续跑 leaf264（状态 running、processed16、frontier 余 9），无需人工。
  - 备注：cloud_discover 旧路径在 bread 上曾跑出 207 品牌/180 库外/482 oral（噪声待 gate 过滤）；新 router 已统一走 gap_runner，cloud_discover 不再被调度。
- **【2026-09-28 12:00 已绕开浏览器风控：签名直连 HTTP 后端落地，不再需要加账号】**
  - 新增 `cloud/xhs_api.py`：用 **xhshow 纯 Python 签名**（x-s/x-t/x-s-common/x-b3-traceid）直连 edith 接口；cookie 池轮换 + 限速（2.2s/次 + 抖动）。
  - **决定性实测**：①匿名 a1 搜索 → -101（关键词搜索必须登录态，无法彻底免登录）；②但浏览器里被标 restricted(300011) 的 account_b，走签名 API **code=0 正常返回**——浏览器搜索风控不影响 API 路径，这就是绕开点。
  - 端点姿势（踩坑后确认）：搜索 POST `/api/sns/web/v1/search/notes`；详情 POST `/api/sns/web/v1/feed`；评论 GET `/api/sns/web/v2/comment/page` **必须带 `xsec_token`+`xsec_source=pc_search`（否则 300031），但不可带 top_comment_id/image_formats（否则 code -1）**，评论翻页用 cursor。
  - gap_runner 已改为**全程 HTTP、不启动浏览器**：monkeypatch `D._gather_one_query` → api.gather_query；leaf264 实跑 saturated（processed21）→ 自动 gate（reject2/hold1/admit0）→ apply（errors0）；`pick_next_leaf` 自动滚到 (265, ramen)。
  - 依赖 `xhshow==0.1.0`、`xhs==0.2.13` 已写进 `cloud/requirements.txt`（重建镜像不丢）。
  - **现状**：cron */20 router → gap_runner --next 会持续以 HTTP 逐叶推进 129 缺口，不再受浏览器账号阻塞；account_a -100 已自动跳过、account_b 经 API 可用。第三账号非必需。
- **【2026-09-28 12:20 升级为并行采集池（每账号一个 worker，自动扩缩）】**
  - `cloud/gap_pool.py`（常驻守护，crontab `@reboot` 自启）：每 300s **逐账号绑定探测** classify（code 0 健康 / -100 过期），每个健康账号拉起一个 `gap_runner.py --pool --account <name>`；worker 退出按健康状态决定重启；写 presence `/app/data/POOL_RUNNING`。
  - `gap_runner.py` 新增：`claims.json`+`fcntl` 跨进程原子认领（claim_next_leaf/release_leaf，保证一叶同时只被一个 worker 处理）；`worker_loop(account)`（认领→跑到 saturated 自动 gate+apply 或账号失效→释放→再认领）；`--pool/--account`。
  - `xhs_api.py` 新增 `pin`：worker 绑定单账号，非 -100 风控冷却后在本账号重试、不占用别人账号；-100 直接判死让 worker 退出。
  - `cloud_router.py`：见 `POOL_RUNNING` 即整体让位（返回空 target），避免与池重复。
  - 并行限速：每 worker 3.2s/次。**注意所有 worker 共享服务器单一出口 IP，账号越多并行越可能被按 IP 关联风控；要安全提速可给每账号配独立代理（未配置）。**
  - **重新激活 account_a 的唯一办法**：其登录已过期(-100)，AI 无法自愈，需用户用 account_a 重新扫码登录、导出新 cookie 覆盖 `/home/ubuntu/food-cloud/xhs_accounts/account_a.json`；池在 300s 内探测到 code 0 即自动拉起第二个 worker。第三账号同理丢一个 `<id>.json` 即自动加入。
  - 运维：查进程 `cloud/_inspect_pool.py`、停池 `cloud/_stop_pool.py`（均经 `ssh ... 'docker exec -i food-cloud python3 -' < cloud/<f>.py`）；日志 `/app/data/pool.log`、`/app/data/pool_logs/<account>.log`。
  - **【2026-09-28 12:30 实测最终状态】account_a 已重新登录激活、是当前活跃 worker（连续产出，每查询 3 篇）；但 account_b 在前期持续自动化搜索后被服务端失效(-100)，需同样重新扫码才能成为第二个并行 worker。当前实际并行度=1。**
  - **关键结论（瓶颈不是账号数量）**：约束是 ①web_session 在持续自动化搜索下会被失效(-100)；②所有 worker 共享服务器单一出口 IP，并行搜索会被按 IP 关联并触发软限流（code0/空页，已加 20→40→90s 指数退避）。要获得稳定的 N 倍并行吞吐，必须给每个账号配**独立出口代理**（XhsApi 支持按账号传 proxies，待配置）；否则即使两个账号都在线，同 IP 并行也会互相拖累。

### 2026-09-28 KOL 名单任务「找回」：mid 落库 bug 修复 + 回填 + 多平台机制设计

- **"任务丢失"真相**：`food_kol_watchlist` 表与 B站 cron（`30 */6` cloud_bili_collect）一直在，没丢。丢的是：①上一版 P1–P9 计划**漏列 KOL 交付项**（已重新挂为独立工作项）；②平台覆盖**仅 B站**；③代码 bug——`upsert_kol` 有 mid 却没写进 row（已修，加 `"mid": mid or None`），且从不抓 follower_count；④无"推文归档→线索/特征标签"表。
- **本轮已做（写库回读）**：修 `cloud/cloud_bili_collect.py upsert_kol`；从 `/app/data/bili_state.json` 回填 **18/22 mid**，并按 mid 调 B站 `x/relation/stat` 回填 **follower_count 18 条**（如 真探唐仁杰 473.8万、哇塞几张 213.5万、元气八眉菌 236.7万、无所尉 35.9万）。4 个未在搜索结果出现的预填名（跟着老高/周大猫/头五头六/味觉川菜）随 cron 自动补。
- **待建：多平台 KOL + 推文线索机制（拟 migration 013_kol，与 P2 深覆盖共用源矩阵）**：
  - 扩 `food_kol_watchlist`：kol_type（博主/美食家/美食导演/美食作家/主厨自媒体）、specialty_tags jsonb（菜系/场景/食材）、region、profile_url、trust。
  - 新表 `food_kol_posts`（kol_id、platform、post_url 唯一、title、summary、published_at、raw_mentions、captured_at）；新表/视图 `food_kol_mentions`（post_id、restaurant_id、mentioned_raw、match_status matched/ambiguous/unmatched、polarity）。
  - 采集器：B站（扩写 posts）；公众号（搜狗微信/RSS）；抖音/小红书/微博（复用 cloud browser + 账号池）。种子=权威名册（沈宏非/殳俏等美食作家、黑珍珠/米其林相关、头部博主）+ 提及频次≥3 自发现。
  - 流程：posts→NER 抽店名→模糊+地址匹配（歧义 hold）→未匹配进 P2/P3 候选；KOL 到访只写**特征标签**（不计入 taste）；软广闸门用 KOL 多样性（单一 KOL 反复=降权）。

### 2026-09-28 P1 数据质量收尾：品粹1788/徽季 合并 + group_members 400 查明（已写库回验）

- **966 品粹1788 与 1884 徽季 = 同店更名，已合并（keeper=1884）**：经米其林官网（Hui Ji，Villa 2）+ 携程/抖音核实——品粹1788（2021 起，大别山食材高端徽菜，人均约932）2024 年与新荣记联手，将同栋 V2 别墅、同电话 021-68581788 改造为新荣记徽菜品牌「徽季」（米其林在册）。走 `entity_resolve --apply research/atlas/huiji_verdict.json` 合并；随后 detach 迁移来的冲突标签 72 Casual Dining（保留 71 Finedining），price_avg 校正为 **932**（同实体 Ctrip 实测，待 P7 复核），并补 `restaurant_group_members(group1新荣记,1884,品牌「徽季」)`。最终 1884 标签：8徽菜/71 Finedining/159米其林/160黑珍珠/162午餐/163晚餐。**restaurants 1480→1479（active 1472 / closed 7）**。
- **restaurant_group_members GET 400 根因**：该表为复合主键（group_id+restaurant_id）、**无 id 列**，默认 `order=id` 报 42703；表本身有数据、健康。正确访问 `order=group_id`（无管线代码读取它，仅临时分析受影响，无需改代码）。
- **现网基线（2026-09-28）**：坐标 100%、电话 1250/1479（84.5%）、营业时间 897/1479（60.6%）；reviews 1038（真实 mid/high 139、高德 low 899）；evidence verified 35 / provisional 1441 / insufficient 3；chefs 56、restaurant_groups 10、food_events 25（17 缺日期、25 缺报名链接、10 缺关联店）。
- **下一步 = P2 深覆盖 sourcing 机制**（菜系×场景×食材×口碑四维 + 多平台源矩阵 + 标准地毯搜索/可定制词根模块），随后 P3 扩容、P4 真实评价、P5 events、P6 chef/集团、P7 字段质量、P8 清理、P9 前端。

### 2026-09-28 residual 71 外部封闭选项集裁决清零 + Polux 合并（已写生产库并回验）

- **背景**：`identity_conflicts` R1–R7 + 父链 `_coerce` 修复后，仍剩 **71 个证据指向不明的多根店**（residual）。云端容器无 LLM 凭据，用户拍板**不配云端 LLM key，由主 agent 在外部裁决**（教训 **#73**）。
- **做法**：容器 `conflict_plan2.json` residual 拉到本地 `research/atlas/residual71.json` → 对证据不明的店逐家联网核验官方/权威口径 → 每家在既有根封闭选项内输出 winner → `research/atlas/adjudicate_residual.py` 先内存安全模拟（attach cid 合法、detach 配对、每店最终恰好一个菜系根、无空标签店）再 apply，计划 `/app/data/residual_verdict_plan.json`。
- **关键裁决**：JG/POLUX/SHADOWS/Ortensia=法餐26；The Nest=北欧34；Sir Elly's 半岛现行北意=意餐27（不挂法）；Obscura/The Pine/EIGHT UNDER=融合44（The Pine 1882 为唯一 attach44 + detach26/31）；日式强信号群（一风堂/竿屋/平成屋/洋食…）=日料85；金陵烤鸭/盐水鸭/美龄粥=苏菜4；利苑/金轩/头灶=粤3；虹泉路韩国街=韩35；dry-aged 牛排/dining bar 全食物/全早餐 brunch=美餐31；Nordic bakery(SMAKA)=面包301；coffee&gelato(HUFFY)、蛋挞+中式茶饮(裕莲)=甜品302；closed EHB 不动。
- **执行结果（写库回读）**：**76 ops（75 detach + 1 attach）全 applied，verify mismatches=0，active 多根店 = 0**；stage4 **ERROR=0、WARN=258**（多为缺电话，电话 cron 在补）。
- **Polux 重复合并**：rid1152「POLUX」（马当路245，地址错、0 review）与 rid1810「Polux by Paul Pairet」（权威地址太仓路181弄5号）确认真重复，走 `entity_resolve --apply research/atlas/polux_verdict.json` 合并，restaurants 1481→**1480（active 1473 / closed 7）**，1152 已删、1810 标签完整。
- **新候选重复待核（未处理）**：rid966 品粹1788 与 rid1884 徽季，同固话 021-68581788、同在世纪大道1788号 V2 别墅，疑似更名/同实体，落 PHONE 桶，下次核对。
- **仍未充分完成（9 条短板）**：真实评价覆盖仅 62/1480（真实 XHS 139）；events 去重/起始日期/报名入口（Nuits 重复、expires 空17、报名仅4、rid 空10）；chef/集团 profile 广度（chefs56/groups10、group_members GET 400 待核）；简介质量与 open_days（仅69）；私房/会所覆盖；更广覆盖（佐佐/福寿司/肉屋kita 等）。前端继续搁置（省额度、先做数据库/管线）。

### 2026-09-27 菜系父链根因修复：无主身份 375→0，冲突二次裁决（已写生产库并回验）

- **真正根因（此前两轮"数据修复"无效的原因）**：`cuisines.parent_category` 是**文本列**。历史多条代码路径把父级写成字符串——一类是根**名字**（"粤菜"/"日料/日本料理"），一类是**数字 id 串**（"85"）。PATCH 整数进文本列会被转回 "85"，所以改数据无效；`trad_root` 只在 `isinstance(par,int)` 时向上走，导致深一层叶子全部解析不到根 → 375 店无主身份。
- **修复（在引擎，不在数据）`identity_conflicts.trad_root`**：内置 `_coerce`，把数字字符串父级（"85"）归一为 int 后再遍历；名字型父级（拉面/乌冬/荞麦=89/236/261）经 int 父链自然解析。
- **两道安全闸（机制，非枚举）**：①零证据裁决（无任何菜品/品牌/店名票、且非店名 forced）一律转 residual，不自动执行；②NAME_ROOT 的 bar 判定排除附带的 "& Bar / and Bar"（牛排馆/餐厅常见，serves≠is）——修掉 Stone Sal 言盐被误判 Bar（现转 residual 待判 美餐）。apply 计数把 **409 已存在判成功**（幂等）。
- **执行结果（写库回读）**：先做内存安全模拟（attach cid 合法、detach 配对存在、受影响店最终恰好一个菜系根、无空标签店）=PASS；`conflict_plan2.json` **47 ops 全部 applied**。最终 active：**1398 单一根、约 75 多根（全部在 residual 队列=71，含一风堂/利苑/南京大牌档/JG/POLUX 等）、无主身份 0**；**stage4 ERROR=0、WARN=260**（232 缺电话由电话 cron 补）、坐标 **100%**。备份 `/app/data/backup_pre_parentfix_cuisines.json`。
- **下一阶段（未开始）**：**71 residual 逐店裁决**——多数证据明确（一风堂/竿屋/平成屋→日料；南京大牌档/盐水鸭/南伶→苏菜；JG/POLUX→法餐；利苑→粤菜；韩餐炸鸡群→韩餐），需补通用规则（日式强信号：豚骨/刺身/牛肠锅/明太子；金陵烤鸭≠北京烤鸭）或封闭选项集 LLM 批量裁决。**云端容器仍无 LLM API key（仅 TELEGRAM_BOT_TOKEN）**：离线自动裁决需先配 LLM 凭据，否则由主 agent 分批裁决。

### 2026-09-27 主身份归类「回滚」：茶域试点 + 跨传统冲突全量裁决（已写生产库并回验）

- **根因（RC2，污染总根）**：把"菜单出现某菜/饮品"（serves/contains）误当"店铺是什么"（is/primary identity）。一家店只有一个主传统根；单菜/单饮只能进 secondary/食材。
- **机制（确定性规则为主、LLM 仅在封闭选项集裁决，五阶段：清本体→证据包→强信号预路由→歧义裁决→校验对账）**，两个引擎：
  - `cloud/vendor/pipeline/identity_resolution.py`（已部署；默认 dry、`--plan`、`--apply`）：**茶域试点**。规则含 HK_NAME/HK_BRANDS/HK_DISH（港式茶餐厅/冰室→109）、BREWED_TEA/TEA_SEAT（冲泡叶茶/茶席→茶馆）、COUNTER_TEA（柜台奶茶/蛋挞→新中式茶饮352/奶茶353）、MATCHA（抹茶→324）、PASTRY/DINNER_MAIN；计数按"每道菜/店名"（修抹茶重复计 2）。口径：**茶馆=菜系324茶饮 + 形式82茶馆 双标签**。
  - `cloud/vendor/pipeline/identity_conflicts.py`（已部署；`--plan`/`--apply <plan>`）：**跨传统根冲突**，规则 R1 关店不动；R2 pasta bar→意餐27、bistro/brunch/小酒馆/餐酒馆/eatery→融合44（仅 wine bar/cocktail/whisky/酒吧/清吧 才是 drinking Bar303）；R3 店名私房菜→形式348、会所→形式347（菜系保留或另判）；R4 融合菜是风格、店名无 fusion 词时让位具体国菜；R5 单一正餐根压过非正餐 minority；R6 大洲/区域泛节点（亚洲菜/非洲菜/欧洲菜/新马印）让位具体国家；R7 品牌/店名强信号/≥3票领先2。
- **执行结果（已写库回读）**：茶域 apply 47 ops（首批42+补回5）；冲突全量 final_plan **104 ops**（引擎87+残留裁决17），apply 98 写入 + 6 个 409（已存在=幂等达标）。**最终：1105 店单一传统根；唯一多根=1262 EHB（closed，按设计保留）**；stage4 **ERROR=0、WARN=260**（全是缺电话，电话 cron 在补）。备份：茶域前 `/app/data/backup_pre_tea_rc.json`；冲突前 `/app/data/backup_pre_conflict_rc.json`（10799 行）；计划 `/app/data/conflict_plan.json`、`/app/data/final_plan.json`。
- **关键工程教训（待入 lessons）**：①detach 只能对 `dimension=菜系 且根不同` 的叶子，**食材/形式/认证/时段（ROOT_OF=None）一律保留**（曾误删）；②裸"茶"误匹配茶座/茶楼、"酒馆"误匹配小酒馆——茶/酒馆店名强信号需收紧（茶座归下午茶、小酒馆归 bistro）；③attach 409=已存在应判成功（幂等）；④同名异址分店保留。
- **下一阶段（未开始）**：**375 店无菜系传统根**（实测它们挂了 439 个菜系标签但 trad_root 解析为 None=父链异常/孤叶，形式多为 Casual Dining 282；price_scene 正餐331/快餐40）——先修这些菜系叶的父链本体，再逐店补主身份（量大、需 LLM 裁决，**云端容器无 LLM API key，只有 TELEGRAM_BOT_TOKEN**，须主 agent 分批或先配 LLM 凭据）。其余 9 条短板：真实 XHS 评价仅覆盖 62/1481、events 去重/日期/报名、chef 广度、简介质量/open_days、更广覆盖（佐佐/福寿司/肉屋kita 等）。

### 2026-09-27 实体归并「彻底改造」已执行：多信号三桶 + 持久 keep，restaurants 1507→1481

- **模块 `cloud/vendor/pipeline/entity_resolve.py`（已部署 /app/pipeline；默认 dry，`--plan` 导出，`--apply verdicts.json` 执行）**：多信号实体解析三桶 AUTO/REVIEW/PHONE；详见教训 **#70**。
- **本轮结果（已写生产库并回读）**：合并 **26 簇**（AUTO 14 + REVIEW 全并 8 + 部分合并 2 + PHONE 桶里同店/同铺位 2），restaurants **1507→1481**；子表（reviews/favorites/negotiations/price_benchmarks/restaurant_cuisines）由 `merge_duplicates.fill_master/migrate` 迁移，重复行删除。
- **四类代码根因已修**：①latin 品牌被拆单字母（改整词 joined）；②商场中心坐标过聚（坐标近不单独 AUTO，须叠加同铺位/同门牌/同固话）；③商场词过笼统（mall_of 带前 5 字前缀，区分五角场/宝山万达）；④拉丁菜系词当品牌（`_LATIN_CUISINE` 剔除 indian/chinese/thai…）。
- **刻意保留（不并）**：同名异址分店（滇味园、莲餐厅、有喜屋各万达、璞徽）；同楼不同层不同餐厅（Robuchon 3楼餐厅 vs 1楼烘焙坊；**Barbarossa 二/三楼在营 vs MOC 一楼 2018 入驻，Barbarossa 并未关店**）；酒店总机/同楼餐厅共享号码（香格里拉/宝格丽/柏悦）。错号 null_both 4 对、null_one 2 对（Manner 误挂星巴克 400、食光误挂临江宴）。
- **持久裁决**：保留对写入 `/app/data/entity_keep_pairs.json`，并随镜像打包 `/app/pipeline/entity_keep_pairs.json`（代码合并两处读取）。**复跑 `entity_resolve.py` 已收敛 AUTO/REVIEW/PHONE 全 0；stage4 ERROR=0**（仅缺电话 WARN，电话补全持续）。合并前全库备份 `/app/data/backup_pre_entity_1507.json`。
- **下一步（未开始）**：P2 主身份重归类（primary vs secondary serves/食材、同音异义、误挂成对删挂）；P4 覆盖（权威名单+平台类目枚举+KOL 合集/评论区建候选全集，与库 diff 佐佐/福寿司/肉屋kita 等真缺）。

### 2026-09-27 评分引擎「真实食客对齐」迁移 012 已执行 + 软广分布自学模块上线

- **根因（生产库实测）**：1504/1507 家有全套 `score_*`，但 589 家 0 真实评价、905 家仅 1~3 条；1038 条 reviews 中 **899 条是高德聚合评分（trust=low）**、真正小红书 UGC 仅 139 条。旧 `recalc_taste_for` 只过滤 `review_kind='diner'`、**不过滤 trust/来源**，平台聚合评分被当成口味分 → "口味优先"空心。`soft_ad_flag_reviews` 此前全为 none（无自学机制）。
- **迁移 `db/migrations/012_scoring_realign.sql`（SQL Editor 已执行并回读）**：
  - 删除旧约束 `ch_rest_score_complete`（要求四项分数全有/全无，与新设计冲突）；新增 `restaurants.score_evidence_level`（verified/provisional/insufficient）。
  - `cuisine_prior` 与 `recalc_taste_for` 改为**只采 `trust_level IN ('mid','high')`**（排除高德 low）；taste=贝叶斯收缩(m=8、半衰期180)、diner=时间加权原始均值、review_count/confidence 只数真实 UGC，无则 NULL/0。
  - 重写 `derive_restaurant`：**verified(≥2 独立真实食客)** = .45 taste+.25 diner+.18 objective+.12 endorsement（真实 .70/平台 .30）不封顶；仅 1 名真实食客=provisional 封顶 82；无真实评价=.6 objective+.4 endorsement=provisional **封顶 70**；无任何证据=insufficient、total NULL。
  - 价格：补全 price_scene（按标签，默认正餐）并按 `price_band_thresholds` 全量重算 price_band → **price_scene/price_band 为唯一价格权威**；tier/price_position 为遗留字段（前端恢复时移除，暂不 DROP）。
- **执行后实测**：evidence **verified 35 / provisional 1469 / insufficient 3**；仅 **62** 家有真实 taste/rc；provisional(无 taste) 总分 max=70（封顶生效）；price_scene 空=0、price_band 空（有 price_avg）=0。注意：当前 verified 多为面/饺/小吃（XHS 真实评价先覆盖到这些），高端 omakase/米其林因真实评价尚未采集暂落 provisional——随 XHS 批量采集自动提升，机制已正确。
- **软广分布自学 `cloud/vendor/pipeline/softad_distribution.py`（已部署，cron 每天 5:37）**：从真实 UGC 语料学正常分布，五信号（五星占比/无实质内容占比/时间 burst/近重复文本 3-gram Jaccard≥0.8 聚类/作者多样性），阈值取语料稳健分位数(P90/P75)+保守固定底线，n<3 不判定；写 `soft_ad_flag_reviews`（输入列），最终 flag/penalty 由 007 trigger 纯派生、可随证据升降。首跑：62 真实UGC店、17 可判定，**全 none、零误杀**；基线落 `/app/data/softad/baselines.json`。crontab 第 9 条已装入容器。
- **鉴权关键**：新版 Supabase 密钥（`sb_secret_`/`sb_publishable_`，非 JWT）在云端容器内可正常读写，但**本机经 Clash 出口直连 PostgREST 报 PGRST301**；任何分析/盘点脚本须放进容器跑：`ssh ... 'sudo docker exec -i food-cloud python3 -' < local.py`。

### 2026-09-27 数据完整性巡逻 / 保鲜机制已部署（cloud_patrol.py + patrol_classify.py）

- **根因（5 类通识，问题反复回潮）**：①实体解析只认精确键→异名重复（pain chaud/百丘）；②分类只看“关键词在场”而非主身份语义→拉面误挂酱蟹/大盘鸡、老干杯双标签；③去重/分类/价格/简介都是一次性跑、没接成持续巡逻；④价格绝对阈值且场景盲；⑤卡片（chef/简介）无 QC。
- **新模块（非浏览器 REST，已上云）**：
  - `cloud/patrol_classify.py`：概念本体——每叶给强/弱特征+有序改道路由；店名优先于菜品；REMOVE 须有肯定反向证据（店名命中=high、菜品≥2 道[nd≤2 时 1 道]=high、仅弱信号+店名别业态=high、无锚→review）；ADD 仅店名强锚定；日式强信号（豚骨/鸡白汤/虾白汤/蘸面/家系/二郎/背脂/鱼介/博多）存在时不按兄弟菜品路由；互斥组（烧肉vs美式牛排）品牌命中>强特征、零支持移除。
  - `cloud/cloud_patrol.py`：总编排六检（实体 merge_duplicates / 分类 patrol_classify / 价格 stage7 / chef 补链 / 保鲜 / 简介 semantic_profile）；默认 dry、`--apply` 才写；state.json 指纹 diff new/fixed，digest 有变化才发双通道、无变化 24h 心跳。
- **首跑战果（已写生产库并回读）**：实体 14 簇合并（restaurants 1521→**1507**，子表迁移）、分类 **23/23** 写、价格 1500 家场景归一（五档 入门315/主流276/进阶289/高端276/旗舰344）、chef 补链 **39**、简介补 2；复检实体/分类/简介全 0，**stage4 ERROR=0**（坐标100%、电话85%）。
- **部署**：Dockerfile COPY 与 build_on_server.sh 打包清单均已加两文件；crontab 第 8 条 `42 */3 * * *`（独立 /tmp/patrol.lock，避开 amap :15/:35/:55）；新镜像 `2a474ae50a3c`，容器内 crontab -l 与 dry-run 已核对。
- **遗留**：旧绝对字段 `tier` 与场景相对 `price_position` 并存，后续对齐（见教训 #70）。

### 2026-09-27 多平台采集「轮候路由」cloud_router.py（dry-run 已验证，待切 cron）

- **问题**：服务器同一时刻只有一个无头浏览器；旧 cron 靠手动错峰(:00/:05/:25/:35)，新平台（米其林/抖音）插不进来，且账号被风控时还在硬刷小红书，易触发 300011。
- **方案（资源分池）**：R1 单浏览器（小红书发现/reviews + 米其林榜单，串行）；R2 B站 HTTP API（独立 cron 每 6h，不抢浏览器）；R3 高德日配额（回填任务夜间预算制，POI 枚举待配额决定后上）。
- **新脚本 `cloud/cloud_router.py`**：每个 tick 先读 `xhs_cookie_pool.summary()`（扁平 dict，key=account_id，值含 status/cooling），有可用账号→跑 `cloud_discover.py`（开放式发现，找宝藏店主力）；全部账号冷却→改跑 `michelin_collect.py`（不依赖小红书登录），避免硬刷风控。带 `--dry` 只决策不执行。
- **已部署到容器并 dry-run 验证**：账号 a=restricted/cooling、b=ok → 决策 `cloud_discover`（正确）。**注意 summary() 是 {account_id:{status,cooling}} 扁平结构，不要当成 {accounts:[...]}**。
- **【已完成】router 接管 cron（2026-09-27）**：浏览器类任务统一由 `cloud_router.py` 每 20 分钟一个 tick 接管（`flock /tmp/browser.lock`），不再手动错峰。决策：账号全冷却→`cloud_michelin_collect.py`（cloud_bu，不依赖 XHS 登录）；有可用账号→按 `/app/data/router_tick.txt` 轮替 discover / run_batch，reviews 全部采完（ALL_REVIEWS_DONE）后恒走 discover。非浏览器任务保持各自 cron：电话:05/:25/:45、坐标03:00、营业时间04:00、高德多key:15/:35/:55、看门狗:10/:30/:50、B站:30 */6。新镜像 a235c8642924，容器内 crontab -l 已核对。
- **高德配额硬约束（第二个开发者账号已上线，日配额翻倍，已端到端实测）**：`map_helpers.py` 为**多 key 池**，env `AMAP_KEYS=key0,key1`、`AMAP_SKS=sk0,sk1`（位置一一对应、保留空 SK，未配则回退单 key/AMAP_SK）；一个 key 撞 10003/10044 本进程标记停用并自动切下一个，全部耗尽才返回 `QUOTA_EXCEEDED`。
  - key#0 `1f319f...`：**无 SK，走服务器出口 IP 白名单**（AMAP_SKS 第 1 位留空，空 SK 时不附 sig）。
  - key#1 `0e28d25644fac7a18ce2f10f5651d19f`：第二账号（app id 3688486），**数字签名已开启**，SK `0f6ae3532c2bbc31727fa270ea58ec02`。
  - **关键坑（10007）：高德 sig 必须是【小写】md5 十六进制；大写一律回 `INVALID_USER_SIGNATURE`。** 中文参数按 UTF-8 原始值入签名、发送时 urlencode（与官方一致）。
  - 实测：key#0 当日 10044→标记停用→自动轮换 key#1（小写签名）→返回真实 POI。新镜像 `53c30bd9405b`，容器 food-cloud Up。凭据权威在本地 cloud/deploy.env（build 自动携带）。
- **米其林 P4 已容器化验证**：新增 `cloud/cloud_michelin_collect.py`（用 cloud_bu.CloudBrowser，不依赖小红书登录），容器内实跑 4 页共 **153 家**写入 /app/data/michelin_shanghai.json；cloud_router P4 已指向它。dry-run：账号 b 可用→cloud_discover，全冷却→cloud_michelin_collect。

### 2026-09-27 云端最新状态：账号 B 已接入并实测通过，小红书采集恢复

- 账号 A 处于账号级搜索风控 `300011`（restricted，冷却中）。账号 B（小红书 uid `6972702800000000370282a7`）已登录、导出 19 个 cookie（含 `web_session`/`a1`），存为服务器与容器挂载目录 `/secrets/xhs_accounts/account_b.json`（chmod 600），零改代码、无需重建镜像。
- **端到端实测通过**：`cloud_ready.open_ready_browser()` 自动跳过冷却中的 A → 用 B 开浏览器 → check_login + check_search 均通过 → `mark_ok`。当前 pool.summary：account_a=restricted/cooling，account_b=**ok**。后续 cron 的 run_batch/cloud_discover 将自动用 B 采集。
- 加号（第三、四个账号）= 往服务器 `/home/ubuntu/food-cloud/xhs_accounts/` 丢一个 `<id>.json`（顶层 cookie JSON 数组），容器只读挂载即生效。
- 排错要点：① 托管 profile 对 CDP `Storage.clearDataForOrigin`（仅 cookies）有韧性、登不出；彻底登出走应用自身菜单（`.menu-icon-btn`→`.menu-icon-dropdown-nav`→点 `div.menu-item`「退出登录」，点内层文字不触发 React）。② 整页 `/website-login?redirectPath=...` 报「回调地址错误」；应在 explore 用「点赞」触发页内弹窗 `.login-container`（小红书/微信扫码+手机号，无回调问题）。
- 账号 A cookie 仍在服务器 `account_a.json`，未丢失，冷却到期自动复检。

### 2026-09-27 B站(bilibili)美食探店采集已接入（API 优先 / bili-cli 兜底）

- **新脚本** `cloud/cloud_bili_collect.py`（容器内 `/app/cloud/`），cron `crontab.txt` 第 8 条：`30 */6 * * *`（每 6 小时，:30 错峰，flock `/tmp/bili.lock`）。
- **采集源**：首选零依赖搜索 API `x/web-interface/search/all/v2`（必须带 `Referer: https://search.bilibili.com`，否则 -412 风控）；API 非 code=0 自动切 `bili-cli`（容器内容错 pip 安装，装不上不阻断构建）。每次请求间隔≥1s，每轮≤10 词（≤200 条）。
- **词根矩阵**：复用 `discovery_keywords.CATEGORY_SPEC`（41 品类）× 6 句式（`上海 <品类> 探店/苍蝇馆子/宝藏/正宗/主厨/新店`）= 246 词轮询；状态 `/app/data/bili_state.json` 记录已搜词/已处理 bvid/UP主累计计数，断点续跑。
- **双通道**：① KOL 监控——UP主出现≥3 次 upsert 进新表 `food_kol_watchlist`（DDL：`db/migrations/011_bili_kol.sql`，**需在 Supabase SQL Editor 手动执行**）；② 餐厅候选——视频 title+简介落 `/app/data/discovery/raw_bili_<cat>.jsonl`（kind=discover，desc 已归一化全角竖线→冒号、并补店名锚点行）→ `admission_gate.py --raw ... --category <cat>` → `candidate_apply.py --category <cat> --commit`。
- **反软广不变**：B站视频标题/简介只算一条整理声音，独立声音≥2（≥2 个不同 UP主）、口味均分≥3.5、招牌≥1 才 admit；单视频提及一律 hold/reject，宁空不假。坐标受上海 bbox 硬约束，电话/坐标/营业时间不确定留空。
- **已知缺口**：抖音 / 公众号 / 视频号 源仍未接入。`food_kol_watchlist` 建表后首次运行自动预填 7 个已知美食 UP主（跟着老高吃东西、周大猫Mc、无所尉吃什么、元气八眉菌、一天世界的陆老师、头五头六白相相上海、味觉川菜）。

### 2026-09-27 迁移 011 已执行并核验；修复 KOL upsert 不合并问题

- **建表完成**：已在 Supabase SQL Editor 执行 `db/migrations/011_bili_kol.sql`。PostgREST 独立核验：`GET /food_kol_watchlist?select=id` → 200；实际列 = id/name/platform/follower_count/video_count/first_seen/last_seen/status/notes（无 mid、无 updated_at，即仓库权威 schema）；RLS 已启用、service role 写入。
- **修复 upsert 缺陷**：原 `upsert_kol` 只发 `Prefer: resolution=merge-duplicates` 但不传冲突目标，PostgREST 无法稳定推断 `(name,platform)`，**重复 upsert 返回 409（23505）而非更新**，导致 video_count/last_seen 不刷新。已改 `cloud/cloud_bili_collect.py` POST 路径为 `/food_kol_watchlist?on_conflict=name,platform`，实测连续两次 upsert：201→200 且 video_count 正确更新。
- **镜像已重建并验证（2026-09-27）**：已跑 `cloud/build_on_server.sh` 在服务器原生 amd64 重建（无 OOM），容器 Up。运行镜像 grep 确认 266–267 行含 `?on_conflict=name,platform`；cron `30 */6` B站任务在、双账号（account_a/b）已挂载。容器内端到端测试：对已存在 KOL「味觉川菜」调 `upsert_kol` 返回 True（HTTP 200 合并，非 409），修复正式生效。
- **已即时预填**：7 个已知美食 UP主已通过 API merge 写入，表共 7 行。云端旧镜像下轮 cron 即使再跑一次 prefill 也只产生无害 409、不会重复建行（随后 `prefilled` 置真）。
- 教训沉淀：SQL Editor 的 Monaco 逐字 `type` 会自动补全括号、且 `/sql/new` 可能复用带残留标签导致内容错乱；可靠做法是先关闭全部旧查询标签 → `pbcopy < 迁移文件` → 聚焦编辑器 `Cmd+V` 粘贴（粘贴不触发自动补全）。



***

## ① 项目目标与最高原则

**一句话**：做一份「上海美食图鉴」—— 口味优先、只认真实食客堂食 UGC、对抗软广的餐厅榜单。



* **口味优先**：评分引擎以 `score_taste`（真实食客口味）为最高权重（0.35），不是平台人均 / 媒体榜单。

* **真实食客堂食 UGC**：只采信 `review_kind='diner'`、`is_fake_suspect=false`、`is_hidden=false` 的评价；外卖 / 媒体稿不计入口味分。

* **对抗软广**：中央厨房 / 预制菜 / 资本化连锁 → 自动派生 `soft_ad_flag` 并扣分（confirmed 扣 25 /suspected 扣 10）；非正餐（咖啡 / 面包 / 甜品 / Bar / 茶饮）豁免连锁供应链扣分。

* **宁空不假**：电话、坐标、营业时间宁可留空也不编；坐标宁空不猜（上海 bbox 硬约束）；关店三要素（status/closed\_date/closed\_source）齐。

* **淘汰软标记不物理删除**：关店店保留记录（status='closed'），不 DELETE；软广店降级不删库。

* **一条线做精再复用**：机制跑通后再扩品类；用户点名的店是**回归测试用例**，不是待补清单（漏店 = 机制有断点，修机制而非手补）。

* **榜单只收真正好吃的店**：候选池 = 全量发现 + 实测补充，≥2 条可溯源堂食评价、≥2 个独立渠道才入精选。



***

## ② 技术栈与整体架构



| 层        | 技术                                                                                                 | 位置                                                                            |
| -------- | -------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| 前端       | Next.js 14.1 (Pages Router) + TypeScript + Tailwind + Leaflet/markercluster + @ducanh2912/next-pwa | `app/`                                                                        |
| 前端部署     | Vercel（GitHub push main 自动构建，**Root Directory 必须显式设为&#x20;**`app`）                                 | 生产：[https://app-lyart-eta-22.vercel.app](https://app-lyart-eta-22.vercel.app) |
| 数据库      | Supabase / PostgreSQL 17 + PostGIS，REST API（PostgREST）                                             | project ref `bdwrhshgdeghgyzwpxnl`                                            |
| 云端采集     | 腾讯云轻量服务器 `49.234.35.92`（Ubuntu，amd64），Docker 容器 `food-cloud`，cron 常驻                               | `cloud/`                                                                      |
| 反代 / 告警  | 告警走 Telegram Bot / 飞书自定义或应用机器人（国内服务器直连 TG 不通时填 `TELEGRAM_API_BASE` 反代）；容器内 `telegram_proxy/`       | `cloud/health.py`                                                             |
| 方法论 / 管线 | city-food-guide skill（SKILL.md + references/ + scripts/food\_pipeline/）                            | 见下方路径                                                                         |

**方法论 skill 路径**（不在本仓库内，是外部 skill）：



```
\~/.doubao/agent\_mode/workspace/.user\_skills/city-food-guide/

├── SKILL.md                 # 总 playbook（六步工作流 + 交付自检清单）

├── references/              # 23 份方法论文档（data-pipeline / scoring-rubric / discovery-playbook /

│                            #   cuisine-map / chain-premade-audit / lessons-learned 等）

├── scripts/food\_pipeline/   # 确定性管线脚本（stage1\~7 + 采集/分类/评分/补全）

└── templates/               # 新品类冷启动空白模板
```

本机展开路径：`/Users/hubowen/Library/Application Support/Doubao/Default/.doubao/agent_mode/workspace/.user_skills/city-food-guide/`

**ASCII 架构图**：



```
&#x20;                       ┌─────────────────────────────────────────────┐

&#x20;                       │              用户浏览器 (PWA)               │

&#x20;                       │   Next.js (app/, Vercel)  Leaflet 地图      │

&#x20;                       └───────────────┬─────────────────────────────┘

&#x20;                                       │ HTTPS · anon key · 只读 RLS

&#x20;                                       ▼

&#x20;       ┌───────────────────────────────────────────────────────────┐

&#x20;       │        Supabase Postgres + PostGIS (rest/v1)             │

&#x20;       │  restaurants / reviews / chefs / food\_events / cuisines  │

&#x20;       │  触发器：derive\_restaurant(算 tier/score\_total/soft\_ad)  │

&#x20;       │         trg\_reviews\_taste(口味分) trg\_awards\_endorse(背书)│

&#x20;       │  视图：v\_feed\_recent / restaurant\_detail\_view / feed\_view │

&#x20;       └───────▲───────────────────────────────▲───────────────────┘

&#x20;               │ service\_role key (写)          │ anon key (读)

&#x20;               │                                │

&#x20;  ┌────────────┴───────────┐         ┌────────┴─────────┐

&#x20;  │  本机管线 (skill/       │         │  /api/sync 心跳   │

&#x20;  │  scripts/food\_pipeline)│         │  (Vercel Cron 3am)│

&#x20;  │  stage0..7 确定性入库   │         └──────────────────┘

&#x20;  └────────────▲──────────┘

&#x20;               │ REST (common.req)

&#x20;               │

&#x20;  ┌────────────┴───────────────────────────────────────────────┐

&#x20;  │  腾讯云 49.234.35.92 · Docker 容器 food-cloud (cron 常驻)  │

&#x20;  │  每20min run\_batch.py → xhs\_collect(无头Chromium)          │

&#x20;  │    → xhs\_to\_reviews.py → atlas\_write.py --commit → Supabase│

&#x20;  │  另: phone\_fill(每20min错峰) / coord\_fill(每天3am)          │

&#x20;  │        / hours\_fill(每天4am)                                │

&#x20;  └─────────────────────────────────────────────────────────────┘
```



***

## ③ 目录结构与职责

整理后（2026-09-26）项目根：



```
china-travel-food/

├── app/                      # 【前端】Next.js Pages Router + PWA，Vercel Root Directory=app

│   ├── pages/                # \_app/\_document/index/map/login/auth-callback

│   │   ├── restaurants/index.tsx, \[id].tsx   # 列表页 / 详情页

│   │   └── api/sync.ts       # Vercel Cron 只读保鲜心跳（写 sync\_log，不改 status）

│   ├── components/           # ClusterGroup(地图聚合) / EventModal(事件弹窗) / FeedSection

│   ├── lib/                  # supabase.ts(client+类型) / auth.tsx / favorites.ts / geo.ts / format.ts

│   ├── public/ styles/ next.config.js(tailwind+PWA) vercel.json(Vercel Cron)

│   └── .env.local            # 前端+本地管线密钥（见⑦，不入库）

├── cloud/                    # 【云端采集】腾讯云 Docker 常驻服务

│   ├── Dockerfile docker-compose.yml entrypoint.sh crontab.txt build\_on\_server.sh deploy.sh

│   ├── run\_batch.py          # 一轮采集编排（断点续跑：采→转→入库）

│   ├── xhs\_collect.py 等     # 实际采集脚本在 vendor/pipeline（镜像内 /app/pipeline）

│   ├── cloud\_bu.py health.py# 无头浏览器封装 + 登录态探测/告警

│   ├── cloud\_phone\_fill.py / cloud\_coord\_fill.py / cloud\_hours\_fill.py  # 云端补齐

│   ├── vendor/pipeline/     # 管线快照（skill scripts/food\_pipeline 的拷贝，build 时 COPY）

│   ├── deploy.env(.template) # 云端环境变量（密钥，不入库）

│   └── xhs\_cookies.json      # 小红书登录态（只读挂载进容器，不入库）

├── db/migrations/            # 【DB Schema】001\_init → 010\_chef\_group\_hours\_events，按顺序在 SQL Editor 执行

├── research/                 # 【调研数据】atlas(小红书原始)/authority(米其林黑珍珠召回)/social/

│                            #   scene/scene\_v3/poi/private\_dining/regional/continents/design(设计文档)

│                            #   + 各菜系目录(川菜/粤菜/...) + 大量 \_\*.jsonl 过程稿（gitignored 工作区）

├── backups/                 # 【备份】写库前快照（restaurants/reviews/cuisines 等 JSON）

├── pipeline\_work/           # 【近期工作产物】如 recall\_20260926/（Ministry of Crab 召回）

├── archive/                 # 【本次整理】历史过程稿归档（audit-2026-09-22/23、coverage-tasks、cross\_cuisine\_report）

├── data/                    # 旧深度调研工作区（gitignored，体量大，可忽略）

├── scripts/                 # 空目录（旧飞书同步脚本已删，写库统一走 skill/scripts/food\_pipeline）

├── reviews\_priority.expanded.json   # 小红书采集优先级清单（1100 家，云端读取驱动采集顺序）

├── review-coverage-report-2026-09-26.md  # 最新采集/覆盖报告（保留在根）

├── audit-semantic-hours-2026-09-26.md    # 最新语义简介/营业时间审计（保留在根）

├── README.md DEPLOY.md       # 旧版说明（README 仍提"飞书表格"为历史残留，实际写库已走 food\_pipeline）

└── HANDOFF.md                # 本文档
```

**注意**：`research/` 下有大量 `_*.jsonl`、`_*.py`、`plan_*.json`、`write_b*.json` 等 9/23\~9/24 的过程稿，它们是管线分片产物，**保留不删**（属 gitignored 工作区，体量大但含证据链）；有效数据子目录为 `atlas/ authority/ social/ scene/ design/`。



***

## ④ 完整 DB Schema

> 现网实测行数（2026-09-26，service_role count=exact）：restaurants 
>
> **1519**
>
> 、reviews 
>
> **136**
>
> 、chefs 
>
> **56**
>
> 、restaurant_groups 
>
> **10**
>
> 、food_events 
>
> **25**
>
> 、cuisines 
>
> **332**
>
> 、restaurant_awards 
>
> **157**
>
> 。
> 注意：
>
> **没有独立的&#x20;**
>
> `sources`
>
> **&#x20;表**
>
> ——
>
> `sources`
>
>  是 
>
> `food_events`
>
>  上的 JSONB 列。
>
> `restaurant_cuisines`
>
>  / 
>
> `restaurant_chefs`
>
>  / 
>
> `restaurant_group_members`
>
>  是
>
> **复合主键、没有&#x20;**
>
> `id`
>
> **&#x20;列**
>
> 。

### 4.1 表清单



| 表                                                                           | 主键                               | 说明                                        |
| --------------------------------------------------------------------------- | -------------------------------- | ----------------------------------------- |
| `restaurants`                                                               | id SERIAL                        | 餐厅核心表（见下）                                 |
| `reviews`                                                                   | id UUID                          | 食客点评（只计堂食）                                |
| `cuisines`                                                                  | id SERIAL                        | 三维分类字典（菜系 / 食材 / 形式 / 标签 / 时段 / 认证）       |
| `restaurant_cuisines`                                                       | (restaurant\_id, cuisine\_id)    | 餐厅↔分类多对多，**无 id 列**                       |
| `chefs`                                                                     | id SERIAL                        | 主厨档案                                      |
| `restaurant_chefs`                                                          | (restaurant\_id, chef\_id, role) | 餐厅↔主厨任职关系                                 |
| `restaurant_awards`                                                         | id SERIAL                        | 米其林 / 黑珍珠等荣誉                              |
| `food_events`                                                               | id SERIAL                        | 动态 feed（新开店 / 搬迁 / 主厨更替 / 快闪…）            |
| `restaurant_groups`                                                         | id SERIAL (UNIQUE name)          | 餐饮集团 / 品牌矩阵                               |
| `restaurant_group_members`                                                  | (group\_id, restaurant\_id)      | 集团↔餐厅                                     |
| `price_band_thresholds`                                                     | (scene, band)                    | 各价格场景 5 带固定数值边界                           |
| `negotiations` / `price_benchmarks` / `sync_log` / `profiles` / `favorites` | —                                | 001 建的议价 / 价格锚点 / 同步心跳 / 用户 / 收藏（当前业务量很小） |

### 4.2 `restaurants` 关键字段与枚举



```
id, name, name\_en, aliases(text\[])

price\_avg(int), price\_range, tier(派生), business\_area(商圈), address, district

location GEOGRAPHY(POINT,4326)   -- PostGIS 坐标；REST 读写用 lng/lat，见 upsert\_restaurant RPC

phone, booking\_method, signature\_dishes JSONB\[]

\-- 反软广 / 工业化

chain\_type        TEXT  CHECK IN ('独立店','小型连锁','大型连锁','资本化连锁')

central\_kitchen   TEXT  CHECK IN ('无','疑似','确认')

premade\_risk      TEXT  CHECK IN ('无','低','疑似','高')

price\_position    TEXT  CHECK IN ('入门','主流','进阶','高端','旗舰')   -- 已停用，前端不再展示

price\_scene       TEXT  -- 正餐/快餐小吃/酒吧/咖啡茶饮/面包/甜品（管线回填）

price\_band        INT   CHECK 1..5（按 price\_band\_thresholds 由 price\_avg+scene 算）

is\_chain\_standardized BOOLEAN GENERATED ALWAYS (008，前端隐藏连锁/角标依据)

soft\_ad\_flag / soft\_ad\_flag\_reviews TEXT CHECK IN ('none','suspected','confirmed')

soft\_ad\_penalty   NUMERIC 0..30（派生：confirmed=25/suspected=10/none=0，禁止手填）

\-- 评分（四项 0..100）

score\_objective, score\_diner, score\_taste, score\_endorsement, score\_total(派生)

review\_count INT, review\_confidence NUMERIC(4,3) 0..1（口味贝叶斯置信度）

\-- 状态

status TEXT CHECK IN ('active','closed') DEFAULT 'active'

closed\_date, closed\_source  -- closed 时必填（ch\_rest\_closed\_triple）

\-- 010 新增

opening\_hours JSONB, open\_days TEXT, semantic\_description TEXT, chef\_name TEXT(反范式冗余)

selling\_points JSONB, last\_listened\_at, freshness\_due, taste\_prior\_source

data\_updated\_at DATE, created\_at, updated\_at
```

`tier` 派生规则（`tier_for_price`）：`<50 经济 / <100 平价 / <200 中档 / <500 高档 / else 奢华`。

### 4.3 关键约束（CHECK / 派生）



* `ch_rest_score_complete`：四项评分（objective/diner/taste/endorsement）**要么全有、要么全空**（NOT VALID，只拦新增 / 更新）。

* `ch_rest_coord_shanghai`：坐标要么空，要么 SRID=4326 且 `lng ∈ [120.80,122.20]`、`lat ∈ [30.65,31.95]`（上海 bbox）。

* `ch_rest_closed_triple`：status='closed' 必须同时有 closed\_date + closed\_source。

* `ch_rest_status`：只能 `active`/`closed`（前端勿用旧值 "推荐"）。

* `uq_rest_name_addr`：同名 (norm\_shop\_name)+ 同址 (norm\_addr) 唯一，仅约束有地址的店。

* `search_vector`：GENERATED ALWAYS tsvector（店名 / 英文名 A 权重、商圈 / 行政区 B、地址 C），数据库强制维护。

* `is_chain_standardized`：GENERATED STORED（008）。

### 4.4 触发器与派生（写库时数据库自动算，**勿手填**）



* `trg_restaurants_derive` (BEFORE INSERT/UPDATE) → `derive_restaurant()`：


  * `tier` 由 price\_avg 算；

  * `soft_ad_flag = greatest(chain硬信号, soft_ad_flag_reviews)`（非正餐豁免连锁扣分）；

  * `soft_ad_penalty` 由 flag 派生；

  * `score_total = round(0.35·score_taste + 0.25·score_objective + 0.25·score_diner + 0.15·score_endorsement − soft_ad_penalty, 1)`**，clamp\[0,100]**。

    （注：早期 002 文档写的是 0.4/0.3/0.2/0.1，已被 005 升级为 taste 核心的 0.35/0.25/0.25/0.15，以现网触发器为准。）

* `trg_reviews_taste` (AFTER reviews 增改删) → `recalc_taste_for(restaurant_id)`：口味分 = 时间衰减 (半衰期 180 天) + 贝叶斯收缩到**品类先验**(`cuisine_prior`，m=8)，只算 diner / 非软广 / 未隐藏评价；同时回写 `review_count`、`review_confidence`。

* `trg_awards_endorsement` (AFTER restaurant\_awards) → `recalc_endorsement_for`：背书分由荣誉派生（米其林三星 100 / 二星 90 / 一星 80，黑珍珠三钻 90 / 二钻 75 / 一钻 60，必比登 65，媒体 50，其他 40）。

### 4.5 RPC（幂等写入口，service\_role 专属）



* `upsert_restaurant(p jsonb)`：传 `{name, address, lng, lat, price_avg, ...}`，内部按归一名称 + 地址查存在则 UPDATE 否则 INSERT，所有触发器 / 约束生效。REST 端用 `POST /restaurants` 也可，但推荐 RPC。

* `recalc_taste_all()` / `recalc_endorsement_all()`：全库重算。

### 4.6 视图（前端只读）



* `v_feed_recent` / `feed_view`：首页动态 feed（event\_date 倒序，含 restaurant\_name/chef\_name）。

* `restaurant_detail_view`：详情聚合（cuisine\_arr/form\_arr/ingredient\_arr/awards/chefs/recent\_reviews）。

* `v_restaurant_enriched`：lng/lat + 菜系数组 + ugc\_count/ugc\_avg。

* `v_tag_coverage`：每标签挂店数（含 0 店漏挂）。

* `v_audit_gaps` / `v_data_freshness`：**仅 service\_role**（不向前端暴露缺口），stage4 体检用。

### 4.7 关键枚举速查



* `food_events.scope`: local/overseas/industry ｜ `category`: new\_open/relocated/closed/chef\_changed/guest\_kitchen/collaboration/popup/award/menu\_update/coming\_soon ｜ `confidence`: high/mid/low ｜ `status`: verified/rumor

* `reviews.review_kind`: diner/takeaway/press ｜ `trust_level`: high/mid/low

* `restaurant_awards.award_type`: michelin\_star/bib\_gourmand/black\_pearl/media\_show/other\_list

* `cuisines.dimension`: 菜系 / 食材 / 形式 / 标签 / 时段 / 认证



***

## ⑤ 数据管线全流程

**铁律：任何写数据任务禁止绕过脚本手拼 REST，必须走 skill 里的&#x20;**`scripts/food_pipeline/`**。** 模型只做 "发现 + 判断"，产出符合 `raw_place.schema.json` 的证据 JSONL；机械环节全部脚本化。

### 5.1 建库主流程（stage0 → stage7）



| stage | 脚本                         | 职责                                                |
| ----- | -------------------------- | ------------------------------------------------- |
| 0     | （人工 / 网格）                  | 把菜系拆成「细分叶子 × 档位」网格，每格定配额（中餐 = 地域子流派 × 品类双轴）       |
| 1     | `stage1_validate.py`       | 入库质量门：不合格打回                                       |
| 2     | `stage2_prepare.py`        | 实体对齐 / 标签解析 / 地理编码（dry-run 默认）                    |
| 3     | `stage3_upsert.py`         | 幂等写库 + 回读（默认 dry-run，`--commit` 才写）               |
| 4     | `stage4_audit.py`          | 全库只读体检 / 保鲜（查单店字段 / 硬伤）                           |
| 5     | `stage5_recalc.py`         | score\_total 漂移检测（total 现由 DB 触发器算，只读比对）          |
| 6     | `stage6_coverage.py`       | 网格覆盖审计（空格 / 薄格 / 薄证据 → coverage\_tasks.json 驱动回采） |
| 7     | `stage7_price_position.py` | 价格分位回扫（后被 009 price\_band 取代）                     |

### 5.2 小红书采集闭环（云端常驻）



```
reviews\_priority.json(1100家)

&#x20; → run\_batch.py（每20min，BATCH=15，flock 断点续跑）

&#x20;   → xhs\_collect.py（无头 Chromium + cookie 登录态，逐家采笔记）

&#x20;     → 落盘 research/atlas/xhs/raw\_xhs.jsonl

&#x20;   → xhs\_to\_reviews.py（全量重算 raw\_reviews；无口味信号词不打分）

&#x20;   → atlas\_write.py --domain reviews --commit（幂等入 reviews 表）

&#x20;     → DB 触发器 trg\_reviews\_taste 自动重算 score\_taste / review\_count
```

登录态失效时 `health.check_login` 探测 → Telegram / 飞书告警 → 本轮跳过（不硬刷）。

### 5.3 权威召回闭环



* `authority_sitemap.py`：拉米其林 sitemap 全量索引，与官方总数对账，产出 missing 清单。

* `authority_compare.py`：missing 店强制 "详情取证→够门槛入库"；近名异店排除、同名异址分店保留。

### 5.4 分类与补全脚本（skill/scripts/food\_pipeline/）



* `private_kitchen_detector.py`：会所 vs 私房菜拆分（010）。

* `signature_dish_classifier.py`：招牌菜分类。

* `semantic_profile_generator.py`：语义简介（菜系 + 商圈 + 荣誉 + 主厨 + 招牌菜 + 人均，已全库 1519/1519）。

* `opening_hours_collector.py`：从 evidence\_summary 正则提取营业时间（当前 69/1519）。

* `chef_tracker.py` / `build_chefs.py` / `finish_chefs.py`：主厨建档。

* `events_build.py` / `events_collect.py`：food\_events feed。

* `price_band_assign.py`：按 009 阈值表回填 price\_scene/price\_band。

* `nondiner_main.py`：非正餐识别（豁免连锁扣分）。

* `release_audit.py`：发版前只读串联各质量门。



***

## ⑥ 部署命令

### 6.1 前端（本地开发）



```
cd "/Users/hubowen/Desktop/桌面 - 胡博文的MacBook Pro/china-travel-food/app"

npm install        # node\_modules 已在，359M

npm run dev        # http://localhost:3000
```

### 6.2 前端（生产部署）



```
\# 本地推送 main，Vercel 自动构建（Root Directory 已设为 app）

cd "/Users/hubowen/Desktop/桌面 - 胡博文的MacBook Pro/china-travel-food"

git add -A && git commit -m "..." && git push origin main

\# 验收：Vercel 最新部署状态为 Ready；生产 https://app-lyart-eta-22.vercel.app
```

Vercel 环境变量需配 `NEXT_PUBLIC_SUPABASE_URL`、`NEXT_PUBLIC_SUPABASE_ANON_KEY`、`CRON_SECRET`（/api/sync 鉴权用）。`SUPABASE_SERVICE_ROLE_KEY` 也在 Vercel 配（/api/sync 心跳用）。

### 6.3 云端采集容器（**必须在服务器原生 amd64 构建**）



```
\# 一键脚本（本机执行，自动打包上传 + ssh 到服务器 build + compose up）

cd "/Users/hubowen/Desktop/桌面 - 胡博文的MacBook Pro/china-travel-food/cloud"

./build\_on\_server.sh
```

等价手动步骤（**勿在本机 arm64 build，勿用&#x20;**`docker compose build`）：



```
\# 1) 上传 cloud/ 上下文到服务器（含 vendor/pipeline、deploy.env、xhs\_cookies.json）

\# 2) ssh 到服务器：

ssh -i \~/.ssh/food\_cloud\_deploy ubuntu@49.234.35.92

cd /home/ubuntu/food-cloud

sudo docker build -t food-cloud:local .      # ★ 服务器原生 amd64 build

sudo docker compose up -d

sudo docker compose ps                        # 验证 food-cloud Up
```

服务器 SSH：`ubuntu@49.234.35.92`，私钥 `~/.ssh/food_cloud_deploy`，部署目录 `/home/ubuntu/food-cloud`。

### 6.4 云端 cron（容器内 `/app/cloud/crontab.txt`，entrypoint.sh 安装）



```
\*/20 \* \* \* \*  run\_batch.py          >> /app/data/cron.log        (小红书采集，flock /tmp/xhs.lock)

5,25,45 \* \* \* \* cloud\_phone\_fill.py >> /app/data/phone\_fill.log (电话补齐，错峰5min)

0 3 \* \* \*    cloud\_coord\_fill.py    >> /app/data/coord\_fill.log (坐标补齐，每日)

0 4 \* \* \*    cloud\_hours\_fill.py    >> /app/data/hours\_fill.log (营业时间补齐，每日)

15,35,55 \* \* \* cloud\_amap\_fill.py --apply >> /app/data/amap\_fill.log (高德全字段，取代旧 review\_fill)
```

全部 `. /app/cloud/env.sh`（cron 不继承 docker -e，由 entrypoint.sh 固化）+ `flock -n` 防重叠。

### 6.5 数据库迁移



```
\# Supabase Dashboard → SQL Editor → 按文件名顺序粘贴执行（幂等可重跑）

db/migrations/001\_init.sql

db/migrations/002\_harden.sql

... 依次到 ...

db/migrations/010\_chef\_group\_hours\_events.sql

\# DDL 无法走 REST，只能 SQL Editor。
```



***

## ⑦ 环境变量清单与凭据位置

> **严禁明文 token/secret/service role**
>
> 。下表只列变量名与读取位置。



| 变量名                                                                                                               | 用途                                          | 读取位置                             |
| ----------------------------------------------------------------------------------------------------------------- | ------------------------------------------- | -------------------------------- |
| `NEXT_PUBLIC_SUPABASE_URL`                                                                                        | Supabase 项目 URL                             | `app/.env.local`（前端 + 本地管线共用）    |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY`                                                                                   | 前端公开 anon key                               | `app/.env.local`                 |
| `SUPABASE_SERVICE_ROLE_KEY`                                                                                       | 服务端写库密钥（绕过 RLS）                             | `app/.env.local`；云端 `deploy.env` |
| `FOOD_APP_DIR`                                                                                                    | 覆盖默认 app 目录（common.py 找 .env.local）         | 本地可选，默认仓库 app/                   |
| `XHS_COOKIE_FILE`                                                                                                 | 小红书登录态文件路径（容器内 `/secrets/xhs_cookies.json`） | 云端 `deploy.env`                  |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` / `TELEGRAM_API_BASE`                                                   | cookie 失效 / 任务完成告警                          | 云端 `deploy.env`                  |
| `FEISHU_WEBHOOK` / `FEISHU_SECRET` / `FEISHU_APP_ID` / `FEISHU_APP_SECRET` / `FEISHU_CHAT_ID` / `FEISHU_API_BASE` | 飞书机器人告警                                     | 云端 `deploy.env`                  |
| `ALERT_WEBHOOK` / `ALERT_COOLDOWN_SEC`                                                                            | Bark/Server 酱兜底告警、冷却                        | 云端 `deploy.env`                  |
| `BATCH`                                                                                                           | 每轮采集店数（默认 15，从10提速）                      | 云端 `deploy.env` / compose        |
| `AMAP_KEY`                                                                                                        | 高德 Web 服务 key（全字段采集，无 SK/sig）             | 云端 `deploy.env`                  |
| `CRON_SECRET`                                                                                                     | Vercel /api/sync 心跳鉴权                       | Vercel 环境变量                      |

**凭据文件位置**：



* 本地前端 + 管线：`app/.env.local`（3 个 Supabase key）。根目录 `.env.local` 是 Vercel CLI 的 OIDC token，与管线无关。

* 云端：容器内 `/app/cloud/env.sh`（entrypoint.sh 从环境变量固化生成，cron source 它）；构建期 `cloud/deploy.env`（compose `env_file`）；小红书 cookie 只读挂载 `/secrets/xhs_cookies.json`（宿主机 `cloud/xhs_cookies.json`）。

* 模板：`app/.env.local.example`、`cloud/deploy.env.template`。

`.gitignore`**&#x20;应包含**（现状已含）：`node_modules/`、`.next/`、`.env*.local`、`.env`、`.vercel/`、`*.tsbuildinfo`、`app/public/sw.js`+workbox-\*.js、`__pycache__/`、`.venv/`、`/backups/`、`/data/`、`/pipeline_work/`、`/data_subagent_work/`、`/geocode_progress/`、历史一次性 `build_*.py`/`push_*.py`、`*.bak`。



***

## ⑧ 当前进度、关键数字与已知缺口（2026-09-26 实测）

**规模**：餐厅 **1521**（active 1514 / closed 7）、reviews **136** 条、主厨 **56** 位、餐饮集团 **10** 个、food\_events **25** 条、cuisines 标签 **346**、restaurant\_awards **157** 条。

**最大短板 —— 评价覆盖**：



* `review_count=0` 的店约 **1459 家**（1519 中仅 60 家有评价），云端小红书采集推进中。

* 云端已采 **614/1100**（优先级清单 `reviews_priority.expanded.json`），BATCH 从 10 提至 **15**（300031 零触发后提速 50%），剩余约 486 家待采。

* 高端 / 奢华店（price\_band 4-5 共 404 家）几乎 0 评价；欧洲菜 / 湘菜 / 闽菜 / 融合菜是空白区。

* **新来源（2026-09-26 P0-1，已升级见⑧.8）**：
  * 旧 `cloud_review_fill.py`（只补评分、错误 sig）**已被 `cloud_amap_fill.py` 取代**（cron 第5条，:15/:35/:55）：一次高德 place/text extensions=all 同时回填评分/人均/电话/营业时间/坐标，地址锚定锁定正确分店；AMAP_KEY 已配、端到端写库验证通过。
  * 腾讯位置服务 WebService API **不返回评论文本/评分**（已实测：search/detail 仅返回 POI 基本字段），不可用于评价采集。
  * 大众点评强反爬 + 登录墙，REST 不可行；需登录态 RPA 时 blocked=auth 再找用户。

* **visit_date 已接入**：`xhs_to_reviews.py` 现解析笔记日期写入 `visit_date`，DB 触发器 trg\_reviews\_taste 时间衰减（半衰期180天）据此回算。新增评价自动带 visit_date；历史 136 条不回溯。

**字段完整率**（来自 audit-semantic-hours-2026-09-26）：



* ✅ name/address/district/signature\_dishes/price\_avg/tier/semantic\_description(100%, 1521/1521)

* ⚠️ 坐标 99.7%（6 家无坐标：id=1854,1939 待核实；1985-1988 已于本轮用腾讯 place suggestion 补齐）

* ⚠️ 电话 67.0%（约 502 家无电话，云端 `cloud_phone_fill.py` 每小时 :05/:25/:45 补，腾讯 place suggestion 精确锁定分店）

* ⚠️ 营业时间仅 69 家（4.5%，云端 `cloud_hours_fill.py` 每日补）

* ⚠️ chef\_name 反范式列空（restaurant\_chefs 有 56 位主厨但未回写冗余列）

* ✅ 评分四项 99.8%（3 家无评分）

**分类与收录**：



* 会所 3 家 / 私房菜 14 家已拆分；裕莲茶楼分类已修正。

* **Ministry of Crab 已入库（id=2002）**，评分 82.3，地址 / 电话 / 坐标 / 招牌菜 / 语义简介齐全，仅营业时间待补。

* **EIGHT UNDER（rid=1905）已确认为用户说的「八by8/8byeight」**：徐汇区永康路73号，主厨 Gabo，Chifané 跨文化创意菜（麻酱油泼辣子意面、鸭cannelloni担担酱），aliases 已补 ["八eight","EIGHT","8by8","八by8"]，融合菜/私房菜标签齐全。

* 米其林 0 缺失（sitemap 对账闭环）；黑珍珠 7 家证据不足待补。

**其他**：`score_taste` 对单条评价做了贝叶斯收缩（n=1 的 5 星不给 100，给～80）；软广事后扫描 21 条命中经人工复核无一例确证，`is_fake_suspect=0`。大众点评未接入（强反爬 + 登录墙，REST 不可行；需登录态 RPA 时 blocked=auth 再找用户）。高德评分采集脚本 cloud_review_fill.py 已就位，待配置 AMAP_KEY/AMAP_SK 后自动启动。

### ⑧.5 负面清单三字段跑全（2026-09-26 P0-3，已完成）

`chain_type / central_kitchen / premade_risk` 三字段**非 NULL 率 100%（1519/1519）**。枚举以库 CHECK 约束为准（非任务书里的"直营/加盟/有/中"字样，那些是示意）：

```
chain_type      : 独立店 1242(81.8%) / 小型连锁 209(13.8%) / 大型连锁 61(4.0%) / 资本化连锁 7(0.5%)
central_kitchen : 无 1308(86.1%) / 疑似 185(12.2%) / 确认 26(1.7%)
premade_risk    : 无 1308(86.1%) / 低 171(11.3%) / 疑似 17(1.1%) / 高 23(1.5%)
is_chain_standardized(派生): true 210 / false 1309   ← 前端"隐藏连锁/预制"开关过滤的就是 true 且非正餐的店
```

**做法**：
- 批量：1231 家 `chain_type=独立店 且 ck/pr 均 NULL` 一次过滤 PATCH 为 `ck=无, pr=无`（独立小店无中央厨房无预制，`is_chain_standardized` 仍为 false，不被隐藏）。
- 人工：21 个 chain_type=NULL（7 关店 + 14 家 id≥1989 新店）+ 3 个 pr=低 异常独立店，逐家看 evidence_summary 判定，共 24 条 PATCH。
- 写前备份：`backups/negative_fill_2026-09-26/restaurants_3fields_before.json`（1519 行）。
- 脚本：`food_pipeline/fill_negative_fields.py`（dry-run / `--commit`，只 PATCH 这三列）。

**用户点名店（已全部正确标记，std=true 可被隐藏）**：小菜园=资本化连锁/确认/高；望湘园=大型连锁/确认/高；盖饭邦=大型连锁/确认/高；FAT PHO 大發越南粉=小型连锁/疑似/低；西贡妈妈 Saigon Mama=小型连锁/疑似/低。

**前端"隐藏连锁/预制"端到端验证（线上实测）**：`app/pages/restaurants/index.tsx` L310 `if(hideChain) result=result.filter(r=>!r.is_chain_standardized||isNonDiner(r))`，取数 `select='*'` 含派生列，逻辑正确、无需改码部署。线上 https://app-lyart-eta-22.vercel.app/restaurants 实测：搜"小菜园"默认显示 2 家（带"预制菜/连锁"角标）→ 点"隐藏连锁/预制"→ 0 家"没有找到"；关闭后御宝轩/Da Vittorio/8½ Otto 等独立高端店正常保留。非正餐（咖啡/面包/甜品/Bar/茶饮）即使连锁也被 `isNonDiner` 豁免不隐藏。

**已知缺口/保守判定**：
- 14 家 id≥1989 新店中，横县鱼生连锁（渔八公/粤桂發）、胡老头鱼丸、少山集/隐溪/黄庭茶馆 按"现做/茶饮、无中央厨房"标 `小型/大型连锁 + ck=无 + pr=无`，故 `is_chain_standardized=false` 不被隐藏——这是有意为之（现做多店、茶饮业态），非漏标。
- 高端餐饮集团（新荣记/甬府/大董/鲁采等）多店但 ck=无/pr=无，std=false 保留入精选。
- 24 家人工判定里关店 7 家的连锁分级仅为补齐枚举，不影响线上（status=closed 本就不展示）。



### ⑧.6 方法论回滚·八大菜系（2026-09-26 P0-2，第一批完成）

**核心机制修复：第二轴（品类/店型）叶子从 0 到 14**

此前八大菜系只有地域子流派叶子，火锅/串串/冒菜/小面/早茶/烧腊等店型完全没有独立叶子。本批新建 14 个 dimension=菜系 的第二轴叶子（id 355-368，355重庆火锅此前已存在）：

| 叶子 | 归属 | 现挂店数 |
|---|---|---|
| 重庆火锅(355) | 川菜 | 5 |
| 串串香/冷锅串(356) | 川菜 | 5 |
| 冒菜/麻辣烫(357) | 川菜 | 2 |
| 川味面馆(358) | 川菜 | 12 |
| 烤鱼/酸菜鱼专门(359) | 川菜 | 8 |
| 广式早茶点心(360) | 粤菜 | 4 |
| 潮汕牛肉火锅(361) | 粤菜 | 8 |
| 潮汕打冷/生腌排档(362) | 粤菜 | 5 |
| 砂锅粥/粿条(363) | 粤菜 | 4 |
| 苏式汤面(364) | 苏菜 | 7 |
| 淮扬茶社/细点(365) | 苏菜 | 5 |
| 胶东海饺/面点(366) | 鲁菜 | 13 |
| 闽菜Fine Dining(367) | 闽菜 | 9 |
| 湖南米粉(368) | 湘菜 | 8 |

**现有店回挂 93 条** `restaurant_cuisines`（手工 curated，只挂主营店型明确的专门店，避免正则过度触发把高端粤菜馆误标烧腊）。备份 `backups/second_axis_leaves_before.json`。

**新增店 2 家（走完整管线 stage1→stage2→stage3）**：
- 蜀南面馆（rid=2003，闵行莘沥路39-43号，宜宾燃面，《孤独的美食家》五郎打卡，川南·宜宾菜+川味面馆）
- 觉味燃面（rid=2004，浦东商城路2000号，开了15年的宜宾苍蝇馆子，川南·宜宾菜+川味面馆）
两家坐标已用腾讯 place suggestion 补齐，评分四项齐全。

**stage6 覆盖审计结果**：active 1514 家，**空格 0**，薄格 10（川菜5：冒菜/海派改良/内江/泸州/绵阳；浙菜1：金华衢州；闽菜1：闽北；广西1：桂林米粉；河南1：开封洛阳；创新菜1），深采任务 10 项。川菜叶子从 11 增至 16，川南·宜宾菜从 2 家增至 4 家。

**回归用例核验**：鸟鸟(id=1434)✓、张记川味苑(id=601,已挂川南·宜宾菜)✓、帅帅(id=1892)✓、聪菜馆(id=1843)✓、nagi凪(id=1887)✓。鮨照/Proustmoment/time&flour 属日料/面包批，留待下一批。

**教训**：正则自动挂标签会过度触发（云南火锅/台湾牛肉面/上海面馆被误收），必须手工 curated 主营店型；stage1_validate.py 全库实体匹配可能超时，需加 watchdog 超时保护。

### ⑧.7 模糊召回/口述逼近层（2026-09-26，机制新增）

已写入 `references/discovery-playbook.md` §7（v2.2），解决"精确关键词=0就放弃"的缺陷：
- **店名归一扩展**：数字↔英文↔中文互转（8↔eight↔八）、去连接符、分店名剥离、中英文混排、口述变体
- **召回=0时的模糊扩展流程**：归一扩展→叠加地标→叠加主厨/形态→UGC评论区反查→待核实标注
- **候选多信号排序**：店名30%+地址25%+主厨20%+菜系15%+热度10%，阈值<0.6不确认
- **库内别名联动**：`restaurants.aliases` JSONB 数组存储口述名，检索时匹配 name+name_en+aliases
- 触发案例：用户说"8by8"→库内 EIGHT UNDER(rid=1905)，aliases 已补全

### ⑧.8 高德统一全字段采集（2026-09-26，已部署，取代旧 cloud_review_fill）

**一次 place/text（extensions=all）同时回填 评分+人均+电话+营业时间+坐标**，替代此前腾讯/高德分散、旧 cloud_review_fill 带错误 sig、只补评分的方案。脚本 `cloud/cloud_amap_fill.py`（容器 /app/cloud）。

**店名↔POI 匹配引擎（地址锚定优先，宁 hold 不错配）**：
- `amap_text`：返回全部 POI 不预过滤（地名/非餐饮在 match 阶段排除）；限流指数退避，infocode 10003=日配额(5000)超限立即停并告警；间隔≥0.4s。
- `is_dining_poi`：以高德 keytag 语义为主（不硬编码 typecode 大类，因 08 含酒吧/部分蛋糕）；地名 POI 硬排除。
- `split_name/core_norm`：拆主名+括号、跨字形归一、ramen=拉面、近形（膳/善）。
- **地址锚定（核心）**：库有具体地址/地标或锁分店时，候选必须地址/分店/地标一致（confirm≥0.9）：
  - `road_number`：先去开头行政区（含"区"），枚举路名，对门牌号取前方间隙≤4 且不跨越"路/街/道"的最近路名（治"江苏路街道凯旋路1398"误锚江苏路）。
  - `addr_anchor`：同路名 + 门牌号交集/号段范围重叠（189-193 vs 191-193）/原始 sim≥0.8 → confirmed≥0.9；路名不同（错分店）→ 排除。
  - 强确认(0.95)时店名 ratio 放宽到 0.4（治"拉面满吉/满吉拉面"语序相反）；否则 ratio≥0.55。
  - 地标 LANDMARKS（龙之梦/来福士/恒隆/合生汇…）；库只有泛区域（"古北地区"）靠主名+业态，泛品牌不采。
- 只补空：price_avg（tier 触发器算）、phone（过 clean_phone）、opening_hours({raw})、location(point_ewkt+in_shanghai)；评分→reviews（高德地图, trust_level=low）；keytag/tag 仅线索不改菜系。
- 当天 POI 缓存（rid+日期）+ 断点 + 配额计数；默认 dry-run，`--apply`/`--limit`。

**实测（正确分店，无一错配）**：御千代(rid4)→诺雅 凯旋路1398长宁国际T8（非信联公寓）；酉町(rid8)→番禺路390；满吉(rid20)→广元西路（非前滩晶耀）；小景门(rid10)→招商局广场；晚餐馆(rid16)→古北金狮花园；天天天妇罗(rid36)→五角场合生汇；天嘉(rid37)→虹梅路3194；一滨(rid45)→世博天地。rid1939 北外滩私宴（地址"预约后告知"）正确 hold、不锚地名。

**部署**：AMAP_KEY 已写入云端 deploy.env（env_file 传入、env.sh 固化）；Dockerfile COPY 加 cloud_amap_fill.py；crontab 第5条由 cloud_review_fill 改为 `cloud_amap_fill.py --apply`（:15/:35/:55，flock /tmp/amap_fill.lock）。容器 dry-run 与 `--apply --limit 10` 均实测通过、字段落库。全库缺营业时间(~1445)/电话(~499) 在 5000/天配额内 1 天左右补全。

### ⑧.9 sourcing 开放式发现闭环工程化 + 高德队列/匹配修复（2026-09-26，本轮）

**(1) 开放式发现闭环五模块（已离线端到端测试 + 上云部署）**。治"文档完整、实现不完备"的五个断点（云端只取证不发现、发现词只覆盖 6 品类、静态词表无自生成/图遍历、评论区线索无闭环、admit 无自动收录）：

| 模块 | 位置 | 职责 |
|---|---|---|
| `discovery_keywords.py` | PIPE | 全品类发现词矩阵自动生成器：8 通用句式 + SUB/REGION/EN 模板，配每品类 CATEGORY_SPEC（约 40 品类）；含 **CUISINE_ROOT**（category→菜系根名，gate/apply 共用，避免映射散落）。验证计数 sichuan 31 / ramen 20 / bread 21。 |
| `discovery_engine.py` | PIPE | 自驱动图遍历 DiscoveryEngine：种子入 frontier → 采集→raw_discovery→_ingest 识别品牌并扩展 frontier（合集锚点入 high、品牌长别名、评论区品牌、"明确推荐另一家"5 条 RE_REC、英文专名≥2 提及入 high、口述 SHOP_SUFFIX/重复≥2 入 low，否则 oral）；状态 engine_<cat>.json 断点续跑，frontier 清空才判饱和。离线识别鸟鸟/张记/宜宾燃面并追查到底。 |
| `admission_gate.py`（v3 全品类参数化） | PIPE | load_db 用 CUISINE_ROOT 定位菜系子树；verdict：is_cat（section/品类标签/item≥1）+ 阈值（独立声音≥2、item≥1、均分≥3.5；<3.3 淘汰、3.3–3.5 hold；全好评 admit* 降置信；单一博主无食客交叉 hold；closed reject）。RE_PIN 贪婪 bug 已修。 |
| `candidate_apply.py` | cloud | admit/admit* 且库外新店自动收录：amap_text 找餐饮 POI → pick_new_poi 锁唯一高分（差距<0.12 返 AMBIG 转 hold、top<0.6 返 None）→ build_fields 组装（phone 过 clean_phone、location EWKT+in_shanghai，宁空不假）→ name+addr_core 幂等回查 → POST 拿 id → tag_cuisine 挂根标签。默认 dry-run。 |
| `cloud_discover.py` | cloud | 云端总编排：discover_state.json 维护 40 品类队列（先中餐八大+本帮京菜，再日料细分/亚洲/西餐，最后非正餐与场景）；每品类 Engine.run→未饱和下轮续，饱和→gate 裁决→apply 收录→双通道告警。cron 第6条（:25，flock discover.lock）。 |

**(2) 小红书搜索账号级风控（300011，当前卡点）**：搜索整页跳 `website-login/error?error_code=300011 当前账号存在异常，请切换账号`（标题"安全限制"），任何关键词 0 卡片；explore 首页正常、登录态有效。**非 DOM/选择器 bug，是账号级搜索风控**。处置：`health.py` 新增 check_search / mark_search_restricted / clear / search_recently_restricted（标记文件 `/app/data/SEARCH_RESTRICTED`，冷却 SEARCH_RETRY_SEC=3 小时自动复检），已接入 run_batch 与 cloud_discover，冷却窗口内不开浏览器直接跳过并双通道告警。**解封依赖用户提供第二个账号 cookie 做账号轮换（推荐，多 cookie 承载机制尚未实现）或等待**。

**(3) 高德"0 回填"两类底层修复（已实测回填增长、已编译进持久化镜像）**：
- **队列饿死**：缺字段最多的难匹配店每轮排最前、主搜+3 级降级可烧 4 次调用，37 家 no_match 持续烧光每轮预算、队列无法推进。修复：state 新增 per-rid `fail` 计数（no_match 自增、匹配即 pop，每日配额重置时保留），候选排序改为 `fail_bucket`（0 次=0、1–2 次=1、≥3 次=2 沉底）+(-missing,id)。
- **match_poi 过严误拒正确 POI**：新增 ① `name_score()`——剥 POI 尾部业态/菜品词（FOOD_TAIL，剥完≥3 字）+ 近音字归一（HOMO_CANON：膳/善、庭/亭、轩/萱、堂/唐、记/纪、城/成、园/元/缘/源、居/局、焙/培、合/和、味/未、渔/鱼、鲜/仙、茶/查、烤/考）+ 包含/序比取最大；② `primary_road()`——独立于门牌号提取去行政区后的第一条路/街/大道；③ 通用商场锚 `mall_token/mall_hit`（XX广场/商场/中心/天地/万象城…，不依赖手写 LANDMARKS）。锁定分支确认改为：强地址/分店/地标/商场 confirm≥0.9 时店名门槛 0.4/0.55；**否则同名（name_score≥0.85）+ same_road（primary_road 一致）也可确认**。修复后正确匹配：rid39 尚膳天焱→尚善天焱(龙之梦)、rid470 惠中川香蛙(嘉善路)、rid512 天水雅居(滨江)；并正确拒绝 rid455 误匹配到环宇城的错商场分店。
- 已考虑未实现：地址为地标且主搜空时 resolve 已加"主名+地标"补搜（哲平鳗满+正大，实测高德确无该店则宁空）。

**(4) 凭据持久化教训（重要，已加入 release 清单 #14）**：`build_on_server.sh` 第 24 行会用**本地 cloud/deploy.env 覆盖服务器同名文件**，此前直接在服务器追加的 AMAP_KEY/TG/飞书凭据在重建后全部丢失。**权威 deploy.env 必须维护在本地 cloud/deploy.env（gitignored、不入库）**，本轮已把高德/TG/飞书全部凭据补入本地文件，此后构建自动携带。

**(5) 本轮覆盖率变化（active 1514）**：电话 68%→**73.4%（1111）**；营业时间 6%→**11.9%（180）**；坐标 **99.9%（1513，缺1）**；有评价店升至 **175**。高德 cron（:15/:35/:55，--apply）持续推进，电话/营业时间当日内继续补齐。

> **凭据恢复后复验（2026-09-26，凭据曾因容器重建短暂丢失、已修复）**：重建容器一度带空凭据（AMAP_KEY 未配置），已把高德/TG/飞书全部凭据确认在**本地 cloud/deploy.env（权威、gitignored）**并 scp + compose up 重生效。手动 `cloud_amap_fill.py --apply --limit 60` 实测：60 调用回填 **37 字段 / 20 评分评价**，未匹配从修复前 37 降到 **11**，匹配修复与 fail 沉底端到端确认有效。新教训已沉淀至 lessons-learned #66/#67/#68。



***

## ⑨ 一键复现步骤



```
\# 0) clone 仓库后进入

cd "/Users/hubowen/Desktop/桌面 - 胡博文的MacBook Pro/china-travel-food"

\# 1) 装前端依赖

cd app && npm install

\# 2) 配置密钥：复制模板填真实值

cp .env.local.example .env.local

\#   编辑 .env.local 填入 NEXT\_PUBLIC\_SUPABASE\_URL / NEXT\_PUBLIC\_SUPABASE\_ANON\_KEY / SUPABASE\_SERVICE\_ROLE\_KEY

\# 3) 本地跑前端

npm run dev          # http://localhost:3000

\# 4) 连接数据库验证（用 skill 共享层，已实测可跑）

SKILL="/Users/hubowen/Library/Application Support/Doubao/Default/.doubao/agent\_mode/workspace/.user\_skills/city-food-guide"

python3 -c "

import sys; sys.path.insert(0, '\$SKILL/scripts/food\_pipeline')

import common as C, requests

h=C.headers(); h\['Prefer']='count=exact'

for t in \['restaurants','reviews','chefs','food\_events','cuisines']:

&#x20;   r=requests.get(f'{C.BASE}/{t}', params={'select':'id','limit':1}, headers=h, timeout=30)

&#x20;   print(t, r.headers.get('content-range'))

"

\# 预期输出：restaurants 0-0/1519、reviews 0-0/136、chefs 0-0/56、food\_events 0-0/25、cuisines 0-0/332

\# 5) 继续采集：确认云端容器在跑（cron 自动推进，无需本机干预）

ssh -i \~/.ssh/food\_cloud\_deploy ubuntu@49.234.35.92 \\

&#x20; "sudo docker compose ps && tail -5 /home/ubuntu/food-cloud/data/cron.log"

\# 6) 补齐数据：云端 cron 已自动跑 phone/coord/hours fill；本机可手动跑 stage 审计

cd "\$SKILL/scripts/food\_pipeline" && python3 stage4\_audit.py        # 只读体检

cd "\$SKILL/scripts/food\_pipeline" && python3 stage6\_coverage.py    # 网格覆盖

\# 7) 前端部署：git push main → Vercel 自动构建

cd "/Users/hubowen/Desktop/桌面 - 胡博文的MacBook Pro/china-travel-food" && git push origin main
```



***

## ⑩ 独立回验方法与 release regression 清单

### 10.1 数据回验（REST / SQL）



```
\-- 数量

SELECT count(\*) FROM restaurants;                       -- 1519

SELECT count(\*) FROM restaurants WHERE status='active'; -- \~1512

SELECT count(\*) FROM reviews;                           -- 136

\-- 维度覆盖缺口（service\_role 才能查）

SELECT issue, count(\*) FROM v\_audit\_gaps GROUP BY issue ORDER BY 2 DESC;

\-- 保鲜

SELECT count(\*) FROM v\_data\_freshness WHERE stale;

\-- 评分漂移（应为 0）

SELECT count(\*) FROM restaurants WHERE score\_total IS NOT NULL

&#x20; AND abs(score\_total - greatest(0,least(100,round(

&#x20;     0.35\*score\_taste+0.25\*score\_objective+0.25\*score\_diner+0.15\*score\_endorsement

&#x20;     -coalesce(soft\_ad\_penalty,0),1))))>0.1;

\-- 无坐标营业店（应为 6 家）

SELECT id,name FROM restaurants WHERE status='active' AND location IS NULL;
```

REST 速查：`GET /restaurants?select=id&limit=1` 看响应头 `content-range` 总数。

### 10.2 前端验收（以浏览器真实渲染为准，`next build` 通过不算完）



* 首页统计数字、根 / 二 / 三级菜系导航（**动态从 cuisines 表构建，无硬编码**）。

* 亮点标签筛选（米其林 / 黑珍珠 / Off Menu / 纯素 / 分子）。

* 列表页排序、价格带区间标签（price\_band\_thresholds）。

* 详情页：语义简介、营业时间、内嵌 Leaflet 地图（瓦片 + marker）、荣誉 / 主厨 / 最近评价。

* 地图页聚合（ClusterGroup）、Feed 事件 Modal（EventModal）。

* 改了前端先注销 PWA service worker + 清缓存再判断。

### 10.3 云端验收



```
ssh -i \~/.ssh/food\_cloud\_deploy ubuntu@49.234.35.92

sudo docker compose ps                       # food-cloud Up, restart=always

tail -20 /home/ubuntu/food-cloud/data/cron.log       # 采集进度

tail -5 /home/ubuntu/food-cloud/data/phone\_fill.log  # 电话补齐

docker exec food-cloud crontab -l            # 4 条 cron 在
```

### 10.4 release regression 通识清单（历次踩坑汇总，发版前逐条过）



1. **iCloud&#x20;**`.next`**&#x20;锁定**：`app/.next` 若为 iCloud dataless 占位目录，删除报 `EDEADLK/Resource deadlock avoided` 时**勿硬删**，等它落地或忽略（gitignored，不影响部署）。本次整理中 `__t_root`/`data_subagent_work`/`geocode_progress`/`cloud/__t_cloud`/`cloud/chunks` 即此类空占位目录，删不掉属正常，已在本档注明。

2. **PostgREST 204 / 空响应**：带错误 header 或 select 不存在列会 400；`Prefer: count=exact` 才返回总数。

3. `restaurant_cuisines`**&#x20;无&#x20;**`id`**&#x20;列**：复合主键 `(restaurant_id,cuisine_id)`，客户端拉取必须 `order=restaurant_id`，否则 400 且 `Promise.all` 整体 reject、整页静默归零。

4. **枚举值以库 CHECK 约束为准**：status 用 `active/closed`，勿用旧值 "推荐"；加载失败要让错误上浮，不渲染空壳。

5. **虚拟根 8 个**：中餐 / 亚洲 / 欧洲 / 非洲 / 北美洲 / 南美洲 / 融合菜 / 非正餐是虚拟根（cuisines 表无同名行），URL `?cuisine=` 定位、点根筛选、二三级展开都要先判虚拟根。

6. **坐标 EWKT/GeoJSON**：DB 存 `GEOGRAPHY(POINT,4326)`；写库走 `upsert_restaurant` 传 `lng/lat`（RPC 内部 `ST_SetSRID(ST_MakePoint(lng,lat),4326)`），勿手拼文本。

7. **评分四项全有或全无**：`ch_rest_score_complete` 约束；不完整时 `score_total` 自动为 NULL，不展示官方分。

8. **大表分页**：restaurant\_cuisines 约 1.4 万行，客户端分页十余页、首屏数秒属正常，勿误判死循环。

9. **PWA 残留**：曾因残留旧 workbox 致 build 失败；`app/public/sw.js` 等已 gitignore，每次构建重新生成。

10. **云端 build 必须服务器原生 amd64**：本机 arm64 构建跨架构跑不起来；用 `build_on_server.sh`，勿用 `docker compose build`。

11. **cookie 失效**：小红书 cookie 会过期，health 探测失效后告警并跳过，需人工重新导出 `xhs_cookies.json` 重新部署。

12. **写库不手填派生列**：tier/score\_total/soft\_ad\_flag/soft\_ad\_penalty/is\_chain\_standardized/review\_count/review\_confidence 全由触发器生成，手填会被覆盖或破坏一致性。

13. **compose 无 build 段**：docker-compose.yml 只写 `image: food-cloud:local`、无 `build:`，故 `docker compose build` 空操作、`up` 沿用旧镜像；更新代码必须显式 `sudo docker build -t food-cloud:local .` 再 `compose up -d`。

14. **build 会用本地 deploy.env 覆盖服务器凭据**：build_on_server.sh 上传本地 cloud/deploy.env 覆盖服务器同名文件，直接在服务器追加的键重建即丢；所有凭据（AMAP_KEY/TG/飞书）必须维护在本地 cloud/deploy.env（gitignored），勿只在服务器手改。

15. **小红书搜索风控 300011 ≠ 登录失效**：搜索跳"安全限制/当前账号异常"但 explore 正常是账号级搜索风控，check_search 落标记、3 小时冷却复检，勿在窗口内硬刷；恢复靠换账号 cookie 轮换。

16. **高德队列防饿死**：难匹配店用 fail 计数沉底（fail_bucket），否则每轮预算被同一批 no_match 烧光、队列不推进；店名匹配用 name_score（剥业态后缀+近音字），同名同路即可确认，不靠门牌号一刀切。

17. **多账号 cookie 轮换已落地（300011 的工程解，2026-09-27）**：新增 `cloud/xhs_cookie_pool.py`（账号池 + 按账号状态/冷却，状态持久化 `/app/data/_cookie_pool_state.json`）与 `cloud/cloud_ready.py`（轮换开浏览器：登录失效/搜索风控/无卡片 → 标记该号、关浏览器、自动切下一个；全不可用才告警一次）。`health` 的标记/冷却函数委托 cookie 池（唯一真相源），`run_batch`/`cloud_discover` 改为经 `cloud_ready.open_ready_browser` 拿可用号。账号目录 compose 只读挂载 `/secrets/xhs_accounts`（本地 `cloud/xhs_accounts/`，gitignored），每文件一号（`account_a.json`/`account_b.json`，形态见 `cloud_bu.load_cookies_from_text`）；**加号 = 往目录丢一个 json，零改代码、无需重建镜像**。无账号目录时回退旧单账号（id=default）。冷却 `ACCOUNT_RETRY_SEC` 默认 3 小时。已实测：单号被风控 → 标记 restricted + 全不可用告警一次（TG/飞书均成功），不硬刷；高德 cron 不受影响。



***

## 附：本次项目整理记录（2026-09-26）



* **整理前体积**：592M（其中 app/node\_modules 359M、app/.next 102M、.git 93M，均为 gitignored / 版本控制目录，未动）。

* **整理动作**：


  * 新建 `archive/`，移入 24 个根目录历史过程稿（audit-2026-09-22/23 共 10 份、coverage-\* 共 10 份、coverage-tasks\*.json 3 份、cross\_cuisine\_report.\* 4 份），共约 380K。

  * 根目录只保留最新两份报告（`review-coverage-report-2026-09-26.md`、`audit-semantic-hours-2026-09-26.md`）+ `reviews_priority.expanded.json` + README/DEPLOY。

  * 尝试删除空临时目录 `__t_root`、`data_subagent_work`、`geocode_progress`、`cloud/__t_cloud`、`cloud/chunks`，全部报 `EDEADLK (Resource deadlock avoided)`—— 系 iCloud dataless 占位空目录，**按约定不硬删，留空占位**。

  * `cloud/.venv`、`cloud/.venv312` 为空 venv 骨架（gitignored），保留。

  * `app/.next`（102M）为真实构建缓存（非 iCloud 占位，含 cache/server/static），gitignored，**保留不删**（删了会触发下次 `npm run build` 全量重建）。

  * `research/`、`data/`、`backups/`、`pipeline_work/` 为工作数据区，未动。

* **整理后体积**：仍为 592M（大头是 node\_modules/.next/.git，本就不该入库；过程稿仅 380K 移到 archive，净释放可忽略）。根目录文件从 20+ 个过程稿精简到 5 个根级 md/json + 配置。
## 2026-09-27 店名抽取精度修复 + unmatched 闭环 + 城市闸门

### 根因（用户审计 candidates_*.jsonl 确认）
旧 admission_gate 把菜名/路名/泛词/元话术/外地城市名误抽成 brand，导致 190 条 unmatched 线索 0 收录：
resolve_anchor_name/pin_name 的兜底「任意≥3字即收」是漏勺；GENERIC_ANCHOR 只有面包词无负样本；无城市闸门（B站/小红书搜「上海X」返回大量长沙/珠海/北京视频照单全收）。

### 修复（确定性函数在 common.py）
- `common.looks_like_brand(token) -> (bool, reason)`：菜名/路名/泛词/元话术/外地城市/整句/过长(>14) 一律拒；带店后缀或短 token(2-6字) 放行，下游门槛再过滤。
- `common.note_is_out_of_shanghai(title, desc)`：正文明确外地城市且无上海信号 → 整篇丢弃。
- admission_gate：resolve_anchor_name/pin_name 兜底过 looks_like_brand；主循环加城市闸门（统计「外地丢弃 N」）。
- candidate_apply：入库前再过 looks_like_brand 第二道。
- cloud_amap_fill：配额码 10044(USER_DAILY_QUERY_OVER_LIMIT) 与 10003 同视为日配额耗尽即停。

### unmatched→discovery 闭环（本次新增 cloud/unmatched_bridge.py）
旧断点：xhs_to_reviews 把锚不入库的笔记写 unmatched_shops.jsonl 后无下游。新桥接：
- 从 raw_xhs.jsonl 按 note_url 找回完整笔记（正文+评论）；
- 推断品类（优先 search_name 在库菜系反查 CUISINE_ROOT，兜底正文品类词）；
- 去重(note_url 状态文件)后追加进 raw_discovery.jsonl；
- 对每个有新证据的品类跑 admission_gate → candidate_apply --commit。
已接入 run_batch.py（无论是否采到新店都跑，幂等）。

### 验证
- bread 品类：修复前垃圾 brand（第二次来总结/年老店/小而美的面包店/定西路/芝士猪排咖喱饭/要不要再加一句简短标签…）全消；修复后 admit 全是真店（BAsdBAN/FASCINO/Soso/O'mills/ComeCome/Punch Monday/L'Atelier Over Bakery/Table A Deli/Shiopon）。
- 高德日配额当日已耗尽（USER_DAILY_QUERY_OVER_LIMIT），candidate_apply 暂 0 插入；配额次日重置后自动补录。回归店 Proust Moment 现 reject(非本品类)、B+Baked hold(独立声音1)，需 cloud_discover 继续图遍历补证据。

## 2026-09-27（补）精度收尾：字段标签/产品名检测 + 品牌归一去重 + 负面清单闸门

用户复跑 bread 后指出三类残留，全部以确定性函数收干净：

### 1. looks_like_brand 仍漏过的非店名 token（common.py）
- 新增 `FIELD_LABELS`（精确等于匹配）：门店地址/电话/营业时间/个人cv/菜单/人均/预约/招牌 等独立字段标签 → reject。「招牌菜」不受影响（精确等于，非子串）。
- 新增 `INGREDIENT_WORDS` + `PRODUCT_BARE_SUFFIX`：`提子面包` 类 = 食材前缀+面包/烘焙后缀 → reject（product:提子面包）。`MBD面包` 前缀非食材 → 放行。

### 2. 品牌归一去重（common.normalize_brand_name + admission_gate.get_brand）
- `normalize_brand_name`：剥尾部「面包/烘焙/蛋糕店」后缀、小写、去空格/引号/连接符。
- profiles 的 key 改用归一值，「mbd面包」和「MBD」合并到同一 profile，声音累加；显示名取最短写法（aliases 字段记录所有原始写法）。

### 3. 负面品牌硬闸门（admission_gate.NEGATIVE_BRANDS）
- 硬编码连锁/预制清单：苹果花园/外婆家/绿茶/海底捞/瑞幸/星巴克/85度C/好利来/巴黎贝甜/面包新语/和府捞面/陈香贵 等。
- verdict 里归一后命中即 reject（reason=negative_brand），**即使独立声音≥2、均分≥3.5 也不进精选**。苹果花园（声音5/均分4.15）实测被正确 reject。

### 验证结果（bread 品类，136 篇笔记）
- 0 个元话术/菜名 brand 漏网（门店地址/个人cv/提子面包 已消失）。
- MBD 归一合并（aliases=[MBD, mbd面包]）。
- 苹果花园 negative_brand reject。
- admit/admit* 共 16 家，全为真店：BAsdBAN/FASCINO/Soso/ComeCome/Punch Monday/Shiopon/Proust Moment（回归店，声音3/4.04）/Dear You/Skroll/Bake No Title/Baker & Spice/O'mills/Pain Chaud/Table A Deli/L'Atelier Over Bakery/银座仁志川。
- B+Baked 仍 hold（声音1），Orenda Bay 未在现有笔记出现——需 cloud_discover bread 继续图遍历补证据。
- 其余 23 品类笔记量太少（1~44篇）凑不齐独立声音≥2，gate 正确 hold/reject 无误 admit；待 cloud_discover 采量上来后自动出结果。

### SSH 运维备注
SSH 若域名别名 `food-cloud` 不通（Clash TUN 模式会把域名解析成 fake-IP），改用直连：
`ssh -i ~/.ssh/food_cloud_deploy ubuntu@49.234.35.92`（私钥 ~/.ssh/food_cloud_deploy，user=ubuntu）。

---

## 2026-09-28｜每账号独立出口 IP + 服务端隔离二维码登录（并行采集）

### 背景
并行 worker 池虽支持多账号，但所有账号共享上海服务器单一出口 IP，并行触发软限流；且 account_b 登录会挤掉本地浏览器里的 account_a。用户要求：独立 IP 由 AI 完成、b 由用户扫码、与 a 并行、三级菜单必须修好（菜单修复见 commit 7947cb1）。

### 独立出口 IP（已验证）
- 新增广州 Lighthouse 实例做鉴权代理（与上海主服务器不同地域/不同 IP）：
  - 公网 IP **139.199.90.169**，实例 ID **lhins-kqyl0sh9**，zone ap-guangzhou-6（regionId=1）。
  - 锐驰型 2核1GB/40GB SSD/200Mbps，Ubuntu 26.04 LTS，**40 元/月，2026-10-28 12:24 到期**。
- 代理：tinyproxy 监听 **0.0.0.0:18080**，BasicAuth 用户 **xhsb** / 密码 **a7887d57a979acf608916ceb**；
  ConnectPort 仅 443/563；云防火墙 TCP 18080 **来源仅 49.234.35.92/32**（仅上海主服务器可用，纵深防御）。
- 验证：从上海服务器经代理 `https://myip.ipip.net` 返回「当前 IP：139.199.90.169 广东 广州 电信」；
  `http://ip-api.com/json` query=139.199.90.169、AS45090。
  注意 api.ipify.org（Cloudflare 104.26/172.67）在该广州网络直连也为空、不可用，非代理问题。
- 容器内 `/app/data/account_proxies.json`：
  `{"account_b":"http://xhsb:a7887d57a979acf608916ceb@139.199.90.169:18080"}`
  gap_runner.proxies_for(account) 读取并透传给 XhsApi（requests proxies）。account_a 不配置 → 走上海 IP。

### 服务端隔离二维码登录（cloud/xhs_qr_login.py）
- 独立 headless Chromium + 独立 context（与本地 account_a 完全隔离），打开 xhs 首页截登录二维码。
- 容器缺 chromium_headless_shell-1148（只有完整 chromium-1148），用 executable_path 指向
  `/root/.cache/ms-playwright/chromium-1148/chrome-linux/chrome` 跑内置 headless。
- **登录成功判据 = cookie 同时含 web_session 与 id_token**（XHS 给访客也发 guest web_session，
  只判 web_session 会误判；account_a 另有 id_token/last_web_session/unread/gid）。
- 扫码成功导出 cookie → 宿主机 `/home/ubuntu/food-cloud/xhs_accounts/account_b.json`（600，owner 1000:1001）。

### 当前运行状态（已验证）
- 重启后新 gap_pool（PID 4093）下双 worker 并行：account_a（worker 4103，leaf 170，上海 IP）、
  account_b（worker 4104，leaf 171/172，广州 IP）；claims 原子认领、不同叶子。
- tinyproxy 已记录 b 对 edith.xiaohongshu.com 的 CONNECT（115+），独立出口确认。
- 提交：cloud/xhs_qr_login.py、gap_runner.py、xhs_api.py（commit 见 git log，已推 main）。

### 扩容更多账号（c/d/e/f）的标准动作
1. 每新增一个账号 → 新增一台不同地域 Lighthouse tinyproxy 实例（同法，40 元/月），
   防火墙仅放行上海主服务器 IP；
2. 在容器 `/app/data/account_proxies.json` 增加 `<account_x>: 代理URL`；
3. 跑 xhs_qr_login.py（改输出文件名/账号）出二维码，用户用对应手机账号扫码；
4. cookie 落宿主机 xhs_accounts/<account_x>.json；池自动 classify 并拉起该账号 worker。

---

## F3「集团 / 品牌 / 主厨树」抽样框 —— 已闭环（2026-09-28）

模块：`cloud/vendor/pipeline/group_chef_tree.py`（已部署 /app/pipeline，已提交推 main）。
默认 dry-run，`--apply` 才写库；幂等可复跑。

### 机制（确定性，不靠模型即兴）
- 把集团“期望品牌”解析到在营 restaurant，逐一对账：linked 已挂 / new 在库未挂（补挂）/
  ambiguous 多分店（不自动连）/ closed 仅匹配到关店 / out_of_market 外地品牌 / missing 真缺口。
- **跨集团守卫**：品牌解析到的店全部已属其他集团、本集团没有 → 判为雇主品牌跳过
  （解决卢怿明受雇福系列导致福1015 串到自创品牌集团；福和慧反串福系列）。
- **品牌状态注册表** `/app/data/coverage/group_brand_status.json`（版本化副本
  `research/authority/group_brand_status.json`）：外部时效/关店/外地核验写入，每条带 source_url；
  status=closed / out_of_market。集团树据此把非上海缺口剔除发现队列。

### 本轮结果（已 apply、已回验）
- 补挂成员 5：荣府宴 rid759→新荣记；雍颐庭 rid539→卢怿明品牌；
  La Boulangerie rid1166→海外名店；逸龙阁 rid716、香聚江南灶 rid782→国际酒店集团。
  restaurant_group_members 42 → **47**。
- 核实并分流“疑似缺口”：Ultraviolet（2025-03-29 永久关店）、Charbon（2024-12-31 关店）、
  L'Atelier de Joël Robuchon rid1139（已关店）；京季、芙蓉无双（仅北京，非上海）。
- 最终：**真缺口 0、待补挂 0**；发现队列 group_missing_brands.json = []。
- 权威 sitemap 全量召回（154，含望庐）经核实与米其林官方口径一致，权威召回机制正常。

---

## KOL / 美食声音体系 —— 已落地（2026-09-28，commit 2c710d5）

迁移：`db/migrations/013_kol.sql`（经 Supabase SQL Editor 执行、回验）。
- food_kol_watchlist 扩列：kol_type（博主/美食家/美食导演/美食作家/主厨自媒体/媒体）、
  specialty_tags jsonb、region、profile_url、trust（high/mid/low）。
- 新表 food_kol_posts（帖子归档，post_url 唯一）、food_kol_mentions（提及，
  matched/ambiguous/unmatched + polarity pos/neu/neg/mixed）；RLS 默认仅 service role。

名单：25 B站博主 + 9 权威声音 = **34**。9 权威声音（种子 `research/authority/kol_seed.json`）：
沈宏非、殳俏（上海/作家）、陈晓卿（美食导演/北京）、蔡澜、欧阳应霁（香港）、
董克平、小宽（北京）、叶怡兰、焦桐（台湾）。社交 handle/profile_url 未核验者留空，连接器补。

模块：`kol_post_ingest.py`（skill scripts/food_pipeline + 项目 cloud/vendor/pipeline）。
- 平台无关：连接器把帖子拉成统一 jsonl，本模块做最长匹配店名 + 归档 + 提及；
- 情感用**归属窗口**：提及拥有“自己起点→下一个提及起点”的描述，名字后的赞美/批评归该名字、
  不越过下一个名字；服务/情绪词不计口味；默认 neu。
- 已端到端测试：正/负/中性三种语境全部判对（pos/neg/neu），合成测试数据已清。
- 边界：KOL 到访只作线索/特征标签，**不计 taste**；unmatched 店名由连接器侧入发现队列。

待办：①把 bilibili 采集的 KOL 视频接入 kol_post_ingest 归档；②douyin/wechat 连接器（P5）；
③未匹配提及→发现队列的自动闭环。

---

## 覆盖闭环诊断 + 准入误杀修复 —— 2026-09-28（commit 77c379e）

**现象**：gap_pool 2 worker 常驻、账号签名通道健康、discovery 持续产出，但 ledger `met`
长期停在 17/291。逐段排查定位闭环有 3 个断点：
1. **准入误杀（本轮已修）**：admission_gate 的品类归属 `is_cat` 只认“结构化分区 / 库内品类
   tag / 有限招牌词表”。带店铺后缀、有真实口味信号的小店被误判“非本品类 reject”：
   - 四吉饭店（avg_taste 4.15、有食客引语，因“皮蛋”不在招牌词表）；
   - 青山製麺（拉面店，“製麺”形态未被识别）。
   修复：新增 SHOP_SUFFIX 店铺后缀 + STRONG_MORPH 强品类形态 + shop_morph()，并补川菜/拉面
   高频出品词（皮蛋/豆花/担担面/燃面/钵钵鸡、沾面/叉烧/鸡白汤等）。纯菜名（夫妻肺片/麻辣鱼）
   无店铺后缀，仍正确 reject。验证：四吉饭店、青山製麺均 reject→**hold**。
2. **每品牌独立声音太浅（未修，覆盖主瓶颈）**：discovery 每品牌基本只采到 1 篇笔记，
   independent_sources 几乎都=1，达不到 admit 门槛（≥2）。需加深“每品牌定向取证”：
   多篇笔记 + 评论区独立食客 + 跨源（点评长评/公众号），并把 L0/L1 免登录源占比提上来（P4）。
3. **缺 candidate_apply（未修）**：容器内不存在该模块，admit 候选不写库、ledger `met`
   不重算。需新建：admit 且在库→补品类 tag/证据；admit 新增→富化后建店；最后按真实库状态
   重算 coverage ledger 的 met/gap。

**结论（先原因后数据）**：覆盖停滞 = 误杀（已修）+ 取证太浅（待修）+ 无 apply（待修）。
下一步顺序：先做每品牌深取证把独立声音做到≥2，再建 candidate_apply 接通账本。

---

## 地图配额根治（2026-09-28，对标小红书方案）

告警“地图日配额耗尽、电话暂停”的根因（证据）：
1. 真瓶颈=高德**搜索服务个人 5,000/月**（非硬编码 5,000/日），**10044 账号级**；同账号多 key 共享、不扩容。
2. 最重 cloud_amap_fill 走**单 key、绕开 key 池**，吃光月配额；无配额仲裁，电话被饿死。
3. 腾讯单 key 无池，且大量 **status=111 签名失败**（关键词含 `&`/`+`）。
4. 一个兜底挂就整轮中止；电话/坐标/营业时间/全字段对同 POI 重复调用、无共享缓存；无 L0 免配额源；无看门狗自愈。

**已做 P0**：修复腾讯 111——tencent_sig 签名前清洗值内 `&+=#%`（实测 Mr & Mrs Bund/a+b c 由 111→status=0）。
已部署 /app/pipeline/tencent_sig.py，vendor 同步。

**待做**：P1 `map_quota.py`（持久 key×接口 日/月账本 + 腾讯多 key 池 + acquire 仲裁 + 电话预留预算 +
cloud_amap_fill 走池降频 + 持久 POI 缓存一次 extensions=all 共享）；P2 注册多个**独立实名开发者账号**
+免费企业认证（搜索 5千→5万/月，需用户实名）；P3 L0 官方源取电话 + map_key_repair 接看门狗。
完整方案：skill `references/map-quota-fix.md`（副本 research/design/map-quota-fix.md）。

---

## 告警专项 warning_handler（2026-09-28，看门狗内独立 warning subagent）

诉求：TG 报 account_a 登出需重登，要求看门狗有**单独处理 warning、与用户沟通到解决**的专项
（原 R3 只发一条一次性告警，无人跟进）。实测 account_a 双出口均 **-100（真登出）**、account_b code=0。

新增/改造（均在容器 /app/cloud，源码同步项目 cloud/）：
1. `xhs_qr_login.py` 重写为**任意账号、后台常驻**：产物按 `/app/data/qr/<account>.png|_status.json|
   _new.json|_pid` 组织，worker 隔离 headless Chromium，二维码每 40s 自刷新，web_session+id_token
   判成功；`start/is_running/status`。proxy 按 account_proxies.json 取（b 走广州代理）。
2. `warning_handler.py`（核心）：持久工单账本 `/app/data/warning_tickets.json`，生命周期
   open→waiting_user→resolved；`request_login` 拉二维码并把**二维码图片推 TG(sendPhoto)+飞书
   (上传 im/v1/images 再发 image)**；`poll()`（watchdog 每轮）验证重登（等宿主机安装→probe code=0）、
   二维码过期/worker 退出自动重拉（≤6 次）、限时提醒（20/40min 后每 60min）、TG getUpdates
   收“重拉/已扫”指令；成功推“✅已重登”并关单。通用 `warn()` 统一处理非登录告警。
3. `account_repair.human_alert_if_needed`（R3）改调 warning_handler.request_login（失败回退 health.alert）；
   `watchdog.main` 在账号修复后调 warning_handler.poll()。
4. **宿主机安装器** `/root/food-qr-installer.py`（root cron 每分钟；副本 cloud/host/）：容器内
   /secrets 只读，无法自写；脚本校验 fooddata 卷 qr/*_new.json（含 web_session+id_token）后安装到
   /home/ubuntu/food-cloud/xhs_accounts/<account>.json（600 ubuntu:ubuntu），并改名 _installed.json。

当前：account_a 工单 waiting_user，二维码已推 TG/飞书/用户，扫码后自动验证恢复；后续账号失效全自动走此闭环。

## 2026-09-28（定稿）登录路径收敛 + 搜索速率软限流 —— account_a 已恢复

接上文，多轮实测推翻「云端 headless 扫码可重登」的假设，定位唯一可用路径与搜索限流真相。
**完整 SOP 见 skill `references/xhs-login-runbook.md`。**

1. **云端 headless 扫码是死路**：二维码能识别，但手机「确认」后必 **fail to login**、id_token 永不出现
   （服务端在确认环节拒绝数据中心 IP/自动化会话，多次重扫相同）。宿主机安装器/warning_handler 的
   自动二维码无法完成确认登录——**重登必须人工在本机真实有头浏览器扫码**。
2. Playwright 有头（navigator.webdriver=**true**）能登录成功（guest=false），但该账号搜索被持续抑制；
   豆包内置浏览器导出的 cookie 是**游客态**（guest=true）。
3. **唯一可用路径 = 本机真实 Google Chrome**：`open -na "Google Chrome" --args --remote-debugging-port=9222
   --user-data-dir=<全新目录> ...`（经 launchd 启动；shell fork/nohup 会 abort134 或被回收，默认 profile
   有锁权限），再用 Playwright connect_over_cdp **只读**导出 cookie。实测 navigator.webdriver=**false**，
   user/me **guest=false**（uid 6972702800000000370282a7）。
4. **搜索是速率型软限流，不是账号死**：结果按时间窗在「满/空」翻转；连续快速请求触发数分钟 code=0、
   data 空冷却，停顿自恢复。实测安全速率 **≤2 次搜索/分钟（间隔 ≥28s）**，连续 3 分钟 7 次全返回 22 条；
   登录后还有数分钟**搜索预热窗口**（可能空）。空 code-0 = 放慢/冷却中，禁止硬刷。
5. 已固化并部署 `/app/cloud/xhs_api.py`：`SEARCH_MIN_GAP=28`、`_search_pace()` 强制节流、空页走
   60–180s 长冷却最多重试 2 次（COMPILE_OK）。项目 cloud/ 源已同步，待提交。

**当前状态**：account_a 已用真实 Chrome 干净账号覆盖并验证搜索恢复（两出口、全关键词格式均返回）；
account_b 仍 -100，需按 runbook 在另一真实 Chrome 窗口扫码（走广州代理）。看门狗对 -100 的自动二维码
仅作告警/沟通入口，实际重登走人工真实 Chrome 流程。

## 2026-09-28 看门狗推送整顿（已部署/提交）

问题：health.alert / warning_handler / progress_broadcast 各自为政，标题格式不一、10 分钟播报绕过
冷却、且对 -100 持续推送【云端 headless 二维码】——而该路径在确认环节必 fail，属无效打扰。

新增 **`cloud/notifier.py`（唯一通知出口）**，所有外发统一走它：
- 四级：INFO(例行心跳, cadence=600) / WARN(自动处理中, 同内容冷却 3600) / ACTION(需用户操作,
  首次即推 + 按 30/60/60/120 分钟有界提醒 4 次后不刷屏) / RESOLVED(每 key 一条收尾)。
- 统一格式（级别标签+时间+正文+“无需操作/👉需要你做”），按 key 内容哈希去重，sanitize 截断并遮蔽凭据；
  不推 traceback / 遮罩图 / 过期码。通道复用 health._telegram/_feishu_app/_feishu。
- 账本 `/app/data/notifier_ledger.json`。

改造：
- `progress_broadcast.py`：新增 build_compact（每块一行），main 走 notifier.info(cadence=600)。
- `warning_handler.py`：**停用云端 headless 二维码**（不再 Q.start/_send_qr，并清理残留 worker）；
  -100 改推「本机真实 Chrome 重登」ACTION（回到豆包说「重登」由主 agent 开窗）；poll() 双出口
  轻量复核，code=0 自动 notifier.resolve 关单；通用 warn() 走 notifier.warn。
- `watchdog.alert` 走 notifier.warn。
实测紧凑播报双通道推送 True。

## 2026-09-28 xhshow 签名升级 + 反检测移植（已部署/提交）

审查 jackwener/xiaohongshu-cli 后确认：它也是 xhshow 薄封装，但固定 **xhshow 0.1.9**（我方原 0.1.0），
并有 gaussian 抖动 / 验证码后永久降速 / sec-ch-ua 对齐 / browser_cookie3 自动取 cookie。

已移植进 `cloud/xhs_api.py`（兼容 0.1.0 与 0.1.9）：
- 自备 `generate_search_id()`（0.1.9 已移除 Xhshow.get_search_id）；
- `_human_jitter()`：高斯抖动(均值0.3)+5%概率2–5s长停顿，用于 _gap/_search_pace；
- sec-ch-ua / sec-ch-ua-platform / sec-fetch-* 与 UA(Chrome126) 严格对齐；
- `slow_down()`：遇速率验证码(300011/300012/120/406)搜索间隔永久翻倍（28→…→封顶120s）。
requirements 固定 xhshow==0.1.9。
**待办**：当前会话已 -100（同账号重复登录被顶，见下），0.1.9 真实搜索的端到端验证需在一次干净
重登后进行；签名版本本身不影响 web_session 有效性（-100 是服务端会话校验，非签名问题）。

## 账号独立性：account_a / account_b 当前是【同一账号】（2026-09-28 取证）

两文件 web_session 身份段完全相同：均以 `040069b80633608cd2f1` 开头（仅设备后缀不同）；
a1（设备指纹）不同 = 两个不同设备，但登录身份是同一个小红书账号（uid …370282a7）。
原因：第二个二维码是用【同一台手机/同一个已登录账号】的小红书 App 扫的。同账号在第二个新设备
登录会把第一个会话顶掉（单会话安全策略），故随后两出口统一 -100。
**要独立**：第二个码必须用【另一个小红书账号】扫——在 App「我 → 切换账号」切到别的账号再扫，
或用第二部手机/第二个账号；且登完不要在别处重复登录。

**已定义用户名（2026-09-28，账本 cloud/account_identities.json → 持久卷 /app/data）**：
- account_a = **ahuhu**
- account_b = **猪蛤蛤**
登录成功（user/me guest=false）时自动回填 nickname/red_id/uid 并校验昵称与 expected_nickname 一致；
看门狗/通知按 friendly_name 播报。当前 cookie 仍是同一旧身份，需按此分别重登才生效。

## 大众点评电话连接器 cloud/cloud_dianping_phone.py（2026-09-28）

**目的**：为 phone 为空的 active 店在点评按店名检索，锚定唯一门店（记录 uuid/URL/地址），尝试取公开电话。
**登录态**：本机真实 Chrome + CDP 扫码取得，账号 **LANCE（member 1329295730）**。
cookie 存 `cloud/.dianping_cookies.json`（gitignored，600，含 httpOnly `dper`/`dplet`），
容器内 `/app/data/.dianping_cookies.json`（600），cookie 可移植、本机 IP 取得。

**机制结论（重要）**：点评 web（www/m 门店页 + 桌面搜索页）**不公开电话**——
门店页为 H5 shell（260 处 wx-view），`desc-phone` 是空 CSS 图标/App 深链；HTML 内嵌 JSON
（shopConfig/__NEXT_DATA__）无 tel 字段；wxmapi shopservice 仅返回服务能力标志；
mapi shopinfo/shopdetail 404；poi-bundle JS 无电话 API 路径。电话为 **App-only**。
已用连锁（外婆家）+ 多家高端店双向验证，非解析错误。

**连接器行为**：
- `common.fetch_all("restaurants", extra="phone=is.null&status=eq.active")` 取全量缺号店；
  点名回归店（id 列表）优先；
- 搜索 `data-click-name="shop_title_click" data-shopid=... title=店名` 解析结果；
- `cjk_norm` 名称相似度 + `addr_core` 地址重合双闸门；仅名称≥0.75 且地址≥0.5 才锚定；
- 电话候选过 `clean_phone`，并排除 poiId 碎片/点评客服 4003101100；
- 默认 dry-run，`--apply` 才 PATCH（只 PATCH phone 一个字段）；
- 礼貌限速 4s/店、幂等、可复跑；取证报告 `/app/data/dianping_phone_report.json`。

**dry-run 结果（2026-09-28，197 家唯一缺号店）**：
- 锚定点评门店 163 家、点评搜不到 101 家；
- 拟采纳电话 **0**；唯一候选 `0379254716`（洛阳区号、地址不匹配）被 clean_phone/闸门正确拦截；
- 全部留空（点评 web App-only，无公开号）。覆盖率维持 84.8%（1248/1472，null=224）。
- 未做 --apply（0 采纳，no-op）。后续若点评开放 web 电话或改走 App 抓包，再补。

## Phase 0-A 实体解析去重 + 名称交叉验证（2026-09-28）

**目的**：修机制（不是手工补这几家）——全库重复实体检测/合并 + 名称权威源校验，双向防错并保护子表数据。
新引擎 `cloud/vendor/pipeline/entity_dedup.py`（默认 dry-run），已部署容器 `/app/pipeline/`。

**双向裁决（核心）**：
- 同店异写→合并：品牌相关 AND（同座机 OR 同门牌 addr_core OR 坐标<25m）。正名为准、异写并入 `aliases`、证据取并集。
- 近名异店→保留：连锁异址分店（坐标>200m/不同路）即使同品牌也不并；`entity_keep_pairs.json` 强制豁免。
- 中间带（25–200m、共享手机/商场共用中心坐标）→ REVIEW，不自动并。

**合并数据安全（全子表，以 db/migrations 实际 schema 为准）**：
- 迁移覆盖 10 类 FK：restaurant_cuisines(PK cid)、reviews(user+visit_date+content)、
  restaurant_chefs(PK chef+role)、restaurant_awards(uniq award_type+year)、food_events
  （restaurant_id CASCADE 与 related_restaurant_id SET NULL **两字段都迁**）、
  restaurant_group_members(PK group_id)、negotiations/price_benchmarks/favorites/food_kol_mentions。
- 复合 PK 表（无独立 id）走 POST 新行+删旧行；有 id 表按业务键去重后 PATCH 改指。
- 字段合并只补 keeper 空值（coalesce），**电话/坐标永不覆盖已存在有效值**；旧店名并入 aliases。
- 绝不直接 DELETE restaurant 行触发 CASCADE：先全量迁子表 FK，最后才删被合并行。

**并发健壮**：每簇 apply 前重新快照成员行；若与计划时不一致就该簇重算字段合并，
不覆盖 amap/电话定时任务刚 PATCH 的字段。写后回读 keeper + 自检（keeper 在、drop 行已消失）。

**名称交叉验证（L1–L6）**：正名需 ≥2 个 L1–L5 源一致；UGC 异写入 aliases。
`name_audit()` 产出 `name_fixes.jsonl`（id/wrong/correct/level/authority_urls）；
已核实表（白茸/佰荣/白荣/百荣→「白茸 Bai Rong」BFC 鲁菜米其林）+ 店名混入营业时段等噪声后缀检出。
heuristic 类（无 authority_urls）只列清单**不自动改写**，待 L1–L5 核证后 --apply。

**回归用例（--selftest 全 PASS）**：
- pain chaud：1164(建国西路) vs 1785(番禺路) = 连锁分店→keep；历史同店异写 1235 已并入 1164。
- 纹兵卫：44(金虹桥) vs 1870(天山) = 不同分店→keep；44 店名「（午市套餐）」噪声被审计检出。
- 南兴园：已收敛为单条实体(478)，不误拆/不重建重复。
- 白茸：815(BFC「白茸 Bai Rong」) vs 812(太阳宫白茸小鲜) = 子品牌异店→keep；815 正名正确，
  不与南京东路温州馆「白荣」误并（库内当前无该白荣行）。
- 合成对：同店异写→merge；近名异店(同品牌~3km)→keep。

**dry-run 结果（容器 food-cloud，2026-09-28）**：全库 1479（active 1472/closed 7），
自动合并簇 0、待复核 0（强信号候选此前已由 entity_resolve/keep_pairs 裁决收敛），
名称修正 1 条（纹兵卫 id=44 噪声后缀，heuristic 待核）。基线：电话覆盖 1256/1479≈84%、
坐标 1473/1479≈99%，合并前后只许变好。未 --apply（0 真合并 + 名称修正无权威源，no-op）。

**周期化**：只读扫描已接入 `cloud/cloud_patrol.py`（不碰 crontab.txt）；
patrol dry-run 报告「全子表版: N 簇 / M 待复核 + 名称修正 N 条」。真正合并仍需人工确认后
`python3 entity_dedup.py --apply`。如需 cron 行建议由运维统一安排。


---

## Phase 0-B · 云端地图运维修复 + 每日只读自进化（云端运维执行者，2026-09-28，commit b191716）

> 本节为云端运维部分独立章节，不改动上方 Phase 0-A（实体去重）内容。

### 背景与真因
- 现象：`cloud_amap_fill.py` 每个 cron tick 都「新调用:1 … 配额超限，本轮提前终止」空转，
  待补 1433、回填字段长期为 0；经 map_quota 池调 amap `/v3/place/text` 返回
  `status=0, infocode=10007 INVALID_USER_SIGNATURE`。
- 真因（非配额、非代码逻辑错误）：`AMAP_KEYS` 有 2 个 key，但 `AMAP_SKS` 只配了 1 个 SK，
  第二把 amap:1 被 `load_provider_keys` 配成 `(key, "")` 空签名 → 每次 10007。
- 旧代码把 10007 当通用 error：每候选重试、烧 amap:1 月桶计数、不熔断；并把"高德不可用"
  误判成"地图配额尽"导致整轮中断（腾讯主通道其实健康）。

### 机制修复（最小改动，已部署容器 food-cloud）
1. `cloud/map_quota.py` `report()`：amap `infocode=10007` → `dead_reason="auth"`、
   `dead_until=now+1800`（30min 熔断）、`bucket.used -= 1`（**不耗配额桶**）、result=auth。
   **鉴权错误与配额错误彻底分开**。
2. `cloud/map_key_repair.py` `_key_usable()`：reason=="auth" 冷却期内全接口判不可用。
3. `cloud/cloud_amap_fill.py`：新增 `_tencent_poi(name, addr)`（腾讯 suggestion→search 兜底），
   `resolve()` 三处返回点接入——amap search 无预算时先走腾讯兜底，腾讯无预算才整轮停，
   腾讯正常但本店无匹配则继续下一家；`pick_best` name_thresh=0.85、综合分≥0.6 才回填（宁空不假）。
4. `cloud/cloud_phone_fill.py`：③步 amap_search 返回 QUOTA_EXCEEDED 不再 set quota_hit
   （高德不可用只算本店无匹配，不中断腾讯主通道）。

### 验证（真实输出）
- map_key_repair 修复后实跑 exit=0：`tencent/search=全尽(解封次日00:00)；amap/search=全尽；
  amap/geocode=ok(1/2)` —— **amap search 月桶/auth dead 不影响 geocode，日/月桶隔离正确**。
- amap_fill 手动 `--limit 40/150`：连续处理 40/150 家、不再 1 调用即中断；最新 cron tick
  「新调用:40 用缓存:157 未匹配:6」（旧日志「新调用:1」模式已消失）。
- phone_fill 实跑**回填 6 个电话**：id 1895 RONG融→17520618326、1898 之舞→18721495794、
  1907 Tuttu→18321133722、1912 瑰禧→02162881977、1923 鮨琉璃→18930255116、
  1924 三佰杯→13564171130；电话覆盖持续上升（自检计数：已补电话 1281/1479）。
- 回填字段=0 的原因已查清：全库仅 1 家缺坐标，队列几乎都已有坐标、只缺电话/营业时间/评分，
  腾讯 suggestion 不返回 tel/cost/hours；机制在可匹配店（南兴园/老吉士/鲜得来）上已验证产出"坐标"patch。

### 每日 01:00 只读自进化（新上线）
- 脚本 `cloud/self_evolve.py`：**只读、确定性、可复跑**，无任何 PATCH/DDL/删改。
  复盘当日 `/app/cloud/*.py` mtime 改动 + Supabase 只读计数 + 跑 `release_audit.py` A–G 只读扫描。
- 产出落盘 `/app/data/self_evolve/YYYY-MM-DD.md`；经 `cloud/notifier.py` 推精简结论
  （常态 INFO，出现 ERROR/需人工处理才 ACTION）到 Telegram(@ShanghaiFoodAtlasBot)+飞书。
- crontab 已装入容器并 `crontab -l` 验证：
  `0 1 * * * cd /app/cloud && . /app/cloud/env.sh && flock -n /tmp/self_evolve.lock /usr/local/bin/python self_evolve.py >> /app/data/self_evolve.log 2>&1`

### ⚠ 需用户在控制台处理的行动项（运维无法自解）
1. **补 amap:1 的数字签名 SK**：到高德开放平台控制台取第二把 key 的「数字签名(SK)」，
   追加到 gitignored `cloud/deploy.env` 的 `AMAP_SKS`（逗号分隔，与 AMAP_KEYS 一一对应）。
   未补前 amap:1 search 持续 10007/auth，amap 全字段主要靠腾讯兜底。
2. **腾讯 key 真实日量偏低**：tencent:0 在 used=429 即返回真实 `code=121`（日量超限），
   被正确标记 daily_quota 至次日 0 点。需注册更多独立实名腾讯 key 写入
   `TENCENT_MAP_KEYS`/`TENCENT_MAP_SKS` 以扩容电话/坐标兜底通道。


---

## Phase 0-B 分类机制重做（主营 is / 含有 serves / 地名陷阱）

> 执行者：分类开发执行者；日期 2026-09-28。前置 Phase 0-A 实体去重已完成。
> 本机制把 `restaurant_cuisines.is_primary` 系统性打成「主营(is)=true / 含有(serves)=false」，
> 按门店**主营出品**定主菜系叶；店名/地址里的地名 token 只作弱信号。

### 交付物
- 引擎：`cloud/vendor/pipeline/primary_cuisine_engine.py`（确定性、默认 dry-run、`--commit` 才写库）。
- 报告：`cloud/vendor/pipeline/primary_engine_report.json`（逐店 before→after/证据/置信/原因/证据URL）、
  `primary_engine_before_after.tsv`（人读摘要）。
- 已部署容器 food-cloud `/app/pipeline/primary_cuisine_engine.py`，容器内 dry-run 复跑 **no_change=1472、0 变更**（幂等）。

### 机制要点（修机制，不是手工清单）
1. **主营 is vs 含有 serves**：每家 active 店在**既有**菜系关联中确定性选恰好 1 个主菜系叶；
   其余菜系 link 一律 serves。不新增/删除 link，不动 restaurants/cuisines 其他字段。
   - 中餐：地域子流派(identity)优先于产品/形式第二轴(format)。潮汕牛肉火锅店主=潮汕菜、
     潮汕牛肉火锅=serves；松鹤楼主=苏帮菜、苏式汤面=serves。
   - 日料/西餐/非正餐（无地域子流派）：按主营出品证据在产品叶中选主（鮨琉璃=寿司、酉町=烧鸟、
     BOTTEGA=那不勒斯披萨、Speak Low=鸡尾酒吧）。
2. **地名陷阱弱信号**：扬州/四川/重庆/潮汕/海南…等地名 token 在店名里权重仅 0.1，须招牌菜/食客
   证据佐证才采纳。引擎自动记录「名字地名指向 X、但招牌/证据证明主营 Y」的纠正案例 **17 条**
   （典型：八合里/陈记/潮牛嗨等潮汕牛肉火锅店名带"潮汕牛肉火锅"，主菜系按身份定=潮汕菜、火锅=serves；
   武妹娘/粉醉牛湖南米粉店招牌=常德牛肉粉，主=洞庭湖区菜、湖南米粉=serves；小吊梨汤北京菜烤鸭店
   招牌=烤鸭/爆肚/炸酱面，主=京味家常、北京烤鸭=serves）。
3. **覆盖保护**：不推翻人工已设 leaf primary——仅当新叶招牌菜≥2 命中且旧叶 0 命中（证据明确矛盾）
   才改；root→leaf 提升允许。1025 怡妮新疆（手抓饭/烤串菜单混合）即被保护保留人工"新疆正餐"。

### 全库 dry-run→apply 数字（真实运行，非估算）
- apply 前：rc 10600 行、is_primary=true **470**；active 1472 家中 1013 家无主菜系、458 家已标。
- dry-run 结果：main_newly_set **1013**（新定主）、no_change **443**、main_changed **15**
  （13 证据纠错+root→leaf 提升）、main_dedup **1**（id=517 莆田餐厅双 primary 收敛为莆仙菜、闽南菜降 serves）。
- apply：PATCH **1044 行全部成功 / 0 失败**。
- 回读：rc 仍 10600 行（未增删 link）；is_primary=true 470→**1482**（1472 active 各 1 主 + 10 闭店保留）；
  active 店 **0 无主、0 多主**。
- **restaurants 表零变化**：total 1479 / active 1472 / 电话 1254(85.2%) / 坐标 1471(99.9%) 与基线完全一致；
  本任务只 PATCH `restaurant_cuisines.is_primary`，`trg_restaurants_derive`(tier/score_total/search_vector)
  未被触碰、派生 trigger 未破坏。

### 回归用例
- reclassify_83 的 34 家 active 店（1927 鮨心和已闭店跳过）全部落定唯一主菜系：
  568 皖宴龙柏=徽州菜、759 荣府宴=台州菜、1446 釜溪盐韵=自贡盐帮菜、1517 乾七道=莆仙菜、
  1846 AmoyA=闽南菜、1923 鮨琉璃=寿司、1925 宫楽=怀石、1928 奈良本=寿司、1903 Endo=蛋糕/法式甜品、
  1989-1992 四家茶馆=茶饮、融合私宴系=融合菜/Fusion。
- 私房菜(形式 348)店按主营定类（1844 豪生=本帮、1846 AmoyA=闽南、1446 釜溪=自贡盐帮），
  不因"私宴/私房"名误判；形式维度 link 未动。
- 15 个 main_changed 均有招牌菜反证（515/884 闽南沙茶海蛎煎、569 徽州臭鳜鱼毛豆腐、648 潮汕鱼生薄壳、
  1038 台湾家常菜、1064 武汉过早热干面豆皮、1065 藕汤粉蒸肉等）。

### 周期化建议（未自行改 crontab）
- 建议加一条只读校验 cron（每日/每周）：`cd /app/pipeline && python3 primary_cuisine_engine.py`
  （dry-run，天然幂等；若有新店/新 link 导致 no_change<1472 则告警人工复核）。
  是否接入 `cloud_patrol.py` 或独立 cron，由用户统一安排。

### 遗留问题
- 少量 low/medium 置信的日料/西餐店（如 Da Vittorio、8½ Otto e Mezzo 仅有"意面"叶）主菜系叶偏窄，
  待后续补更细叶标签或证据后再优化；当前不影响"每店恰 1 主"的正确性。
- 地名纠正 17 条均为"身份叶优先于产品叶"的正确案例；若后续发现新的"名字带地名但主营另一菜系"反例，
  往 `LEAF_DISH_KW` 补招牌菜关键词即可，无需改机制。

---

## Phase 0-C：连锁 / 工业化预制 / 软广 负面清单 tag-on + 隐藏连锁联动（2026-09-28）

> 脚本：`cloud/vendor/pipeline/phase0c_negative_tagon.py`（默认 dry-run，自检全绿才 `--apply`；幂等可复跑）。
> 原则：机制优先、可溯可逆；只加负面标签/派生标志，不删店、不改菜系/电话/坐标/价格。

### 现状盘点（真实运行数字，active=1472）
- chain_type 已 100% 覆盖无 NULL：独立店 **1208** / 小型连锁 **203** / 大型连锁 **55** / 资本化连锁 **6**。
- central_kitchen：无 1266 / 疑似 181 / 确认 25；premade_risk：无 1266 / 低 168 / 疑似 15 / **高 23**。
- 软广：`soft_ad_flag` none 1253 / suspected 197 / confirmed 22；**`soft_ad_flag_reviews` 全 1472=none**（分布模型 cron 5:37 跑过，17 家有≥3条真实UGC的店全判 none，无误杀）。
- 隐藏联动：`is_chain_standardized`(generated) True **205** 家 = 前端"隐藏连锁/预制"过滤依据；penalty 218 家。

### 本轮唯一写库动作（tag-on 补缺）
- 缺口：migration 003 审计视图规定「pr=高 ⇒ 必挂工业化餐饮标签(cuisine_id=258)」，但 23 家 pr=高 全部未挂。
- apply：INSERT `restaurant_cuisines(restaurant_id, 258)` **23/23 成功，0 失败**；回读挂标总数 2→**25**，pr=高 23 家 **0 缺失**。
- 涉及品牌（均有 curated 证据，非"出餐快/平价"臆测）：小菜园×2、望湘园×2、盖饭邦、外婆家、点都德×3、
  南京大牌档×6、新旺×2、东发道×2、丸龟制面、新白鹿、费大厨、鲜芋仙。
- **restaurants 表零变化**：apply 前后全字段 SHA256 完全一致（`925e19eb…`）；total 1479/active 1472/closed 7、
  电话 1254、坐标 1471 与基线一致。只动了 tag junction；`soft_ad_flag/penalty/is_chain_standardized` 全部由 trigger/generated 派生，未直写。

### 反误伤（最高验收，自检 PASS）
- 独立店被标 suspected/confirmed 必须有 ck/pr 具体输入——无信号误杀 = **0**。
- 高端锚点新荣记/荣府宴/大董/甬府/鲁采/福和慧/唐阁/Ling Long/菁禧荟/鮨系 全部 `is_chain_standardized=False`（不隐藏）。
- 预制正例召回：小菜园/望湘园/盖饭邦/外婆家/点都德 全部 pr=高+ck=确认+std=True+flag=confirmed。
- 软广分布模型 17 家可打分店全 none——高口碑/低评论店未因平价或低评论数被误判。

### 人工复核项（脚本只报告不自动改/删，可逆）
- 遇外滩×3（高端闽菜真·三店连锁，ck疑似/pr低→按008公式保守隐藏，可申诉撤销）。
- POP露台餐厅(1984)：独立店但 ck=疑似/pr=低→trigger 派生 suspected；非低价小馆误伤，ck 依据可复核。
- 历史已挂 tag258 但 pr=无 的 2 家（1715 Alimentari Grande、1853 苹果花园）与派生口径不一致，人工复核（本脚本不自动删）。

### 周期化建议（未自行改 crontab.txt）
- softad 自学已在 cron 5:37。连锁/预制本脚本为只读扫描+幂等 tag-on，建议每周一条：
  `cd /app/pipeline && python3 phase0c_negative_tagon.py`（dry-run；若 pr=高新店漏标则报告新增，人工确认后 --apply）。
  是否接入 `cloud_patrol.py` 或独立 cron，由用户统一安排。

---

## Phase 0-D：深覆盖 sourcing（信源资产化 × 多抽样框覆盖矩阵）（2026-09-28）

> 执行者：sourcing 专职开发；前置 0-A 实体去重 / 0-B 分类 / 0-C 负面清单已完成。
> 本阶段修「信源」机制（A4 信源沉淀 / A5 账号最后手段 / P5 信源资产化），并把 P1 覆盖从
> 「单框关键词」升级为「目标全集 × 多个相互独立抽样框」，缺口可计算、可复现。
> 原则：默认 dry-run、只读不造店、候选必经实体锚定去重 + 堂食证据门槛；不靠关键词碰运气。

### 新增机制（两个确定性模块，已部署容器 /app/cloud）
1. **`cloud/source_registry.py`** — 信源注册表（Source Registry，P5）。
   把每个可用源注册为长期连接器：`id/name/platform/kind/auth_level(L0–L3)/covers框/connector_module/
   reliability(0–1)/refresh_cadence/account_dependency/淘汰条件`；并**动态探测健康**（连接器是否在、
   状态文件 last_polled、账号池状态）。默认只读，`--save` 落 `/app/data/source_registry.json`。
2. **`cloud/coverage_matrix.py`** — 多独立抽样框覆盖矩阵（P1）。
   逐框量化 已覆盖/缺口，只读，`--save` 落 `/app/data/coverage/coverage_matrix.json`。
   F2 权威框复用 `authority_sitemap.make_matcher` 权威四态匹配（cjk 繁简异体+中文数字+slug 品牌前缀+
   单汉字规则），**不**用粗糙子串（后者会把唐阁/甬府/福10xx/言盐误报缺失）。

### 真实运行数字（容器 dry-run，复跑一致；非估算）
- **权威基线只升不降**：total 1479 / active 1472 / closed 7；电话 1254(85.2%) / 坐标 1471(99.9%)，
  与本阶段开始前完全一致（本阶段**零写库**）。
- **F2a 米其林权威框**：分母 153（主列表），在库 exact+strong = **153**（136 exact + 17 strong），
  weak/short=0，**true_missing(none)=0，召回 100%**。官方口径 156，差额为发布后动态关店/口径差（已知）。
- **F2b 黑珍珠权威框**：无全量名录连接器 = **已知缺口**（待建；须对齐 authority-recall 三件套：
  全量索引 + 官方总数对账 + 缺店强制闭环）。
- **F5 地图 POI 框**：frontier 池 65（new 59 / ambiguous 3 / matched 3）；其中 **55 个非连锁单平台
  (amap) 新候选**，hits 多=1、仅 1 个声音 → 按机制**正确地未收录**，等待社交/评论区第二声音。
- **F4 社交发现框**：账本 291 叶，状态 shallow 99 / rich 61 / thin 54 / ok 47 / empty 30；
  **缺口叶 empty+shallow=129**（已展开为 discovery_plan 129 bundle × 6 平台路由）。
  ⚠ 两个小红书账号 account_a/account_b 当前均 **-100 web_session 过期**，F4 停摆（见遗留）。
- **F1 行政区格网**：1472 active；黄浦309/静安261/徐汇220/浦东173/长宁162 密集；
  **稀疏区（<20）奉贤1/青浦4/松江10/嘉定16/宝山16** = 地理框漏采候选；
  另发现 23 条脏名「海市X区」（缺"上"），登记不修（非本阶段范围）。

### 注册连接器清单与健康（source_registry.json）
| 源 | 层级 | 框 | rel | 健康 | 账号 |
|---|---|---|---|---|---|
| michelin_list 主列表 | L2 | F2/F6 | .95 | ok | - |
| michelin_sitemap 全量对账 | L2 | F2 | .98 | ok | - |
| blackpearl | L2 | F2 | .85 | **待建** | - |
| amap_poi | L0 | F1/F5 | .80 | ok(配额) | - |
| tencent_map | L0 | F1/F5 | .75 | ok(配额) | - |
| xhs_signed | L1/L3 | F4/F6 | .70 | **down(账号-100)** | 是 |
| bili_search | L0 | F4/G | .75 | ok | - |
| dianping_identity | L3 | C | .60 | ok | 是 |
| media_overseas | L2 | F2/D | .80 | **待建** | - |
- 合计 9 源：ok 6 / down 1 / 待建 2；**L3 登录账号依赖仅 1/9（dianping）**，符合 A5「账号最后手段」。

### 本轮候选与落库
- admission_gate 全量裁决现状：**hold 208 / reject 250 / admit 0**（独立声音≥2+均分≥3.5 门槛正常工作）。
- **本轮真实新增落库店 = 0**：不是失败，是机制正确——地图单平台 55 候选未达「≥2 独立声音」门槛；
  且小红书账号全过期、无新堂食证据可喂。候选不进库、不造重复、不收网红店。

### 周期化（未改 crontab.txt）
- 建议由用户统一安排：在 cloud_router/gap_pool 既有调度里加只读定时（每日/每周）：
  `cd /app/cloud && python3 source_registry.py --save && python3 coverage_matrix.py --save`
  （产出健康快照 + 覆盖矩阵，供监控 F2 召回是否掉 100%、F4 账号是否恢复）。

### 遗留 / 需用户处理
1. **小红书账号过期**：account_a/account_b 均 -100（web_session 失效），F4 社交框与 gap_pool 停摆；
   需重新扫码登录或提供新 cookie。恢复后 gap_pool 自动认领 129 缺口叶、并给 55 个地图候选补第二声音。
2. **黑珍珠连接器待建**：F2 第二权威框尚无全量索引，是目前最大权威缺口。
3. **23 条「海市X区」脏名**（历史 district 缺"上"），可在后续字段清洗阶段批量归一，本阶段不动。

---

### 2026-09-28（晚）地毯式采集落地：router 修复 + 米其林/黑珍珠权威对账 + 跨源证据池

**背景**：用户重启并拍板——非小红书源默认走**地毯式（carpet-sweep）**、云端 24/7 先跑不需小红书登录的源；小红书只定向补充、不在数据中心登录。本对话框角色＝采集运维与效率负责人。

**1. cloud_router「永久让位」bug（已热部署，未 commit）**
- 根因：旧 `decide()` 第一条即「若 presence `/app/data/POOL_RUNNING` 存在就无条件 return 空（让位）」；gap_pool 账号全 -100 空转时仍长期保留该文件，router.log 连续近 3 小时每 20min 打印让位、米其林永不被调度。
- 修复：账号健康探测（`xhs_usable_accounts`，status ok 且非 cooling 才 ready）提前；`decide()` 改为「ready>0 且 POOL_RUNNING 存在」才让位，ready<=0 时返回 `cloud_michelin_collect.py`。dry-run 实测 ready=0 → 正确调度米其林。

**2. 米其林权威召回闭环：154/154 全命中（确定性对账）**
- 本机 `research/authority/_sitemap_cache.json` 提取 ae-az 段上海 154 slug；`michelin_shanghai_153.json` 提供 153 中文名，唯一缺名 slug=`wang-lu` 补「望庐」。
- 自包含脚本（内 `fetch_all` 拉实时库 + 复刻四态匹配器）经 stdin 进容器执行。结果落 `/app/data/authority_reconcile.json` = `{"total":154,"missing":[],"uncertain":[]}`。官方口径 156，差 2 为发布后动态关店/口径差异，不硬追。

**3. 黑珍珠对账：61 家 → 真品牌缺失 5**
- 结构 `{three_diamond:3, two_diamond:6, one_diamond:52}` = 61。容器对账：51 在库、3 弱匹配（头灶/宝丽轩/周舍，经核候选名都在库）、7 缺失。
- 别名核验后：**徽季在库 id1884（假缺失，四态强包含未覆盖长权威名）**；**成隆行在库 id1385（九江路店），虹桥店/怡丰园为同名异址分店、待地址核验是否新增**；真品牌缺失＝**堀田 Horita、楼上菜馆(静安嘉里)、西郊5号 Maggie 5、VALE RESTAURANT、Sushi Aoki**。这 5 家缺真实口味证据，按宪章不仅凭榜单录入（四项评分全空），进证据采集。结果落 `/app/data/blackpearl_reconcile.json`。

**4. 跨源证据池 `evidence_pool.py`（新建，已部署 + crontab 第13条）**
- 根因：`admission_gate v3` 按「单品类 × 单来源目录」聚合、**不跨源**；B站搜索只给标题（desc 常空），单源凑不齐门槛 → B站 0 admit、稀疏源永不贡献。
- 机制：把所有来源归一化到同一餐厅账本并**跨源互证 + 信任加权**——
  - 真实食客（小红书 verified，trust high/mid）权重 1.0、独立声音全计；
  - 地图平台评论（高德 899 条，trust low）权重 0.4、仅弱互证、**不单独构成独立食客**；
  - B站 KOL 视频（标题**严格**品牌匹配）权重 0.6、计 curator；
  - 权威标签（米其林/黑珍珠）＝1 个来源声音、保证不漏、触发取证，不带口味。
  - 口味取评论 `aspect_taste`（1-5），B站标题 POS/NEG 现算；时间半衰期 180 天。
- 品牌匹配高精度：`brand_forms()` 用主名（≥2 汉字）+ ·分段（仅 ≥3 汉字）+ aliases，统一过 STOP 通用词表（居酒屋/外滩/海上/烧烤/炸猪排/日本料理…），消除此前把通用词当品牌的误命中。
- **首跑实测（1479 店 / 719 B站视频）**：
  - 权威标签店 **212，其中 209 家无真实食客口味**（最大待取证队列）；
  - 真实食客 ≥2 仅 **35**、=1 27（合计 62，与触发引擎口径一致）；
  - B站 KOL 正确覆盖 **18** 家真实品牌（酉町/平成屋/虎丸烧肉/点都德/敏华/喜粤8号/茂隆/圆苑…），多为 1 声音、不足单源门槛；
  - 无真实食客但有 KOL/权威（跨源待补）**223** 家。
- 输出 `/app/data/evidence/pool.jsonl`；crontab `17 * * * *`（flock evidence.lock）。`--commit` 已预留（对跨源够格**新品牌**走 candidate_apply），当前 B站标题只命中在库店、无新品牌可 apply。

**5. reviews / 口味引擎现状（关键，已摸清）**
- reviews 真实列：`id,restaurant_id,user_id,author_name,rating_total,rating_taste,content,visit_date,is_hidden,report_count,created_at,source_platform,source_url,review_kind,is_verified_diner,trust_level,is_fake_suspect,aspect_taste,aspect_service,aspect_env,aspect_value,aspect_json`。
- 1038 行 = **899 高德（low、未验证）+ 139 小红书（verified，mid56/high83）**；rating_taste 全空；aspect_taste/aspect_json 已派生 1037。
- 触发引擎 `trg_reviews_taste` **只采信 verified 真实食客**：score_taste/score_diner/review_count>0 仅覆盖 62 店（899 高德被正确忽略）。瓶颈＝高信任真实食客来源太窄（小红书被封），非引擎错误。

**6. B站通道审计**：搜索 `x/web-interface/search/all/v2`（必须 Referer 否则 -412）只给 title/author/play/bvid、desc 常空；旧 gate 把菜名/短语当品牌（sushi 仅 1/33、bread 0/37 命中库）。详情接口 `x/web-interface/view?bvid=`（code 0）可用但样例 desc 仍空。结论：**B站需视频详情/字幕 enrichment 后才有独立价值**，当前仅经证据池严格标题匹配贡献 KOL 互证。

**地图配额现状（硬约束）**：腾讯 key 今日用 429、0 点重置；高德 key#0 月度尽（dead 至 10/1）、key#1 auth 冷却。非小红书覆盖受日/月配额限制，电话/坐标/amap 补齐已由既有 cron 在重置后自动推进。

**遗留 / 下一步**：
1. 小红书稳健采集方案（已委派 OrganizerAgent `o_000cb5ClpVN`，进行中）→ 查结果后部署；两账号 -100 需真实 Chrome 重登（account_a LANCE / account_b 猪蛤蛤）。
2. 黑珍珠真缺失 5 家 + 209 权威店 → 证据池驱动定向取证，不仅凭榜单录入。
3. B站视频详情/字幕 enrichment（提 KOL 通道独立价值）；地图 POI 作地毯抽样框（配额内、多独立开发者 key）。
4. cloud_router 修复 + evidence_pool 待 git commit/push（push 状态需先核验）。
