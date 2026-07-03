"""
launch/launchers.py - 启动逻辑模块
============================================================
从 launcher.py / monitor_launcher.py 中提取的公共启动逻辑。
包含：纯净启动、监控启动、验证启动、诊断启动。
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any, Optional

from core.browser import StealthBrowser
from core.monitor import MonitorEngine, create_monitor
from core.recorder import ActionRecorder, get_record_script
from config import AppConfig, BrowserConfig

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# 诊断器
# ═══════════════════════════════════════════════════════════════════════════════


async def diagnose_assignments(browser: StealthBrowser) -> dict[str, Any]:
    """诊断 Assignments 列表页的 Submit 按钮问题"""
    if not browser.page:
        return {"error": "页面未初始化"}

    page = browser.page

    print("\n" + "=" * 60)
    print("  [DIAGNOSE] Assignments List Page")
    print("=" * 60)

    # 1. 当前 URL
    print(f"\n[*] Current page: {page.url}")

    # 2. 检查所有 frames
    print("\n=== All Frames ===")
    frame_list: list[dict[str, Any]] = []
    for i, f in enumerate(page.frames):
        name = getattr(f, "name", "unnamed") or "unnamed"
        f_url = f.url or "no url"
        print(f"  Frame {i}: name='{name}', url={f_url[:80]}...")
        frame_list.append({"index": i, "name": name, "url": f_url})

    # 3. 查找按钮
    print("\n=== Buttons in Each Frame ===")
    buttons_info: list[dict[str, Any]] = []

    # 主文档按钮
    main_btns = await page.query_selector_all(
        'input[type="button"], input[type="submit"], button'
    )
    print(f"\n  [main document] Found {len(main_btns)} buttons:")
    for btn in main_btns:
        try:
            value = (await btn.get_attribute("value")) or ""
            class_name = (await btn.get_attribute("class")) or ""
            onclick = (await btn.get_attribute("onclick")) or ""
            visible = await btn.is_visible()
            print(
                f"    - value='{value}' class='{class_name}' visible={visible}"
            )
            if onclick:
                print(f"      onclick: {onclick[:80]}")
            buttons_info.append({
                "frame": "main",
                "value": value,
                "className": class_name,
                "onclick": onclick,
                "visible": visible,
            })
        except Exception as exc:
            logger.debug("按钮检查失败: %s", exc)

    # 子 frames 中的按钮
    for f in page.frames:
        name = getattr(f, "name", "unnamed") or "unnamed"
        if name == "main" or name == page.main_frame.name:
            continue
        try:
            frame_btns = await f.query_selector_all(
                'input[type="button"], input[type="submit"], button'
            )
            print(f"\n  [{name}] Found {len(frame_btns)} buttons:")
            for btn in frame_btns:
                try:
                    value = (await btn.get_attribute("value")) or ""
                    class_name = (await btn.get_attribute("class")) or ""
                    onclick = (await btn.get_attribute("onclick")) or ""
                    visible = await btn.is_visible()
                    print(
                        f"    - value='{value}' class='{class_name}' visible={visible}"
                    )
                    if onclick:
                        print(f"      onclick: {onclick[:80]}")
                    buttons_info.append({
                        "frame": name,
                        "value": value,
                        "className": class_name,
                        "onclick": onclick,
                        "visible": visible,
                    })
                except Exception as exc:
                    logger.debug("子 frame 按钮检查失败: %s", exc)
        except Exception as exc:
            logger.debug("无法访问 frame [%s]: %s", name, exc)

    # 4. 检查 navigator.webdriver
    print("\n=== navigator.webdriver Status ===")
    webdriver_results: list[dict[str, Any]] = []

    try:
        wd_main = await page.evaluate("navigator.webdriver")
        status = "OK" if not wd_main else "⚠️ PROBLEM"
        print(f"  [main] navigator.webdriver = {wd_main} ({status})")
        webdriver_results.append({"frame": "main", "webdriver": wd_main})
    except Exception as exc:
        logger.debug("webdriver 检查失败 [main]: %s", exc)

    for f in page.frames:
        name = getattr(f, "name", "unnamed") or "unnamed"
        if name == page.main_frame.name:
            continue
        try:
            wd = await f.evaluate("navigator.webdriver")
            status = "OK" if not wd else "⚠️ PROBLEM"
            print(f"  [{name}] navigator.webdriver = {wd} ({status})")
            webdriver_results.append({"frame": name, "webdriver": wd})
        except Exception as exc:
            logger.debug("webdriver 检查失败 [%s]: %s", name, exc)
            webdriver_results.append({"frame": name, "error": str(exc)})

    # 5. Submit 按钮汇总
    print("\n=== Submit Button Summary ===")
    submit_btns = [
        b
        for b in buttons_info
        if "submit" in (b.get("value", "") + b.get("className", "")).lower()
    ]
    print(f"  Total Submit buttons found: {len(submit_btns)}")
    for sb in submit_btns:
        print(
            f"    [{sb['frame']}] value='{sb['value']}' "
            f"class='{sb['className']}' visible={sb['visible']}"
        )

    # 6. 截图
    await browser.screenshot("diagnose_assignments.png", full_page=True)
    print("\n[*] Screenshot saved: diagnose_assignments.png")

    # 7. 结论
    print("\n" + "=" * 60)
    if len(buttons_info) == 0:
        print("  WARNING: No buttons found!")
        print("  Possible reasons:")
        print("    1. Page still loading (wait 2-3 seconds)")
        print("    2. Login expired (re-login needed)")
        print("    3. Wrong URL (should be studentassign.jsp)")
    else:
        if submit_btns:
            print(f"  OK: Found {len(submit_btns)} Submit button(s)")
            for sb in submit_btns:
                if not sb["visible"]:
                    print(
                        f"    BUT: [{sb['frame']}] Submit button exists but is INVISIBLE!"
                    )
        else:
            print("  PROBLEM: No Submit buttons found, but other buttons exist")
            print("  This means the page knows it's a bot (navigator.webdriver=true)")
    print("=" * 60)

    # 保存结果
    result = {
        "url": page.url,
        "frames": frame_list,
        "buttons": buttons_info,
        "webdriver": webdriver_results,
        "submit_count": len(submit_btns),
        "submit_buttons": submit_btns,
    }
    with open("diagnose_result.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print("[*] Results saved: diagnose_result.json")

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 启动模式
# ═══════════════════════════════════════════════════════════════════════════════


async def launch_clean(
    url: str, config: AppConfig | None = None
) -> None:
    """纯净模式：反检测浏览器，无监控"""
    cfg = config or AppConfig()
    logger.info("纯净模式启动: %s", url)

    async with StealthBrowser(config=cfg.browser) as browser:
        if url and url != "about:blank":
            if not url.startswith("http"):
                url = "https://" + url
            print(f"[*] 正在打开: {url}")
            ok = await browser.goto(url, wait_until="load", timeout=60000)
            if not ok:
                print("[!] 页面加载失败")
            else:
                print("[OK] 页面已加载")
                await asyncio.sleep(2)

        print("\n[OK] 浏览器就绪，请手动操控。")
        print("     关闭浏览器窗口退出。\n")
        await browser.wait_until_closed()

    print("[*] 浏览器已关闭")


async def launch_verify(
    url: str, config: AppConfig | None = None
) -> None:
    """验证模式：打开后输出指纹检测报告"""
    cfg = config or AppConfig()
    logger.info("验证模式启动: %s", url)

    async with StealthBrowser(config=cfg.browser) as browser:
        if url and url != "about:blank":
            if not url.startswith("http"):
                url = "https://" + url
            await browser.goto(url)

        await asyncio.sleep(2)
        print("\n── 指纹检测报告 ──")
        await browser.fingerprint_report()
        await browser.screenshot("fp_verify.png")
        print("[*] 截图已保存: fp_verify.png")

        print("\n[OK] 浏览器就绪，请手动操控。")
        print("     关闭浏览器窗口退出。\n")
        await browser.wait_until_closed()

    print("[*] 浏览器已关闭")


async def launch_monitor(
    url: str, config: AppConfig | None = None, proxy: str = ""
) -> None:
    """监控模式：反检测 + MonitorEngine 实时监控"""
    cfg = config or AppConfig()
    if proxy:
        cfg.apply_proxy(proxy)

    logger.info("监控模式启动: %s", url)
    print(f"\n  ▶ 网址: {url}")
    print(f"  🟢 监控引擎: 已启用")

    sb_kwargs: dict[str, Any] = {"config": cfg.browser}
    if proxy:
        sb_kwargs["proxy"] = {
            "server": proxy if "://" in proxy else "http://" + proxy
        }

    async with StealthBrowser(**sb_kwargs) as browser:
        page = browser.page
        monitor = create_monitor(context_id="session")

        await monitor.attach_to_page(page)
        print(f"  📊 规则数: {len(monitor.rules.rules)}")
        print(f"  📁 日志文件: {monitor.log_file.name}")

        # 新标签页自动绑定
        def _on_new_page_monitor(new_page: Any) -> None:
            async def _attach() -> None:
                try:
                    await new_page.wait_for_load_state(
                        "domcontentloaded", timeout=15_000
                    )
                except Exception:
                    pass
                try:
                    await monitor.attach_to_page(new_page)
                    logger.info("[监控] 已绑定新标签页: %s", new_page.url[:80])
                except Exception as exc:
                    logger.warning("[监控] 新标签页绑定失败: %s", exc)

            asyncio.ensure_future(_attach())

        if browser.context:
            browser.context.on("page", _on_new_page_monitor)

        target = url if url.startswith("http") else "https://" + url
        await browser.goto(target)
        await asyncio.sleep(2)

        print(f"\n  {'─'*50}")
        print(f"  🟢 监控引擎运行中（关闭浏览器窗口停止）")
        print(f"  {'─'*50}")

        async def print_monitor_status() -> None:
            last_count = 0
            while True:
                await asyncio.sleep(5)
                total = len(monitor.events)
                new_events = monitor.events[last_count:]
                last_count = total
                if new_events:
                    blocked = sum(
                        1 for e in new_events if e.block_status == "blocked"
                    )
                    print(
                        f"\n  [+] 新增 {len(new_events)} 事件, {blocked} 已阻断"
                    )
                    for ev in new_events[-5:]:
                        icon = "🚫" if ev.block_status == "blocked" else "✅"
                        content = ev.content[:60]
                        print(f"      {icon} [{ev.event_type}] {content}")

        status_task = asyncio.ensure_future(print_monitor_status())
        try:
            await browser.wait_until_closed()
        except asyncio.CancelledError:
            pass
        finally:
            status_task.cancel()
            try:
                await status_task
            except (asyncio.CancelledError, Exception):
                pass
            monitor.detach()
            print(f"\n\n  {'─'*50}")
            print(f"  📊 监控报告")
            print(f"  {'─'*50}")
            print(monitor.generate_report())
            print(f"\n  📁 日志已保存: {monitor.log_file}")

    print("[*] 浏览器已关闭")


async def launch_record(
    url: str, config: AppConfig | None = None
) -> None:
    """录制模式：反检测 + 操作录制"""
    cfg = config or AppConfig()

    recorder = ActionRecorder()
    print(f"[REC] 录制模式已开启，操作将保存到: {recorder.output_file.resolve()}")
    print("[REC] 关闭浏览器后自动保存。\n")

    async with StealthBrowser(config=cfg.browser) as browser:
        # 注入录制脚本（通过 page.evaluate，避免 add_init_script 注入子 frame 导致异常）
        if browser.page:
            try:
                await browser.page.evaluate(get_record_script())
            except Exception as exc:
                logger.warning("录制脚本注入失败: %s", exc)

        # 绑定 console 监听
        handler = recorder.console_handler
        if browser.page:
            browser.page.on("console", handler)

        # 新标签页绑定（通过 StealthBrowser._on_new_page 自动处理 setup_page，
        # 但录制脚本需要手动重新注入）
        if browser.context:
            def _on_new_page_record(new_page: Any) -> None:
                new_page.on("console", handler)
                asyncio.ensure_future(_inject_record_script(new_page, recorder))

            async def _inject_record_script(page: Any, rec: ActionRecorder) -> None:
                try:
                    await page.wait_for_load_state("domcontentloaded", timeout=15_000)
                    await page.evaluate(get_record_script())
                    page.on("console", rec.console_handler)
                except Exception as exc:
                    logger.debug("新标签页录制脚本注入失败: %s", exc)

            browser.context.on("page", _on_new_page_record)

        if url and url != "about:blank":
            if not url.startswith("http"):
                url = "https://" + url
            print(f"[*] 正在打开: {url}")
            ok = await browser.goto(url, wait_until="load", timeout=60000)
            if not ok:
                print("[!] 页面加载失败")
            else:
                print("[OK] 页面已加载")
                await asyncio.sleep(2)

        print("\n[OK] 浏览器就绪，请手动操控。")
        print("[REC] 正在录制中... 关闭窗口后保存记录。")
        print("     关闭浏览器窗口退出。\n")

        try:
            await browser.wait_until_closed()
        except KeyboardInterrupt:
            pass
        finally:
            if recorder.records:
                recorder.save()

    print("[*] 浏览器已关闭")


async def launch_diagnose(
    url: str = "", config: AppConfig | None = None
) -> None:
    """诊断模式：手动操作后诊断 Submit 按钮"""
    cfg = config or AppConfig()

    async with StealthBrowser(config=cfg.browser) as browser:
        if url and url != "about:blank":
            if not url.startswith("http"):
                url = "https://" + url
            print(f"[*] 正在打开: {url}")
            await browser.goto(url)
        else:
            await browser.goto("about:blank")

        print("\n" + "=" * 60)
        print("  [DIAGNOSE MODE] 请在浏览器中操作...")
        print("=" * 60)
        print("  1. 在浏览器里导航到目标页面")
        print("  2. 登录账号")
        print("  3. 点击目标功能")
        print("  4. 等页面完全加载（2-3秒）")
        print("  5. 回到此窗口等待 90 秒倒计时结束")
        print("=" * 60)

        for i in range(90, 0, -10):
            await asyncio.sleep(10)
            remaining = max(0, i - 10)
            print(f"  [{remaining}s remaining...] 请确认已到目标页面")

        print("\n[*] 开始诊断...")
        await diagnose_assignments(browser)

        print("\n[OK] 浏览器就绪，关闭窗口退出。\n")
        await browser.wait_until_closed()

    print("[*] 浏览器已关闭")
