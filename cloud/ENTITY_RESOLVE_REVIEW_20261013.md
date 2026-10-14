# 实体归并独立工程审查（2026-10-13）

基线：canonical `huming0018-dot/china-travel-food` main `81d8c685acf7a321f73f0b430f18e7bf075b4e12`。
范围：`cloud/vendor/pipeline/entity_resolve.py`、keep 基线和其调用的 `merge_duplicates.py`。所有输入为隔离合成数据，数据库/API 被 mock，未读取生产餐厅数据、未执行迁移或删除。

## 已复现问题与最小修复

| 问题 | 基线事实/隔离例 | 修复行为 |
|---|---|---|
| AUTO/REVIEW 重叠 | 同品牌 A/B 地址为月光路12号，C 为月光路20号；三者坐标相同。原版 AUTO=[A,B]，REVIEW=[A,B,C] | 按联合图仅输出一个不重叠分区；包含弱边的簇为 REVIEW |
| 强边传递误升级 | A=星月、B=星月海天、C=海天，同完整地址；AB/BC 品牌相关，AC 不相关 | AUTO 必须每一对均有强边；强链整体降 REVIEW，不将连通性视为同一实体证明 |
| keep 成员变化失效 | 原版只按完整签名过滤，历史 A/B 保留后新增 C 或历史 A/B/C 缩为 A/B 都会失配 | 历史簇内部任意两成员构成保守禁止合并约束，跨成员变化继续生效；冲突显式输出 `keep_constraints`，不静默丢掉审阅对象 |
| canonical keep 未加载 | 原版仅读 `/app/data` 和 `/app/pipeline`，不读仓库相邻文件 | 同时加载相邻 canonical keep，校验格式，坏记录直接终止 |
| 商场/共享电话假匹配 | 原版相同无铺位商场地址、同品牌共享固话/400 号可直接 AUTO；手机+商场也可 AUTO | 电话/坐标单独不作强证据；已识别商场必须同铺位；完整非商场门牌可作强证据。不同铺位或 >=120m 坐标矛盾降 REVIEW |
| 地下楼层混淆 | 原版 B1层101 与 1层101 均提取 (1,101) | 保留 B/L 前缀，不视为相同铺位 |
| 更名覆盖电话问题 | 原版不同品牌同铺位先入 REVIEW，`elif` 吞掉共享电话问题 | 可同时输出 REVIEW 与 PHONE 证据；PHONE 不是合并簇，不作为写入授权 |

候选识别仍是启发式而非事实核验：mall_of 词表、铺位正则、品牌包含/前缀关系不可能覆盖全部地址/同楼多店。缺乏证据时可能增加 REVIEW 或漏报。AUTO 也只供人工审阅，计划的 action 全为 review，不能直接作为裁决文件。整个弱图可能形成较大审阅簇；本次优先防误合并，未做弱图细分性能优化。

## `--apply` 审查结论：原执行器不具备安全执行条件

- 裁决：原版不核对 sig、keeper/drop 成员、当前候选、跨簇重复/交叉 keeper、keep 冲突；无快照版本/指纹、裁决身份/理由/过期检查。空 drop 可静默成为无操作，电话 ids/keep_id 也不校验。
- 写入回执：`M.migrate` 只是记状态码，多处 POST/PATCH/DELETE 失败后不终止。隔离注入 reviews PATCH=500，函数正常返回 `reviews 7 -> 1: 500`，上层随后仍可删除餐厅。电话 PATCH 及 cuisine DELETE 同样未检查。HTTP 204 不能证明影响了预期行，无统一回读断言。
- 失败恢复：多个 REST 调用独立提交，没有事务/锁/回滚；日志仅在整轮成功末尾写入固定文件，异常时可能无日志且覆盖历史；无 verified backup、恢复清单、运行 ID 或重放幂等协议。
- 关系：仅列出五张子表，不做数据库 FK 全量枚举或剩余引用断言；reviews 同 user、negotiations 同 channel 等去重可能丢不同内容。无法从源码确认生产 FK/cascade 真实布局。孤儿或级联丢失风险待生产只读审计。

**修复采用 fail-closed：删除本脚本旧写入分支，`--apply` 在任何数据库读取/写入前以退出码 2 拒绝。** 这不是已经补齐事务执行器，也不宣称失败恢复通过；暂停不安全能力就是本次最小防护。今后重新启用必须独立实现并验证：新鲜人工裁决绑定数据指纹、全批次无交叉校验、keep 约束、备份可恢复验证、所有 FK 及业务关系清单、服务端事务/锁、精确影响行数和回读、持久成功/失败回执、失败注入和重放测试。不得仅增加一个绕过开关。

**范围外风险：** `merge_duplicates.py --commit` 本身未改；`cloud/cloud_patrol.py` 源码另有调用它的路径。此次只阻断 entity_resolve 的不安全入口，不能宣称全项目删除入口已保护；未核实该 patrol 路径当前生产调度/运行状态。

## 验证与运行

```bash
python -m unittest discover -s tests -p test_entity_resolve_safety.py -v
python -m py_compile cloud/vendor/pipeline/entity_resolve.py
python cloud/vendor/pipeline/entity_resolve.py --apply verdicts.json  # 应退出 2，零数据库调用
# 生产只读审计取得已有连接后才能运行：
python cloud/vendor/pipeline/entity_resolve.py --plan /app/data/entity_plan_review.json
```

25 项隔离回归通过：正例含同完整街道地址、同商场同铺位、强边完全图；反例含真实品牌桥接、强/弱边桥接、keep 增减、无关 keep、共享固话/400/手机/坐标、异址、异铺位、疑似更名、地址占位符、楼层、keep 格式错误；CLI 验证 apply 零读零写和计划零写。

状态必须分别跟踪：代码发布以 GitHub main/PR 回读为准；隔离测试已通过；生产数据审计未执行；实际归并/删除未执行。生产容器未部署本修复，不应将 main 状态当作线上生效。不得回滚到旧脚本后恢复 apply；如需要回滚识别逻辑，必须保留写入禁用闸门。
