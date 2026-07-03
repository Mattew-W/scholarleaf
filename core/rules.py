"""
core/rules.py - 阻断规则引擎
============================================================
从 monitor_engine.py 中提取的独立规则管理模块。
支持内置规则、持久化、自动学习。
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Optional

LOG_DIR = Path(__file__).parent.parent / "monitor_logs"
LOG_DIR.mkdir(exist_ok=True)


@dataclass
class BlockingRule:
    """阻断规则"""

    name: str
    pattern: str             # 正则表达式
    category: str            # dialog / console / dom / timer / visibility
    action: str              # block / log / ignore
    created_at: str
    match_count: int = 0

    def matches(self, content: str) -> bool:
        """检查内容是否匹配此规则"""
        try:
            return bool(re.search(self.pattern, content, re.IGNORECASE))
        except re.error:
            return self.pattern.lower() in content.lower()


class RuleEngine:
    """规则引擎：管理阻断规则的增删改查和持久化"""

    # 内置已知的高风险检测关键词
    # 注意：created_at 在 __init__ 中动态赋值，避免模块加载时固定
    DEFAULT_RULES: list[BlockingRule] = [
        BlockingRule(
            name="alert_通用警告",
            pattern=r"离开|切出|切换|切走|切屏|离开本页面|switch|switched|tab|leave",
            category="dialog",
            action="block",
            created_at="",
        ),
        BlockingRule(
            name="confirm_离开确认",
            pattern=r"确定要离开|是否离开|确认退出|confirm.*leave|leave.*confirm",
            category="dialog",
            action="block",
            created_at="",
        ),
        BlockingRule(
            name="console_离开通知",
            pattern=r"leave|切换|切屏|切出|离开监测|monitor.*(leave|exit)",
            category="console",
            action="block",
            created_at="",
        ),
        BlockingRule(
            name="console_异常上报",
            pattern=r"report.*(abnormal|error|violation)|上报.*异常|违规.*检测|violation|proctor.*alert",
            category="console",
            action="log",
            created_at="",
        ),
        BlockingRule(
            name="dom_离开警告",
            pattern=r"离开|切出|切屏|切换|切走|已离开本页面|warning|alert|您已离开",
            category="dom",
            action="block",
            created_at="",
        ),
        BlockingRule(
            name="dom_弹窗标题",
            pattern=r"提示|警告|注意|提醒|警告|系统提示|温馨提示|tip|notice|warning",
            category="dom",
            action="log",
            created_at="",
        ),
    ]

    def __init__(self, rules_file: Optional[Path] = None) -> None:
        self.rules_file: Path = rules_file or LOG_DIR / "blocking_rules.json"
        self.rules: dict[str, BlockingRule] = {}
        self._lock: Lock = Lock()

        # 加载内置规则（动态赋值 created_at，避免模块加载时固定）
        now = datetime.now().isoformat()
        for rule in self.DEFAULT_RULES:
            if not rule.created_at:
                rule.created_at = now
            self.rules[rule.name] = rule

        # 加载持久化规则
        self._load_rules()

    # ── 持久化 ───────────────────────────────────────────────────────────

    def _load_rules(self) -> None:
        """从磁盘加载规则"""
        if not self.rules_file.exists():
            return
        try:
            data = json.loads(self.rules_file.read_text(encoding="utf-8"))
            for d in data:
                rule = BlockingRule(**d)
                self.rules[rule.name] = rule
        except (json.JSONDecodeError, TypeError) as exc:
            import logging
            logging.getLogger(__name__).warning("规则加载失败: %s", exc)

    def _save_rules(self) -> None:
        """保存规则到磁盘"""
        with self._lock:
            data = [asdict(r) for r in self.rules.values()]
            self.rules_file.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    # ── 规则操作 ─────────────────────────────────────────────────────────

    def add_rule(self, rule: BlockingRule) -> None:
        """添加新规则（自动保存）"""
        with self._lock:
            self.rules[rule.name] = rule
        self._save_rules()

    def check(self, content: str) -> tuple[Optional[str], Optional[str]]:
        """检查内容是否命中已知规则。

        Returns:
            (action, rule_name)：action 为 block/log/ignore/None
        """
        with self._lock:
            for rule in self.rules.values():
                if rule.matches(content):
                    rule.match_count += 1
                    return rule.action, rule.name
        return None, None

    def learn_from_content(
        self, content: str, event_type: str, block_action: str = "block"
    ) -> Optional[BlockingRule]:
        """从事件内容中自动学习，生成新规则。

        Args:
            content: 事件内容
            event_type: 事件类型（console/dialog/dom_change/...）
            block_action: 命中后的动作

        Returns:
            新生成的规则，如果重复则返回 None
        """
        # 提取关键词（去除标点，保留中文/英文/数字）
        keywords = re.findall(r"[\u4e00-\u9fffA-Za-z]{2,}", content)
        if not keywords:
            return None

        # 生成规则名
        keyword_part = "".join(keywords[:2])
        rule_name = f"learned_{keyword_part}_{int(time.time()) % 100000}"

        # 避免重复
        for r in self.rules.values():
            if r.name.startswith("learned_") and r.pattern == content[:100]:
                return None

        rule = BlockingRule(
            name=rule_name,
            pattern=re.escape(content[:100]),
            category=event_type,
            action=block_action,
            created_at=datetime.now().isoformat(),
        )
        self.add_rule(rule)
        return rule

    def get_summary(self) -> dict[str, int]:
        """获取规则摘要（按分类统计）"""
        cats: dict[str, int] = {}
        with self._lock:
            for r in self.rules.values():
                cats[r.category] = cats.get(r.category, 0) + 1
        return cats
