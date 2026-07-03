# ScholarLeaf

自动化答题/监控系统 — 基于 Playwright/Patchright 反检测浏览器，针对 TeaLeaMan 在线考试平台。

## 功能

- **反检测浏览器**：指纹随机化、Canvas 噪声、WebGL 伪装
- **多模式运行**：纯净 / 监控 / 验证 / 录制 / 诊断
- **自动依赖检测**：启动时自动检查并安装依赖
- **Windows 一键启动**：双击 `.bat` 即可运行

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 交互模式
python cli.py

# 命令行模式
python cli.py launch <URL>
python cli.py monitor <URL>
python cli.py verify <URL>
python cli.py diagnose
```

## 项目结构

```
scholarleaf/
├── cli.py              # 统一命令行入口
├── config.py           # 配置文件
├── core/               # 浏览器/监控核心
├── launch/             # 启动器
├── auto/               # 自动化脚本
├── tests/              # 测试
├── 一键启动.bat         # Windows 一键启动
└── requirements.txt    # 依赖列表
```

## 依赖

- patchright
- playwright-stealth
- curl-cffi

## 注意事项

本项目仅供学习研究使用。
