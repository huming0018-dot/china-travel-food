# 众包 v4 数据与运行契约

当前客户端版本 4.0.0，schema_version=4，consent=crowd-public-v4。旧 v3.2 迁移和历史账本保留，但新客户端只调用 `crowd_v4_*`。

## 身份、任务和持久化

所有参与 RPC 都使用实际用户 access_token，由 `auth.uid()` 确定归属；anon/publishable key 仅标识项目。参与者注册为 pending，运营批准后可领取，未登录/未同意/未批准不能开始。运营 RPC 只授权 service_role，私有 schema 不暴露给 anon/authenticated，SECURITY DEFINER 固定空 search_path 并撤销 PUBLIC EXECUTE。

任务：`open → leased → complete/exhausted`。SQL 原子领取与租约续期；租约 20 分钟，临到期续租。target 1–20；默认每日 20 篇，运营最多设 100；日界使用 Asia/Shanghai。任务完成进度是**接收的去重笔记数**，不是核验通过数。搜索结果耗尽记 exhausted，不伪造 complete。系统没有任务时 5 分钟后再试。

浏览器/原生容器存储当前 task/lease、阶段、已浏览 note_id、候选导航 URL、next_at、待回传证据。每次回传单篇、每篇固定 request UUID。服务器缓存 payload 和准确结果；丢响应后即使任务已关闭、租约已过期，也返回同一回执。request 重用于其他 payload 必须拒绝。租约丢失/永久拒收的证据留在本机可导出；累计 20 个拒收会暂停等待处理，不能静默删除。账户使用独立本地状态命名空间。

停止持久化并取消在途运行，不恢复新搜索。回传重试独立于采集冷却，断网退避 1/2/4/8/15 分钟；认证失败暂停。本机按上海日界限制每天最多 60 次新笔记浏览，最近 2000 个已接收/重复 ID 跨任务避重；暂停后重新打开未采完的笔记并重新计算停留，不跳过阅读阶段。每个工作批次每 8 篇休息 5–10 分钟；操作间隔 30–45 秒，笔记首次加载之后停留 45–90 秒并至少滚动两次。后台停留只代表调度间隔，不代表真人已阅读。验证码、限流、登录失效优先于提取；不自动破解、不使用代理轮换/指纹伪装或隐藏接口。

## 记录

```json
{
  "schema_version": 4,
  "standard": {
    "platform": "xiaohongshu",
    "note_id": "abcdef0123456789abcdef01",
    "url": "https://www.xiaohongshu.com/explore/abcdef0123456789abcdef01",
    "title": "公开笔记标题",
    "captured_at": "2026-10-05T12:00:00.000Z",
    "published_at": null,
    "author_display": null,
    "like_count": null,
    "collect_count": null,
    "comment_count": null
  },
  "extra": {
    "hashtags": [],
    "published_label": null,
    "author_opinion_quotes": [],
    "自定义字段": "允许保留未知扩展字段"
  },
  "evidence": {
    "text": "页面可见的公开正文，保留逐字证据",
    "original_length": 18,
    "truncated": false,
    "selector": "#detail-desc",
    "parser_version": "4.0.0",
    "source": "rendered_public_dom"
  }
}
```

标准字段缺失明确为 null；extras 独立 JSONB 空间，永不覆盖标准字段。数量单位万/千被转换为数值，无法识别不猜。发布日期只取页面明确年月日，不推测相对日期。保留原文到 24,000 字符，超限明确 truncated 和原长度，发送体有限；不沿用 200 字截断。正文作者意见只能逐字引用，不包含参与者自己的口味评分、手机号、设备标识或小红书凭据字段。公开正文可能包含作者自行公开的信息，运营应按研究必要性处理，不扩展抓取私信、个人联系方式、关注关系或账号资料。

导航 URL 可暂留原页面提供的 xsec_token 在本机候选队列；提交标准 URL 永远规范化到精确 HTTPS 域名和 24 位十六进制 note_id，不上传 URL 查询参数、cookie 或 header。服务器检查标题/正文确实包含任务 anchor_terms，不能靠参与者自报 matched_store 混入店铺。

## 核验、建店和奖励

`received → verified/rejected`；接收不自动核验，返回 gate=received。核验需运营独立检查公开可见、相关性、真实作者体验、逐字原话及核验时间；源码不能证明一份客户端 DOM 是未伪造的真实采集，不把客户端自报当权威。verified 为最终状态，重复审核幂等。

全局 note_id 唯一；同一篇笔记跨任务/账户最多一次进入有效数和奖励。通过审核才增加 verified_count，100 篇生成固定 valid_notes=100 / amount_fen=10 流水，余额累计；金额用整数分。支付由运营登记实际付款 reference，已付流水不可改写。

导出 verified 记录保留原文/引用/检查时间/服务端任务店铺上下文，进入 `build_bridge` 的原 stage1–4 确定性证据门。不会把作者片段或参与者评分直接折算成餐厅 score_diner。没有足够 UGC/地址/来源则仍落 need_ugc/need_poi。

证据及账本保存在中台研究库；本机成功收到服务端回执后移除待发正文，只保留阶段/计数。停止不销毁未提交证据。生产保留/删除期限尚需运营落实，当前不自动清除审计记录。
