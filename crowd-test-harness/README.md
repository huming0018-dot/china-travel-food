# 众包测试历史材料

本轮只清理已声明退役的 v3 浏览器测试实现，不恢复众包开发。

## 已退出工作树
`harness.js`、`run-all.js`、`run-extra.js`、`run-extra2.js`、`run-fixes.js`、`run-v347.js`。它们测试旧 MV3 内部状态、v3 信封与旧版本修复标志，不是独立通用测试工具；保留完整源码只会让旧入口继续被误用。

恢复点：[1dddf6e5dbca45b77a9e4e894010a463426b863d](https://github.com/huming0018-dot/china-travel-food/tree/1dddf6e5dbca45b77a9e4e894010a463426b863d/crowd-test-harness)。普通 Git 删除，不改写历史。

## 保留的经验和边界
- 浏览器测试使用独立临时 profile；不能访问用户日常 profile。
- 网络拦截必须在页面/worker 导航和请求之前建立，并检查真实外流。旧 harness 注释承诺 DNS 兜底永不外流，而旧 README 已记录 host-resolver-rules 不生效，不能继承该安全保证。
- 队列测试覆盖逐条失败、固定重试身份、丢响应后恢复、满队列、时钟边界、重启与同意状态。模拟网络成功不等于真实采集交付。
- 版本标志与内部状态断言属于旧项目，不能当新协议或通用接口合同。

`report.md`、`fix-report-v346.md`、`verify-report-v347.md` 等是历史记录，不是当前验收结果。

## 当前入口真实状态
保留 package.json/锁文件不改，但固定恢复点中它列出的两个入口 `../crowd_extension/tests/run.cjs`、`../crowd_extension/tests/puppeteer.cjs` 均不在 Git 树中。因此本仓此版本的 npm test / npm run test:puppeteer **不可当作可用验收入口**，不再给出安装后即可执行的承诺。本次不补造新测试、不恢复众包开发。

`platform-test/run-platform.js` 未改，仍是读取线上页面的历史跨平台脚本，不属于离线验收；本次未执行。其报告仅代表历史测试。

## 本次验证
扫描固定恢复点 532 个代码/配置文件（3个超过300KB的结果JSON及依赖锁文件不在扫描内），无读取失败；旧六文件的代码引用仅在六文件自身。当前 GitHub workflow 不引用它们。
验收只包含删除范围及剩余文件一致性，不启动浏览器、不采集、不部署，也不把删除测试称为测试通过。
