# 问题排查记忆

> 记录时间：2026-07-02
> 关联项目：TeaLeaMan 自动化答题/监控系统

## 问题现象

使用 Playwright/patchright 反检测浏览器访问 TeaLeaMan 在线考试/作业系统：
- 页面采用 JSP + frameset 架构：左侧导航框架 + 右侧内容框架（`rightwinmoniter`）
- 点击左侧「作业与测验」后，右侧 `studentassign.jsp` 能加载
- 但右侧页面中的 **grade / submit 等操作按钮不显示**

## 根本原因

`_LITE_INIT_SCRIPT` 和 `_VIEWPORT_ADAPTER_JS` 中包含了 `fixFrameset` 逻辑：

```javascript
// 当左侧 frame 宽度百分比 < 400px 时
fs.setAttribute('cols', '100%,0%');
```

TeaLeaMan 的 frameset 布局为 `cols="70%,*"`，该逻辑触发后将右侧内容框架宽度设为 **0%**。按钮虽然被渲染，但占用宽度为 0，完全不可见。

## 为什么之前没发现

- 早期使用 `add_init_script` 向所有 frame 注入脚本，导致子 frame 出现 SyntaxError，页面根本加载失败
- 改为 `page.evaluate` 只注入顶层页面后，SyntaxError 消失，但 `fixFrameset` 仍在顶层页面执行，继续破坏布局
- 日志中明确显示 `add_init_script` 仍在运行，说明删除不彻底

## 修复内容

| 文件 | 修改 |
|------|------|
| `core/browser.py` | 删除 `_LITE_INIT_SCRIPT`、`_VIEWPORT_ADAPTER_JS`；移除所有 `add_init_script` 调用；反检测脚本仅通过 `page.evaluate` 注入顶层页面 |
| `config.py` | `inject_viewport_adapter` 默认值由 `True` 改为 `False` |
| `TEST_GUIDE.md` | 更新为修复总结（已删除） |

## 目录结构

```
c:\Users\huang\Desktop\zb\
├── cli.py                 ← v2 命令行入口
├── config.py
├── core/                  ← 浏览器/监控核心
├── launch/                ← 启动器
├── auto/                  ← 自动化脚本
├── tests/
├── 一键启动.bat           ← 调用 cli.py
├── 一键启动(全能版).bat
├── TeaLeaMan作业答题.bat
├── ...
└── MEMORY.md
```

## 验证方法

修复后启动程序，登录 TeaLeaMan，点击左侧「作业与测验」，确认：
1. 右侧内容区占满剩余宽度
2. grade / submit 按钮正常显示
3. 浏览器控制台无 SyntaxError 或布局相关异常

## 后续如果仍有问题

按以下顺序排查：
1. 子 frame 的 `navigator.webdriver` 是否仍为 `true`
2. Part B 的 `visibilityState` / `hasFocus` 伪造是否影响按钮渲染
3. 用裸浏览器测试，确认是否为网站本身反爬机制

## 核心原则

> 所有反检测脚本统一通过 `page.evaluate` 只注入顶层页面，**绝不再用 `add_init_script` 注入子 frame**，避免与 JSP 内联脚本产生不可预期的交互。

---

# 启动脚本排查记忆

> 记录时间：2026-07-03
> 关联项目：TeaLeaMan 自动化答题/监控系统

## 问题现象

双击 `一键启动.bat` 后，CMD 窗口报错：
- `'ple'` 不是内部或外部命令
- `'-------------'` 不是内部或外部命令
- 随后直接进入 Python 交互模式（`>>>`），主程序未正常启动

## 根本原因

`一键启动.bat` 被保存为 **LF（Unix）换行符**，而 Windows CMD 解析批处理时需要 **CRLF（Windows）换行符**。LF 导致整行命令被错误拆分，部分内容被当作独立命令执行，最终把 `python` 命令也拆成了无参数调用，进入交互模式。

同时，之前的 `一键启动.bat` 只做了简单的 `patchright` 存在性检查，缺少：
- 对所有 `requirements.txt` 依赖的版本检测
- 自动安装与安装后复检
- 清晰的步骤与进度反馈

## 修复内容

| 文件 | 修改 |
|------|------|
| `一键启动.bat` | 重写为 4 步流程：定位 Python → 扫描依赖 → 自动安装 → 安装后复检；添加清华 PyPI 镜像源；保存为 UTF-8 + CRLF 编码 |
| `check_deps.py` | 新增依赖检测脚本，解析 `requirements.txt`，检查每个包是否安装及版本是否符合 |
| `requirements.txt` | 未改动，仍为 patchright / playwright-stealth / curl-cffi |

### 一键启动.bat 4 步流程

```
[1/4] 定位 Python 解释器（优先 .venv，否则系统 python）
[2/4] 扫描项目依赖 (requirements.txt)
[3/4] 检测到依赖缺失或版本不符，正在自动安装...
[4/4] 安装后复检...
```

依赖满足时直接跳过安装；不满足时自动调用：

```batch
"%PYTHON%" -m pip install -r "%ROOT%requirements.txt" --upgrade --progress-bar on -i "%PIP_INDEX%"
```

其中 `PIP_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple`。

## 验证方法

1. 双击 `一键启动.bat`，确认不再出现 `'ple'`、`'-------------'` 等解析错误
2. 首次运行应进入 `[3/4] 自动安装` 并显示 pip 下载进度
3. 安装完成后应显示 `[4/4] 复检通过` 并进入主程序
4. 再次双击应跳过安装，快速启动主程序

## 后续如果仍有问题

