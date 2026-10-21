# 录后校验 · 流程优化与经验沉淀 v2（2026-10-21）

> 上海美食图鉴「录后校验·搜索引擎校准」定时任务（工作日 07:20，周一至周六增量、周日全量复扫）。
> 本文沉淀 10-01 全量至 10-21 增量共 20+ 轮运行的实测经验与流程优化，作为后续每轮执行的标准依据。
> 核心原则一句话：**宁空不假 + 容器门控以脚本实测为准 + 批量/并发/落盘纪律决定产出效率**。

---

## 0. 产出效率提升（2026-10-21 用户三指令）

| 项 | 旧 | 新 | 机制 |
|---|---|---|---|
| 每日增量批大小 | 40 店（planner --batch 40） | **120 店（--batch 120）** | findings_planner.py `--batch`，取「新增 active + 从未审计 + data_updated_at 变化 + 待复查」池前 N 家 |
| 每日候选行目标 | ~20 条 | **≥60 条** | 批大小 3 倍 + 单店多字段 |
| 单店产出 | 多只写 chain_type / investor_info | **同店尽量补齐 price_avg / central_kitchen / premade_risk** | 一店一次取证多字段，减少重复跑 |
| 全量复扫 | 48 取证单元 → 0 产出（10-18 失败） | **12 片 / 3-4 并发 / 每片完成即 flush / 逐片核对** | 见 §7 |

已同步更新定时任务 13364749493762 的 query（2026-10-22 起生效）。

---

## 1. 容器门控实测白名单（findings_ingest.py 权威，覆盖任何纸面口径）

`is_trusted(url,title)`：先判 NOISY 命中即 false，再判 TRUSTED 片段匹配（url 或 title 小写子串）。

- **NOISY 硬杀**：sohu.com/a、163.com/dy、baijiahao、zhihu.com/question、xiaohongshu.com/search|explore、toutiao.com/group、m.toutiao.com、douyin.com、iesdouyin、ctrip、jobui、jiameng、zhipin、shuidi.cn、china.com/、jianlimo、1637.com、21food
- **TRUSTED 放行**：meituan.com、dianping.com、michelin.、blackpearl、timeout、smartshanghai、official、weixin、mp.weixin、.gov.cn、.gov.、**qcc.com / qixin.com / tianyancha.com / aiqicha.com**、news.cn、xinhuanet、xinhua、people.com、chinanews.com、gmw.cn、cnr.cn、jjckb.cn、ce.cn、zgswcn.com、bjd.com.cn、bjnews.com.cn、xinmin.cn、xinminweekly.com.cn、yunnan.cn、tmtpost.com、thepaper、jiemian、36kr、yicai、stcn
- **OFFICIAL 硬负面（单源即可）**：.gov.cn、.gov.、news.cn、xinhuanet、xinhua、people.com、chinanews.com、gmw.cn、cnr.cn、jjckb.cn、ce.cn、samr
- **实测不放行（勿再用）**：diningcity.cn、rednet.cn（moment.rednet.cn）、hilton.com / hilton.com.cn / waldorfastoriahotels.com.cn / stories.hilton.com、huanqiu.com（环球网）、eastday.com（东方网）、shobserver.com（上观）、h5.ifeng.com（凤凰）、stheadline.com（星岛）、news.qq.com / view.inews.qq.com（腾讯）、sina.com.cn / finance.sina、shinkong-place.com、meet-in-shanghai.net、fznews.com.cn、flyert.com.cn、cncn.com、cafa.edu.cn（.edu.cn 非 .gov）
- **food_safety 注意**：ingest 接受「问题」；post_audit 入库时 to_db_value 自动映射 DB「确认」落库 204（DB CHECK 只认 无/疑似/确认，见 §4.7）；禁止手写 PATCH 直传「问题」。

---

## 2. 取证与候选规则（每店）

- 每店 2 条合并 general_search：①「店名 连锁 分店 集团 老板」②「店名 预制菜 中央厨房 人均」；据真实返回标题/摘要/链接判候选，**不用模型记忆当证据**。
- 候选 schema 严格：`restaurant_id,name,field,value,confidence,source_url,source_title,reason`
- field/value 枚举：chain_type∈独立店/小型连锁/大型连锁/资本化连锁；central_kitchen∈无/疑似/确认；premade_risk∈无/低/疑似/高；food_safety∈无/疑似/问题；investor_info=自由文本；price_avg=数字
- confidence：官方/权威新闻/≥2 独立来源互证且明确才 ≥0.8；单一来源/推断/存疑一律 <0.8 丢弃
- 保守铁律：
  - 硬负面（central_kitchen=确认 / premade_risk=高 / food_safety=问题）需 ≥2 独立可信源或官方源
  - 连锁可用「点评分店列表 + 工商注册主体」互证；同名异址分店保留
  - 排除同名不同店（如「吉兆」≠日本京都吉兆）；多「席」系/多「瓯」系先消歧再落
  - 营销号/SEO 聚合/百家号/小红书搜索页/知乎问答页一律不用

---

## 3. 源替换速查（实测不放行的源 → 可用替代）

