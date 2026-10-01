# 角色工作内容调整方案 · ROLE_WORK_SPEC

> 发布：2026-10-01 | QA窗口统筹 | 用户对三窗口工作内容不满的针对性调整
> 配套：AUDIT_OPTIMIZATION.md（全项目审计）+ role-task-allocation.md（角色分配）

---

## 一、现状症结（代码实查）

### 症结1：xhs账号"四处认定"——11个模块各自读状态

| 模块 | 读取方式 | 问题 |
|------|---------|------|
| gap_pool | 自写classify()调account_repair.probe | 每300s全账号probe一次，重复探测 |
| cloud_router | pool.summary() + 自写pool_alive() | 混合两套判定 |
| health | _pool()（复用xhs_cookie_pool） | ✅ 复用 |
| account_repair | 自写probe + mark_* | 探测逻辑所有者，但API入口不统一 |
| warning_handler | 动态import xhs_cookie_pool | ✅ 复用但方式不一 |
| progress_broadcast/public_status/qa_broadcast/cloud_ready/coverage_matrix/xhs_api | 各自读状态文件 | 无统一API |

**结论**：账号状态存储/探测有雏形（account_repair.probe + xhs_cookie_pool），但**没有统一入口API**，11个模块各自import、各自调用、各自判定 → "四处认定"。

### 症结2：公共组件调用无规范——health被13个模块调用，各自为政

- health.py 提供通道/告警，13个模块import，但**没有统一调用规范文档**
- 告警级别/冷却/格式靠各模块自觉遵守（notifier已收敛部分）
- dev没有产出"公共组件调用规范"代码实现（如统一 require 封装、统一配置读取）

### 症结3：采集数据无二次验证模组

- 数据入库门槛有 admission_gate（概念存在）
- 但**没有统一的"采集数据二次验证"模组**——各采集器自己校验自己，无cross-check（如高德电话 vs 点评电话互验、坐标合理性校验）

### 症结4：采集通道无SOP

- 通道分散：router调度（浏览器类）+ cron（HTTP类）+ Apify（计划中）
- 无文档说明：每个通道采什么、数据规范、需要的公共组件、遇到问题怎么处理

---

## 二、调整方案

### 方案A：PM工作内容明确化——产出"运作体系总图"

**PM必须交付（本迭代内）**：

1. **体系逻辑文档** `SYSTEM_ARCH.md`：
   - 角色→模块→数据流 全图（Mermaid）
   - 各窗口边界、公共组件清单、数据流向
2. **三大公共组件设计确认**：
   - account_registry（账号统一管理）
   - common_core（公共调用规范）
   - data_gate（数据二次验证）
3. **流程图**：任务流转 / 问题升级 / 数据入库 三条主流程
4. **模块设计评审**：dev交付的组件设计先过PM评审再实现

**验收标准**：任何新窗口/新角色读 SYSTEM_ARCH.md 5分钟内能说清"谁负责什么、数据怎么流、遇到问题找谁"。

---

### 方案B：dev工作内容明确化——统一公共组件实现

**dev必须实现（三个公共组件，收敛重复）**：

#### B1. account_registry（账号统一管理模组）——解决"四处认定"
```python
# cloud/account_registry.py（新建，dev实现）
class AccountRegistry:
    # 唯一状态入口：list / probe / status / mark / pick / cooling
    def list(self) -> list[Account]      # 全部账号+状态
    def probe(self, aid) -> int          # 权威探测（复用account_repair.probe）
    def status(self, aid) -> str         # active/dead/restricted/parked
    def mark(self, aid, status, reason)  # 唯一写入口
    def pick(self) -> str                # 按健康度选号（替代散落的pick_account）
    def summary(self) -> dict            # 全局摘要
```
- **其他11个模块改造为只import account_registry**，删各自状态判定
- 状态文件单一：/app/data/_cookie_pool_state.json（account_registry独占写权限）

#### B2. common_core（公共调用规范）——解决"各自为政"
```python
# cloud/common_core.py（新建，dev实现）
class Core:
    def req(self, method, path, ...)      # 统一DB请求（复用common，带重试/超时/日志）
    def config(self, key, default)        # 统一配置读取（deploy.env/env.sh/notify_channels）
    def notify(self, level, key, body)    # 统一通知（封装notifier，规范级别/冷却）
    def log(self, module, msg)            # 统一日志（带模块前缀，进对应log）
```
- **所有新代码必须走common_core**；存量代码逐步迁移（迁移清单由dev列出）
- 告警/请求/日志三件套收敛，杜绝各模块自造

