# 证据账本入口边界

`python cloud/vendor/pipeline/evidence_pool.py` 读取餐厅、评价和本地 B站发现文件，生成本地 pool.jsonl；会读取数据库，但不写数据库、不收录新品牌。原 `--commit` 从未实现提交，现拒绝该参数，且在 main 中的数据库读取与报告目录创建前退出；模块导入仍可能由 common 读取本地 env 配置。聚合算法不变。

恢复点：b9cb0c3d98d45a6a6b2c77341b68d2c93f77c322。离线验证：`cd cloud && python -m unittest -v test_evidence_pool_entry`，只提供最小 common 夹具（读取表和原样文本函数），不测试真实归一化或 common 导入，验证正常账本及无效入口先行失败；不证明真实采集或生产数据质量。

项目欠账（未在本轮修复）：同作者不同 URL 被计为多个独立声音；重复评价键计数去重但口味均分仍重复计入。保留项目核心，不将这些局部缺陷误判为整模块无用。
