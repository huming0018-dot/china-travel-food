# 凭据轮换清单（A 批配套，仅列清单，本轮不执行轮换、不重写 git 历史）

> 依据：F14 已把硬编码密钥从云仓源码移除，但**密钥只要进过 git 历史就必须视为已泄露**，
> 必须在控制台轮换。本文只登记资产、所在位置与处置动作，**不写任何明文密钥**
> （仅用「前4…后4」指纹用于辨认）。
> 配套代码状态见 `cloud/SECURITY_BATCH_A_LEDGER_20261014.json`。

## 1. 必须轮换（曾进入 git 历史）

| # | 资产 | 指纹（仅辨认） | 曾经所在位置 | 现状 | 处置动作 |
|---|---|---|---|---|---|
| 1 | 腾讯位置服务 WebService **key**（SK 鉴权） | `7PQB…OBT6` | 历史提交中的 `cloud/vendor/pipeline/tencent_sig.py`、`cloud/map_quota.py` | 源码已移除（A 批），但**仍在 git 历史** | 在腾讯位置服务控制台**作废旧 key 并新建**；新 key 仅写入 gitignored `deploy.env`（`TENCENT_MAP_KEY(S)`） |
| 2 | 腾讯位置服务 **SK（签名密钥）** | `4ibu…HlZo` | 同上 | 同上，仍在 git 历史 | 与新 key 配对重置/新建 SK；仅写入 `deploy.env`（`TENCENT_MAP_SK(S)`） |

说明：
- 轮换后，若历史已推送到远端，删除提交不能让泄露失效，**作废重发才是根治**。
- 新配置格式（多独立账号池，逗号分隔，见 `map-quota-fix.md`）：
  `TENCENT_MAP_KEYS=...`、`TENCENT_MAP_SKS=...`，或单值 `TENCENT_MAP_KEY`/`TENCENT_MAP_SK`。
- 代码在缺配置时结构化停用（`MapCredentialUnavailable` / `no_credentials`），
  不影响高德通道；部署前必须先把新 key/SK 写好，否则腾讯通道停摆（属预期，不报错刷屏）。

## 2. 不在 git 仓内、但仍需处理（明文副本）

| # | 资产 | 位置 | 说明 |
|---|---|---|---|
| 3 | 同一腾讯 key/SK 的明文副本 | city-food-guide **skill 副本** `scripts/food_pipeline/tencent_sig.py` 第 21–22 行常量（`KEY=`/`SK=`） | 不在 git 仓内，A 批未改；该文件与云仓 vendor 是两套副本。**轮换密钥后**需同步改为从环境读取（或删除该副本，统一指向云仓），避免旧明文继续可用。 |

## 3. 本次确认**未**在云仓源码树出现、暂不列入轮换

- Telegram bot token：云仓 `cloud/` 源码树未发现明文；由 deuce 本地 `tg_send.py` 经
  `.tg_env` 读取，部署/容器不持有。仍应纳入密钥台账，定期巡检。
- Supabase service_role key：未在云仓源码树发现；REST 仅在请求头携带（非 URL）。
  扩展页 publishable key 为按设计公开，不需要轮换。

## 4. 执行顺序（后续独立批次，勿与 A 批止损 PR 混做）

1. 控制台作废 #1/#2 旧 key/SK，新建并记录到 `deploy.env`（本地，不入库）。
2. 更新 #3 skill 副本（改为环境读取或删除），确认无其它明文残留。
3. 配置就绪后再做 `build_sync` 烘焙与线上验证；本次 A 批不部署。
4. 轮换完成后在本清单与修复账本标注完成日期与操作人。
