"""
auto/run.py - 自动化功能 CLI 入口
============================================================
独立的自动化命令行工具，不修改 cli.py 原始文件。

【用法】
  python -m auto.run replay <record_file>              # 回放录制操作
  python -m auto.run replay <record_file> --speed 2    # 2倍速回放
  python -m auto.run tealeaman login --user X --pwd Y  # TeaLeaMan 登录
  python -m auto.run tealeaman scan                    # 扫描作业列表
  python -m auto.run tealeaman full --user X --pwd Y   # 全流程自动化
  python -m auto.run tealeaman full --user X --pwd Y \\
      --answers '{"q0":"A","q1":"B"}'                  # 带答案全流程

【所有模式】
  replay <file>        回放录制文件
    --speed N          播放速度倍率 (默认=1.0, 2=2倍速)
    --no-stop          出错不停止

  tealeaman login      仅登录
    --user USER        用户名/学号
    --pwd PWD          密码

  tealeaman full       全流程: 登录→作业→答题→提交
    --user USER        用户名
    --pwd PWD          密码
    --answers JSON     答案 JSON
    --answers-file F   答案文件路径
    --index N          作业序号 (默认=0)
    --title TITLE      作业标题
    --no-submit        不自动提交（仅保存）

  tealeaman scan       扫描作业列表（需先登录）

  tealeaman answer     仅答题（需已在答题页）
    --answers JSON     答案 JSON
    --answers-file F   答案文件路径
    --submit           答题后提交
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

# 添加父目录到 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.browser import StealthBrowser
from config import BrowserConfig
from auto.replay import ReplayEngine
from auto.tealeaman import TeaLeaManBot

# ── 日志配置 ─────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("auto")


# ═══════════════════════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════════════════════


def _build_parser() -> argparse.ArgumentParser:
    """构建 CLI 参数解析器。"""
    parser = argparse.ArgumentParser(
        description="StealthBrowser 自动化工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    sub = parser.add_subparsers(dest="command", help="自动化模式")

    # ── replay ─────────────────────────────────────────────────────────
    replay_p = sub.add_parser("replay", help="回放录制文件")
    replay_p.add_argument("record_file", help="录制文件路径 (record_操作记录.json)")
    replay_p.add_argument("--speed", type=float, default=1.0,
                          help="播放速度倍率 (默认=1.0)")
    replay_p.add_argument("--no-stop", action="store_true",
                          help="出错不停止")
    replay_p.add_argument("--headless", action="store_true",
                          help="无头模式")

    # ── tealeaman ─────────────────────────────────────────────────────
    tm_p = sub.add_parser("tealeaman", help="TeaLeaMan 平台自动化")
    tm_sub = tm_p.add_subparsers(dest="tm_action", help="操作")

    # login
    login_p = tm_sub.add_parser("login", help="自动登录")
    login_p.add_argument("--user", required=True, help="用户名/学号")
    login_p.add_argument("--pwd", required=True, help="密码")
    login_p.add_argument("--headless", action="store_true")

    # full
    full_p = tm_sub.add_parser("full", help="全流程自动化")
    full_p.add_argument("--user", required=True, help="用户名/学号")
    full_p.add_argument("--pwd", required=True, help="密码")
    full_p.add_argument("--answers", type=str, default=None,
                        help='答案 JSON, 例: \'{"q0":"A","q1":"B"}\'')
    full_p.add_argument("--answers-file", type=str, default=None,
                        help="答案 JSON 文件路径")
    full_p.add_argument("--index", type=int, default=0,
                        help="作业序号 (默认=0)")
    full_p.add_argument("--title", type=str, default=None,
                        help="作业标题关键词")
    full_p.add_argument("--no-submit", action="store_true",
                        help="不自动提交（仅保存）")
    full_p.add_argument("--headless", action="store_true")

    # scan
    scan_p = tm_sub.add_parser("scan", help="扫描作业列表")
    scan_p.add_argument("--user", required=True)
    scan_p.add_argument("--pwd", required=True)
    scan_p.add_argument("--headless", action="store_true")

    # answer
    ans_p = tm_sub.add_parser("answer", help="仅答题（需已在答题页）")
    ans_p.add_argument("--answers", type=str, default=None,
                       help='答案 JSON')
    ans_p.add_argument("--answers-file", type=str, default=None,
                       help="答案文件路径")
    ans_p.add_argument("--submit", action="store_true",
                       help="答题后提交")
    ans_p.add_argument("--url", type=str, default=None,
                       help="直接打开答题页 URL")
    ans_p.add_argument("--headless", action="store_true")

    return parser


def _parse_answers(args: argparse.Namespace) -> dict | None:
    """解析答案参数。"""
    answers: dict | None = None

    if hasattr(args, "answers") and args.answers:
        try:
            answers = json.loads(args.answers)
        except json.JSONDecodeError:
            logger.error("答案 JSON 格式错误")
            return None

    if hasattr(args, "answers_file") and args.answers_file:
        try:
            path = Path(args.answers_file)
            answers = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("读取答案文件失败: %s", exc)
            return None

    return answers


async def _run_replay(args: argparse.Namespace) -> None:
    """执行回放。"""
    cfg = BrowserConfig(headless=args.headless)

    async with StealthBrowser(config=cfg) as browser:
        record_path = args.record_file

        speed = args.speed
        min_delay = max(0.05, 0.3 / speed)
        max_delay = max(0.1, 1.5 / speed)

        engine = ReplayEngine(
            browser,
            min_delay=min_delay,
            max_delay=max_delay,
            stop_on_error=not args.no_stop,
        )

        stats = await engine.replay(record_path)

        print(f"\n回放结果: {stats['success']}/{stats['total']} 成功, "
              f"{stats['failed']} 失败, {stats['skipped']} 跳过")

        if args.headless:
            await asyncio.sleep(1)
        else:
            print("\n浏览器窗口保持开启，按 Ctrl+C 关闭...")
            try:
                await browser.wait_until_closed()
            except (KeyboardInterrupt, asyncio.CancelledError):
                pass


async def _run_tealeaman(args: argparse.Namespace) -> None:
    """执行 TeaLeaMan 自动化。"""
    cfg = BrowserConfig(headless=args.headless)
    action = args.tm_action

    async with StealthBrowser(config=cfg) as browser:
        bot = TeaLeaManBot(browser)

        if action == "login":
            ok = await bot.auto_login(args.user, args.pwd)
            print(f"\n登录结果: {'✅ 成功' if ok else '❌ 失败'}")
            if not args.headless:
                print("浏览器窗口保持开启...")
                try:
                    await browser.wait_until_closed()
                except (KeyboardInterrupt, asyncio.CancelledError):
                    pass

        elif action == "full":
            answers = _parse_answers(args)
            report = await bot.run_full_cycle(
                username=args.user,
                password=args.pwd,
                answers=answers,
                assignment_index=args.index,
                assignment_title=args.title,
                submit=not args.no_submit,
            )
            print(f"\n{'='*55}")
            print(f"  执行报告")
            print(f"{'='*55}")
            for step in report.get("steps", []):
                icon = "✅" if step.get("ok") else ("⚠️" if step.get("ok") is None else "❌")
                print(f"  {icon} {step['step']}")
            if "questions_count" in report:
                print(f"  📝 题目数: {report['questions_count']}")
            if "elapsed_seconds" in report:
                print(f"  ⏱️  耗时: {report['elapsed_seconds']}s")
            if not args.headless:
                print("\n浏览器窗口保持开启...")
                try:
                    await browser.wait_until_closed()
                except (KeyboardInterrupt, asyncio.CancelledError):
                    pass

        elif action == "scan":
            ok = await bot.auto_login(args.user, args.pwd)
            if ok:
                ok = await bot.navigate_assignments()
                if ok:
                    assignments = await bot.scan_assignments()
                    print(f"\n找到 {len(assignments)} 个作业")
            if not args.headless:
                print("浏览器窗口保持开启...")
                try:
                    await browser.wait_until_closed()
                except (KeyboardInterrupt, asyncio.CancelledError):
                    pass

        elif action == "answer":
            answers = _parse_answers(args)
            if not answers:
                print("❌ 请提供答案 (--answers 或 --answers-file)")
                return

            if args.url:
                await browser.goto(args.url)
                await asyncio.sleep(2)

            ok = await bot.fill_answers(answers)
            if ok and args.submit:
                await bot.submit_assignment()

            if not args.headless:
                print("浏览器窗口保持开启...")
                try:
                    await browser.wait_until_closed()
                except (KeyboardInterrupt, asyncio.CancelledError):
                    pass


def main() -> None:
    """CLI 主入口。"""
    parser = _build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    if args.command == "replay":
        asyncio.run(_run_replay(args))
    elif args.command == "tealeaman":
        if not args.tm_action:
            print("请指定 TeaLeaMan 操作: login | full | scan | answer")
            return
        asyncio.run(_run_tealeaman(args))


if __name__ == "__main__":
    main()
