# Brunch+下午茶 v3 Sourcing 增长曲线

## 基本统计
- 场景: Brunch+下午茶
- v3推广日期: 2026-09-23
- 原始存量: 28家
- 最终raw: 37家（+9新店）

## BFS轮次与新增

| 轮次 | 通道 | 新增候选 | 通过证据门入raw | 说明 |
|------|------|---------|---------------|------|
| R1 | general_search合集 | 14 | 0 | Moving/SOMETHING/MEL BOURNE/Brut/Chez Maurice/emo/LA COUR等初筛 |
| R1 | general_search酒店下午茶 | 8 | 4 | 半岛/浦东丽思/柏悦/璞丽 |
| R1 | general_search班尼迪克蛋 | 5 | 2 | 泥靴Boots/LA COUR(暂存) |
| R1 | general_search定向深挖 | 6 | 2 | 半岛/Brut/SOMETHING/猫尔本/Aura Lounge/柏悦璞丽 |
| R1 | B站采集器 | 2 | 0 | Ocean's Table/Le Pain Sense(偏bistro非brunch) |
| R1 | 公众号采集器 | 0 | 0 | **断点**: site:mp.weixin.qq.com搜索返回空 |
| R2 | 小红书评论区(啵啵糖9家) | 11 | 0 | 夏朵花园(预制菜差评)/古董花园(霉味)等被拒 |
| R2 | 小红书评论区(一颗小金星1072赞) | 4 | 0 | Bistro11/pêcher/Bijou/WOKKA(证据不足或负面多) |
| R2 | 小红书评论区(ShanghaiWOW茶馆10家) | 10 | 0 | 茶馆类证据不足偏茶室 |
| R2 | 大众点评brunch口味榜 | 9 | 1 | CASALUNA(4.7/3726条) |
| R2 | 大众点评下午茶搜索 | 4 | 0 | The Red Macaron/一尺花园/Fuzii/Tiffany Cafe(证据偏弱) |
| R3 | 饱和检查 | 0 | 0 | 连续搜索零新增，frontier清空 |

## 每轮入raw家数
- R1: +8家（泥靴Boots/半岛/Aura Lounge/柏悦/璞丽/猫尔本/SOMETHING/Brut）
- R2: +1家（CASALUNA）
- R3: 0家（饱和）

## 饱和点
- R3连续零新增，frontier清空 → **饱和**
- 机制断点: 公众号采集器(site:mp.weixin.qq.com搜索空)、大众点评商户长评深度受限(页面只展示3条最新评价)

## 种子数
- 高置信种子(ugc≥2): 28家全部满足(每家3条diner_quotes)
- BFS起点: 全部28家

## 坐标率
- 已有坐标: 9/37 = 24.3%
- 新增9家坐标均为null(待腾讯拾取器补)
