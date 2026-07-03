"""
StealthBrowser.__init__ 单元测试
覆盖：默认初始化、config 传入、kwargs 覆盖、无效 kwargs 忽略
"""
from __future__ import annotations

import pytest

from config import BrowserConfig
from core.browser import StealthBrowser


class TestStealthBrowserInit:
    """测试 StealthBrowser 构造函数的初始化行为"""

    def test_default_initialization(self) -> None:
        """无参数初始化时应使用默认 BrowserConfig"""
        browser = StealthBrowser()

        assert browser._cfg is not None
        assert isinstance(browser._cfg, BrowserConfig)
        assert browser.headless == BrowserConfig.headless
        assert browser.slow_mo == BrowserConfig.slow_mo
        assert browser.user_data_dir == BrowserConfig.user_data_dir
        assert browser.proxy == BrowserConfig.proxy

    def test_initialization_with_custom_config(self) -> None:
        """传入自定义 BrowserConfig 时应使用传入的配置"""
        cfg = BrowserConfig(
            headless=True,
            slow_mo=200,
            user_data_dir="/tmp/test_profile",
            proxy={"server": "http://127.0.0.1:8080"},
        )
        browser = StealthBrowser(config=cfg)

        assert browser._cfg is cfg
        assert browser.headless is True
        assert browser.slow_mo == 200
        assert browser.user_data_dir == "/tmp/test_profile"
        assert browser.proxy == {"server": "http://127.0.0.1:8080"}

    def test_kwargs_override_config(self) -> None:
        """kwargs 中存在的属性应覆盖 config 中的默认值"""
        browser = StealthBrowser(
            headless=True,
            slow_mo=500,
            user_data_dir="/tmp/kwargs_profile",
            proxy={"server": "http://127.0.0.1:9999"},
        )

        assert browser.headless is True
        assert browser.slow_mo == 500
        assert browser.user_data_dir == "/tmp/kwargs_profile"
        assert browser.proxy == {"server": "http://127.0.0.1:9999"}
        # 确保底层 config 也被覆盖
        assert browser._cfg.headless is True
        assert browser._cfg.slow_mo == 500

    def test_kwargs_override_provided_config(self) -> None:
        """kwargs 应覆盖显式传入的 config 属性"""
        cfg = BrowserConfig(headless=False, slow_mo=100)
        browser = StealthBrowser(config=cfg, headless=True, slow_mo=300)

        assert browser._cfg is cfg
        assert browser.headless is True
        assert browser.slow_mo == 300

    def test_invalid_kwargs_are_ignored(self) -> None:
        """kwargs 中 BrowserConfig 不存在的属性应被忽略，不报错"""
        browser = StealthBrowser(nonexistent_attr="should_be_ignored", headless=True)

        assert browser.headless is True
        assert not hasattr(browser, "nonexistent_attr")
        assert not hasattr(browser._cfg, "nonexistent_attr")

    def test_runtime_state_defaults(self) -> None:
        """运行时状态属性应初始化为默认值"""
        browser = StealthBrowser()

        assert browser._pw is None
        assert browser.browser is None
        assert browser.context is None
        assert browser.page is None
        assert browser.console_logs == []
        assert browser._running is False

    def test_config_and_kwargs_combined(self) -> None:
        """config 与 kwargs 组合时只覆盖 kwargs 中指定的字段"""
        cfg = BrowserConfig(
            headless=False,
            slow_mo=100,
            user_data_dir="/from/config",
            viewport_width=1920,
        )
        browser = StealthBrowser(config=cfg, headless=True)

        # kwargs 覆盖的字段
        assert browser.headless is True
        # config 中其他字段保持不变
        assert browser.slow_mo == 100
        assert browser._cfg.user_data_dir == "/from/config"
        assert browser._cfg.viewport_width == 1920
