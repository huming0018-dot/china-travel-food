# Grid Gap Analysis（菜系×场景 覆盖核对）

**方法**：遍历 99 个源的 covered_grid，反推每格源数；要求 ≥3 独立源且 ≥1 dine_in_evidence=true。

## 源类别分布（99 个唯一源）
| 类别 | 数 |
|---|---|
| OPEN_API | 14 |
| UGC | 13 |
| DATA_MARKET | 12 |
| OVERSEAS | 11 |
| REGISTRY | 9 |
| MEDIA_TV | 8 |
| GUIDE | 7 |
| MEDIA | 7 |
| OFFICIAL | 7 |
| LONGFORM | 4 |
| SHORTVIDEO | 4 |
| MAP | 3 |

## 格覆盖初判

**达标（≥3 源 + 堂食证据）**：
- 综合×正餐（UGC 多 + GUIDE + MAP）
- 综合×休闲（UGC + 短视频 + 媒体）

**不达标/缺口**：
| 格 | 缺口类型 | 说明 |
|---|---|---|
| 赣菜×fine-dining | 已存在未接入 | 望庐 hold；XHS 未跑 |
| 日料×omakase/割烹 | 已存在未接入 | 多家漏店；XHS 未跑 |
| 中东×正餐 | 已存在未接入 | yaya's；XHS 未跑 |
| 海鲜×fine-dining | 源存在但少 | ministry of crab；海外 Instagram/TripAdvisor 源未注册 |
| 菜场/市集 | 源不存在 | 无成熟 UGC 源覆盖菜场档口 |
| 早餐×本地传统 | 已存在未接入 | 鲜得来/大壶春等老店 UGC 少 |
| 酒吧×cocktail bar | 源存在但少 | 需海外/外语社区 |

**最大缺口**：小红书 UGC 通道（13 个 UGC 源中占核心）因账号 parked 实际未跑——属「已存在但未接入」，Apify token 到位即可立即补。
