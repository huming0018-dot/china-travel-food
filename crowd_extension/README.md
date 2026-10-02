# 众包采集插件（Crowd Extension）

> PM 窗口独立开发 · 2026-10-02 · 契约 CROWD-CONTRACT-001
> 上海美食图鉴「任务发放 + 众包采集」的插件载体：参与者自有账号/设备/网络，全自动采集，直接回传 Supabase。

## 目录
```
crowd_extension/
├── manifest.json          # Chrome 扩展 manifest v3
├── CROWD_CONTRACT.md      # 数据契约（格式/获取/回传/同步一致性铁律）
└── src/
    ├── background.js      # Service Worker：任务拉取/调度/回传
    ├── content.js         # 页面注入：搜索结果/笔记详情采集
    ├── safety_engine.js   # 安全线引擎（硬编码不可调）
    ├── popup.html         # 状态面板
    └── onboarding.html    # 知情同意书（参与协议门槛）

cloud/
├── crowd_ingest.py        # 服务端回传校验+落库+状态回写（契约执行者）
└── crowd_pack.py          # 任务包生成发布（店铺池→crowd工单）
```

## 打包步骤（发给参与者）
1. `cd crowd_extension`
2. 构建时注入配置：在 `background.js` 顶部替换 `CROWD_API_BASE` / `CROWD_API_KEY`（Supabase anon key，最小权限）。
3. Chrome → `chrome://extensions` → 开发者模式 → 加载已解压的扩展程序 → 选择本目录。
4. 参与者打开 `onboarding.html`（扩展详情 → 扩展程序选项）阅读协议 → 填报名发放的参与者ID → 同意。
5. 回到小红书页面，插件自动拉取 `assignee=crowd` 的任务包并按安全线采集。

## 服务端（回传闭环）
- 发布任务包：`python3 cloud/crowd_pack.py --stores stores.json --pack-size 6`
- 收回传（HTTP 服务或定时 ingest）：`python3 cloud/crowd_ingest.py --ingest envelope.json`
- 校验预览：`python3 cloud/crowd_ingest.py --dry-run envelope.json`

## 依赖表（Supabase 需建，dev 或 PM）
- `crowd_tasks`（task_id/pack/progress/status/assigned_count）
- `crowd_proofs`（信封+proof 字段+gate_status+dedupe_key 唯一）
- `crowd_reviews`（store/rating/reason/trust_level）
- `crowd_settlements`（participant/period/effective_count/amount）

## 同步一致性（契约 §5 摘要）
- task_id 原样回传 · sync_version=1 不符即拒 · proof_seq 幂等 · gate_status 唯一权威 · 一机一号 · 断点续传
