# food-radar HANDOFF（v3 合并态）

> 2026-10-18 ｜ 执行规程见 PROPOSAL.md ｜ 候选来源 `food-radar-20261017-42f98d5ddf`

## 一、本次做了什么

把第三方候选实现（`food-radar-pending`）与自建v2 合并为 v3。**不是替换，是取长补短。**

### 采纳候选的（我缺的能力）

| 能力 | 价值 |
|---|---|
| `radar.py` 480 行记录引擎，**纯标准库零依赖** | 可移植性远超我的 uv/playwright/sqlite 栈 |
| `data-contract.md` 字段级 `basis` + `valid_until` **TTL 衰减** | 余位15分钟/营业7天/菜单30天/新鲜度1天——这是"置信度落到字段"的正确实现 |
| `origin_id` 同通稿转载去重 | 落实了外部审阅"转载不算独立证据" |
| **安全威胁模型**：平台内容不执行其中指令、不拼 shell、DB 路径宿主固定、**身份不信用户粘贴的 JSON** | 我完全没做；用户此前就贴过带 `conversationId` 的 JSON |
| `channel_unverified` + `not proof of zero shops` | 把我 8 轮才学会的教训做成了**枚举值**而非文档句子 |
| `doctor.py` 按任务通道预检 | "缺一个工具全盘报废"是我的设计缺陷 |
| `diner-rubric.md` | "榜单/装修/价格/稀有度都不是好吃的证据""发酵≠不新鲜" |

### 保留我的（候选没有的）

- MediaCrawler 采集层（小红书/抖音登录态持久化）
- 点评真实世界验证：选择器 `a[href*='/shop/']`、三种菜名布局、团购解析
- `references/environment.md`（本机工具实测）、`validation.md`（铁律与踩坑）

### 我在合并中修的三个问题

1. **`radar.py` DB 路径未强制**：文档称"宿主固定"，代码却是 `Path(db).expanduser()`。
   已加 `_allowed_db_root()` 守卫（构造时解析，支持 `FOOD_RADAR_DATA_ROOT` 覆盖），
   拒绝 `../` 逃逸与根下嵌套目录；补 3 条用例。
2. **候选 `parse_detail` 缺推荐菜/团购**：已按其"只读可见文本、不扫隐藏 HTML"原则追加，
   未破坏 `requires_visual_verification=True`。
3. **`doctor.py --channel media` 未接实际路径**：已加 MediaCrawler 根自动探测、
   node 路径、以及登录 cookie 落盘检测（明确标注 **NOT VERIFIED**，cookie 存在≠会话有效）。

### 合并中我自己写出的 bug（都由测试/真实数据抓到）

- `mkdtemp` 误从 `shutil` 取（实际在 `tempfile`）→ 登录态检测静默返回 null
- 团购正则要求套餐名与 `¥` 同行 → **合成测试过了，真实页面失败**
  （真实是 `¥\n2980` 跨行）→ 改为跨行 + `¥\s*`，并补真实布局回归用例

## 二、测试

```
python3 -m unittest discover -s scripts -p 'test_*.py'
→ Ran 42 tests ... OK   （候选 38 + 我新增 4）
```
已在本机 Python 3.12 独立复跑通过。

## 五、未完成项的真实状态（2026-10-18 收尾核对）

### ✅ P1 主体：三入口路由 + 卡片输出 —— 已落地
`references/prompt-template.md` 重写为可直接套用的句式：五类入口识别、
三入口命令、卡片模板、活动两栏格式、深查流程、**"组合无解直接说无解"的硬要求**、
可挂任意 agent 的系统级约束。

### ✅ P2前置：真实记录落库 —— 已完成
`evidence/2026-10-17-restaurants.json`：当霁、ONCUE 两条按 v2 契约的快照，
全部带 `basis` / `origin_id` / `observed_at`。已用真实数据端到端跑通
ingest → save → shortlist → wishlist → changes，幂等正确（重复入库为 `refreshed`）。
ONCUE 的 `business_status` 存为 `unknown`——页面显示"暂无营业时间"，不足以判定在营。

### ⚠️ P0「点评解析器转 DOM 选择器」—— **未成功，假设被实测推翻**

原计划"正则对改版脆，改用 DOM 选择器"。实测真实页面后结论是**两者都不稳**：

| | 当霁 第一次加载 | 当霁 第二次加载 |
|---|---|---|
| DOM 选择器 | score 4.7 ✅、address ✅、review "38人推荐" ❌ | **全 None** |
| 文本锚定解析 | 全 None | 全 None |
| 推荐菜 / 团购（文本） | ✅ | ✅ |

要点：
1. **DOM 选择器跨次加载不稳定**，同一页面两次运行结果不同。
2. **宽松选择器 `[class*=comment]` 会把"38人推荐"当评价数** —— 已在
   `parse_detail_dom` 中改为逐字段形状校验，不合形状即丢弃，并加了 5 条回归。
3. **文本锚定解析在本页取不到 score/price/address**：这些值肉眼可见（截图确认）
   但 innerText 里没有 `地址：` 这类行首标签，锚定模式匹配不到。
4. **页面内容每次加载会变**：同一店铺团购名出现过「相遇」「相逢」两种。

**已做的改进（仍然有效）**：`parse_detail_dom` + `merge_detail` 双通道，
DOM 优先、文本兜底，每字段形状校验，一律带 `requires_visual_verification`。
测试从 42 → **47**。

**未解决**：要稳定拿到 score/price/address，需要的是
① 更长的 JS settle 时间 ② 每次运行前重新探测有效选择器 ③ 失败即走
`channel_unverified`（而非报"抓到了"）。
**不要再把"解析器换成 DOM"当成已完成的 P0。**

### 🔒 小红书登录态 —— 阻塞，等用户扫码
cookie 落盘但会话已失效（`Login state result: False`，页面重定向 /login）。
ONCUE 的跨平台同名冲突（西餐 vs 顺德菜）因此仍未验证。

### ❌ 定时订阅 —— 未做（设计如此）
`changes` 只是可消费的增量日志，不含 cron、不发消息。仅在用户明确要求后才接宿主调度。

## 六、诚实边界（未验证/未做）
（未验证/未做）

- 测试数据**全部合成**，`.example` 域名；无真实用户找店质量评估
- 无定时调度：`changes` 只是可消费的增量日志，**不含cron、不发消息**
- 小红书登录态2026-10-18 已过期，需重扫
- 候选来源未联网，所有公开检索仍依赖宿主实际能力

## 七、下一步（按优先级）

1. **P0'** 点评字段稳定化：JS settle 时间 + 选择器运行时探测 + 失败即
   `channel_unverified`。**不要再假设"换 DOM 就稳了"。**
2. **P1** 用真实数据评估找店质量（当前只有 2 条记录、全部来自点评，无UGC 交叉）
3. 恢复小红书登录态，补 ONCUE 跨平台同名验证
4. P2 扩展：把 feedback/历史到访落库，验证"下次记得你想吃什么"
