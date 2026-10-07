# Kimi v1.0.0 对照与 Mac v4.0.3 修复 · 2026-10-07

## 参考资料

用户指定仓库 [crawler-extension v1.0.0](https://github.com/huming0018-dot/crawler-extension/tree/v1.0.0)，annotated tag 指向提交 `5b9e327a5812974fdd08cbeb109141a57e41fda1`。已读取完整 content.js、background.js 的采集/入队路径、manifest、README、MIT LICENSE。[Release](https://github.com/huming0018-dot/crawler-extension/releases/tag/v1.0.0) 的资产页本次只列 Source code ZIP/TAR；没有可比对的独立安装包。只读克隆位于 `/workspace/crawler-extension-reference`。

## 发现与采用

- 参考版按 `section.note-item, div.note-item` 逐卡片读取标题、作者和链接，列表 `excerpt=null`，列表采集不会主动进入每篇详情页。上传预检允许标题至少两字，因此它的卡片回传不等同于 v4 正文证据回传。用户实测能采到应视为有价值的对照，不能因此否定其结果。
- 参考版核对页面 keyword 与任务 keyword，采用 NFC、空白归一化与忽略大小写。v4.0.3 使用相同规则校验，错页暂停，结果链接优先限定在各卡片内；仍保留 explore/discovery/item/search_result 三类严格同域详情链接。本机导航参数保留，回传 URL 去除 token。
- 参考版也只在 note-ID 正则接受 explore/discovery/item，搜索页面完成后等待两秒再提取；该 tag 的源码本身无法证明能解决当前 search_result 详情路径或真实网络加载问题，不能盲目整体替换。
- 参考版区分 `page_load_timeout` 和 `content_unavailable` 并为 content 消息设超时。v4.0.3 的探针等待上限两秒，避免消息不返回时整个采集锁无法释放；分别报告 page_loading、content_unavailable、probe_timeout。连续三次页面失败暂停，本人继续才重置预算。页面已渲染而图片持续加载时仍能读取正文。
- 两个仓库使用相同 extension public key。Mac 更新器仅更新 v4 安装；不能把 Kimi 的 v1 安装或旧 v3 当作 v4 覆盖，也不迁移它们的参与身份。

## 导航诊断

增加 `webNavigation` 权限，仅在诊断开启、当前参与身份、当前采集标签页、顶层 frame、精确 HTTPS 小红书域名满足时，保存最后一次导航阶段与固定错误码。未保存完整 URL、关键词、Cookie、请求内容、正文、其他标签页或事件历史。关闭/退出清除本机快照；云端沿用原有版本化 opt-in/opt-out 和最新一条状态规则。

字段：`nav_stage`（started/committed/dom_ready/complete/failed/unknown）、`nav_error`（固定 Chromium 网络错误码，未知值为 OTHER）、`nav_age_s`（距最后事件秒数，上限86400）、`probe_status`（ok/no_receiver/timed_out/unknown）。DNS、连接重置、代理/证书失败等只有浏览器实际报告相应错误码时才能判定。webNavigation 不提供 HTTP 响应状态，所以不能据此声称识别所有 403/429；页面内验证/限流仍由现有可见页面检测暂停。

生产迁移 `20261007100305_crowd_v4_navigation_diagnostics` 已应用。只扩展原诊断 RPC 的可选字段/枚举；兼容4.0.1，不改变任务、邀请、奖励和参与身份。回验 RLS=true，anon 不可执行，authenticated 可调用但不能直接读诊断表，函数固定空 search_path、auth.uid() 本人边界保留。安全 advisor 仍提示预期的 [authenticated SECURITY DEFINER](https://supabase.com/docs/guides/database/database-linter?lint=0029_authenticated_security_definer_function_executable) 窄接口；未宣称存量整个项目无告警。

## 验证与交付

`node crowd_extension/tests/run.cjs` 通过（完整业务 PostgreSQL 独立套件未配置，明确 SKIP）。另运行真实 Chromium 固定页面 → 隔离 PGlite 实际 claim/submit/finish：正文、标准/非标字段落库，首个回执丢失后原 UUID 重放只存一条；卡片外推荐不进入候选、加载中资源不阻断可读 DOM、验证码暂停通过。`diagnostics-db.mjs` 在隔离 PostgreSQL 验证新字段、旧版兼容、任意错误文本/URL/非法值拒绝、本人隔离和退出清除。Chrome API 适配测试验证网络错误白名单、非采集标签/子 frame 忽略、关闭诊断不记录、陈旧事件不覆盖新事件及有界消息超时。

以上并非 Mac 本机安装或真实小红书验收。18:03 北京时间生产快照仍为4.0.1，loading/unknown、page_timeout，v4 proof_count=0。没有把测试证据写入生产或修改真实诊断快照。

私有候选 `/workspace/Mac轻量内测-v4.0.3.zip`：38,766 bytes，SHA256 `a889c49b021fc933fbb4be27fb7e9bf443f9c7f1696a93aa998845dee3ad0de4`。全部包内文件摘要与当前源文件验证；新增 webNavigation 权限在安装说明和诊断说明中披露。保留原扩展 ID、邀请及配额，原 v4 目录更新后刷新，不卸载、不重新报名。包含试点邀请，只交付当前用户，不上传公开 Release。正式分发仍未开放。
