"""
core/browser.py - 反检测无头浏览器核心模块 (v2.0)
============================================================

【模块定位】
本模块是整个项目的底层基础设施——只负责创建一个"看起来像真人的浏览器"。
不包含任何业务逻辑，上层调用方自行实现具体操作。

【技术架构：三层防护体系】

  Layer 1 · 浏览器启动参数
  ├── 禁用 AutomationControlled 标志
  ├── 禁用自动化特征（--disable-dev-shm-usage, --no-sandbox）
  └── 设置平板级窗口尺寸

  Layer 2 · JS 指纹注入（注入到顶层页面 JS 执行上下文）
  └── 顶层页面（通过 page.evaluate）：
      └── get_stealth_script()：指纹伪装（A1-A12）+ 框架阻断（B1-B2）

  Layer 3 · 网络层（可选，curl_cffi）
  └── TLS/JA3 指纹伪装，模拟真实 Chrome Client Hello

【子 frame 保护的核心问题】
  TeaLeaMan 使用 frameset 结构，作业列表在子 frame（studentassign.jsp）中渲染。
  子 frame 的 navigator.webdriver=true 会被 JSP 内联脚本检测到，导致 Submit 按钮被隐藏。
  解决方案：通过 page.evaluate 只在顶层页面注入反检测脚本，避免 add_init_script 注入子 frame
  产生 SyntaxError 或布局错误。

  ⚠ 为什么不把完整脚本用 add_init_script 注入子 frame？
     JSP 脚本以语句开头（如 if(...){...}），拼接 IIFE 会产生 SyntaxError，
     导致子页面 JS 失效。

【v2.0 改进】
  - 移除硬编码的 --disable-web-security，改为可配置选项（默认关闭）
  - 人类行为模拟使用 secrets 模块替代 random（密码学安全）
  - 完整的类型注解
  - 统一的 logging 体系
  - 更好的异常处理（不再静默吞错）
"""
from __future__ import annotations

import asyncio
import json
import logging
import secrets
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import BrowserConfig

logger = logging.getLogger(__name__)

# ── 浏览器引擎选择（优先 patchright > playwright）──────────────────────────────
PATCHRIGHT_AVAILABLE = False
try:
    from patchright.async_api import (  # type: ignore[import-untyped]
        async_playwright,
        Browser,
        BrowserContext,
        Page,
        Playwright,
    )
    PATCHRIGHT_AVAILABLE = True
    logger.info("patchright 加载成功（优先引擎）")
except ImportError:
    logger.warning("patchright 未安装，回退到标准 playwright")
    from playwright.async_api import (  # type: ignore[import-untyped]
        async_playwright,
        Browser,
        BrowserContext,
        Page,
        Playwright,
    )

# ── playwright-stealth（可选）──────────────────────────────────────────────────
STEALTH_AVAILABLE = False
_stealth_fn = None
try:
    # v2.0: 兼容 playwright-stealth 多版本 API
    from playwright_stealth import stealth_async as _stealth_fn  # type: ignore[import-untyped]
    STEALTH_AVAILABLE = True
    logger.info("playwright-stealth (async) 加载成功")
except ImportError:
    try:
        from playwright_stealth import stealth as _stealth_fn  # type: ignore[import-untyped]
        if callable(_stealth_fn):
            STEALTH_AVAILABLE = True
            logger.info("playwright-stealth 加载成功")
        else:
            logger.debug("playwright-stealth.stealth 不是可调用对象，跳过")
    except ImportError:
        logger.debug("playwright-stealth 未安装（可选）")

# ── curl_cffi（可选）───────────────────────────────────────────────────────────
CURL_CFFI_AVAILABLE = False
try:
    from curl_cffi import requests as _cffi_requests  # type: ignore[import-untyped]
    CURL_CFFI_AVAILABLE = True
    logger.info("curl-cffi 加载成功")
except ImportError:
    logger.debug("curl-cffi 未安装（可选）")


# ═══════════════════════════════════════════════════════════════════════════════
# 反检测 JS 注入脚本（从独立文件加载）
# ═══════════════════════════════════════════════════════════════════════════════

_JS_DIR = Path(__file__).parent / "js"

