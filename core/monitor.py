"""
core/monitor.py - 在线考试监控系统检测与阻断引擎 (v2.0)
============================================================

【模块定位】
作为 browser.py 的扩展模块，运行于上层。
当目标是"未知网站"（如在线考试系统）时启用，实时监控页面的所有检测行为。

【v2.0 改进】
  - 修复 JS 注入脚本的安全转义问题（使用 JSON.parse 而非内联 JSON）
  - 自适应事件轮询（有事件加速，无事件退避）
  - 独立规则引擎（core/rules.py）
  - 完整的类型注解

【监控对象】
  1. console.* — 捕获 JS 向控制台输出的所有内容
  2. alert / confirm / prompt — 拦截离开确认弹窗
  3. MutationObserver — 监控 DOM 中动态插入的 div 弹窗
  4. visibilitychange — 捕获标签页切换检测
  5. setInterval — 监控计时器中的检测逻辑

【阻断策略】
  - block：静默丢弃，不弹窗，不打印
  - log：放行但记录
  - ignore：完全放行
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Optional

from core.rules import RuleEngine, BlockingRule

# 支持 async patchright / playwright 的 Page 类型
try:
    from patchright.async_api import Page, BrowserContext  # type: ignore[import-untyped]
except ImportError:
    from playwright.async_api import Page, BrowserContext  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

LOG_DIR = Path(__file__).parent.parent / "monitor_logs"
LOG_DIR.mkdir(exist_ok=True)


@dataclass
class DetectionEvent:
    """单次检测事件"""

    timestamp: str
    event_type: str          # console / dialog / dom_change / visibility / timer
    content: str             # 捕获到的内容
    stack_preview: str       # 调用栈预览（截取前200字符）
    block_status: str        # blocked / allowed / new_pattern
    rule_applied: str        # 匹配到的规则名称


class MonitorEngine:
    """监控引擎：接管浏览器页面，捕获所有可疑行为（v2.0）"""

    def __init__(
        self,
        context_id: str = "default",
        rule_engine: Optional[RuleEngine] = None,
        poll_interval_base: float = 0.5,
        poll_interval_max: float = 5.0,
        poll_backoff_factor: float = 1.5,
        auto_learn: bool = True,
    ) -> None:
        self.context_id: str = context_id
        self.session_id: str = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file: Path = LOG_DIR / f"monitor_{self.session_id}_{context_id}.jsonl"

        self.events: list[DetectionEvent] = []
        self.rules: RuleEngine = rule_engine or RuleEngine()
        self._poll_running: bool = False
        self._poll_tasks: list[asyncio.Task[Any]] = []
        self._injected: bool = False
        self._last_event_count: int = 0
        self.auto_learn: bool = auto_learn

        # 自适应轮询参数
        self._poll_interval_base: float = poll_interval_base
        self._poll_interval_max: float = poll_interval_max
        self._poll_backoff_factor: float = poll_backoff_factor
        self._current_poll_interval: float = poll_interval_base

    # ── 检测引擎 ─────────────────────────────────────────────────────────

    def check(self, content: str) -> tuple[Optional[str], Optional[str]]:
        """检查内容是否命中已知规则。

        Returns:
            (action, rule_name)
        """
        return self.rules.check(content)

    # ── 事件记录 ─────────────────────────────────────────────────────────

    def record(self, event: DetectionEvent) -> None:
        """记录事件到内存和文件"""
        self.events.append(event)
        # 追加到日志文件
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(event), ensure_ascii=False) + "\n")
        except OSError as exc:
            logger.warning("日志写入失败: %s", exc)

    # ── JS 注入脚本（修复了安全转义问题）─────────────────────────────────

    def get_injection_script(self) -> str:
        """
        生成注入到页面的监控脚本。

        v2.0 修复：使用 JSON.parse() 方式传递规则，避免内联 JSON
        被页面中的 </script> 或特殊字符破坏 JS 语法。
        """
        rules_data: list[dict[str, str]] = [
            {
                "name": r.name,
                "pattern": r.pattern,
                "action": r.action,
                "category": r.category,
            }
            for r in self.rules.rules.values()
        ]
        # 将规则 JSON 再次 JSON 编码，确保安全嵌入 <script> 标签
        rules_json_escaped: str = json.dumps(
            json.dumps(rules_data, ensure_ascii=False)
        )

        return f"""
