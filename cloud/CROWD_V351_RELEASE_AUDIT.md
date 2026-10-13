# 众包采集器 v3.5.1 发布链路核验
核验：2026-10-13（生产读数最后窗口 15:54 UTC；北京时间 23:54）。仓库修复提交发生在 2026-10-14 北京时间；按实际 GitHub UTC 时间记录，不能将后续写入视为10月13日原发布。

## 四种状态
|层级|证据与结论|
|---|---|
|仓库文件|crowd-pages 原 main 7054c50 中 updates.xml/CRX 均3.5.1，但 latest ZIP 内3.4.14；已通过 PR #3 合入 main，merge 039484307493cd7cc9ca22caa2b3feb624b262d5，ZIP与已验签CRX payload逐文件一致|
|公开地址|本会话 curl 超时、检索工具无法访问。无法据此断言公网故障；没有200/MIME/公网下载哈希证据|
|设备升级|crowd_install_log 多次 upd_found=3.4.14->3.5.1，upd_applied及upd_chrome_restarted仍3.4.14。涉及 Mac mini / MacBook Air 的不同 run_id。不是3.5.1成功回执，且脚本回执不是浏览器实际加载版本|
|持续评分|10月13日北京时间00:00起截至生产核验时，仅1条accepted rating，4.5，task15，创建05:43:44Z；sync_version=2。它是原验收样本，不能证明最新客户端或持续采集|

## 包与安全代码
- CRX3 RSA-SHA256验签通过；公钥、SignedData ID、manifest key均一致；扩展ID licijehcpohikchlnkbpjdjdfkcocndg。
- CRX SHA256：91efcab820e87b8603849a5035afd91fb01a13d7a10ffb4cc44ee8eab45fe5fa。
- 包内 version=3.5.1，Chrome后台 src/background_v3414.js；无 background.scripts（打包兼容转换）。
- 全部31个非manifest文件的Git blob与china-travel-food/main crowd_extension相同；manifest仅删除Firefox background.scripts及格式化。
- 保留同意门、全局暂停、remote limits、安全引擎、幂等队列、认证熔断。评分表单和rating-only信封存在，sync_version=3。
- canonical crawler-extension/main manifest仍1.0.0且runtime与已发包不同；不能从那个仓库直接重打包3.5.1覆盖现有安全引擎。当前发布源码实际对应china-travel-food/crowd_extension。canonical源码全量收敛仍待后续明确的差异审查。
- 现存Mac helper下载latest ZIP且原来不核对包内版本。修复latest ZIP解决本次已知缺口；版本校验补丁仅进入源码，未重签CRX、未声称已安装到存量helper。

## 生产RPC与行为
已直接读取 pg_get_functiondef(public.crowd_submit_proof(text,jsonb))，函数体与cloud/sql/crowd_fix_v351_rating_gate.sql一致（SQL文件头说明除外）。
- rating-only不要求URL/标题正文；仍要求合法分值、理由、任务pack关键词和已入库笔记锚点。
- fulfilled仅rating-only且本人认领/已有accepted笔记放行。
- 日配额只数note；评分不累计accepted/keyword_progress/任务progress。
- 原真实回执：ok=true, rated=1, accepted=0, gate=accepted, progress=61。
- 本次生产BEGIN/ROLLBACK：原submission重放与存储response相等；新submission同评分返回duplicate/rated=0/accepted=0/progress=61；临时quota_day=1后rating仍返回duplicate而非quota。全部回滚，不新增评分、不改变参与者状态或任务进度。
- 当前accepted rating重复dedupe分组=0；这不是并发压力测试。
- 未执行全量设备枚举、真实新评分制造、RPC重部署。

## 尚未闭合的客户端语义
- submitRating先置本地rated=true再收到服务端确认；拒收或死信后缺少可重评恢复，入队成功不等于评分入库。
- 表单仅从active_task展示；任务结束清active_task后没有历史任务补评分入口。RPC支持补评分不等于UI支持。
- syncKeywordProgress兜底统计全部accepted results而未按kind排除rating；当前active_task的权威keyword_progress避免了常规污染，但非active任务/缺权威回执的本地兜底仍需独立修复验证。
这些属于已发客户端局限，不应在同名3.5.1签名包中静默改代码。

## 收尾验收
1. 从合法设备访问公开updates.xml及latest ZIP/CRX，记录200、类型、version、hash；存量Mac下次自然更新后读取实际Chrome扩展版本及后台日志，不仅看upd_applied。
2. 在已有真实评分发生后有界回读（最多10条）：排除原验收sid，确认rated回执/proof一致、任务和关键词进度未增加、笔记配额不消耗。
3. canonical客户端先审查安全代码差异再收敛；上述本地rated/历史任务/兜底计数修复使用新版本，不复写既有签名3.5.1。
DevSpace本次返回Internal error，没有触发设备升级、重启浏览器或新采集任务。
