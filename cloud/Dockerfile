# Dockerfile — 上海美食图鉴·云端采集常驻服务（amd64 原生构建，全部走国内源）
# 用精简 python base + 仅装 Chromium（体积小、国内可达），替代庞大的完整 Playwright 官方镜像。
FROM python:3.12-slim-bookworm

# 国内 apt 源（Debian bookworm）+ 中文字体/cron/时区/基础工具
RUN sed -i 's@//deb.debian.org@//mirrors.aliyun.com@g; s@//security.debian.org@//mirrors.aliyun.com@g' \
        /etc/apt/sources.list.d/debian.sources 2>/dev/null || true; \
    apt-get update && apt-get install -y --no-install-recommends \
        fonts-noto-cjk fonts-wqy-zenhei cron tzdata ca-certificates curl \
    && ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime \
    && rm -rf /var/lib/apt/lists/*

ENV TZ=Asia/Shanghai \
    FOOD_PIPELINE_DIR=/app/pipeline \
    FOOD_DATA_DIR=/app/data \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_DOWNLOAD_HOST=https://cdn.npmmirror.com/binaries/playwright

WORKDIR /app/cloud

# 1) Python 依赖（清华源；含 playwright）
COPY requirements.txt /app/cloud/requirements.txt
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

# B站搜索兜底 CLI（上游2026-03停更，仅API失败时用；装不上不阻断构建，主路径是零依赖API）
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple "bilibili-cli==0.6.2" || echo "bili-cli 安装失败，仅走B站API主路径（可接受）"

# 2) 装 Chromium 系统依赖 + 浏览器（主包/ffmpeg 走 npmmirror）。
#    npmmirror 缺可选的 chromium-headless-shell（404），而本服务 launch() 默认用完整
#    Chromium 的新 headless、不依赖 headless-shell，故容忍其下载失败，并校验主包可执行文件就位。
RUN playwright install --with-deps chromium || true
RUN test -x /root/.cache/ms-playwright/chromium-1148/chrome-linux/chrome && echo CHROMIUM_MAIN_OK

# 3) 管线快照 + 路径修正（本机绝对路径 -> 容器路径）
COPY vendor/pipeline /app/pipeline
COPY fix_paths.py /app/cloud/fix_paths.py
RUN python /app/cloud/fix_paths.py /app/pipeline

# 4) 云端运行代码
COPY cloud_bu.py xhs_cookie_pool.py cloud_ready.py health.py run_batch.py map_helpers.py cloud_phone_fill.py cloud_coord_fill.py cloud_hours_fill.py cloud_review_fill.py cloud_amap_fill.py candidate_apply.py cloud_discover.py cloud_bili_collect.py unmatched_bridge.py watchdog.py /app/cloud/

# 5) 定时与启动脚本
COPY crontab.txt entrypoint.sh /app/cloud/
RUN chmod +x /app/cloud/entrypoint.sh \
    && mkdir -p /app/data/research/atlas/xhs

# 数据持久化目录（运行时挂载：-v fooddata:/app/data）
VOLUME ["/app/data"]

ENTRYPOINT ["/app/cloud/entrypoint.sh"]
