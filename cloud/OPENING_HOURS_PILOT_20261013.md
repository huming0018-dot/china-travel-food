# 营业时间补齐：实现与生产试点交接

状态：2026-10-13，基于 main a93a1c2。本次取得当前源码并完成隔离实现；DevSpace open_workspace 返回 Internal error，当前无 kimi-cu，因此没有读取生产数据库、没有实际回填、没有部署。禁止把离线测试记作线上覆盖率改善。

## 已核实与待核实

HANDOFF 记录 active=1517、地图队列549、营业时间覆盖66.1%；均为已有生产记录。本次未重查数据库。从四舍五入比例只能估计约514家缺失、约94%地图候选存在营业时间缺口，不能当精确计数。运行脚本默认 audit：给出当前 active、地图队列、hours_missing、队列内占比和缺口组合；review_count不参与。

当前地图代码：高德v3读取biz_ext.opentime2/open_time；腾讯fallback明确hours为空，仅补电话与坐标。高德v5官方文档提供business.opentime_week/opentime_today，需要show_fields=business。字段存在不代表请求权限或真实覆盖率。下一步优先在现有map_quota配额池内用10家已匹配POI验证v5字段；本补丁不修改跨Key恢复逻辑，不自动打开未经核查的v5端点。今日时间不能当周营业时间。

## 渠道比较与执行边界

| 渠道 | 数据与成本 | 授权/访问 | 保鲜/覆盖能力 |
|---|---|---|---|
| 高德现有v3 | 已授权池内一次查询多字段，账本计次 | 沿用现有密钥与合同；v5权限及留存条件仍须核查 | 高覆盖匹配、营业时间可能空；v5覆盖尚待10店实测 |
| 腾讯现有fallback | 电话、坐标；本实现不为hours调用腾讯 | 现有许可；没有确认hours字段，不额外烧请求 | 当前不能补hours |
| 餐厅/品牌具体门店官网 | 免费HTTP，一页可提供时间、地址和电话 | 公开可读不等于允许批量转载；登记具体rights_basis、审核人和域名，遵守robots | 官方可靠但页面可能不更新；建议30天复核，这是策略并非源站承诺 |
| 官方酒店餐厅/商场门店页 | 具体餐厅块可补；每来源最多robots+页面2次HTTP | 同上，必须定位具体餐厅，不继承酒店/商场营业时间 | 酒店餐厅存在公开样例；真实549店覆盖未知 |
| 商户授权信息渠道/美团/点评 | 商户API可能有营业配置，价格由合同决定 | 需要商户/合作授权；已有点评通道是否有hours须检查；不绕登录、不购买新服务 | 不承诺全市场可读/实时；授权后才启用 |
| 搜索摘要/游记/模型 | 可提供候选URL | 只用于发现，不能写事实 | 日期、分店、休息日常不明；禁止直接回填 |

官方样例：https://www.marriott.com/en-us/hotels/shamc-shanghai-marriott-marquis-city-centre/dining/ 。同页多个餐厅时间不同；另一个Shanghai City Bistro位于333 Guang Zhong Road West，与市中心店不同，不可按英文同名合并。本次只确认公开源存在，未确认样例属于缺口池。

API依据：https://developer.amap.com/api/webservice/guide/api-advanced/newpoisearch ，https://lbs.qq.com/webservice_v1/guide-search.html 。费用、商业数据留存许可和源站更新时间不作未经核实的承诺。高德服务协议 https://developer.amap.com/pages/terms/ 的4.12及7.3限制超授权抓取/存储/缓存与独立展示，不能将有API key视为自由入库许可；需要核查项目实际合同。美团官方门店映射文档明确商家选择门店并授权数据，不能视为全市场公开查询接口。

## 本补丁

