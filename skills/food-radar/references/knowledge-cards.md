# 食客百科卡规范（knowledge cards）

每次为用户预约/记录一家餐厅后，把查到的**餐厅、主厨、人际关系**沉淀成卡片，避免下次重复检索、并支撑「谁和谁同门、哪家店是谁的师承」这类追查。

卡片存放：`knowledge/` 目录，一个实体一个 `.md` 文件。

## 三种卡

| 类型 | 文件名 | 回答什么 |
|---|---|---|
| `restaurant` | `r-<slug>.md` | 这家店在哪、谁做、什么菜、怎么订 |
| `chef` | `c-<slug>.md` | 这个人是谁、师承、履历、现在在哪 |
| `venue-network` | `n-<slug>.md` | 一条关系链（同门、师承、集团、四手联弹） |

## 必填字段（restaurant）

```yaml
id: r-wip-weipu
name: WIP 未樸
city: 上海
district: 徐汇
address: 建国西路485-1号
opened: 2026-09-26        # 试营业也写，标 trial
hours: 周二至周日 18:30-21:30
price: 1288 + 10%
cuisine: 岭南风味／粤菜解构
booking: 微信（待补具体号）
chef_ids: [c-shui]        # 关联 chef 卡
network_ids: [n-cia-shanghai]
confidence: partial       # confirmed / partial / unverified
sources: [...]
```

`confidence` 必填，含义：
- `confirmed`：至少两个独立来源一致
- `partial`：单一来源，或关键字段（地址/主厨）有一项未证
- `unverified`：仅 UGC 提及，未交叉验证

## 主厨卡必须区分的事实

追查师承时，**不要把三种关系混为一谈**：

1. **校友**（同校，如 CIA）—— 不等于同门
2. **师承**（明确拜师，如张一峰 → 吴稚阳）—— 才叫同门
3. **同事/同店**（同在一家餐厅工作）—— 不等于师承

中文语境里「师出同门」常被口语化使用，写卡时必须标明属于哪一类，并从原文取证。

## 已知的强关系节点

- **CIA（Culinary Institute of America）**：上海一批高端餐厅主厨的共同起点，属「校友」而非「师承」。
- **泰安门 Taian Table（上海，米三）**：Stefan Stiller 创办，是上海高端餐饮的重要「出身地」。
- **潮上潮（北京，米二）**：行政总厨张一峰；其 Chef's Table 子项目「潮1/2」由张一峰与徒弟吴稚阳共同主理。
- **Odette（新加坡，米三）**：Julien Royer；ONCUE 主厨 Johnston Teo 曾任其研发主厨。

## 写入时机

- 用户新预约一家店 → 建 restaurant 卡
- 查到主厨履历 → 建/更新 chef 卡
- 发现跨店关系（同门、师承、集团、联弹）→ 建/更新 network 卡

## 证据纪律

- 每个关键字段都要能追到 source。
- 冲突时并列不取平均，写明「A 说 X，B 说 Y」。
- 姓名/时间这类硬事实，单一小红书 UGC 不足以定论，标 `partial`。
