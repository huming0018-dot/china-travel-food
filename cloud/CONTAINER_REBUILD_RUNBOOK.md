# 容器重建 RUNBOOK — 上海美食图鉴·云端采集常驻服务

> 本文记录现存项目重建入口，不是部署授权或本轮构建成功证明。目标是从 GitHub 源码重建，避免 `docker cp` 补脚本后重建丢失。服务器地址为历史配置，本轮未连接核验。

## 一、架构一图

```
GitHub: huming0018-dot/china-travel-food (main，唯一权威源)
   ├─ cloud/*.py                 容器运行代码（采集/校验/调度/通知）
   ├─ cloud/vendor/pipeline/*.py 管线模块（容器内 /app/pipeline）
   ├─ cloud/Dockerfile           镜像定义
   ├─ cloud/crontab.txt          容器内 cron（声明式，构建时加载）
   ├─ cloud/entrypoint.sh        容器入口（固化env→加载crontab→起cron）
   ├─ cloud/docker-compose.yml   编排（restart:always + 卷 + 密钥挂载）
   └─ cloud/requirements.txt     Python 依赖
        │ build_sync.sh（服务器上跑）
        ▼
镜像 food-cloud:local ──► 容器 food-cloud（生产，常驻）
        ├─ volume  food-cloud_fooddata → /app/data   （断点/日志/数据，持久化）
        ├─ bind    ~/food-cloud/xhs_accounts → /secrets/xhs_accounts (ro)
        └─ bind    ~/food-cloud/xhs_cookies.json → /secrets/xhs_cookies.json (ro)
```

- 另有 `searxng` 容器（搜索引擎，compose 外独立，每日 03:14 与 food-cloud 一起 restart）。
- 容器内**无 git**：代码在构建时 COPY 进镜像，改代码必须走 GitHub + 重建，**不要 docker cp**（不进镜像、重建即丢）。

## 二、一键重建（标准操作）

SSH 进服务器后，**一条命令**完成「拉最新代码 → 同步构建上下文 → 构建镜像 → 起容器」：

```bash
bash ~/food-cloud/build_sync.sh
```

- 脚本内部：`git fetch/reset origin/main` → rsync `cloud/*.py` 与 `cloud/vendor/pipeline/*.py`
  到构建上下文 `~/food-cloud/` → 拷贝 Dockerfile/crontab/entrypoint/requirements/compose
  → `docker build -t food-cloud:local .` → `docker compose up -d`。
- 结束标志：输出 `BUILD_SYNC_DONE based on <commit>`，并打印 compose ps。
- 只想同步代码不构建：`bash ~/food-cloud/build_sync.sh --no-build`。
- 注意：docker 命令需 sudo（脚本内已带 sudo）；服务器无本机代理，脚本直连。

## 三、重建后验证清单（逐项确认）

```bash
sudo docker ps --format '{{.Names}} {{.Status}}'        # food-cloud Up、restart 计数正常
sudo docker exec food-cloud crontab -l | wc -l          # crontab 已加载（非0）
sudo docker exec food-cloud pgrep -c cron               # cron 进程在跑（≥1）
sudo docker exec food-cloud ls /app/pipeline | wc -l    # pipeline py 数与 git cloud/vendor/pipeline 一致
sudo docker exec food-cloud sh -c 'tail -5 /app/data/*.log 2>/dev/null'  # 有最新日志
```

- 容器 /app/cloud、/app/pipeline 的 py 数应与 GitHub main 一致（版本对齐）。
- 数据卷不被重建影响：历史断点、日志、`/app/data/notify_channels.json` 通道开关保留。

## 四、密钥与数据（不进 git，重建前必须就位）

构建上下文 `~/food-cloud/` 下（脚本 rsync 只同步 *.py，不会覆盖这些）：

| 文件 | 用途 | 缺失后果 |
|---|---|---|
| `deploy.env` | 所有密钥（Supabase/TG/飞书/地图/LLM），compose `env_file` | 容器起来但全部鉴权失败 |
| `xhs_accounts/` | 小红书多账号 cookie 池 | 小红书采集无账号 |
| `xhs_cookies.json` | 旧单账号 cookie（回退） | 仅旧路径不可用 |

> 这些只存在于服务器，**绝不提交 git**。换服务器时需单独备份迁移。

