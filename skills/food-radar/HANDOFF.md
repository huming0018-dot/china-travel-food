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

## 三、诚实边界（未验证/未做）

- 测试数据**全部合成**，`.example` 域名；无真实用户找店质量评估
- 无定时调度：`changes` 只是可消费的增量日志，**不含cron、不发消息**
- 小红书登录态2026-10-18 已过期，需重扫
- 候选来源未联网，所有公开检索仍依赖宿主实际能力

## 四、下一步

1. **P1**：把 PROPOSAL 的三入口路由落地为可执行流程 + 卡片输出
2. **P2**：用 `radar.py` 落真实记录（当霁/ONCUE 已在 json 里，需转 ingest 快照）
3. **P0**：点评解析器从正则转 DOM 选择器（正则对改版极脆）
4. 恢复小红书登录态并补 ONCUE 的跨平台同名验证（西餐 vs 顺德菜）
