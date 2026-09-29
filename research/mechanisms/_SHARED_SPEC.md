# 共享施工规约（SHARED SPEC）—— W1–W5 并行机制建设

> 本文件是五个并行工作流代理共同遵守的硬约束。目标：产出**确定性脚本/模块 + 状态账本 + 被质量门调用**，
> 不接受"只写文档"。北极星：口味唯一最高、宁空不假、机制优先不补单店、信源沉淀、账号最后手段、闭环自检。

## 0. 路径与运行方式（机器=deuce，勿用 MacBook / 另一台 HAE）
- 项目根 `ROOT=/Users/deuce/Doubao/chats/2026-09-28/new-chat-1/china-travel-food`
- 共享连接层用 **`$ROOT/cloud/vendor/pipeline/common.py`**（读 `app/.env.local`，已在 deuce 配好、gitignored）。
- 所有自写 Python 必须带环境变量：`FOOD_APP_DIR=$ROOT/app`，并 `sys.path.insert(0, "$ROOT/cloud/vendor/pipeline")`。
  注意存在多个同名 common.py，**只 import 上面这个**；不要用 skill 里或 HAE 路径（/Users/hubowen/...）的副本。
- 一行运行示例：
  `cd $ROOT && FOOD_APP_DIR=$ROOT/app python3 your_module.py --dry-run`
- 现状基线（只读核对用）：restaurants 1478 / active 1472、reviews 1716、cuisines 347、chefs 59、
  restaurant_chefs 79、restaurant_groups 10 / members 47、lead_hypotheses 64、kol_watchlist 50 / posts 104。

## 1. 通道红线（最高，违反=失败）
- **本轮 Apify 付费额度已耗尽（剩约 $0.00066）、账户无支付方式：禁止调用付费 Apify 或任何产生费用的通道。**
- 只走免费通道：`general_search` / `web.fetch`（免费 web 搜索与权威页）、权威 sitemap/公开 API、
  地图 POI 免费额度、Supabase REST、确定性脚本。
- 浏览器：优先不依赖；确需时遵守现有串行锁、单实例，避免与 HAE 冲突。账号当前 parked，不硬刷、不触发登录/短信。
- 密钥只在 gitignored `app/.env.local` / `cloud/deploy.env`，**绝不打印、外发或写进任何产物**。

## 2. 每个工作流统一交付物（缺一不可）
1. **确定性模块**：模型只做"发现+语义判断"，机械环节（匹配/清洗/校验/门控/幂等写/回读）走脚本。
   - 规范运行副本放 `$ROOT/cloud/<module>.py`（运行时、进 git）；
   - 同时**沉淀进 skill**：复制到
     `/Users/deuce/Library/Application Support/Doubao/Default/.doubao/agent_mode/workspace/.user_skills/city-food-guide/scripts/food_pipeline/<module>.py`。
   - 模块默认 **dry-run**；`--apply` 才写库；写库幂等；**写后必须回读断言**（re-fetch 并 assert 值/行数）。
2. **状态账本**：`$ROOT/research/mechanisms/<wf>/ledger.json`，固定骨架：
   ```json
   {"workflow":"Wx","version":"2026-09-29","generated_at":"...",
    "denominator":{...},"frames":[...],
    "items":[{"id":..,"name":..,"frame":..,"evidence":..,"decision":..,"source_urls":[..], "discovery_path":".."}],
    "stats":{...},"gaps":[...],
    "regression":{"<点名店>":{"found":true,"discovery_path":"<框/源/查询>","restaurant_id":..}}}
   ```
   另存中间证据/种子到同目录（如 seed.json、candidates.jsonl）。
3. **被质量门调用**：把模块挂到对应质量门（见各 W 指定），并在账本记录 gate 名称；只 standalone 跑=未实现。
4. **skill 文档沉淀**：为该 W 新建**独立** reference 文件
   `references/<wf>-*.md`（新文件，避免与他人并发改共享文件）；
   共享文件 `SKILL.md` 的 References 行、`mechanism-master-v4.md` 绑定表行**不要自己改**——
   在最终回报里给出"应追加的原文行"，由 Organizer 统一合并。

## 3. 回归用例铁律（A3）
- 点名店一律是**回归用例**，不是手工待补清单。机制跑完若没自动捞到 = 发现机制有断点，
  修机制（来源/抽样框/关键词/解析器/闸门）后重跑，**禁止手工 REST 补这一家**。
- 每个回归用例必须能在 ledger.regression 指出**自动发现路径**（哪个抽样框 F1–F6、哪个源、什么查询、哪条 URL）。
- 权威榜单走全量召回并与官方总数对账，缺店"详情取证→够门槛入库"闭环；近名异店排除、同名异址分店保留。
- 只采信真实食客堂食/可溯源事实；电话/坐标/评分宁空不猜（宁空不假）。

## 4. 写库与冲突避免
- 任何写数据走脚本，禁止绕过脚本手工写 REST。
- 各 W **只操作归属自己的 cuisine 叶子 id 集合**（见各 W subtask），互不交叉；
  对 `restaurant_cuisines` 做"补链接"，不删除他人/他类链接。
- **禁止 `git add -A` / `git add .`**：deuce 工作区有一批"旧在途删除"（app/pages/chefs|groups、
  cloud/kol_monitor.py、cloud/source_registry.py、cloud/ugc_longrun.py、cloud/review_ugc_fill.py 等，
  远端仍保留）。**不要提交这些删除、不要恢复/新建这些被删路径、不要删除它们。**
- **本阶段不要 git push、不要改 HANDOFF.md**（由 Organizer 最后统一合并，避免与 HAE 高频推送冲突）。
  最终回报里给出"应追加进 HANDOFF 的章节原文"和"新建/修改文件清单（绝对路径）"。

## 5. 完成回报格式（给 Organizer）
- 落地模块绝对路径（cloud 运行副本 + skill 副本）+ 挂载的质量门；
- 账本绝对路径 + 关键统计（分母/召回/补缺店数/纠错数/仍缺口）；
- 每个回归用例：found 与否 + 自动发现路径 + restaurant_id；
- 新建 skill reference 路径 + 应追加到 SKILL.md / mechanism 绑定表的原文行；
- 应追加进 HANDOFF 的章节原文；仍待人工项（尤其 Apify 充值门）。
