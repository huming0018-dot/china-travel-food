# food-radar HANDOFF

> 更新 2026-10-17 ｜ 对应版本 v1.2 ｜ 上次提交见 git log

## 一、已完成

**方法论层**（可复用框架）
- 五步法工作流 + 环境自检（Step 0）
- 四条铁律、字段规范、平台覆盖矩阵、prompt 模板、检索 checklist
- PRD / HANDOFF（本次补齐）

**采集层**（三平台实测跑通）
- 小红书：扫码登录，登录态持久化，40 笔记 / 133 评论 / 11,910 互动
- 抖音：**需 Node** 生成签名，69 条 / 92,910 互动
- 大众点评：Playwright 直采，拿到评分/人均/营业时间/推荐菜/团购
- agent-reach：4/16 通路（Jina Reader 抓原文核对发布日期很好用）

## 二、本次修复（依据外部静态审阅）

审阅指出 5 类问题，**逐条验证后确认 3 条为真缺陷并已修**：

| # | 问题 | 验证结果 | 处理 |
|---|---|---|---|
| ① | `await h.as_element()` 会崩溃 | ✅ 复现：`as_element` 非协程，抛 TypeError | 去掉 `await`；新增 3 城市回归样本 |
| ② | 自检与采集器 profile 路径不一致 | ✅ 复现：`scripts/dianping_profile` vs `browser_data/dianping_user_data_dir` | 统一为 `<skill>/browser_data/dianping_user_data_dir` |
| ③ | 城市硬编码（cityid=1、虹口区、北外滩街道） | ✅ 复现 | 新增 `--city` + `CITY_ID` 映射；地址/荣誉正则改形态匹配，解除行政区绑定 |
| ④ | 安装说明缺前置、`tools/` 不在仓库 | ✅ 部分成立 | `environment.md` 新增第 0 节「变量约定」与「〇、工具安装」，明示 `cd tools/...` 在裸仓库会失败 |
| ⑤ | 校验规则过于机械 | ✅ 成立 | 铁律1 改查询窗浮动 + 独立性判定（转载不算独立信源）；冲突裁决改**按问题类型分治**；field-spec 拆分 `closed`/`suspected`/`upcoming` |

### 修复过程中我自己测试又抓出的 3 个 bug
1. `taste_env_service` 只搜 `flat`(HTML) 没搜 `text` → 分项恒为 None
2. 地址正则跨字段吞并（把"荣誉"字段吃进地址）
3. 评分兜底正则误抓「环境 4.8」当总分 → **按"宁缺毋滥"原则删除兜底**，无「分数」标记时返回 `null`

> 第 3 条的教训：**任何"智能兜底"都可能变成静默造假**。宁可少一个字段。

## 三、关键设计决策与理由

| 决策 | 理由 |
|---|---|
| 扫码登录而非复用 Chrome cookie | Chrome 155 App-Bound Encryption 使自动化提取不可行；`web_session` 为 HttpOnly 控制台也取不到。CDP 模式三次尝试均失败，已停用 |
| 抖音装 Node 而非 Java | execjs 依赖 Nashorn，JDK 15+ 已移除。报错字面提示"缺 Java"是**误导** |
| 放弃 dianping-crawler | 核心接口 `mapi.dianping.com/searchshop.json` 返回 403（加 UA 仍 403），2017 年项目彻底失效 |
| 点评用 headful 而非 headless | 无头会被识别并下发 no-result 模板 |
| 判定"有结果"看 `a[href*='/shop/']` 而非 `.no-result` | `.no-result` 是常驻模板，永远存在于 DOM，用它判断必然误判 |

## 四、留下的最大教训

**2026-10-17 代价最大的一次误判**：连续 8 轮失败后得出"点评自动化不可行"并建议用户放弃。
用户反问"**我能在页面里看到当霁，你却拿不到数据**"——重查发现选择器 `div.shop-wrap` 已下线，
换成 `a[href*='/shop/']` 后**首次即通**。

已沉淀为**铁律4：否定结论必须有正向证据**：
- 禁止用"页面提示不存在"作为"数据不存在"的依据
- 下否定结论前必须先用已知存在的实体做对照实验，证明通道可用
- **用户/人工观察优先级高于工具结论**，冲突时先查自己的假设

配套《工程判据速查表》7 条（见 `references/validation.md` 第七节）。

## 五、遗留问题

见 `PRD.md` 第七节。要点：
- **无增量去重与定时调度**（「每日雷达」目前只是 prompt 模板）
- 点评解析器基于正则，平台改版即失效 → 建议改 DOM 选择器
- `keyword-matrix.yaml` 仍写死上海/2026
- `preflight.sh` 的 Chromium 版本号硬编码
- 微博/快手/贴吧等平台尚未接入

## 六、下一步建议（按优先级）

1. **P0** 建增量机制（按 `note_id`/`shop_id` 去重 + 状态存储）——否则无法做真正的持续监控
2. **P0** 点评解析器改 DOM 选择器
3. **P1** 关键词矩阵与城市/年份解耦
4. **P1** 接入微博/快手/贴吧
5. **P2** 定时调度

## 七、怎么验证这套东西是真的能用

```bash
bash scripts/preflight.sh                      # 1. 环境自检
# 2. 三平台各实采一次，确认"有数据落盘"（不是看 cookie 非空）
python scripts/dianping_fetch.py --keyword 当霁 --detail --out /tmp/dp.json
# 3. 打开 /tmp/dp_detail.png 截图，人工核对提取结果是否与页面一致
```

> 第 3 步很关键：**正则解析必须人工比对截图**，这是目前唯一能发现解析错误的手段。