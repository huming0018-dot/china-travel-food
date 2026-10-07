# 数据回收位置与核验边界

2026-10-07 已部署参与接入服务 `crowd-access` 到现有 Supabase 项目 `bdwrhshgdeghgyzwpxnl`。网站不需要 Supabase 管理员密钥，发布者通过独立私有管理口令查看数据。该口令不交给参与者。

| 数据 | 持久位置 | 内容与用途 |
| --- | --- | --- |
| 原始回传 | `crowd_v4.proofs.record`，PostgreSQL JSONB | `standard` 标准字段、`extra` 非标字段、`evidence` 原文及解析来源完整保留 |
| 标准字段 | `record.standard` | 平台、笔记 ID、原帖 URL、标题、发布时间、采集时间、公开作者昵称、公开阅读/浏览量（view_count）、赞/收藏/评论数；未知值保留 null |
| 评论与回复 | `record.extra.comments` | 本次已加载的评论/回复文本、父子关系、公开昵称、点赞数、时间标签、范围与截断标记 |
| 指标原显示值 | `record.extra.metric_labels` | 如“1.3万次浏览”；保留页面显示精度，不能把近似数当精确后台统计 |
| 非标字段 | `record.extra` | 标签、逐字意见等解析内容及扩展字段；不转成虚构评分 |
| 原文证据 | `record.evidence` | 可见正文、原文长度、截断标记、解析版本、`rendered_public_dom` 来源 |
| 去重和收件回执 | `crowd_v4.proofs.note_id` / `crowd_v4.receipts` | 笔记全局去重；断网重传沿用相同请求 UUID，返回相同回执 |
| 任务与租约 | `crowd_v4.tasks` | 店铺关联、关键词、领取状态、租约、目标条数 |
| 核验状态 | `crowd_v4.proofs` 的 status / verified_quote / source_checked_at | 新记录为 received；核验原帖、逐字引文及质量门后才为 verified；不符合的为 rejected |
| 研究补贴账本 | `crowd_v4.rewards` | 每 100 条核验有效且去重的笔记记 10 分，独立于实际付款 |

```mermaid
flowchart LR
  A[客户端离线队列] -->|参与者登录 RPC、租约校验| B[Supabase crowd_v4.proofs\n标准 / 非标 / 原文]
  B --> C[待核验 received]
  C -->|核对原帖及逐字证据| D[verified]
  D --> E[crowd_v4_verified.jsonl]
  E --> F[build_bridge / stage1–4 质量门]
  F -->|通过全部门槛| G[正式餐厅资料库]
```

主副本是数据库，不在 Vercel 临时文件系统。公开 key 不能直接读取这些私有表；数据查看和导出需要发布身份。管理页 `/crowd/admin` 的“数据回收”可查看前 100 条待核验记录、分页下载已核验证据。无发布身份返回 403。原始记录始终保留在数据库，即使尚未核验或未进入餐厅资料库。

部署流水线的第二份证据文件路径是 `/app/data/coverage/crowd_v4_verified.jsonl`，由 `cloud/crowd_v4.py cycle --apply` 幂等导出，`build_bridge.py` 读取同名文件。这个流水线定时开关仍为 `CROWD_V4_ENABLED=0`：当前没有接通运行它的生产 Docker 环境，不能声称已自动入库。文件导出不代替数据库；网页下载是第三份副本，落在发布者浏览器的下载目录。

本工作区已实际运行导出，文件在私有 `.crowd-launch/recovery/crowd_v4_verified.jsonl`；实际为 0 条，未塞入模拟笔记。数据库已发布三条真实店铺试点任务，每家目标两条；参与者和回传记录仍为 0。设备验收、原帖核验和生产流水线启用后才可宣称完整采集入库闭环运行。

回收接口由 `crowd-access` 的 `operations` 支持限定的 publish/review/list/export；不接受任意 RPC、付款或账号管理。参与接入通过有效邀请与预留安装身份验证。安装清单只从经现有产物/源码/设备验收的私有发布清单读取，不把构建通过当作实机通过。


## v4.0.4 评论字段与限制

`extra.comments.items` 是扁平数组；每条有快照内唯一 `key`、可读到时的 `comment_id`、`parent_key`、`is_reply`、`author_display`、`text`、`original_length`、`truncated`、`like_count`、`like_label`、`published_label`。`parent_key` 只指向同一快照中已保存的父评论，未知时为null；不根据文字猜测父子关系。父评论文本独立提取，不拼入嵌套回复。昵称/时间标签是页面公开信息，不访问用户主页、私信或账号设置。

每篇详情先按既有停留/滚动规则读取正文，再最多4轮（每轮间隔至少30秒）展开明确的“展开回复/查看更多评论”控件或继续滚动；绝不点击点赞、发评论/回复输入按钮。连续滚动从当前位置前进。验证码、登录失效或限流依旧暂停。最多保存50条评论/回复，每条2000字符；评论JSON还受20000字符上限及正文/意见引用占用后的剩余包预算限制，可能提前截断。

`coverage='visible_loaded_only'`、`complete=false` 保守地说明仅保存本次页面已加载并可读取的部分；`loaded_count`、`captured_count`、`omitted_count`、`truncated`、`panel_found`、`more_available` 用于解释数量与缺失。总评论数可能含未加载/折叠/删除内容，与items长度不同属正常，不能填造评论凑数。DOM虚拟化可能让先前离开页面的评论不在最终快照中；本版本不承诺全量抓取。读取不到的阅读量、点赞、作者、发布时间为null，明确显示0时才写0。

迁移 `20261007120848_crowd_v4_view_count` 只把可选view_count加入原submit数量校验，旧客户端不带该字段仍可回传。评论作为已有extra JSONB保存，导出保留完整record。原任务、租约、幂等回执、RLS和核验/奖励规则不变，评论条数不另计奖励。生产权限回验：anon不可调用submit、authenticated可调用但不能直读proofs、RLS开启。安全advisor对原有 [authenticated SECURITY DEFINER](https://supabase.com/docs/guides/database/database-linter?lint=0029_authenticated_security_definer_function_executable) 本人RPC仍有提示；本人、租约及固定search_path边界保留。

本地验证通过：真实Chromium固定页面中提取阅读量、独立父评论与嵌套/延迟展开回复，保存到隔离PostgreSQL实际submit函数；丢回执重试仍只有一条完整记录，非法阅读量被拒。数量/长度截断、总包预算、未知值与明确0、隐藏评论、非互动展开、滚动推进、正文缺失时拒绝用评论替代等边界通过。此前完整业务数据库独立套件因未配置而SKIP，未将其算作通过。Mac真实安装和小红书DOM适配尚未验证。
