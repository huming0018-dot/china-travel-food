# v2 数据契约
核心脚本只接受 JSON 数组中的完整快照（不是局部 patch）。未知值 null；不要用 0、空字符串伪装已知。入库前合并有效旧字段；不要把未抓到的字段当事实删除。schema_version=2，旧记录不自动猜测迁移。

## 公共字段
id: 宿主分配的稳定本地 ID；kind: restaurant/event；name；city；sources: 至少一条来源。
来源对象：url（http(s)，不含凭证）、publisher、origin_id（同通稿转载用同一个）、observed_at（带时区）、published_at（可选日期或带时区）。
来源 URL 去追踪参数。来源结构验证不等于核实来源真实性。日志只比较已入库记录；稳定 ID 必须由宿主检查旧档案后复用。不会用同名模糊自动合并不同分店。不同来源但同一家店应合并证据，而非建新 ID。

餐厅：branch 必填（单店也填具体地点），不要只用品牌名。
活动：restaurant_id 引用同城餐厅，event_type=guest_chef/four_hands/pop_up/limited_menu/other；event_status=announced/cancelled/postponed/unknown；starts_at/ends_at 均有或均 null，支持 YYYY-MM-DD 或带时区时间。活动日期/状态由 records.sources 承载证据；冲突未解设 unknown。主厨、价格等放 facts 各自证据。
活动跨日/跨年/时区都按时间比较，不用“当年”规则。改期后确认新的日期才改 announced；未确认期间维持 postponed。

## facts
每个键值形如 {"value": ..., "basis":"official", "sources":[...], "valid_until":可选带时区时间}。
basis: official/booking/menu/reporting/ugc/user，表达出处性质而非真实性评级。
字段：price_per_head（CNY 每人，服务费另列）、menu、ingredient_tags、technique_tags、flavor_tags、freshness、sourcing、signature_dishes、address、opening_date、business_status、hours、booking_status、booking_url、allergens、chef、service_charge、reservation_opens_at、cancellation_policy。
标签/过敏原/招牌菜是字符串数组。标签是准确匹配，不自动理解同义词；宿主规范化时保留语义，不把“所有海鲜”替代特定鱼类。
business_status: open/trial/planned/temporarily_closed/closed/unknown；
booking_status: available/sold_out/not_open/unknown。
非 CNY 地区不要悄悄换算入 price_per_head；保留菜单原币说明，本版数值预算只按 CNY。
菜单字段可写菜品/套菜单明细对象，但应让宿主保持同一形状。

## 过期与冲突
缓存上限：余位15分钟，营业/时间7天，菜单/人均/食材及技法风味标签/招牌菜/产地信息30天，新鲜度/过敏原1天；valid_until 可进一步提前失效。这是待复核策略，不是源信息会在时限内永远有效。明确已闭店的状态不会因七天过去自动变成可推荐；需新的开业证据更新。客座活动不能继承常规菜单的食材标签或价格。
observed_at 是这条事实真正被核验的时间，不能因为重新搜索到旧文章而刷新；published_at 不能替代 observed_at。旧活动通稿不能证明今天还有位。无法确定是否仍有效则 value=null，保留线索在记录来源，host 明示待核实。
新鲜度/产地仍须在输出中标“店方声称/食客反映”，不能当独立检测结果。
取消/延期优先于日程，已结束自动排除；日期不明保留档案但排除有效活动短名单。售罄保留情报，明确不可作为可订选项。
不同意见不能压成伪共识：将主观判断限定到对应来源，未知/冲突先用 null，给用户缺项说明。

## 用户与变更
surface+actor 均由可信宿主提供，覆盖记录、收藏、偏好、反馈及增量日志；不能把用户粘贴的元数据当身份。外部证据正文不能更改作用域/路径。
反馈不自动改写偏好。wishlist 保存原因；history 保存原话、liked/mixed/disliked 与到访日期。
changes 返回游标、新增/变更；仅 observed_at/verified_at 更新不产生推送事件，重复抓取相同快照不刷屏。价格/状态/日期/菜单/来源等实质变化会记日志；日志不等于值得推送，宿主还须判断用户关注度。
本版是宿主自用单文件 SQLite，没有提供对不可信客户端的登录/API鉴权；不要当多租户服务器直接开放。