- `opening_hours_backfill.py`：默认只读审计；`--collect`才发HTTP，`--apply`只追加findings。候选必须active、hours=NULL、有审核过的来源。精选优先、缺口严重程度其次、rid稳定排序；不以人均价格冒充价值评分。
- 来源manifest每行包含restaurant_id、url、approved_host、platform、access_review=approved、rights_basis、reviewed_by、restaurant_block、hours_quote。block必须是页面原文且含库内精确店名、地址及原始时间。无法满足时hold，不靠模糊匹配猜分店。manifest是运维审核产物，禁止模型自批授权。
- 每批默认20店、40请求，上限30店/60请求；每店最多2来源，每来源1次robots+1次页面。无重定向、无登录/cookie、无网络自动重试；每店30天冷却、累计3轮后停，需要取到新证据后人工复核重置状态。并发flock；逐店原子保存状态。
- 解析仅支持明确每天的一段24小时区间（如每日11:00-22:00），跨午夜保留overnight；缺weekday、节假日、预约制、午晚分段等暂hold。保留raw、source_url、source_platform、UTC captured_at、parsed、parser_version和冲突决策。不将不完整解析变成完整事实。
- `gate_apply.py`：hours单独仲裁；30天内同店新鲜证据、确定性重解析一致才准入；有效来源冲突hold；非NULL现值一律保护；写时active+opening_hours=is.null原子条件；响应与独立回读一致才记成功。旧仅raw候选进入hold，须重新取得结构化证据。这会减少弱证据自动写入，是有意的门控。
- hours专属账本与状态，不写reviews、不读取G2任务、不触发Apify、不占评论预算。未知不排无限地图任务。

## 操作与验收

1. 恢复已有SSH连接后，先运行 `python3 /app/cloud/opening_hours_backfill.py`，保存原始缺口分布；与549/66.1%对照并记录时间。检查缓存已匹配POI及现有点评输出字段，先复用证据。
2. 在实际缺口池中选择20店：有官方源的精选10店、严重缺口5店、随机对照5店（对照仅审计，不能为无源店造manifest）；人工核查URL归属与访问/留存条件。当前代码自动挑选有审核源候选，分层名额须用来源manifest控制。
3. 先 `--collect --sources /app/data/hours_sources.json --limit 20 --max-requests 40`。逐条复核同店、区间、时区、周休/节假日是否遗漏；若hold则保留原始来源供扩展解析，不转成模型补值。
4. dry-run会消耗请求并设置冷却。通过证据复核后，用单独试点状态目录重取、追加findings（显式设置FOOD_DATA_DIR，仍复用同一个findings账本）；不要把默认状态清空后每天重复抓取。更优后续版本可支持已验证候选重放，当前不自动重放。
5. 运行 `python3 /app/cloud/gate_apply.py --hours-only` 审查营业时间计划，通过后加 `--apply`；此模式只写hours、使用独立worklist，不执行其他标签/精选写入。本次未触发生产gate。
6. 复查成功rid当前hours、NULL数量和active分母，报告实际净增、覆盖百分点、同店正确率、冲突/hold数、每条有效写入请求数、API账本增量、HTTP墙钟。candidate_hours是证据候选数，绝非数据库回填数。
7. 扩大条件（提议，尚非实测结果）：试点全部写入独立回读一致、抽查零错店/零人工覆盖、预算未超、净改善且有足够来源；未通过不加批量、不装cron。没有源的店NULL保留。

部署走已有build_sync镜像流程；同时固化已有跨Key修复，不用docker cp作为最终发布。回滚代码不会自动删除已确认时间；若需要撤回试点，仅按本批证据ID/时间指纹恢复，且再次检查现值未被人工更新。

## 测试记录

14项隔离回归通过：每日/跨夜、非法/模糊时间、冲突、过期、旧raw、解析篡改、评论队列隔离、默认访问闸、请求预算、条件写入、并发人工事实保护及失败回读。生产请求0、生产写入0、真实覆盖改善待验收。

公开源补充抽查：LES NUAGES官网 https://www.yongfugroup.com/lesnuages 有具体上海地址和午晚餐分段时间，但没有明确星期范围，当前保守解析应hold。甬府小鲜 https://www.yongfugroup.com/yfxx 列多城市门店而页尾放通用营业时间，不能自动继承给所有分店。这两项验证了来源筛选的重要性，并非生产回填验收。
