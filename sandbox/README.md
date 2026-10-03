# 上海美食图鉴 · 沙盒核心模块

> 这是精简重构后的核心代码，总共1700行，实现完整功能。
> 新对话框拿到这个目录就能直接跑，不需要额外交接。

---

## 快速开始

### 1. 环境变量配置

创建 `.env` 文件，或直接设置环境变量：

```bash
# 数据库（Supabase）
export SUPABASE_URL="https://xxx.supabase.co"
export SUPABASE_SERVICE_ROLE_KEY="xxx"

# 高德地图
export AMAP_KEYS="key1,key2"
export AMAP_SKS="sk1,sk2"

# 腾讯地图
export TENCENT_MAP_KEY="xxx"

# Telegram通知
export TELEGRAM_BOT_TOKEN="xxx"
export TELEGRAM_CHAT_ID="xxx"

# Apify（可选，默认禁用）
export APIFY_TOKEN="xxx"
export APIFY_DISABLED="1"
export APIFY_MONTHLY_BUDGET="0.5"
```

### 2. 运行测试

```bash
# 标准测试15项
python3 test_standard.py

# 变态攻击测试18项
python3 test_chaos.py
```

### 3. 运行模块

```bash
# 看门狗检查
python3 watchdog.py

# 高德批量补字段
python3 amap_batch.py --apply --limit 10

# 预算查询
python3 -c "import cost_guard; print('剩余:', cost_guard.remaining())"
```

---

## 模块说明

| 文件 | 行数 | 功能 |
|---|---|---|
| config.py | 52 | 统一配置，所有key从环境变量读 |
| common.py | 146 | DB/HTTP/日志/重试，公共工具 |
| cost_guard.py | 62 | 统一预算门，所有付费采集过这里 |
| notifier.py | 83 | TG通知出口，去重+冷却 |
| amap_batch.py | 209 | 高德批量补字段（电话/坐标/营业时间/评分） |
| apply.py | 160 | 统一写库门控，所有数据入库走这里 |
| watchdog.py | 95 | 看门狗：磁盘/内存/数据新鲜度/预算 |
| progress_broadcast.py | 68 | 心跳播报 |
| scheduler.py | 70 | 任务调度 |
| discover.py | 64 | 新店发现 |
| **核心代码总计** | **1009** | |

---

## 技术规范

详见 [DEV_STANDARD.md](DEV_STANDARD.md)

核心原则：
1. 单文件不超过200行，单函数不超过30行
2. 所有错误打日志，不允许`except: pass`
3. 所有通知人类可读，不发原始JSON
4. 所有外部调用有重试（最多3次，指数退避）
5. 所有写入有校验，空值不写

---

## 测试覆盖

| 测试 | 用例数 | 覆盖角色 |
|---|---|---|
| test_standard.py | 15 | 标准功能测试 |
| test_chaos.py | 18 | 黑客/误操作/恶意访问/极端环境/并发/边界 |
| test_security.py | 216行 | 安全测试 |

**总共50+测试用例，全部通过。**

---

## 部署到服务器

```bash
# 1. 复制代码到服务器
scp -r sandbox/ ubuntu@49.234.35.92:/home/ubuntu/food-cloud/sandbox

# 2. 在服务器上运行
ssh ubuntu@49.234.35.92
cd /home/ubuntu/food-cloud/sandbox
python3 test_standard.py  # 验证环境
```

---

## 常见问题

**Q: 为什么我运行时报错？**
A: 先检查环境变量是否配置了，特别是SUPABASE_URL。

**Q: 怎么加新模块？**
A: 先看DEV_STANDARD.md的检查清单，确认功能真的需要，再写50行以内的代码，最后加测试用例。

**Q: 怎么调试？**
A: 日志在 `data/logs/app.log` 和 `data/logs/error.log`。
