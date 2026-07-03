"""
auto/replay.py - 操作回放引擎
============================================================
加载 ActionRecorder 录制的 JSON 操作记录，在 StealthBrowser 中逐条回放。

【功能】
  1. 加载 record_操作记录.json
  2. 按时间顺序回放 click / input / navigate 操作
  3. 自动处理 frameset 跨 frame 操作
  4. 动作间模拟人类延迟（可配置）
  5. 错误容错 + 重试机制
  6. 实时进度报告

【用法】
  from auto.replay import ReplayEngine
  engine = ReplayEngine(browser)
  await engine.replay("record_操作记录.json")
"""
from __future__ import annotations

import asyncio
import json
import logging
import secrets
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ReplayEngine:
    """操作回放引擎 —— 把录制的人类操作自动重放一遍。"""

    def __init__(
        self,
        browser: Any,  # StealthBrowser 实例（避免循环导入）
        *,
        min_delay: float = 0.3,
        max_delay: float = 1.5,
        click_timeout: int = 15_000,
        input_timeout: int = 10_000,
        max_retries: int = 3,
        stop_on_error: bool = False,
    ) -> None:
        """
        Args:
            browser:       已启动的 StealthBrowser 实例
            min_delay:     动作间最小延迟（秒）
            max_delay:     动作间最大延迟（秒）
            click_timeout: 点击操作超时（毫秒）
            input_timeout: 输入操作超时（毫秒）
            max_retries:   失败重试次数
            stop_on_error: 出错是否立即停止
        """
        self.browser = browser
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.click_timeout = click_timeout
        self.input_timeout = input_timeout
        self.max_retries = max_retries
        self.stop_on_error = stop_on_error

        self.actions: List[Dict[str, Any]] = []
        self.stats: Dict[str, int] = {"total": 0, "success": 0, "failed": 0, "skipped": 0}

    # ── 加载 ────────────────────────────────────────────────────────────────

    def load(self, record_path: str) -> bool:
        """加载录制文件。

        Args:
            record_path: JSON 录制文件路径

        Returns:
            True 表示加载成功
        """
        path = Path(record_path)
        if not path.exists():
            logger.error("录制文件不存在: %s", path)
            return False

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                self.actions = data
            elif isinstance(data, dict):
                # 可能是 { "actions": [...] } 格式
                self.actions = data.get("actions", [])
            else:
                logger.error("无法识别的录制格式")
                return False

            logger.info("已加载 %d 条操作记录", len(self.actions))
            return True
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("读取录制文件失败: %s", exc)
            return False

    # ── 回放 ────────────────────────────────────────────────────────────────

    async def replay(self, record_path: Optional[str] = None) -> Dict[str, int]:
        """执行完整回放。

        Args:
            record_path: 录制文件路径（若不传则使用 self.load() 已加载的数据）

        Returns:
            回放统计: {total, success, failed, skipped}
        """
        if record_path:
            if not self.load(record_path):
                return self.stats

        if not self.actions:
            logger.warning("没有可回放的操作")
            return self.stats

        self.stats = {"total": len(self.actions), "success": 0, "failed": 0, "skipped": 0}

        print(f"\n── 开始回放 {len(self.actions)} 条操作 ──")
        start_time = time.time()

        for i, action in enumerate(self.actions):
            action_type = action.get("action", "unknown")
            print(f"  [{i+1}/{len(self.actions)}] {action_type}: ", end="", flush=True)

            success = await self._execute_action(action)

            if success:
                self.stats["success"] += 1
                print("✅")
            else:
                self.stats["failed"] += 1
                print("❌")
                if self.stop_on_error:
                    logger.warning("stop_on_error=True，停止回放")
                    break

            # 动作间延迟（模拟人类节奏）
            if i < len(self.actions) - 1:
                delay = self.min_delay + secrets.randbelow(
                    int((self.max_delay - self.min_delay) * 1000)
                ) / 1000
                await asyncio.sleep(delay)

        elapsed = time.time() - start_time
        print(f"\n── 回放完成: {self.stats['success']}/{self.stats['total']} 成功"
              f" ({elapsed:.1f}s) ──")

        return self.stats

    async def _execute_action(self, action: Dict[str, Any]) -> bool:
        """执行单条操作，失败自动重试。"""
        action_type = action.get("action", "")

        for attempt in range(self.max_retries + 1):
            try:
                if action_type == "click":
                    return await self._do_click(action)
                elif action_type in ("input", "change"):
                    return await self._do_input(action)
                elif action_type == "navigate":
                    return await self._do_navigate(action)
                elif action_type == "pageload":
                    return True  # pageload 不需要执行，跳过
                else:
                    return True  # 未知类型跳过

            except Exception as exc:
                if attempt < self.max_retries:
                    logger.debug("操作失败，重试 %d/%d: %s", attempt + 1, self.max_retries, exc)
                    await asyncio.sleep(0.5 * (attempt + 1))
                else:
                    logger.warning("操作失败（已重试 %d 次）: %s", self.max_retries, exc)
                    return False
        return False

    # ── 具体操作实现 ───────────────────────────────────────────────────────

    async def _do_click(self, action: Dict[str, Any]) -> bool:
        """回放点击操作 —— 在 frameset 中智能定位元素。"""
        selector = action.get("selector", "")
        tag = action.get("tag", "").lower()
        text = action.get("text", "")
        href = action.get("href", "")
        x = action.get("x")
        y = action.get("y")

        page = self.browser.page
        if not page:
            logger.warning("页面未初始化")
            return False

        # 策略1: 用 href 找链接
        if href:
            try:
                link = page.locator(f'a[href="{href}"]').first
                if await link.count() > 0:
                    await link.click(timeout=self.click_timeout)
                    return True
            except Exception:
                pass

        # 策略2: 用 text 找元素
        if text and len(text) < 100:
            try:
                el = page.get_by_text(text, exact=True).first
                if await el.count() > 0:
                    await el.click(timeout=self.click_timeout)
                    return True
            except Exception:
                pass

        # 策略3: 搜索所有 frame
        if text:
            for frame in page.frames:
                try:
                    el = frame.get_by_text(text, exact=True).first
                    if await el.count() > 0:
                        await el.click(timeout=self.click_timeout)
                        return True
                except Exception:
                    continue

        # 策略4: 用 name 属性
        if selector and "name=" in selector:
            name_val = selector.split("name=")[-1].strip("'\" ")
            try:
                for frame in page.frames:
                    el = frame.locator(f'[name="{name_val}"]').first
                    if await el.count() > 0:
                        await el.click(timeout=self.click_timeout)
                        return True
            except Exception:
                pass

        # 策略5: 用坐标点击（最后手段）
        if x is not None and y is not None:
            try:
                await page.mouse.click(x, y)
                return True
            except Exception:
                pass

        # 策略6: 用 selector 尝试
        if selector:
            try:
                el = page.locator(selector).first
                if await el.count() > 0:
                    await el.click(timeout=self.click_timeout)
                    return True
            except Exception:
                pass
            # 也尝试在 frame 中找
            for frame in page.frames:
                try:
                    el = frame.locator(selector).first
                    if await el.count() > 0:
                        await el.click(timeout=self.click_timeout)
                        return True
                except Exception:
                    continue

        logger.warning("无法定位点击目标: text=%r, href=%r, selector=%r", text, href, selector)
        return False

    async def _do_input(self, action: Dict[str, Any]) -> bool:
        """回放输入操作。"""
        selector = action.get("selector", "")
        tag = action.get("tag", "").lower()
        input_type = action.get("type", "text")
        value = action.get("value", "")

        if value == "***":
            logger.debug("跳过密码回放（密码被屏蔽）")
            return True

        page = self.browser.page
        if not page:
            return False

        # 策略1: 用 selector
        if selector:
            try:
                el = page.locator(selector).first
                if await el.count() > 0:
                    await el.click(timeout=self.input_timeout)
                    await el.fill(value, timeout=self.input_timeout)
                    return True
            except Exception:
                pass

        # 策略2: 找最近的 input
        try:
            if input_type in ("text", "password", "email", "number"):
                inputs = page.locator(f'input[type="{input_type}"]')
                count = await inputs.count()
                if count > 0:
                    await inputs.first.click(timeout=self.input_timeout)
                    await inputs.first.fill(value, timeout=self.input_timeout)
                    return True
        except Exception:
            pass

        # 策略3: 全局搜索 input/textarea
        for frame in page.frames:
            try:
                inputs = frame.locator("input:visible, textarea:visible")
                count = await inputs.count()
                if count > 0:
                    # 找第一个空输入框
                    for idx in range(count):
                        el = inputs.nth(idx)
                        cur_val = await el.input_value()
                        if not cur_val or cur_val == "":
                            await el.fill(value, timeout=self.input_timeout)
                            return True
            except Exception:
                continue

        logger.warning("无法定位输入框: selector=%r", selector)
        return False

    async def _do_navigate(self, action: Dict[str, Any]) -> bool:
        """回放导航操作。"""
        url = action.get("url", "")
        if not url:
            return False

        return await self.browser.goto(url)


# ── 便捷函数 ────────────────────────────────────────────────────────────────


async def replay_record(browser: Any, record_path: str, **kwargs: Any) -> Dict[str, int]:
    """一键回放录制文件。

    Args:
        browser:     StealthBrowser 实例
        record_path: 录制 JSON 文件路径
        **kwargs:    传递给 ReplayEngine 的参数

    Returns:
        回放统计
    """
    engine = ReplayEngine(browser, **kwargs)
    return await engine.replay(record_path)


async def replay_actions(browser: Any, actions: List[Dict[str, Any]], **kwargs: Any) -> Dict[str, int]:
    """回放内存中的操作列表。

    Args:
        browser: StealthBrowser 实例
        actions: 操作记录列表
        **kwargs: 传递给 ReplayEngine 的参数

    Returns:
        回放统计
    """
    engine = ReplayEngine(browser, **kwargs)
    engine.actions = actions
    return await engine.replay()