(function() {{
    'use strict';

    // ═══════════════════════════════════════════════════════════════════════
    //  MonitorEngine 注入脚本 (v2.0)
    //  规则数: {len(rules_data)}
    //  会话ID: {self.session_id}
    // ═══════════════════════════════════════════════════════════════════════

    // 安全反序列化（JSON.parse 而非内联 JSON 对象）
    var RULES = JSON.parse({rules_json_escaped});
    var SESSION_ID = "{self.session_id}";
    var _origConsole = {{}};
    var _eventLog = [];

    // ── 通用匹配检查 ────────────────────────────────────────────────────
    function matchRule(content) {{
        for (var i = 0; i < RULES.length; i++) {{
            var rule = RULES[i];
            try {{
                if (new RegExp(rule.pattern, 'i').test(content)) {{
                    return {{ matched: true, action: rule.action, name: rule.name, rule: rule }};
                }}
            }} catch (_) {{
                if (content.toLowerCase().indexOf(rule.pattern.toLowerCase()) !== -1) {{
                    return {{ matched: true, action: rule.action, name: rule.name, rule: rule }};
                }}
            }}
        }}
        return {{ matched: false }};
    }}

    // ── 发送事件到 Python 端 ────────────────────────────────────────────
    function reportEvent(type, content, stack, action, ruleName) {{
        window._monitorPendingEvents = window._monitorPendingEvents || [];
        window._monitorPendingEvents.push({{
            type: type,
            content: content,
            stack: stack,
            action: action,
            ruleName: ruleName,
            ts: new Date().toISOString()
        }});
    }}

    // ── 1. 接管 console.* ────────────────────────────────────────────────
    ['log', 'warn', 'error', 'info', 'debug'].forEach(function(method) {{
        _origConsole[method] = console[method].bind(console);
        console[method] = function() {{
            var args = Array.prototype.slice.call(arguments);
            var content = args.map(function(a) {{
                return typeof a === 'object' ? JSON.stringify(a) : String(a);
            }}).join(' ');
            var stack = new Error().stack || '';
            var result = matchRule(content);

            if (result.matched) {{
                if (result.action === 'block') {{
                    // 静默丢弃
                }} else {{
                    _origConsole[method]('[Monitor]', content);
                }}
                reportEvent('console', content, stack.slice(0, 200), result.action, result.name);
            }} else {{
                _origConsole[method].apply(console, arguments);
            }}
        }};
    }});

    // ── 2. 接管 alert ───────────────────────────────────────────────────
    window._origAlert = window.alert;
    window.alert = function(msg) {{
        var content = String(msg);
        var result = matchRule(content);
        if (result.matched && result.action === 'block') {{
            reportEvent('dialog', content, '', 'blocked', result.name);
            return;
        }}
        reportEvent('dialog', content, '', 'allowed', result.name || 'none');
        return window._origAlert(msg);
    }};

    // ── 3. 接管 confirm ─────────────────────────────────────────────────
    window._origConfirm = window.confirm;
    window.confirm = function(msg) {{
        var content = String(msg);
        var result = matchRule(content);
        if (result.matched && result.action === 'block') {{
            reportEvent('dialog', content, '', 'blocked', result.name);
            return true;
        }}
        reportEvent('dialog', content, '', 'allowed', result.name || 'none');
        return window._origConfirm(msg);
    }};

    // ── 4. 接管 prompt ──────────────────────────────────────────────────
    window._origPrompt = window.prompt;
    window.prompt = function(msg, def) {{
        var content = String(msg);
        var result = matchRule(content);
        if (result.matched && result.action === 'block') {{
            reportEvent('dialog', content, '', 'blocked', result.name);
            return def || '';
        }}
        reportEvent('dialog', content, '', 'allowed', result.name || 'none');
        return window._origPrompt(msg, def);
    }};

    // ── 5. DOM 弹窗监控（MutationObserver）──────────────────────────────
    var _domObserver = null;
    function initDOMObserver() {{
        if (_domObserver) return;
        _domObserver = new MutationObserver(function(mutations) {{
            for (var i = 0; i < mutations.length; i++) {{
                var m = mutations[i];
                if (m.type === 'childList') {{
                    for (var j = 0; j < m.addedNodes.length; j++) {{
                        var node = m.addedNodes[j];
                        if (node.nodeType !== 1) continue;
                        checkNode(node);
                    }}
                }}
                if (m.type === 'attributes') {{
                    var el = m.target;
                    if (el.id && matchRule(el.id).matched) {{
                        var content = el.id + '|' + (el.textContent || '').slice(0, 100);
                        var result = matchRule(content);
                        reportEvent('dom_change', content, '', result.action, result.name);
                    }}
                }}
            }}
        }});
        _domObserver.observe(document.body || document.documentElement, {{
            childList: true,
            subtree: true,
            attributes: true,
            attributeFilter: ['id', 'class', 'style'],
        }});
    }}

    function checkNode(node) {{
        var text = (node.textContent || '').slice(0, 200);
        if (!text.trim()) return;
        var result = matchRule(text);
        if (result.matched) {{
            reportEvent('dom_change', text, '', result.action, result.name);
        }}
    }}

    // ── 6. visibilitychange 监控 ────────────────────────────────────────
    document.addEventListener('visibilitychange', function() {{
        var content = 'visibilitychange:' + document.visibilityState;
        var result = matchRule(content);
        if (result.matched) {{
            reportEvent('visibility', content, '', result.action, result.name);
        }}
    }}, true);

    // ── 7. 定时器劫持 ───────────────────────────────────────────────────
    var _origSetInterval = window.setInterval;
    window.setInterval = function(handler, delay) {{
        var tid = _origSetInterval(handler, delay);
        var handlerStr = String(handler);
        var result = matchRule(handlerStr);
        if (result.matched) {{
            reportEvent('timer', handlerStr.slice(0,100), '', result.action, result.name);
        }}
        return tid;
    }};

    // ── 8. 提供 Python 读取事件的接口 ───────────────────────────────────
    window._getMonitorEvents = function() {{
        var evs = window._monitorPendingEvents || [];
        window._monitorPendingEvents = [];
        return evs;
    }};

    // ── 初始化 ──────────────────────────────────────────────────────────
    if (document.body) {{
        initDOMObserver();
    }} else {{
        document.addEventListener('DOMContentLoaded', initDOMObserver);
    }}
    setTimeout(initDOMObserver, 100);

    console.log('[MonitorEngine] injected, rules:', RULES.length);
}})();
"""

    # ── Playwright 集成 ─────────────────────────────────────────────────

    async def attach_to_page(self, page: Page) -> None:
        """将监控引擎附加到 Playwright 异步页面。

        注入 JS 脚本 + 启动 asyncio 后台任务定时拉取事件。
        支持多次调用（每个新标签页各自独立轮询，共用同一 log 文件）。
        """
        script = self.get_injection_script()
        try:
            await page.add_init_script(script)
        except Exception as exc:
            logger.debug("add_init_script 失败: %s", exc)

        # 对已加载完的页面直接 evaluate 注入
        try:
            await page.evaluate(script)
        except Exception as exc:
            logger.debug("page.evaluate 注入失败: %s", exc)

        self._poll_running = True

        async def poll_events() -> None:
            """自适应轮询：有事件时加快，无事件时退避"""
            while self._poll_running:
                try:
                    if page.is_closed():
                        break
                    events: list[dict[str, Any]] = await page.evaluate(
                        """() => {
                            var evs = window._getMonitorEvents ? window._getMonitorEvents() : [];
                            return evs;
                        }"""
                    )
                    has_new = False
                    for ev in events or []:
                        event = DetectionEvent(
                            timestamp=ev.get("ts", datetime.now().isoformat()),
                            event_type=ev.get("type", "unknown"),
                            content=ev.get("content", ""),
                            stack_preview=ev.get("stack", ""),
                            block_status=ev.get("action", "unknown"),
                            rule_applied=ev.get("ruleName", "none"),
                        )
                        self.record(event)
                        has_new = True

                        # 自动学习
                        if (
                            self.auto_learn
                            and event.block_status == "blocked"
                        ):
                            self.rules.learn_from_content(
                                event.content, event.event_type
                            )

                    # 自适应轮询间隔
                    if has_new:
                        self._current_poll_interval = max(
                            self._poll_interval_base,
                            self._current_poll_interval * 0.5,
                        )
                    else:
                        self._current_poll_interval = min(
                            self._poll_interval_max,
                            self._current_poll_interval * self._poll_backoff_factor,
                        )
                except Exception as exc:
                    logger.debug("轮询异常: %s", exc)

                await asyncio.sleep(self._current_poll_interval)

        task = asyncio.ensure_future(poll_events())
        self._poll_tasks.append(task)
        self._injected = True
        logger.info(
            "MonitorEngine 已附加到页面 (poll_interval=%.2fs)",
            self._poll_interval_base,
        )

    def detach(self) -> None:
        """停止监控（取消所有页面的轮询任务）"""
        self._poll_running = False
        for task in self._poll_tasks:
            if task and not task.done():
                task.cancel()
        logger.info("MonitorEngine 已分离")

    # ── 报告生成 ─────────────────────────────────────────────────────────

    def generate_report(self) -> str:
        """生成检测报告"""
        lines = [
            f"MonitorEngine 监控报告 (v2.0)",
            f"{'='*50}",
            f"会话ID: {self.session_id}",
            f"记录事件数: {len(self.events)}",
            f"活跃规则数: {len(self.rules.rules)}",
            f"日志文件: {self.log_file}",
            "",
            "事件分类统计:",
        ]

        categories: dict[str, int] = {}
        blocked: dict[str, int] = {}
        for ev in self.events:
            categories[ev.event_type] = categories.get(ev.event_type, 0) + 1
            if ev.block_status == "blocked":
                blocked[ev.rule_applied] = blocked.get(ev.rule_applied, 0) + 1

        for cat, count in sorted(categories.items()):
            lines.append(f"  [{cat}] {count} 次")

        if blocked:
            lines.append("")
            lines.append("已阻断事件 (按规则):")
            for rule, count in sorted(blocked.items(), key=lambda x: -x[1]):
                lines.append(f"  {rule}: {count} 次")

        lines.append("")
        lines.append("规则命中排行:")
        sorted_rules = sorted(
            self.rules.rules.values(), key=lambda r: -r.match_count
        )
        for r in sorted_rules[:10]:
            if r.match_count > 0:
                lines.append(f"  [{r.category}] {r.name}: {r.match_count} 次匹配")

        return "\n".join(lines)


def create_monitor(context_id: str = "default") -> MonitorEngine:
    """工厂方法：创建监控引擎"""
    return MonitorEngine(context_id=context_id)