# 缓存加载的 JS 脚本
_js_cache: dict[str, str] = {}


def _load_js(filename: str) -> str:
    """加载 JS 文件（带缓存）"""
    if filename in _js_cache:
        return _js_cache[filename]
    js_path = _JS_DIR / filename
    if js_path.exists():
        content = js_path.read_text(encoding="utf-8")
        _js_cache[filename] = content
        return content
    # 文件不存在时返回空字符串
    logger.warning("JS 文件不存在: %s", js_path)
    return ""


def get_stealth_script() -> str:
    """获取反检测脚本"""
    return _load_js("stealth.js")

# ═══════════════════════════════════════════════════════════════════════════════
# 核心类：StealthBrowser
# ═══════════════════════════════════════════════════════════════════════════════


class StealthBrowser:
    """反检测浏览器（v2.0）

    提供一个经过全面指纹伪装的 Playwright 浏览器实例，
    供上层业务代码自由操控，不包含任何自动化业务逻辑。

    v2.0 改进：
      - --disable-web-security 改为可配置（默认关闭）
      - 人类行为模拟使用 secrets 模块
      - 完整的类型注解
      - 统一的 logging 体系

    快速示例:
        browser = StealthBrowser()
        await browser.start()
        await browser.goto("https://example.com")
        await browser.cleanup()
    """

    def __init__(self, config: Optional[BrowserConfig] = None, **kwargs: Any) -> None:
        """
        Args:
            config:  浏览器配置对象（优先级高于 kwargs）
            **kwargs: 可覆盖 config 中的字段
                headless, slow_mo, user_data_dir, proxy,
                disable_web_security, inject_full_stealth

        """
        cfg = config or BrowserConfig()

        # 允许通过 kwargs 覆盖
        for key, val in kwargs.items():
            if hasattr(cfg, key):
                setattr(cfg, key, val)

        self._cfg: BrowserConfig = cfg
        self.headless: bool = cfg.headless
        self.slow_mo: int = cfg.slow_mo
        self.user_data_dir: Optional[str] = cfg.user_data_dir
        self.proxy: Optional[Dict[str, str]] = cfg.proxy

        self._pw: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self._pages: List[Page] = []

        self.console_logs: List[Dict[str, Any]] = []
        self._running: bool = False

    @property
    def page(self) -> Optional[Page]:
        """获取当前活跃页面（最后打开的页面）"""
        return self._pages[-1] if self._pages else None

    @property
    def pages(self) -> List[Page]:
        """获取所有页面列表"""
        return list(self._pages)

    # ── 生命周期 ──────────────────────────────────────────────────────────

    async def start(self) -> bool:
        """启动浏览器并应用全套反检测配置。

        Returns:
            True 表示启动成功
        """
        try:
            logger.info("启动 Playwright...")
            self._pw = await async_playwright().start()

            # ── Layer 1: 浏览器进程启动参数 ────────────────────────────
            launch_args = self._cfg.launch_args
            self.browser = await self._pw.chromium.launch(
                headless=self._cfg.headless,
                slow_mo=self._cfg.slow_mo,
                args=launch_args,
            )
            logger.info("浏览器已启动 (headless=%s, web_security=%s)",
                         self._cfg.headless, not self._cfg.disable_web_security)

            # ── Layer 1: 浏览器上下文配置 ──────────────────────────────
            context_kwargs: Dict[str, Any] = dict(
                viewport={"width": self._cfg.viewport_width, "height": self._cfg.viewport_height},
                device_scale_factor=self._cfg.device_scale_factor,
                user_agent=self._cfg.user_agent,
                locale=self._cfg.locale,
                timezone_id=self._cfg.timezone_id,
                permissions=["geolocation"],
                geolocation=self._cfg.geolocation,
                extra_http_headers=self._cfg.extra_http_headers,
            )
            if self._cfg.proxy:
                context_kwargs["proxy"] = self._cfg.proxy

            self.context = await self.browser.new_context(**context_kwargs)
            logger.info("浏览器上下文已创建")

            # Context 级别 init script 已移除（add_init_script 会注入所有 frame，导致子 frame 异常）

            new_page = await self.context.new_page()
            self._pages.append(new_page)
            await new_page.set_viewport_size({
                "width": self._cfg.viewport_width,
                "height": self._cfg.viewport_height,
            })

            # 新标签页监听
            self.context.on("page", self._on_new_page)

            # 为初始页面注入反检测
            await self._setup_page(new_page)

            self._running = True
            logger.info("StealthBrowser 启动成功")
            self._print_status()
            return True

        except Exception as exc:
            logger.error("启动失败: %s", exc)
            await self._partial_cleanup()
            return False

    def _print_status(self) -> None:
        """打印启动状态报告"""
        engine = "patchright (最优)" if PATCHRIGHT_AVAILABLE else "playwright (标准)"
        lines = [
            "=" * 55,
            "  StealthBrowser 启动完成 (v2.0)",
            "=" * 55,
            f"  浏览器引擎:         {engine}",
            f"  playwright-stealth: {'OK' if STEALTH_AVAILABLE else '手动注入模式'}",
            f"  curl-cffi (TLS):    {'OK' if CURL_CFFI_AVAILABLE else '未安装（可选）'}",
            f"  Web 安全:           {'已启用' if not self._cfg.disable_web_security else '⚠️  已禁用'}",
            f"  完整反检测:         {'已启用' if self._cfg.inject_full_stealth else '已禁用'}",
            "=" * 55,
        ]
        print("\n" + "\n".join(lines) + "\n")

    def _on_console(self, msg: Any) -> None:
        """收集控制台消息"""
        self.console_logs.append({
            "type": getattr(msg, "type", "?"),
            "text": getattr(msg, "text", ""),
            "ts": time.time(),
        })

    async def _setup_page(self, page: Page) -> None:
        """为一个页面绑定对话框处理 + console 收集 + JS 注入。

        【注入层次】
          仅第1层：page.evaluate(get_stealth_script())  ← 仅顶层页面
          → A1-A12：Canvas 噪声、WebGL 伪装、AudioContext 扰动等
          → B1-B2：beforeunload 阻断、visibilitychange 静默
        """
        page.on("dialog", self._on_dialog)
        page.on("console", self._on_console)

        # 第1层已移除：add_init_script 不再使用

        # playwright-stealth（可选）
        if STEALTH_AVAILABLE and _stealth_fn is not None:
            try:
                await _stealth_fn(page)
                logger.debug("playwright-stealth 已应用")
            except Exception as exc:
                logger.warning("playwright-stealth 应用失败: %s", exc)

        # 第2-3层：顶层页面注入
        if self._cfg.inject_full_stealth:
            try:
                await page.evaluate(get_stealth_script())
                logger.debug("完整反检测脚本已注入")
            except Exception as exc:
                logger.warning("完整反检测脚本注入失败: %s", exc)

        # Viewport 自适应脚本已移除（会导致右侧 frame 宽度为 0%）

    def _on_new_page(self, new_page: Page) -> None:
        """Context 级别的新标签页监听"""
        logger.info("新标签页: %s", new_page.url or "(正在加载...)")
        self._pages.append(new_page)
        asyncio.ensure_future(self._init_new_page(new_page))

    async def _init_new_page(self, page: Page) -> None:
        """异步初始化新标签页"""
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=15_000)
            logger.info("新标签页已加载: %s", page.url)
        except Exception as exc:
            logger.debug("新标签页加载超时: %s", exc)
        try:
            await page.set_viewport_size({
                "width": self._cfg.viewport_width,
                "height": self._cfg.viewport_height,
            })
        except Exception as exc:
            logger.debug("设置 viewport 失败: %s", exc)
        await self._setup_page(page)

    async def _on_dialog(self, dialog: Any) -> None:
        """自动处理对话框"""
        dialog_type = getattr(dialog, "type", "?")
        dialog_message = getattr(dialog, "message", "")[:100]
        logger.info("对话框 [%s]: %s", dialog_type, dialog_message)
        try:
            if dialog_type == "prompt":
                # Playwright Dialog.default_value 是 str 属性，不是可调用对象
                default = getattr(dialog, "default_value", "") or ""
                await dialog.accept(default)
            elif dialog_type == "confirm":
                # 确认框默认点击"确定"；若业务需要取消可在此处扩展配置
                await dialog.accept()
            else:
                # alert / beforeunload 等只有单一确认按钮
                await dialog.accept()
        except Exception as exc:
            logger.warning("对话框处理失败: %s", exc)


    # ── 等待浏览器关闭 ───────────────────────────────────────────────────

    async def wait_until_closed(self) -> None:
        """阻塞直到浏览器的所有页面都被关闭"""
        try:
            closed = asyncio.Event()
            if self.context:
                self.context.on("close", lambda _=None: closed.set())
            if self.browser:
                self.browser.on("disconnected", lambda _=None: closed.set())
            await closed.wait()
        except asyncio.CancelledError:
            # 用户关闭窗口或 Ctrl+C → 正常退出，不报错
            pass
        except Exception as exc:
            logger.debug("wait_until_closed 异常: %s", exc)

    # ── 导航 ────────────────────────────────────────────────────────────

    async def goto(self, url: str, wait_until: str = "load", timeout: int = 60_000) -> bool:
        """导航到指定 URL。

        Returns:
            True 表示成功
        """
        if not self.page:
            logger.error("页面未初始化，请先调用 start()")
            return False
        try:
            await self.page.goto(url, wait_until=wait_until, timeout=timeout)
            # 随机延迟，模拟人类加载后停顿（使用 secrets 模块确保安全）
            await asyncio.sleep(secrets.randbelow(1500) / 1000 + 1.0)

            # 导航后重新注入完整反检测脚本（page.evaluate 是一次性的）
            await self._reapply_full_stealth()

            logger.info("已导航: %s", url)
            return True
        except Exception as exc:
            logger.error("导航失败 [%s]: %s", url, exc)
            return False

    async def _reapply_full_stealth(self) -> None:
        """重新注入完整反检测脚本（WebGL/Canvas/Audio/字体/时区等）。
        
        在 goto() 导航后调用，因为 page.evaluate() 是一次性的——
        页面跳转后旧注入会丢失。
        """
        if not self.page:
            return
        # playwright-stealth（可选，每次导航后重新应用）
        if STEALTH_AVAILABLE and _stealth_fn is not None:
            try:
                await _stealth_fn(self.page)
                logger.debug("playwright-stealth 已重新应用（导航后）")
            except Exception as exc:
                logger.debug("导航后 playwright-stealth 应用失败: %s", exc)
        if self._cfg.inject_full_stealth:
            try:
                await self.page.evaluate(get_stealth_script())
                logger.debug("完整反检测脚本已重新注入（导航后）")
            except Exception as exc:
                logger.warning("导航后完整反检测注入失败: %s", exc)
        # Viewport 自适应脚本已移除

    async def goto_file(self, path: str) -> bool:
        """加载本地文件"""
        abs_path = Path(path).absolute()
        return await self.goto(f"file:///{abs_path.as_posix()}")

    async def wait_for_load(self, timeout: int = 30_000) -> bool:
        """等待网络空闲"""
        if not self.page:
            return False
        try:
            await self.page.wait_for_load_state("networkidle", timeout=timeout)
            await asyncio.sleep(1.0)
            return True
        except Exception as exc:
            logger.warning("等待加载超时: %s", exc)
            return False

    # ── 人类行为模拟（使用 secrets 模块）─────────────────────────────────

    async def simulate_human_presence(self, duration: float = 5.0) -> None:
        """在页面上模拟自然的人类存在感（鼠标移动 + 滚动）。

        使用 secrets 模块生成密码学安全的随机数，比 random 更难被统计分析检测。

        Args:
            duration: 模拟持续时间（秒）
        """
        if not self.page:
            logger.warning("页面未初始化，无法模拟人类行为")
            return

        logger.info("模拟人类浏览行为，持续约 %.1fs ...", duration)
        deadline = time.time() + duration

        while time.time() < deadline:
            action = secrets.choice(["move", "move", "scroll"])  # secrets 模块

            if action == "move":
                x = secrets.randbelow(1500) + 200   # 200-1699
                y = secrets.randbelow(700) + 150    # 150-849
                steps = secrets.randbelow(18) + 8   # 8-25
                try:
                    await self.page.mouse.move(x, y, steps=steps)
                except Exception as exc:
                    logger.debug("鼠标移动失败: %s", exc)

            elif action == "scroll":
                delta = secrets.randbelow(800) - 400  # -400 ~ 399
                try:
                    await self.page.evaluate(f"window.scrollBy(0, {delta})")
                except Exception as exc:
                    logger.debug("滚动失败: %s", exc)

            await asyncio.sleep(secrets.randbelow(900) / 1000 + 0.3)  # 0.3-1.2s

        logger.info("人类行为模拟完成")

    # ── 指纹检测报告 ────────────────────────────────────────────────────

    async def fingerprint_report(self) -> Dict[str, Any]:
        """采集当前页面的指纹检测结果"""
        if not self.page:
            return {}

        # 确保反检测脚本已注入（防止直接调用时未注入）
        await self._reapply_full_stealth()

        result = await self.page.evaluate("""
            () => {
                const hasAudioCtx = !!(window.AudioContext || window.webkitAudioContext);

                const _canvasFP = (seed) => {
                    const c = document.createElement('canvas');
                    const ctx = c.getContext('2d');
                    ctx.font = '14px Arial';
                    ctx.fillStyle = '#f00';
                    ctx.fillRect(0, 0, 60, 20);
                    ctx.fillStyle = '#00f';
                    ctx.fillText('FP' + seed, 2, 14);
                    return c.toDataURL().slice(-20);
                };
                const fp1 = _canvasFP(1);
                const fp2 = _canvasFP(2);

                const _wgl = document.createElement('canvas').getContext('webgl');
                const ext = _wgl && _wgl.getExtension('WEBGL_debug_renderer_info');

                return {
                    webdriver:           navigator.webdriver,
                    plugins_count:       navigator.plugins.length,
                    languages:           navigator.languages,
                    platform:            navigator.platform,
                    has_chrome_object:   typeof window.chrome !== 'undefined',
                    canvas_fp_1:         fp1,
                    canvas_fp_2:         fp2,
                    canvas_fp_differs:   fp1 !== fp2,
                    webgl_vendor:        _wgl ? _wgl.getParameter(0x1F00) : null,
                    webgl_renderer:      _wgl ? _wgl.getParameter(0x1F01) : null,
                    webgl_unmasked_vendor:
                        (ext && _wgl) ? _wgl.getParameter(ext.UNMASKED_VENDOR_WEBGL) : null,
                    webgl_unmasked_renderer:
                        (ext && _wgl) ? _wgl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : null,
                    has_audio_context:   hasAudioCtx,
                    timezone_offset:     new Date().getTimezoneOffset(),
                    timezone_intl:       Intl.DateTimeFormat().resolvedOptions().timeZone,
                    screen_resolution:   `${screen.width}x${screen.height}`,
                    color_depth:         screen.colorDepth,
                    hardware_concurrency: navigator.hardwareConcurrency,
                    device_memory:       navigator.deviceMemory,
                    connection_type:     navigator.connection ? navigator.connection.effectiveType : null,
                };
            }
        """)
        self._print_fp_report(result)
        return result

    @staticmethod
    def _print_fp_report(r: Dict[str, Any]) -> None:
        """打印指纹检测报告"""

        def chk(val: Any, good: Any, label: str) -> None:
            if isinstance(good, (list, tuple, set)):
                ok = "✅" if val in good else "⚠️ "
            else:
                ok = "✅" if val == good else "⚠️ "
            print(f"  {ok} {label}: {val}")

        print("\n── 指纹检测报告 ──────────────────────────────────────")
        chk(r.get("webdriver"), (None, False), "webdriver")
        chk(r.get("plugins_count", 0) > 0, True, f"plugins ({r.get('plugins_count')})")
        chk(r.get("has_chrome_object"), True, "chrome 对象")
        chk(r.get("canvas_fp_differs"), True, "Canvas 指纹随机化")
        chk(r.get("webgl_unmasked_renderer"), "Intel Iris OpenGL Engine", "WebGL renderer")
        chk(r.get("timezone_intl"), "Asia/Shanghai", "时区")
        print(f"  ℹ️  平台: {r.get('platform')}")
        print(f"  ℹ️  分辨率: {r.get('screen_resolution')}")
        print(f"  ℹ️  硬件并发: {r.get('hardware_concurrency')}")
        print("─" * 52 + "\n")

    # ── 截图 / JS 执行 ──────────────────────────────────────────────────

    async def screenshot(self, path: str = "screenshot.png", full_page: bool = True) -> bool:
        """保存页面截图"""
        if not self.page:
            return False
        try:
            await self.page.screenshot(path=path, full_page=full_page)
            logger.info("截图已保存: %s", path)
            return True
        except Exception as exc:
            logger.error("截图失败: %s", exc)
            return False

    async def evaluate(self, script: str) -> Any:
        """在页面中执行 JavaScript 并返回结果"""
        if not self.page:
            return None
        try:
            return await self.page.evaluate(script)
        except Exception as exc:
            logger.error("JS 执行失败: %s", exc)
            return None

    async def get_html(self) -> str:
        """获取当前页面 HTML"""
        if not self.page:
            return ""
        try:
            return await self.page.content()
        except Exception as exc:
            logger.error("获取 HTML 失败: %s", exc)
            return ""

    # ── 资源清理 ────────────────────────────────────────────────────────

    async def _partial_cleanup(self) -> None:
        """部分清理（初始化失败时使用）"""
        # 关闭所有页面
        for p in self._pages:
            try:
                await p.close()
            except Exception as exc:
                logger.debug("清理页面失败: %s", exc)
        self._pages.clear()

        for obj, method in [
            (self.context, "close"),
            (self.browser, "close"),
            (self._pw, "stop"),
        ]:
            if obj:
                try:
                    await getattr(obj, method)()
                except Exception as exc:
                    logger.debug("清理 %s 失败: %s", method, exc)

    async def cleanup(self) -> None:
        """释放全部资源"""
        logger.info("释放浏览器资源...")
        await self._partial_cleanup()
        self._running = False
        logger.info("资源已释放")

    async def close_page(self, page: Page) -> None:
        """关闭指定页面"""
        if page in self._pages:
            self._pages.remove(page)
        try:
            await page.close()
        except Exception as exc:
            logger.debug("关闭页面失败: %s", exc)

    # ── 上下文管理器支持 ────────────────────────────────────────────────

    async def __aenter__(self) -> "StealthBrowser":
        await self.start()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.cleanup()