## 五、故障排查

| 现象 | 排查 / 处理 |
|---|---|
| 容器反复重启 | `sudo docker logs --tail 50 food-cloud`；多为 deploy.env 缺失或语法错 |
| cron 没跑 | entrypoint 是否执行到 `cron`；`crontab -l` 是否为空；日志在 /app/data/*.log |
| 重建后某脚本丢失 | 说明它当初是 docker cp 补的、没进 GitHub；从容器/备份取回后提交 git 再重建 |
| 数据像被清空 | 确认 fooddata 卷仍挂载（`docker inspect` Mounts）；compose down 不会删命名卷，`down -v` 才会 |
| 容器每天 03:14 短暂重启 | 预期行为（宿主 /etc/cron.d/food_restart），非故障 |
| 端口/网络异常 | 服务为出站采集，不暴露入站端口；检查服务器出站与 DNS |

## 六、治理红线

1. 唯一权威源是 GitHub main；任何改动先提交再 `build_sync.sh` 重建。
2. 禁止 `docker cp` 补代码、禁止在容器内手工改代码（不可复现）。
3. 密钥/账号 cookie 绝不进 git。
4. 新增定时任务：改 `cloud/crontab.txt`（不是进容器编辑），重建生效。
5. 新增管线模块：放 `cloud/vendor/pipeline/`，build_sync 自动 rsync 进 /app/pipeline。

## 七、依赖闭包审计（定期治理）

判断 cloud 里哪些是真死代码（而非"未接线的新功能"）：

```bash
python3 cloud/container_closure_audit.py --json /tmp/closure.json
```

- 输出仅是筛选线索，不是完整依赖闭包、删除依据或“已交付”证明；该脚本已有漏相对/包导入、忽略语法错误及 cron 入口误判的已知限制。
- 结合真实调用、配置、打包与历史核对完整性和价值。归档、未接线、手动运维或备用模块都不凭标签决定保留或删除。
- 未接线模块先判断是否仍值得保留；不自动派工接线，不以仓库整理恢复产品开发。退出须有明确范围、消费者处置和恢复点。

## 旧本机部署链退出

- 归属：Dockerfile/requirements 是项目环境定义，compose/entrypoint/cron 是美食业务运行编排；保留实际闭包，不包装为独立通用环境工具。
- 删除 `prepare.sh`：其输入仅是个人 Doubao 技能绝对路径，先删再覆盖整个 vendor/pipeline；GitHub 已持有管线源码，不再接受本机副本覆盖权威源。
- 删除 `build_on_server.sh`：旧上传式入口会覆盖宿主 Docker daemon 配置并重启 Docker、上传本机凭据覆盖服务器配置、先停服务删镜像再构建。其实际 tar 清单漏掉 Dockerfile 必需的 external_watchdog/telegram_delivery.py，无法完成当前构建闭包。保留这些具体经验，不维护第二套上传部署链。
- 保留 `build_sync.sh`、Dockerfile、compose、entrypoint、crontab、requirements、fix_paths.py 及 deploy.sh 原内容；fix_paths.py 仍是镜像实际消费者，不能随个人路径入口一起删除。
- `build_sync.sh` 会 fetch/reset 源码缓存、rsync 清除多余 Python 文件；默认还构建镜像并 compose up。`--no-build` 仅跳过构建启动，仍修改文件。它不会负责迁移本机未提交内容，不是只读同步或通用安装器。
- 历史 HANDOFF、QUALITY 报告、research/design/ponytail_cutlist.md 及问题汇总中的旧脚本名称仅作历史来源，不能照其命令恢复部署。当前操作规范已改指现存入口。
- 恢复点：Git 提交 `885d13e2ebed10cf24cfec557b662ee797438eaf` 保有两个旧脚本原文。历史可查，不建议恢复运行。
- 验证：固定基线离线核对全部仓内引用、当前 Docker COPY/cron 文件目标；按旧命令生成临时 tar，复现缺件。未运行 Docker 构建、SSH、采集或任何部署，不修改宿主配置、凭据和已安装任务。 `build_sync.sh` 的 external_watchdog/pipeline 两段 rsync 仍以 `|| true` 忽略失败；本批未修改该行为，也未验证同步失败时的镜像一致性，文件目标存在不等于实际构建成功。
