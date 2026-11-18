# 搜索解析边界（内部解耦）

`search_result_parsers.py` 输入HTML字符串、输出既有source_url/source_title/snippet/source_host列表（最多8条）。它不请求网络、读取凭据/环境或初始化账本，不导入美食业务。BeautifulSoup负责HTML/CSS解析；不自研HTML解析器。

真实`serp_producer.search_bing/search_ddg`保留请求及HTTP错误返回；缺失BeautifulSoup时的异常行为有下述明确变化，调用纯解析函数。查询生成、餐厅取证、相关性评分、引擎回退、代理和并发仍属项目，未搬进工具。其他14个函数AST不变。

复现：安装cloud/requirements.txt后，在cloud目录运行`python -m unittest -v test_search_result_parsers`。7项离线测试通过；另有8组旧/新消费者输入输出对照一致。消费者测试编译实际函数定义以避开生产者启动副作用，注入HTTP响应，不运行整个任务。没有实网搜索、采集、DB写入或部署。

两站HTML布局随时可变，本批不证明当前网页兼容，不把空列表当搜索成功保证。未验证生产镜像与真实搜索。原代码依赖BeautifulSoup但requirements未列明，本批补声明。复用成熟库的比较：BeautifulSoup已支持CSS选择器与文本提取，保留该依赖优于新写解析框架；正文抽取器不能直接替代搜索结果卡片合同。参考：https://www.crummy.com/software/BeautifulSoup/bs4/doc/

本项只完成项目内工具边界，不计独立通用工具仓交付；没有跨项目真实使用证据，不为两份脆弱选择器新建包/仓。既有Docker与build_sync的cloud/*.py覆盖新增模块。 

## 独立审查补充

缺失BeautifulSoup时，旧版在try之外导入bs4，直接抛ModuleNotFoundError；新版在解析函数内导入，被生产者捕获为(None, 'bing/ddg err ModuleNotFoundError')。这是明确行为变化，不能称异常合同完全不变。requirements已声明该依赖；错误返回不等于搜索成功。

新增test_search_producer_startup完整导入真实serp_producer/common/findings_extractor，并执行真实CLI --help启动；隔离空环境与临时FOOD_DATA_DIR，阻断HTTP/socket，只产生临时空账本目录、不运行采集。缺依赖场景亦以完整生产者测试。原有纯解析/调用测试加启动测试合计7项通过。

尚未真实Docker构建；与PR#35的requirements/镜像联合验证留待总体集成，不合并或部署。
