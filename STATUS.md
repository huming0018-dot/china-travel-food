# 当前状态 · STATUS

> 最后更新：2026-09-30 10:15
> 三个窗口开始工作时运行 `bash sync.sh <角色>`，结束时运行 `bash sync.sh push "说明"`

## 采集（CTFS_登录）
- 账号：A=cookie在服务器IP上被失效（probe=-100）/ B=parked
- 采集状态：**停摆**，已决定切换Apify云采集方案，不再用本地账号+IP
- 地图API：高德key#1正常（月配额515/4500），高德key#0月配额超限，腾讯key日配额超限（明天0点重置）
- 数据：1472家在营餐厅，电话空171家，营业时间空546家

## 开发（CTFS_开发）
- 已完成：前端P0修复、后端采集P0修复、提醒机制整顿、角色同步机制
- 最近commit：03f7a83（amap_search提取营业时间）
- 待做：Apify集成（apify_collect.py替换xhs_api）、高德评论review_kind清理
- 部署：腾讯云容器food-cloud运行中

## QA（CTFS_QA）
- 问题台账：18条（open 7 / verifying 2 / closed 9）
- 本次修复：map_quota SK配对bug、电话补全配额终止bug、amap_search营业时间提取bug
- 补全结果：电话+8家（179→171），营业时间+30家（576→546）
- 风险：采集停摆导致口味分无法补全（1207家空，82%）

## 任务队列
- 表：task_queue（需在Supabase SQL Editor执行 db/migrations/017_task_queue.sql 建表）
- 查看：`python3 cloud/task_helper.py stats`
- 认领：`python3 cloud/task_helper.py claim <id>`
- 完成：`python3 cloud/task_helper.py done <id>`

## 下一步
1. 【dev】Apify集成：开发apify_collect.py，恢复采集
2. 【collector】提供新腾讯key做轮换；高德key#0确认是日配额还是月配额
3. 【dev】高德评论review_kind清理（Q-004）
4. 【collector】腾讯key明天重置后再跑一轮营业时间补全
5. 【qa】Apify集成后验证采集恢复+口味分补全
