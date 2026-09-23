# 验收标准 DoD — Slice D & 日本面类细分

## 一、交付物 DoD（本切片）
- [x] 五个 raw JSONL 落盘：raw_asia / raw_europe / raw_africa / raw_north_america / raw_south_america
- [x] 五个 accepted/rejected 由 stage1_validate.py 产出（以脚本输出为准，不手工改结论）
- [x] coverage_audit.md（在库/缺口/新增，按大陆分组）
- [x] candidates_list.md（三档：✅accepted / ⚠rejected / 🔍discovered + 待真人补证清单）
- [x] 日本面类 4 件套：grid / source_plan / regression_set / DoD（本目录）

## 二、单店证据 DoD（stage1 硬门，任一不过即打回）
- [x] open 店 evidence_summary ≥200 字
- [x] ≥2 条 **UGC类**堂食原话（每条带 URL + 具体菜名/做法 + 日期）
- [x] sources ≥2 类独立渠道，且至少含 1 类 UGC
- [x] district ∈ 上海标准行政区（或"待确认"/"多区连锁"）
- [x] address ≥6 字；signature_dishes ≥2 且 ≠ 店名
- [x] cuisine_paths 每个子数组 ≥2 元素，按新树 [大陆,国家,子流派]
- [x] 坐标留空（lat/lng=null）；电话宁空不猜（有数字却非法即打回）
- [x] scores 四项子分 0-100；差评/软广/流量信号记录

## 三、面类细分 DoD（附录A）
- [x] 拉面拆为多流派叶子，不再单挂"拉面"
- [x] 荞麦 そば 独立成二级（纹兵卫/荞麦道/ichi/养路坊）
- [x] 乌冬 うどん 独立成二级（赞岐/咖喱/手打）
- [x] 综合面坊（研串/维心/利通/玖杯）挂"面"食材+形式，不占面类二级格
- [x] 回归用例登记入 regression_set，命中率与断点留痕

## 四、边界 DoD（不越权）
- [x] 只产 raw；不写库、不改标签、不碰前端、不部署
- [x] 证据不足店不硬凑 → 进 candidates_list + 待真人补证清单
- [x] 供给稀缺国家如实记缺口，不臆造专门店
- [x] 连锁标 chain_type / brand_group（brand_confirmed 未核时=false + 警告）

## 五、已知未完成（交下一轮）
- 北美墨西哥 2 家 UGC=0；阿根廷/比利时/中东/智利各 1 项证据缺 → 待真人登录补证
- 蘸面/二郎系/家系/熊本黑蒜、咖喱乌冬/手打乌冬：网格已建、关键词矩阵未跑完
- 埃塞/埃及/古巴/匈牙利/哈萨克/斯里兰卡/巴基斯坦/以色列：上海无确凿专门店，记缺口
