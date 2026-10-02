#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_standard.py — 标准测试套件，按边界情况清单测试。

参考：testing-protocol skill 的必测边界：
- 空/null输入
- 最小/最大值
- 无效格式
- 网络失败
- API错误
- 超时条件
"""
import sys
import unittest
sys.path.insert(0, '.')

import config
import common
import cost_guard
import notifier
import apply


class TestHTTPLayer(unittest.TestCase):
    """common.py HTTP层测试"""

    def test_empty_url(self):
        """空URL不崩溃"""
        result = common.http_get("")
        self.assertEqual(result, {})

    def test_none_url(self):
        """None URL不崩溃"""
        result = common.http_get(None)
        self.assertEqual(result, {})

    def test_invalid_url(self):
        """无效URL不崩溃"""
        result = common.http_get("not-a-url")
        self.assertEqual(result, {})

    def test_empty_post(self):
        """空POST不崩溃"""
        result = common.http_post("", {})
        self.assertEqual(result, {})

    def test_none_post_data(self):
        """None POST数据"""
        result = common.http_post("http://example.com", None)
        # 应该不崩溃，可能返回错误
        self.assertIsInstance(result, dict)


class TestCostGuard(unittest.TestCase):
    """cost_guard.py 预算门测试"""

    def setUp(self):
        self.old_disabled = config.APIFY_DISABLED
        config.APIFY_DISABLED = False
        self.old_budget = config.APIFY_MONTHLY_BUDGET
        config.APIFY_MONTHLY_BUDGET = 1.0

    def tearDown(self):
        config.APIFY_DISABLED = self.old_disabled
        config.APIFY_MONTHLY_BUDGET = self.old_budget

    def test_normal_spend(self):
        """正常花钱"""
        cost_guard.record_cost(0.1, "test")
        self.assertTrue(cost_guard.can_spend(0.5))

    def test_over_budget(self):
        """超预算拦截"""
        cost_guard.record_cost(0.9, "test")
        self.assertFalse(cost_guard.can_spend(0.5))

    def test_zero_amount(self):
        """金额为0"""
        self.assertFalse(cost_guard.can_spend(0))

    def test_negative_amount(self):
        """负数金额"""
        self.assertFalse(cost_guard.can_spend(-1))


class TestNotifier(unittest.TestCase):
    """notifier.py 通知测试"""

    def test_empty_body(self):
        """空body不崩溃"""
        # 不实际发送，只测试不崩溃
        try:
            notifier.info("", key="test_empty", cadence=9999)
        except Exception as e:
            self.fail(f"空body崩溃: {e}")

    def test_long_body(self):
        """超长body不崩溃"""
        try:
            notifier.info("x" * 10000, key="test_long", cadence=9999)
        except Exception as e:
            self.fail(f"超长body崩溃: {e}")


class TestApply(unittest.TestCase):
    """apply.py 写库门控测试"""

    def test_valid_fact(self):
        """有效事实校验"""
        self.assertTrue(apply.valid_fact("name", "星巴克"))
        self.assertFalse(apply.valid_fact("name", ""))
        self.assertFalse(apply.valid_fact("name", "  "))
        self.assertFalse(apply.valid_fact("name", None))

    def test_price_implausible(self):
        """价格不合理检测"""
        self.assertTrue(apply.price_implausible(100, 500))
        self.assertFalse(apply.price_implausible(100, 120))

    def test_admit_decision(self):
        """准入决策"""
        reviews = [
            {"author": "食客甲", "rating": 4.0},
            {"author": "食客乙", "rating": 4.0},
        ]
        result = apply.decide_admission({"name": "test"}, reviews)
        self.assertEqual(result, "admit")

    def test_hold_decision(self):
        """证据不足hold"""
        reviews = [{"author": "食客甲", "rating": 4.0}]
        result = apply.decide_admission({"name": "test"}, reviews)
        self.assertEqual(result, "hold")


if __name__ == "__main__":
    unittest.main(verbosity=2)
