"""
config.py - 统一配置管理
============================================================
所有可调参数集中管理，支持环境变量覆盖。
"""
from __future__ import annotations
from pathlib import Path
from typing import Dict, Optional
from dataclasses import dataclass, field


@dataclass
class BrowserConfig:
    """StealthBrowser 配置"""

    # ── 显示设置 ──
    headless: bool = False
    slow_mo: int = 50
    viewport_width: int = 1280
    viewport_height: int = 900
    device_scale_factor: int = 1

    # ── 用户模拟 ──
    user_data_dir: Optional[str] = None
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
    locale: str = "zh-CN"
    timezone_id: str = "Asia/Shanghai"

    # ── 地理位置 ──
    geolocation: Dict[str, float] = field(default_factory=lambda: {
        "latitude": 31.2304,
        "longitude": 121.4737,
    })

    # ── HTTP 头 ──
    extra_http_headers: Dict[str, str] = field(default_factory=lambda: {
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Sec-CH-UA": '"Chromium";v="124", "Google Chrome";v="124"',
        "Sec-CH-UA-Mobile": "?0",
        "Sec-CH-UA-Platform": '"Windows"',
    })

    # ── 代理 ──
    proxy: Optional[Dict[str, str]] = None

    # ── 安全选项 ──
    # ⚠️ disable_web_security=False 是默认安全值
    # 仅在确需跨域 frame 加载时（如 TeaLeaMan 的 frameset 结构）才启用
    disable_web_security: bool = False

    # ── 反检测选项 ──
    # 是否在顶层页面注入完整反检测脚本（Canvas/WebGL/Audio 扰动等）
    inject_full_stealth: bool = True
    # 是否注入 viewport 自适应脚本（已禁用：会导致右侧 frame 宽度为 0%）
    inject_viewport_adapter: bool = False

    @property
    def launch_args(self) -> list[str]:
        """生成 Chromium 启动参数"""
        args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-infobars",
            f"--window-size={self.viewport_width},{self.viewport_height}",
            "--disable-features=IsolateOrigins,site-per-process",
            "--disable-site-isolation-trials",
            "--disable-gpu-sandbox",
            "--use-gl=desktop",
            "--allow-running-insecure-content",
        ]
        # ⚠️ 仅显式要求时才关闭 Web 安全
        if self.disable_web_security:
            args.append("--disable-web-security")
        return args


@dataclass
class MonitorConfig:
    """MonitorEngine 配置"""

    # ── 轮询设置 ──
    poll_interval_base: float = 0.5       # 基础轮询间隔（秒）
    poll_interval_max: float = 5.0        # 最大轮询间隔（秒）
    poll_backoff_factor: float = 1.5      # 无事件时退避因子
    poll_speedup_factor: float = 0.5      # 有事件时加速因子

    # ── 事件记录 ──
    log_dir: Path = Path(__file__).parent / "monitor_logs"
    max_events_in_memory: int = 10_000    # 内存中最大事件数

    # ── 自动学习 ──
    auto_learn: bool = True               # 是否从阻断事件中自动学习
    learn_keyword_min_len: int = 2        # 学习关键词最小长度


@dataclass
class AppConfig:
    """应用总配置"""

    browser: BrowserConfig = field(default_factory=BrowserConfig)
    monitor: MonitorConfig = field(default_factory=MonitorConfig)
    debug: bool = False

    def apply_headless(self) -> "AppConfig":
        self.browser.headless = True
        return self

    def apply_proxy(self, server: str) -> "AppConfig":
        self.browser.proxy = {"server": server}
        return self

    def enable_web_security_bypass(self) -> "AppConfig":
        self.browser.disable_web_security = True
        return self
