# toolbox

CTFS 模块化数据中台工具包（PRD v2.1 Phase 0 骨架）。八个独立工具模块：

- `crawler` M1 采集器 · `cleaner` M2 清洗器 · `scorer` M3 评分器 · `ontology` M4 本体库
- `orchestrator` M5 编排器 · `auditor` M6 审计器 · `deliverer` M7 交付器 · `storage` M0 存储层

导航地图与任务队列见仓库根 `MODULES-NAV.md` / `PRD-ROADMAP.md`。

## 安装（开发模式）

```bash
cd toolbox
python3 -m pip install -e .
```

## CLI（Phase 0）

```bash
toolbox init --domain food --city shanghai --output ../projects/shanghai-food   # 生成项目 Manifest 模板
toolbox manifest validate --manifest ../projects/shanghai-food/manifest.yaml     # 校验 Manifest
toolbox schema list                                                              # 列出数据契约
toolbox schema validate --schema raw --data <raw.json>                           # 契约校验数据
```

## 测试

```bash
cd toolbox && python3 -m unittest discover -s tests -v
```
