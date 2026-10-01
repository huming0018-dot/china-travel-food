# 外部入站健康探针 + 自动关机/开机自愈

为什么需要：food 盒子（上海 Lighthouse）反复出现「实例 RUNNING、出站正常，但公网 IP
完全不通」，根因是 Lighthouse 公网 NAT 映射陈旧；此故障 **Reboot 无效，必须 Stop/Start
重建公网绑定**。探针必须放在**独立于 food 的另一台机器**（本部署在广州 Lighthouse 代理盒），
否则 food 自身失联时无法探测/自救。

## 文件
- `food_watchdog.py`：TCP 探测 food 公网 22；RUNNING 但连续 N 周期不可达即自动 Stop/Start。
- `wd_notify.py`：Telegram + 飞书双通道（TG 走反代、失败降级直连；飞书自建应用）。

## 部署（代理盒）
- 目录 `/home/ubuntu/food-watchdog/`，另有两个 **chmod 600、不入库** 的凭据文件：
  - `wd.env`：`TENCENT_SECRET_ID/KEY`、`FOOD_REGION=ap-shanghai`、
    `FOOD_INSTANCE_ID=lhins-5uumzybo`、`FOOD_PUBLIC_IP=49.234.35.92`。
  - `notify.env`：`TELEGRAM_BOT_TOKEN/CHAT_ID/API_BASE`、
    `FEISHU_APP_ID/APP_SECRET/CHAT_ID`。
- SDK 装在 `/home/ubuntu/wdlib`（common+lighthouse 一次性同装，避免命名空间覆盖）。
- 定时（root，flock 防并发），见 `/etc/cron.d/food_watchdog`：
  ```
  */2 * * * * root /usr/bin/flock -n /tmp/food_wd.lock \
    /usr/bin/python3 /home/ubuntu/food-watchdog/food_watchdog.py >> /var/log/food_wd.log 2>&1
  ```

## 判定参数
- 单轮 TCP 重试 3 次、间隔 5s；连续 `NEED_BAD_CYCLES=2` 个周期失败；
  距上次重启冷却 `RECYCLE_COOLDOWN=900s`；非 RUNNING 视为正常窗口不动作。
- 状态持久化 `wd_state.json`（bad / was_down / announced_pending / last_recycle）防 flapping。

## 已验证
- 手动跑判 `healthy`；cron 每 2 分钟触发、日志连续 healthy。
- 真实各发一条：TG status200 ok=true；飞书 code=0 success。

## 已知遗留
- 第一把主账号「云 API 密钥」无法用 CAM `Delete/UpdateAccessKey` 删停（报
  UinNotMatch，这些接口只作用于 CAM 子用户密钥）；需在网页
  console.cloud.tencent.com/cam/capi 删除。该密钥与有效密钥同属主账号，不额外扩大暴露面。
- 代理盒 2026-10-28 到期：继续依赖需续费，或把本探针改到腾讯 SCF/外部端点。