# ═══════════════════════════════════════════════════════════════════════════════
# TLS 指纹伪装（可选 Layer 3）
# ═══════════════════════════════════════════════════════════════════════════════


class TLSSession:
    """使用 curl_cffi 发起 HTTP 请求，模拟真实 Chrome 的 TLS/JA3 握手指纹。"""

    def __init__(self, impersonate: str = "chrome124") -> None:
        if not CURL_CFFI_AVAILABLE:
            raise ImportError("请先安装: pip install curl-cffi")
        self._session = _cffi_requests.Session(impersonate=impersonate)
        self.impersonate = impersonate
        logger.info("TLSSession 初始化: impersonate=%s", impersonate)

    def get(self, url: str, **kwargs: Any) -> Any:
        return self._session.get(url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> Any:
        return self._session.post(url, **kwargs)

    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> "TLSSession":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


# ═══════════════════════════════════════════════════════════════════════════════
# 快速验证入口
# ═══════════════════════════════════════════════════════════════════════════════


async def _verify() -> None:
    """快速验证：启动浏览器 → 输出指纹报告"""
    async with StealthBrowser(headless=False, slow_mo=30) as browser:
        await browser.goto("about:blank")
        await browser.fingerprint_report()
        await browser.screenshot("verify_stealth.png")
        print("验证截图已保存: verify_stealth.png")

        if CURL_CFFI_AVAILABLE:
            print("\n── TLS 指纹验证 ──────────────────────────────────────")
            with TLSSession("chrome124") as sess:
                try:
                    r = sess.get("https://httpbin.org/headers", timeout=10)
                    ua: str = r.json().get("headers", {}).get("User-Agent", "N/A")
                    print(f"  ✅ TLS 请求成功，UA: {ua}")
                except Exception as exc:
                    print(f"  ⚠️  TLS 请求失败: {exc}")

        print("\n浏览器窗口保持开启，按 Ctrl+C 关闭...")
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    asyncio.run(_verify())
