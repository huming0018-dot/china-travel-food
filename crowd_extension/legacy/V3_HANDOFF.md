# v3 更新保留记录

主分支 27b6030 → e68c7b2 的六项修改已作为本次合并的父历史保留，未重写历史。旧 v3 数据表、账本及新增 cloud/sql/crowd_fix_v349_install_telemetry.sql 保留。

当前 v4 清单、入口和发布脚本使用已验证的独立运行时，不重新启用旧 v3 后台及弹窗。旧安装器的最新版本、遥测和 Chrome 单形态打包修改可从提交 e68c7b234038582b2d7b3ea9fa3723602ec5ec9f 查阅：

- [Mac 安装器](https://github.com/huming0018-dot/china-travel-food/blob/e68c7b234038582b2d7b3ea9fa3723602ec5ec9f/crowd_extension/crowd-install-mac.command)
- [发布脚本](https://github.com/huming0018-dot/china-travel-food/blob/e68c7b234038582b2d7b3ea9fa3723602ec5ec9f/crowd_extension/publish.sh)
- [v3 清单](https://github.com/huming0018-dot/china-travel-food/blob/e68c7b234038582b2d7b3ea9fa3723602ec5ec9f/crowd_extension/manifest.json)

旧后台代码仍在该提交历史中。发布 v4 时不要把旧后台、匿名编号身份或全局浏览器策略写入脚本混进新包。v4 设备验收、签名与来源校验仍必须完成。
