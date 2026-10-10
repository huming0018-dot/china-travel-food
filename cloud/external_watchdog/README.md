# 外部入站健康探针 + 自动关机/开机自愈

探针独立于 food 上海服务器运行。历史部署记录：广州代理盒
139.199.90.169，目录 `/home/ubuntu/food-watchdog/`。
此地址/目录是部署记录，不能替代本轮服务器核查。

## 通知合同（仅 Telegram）

主应用 `health.py` 和外部 `wd_notify.py` 共用 `telegram_delivery.py`：

1. Supabase `telegram_notify_enqueue` 入队，再调用 `telegram_notify_receipt`。
   只有 `delivered=true`（Telegram HTTP 200 且 JSON `ok=true`）才算成功。
2. 中继失败、回执失败或等待超时，尝试 `TELEGRAM_API_BASE`。
3. 反代失败，尝试官方 `https://api.telegram.org`。大陆服务器不能依赖此项可达。

每条消息入队一次，最多查回执四次；每个 Bot API 出口一次。requests 仍遵循
HTTP(S)_PROXY 配置。禁止重定向，日志不输出密钥、完整请求 URL、异常正文或响应正文。
超时后降级可能重复发送；回执超时不代表 Telegram 一定未收到。
完全断网不能实时送达。外部看门狗将失败消息保存至 chmod 600 的
`notify_pending.json`，每次 cron 启动最多重试一条，成功后移除。
主应用失败不记告警冷却，后续相同告警可以重试。

## 最小权限部署

- 两端先部署 `cloud/supabase/migrations/20261010073742_telegram_notify_receipts.sql`。
  迁移复用现有 `crowd_notify_tg`，不改采集表或原函数。
- 在 `crowd_private_config` 中安全配置独立的 `tg_notify_secret`（随机高熵值，
  不提交源码、不回显）。通知能力仅允许向既有机器人/收件人发消息并查询通知回执。
- 看门狗 `notify.env` 参考 `notify.env.example`：URL、publishable/anon API key、
  `TELEGRAM_RELAY_SECRET`；不复制 DB 密码、service_role 或 `CROWD_OPS_SECRET`。
- 主应用支持同样的通知配置，也兼容其已有 Supabase key 与 ops_secret。
  `entrypoint.sh` 已将中继环境变量传给 cron。
- 两端可独立保留 Bot Token、Chat ID、反代供降级；必须核对其收件人与中继一致。
- 看门狗部署必须一起复制 `food_watchdog.py`、`wd_notify.py`、`telegram_delivery.py`。
  只复制旧 wd_notify.py 或只更新仓库，不算完成部署。
- `wd.env`（chmod 600）保留原有腾讯云实例配置；SDK `/home/ubuntu/wdlib`。

cron 原配置（核查服务器后确认）：

```cron
*/2 * * * * root /usr/bin/flock -n /tmp/food_wd.lock /usr/bin/python3 /home/ubuntu/food-watchdog/food_watchdog.py >> /var/log/food_wd.log 2>&1
```

不要为验证通知运行 `food_watchdog.py`：它可能触发真实 Stop/Start。
通知自检须与 cron 共用锁：

```sh
sudo flock -n /tmp/food_wd.lock python3 /home/ubuntu/food-watchdog/wd_notify.py
```

## 验收分层

1. 代码：运行隔离 Python 与 SQL/ACL 测试；没有真实网络或通知。
2. 数据库：核对迁移、函数/表 ACL；回执查询仅返回布尔状态，不回传消息或密钥。
3. 服务器：只读核对 cron、文件 SHA256、notify.env 的配置存在性、文件权限及代理
   环境变量；不得输出 token/secret 值。确认两个新 RPC 可达、鉴权可用。
4. 出口：从广州服务器分别测试中继、反代、官方路径。getMe 成功只能说明机器人
   鉴权/网络可用，不能替代 sendMessage 验证。记录路由、时间与结果。
5. 真实通知：从 wd_notify 发送有明确“自检”标记的一条消息，记录 Telegram 回执；
   用户实际看到消息另行确认。只有数据库发出的消息不能证明看门狗出口。

历史 10 月 1 日曾验证 cron healthy 和旧 TG/飞书双通道，但不作为本版本验收。

## 隔离回归

```sh
python3 -m unittest discover -s cloud/tests -p 'test_telegram_delivery.py' -v
CROWD_TEST_TOOLS=/path/to/pglite-tools node cloud/tests/telegram-notify-receipts.mjs
```

SQL 测试使用真实 PostgreSQL 引擎（PGlite）执行迁移和权限检查，但 pg_net transport
为模拟；不能把测试结果当成生产送达。

## 已知运维事项（历史记录，待服务器核实）

- 连续两轮 TCP 22 不通且实例 RUNNING，距上次操作至少 900 秒才 Stop/Start。
- 广州代理盒历史到期日为 2026-10-28；仍依赖该机器时需核查续费。
