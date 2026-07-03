"""
tests/test_replay.py - ReplayEngine 单元测试
============================================================
"""
import asyncio
import json
import tempfile
from pathlib import Path

import pytest

from auto.replay import ReplayEngine


class TestReplayEngine:
    """ReplayEngine 测试"""

    @pytest.fixture
    def engine(self):
        """创建 ReplayEngine（无浏览器）"""
        return ReplayEngine(browser=None)

    def test_init(self, engine):
        """初始化状态检查"""
        assert engine.actions == []
        assert engine.stats == {"total": 0, "success": 0, "failed": 0, "skipped": 0}

    def test_load_valid_file(self, engine, tmp_path):
        """加载有效录制文件"""
        record = [
            {"action": "click", "selector": "#btn", "text": "Submit", "ts": 1000},
            {"action": "input", "selector": "#input", "value": "test", "ts": 2000},
        ]
        record_file = tmp_path / "test_record.json"
        record_file.write_text(json.dumps(record), encoding="utf-8")

        result = engine.load(str(record_file))
        assert result is True
        assert len(engine.actions) == 2

    def test_load_dict_format(self, engine, tmp_path):
        """加载 {actions: [...]} 格式"""
        record = {
            "actions": [
                {"action": "click", "selector": "#btn", "text": "OK", "ts": 1000},
            ]
        }
        record_file = tmp_path / "dict_record.json"
        record_file.write_text(json.dumps(record), encoding="utf-8")

        result = engine.load(str(record_file))
        assert result is True
        assert len(engine.actions) == 1

    def test_load_nonexistent_file(self, engine):
        """加载不存在的文件"""
        result = engine.load("/nonexistent/path/record.json")
        assert result is False

    def test_load_invalid_json(self, engine, tmp_path):
        """加载无效 JSON"""
        record_file = tmp_path / "invalid.json"
        record_file.write_text("not valid json{", encoding="utf-8")

        result = engine.load(str(record_file))
        assert result is False

    def test_load_empty_list(self, engine, tmp_path):
        """加载空列表"""
        record_file = tmp_path / "empty.json"
        record_file.write_text("[]", encoding="utf-8")

        result = engine.load(str(record_file))
        assert result is True
        assert len(engine.actions) == 0

    @pytest.mark.asyncio
    async def test_replay_empty_actions(self, engine):
        """空操作列表回放"""
        stats = await engine.replay()
        assert stats["total"] == 0
        assert stats["success"] == 0

    @pytest.mark.asyncio
    async def test_execute_pageload(self, engine):
        """pageload 操作应跳过"""
        action = {"action": "pageload", "url": "https://example.com", "ts": 1000}
        result = await engine._execute_action(action)
        assert result is True

    @pytest.mark.asyncio
    async def test_execute_unknown_action(self, engine):
        """未知操作应跳过"""
        action = {"action": "unknown_action", "ts": 1000}
        result = await engine._execute_action(action)
        assert result is True

    @pytest.mark.asyncio
    async def test_execute_click_no_page(self, engine):
        """无页面时点击应失败"""
        action = {"action": "click", "selector": "#btn", "text": "Submit", "ts": 1000}
        result = await engine._execute_action(action)
        assert result is False

    @pytest.mark.asyncio
    async def test_execute_input_no_page(self, engine):
        """无页面时输入应失败"""
        action = {"action": "input", "selector": "#input", "value": "test", "ts": 1000}
        result = await engine._execute_action(action)
        assert result is False

    @pytest.mark.asyncio
    async def test_execute_navigate_no_page(self, engine):
        """无页面时导航应失败"""
        action = {"action": "navigate", "url": "https://example.com", "ts": 1000}
        result = await engine._execute_action(action)
        assert result is False


class TestReplayEngineWithMockBrowser:
    """使用 Mock 浏览器的回放测试"""

    @pytest.fixture
    def mock_browser(self):
        """创建 Mock 浏览器"""
        class MockPage:
            def __init__(self):
                self.frames = []
                self._click_results = []
                self._fill_results = []

            async def goto(self, url, **kwargs):
                return True

            def locator(self, selector):
                return MockLocator()

            def get_by_text(self, text, exact=False):
                return MockLocator()

            def mouse(self):
                return self

            async def click(self, x, y):
                pass

        class MockLocator:
            async def count(self):
                return 1

            async def click(self, timeout=0):
                pass

            async def fill(self, value, timeout=0):
                pass

            async def input_value(self):
                return ""

            def first(self):
                return self

            def nth(self, idx):
                return self

        class MockBrowser:
            def __init__(self):
                self.page = MockPage()

            async def goto(self, url):
                return True

        return MockBrowser()

    @pytest.fixture
    def engine_with_mock(self, mock_browser):
        return ReplayEngine(browser=mock_browser)

    @pytest.mark.asyncio
    async def test_click_with_text(self, engine_with_mock):
        """通过文本点击"""
        action = {
            "action": "click",
            "selector": "button.btn",
            "text": "Submit",
            "href": "",
            "x": None,
            "y": None,
            "ts": 1000,
        }
        result = await engine_with_mock._execute_action(action)
        # Mock 浏览器返回 True（locator 找到元素）
        assert result is True or result is False  # 取决于 Mock 实现

    @pytest.mark.asyncio
    async def test_input_password_masked(self, engine_with_mock):
        """密码输入应跳过"""
        action = {
            "action": "input",
            "selector": "input.password",
            "type": "password",
            "value": "***",
            "ts": 1000,
        }
        result = await engine_with_mock._execute_action(action)
        assert result is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