| 场景 | 不可用源 | 替代 |
|---|---|---|
| 高端餐厅集团/酒店 | hilton / waldorf stories / diningcity | 经济日报中国经济网 ce.cn、中新网上海 sh.chinanews.com.cn、界面 jiemian |
| 人均/经营数据 | diningcity、ctrip（NOISY） | 放弃该行，或 dianping/meituan（白名单） |
| 连锁规模新闻 | rednet 红网、huanqiu、eastday、shobserver | qcc/qixin/tianyancha/aiqicha 工商主体 + 光明网 gmw / 澎湃 thepaper |
| 主理人身份 | stories.hilton、ifeng | 界面 jiemian 人物报道 + 米其林官网 michelin.com.cn |
| 工商主体 | qcc 访问超频时 | qixin / tianyancha / aiqicha 轮换 |

---

## 4. 流水线顺序与坑

1. **备份**：容器 `/tmp/findings.bak.<date>`（apply 前 cp findings.jsonl）+ `/tmp/scan_ledger.bak.<date>`。
2. **两轮 dry-run**：findings_ingest --input 候选（dry）→ 读 DROP 原因修正源/URL → 再 dry 至 0 DROP → --apply。
3. **ingest --apply**：校验枚举/可信源/conf≥0.8/按 rid+field+url 去重，append findings.jsonl（同 URL 挂不同 field 或不同 rid 不冲突，key 含 field/rid）。
4. **post_audit --apply**：**只喂本次 candidates_<date>.json，绝不喂全量 findings.jsonl**（防重放历史弱源）；只改 chain_type/central_kitchen/premade_risk/investor_info/price_avg/food_safety 六列；`is_chain_standardized` 是 generated 列不能 PATCH（428C9）。
5. **DB 回读**：`sys.path.insert(0,"/app/pipeline"); import common as C; C.fetch_all(table, select=..., extra="&id=in.(...)")`（容器有两套 common，必须用 /app/pipeline 的）。
6. **price_avg 必须整型（DB 列 integer）**：post_audit 对候选数字序列化 `88.0` → PATCH 批量 400 `invalid input syntax for type integer`。修复：容器脚本 `fix_price_avg_1018.py` 读 audit 账本 `field=price_avg and http!=204` 行 → `int(float(value))` 重 PATCH → 追加 204 账本行 + readback（10-18 全量批 20 行 + 早间增量/自动流水线 dianping 行共 136 店，OK=136 FAIL=0）。**候选侧写整数、无小数点**可根治。
7. **food_safety「问题」落库映射**：ingest 接受「问题」；post_audit 的 to_db_value 自动映射 DB「确认」落库 204（DB CHECK 只认 无/疑似/确认）——10-18 实测 6 店（有喜屋/段氏龙虾/一绪/小菜园/云海肴/When Pigs Fly）全部 204 且回读=确认，无需放弃；仅当手写 PATCH 直传「问题」才会 400。
8. **scan_ledger**：逐 rid 写 `{date, n_results, n_kept, provenance}`；有候选=incremental:general_search，无=incremental:general_search:zero；周日置 last_full_date。**n_kept 是最近一次扫描采纳字段数快照、非累计**，覆盖旧值属正常（5284→5146 即此因，非丢数据）。
9. **点评日更核查**：`stat -c %y /app/data/dianping_daily.log`（当日 06:40 mtime + active=1517 done=1517 todo=0 = 成功）。

---

## 5. TG 推送纪律（deuce 本地，容器/反代均已失效）

- 脚本：city-food-guide skill `scripts/tg_send.py`；凭据自动读同目录 `.tg_env`；直连成功 route=direct，失败用 `HTTPS_PROXY=http://127.0.0.1:7900`（**7897 已失效**）。
- **禁止 `cmd || echo && retry` 串联**：即使第一条成功也会执行 retry 分支 → 10-21 误发两条（2467+2468），教训已入账；必须单独发送、失败再单独重发。
- 误发补救：bot 48h 内可 deleteMessage 撤回自己消息。
- 容器 cloud/notifier.py 直连被墙、Deno 反代 503，**禁止容器内推送**；飞书通道已彻底移除。

---

## 6. 全量复扫运维（10-18 重跑方案）

- **分片**：12 片（首轮成功档：11×127+120）；**不要切 48 单元**（10-18 实证：48 单元 → 0 产出，线程死亡 thread id not found）。
- **并发**：3-4（8 线程并发被杀 137）。
- **落盘**：每 SubAgent 每完成 ~10 店即追加写 `/tmp/ctfs/fullscan/shard_<NN>.jsonl`（候选行）+ `_zero.txt`（0 发现 id），**禁止攒到最后一次性写**；完成回读确认行数。
- **回收**：OrganizerAgent 逐片核对 12 个 .jsonl + 12 个 _zero.txt 存在且行数合理再回收该片；核对不通过重派该片。
- **闭环**：收齐合并 candidates_2026-10-18.json → ingest --apply → post_audit（显式、只喂本次候选）→ ledger（置 last_full_date=2026-10-18、逐 rid）→ TG 全量报告。
- 复用输入：deuce `/tmp/ctfs/active_full_20261018.json`（1517 店）+ `/tmp/ctfs/shards/shard_01..12.json`。

---

## 7. 待办与验收（2026-10-21 起）

- **10-18 全量复扫重跑中**（OrganizerAgent o_000EySpZxQ6，12 片后台并行）；收齐后由主流程闭环。
- 每日验收：覆盖 ≥120 店；候选行 ≥60；findings 按 field 增量 ≥60；post_audit 全 204 且 DB 回读一致；ledger last_inc 当日；TG 恰一条；点评日更 DONE。
- 独立店/主体未锚/同名异主 → 如实记 0 findings，宁空不假。
