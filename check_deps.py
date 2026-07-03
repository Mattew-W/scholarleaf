#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
依赖自检脚本

读取项目根目录下的 requirements.txt，逐项检查依赖是否已安装、版本是否符合要求。
退出码：  0 - 所有依赖满足；  1 - 有依赖缺失或版本不符；  2 - requirements.txt 不存在或读取失败
"""

import importlib.metadata as metadata
import os
import re
import sys

try:
    from packaging.version import Version, InvalidVersion

    HAS_PACKAGING = True
except ImportError:
    HAS_PACKAGING = False


ROOT = os.path.dirname(os.path.abspath(__file__))
REQ_FILE = os.path.join(ROOT, "requirements.txt")


def parse_requirement(line: str):
    """从 requirements.txt 的一行解析出 (包名, 版本规格)。"""
    line = line.strip()
    if not line or line.startswith("#"):
        return None

    # 移除行内注释
    if "#" in line:
        line = line.split("#")[0].strip()

    # 匹配包名和版本要求，忽略附加选项如 ; extra == "dev"
    m = re.match(r"^([a-zA-Z0-9_.\-]+)\s*(.*?)(?:\s*;|$)", line)
    if not m:
        return None

    name = m.group(1).strip()
    spec = m.group(2).strip()
    return name, spec


def read_requirements(path: str):
    deps = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                parsed = parse_requirement(line)
                if parsed:
                    deps.append(parsed)
    except FileNotFoundError:
        print(f"[错误] 未找到依赖清单: {path}")
        sys.exit(2)
    except Exception as e:
        print(f"[错误] 读取依赖清单失败: {e}")
        sys.exit(2)
    return deps


def normalize_pkg_name(name: str):
    """按 PEP 503 规范化包名，例如 playwright-stealth -> playwright_stealth。"""
    return re.sub(r"[-_.]+", "-", name).lower()


def get_installed_version(name: str):
    """查询已安装版本，未安装返回 None。"""
    for try_name in (normalize_pkg_name(name), name):
        try:
            return metadata.version(try_name)
        except metadata.PackageNotFoundError:
            continue
    return None


def _parse_version_tuple(version_str: str) -> tuple:
    """将版本字符串解析为可比较的整数元组，例如 '0.15.0' -> (0, 15, 0)。"""
    parts = []
    for token in re.split(r"[\.\-\+]", version_str.strip()):
        if token.isdigit():
            parts.append(int(token))
        elif token:
            break
    return tuple(parts) if parts else (0,)


def compare_versions(installed: str, op: str, required: str) -> bool:
    """比较版本号：installed op required 是否成立。"""
    if not HAS_PACKAGING:
        # 没有 packaging 库时，使用版本元组比较（正确处理 0.15.0 >= 0.7 等情况）
        iv = _parse_version_tuple(installed)
        rv = _parse_version_tuple(required)
        if op == "==":
            return iv == rv
        if op == ">=":
            return iv >= rv
        if op == "<=":
            return iv <= rv
        if op == ">":
            return iv > rv
        if op == "<":
            return iv < rv
        if op == "!=":
            return iv != rv
        return True

    try:
        iv = Version(installed)
        rv = Version(required)
    except InvalidVersion:
        if op == "==":
            return installed == required
        if op == ">=":
            return installed >= required
        return True

    if op == "==":
        return iv == rv
    if op == ">=":
        return iv >= rv
    if op == "<=":
        return iv <= rv
    if op == ">":
        return iv > rv
    if op == "<":
        return iv < rv
    if op == "===":
        return iv == rv
    if op == "!=":
        return iv != rv
    return True


def check_spec(installed: str, spec: str) -> bool:
    """根据版本规格字符串检查 installed 是否满足。"""
    if not spec:
        return True

    operators = ("==", ">=", "<=", "~=", "!=", ">", "<", "===")
    op = ""
    val = ""
    for candidate in operators:
        if spec.startswith(candidate):
            op = candidate
            val = spec[len(candidate):].strip()
            break

    if not op:
        # 无法识别的规格，保守视为不满足
        return False

    return compare_versions(installed, op, val)


def format_status(name: str, installed: str | None, spec: str, ok: bool) -> str:
    if ok:
        ver = installed if installed else "已安装"
        return f"  OK  {name:26s} {ver:14s}  要求: {spec or '任意'}"
    if installed is None:
        return f"  MISS {name:25s} {'未安装':14s}  要求: {spec or '任意'}"
    return f"  FAIL {name:25s} {installed:14s}  要求: {spec}"


def main():
    deps = read_requirements(REQ_FILE)

    missing = []
    mismatch = []

    for name, spec in deps:
        installed = get_installed_version(name)
        if installed is None:
            missing.append((name, spec))
            print(format_status(name, installed, spec, ok=False))
        elif not check_spec(installed, spec):
            mismatch.append((name, spec, installed))
            print(format_status(name, installed, spec, ok=False))
        else:
            print(format_status(name, installed, spec, ok=True))

    total = len(deps)
    passed = total - len(missing) - len(mismatch)
    print(f"\n  结果: {passed}/{total} 项通过")

    if missing or mismatch:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