#### B3. data_gate（采集数据二次验证模组）——解决"各自工作"
```python
# cloud/data_gate.py（新建，dev实现）
class DataGate:
    def validate(self, record, schema)    # 字段校验（必填/类型/枚举/长度）
    def cross_check(self, record, channel) # 跨源互验（电话：高德vs点评；坐标：范围合理性）
    def dedupe(self, record)              # 指纹去重（标题+地址hash）
    def admit(self, record)               # 过闸入库（原admission_gate收敛于此）
    def report(self, batch)               # 校验结果报告（拒收率/原因分布）
```
- **所有采集器入库前必须过 data_gate**，违反的PR不合并

---

### 方案C：collector工作内容明确化——采集通道SOP

**collector必须交付 `COLLECTION_SOP.md`（采集作业指导书）**：

#### C1. 采集通道清单（每个通道一段）

| 通道 | 采什么 | 调度 | 公共组件依赖 | 问题处理 |
|------|--------|------|-------------|---------|
| XHS-Apify（计划中） | 小红书笔记/评论 | apify_collect.py（P0） | account_registry / data_gate | Token失效→ACTION给用户 |
| XHS-浏览器（router） | gap_runner深覆盖 / run_batch取证 / discover | cloud_router 20min tick | account_registry | 账号-100→account_registry标记→不硬刷 |
| 米其林 | 榜单153家 | router兜底 | 无 | 24h内不重复采（已实现） |
| B站 | 美食探店 | cron 6h | data_gate | 配额→退避 |
| 高德 | 电话/营业时间/评分/坐标 | cron :15/:35/:55 | map_quota / data_gate | key配额超限→轮换key |
| 腾讯 | 电话/坐标 | cloud_phone_fill/coord_fill | map_quota | 日配额→凌晨重置 |
| 黑珍珠 | 上海官方榜单对账 | cron 6:20 | data_gate | 缺店→留队列取证据 |
| KOL跨平台 | 美食作家文章 | cron 6h | data_gate | 无key→降级 |

#### C2. 采集数据规范（统一字段标准）
- 餐厅必填：name/address/lng/lat/cuisine/status
- 评论必填：restaurant_id/source_platform/review_kind/trust_level/content
- 取值枚举：review_kind(diner|platform_aggregate|kol|media)、trust_level(high|mid|low)
- **违反规范的数据进不了data_gate**

#### C3. 问题处理SOP（统一升级路径）
```
采集异常 → 写模块日志（含错误码）
  → data_gate拒收 → 记录原因，不硬造数据
  → 账号问题 → account_registry标记 → router自动绕开
  → 配额问题 → map_quota自动轮换 → 全尽→WARN播报
  → 必须用户 → ACTION播报（每日1次最多3次）
  → 连续3轮0产出 → 自动停该通道 + QA介入查根因
```

---

## 三、责任矩阵（调整后）

| 交付物 | 内容 | 责任人 | 验收 |
|--------|------|--------|------|
| SYSTEM_ARCH.md | 体系逻辑/模块设计/流程图 | **pm** | qa复核可读性 |
| account_registry.py | 账号统一管理 | **dev** | 11个模块迁移完→qa验证无重复 |
| common_core.py | 公共调用规范 | **dev** | 新代码100%走core |
| data_gate.py | 数据二次验证 | **dev** | 所有采集器接入 |
| COLLECTION_SOP.md | 采集通道SOP | **collector** | pm评审通道全覆盖 |
| MODULES.md | 模块四层分类+合并清单 | qa（已列计划） | dev执行合并 |

---

## 四、落地顺序（依赖关系）

```
第一步（并行）：
  pm → SYSTEM_ARCH.md 体系总图
  collector → COLLECTION_SOP.md 通道SOP
  dev → account_registry.py + common_core.py + data_gate.py 三组件骨架
第二步：
  dev → 11个模块迁移到account_registry（含删重复判定）
  collector → 采集器接入data_gate
第三步：
  qa → 全量验证（无重复探测/无自造数据/无绕路）→ 关闭对应issue
```

**硬约束**：三大公共组件是"唯一入口"，任何绕过直接走自己判定的代码，QA打回。