按以下顺序排查：
1. 确认 `一键启动.bat` 编码为 UTF-8，换行符为 CRLF
2. 确认文件开头有 `chcp 65001 >nul 2>&1`
3. 手动测试依赖检测：`python check_deps.py`
4. 手动安装测试：`python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple`

## 核心原则

> Windows 批处理文件统一使用 **UTF-8 编码 + CRLF 换行符 + `chcp 65001`**。所有 .bat 文件使用 `%~dp0` 获取脚本所在目录，**绝不硬编码绝对路径**。

---

# 依赖检测修复记忆

> 记录时间：2026-07-03
> 关联项目：TeaLeaMan 自动化答题/监控系统

## 问题现象

`一键启动.bat` 运行后，`check_deps.py` 输出：
```
FAIL curl-cffi                 0.15.0          要求: >=0.7
结果: 2/3 项通过
[4/4] 复检未通过
依赖仍存在问题，请检查 requirements.txt 或手动安装。
```

`curl-cffi` 版本 0.15.0 明明满足 `>=0.7` 要求，却被标记为 FAIL。

## 根本原因

`check_deps.py` 中 `compare_versions` 函数在 `packaging` 库不可用时，回退到**字符串比较**：
```python
if op == ">=":
    return installed >= required
```

字符串 `"0.15.0" >= "0.7"` 返回 `False`，因为字典序比较时 `"0.1" < "0.7"`（字符 `'1' < '7'`）。

同时，之前的 `check_deps.py` 强制将 stdout/stderr 重编码为 GBK：
```python
if sys.stdout.encoding != "gbk":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="gbk", errors="replace")
```
这导致 .bat 文件中 `for /f` 捕获的输出出现乱码。

## 修复内容

| 文件 | 修改 |
|------|------|
| `check_deps.py` | 移除强制 GBK 编码；添加 `_parse_version_tuple()` 函数，在无 `packaging` 时使用整数元组比较版本（正确处理 `0.15.0 >= 0.7`）；支持所有比较运算符（`==` `>=` `<=` `>` `<` `!=`） |
| 全部 .bat 文件 | `chcp 936` 改为 `chcp 65001`（UTF-8）；硬编码绝对路径 `c:\Users\huang\Desktop\zb\` 改为 `%~dp0`（相对路径）；移除硬编码凭据（学号 D10774000 改为交互式输入） |
| 新增 `.gitignore` | 排除 `__pycache__/`、`.venv/`、`.pytest_cache/`、`monitor_logs/` 等 |

## 修复后的 check_deps.py 版本比较逻辑

```python
def _parse_version_tuple(version_str: str) -> tuple:
    """将版本字符串解析为可比较的整数元组，例如 '0.15.0' -> (0, 15, 0)。"""
    parts = []
    for token in re.split(r"[\.\-\+]", version_str.strip()):
        if token.isdigit():
            parts.append(int(token))
        elif token:
            break
    return tuple(parts) if parts else (0,)
```

比较时：`(0, 15, 0) >= (0, 7)` → `True` ✓

## 验证方法

1. 运行 `python check_deps.py`，确认输出 `结果: 3/3 项通过`
2. 确认 `curl-cffi 0.15.0 >= 0.7` 显示为 OK
3. 双击 `一键启动.bat`，确认无乱码且正常启动

## 核心原则

> 版本号比较**永远不能**使用字符串比较，必须使用 `packaging.version.Version` 或整数元组比较。编码统一为 UTF-8，不再强制 GBK。

---

# 后续更改规范

> 记录时间：2026-07-03
> 适用于所有未来修改

## 编码规范

| 文件类型 | 编码 | 换行符 | 说明 |
|----------|------|--------|------|
| Python 源文件 | UTF-8 | LF（Unix） | Python 标准，跨平台兼容 |
| Windows 批处理 (.bat) | UTF-8 | CRLF（Windows） | `chcp 65001` 启用 UTF-8 控制台输出 |
| JavaScript (.js) | UTF-8 | LF（Unix） | 标准 JS 文件 |
| Markdown (.md) | UTF-8 | LF（Unix） | 文档文件 |
| JSON | UTF-8 | LF（Unix） | 数据文件 |

## .bat 文件编写规范

1. **使用 `%~dp0` 获取脚本目录**：`set "ROOT=%~dp0"`
2. **优先使用虚拟环境 Python**：`set "PYTHON=%ROOT%.venv\Scripts\python.exe"`
3. **使用 UTF-8 编码**：`chcp 65001 >nul 2>&1`
4. **保存为 CRLF 换行符**：用 Windows 记事本或 VS Code 的 "CRLF" 模式保存
5. **不硬编码凭据**：用户名、密码、URL 中的敏感信息改为交互式输入
6. **不硬编码绝对路径**：所有路径基于 `%~dp0`

## 版本号比较规范

- **必须**使用 `packaging.version.Version` 进行版本比较
- 如果 `packaging` 不可用，使用 `_parse_version_tuple()` 转为整数元组比较
- **永远不能**使用字符串比较（`"0.15.0" >= "0.7"` 会错误返回 False）

## 依赖管理规范

- 新增依赖时，在 `requirements.txt` 中添加并标注版本要求
- 运行 `python check_deps.py` 确认检测脚本能正确识别
- 不需要的依赖及时清理

## Git 提交规范

- 提交前确认 `.gitignore` 已配置，不会提交 `__pycache__/`、`.venv/` 等
- 提交信息使用中文，说明修改内容和原因
- 较大功能修改分多次小提交

## 调试规范

- 新增 .bat 文件时，先用 `python check_deps.py` 测试依赖检测
- 修改 Python 代码后，运行 `pytest tests/` 确认测试通过
- 修改 .bat 后，在 CMD 中实际运行验证（不在 PowerShell 中测试，编码行为不同）
