# 上海美食图鉴 · 极简开发规范

> 本规范适用于所有新增模块和代码修改。目标：用最少的代码实现完整功能，不写一行多余的代码。

---

## 一、核心原则

### 1.1 七层阶梯（来自Ponytail）

写任何代码前，按顺序问自己：

1. **这个功能需要存在吗？** → 不需要就跳过（YAGNI）
2. **代码库里已经有了？** → 复用，不要重写
3. **标准库能做？** → 用标准库，不要装新依赖
4. **平台原生功能？** → 用原生，不要自己造轮子
5. **已安装的依赖？** → 用依赖，不要重复实现
6. **一行能搞定？** → 一行，不要写十行
7. **实在不行** → 写最小可行代码

### 1.2 Simplicity First（来自Karpathy CLAUDE.md）

- 只写用户要求的功能，不加"以后可能会用到"的东西
- 不为单次使用的代码做抽象
- 不写不可能发生的错误处理
- 200行能50行搞定，就重写

### 1.3 Preserve Behavior（来自Addy Osmani /code-simplify）

- 简化代码，但不改变功能
- 所有输入、输出、副作用、错误行为必须保持一致
- 不确定能不能简化就不要动

---

## 二、文件结构规范

### 2.1 目录结构

```
cloud/
├── config.py              # 配置：所有API key/开关从环境变量读
├── common.py              # 公共工具：DB/HTTP/日志，所有模块共用
├── amap_batch.py          # 采集：高德/腾讯地图字段补齐
├── discover.py            # 发现：LLM+关键词+搜索引擎找新店
├── apply.py               # 写库：统一门控，所有数据入库走这里
├── cost_guard.py          # 预算门：所有付费采集统一过这里
├── notifier.py            # 通知：TG播报/告警，只发人类可读
├── progress_broadcast.py   # 播报：定时输出进度
├── scheduler.py           # 调度：所有任务的统一入口
├── watchdog.py            # 看门狗：检查系统是否正常
└── test_security.py        # 安全测试
```

### 2.2 文件大小限制

| 类型 | 最大行数 | 超过怎么办 |
|---|---|---|
| 单文件 | 200行 | 拆分，或者砍冗余 |
| 单函数 | 30行 | 拆分，或者简化逻辑 |
| 单类 | 50行 | 不要写类，用函数 |

**目标：整个项目不超过2000行。**

---

## 三、代码风格规范

### 3.1 导入

```python
# ✅ 好：只导入需要的
import config
import common

# ❌ 坏：不要用 *
from common import *

# ❌ 坏：不要 sys.path.insert 到处插
sys.path.insert(0, "/app/xxx")
```

### 3.2 错误处理

```python
# ✅ 好：try-except只包真正可能失败的操作
try:
    data = common.http_get(url)
except Exception as e:
    common.log.error(f"请求失败: {e}")
    return {}

# ❌ 坏：不要except: pass
try:
    xxx()
except:
    pass  # 吞掉错误，问题永远发现不了

# ❌ 坏：不要为不可能发生的错误写处理
if not data:
    # data不可能是None，common.http_get永远返回dict
    ...
```

### 3.3 日志

```python
# ✅ 好：用统一的log，级别清晰
common.log.info("开始采集")
common.log.warning("配额不足")
common.log.error("请求失败")

# ❌ 坏：不要用print
print("开始采集")

# ❌ 坏：不要在日志里dump整个对象
common.log.info(f"结果: {result}")  # 可能很大
```

### 3.4 通知

```python
# ✅ 好：只发人类可读的一句话
notifier.info(f"在营餐厅 {n}家", key="progress")

# ❌ 坏：不要发原始JSON
notifier.info(json.dumps(data))

# ❌ 坏：不要每次都发，要节流
# notifier.info 有cadence参数，默认3600秒
```

---

## 四、新增模块检查清单

新增任何模块前，先过这个清单：

- [ ] 这个功能真的需要吗？有没有更简单的方式？
- [ ] 能不能复用现有的模块（common/apply/notifier）？
- [ ] 能不能用标准库实现，不装新依赖？
- [ ] 能不能用50行以内写完？
- [ ] 错误处理是不是只写了真正可能发生的？
- [ ] 有没有写不可能发生的错误处理？
- [ ] 通知是不是人类可读，不发JSON？
- [ ] 有没有加安全测试用例？

**如果任何一项答案是"不确定"，就先别写，先问。**

---

## 五、已有模块参考

| 模块 | 行数 | 功能 |
|---|---|---|
| config.py | 52 | 配置加载 |
| common.py | 98 | DB/HTTP/日志工具 |
| cost_guard.py | 59 | 预算门 |
| notifier.py | 80 | TG通知 |
| amap_batch.py | 174 | 高德字段补齐 |
| apply.py | 160 | 统一写库门控 |
| discover.py | 64 | 发现新餐厅 |
| progress_broadcast.py | 68 | 进度播报 |
| scheduler.py | 70 | 任务调度 |
| watchdog.py | 80 | 看门狗 |
| test_security.py | 190 | 安全测试 |
| **总计** | **1095** | |

**新增模块写完后，必须在test_security.py里加对应的测试用例。**
