"""
tests/test_recorder.py - ActionRecorder 单元测试
============================================================
"""
import json
import tempfile
from pathlib import Path

import pytest

from core.recorder import ActionRecorder, get_record_script


class TestActionRecorder:
    """ActionRecorder 测试"""

    @pytest.fixture
    def recorder(self, tmp_path):
        """创建使用临时文件的 ActionRecorder"""
        output_file = tmp_path / "test_record.json"
        return ActionRecorder(output_file=output_file)

    def test_init(self, recorder):
        """初始化状态检查"""
        assert recorder.records == []
        assert recorder.output_file.exists() is False

    def test_save(self, recorder):
        """测试保存功能"""
        recorder.records = [
            {"action": "click", "selector": "#btn", "text": "Submit", "ts": 1000},
            {"action": "input", "selector": "#input", "value": "test", "ts": 2000},
        ]
        result = recorder.save()
        assert result.exists()

        data = json.loads(result.read_text(encoding="utf-8"))
        assert len(data) == 2
        assert data[0]["action"] == "click"
        assert data[1]["action"] == "input"

    def test_save_empty(self, recorder):
        """空记录保存"""
        result = recorder.save()
        assert result.exists()
        data = json.loads(result.read_text(encoding="utf-8"))
        assert data == []

    def test_console_handler(self, recorder):
        """测试 console 消息处理器"""
        handler = recorder.console_handler

        # 模拟 __RECORD__ 消息
        class MockMsg:
            def __init__(self, text):
                self.text = text

        msg = MockMsg('__RECORD__:{"action":"click","selector":"#test","text":"Click me","ts":12345}')
        handler(msg)

        assert len(recorder.records) == 1
        assert recorder.records[0]["action"] == "click"
        assert recorder.records[0]["selector"] == "#test"

    def test_console_handler_non_record(self, recorder):
        """非 __RECORD__ 消息应被忽略"""
        handler = recorder.console_handler

        class MockMsg:
            def __init__(self, text):
                self.text = text

        msg = MockMsg("普通 console 消息")
        handler(msg)
        assert len(recorder.records) == 0

    def test_console_handler_invalid_json(self, recorder):
        """无效 JSON 消息应被忽略"""
        handler = recorder.console_handler

        class MockMsg:
            def __init__(self, text):
                self.text = text

        msg = MockMsg("__RECORD__:invalid json{")
        handler(msg)
        assert len(recorder.records) == 0


class TestRecordScript:
    """录制脚本加载测试"""

    def test_get_record_script(self):
        """测试脚本加载"""
        try:
            script = get_record_script()
            assert isinstance(script, str)
            assert len(script) > 0
            assert "__recorder_injected__" in script
            assert "__RECORD__:" in script
        except ModuleNotFoundError:
            pytest.skip("playwright not installed")

    def test_script_is_valid_js(self):
        """脚本应包含基本的 JS 结构"""
        try:
            script = get_record_script()
            assert "function" in script or "=>" in script
            assert "addEventListener" in script
            assert "console.log" in script
        except ModuleNotFoundError:
            pytest.skip("playwright not installed")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
