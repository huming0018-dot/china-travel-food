# 漏店反推证明（10 家已知漏店）

| 店 | 菜系×场景格 | 应抓源（source_id） | 当时为何没抓 | 应补动作 |
|---|---|---|---|---|
| nabi | 日料×正餐 | xhs_apify_sian / guide_michelin / media_timeouts | XHS 账号 parked；米其林 sitemap 已覆盖但未抓小馆 | Apify XHS 上线后搜「nabi 上海」 |
| jelu | 融合×bistro | xhs_apify_sian / media_tv / rss_smartshanghai | UGC 通道断；媒体未注册 | 注册 timeouts/smartshanghai RSS |
| yaya's | 中东×正餐 | xhs_apify_sian / guide_tripadvisor | 小红书关键词未跑 | Apify XHS 首跑 |
| nono's | 西餐×bistro | xhs_apify_sian / media_timeouts | 同上 | Apify XHS + TimeOut 补 |
| 望庐·精细江西菜 | 赣菜×fine-dining | guide_blackpearl / xhs_apify_sian | 黑珍珠 hold 4 家之一；UGC 未跑 | Apify XHS 优先补；黑珍珠 7 家 hold 清单挂队列 |
| 醉冬 | 日料×omakase | xhs_apify_sian / guide_michelin | UGC 断 | Apify XHS 首跑 |
| 佐佐 | 日料×割烹 | xhs_apify_sian / guide_michelin | UGC 断 | Apify XHS 首跑 |
| 鮨照 | 日料×omakase | xhs_apify_sian / guide_michelin | UGC 断 | Apify XHS 首跑 |
| ministry of crab | 海鲜×fine-dining | guide_michelin / media_overseas / rss_instagram | 海外/外语社区源未注册 | 注册 Instagram/TripAdvisor 源 |
| 8by8 | 融合×bistro | xhs_apify_sian / media_tv | UGC 断 | Apify XHS 首跑 |

**结论**：10 家中 8 家的核心缺口是「小红书 UGC 通道断」（账号 parked），2 家缺海外/媒体源。Apify XHS 上线后 8 家可立即补。
