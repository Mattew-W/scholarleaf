"""
tests/test_rules.py - RuleEngine 单元测试
============================================================
"""
import json
import tempfile
from pathlib import Path

import pytest

from core.rules import BlockingRule, RuleEngine


class TestBlockingRule:
    """BlockingRule 数据类测试"""

    def test_matches_exact(self):
        rule = BlockingRule(
            name="test",
            pattern=r"离开|切换",
            category="dialog",
            action="block",
            created_at="2026-01-01T00:00:00",
        )
        assert rule.matches("确定要离开吗？")
        assert rule.matches("切换标签页")
        assert not rule.matches("正常操作")

    def test_matches_regex(self):
        rule = BlockingRule(
            name="test_regex",
            pattern=r"report.*(abnormal|error)",
            category="console",
            action="log",
            created_at="2026-01-01T00:00:00",
        )
        assert rule.matches("report abnormal behavior")
        assert rule.matches("report error")
        assert not rule.matches("report success")

    def test_matches_case_insensitive(self):
        rule = BlockingRule(
            name="test_case",
            pattern=r"LEAVE|SWITCH",
            category="dialog",
            action="block",
            created_at="2026-01-01T00:00:00",
        )
        assert rule.matches("please leave the page")
        assert rule.matches("SWITCH tab")

    def test_invalid_pattern_fallback(self):
        rule = BlockingRule(
            name="test_invalid",
            pattern=r"[invalid regex",
            category="dialog",
            action="block",
            created_at="2026-01-01T00:00:00",
        )
        # 无效正则应回退到简单包含匹配
        assert rule.matches("包含 [invalid regex 的文本")


class TestRuleEngine:
    """RuleEngine 测试"""

    @pytest.fixture
    def engine(self, tmp_path):
        """创建使用临时文件的 RuleEngine"""
        rules_file = tmp_path / "test_rules.json"
        return RuleEngine(rules_file=rules_file)

    def test_default_rules_loaded(self, engine):
        """内置规则应自动加载"""
        assert len(engine.rules) >= 6
        assert "alert_通用警告" in engine.rules
        assert "confirm_离开确认" in engine.rules

    def test_check_block_action(self, engine):
        """测试 block 类型规则"""
        action, name = engine.check("确定要离开此页面？")
        assert action == "block"
        # 可能匹配 alert_通用警告 或 confirm_离开确认
        assert name in ("alert_通用警告", "confirm_离开确认")

    def test_check_log_action(self, engine):
        """测试 log 类型规则"""
        action, name = engine.check("report abnormal activity detected")
        assert action == "log"
        assert name == "console_异常上报"

    def test_check_no_match(self, engine):
        """不匹配任何规则"""
        action, name = engine.check("正常操作，无异常")
        assert action is None
        assert name is None

    def test_add_rule(self, engine):
        """添加新规则"""
        new_rule = BlockingRule(
            name="test_new",
            pattern=r"test_pattern",
            category="dialog",
            action="block",
            created_at="2026-01-01T00:00:00",
        )
        engine.add_rule(new_rule)
        assert "test_new" in engine.rules
        action, name = engine.check("test_pattern")
        assert action == "block"
        assert name == "test_new"

    def test_persistence(self, tmp_path):
        """测试规则持久化"""
        rules_file = tmp_path / "persist_rules.json"
        engine1 = RuleEngine(rules_file=rules_file)

        new_rule = BlockingRule(
            name="persist_test",
            pattern=r"persist_pattern",
            category="console",
            action="block",
            created_at="2026-01-01T00:00:00",
        )
        engine1.add_rule(new_rule)

        # 重新加载
        engine2 = RuleEngine(rules_file=rules_file)
        assert "persist_test" in engine2.rules
        action, _ = engine2.check("persist_pattern")
        assert action == "block"

    def test_learn_from_content(self, engine):
        """测试自动学习"""
        rule = engine.learn_from_content(
            "警告：您已离开页面，请重新登录",
            event_type="dom",
            block_action="block",
        )
        assert rule is not None
        assert rule.name.startswith("learned_")
        assert rule.category == "dom"

    def test_learn_duplicate(self, engine):
        """重复内容不应生成重复规则"""
        content = "重复测试内容"
        rule1 = engine.learn_from_content(content, "dialog", "block")
        rule2 = engine.learn_from_content(content, "dialog", "block")
        assert rule1 is not None
        assert rule2 is None

    def test_get_summary(self, engine):
        """测试规则摘要"""
        summary = engine.get_summary()
        assert isinstance(summary, dict)
        assert "dialog" in summary
        assert "console" in summary
        assert "dom" in summary


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
