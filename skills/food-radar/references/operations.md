# 操作说明
核心：Python >=3.11，标准库；宿主联网搜索是外部能力，不在本脚本内。以下全部演示变量/路径，不能拿示例 actor 处理真实收藏。路径按宿主配置传入，命令参数安全构造，不对网页文字 eval。
## 无持久化检索
```sh
python3 scripts/radar.py plan --city 上海 --mode radar --from 2026-12-20 --to 2027-01-10 --tag 菌菇
bash scripts/preflight.sh --channel public
```
日期由当前实际时间/用户行程计算，不照抄示例。将 queries 送宿主搜索，读源网页确认具体事实。公告/公众号不可读时保留线索、注明未核实。可选平台不支持时仍能先给公开来源短名单。

## 持久化闭环
宿主先从可信上下文得到 scope，给 --db 固定私有路径、--surface 会话作用域、--actor 用户作用域。用户输入不得覆盖。
```sh
python3 scripts/radar.py ingest --db /private/data/food.sqlite --surface TRUSTED_CHAT --actor TRUSTED_USER --input verified-records.json
python3 scripts/radar.py profile --db /private/data/food.sqlite --surface TRUSTED_CHAT --actor TRUSTED_USER --input explicit-profile.json
python3 scripts/radar.py shortlist --db /private/data/food.sqlite --surface TRUSTED_CHAT --actor TRUSTED_USER --city 上海 --mode now --budget 500
python3 scripts/radar.py shortlist --db /private/data/food.sqlite --surface TRUSTED_CHAT --actor TRUSTED_USER --city 上海 --mode radar --from 2026-10-01 --to 2026-11-01
python3 scripts/radar.py save --db /private/data/food.sqlite --surface TRUSTED_CHAT --actor TRUSTED_USER --id r1 --note "纪念日想去"
python3 scripts/radar.py feedback --db /private/data/food.sqlite --surface TRUSTED_CHAT --actor TRUSTED_USER --id r1 --verdict mixed --eaten-on 2026-10-01 --note "这次酱汁偏甜；想试下次的季节菜单"
python3 scripts/radar.py wishlist --db /private/data/food.sqlite --surface TRUSTED_CHAT --actor TRUSTED_USER
python3 scripts/radar.py history --db /private/data/food.sqlite --surface TRUSTED_CHAT --actor TRUSTED_USER --id r1
python3 scripts/radar.py changes --db /private/data/food.sqlite --surface TRUSTED_CHAT --actor TRUSTED_USER --after 0
```
profile 不带 --input 为只读；完整字段见数据契约。没有强迫用户先填完整问卷。示例 experienced-profile.json 只包含明确重视维度，无菜系、预算、具体食材假设；应用前需可靠确认当前用户，不能在安装时给所有人套这个档案。
new/opening radar 和未来事件可以用不同窗口查后合并；默认两组各 3–5 项即可。now/later 返回店；要给行程增加客座机会再查 radar。排序不是最终好吃判断，宿主结合本次场景解释卡片。脚本不提供地图距离、实时余位/排队 API；这些必须另查或标未知。

## 可选点评
```sh
bash scripts/preflight.sh --channel dianping
python3 scripts/dianping_fetch.py --data-dir /private/data --surface TRUSTED_CHAT --actor TRUSTED_USER --keyword 菌菇 --city-id VERIFIED_CITY_ID
python3 scripts/dianping_fetch.py --data-dir /private/data --surface TRUSTED_CHAT --actor TRUSTED_USER --shop-url https://www.dianping.com/shop/VERIFIED_SHOP_ID
```
城市编号必须核实，未提供拒绝搜索。先搜列表，再明确选择某一分店查详情；不会悄悄只取第一家。需要登录时由用户明确同意交互登录后使用 --login；浏览器独立 profile，按宿主作用域隔离，无 Cookie 导出。登录完成不代表会话已通过实际采集验证。
Playwright 缺失返回 dependency_missing；页面重定向/验证/布局不匹配返回 channel_unverified，并回退公开搜索。新解析器宁缺勿错，不再拿口味/环境/服务分数拼综合分；可见字段也仍需目视核验。
media 自检支持 --media-root 显式目录，仅诊断已有外部工具；未打包、不下载、不安装、不自动运行 MediaCrawler。本版未提供小红书/微信私有 API 采集器。

## 验证
```sh
python3 -m unittest discover -s scripts -p 'test_*.py' -v
```
测试全部合成数据，使用 .example 域名，无真实账号，不代表真实餐厅推荐。真实页面适配需用户有相应环境后单独实机验收。
