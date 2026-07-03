"""
core/recorder.py - 操作录制模块
============================================================
从 launcher.py 中提取的独立录制功能。
监听用户的 click/input/navigate，保存为 JSON。
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

# ── 录制注入脚本（从独立文件加载）──────────────────────────────────────────

def get_record_script() -> str:
    """获取录制脚本（从 core/js/recorder.js 加载）"""
    from core.browser import _load_js
    return _load_js("recorder.js")


class ActionRecorder:
    """操作录制器：注入监听脚本，收集用户操作记录"""

    def __init__(self, output_file: Path | None = None) -> None:
        self.records: list[dict[str, Any]] = []
        self.output_file: Path = output_file or Path("record_操作记录.json")
        self._on_console_callback: Callable[[Any], None] | None = None

    def _make_console_handler(self) -> Callable[[Any], None]:
        """创建 console 消息处理器"""

        def _on_console(msg: Any) -> None:
            text: str = getattr(msg, "text", "")
            if not text.startswith("__RECORD__:"):
                return
            try:
                data: dict[str, Any] = json.loads(text[len("__RECORD__:"):])
                self.records.append(data)
                action = data.get("action", "?")
                if action == "click":
                    logger.info(
                        "  [REC] 点击  %s  \"%s\"",
                        data.get("selector", ""),
                        data.get("text", ""),
                    )
                elif action == "input":
                    logger.info(
                        "  [REC] 输入  %s  = %s",
                        data.get("selector", ""),
                        data.get("value", ""),
                    )
                elif action == "navigate":
                    logger.info("  [REC] 跳转  %s", data.get("url", ""))
                elif action == "pageload":
                    logger.info(
                        "  [REC] 加载  %s  [%s]",
                        data.get("url", ""),
                        data.get("title", ""),
                    )
            except Exception:
                pass

        self._on_console_callback = _on_console
        return _on_console

    def save(self) -> Path:
        """保存录制记录到文件"""
        self.output_file.write_text(
            json.dumps(self.records, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info(
            "操作记录已保存: %s (共 %d 条)",
            self.output_file.resolve(),
            len(self.records),
        )
        return self.output_file

    @property
    def console_handler(self) -> Callable[[Any], None]:
        """获取 console 消息处理器（用于绑定到 page.on('console', ...)）"""
        if self._on_console_callback is None:
            self._make_console_handler()
        return self._on_console_callback  # type: ignore[return-value]
