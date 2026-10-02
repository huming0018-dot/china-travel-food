# 众包任务包扩容机制 · CROWD_SCALE

> 维护：PM 窗口 · 2026-10-02
> 一句话：**数据源 → 过滤 → 去重 → 排序 → 切包 → 发布**，一条命令扩容。

## 一、扩容命令

```bash
cd /Users/deuce/Doubao/chats/2026-09-29/new-chat/china-travel-food
export HTTPS_PROXY=http://127.0.0.1:7897 && export FOOD_APP_DIR="$(pwd)/app"

# ① 从官方榜单种子扩容（权威冷启动）
python3 cloud/crowd_scale.py --source seed --seed-file cloud/dianping_seed.json --pack-size 6 --kpi 5 --quota 20

# ② 从库内店铺池扩容（按档次/商圈/最低分）
python3 cloud/crowd_scale.py --source db --tier 奢华 --pack-size 6 --kpi 5 --quota 20
python3 cloud/crowd_scale.py --source db --district 上海市徐汇区 --min-score 4.0
# tier 支持别名：奢华/luxury/高端、中档/mid/大众、平价/budget

# ③ 从补采池扩容（口味分空等字段缺失的店铺优先补）
python3 cloud/crowd_scale.py --source fill --field taste_score_empty --pack-size 6 --kpi 5 --quota 20
```

## 二、机制（扩容是怎么工作的）

```
┌──────────┐  ┌────────────┐  ┌──────────┐
│ 数据源    │  │ 过滤条件    │  │ 去重      │
│ seed/db/ │→ │ tier/district│→ │ 库内已收录  │
│ fill     │  │ min_score   │  │ +已发布包  │
└──────────┘  └────────────┘  └──────────┘
     │                              │
     ▼                              ▼
┌──────────┐  ┌──────────┐  ┌──────────┐
│ 排序      │  │ 切包6店/包 │  │ 发布      │
│ 评分降序   │→ │ kpi/quota │→ │ crowd_tasks│
└──────────┘  └──────────┘  └──────────┘
```

**关键规则**：
1. **去重是核心**：`load_covered()` 同时读 `restaurants.name`（库内已收录）+ `crowd_tasks.pack`（已发布包）——**绝不重复采集同一家店**。
2. **数据源优先级**（价值排序）：
   - seed（官方必吃榜）> db（库内高分未覆盖）> fill（字段缺失补采）
3. **档次映射**：`奢华/luxury/高端 → 奢华`、`中档/mid/大众 → 中档`、`平价/budget → 平价`
4. **切包**：默认 6 店/包、kpi=5（每家店最低收录 5 条笔记）、quota=20（参与者日配额）
5. **安全**：只发布不删除；包内容由 crowd_pack.publish 落 crowd_tasks 表，插件拉取→采集→回传→进度回写闭环

## 三、当前扩容规模（2026-10-02 基线）

| 批次 | 来源 | 新增店铺 | 新增任务包 |
|---|---|---|---|
| 第1批 | dianping必吃榜种子（160家未收录） | 160 | 29 |
| 第2批 | 库内奢华档（170候选→94未覆盖） | 94 | 16 |
| **合计** | | **254** | **45** |

- 全部 45 个任务包 open 状态，覆盖 254 家未收录店铺
- 库内其余未覆盖池（中档/平价/其他商圈）留作后续批次，按需 `--tier`/`--district` 继续扩

## 四、后续扩容节奏建议

- **触发点**：任务包 fulfillment 率达到 60% 时自动补一批（或 PM 夜间盘点时评估）
- **扩充方向**（按产品价值）：
  1. 中档/平价高分店（评分≥4.5 的社区口碑店）
  2. 各商圈头部店（徐汇/静安/黄浦重点区）
  3. 补采池：口味分空（1152家）、营业时间空（547家）
  4. 新店池：集团动向/新店动向（需 collector 侧新增信源后 feed 进来）
- **扩容治理**：每批发布后跑 `cloud/security_regression.py` 确认安全基线未破；STATUS.md 登记批次

## 五、与其他模块衔接

- `crowd_scale.py` → `crowd_pack.py.publish()`（切包发布）
- 插件 `crowd_fetch_tasks` 拉取 open 包（无需改插件，新包自动可见）
- 回传 `crowd_submit_proof` 校验后回写 progress；kpi 达成自动 fulfilled
