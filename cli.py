"""
cli.py - 统一命令行入口 (v2.0)
============================================================

【支持的运行模式】

  交互模式（无参数）:
    python cli.py
    → 显示菜单，选择模式

  命令行模式:
    python cli.py launch <URL>               # 纯净模式
    python cli.py monitor <URL>              # 监控模式
    python cli.py verify <URL>               # 验证模式
    python cli.py record <URL>               # 录制模式
    python cli.py diagnose [URL]             # 诊断模式
    python cli.py view-log                   # 查看最近日志
    python cli.py view-rules                 # 查看当前规则

  兼容旧版调用:
    python cli.py <URL> --mode monitor       # 兼容旧版参数
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from core.browser import StealthBrowser, CURL_CFFI_AVAILABLE, TLSSession
from core.monitor import create_monitor
from launch.launchers import (
    launch_clean,
    launch_monitor,
    launch_verify,
    launch_record,
    launch_diagnose,
)

# ── 日志配置 ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("cli")


# ═══════════════════════════════════════════════════════════════════════════════
# 查看工具
# ═══════════════════════════════════════════════════════════════════════════════


def view_recent_log() -> None:
    """查看最近一次监控日志"""
    log_dir = Path(__file__).parent / "monitor_logs"
    if not log_dir.exists():
        print("  [空] 暂无监控日志")
        return

    files = sorted(
        log_dir.glob("*.jsonl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not files:
        print("  [空] 暂无监控日志")
        return

    latest = files[0]
    print(f"\n  📄 最近日志: {latest.name}")
    print(f"  修改时间: {datetime.fromtimestamp(latest.stat().st_mtime)}")
    print(f"  {'─'*50}")

    events: list[dict] = []
    try:
        for line in latest.read_text(encoding="utf-8").splitlines():
            if line.strip():
                events.append(json.loads(line))
    except Exception as exc:
        print(f"  读取错误: {exc}")
        return

    if not events:
        print("  无事件记录")
        return

    type_counts = Counter(e.get("event_type", e.get("type", "?")) for e in events)
    blocked_counts = Counter(
        e.get("block_status", e.get("action", "?")) for e in events
    )

    print(f"\n  事件总数: {len(events)}")
    print(f"\n  事件类型分布:")
    for t, c in type_counts.most_common():
        print(f"    [{t}] {c} 次")

    print(f"\n  阻断状态:")
    for a, c in blocked_counts.most_common():
        label = (
            "✅ 允许"
            if a in ("allowed", "log")
            else "🚫 阻断"
            if a == "blocked"
            else f"⚠️ {a}"
        )
        print(f"    {label} {c} 次")

    print(f"\n  最近10条事件:")
    print(f"  {'─'*50}")
    for ev in events[-10:]:
        ts = (ev.get("timestamp", ev.get("ts", "")))[11:19]
        t = ev.get("event_type", ev.get("type", "?"))
        content = ev.get("content", "")[:60]
        action = ev.get("block_status", ev.get("action", "?"))
        rule = ev.get("rule_applied", ev.get("ruleName", ""))
        icon = (
            "🚫"
            if action == "blocked"
            else "✅"
            if action in ("allowed", "log")
            else "⚠️"
        )
        print(f"  {icon} [{ts}][{t}] {content}")
        if rule and rule != "none":
            print(f"       规则: {rule}")


def view_rules() -> None:
    """查看当前阻断规则"""
    monitor = create_monitor()
    rules = monitor.rules.rules

    print(f"\n  📋 当前阻断规则 ({len(rules)} 条)")
    print(f"  {'─'*50}")

    if not rules:
        print("  暂无规则")
        return

    by_cat: dict[str, list] = defaultdict(list)
    for r in rules.values():
        by_cat[r.category].append(r)

    for cat, cat_rules in sorted(by_cat.items()):
        print(f"\n  [{cat.upper()}]")
        for r in cat_rules:
            badge = (
                "🔴"
                if r.action == "block"
                else "📝"
                if r.action == "log"
                else "⬜"
            )
            tag = "内置" if not r.name.startswith("learned_") else "🤖自动"
            print(f"    {badge} {r.name} {tag}")
            pattern_display = (
                r.pattern[:50] + ("..." if len(r.pattern) > 50 else "")
            )
            print(f"        模式: {pattern_display}")
            if r.match_count > 0:
                print(f"        命中: {r.match_count} 次")


# ═══════════════════════════════════════════════════════════════════════════════
# 交互菜单
# ═══════════════════════════════════════════════════════════════════════════════


def interactive_menu() -> None:
    """交互选择启动模式"""
    print()
    print("  ╔══════════════════════════════════════════════════════╗")
    print("  ║         反检测浏览器 · 全功能启动器 (v2.0)          ║")
    print("  ║         MonitorEngine integrated                   ║")
    print("  ╚══════════════════════════════════════════════════════╝")
    print()
    print("  请选择模式（输入数字回车）：")
    print()
    print("    1️⃣  纯净模式      - 纯反检测，不做任何记录")
    print("    2️⃣  监控模式      - 反检测 + 监控引擎（推荐）")
    print("    3️⃣  验证模式      - 反检测 + 指纹检测报告")
    print("    4️⃣  监控+代理     - 反检测 + 监控 + 代理")
    print("    5️⃣  录制模式      - 反检测 + 操作录制")
    print("    6️⃣  诊断模式      - 诊断 Submit 按钮问题")
    print("    7️⃣  查看日志      - 查看最近一次监控日志")
    print("    8️⃣  查看规则      - 查看当前生效的阻断规则")
    print()

    choice = input("  选择: ").strip()

    mode_map: dict[str, tuple[str, str]] = {
        "1": ("clean", ""),
        "2": ("monitor", ""),
        "3": ("verify", ""),
        "4": ("monitor_proxy", ""),
        "5": ("record", ""),
        "6": ("diagnose", ""),
        "7": ("view_log", ""),
        "8": ("view_rules", ""),
    }

    if choice not in mode_map:
        print("  无效选择")
        sys.exit(0)

    action, _ = mode_map[choice]

    if action in ("view_log", "view_rules"):
        if action == "view_log":
            view_recent_log()
        else:
            view_rules()
        return

    url = input("  网址: ").strip()

    proxy = ""
    if action == "monitor_proxy":
        proxy = input("  代理 (如 http://127.0.0.1:7890): ").strip()

    if action == "diagnose":
        asyncio.run(launch_diagnose(url=url))
    elif action == "clean":
        asyncio.run(launch_clean(url=url))
    elif action == "verify":
        asyncio.run(launch_verify(url=url))
    elif action == "monitor":
        asyncio.run(launch_monitor(url=url))
    elif action == "monitor_proxy":
        asyncio.run(launch_monitor(url=url, proxy=proxy))
    elif action == "record":
        asyncio.run(launch_record(url=url))


# ═══════════════════════════════════════════════════════════════════════════════
# 命令行模式
# ═══════════════════════════════════════════════════════════════════════════════


def print_usage() -> None:
    """打印使用说明"""
    print(
        """用法:
  python cli.py                              # 交互菜单
  python cli.py launch <URL>                 # 纯净模式
  python cli.py monitor <URL>                # 监控模式
  python cli.py verify <URL>                 # 验证模式
  python cli.py record <URL>                 # 录制模式
  python cli.py diagnose [URL]               # 诊断模式
  python cli.py view-log                     # 查看最近日志
  python cli.py view-rules                   # 查看当前规则"""
    )


