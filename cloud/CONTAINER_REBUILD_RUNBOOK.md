# 容器重建 RUNBOOK — 上海美食图鉴·云端采集常驻服务

> 目标：任何接手者照本手册，能用**一条命令**把生产容器从 GitHub 权威源码完整重建，
> 不再依赖 `docker cp` 补脚本（重建即丢）。腾讯云服务器 `49.234.35.92`。

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

- 从全部生产入口递归 import 得"活代码闭包"，列出疑似孤儿；
- **静态分析会漏动态 import，孤儿必须再做全仓 grep 交叉验证、人工甄别后才能删**；
- 注意区分三类：① `_archived/_archive` 明确归档→可删；② 已交付但未接线的功能模块
  （建了没生效）→ 不删，应派工单"接线"；③ 手动运维工具/备用通道→保留。
