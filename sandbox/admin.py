#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""admin.py — 可视化后台：查看状态 + 修改配置。

启动：
  python3 admin.py              # 启动Web服务，端口8080
  open http://localhost:8080

功能：
  - 查看所有模块状态
  - 修改任务周期/开关
  - 保存配置
"""
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs
import config
import common
import scheduler

HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>美食图鉴 · 管理后台</title>
    <meta charset="utf-8">
    <style>
        body { font-family: -apple-system, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; background: #f5f5f5; }
        h1 { color: #333; }
        .card { background: white; border-radius: 8px; padding: 16px; margin-bottom: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
        .row { display: flex; justify-content: space-between; align-items: center; padding: 8px 0; border-bottom: 1px solid #eee; }
        .row:last-child { border-bottom: none; }
        input { width: 60px; padding: 4px; margin: 0 8px; }
        button { background: #3498db; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; }
        .save { background: #27ae60; }
    </style>
</head>
<body>
    <h1>🍜 美食图鉴 · 管理后台</h1>
    <div class="card">
        <h3>📊 系统状态</h3>
        <div class="row"><span>在营餐厅</span><strong>1512家</strong></div>
        <div class="row"><span>评价库</span><strong>2457条</strong></div>
    </div>
    <div class="card">
        <h3>⏰ 任务调度</h3>
        <div id="tasks"></div>
        <button class="save" onclick="save()">保存配置</button>
    </div>
    <script>
        async function load() {
            const r = await fetch('/api/tasks');
            const tasks = await r.json();
            const div = document.getElementById('tasks');
            div.innerHTML = '';
            for (const [name, cfg] of Object.entries(tasks)) {
                const row = document.createElement('div');
                row.className = 'row';
                row.innerHTML = `
                    <span>${name}</span>
                    <span>
                        <input type="checkbox" ${cfg.enabled ? 'checked' : ''} onchange="update('${name}', 'enabled', this.checked)">
                        每<input type="number" value="${Math.round(cfg.interval/3600)}" onchange="update('${name}', 'interval', this.value*3600)">小时
                    </span>
                `;
                div.appendChild(row);
            }
        }
        let config = {};
        function update(name, key, value) {
            if (!config[name]) config[name] = {};
            config[name][key] = value;
        }
        async function save() {
            await fetch('/api/save', {
                method: 'POST',
                body: JSON.stringify(config)
            });
            alert('已保存');
            config = {};
            load();
        }
        load();
    </script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML.encode())
        elif self.path == "/api/tasks":
            tasks = scheduler.load_tasks()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(tasks, ensure_ascii=False).encode())

    def do_POST(self):
        if self.path == "/api/save":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode()
            new_config = json.loads(body)
            current = scheduler.load_tasks()
            for name, updates in new_config.items():
                if name in current:
                    current[name].update(updates)
            scheduler.save_tasks(current)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok": true}')


if __name__ == "__main__":
    print("启动管理后台: http://localhost:8080")
    server = HTTPServer(("0.0.0.0", 8080), Handler)
    server.serve_forever()