def main() -> None:
    """主入口"""
    # 无参数 → 交互菜单
    if len(sys.argv) == 1:
        interactive_menu()
        return

    # 有参数 → 命令行模式
    cmd = sys.argv[1]

    # 兼容旧版参数格式: python cli.py <URL> --mode monitor
    if cmd.startswith("http") or cmd.startswith("www."):
        url = cmd
        mode = "clean"
        proxy = ""

        # 解析 --mode / --proxy 等
        args = sys.argv[2:]
        i = 0
        while i < len(args):
            if args[i] == "--mode" and i + 1 < len(args):
                mode = args[i + 1]
                i += 2
            elif args[i] == "--proxy" and i + 1 < len(args):
                proxy = args[i + 1]
                i += 2
            elif args[i] == "--verify":
                mode = "verify"
                i += 1
            elif args[i] == "--record":
                mode = "record"
                i += 1
            elif args[i] == "--diagnose":
                mode = "diagnose"
                i += 1
            elif args[i] == "--headless":
                i += 1
            else:
                i += 1

        if mode == "verify":
            asyncio.run(launch_verify(url=url))
        elif mode == "record":
            asyncio.run(launch_record(url=url))
        elif mode == "diagnose":
            asyncio.run(launch_diagnose(url=url))
        elif mode in ("monitor", "monitor_proxy"):
            asyncio.run(launch_monitor(url=url, proxy=proxy))
        else:
            asyncio.run(launch_clean(url=url))
        return

    # 子命令模式
    if cmd == "view-log":
        view_recent_log()
    elif cmd == "view-rules":
        view_rules()
    elif cmd == "launch" and len(sys.argv) > 2:
        asyncio.run(launch_clean(url=sys.argv[2]))
    elif cmd == "clean" and len(sys.argv) > 2:
        asyncio.run(launch_clean(url=sys.argv[2]))
    elif cmd == "monitor" and len(sys.argv) > 2:
        asyncio.run(launch_monitor(url=sys.argv[2]))
    elif cmd == "verify" and len(sys.argv) > 2:
        asyncio.run(launch_verify(url=sys.argv[2]))
    elif cmd == "record" and len(sys.argv) > 2:
        asyncio.run(launch_record(url=sys.argv[2]))
    elif cmd == "diagnose":
        url = sys.argv[2] if len(sys.argv) > 2 else ""
        asyncio.run(launch_diagnose(url=url))
    elif cmd in ("-h", "--help", "help"):
        print_usage()
    else:
        print(f"未知命令: {cmd}")
        print_usage()


if __name__ == "__main__":
    main()
