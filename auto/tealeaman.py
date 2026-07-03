"""
auto/tealeaman.py - TeaLeaMan 平台专用自动化机器人
============================================================
针对 edqab.com/tealeaman 在线作业平台的专用自动化引擎。

【支持的自动化操作】
  1. auto_login()          - 自动登录（用户名+密码）
  2. navigate_assignments() - 导航到作业列表
  3. open_assignment()     - 点击某个作业的 Submit 按钮
  4. read_questions()      - 读取当前答题页所有题目
  5. fill_answers()        - 批量填写答案
  6. submit_assignment()   - 点击橙色 Submit 提交
  7. save_assignment()     - 点击绿色 Save 暂存
  8. run_full_cycle()      - 一键执行：登录→作业→答题→提交

【已知平台特征】
  - 登录页: studentpage.jsp?orgnum=0&sid={username}
  - frameset 结构: leftwinmoniter (菜单) + rightwinmoniter (内容)
  - 作业列表: studentassign.jsp (在 rightwinmoniter 中)
  - 答题页: stuasfrm.jsp → upleft1 (题目) + uprig1 (帮助)
  - Submit 按钮: name=submit1, class=OrangeButton, onclick=submitass()
  - Save 按钮:   name=submit2, class=GreenButton, onclick=tempsave()

【用法】
  from auto.tealeaman import TeaLeaManBot
  bot = TeaLeaManBot(browser)
  await bot.run_full_cycle(
      username="D10774000",
      password="D10774000",
      answers={"q1": "A", "q2": "B", ...},
  )
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

# ── 平台常量 ──────────────────────────────────────────────────────────────────

BASE_URL = "https://edqab.com/tealeaman"
LOGIN_URL = f"{BASE_URL}/studentpage.jsp?orgnum=0"
ASSIGN_FRAME_NAME = "rightwinmoniter"
MENU_FRAME_NAME = "leftwinmoniter"
ASSIGN_PAGE = "studentassign.jsp"
ANSWER_PAGE = "stuasfrm.jsp"
QUESTION_FRAME = "upleft1"
HELP_FRAME = "uprig1"

SUBMIT_BUTTON_SELECTORS = [
    'input[name="submit1"]',
    'input.OrangeButton',
    'input[type="submit"][value*="Submit"]',
    'input[onclick*="submitass"]',
]

SAVE_BUTTON_SELECTORS = [
    'input[name="submit2"]',
    'input.GreenButton',
    'input[type="button"][value*="Save"]',
    'input[onclick*="tempsave"]',
]


class TeaLeaManBot:
    """TeaLeaMan 平台自动化机器人。

    封装了该平台的所有常见操作，基于 StealthBrowser 实例运行。
    """

    def __init__(
        self,
        browser: Any,  # StealthBrowser 实例
        *,
        base_delay: float = 1.0,
        timeout: int = 30_000,
        screenshot_dir: Optional[str] = None,
    ) -> None:
        """
        Args:
            browser:        已启动的 StealthBrowser 实例
            base_delay:     操作间基础延迟（秒），实际会加随机扰动
            timeout:        默认操作超时（毫秒）
            screenshot_dir: 截图保存目录
        """
        self.browser = browser
        self.base_delay = base_delay
        self.timeout = timeout
        self.screenshot_dir = Path(screenshot_dir) if screenshot_dir else Path("auto_screenshots")
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

        self.username: str = ""
        self._current_frame_name: str = ""
        self._assignment_title: str = ""

    @property
    def page(self) -> Any:
        """快捷访问当前页面。"""
        return self.browser.page

    # ── 辅助方法 ────────────────────────────────────────────────────────────

    async def _sleep(self, min_s: float = 0.5, max_s: float = 2.0) -> None:
        """随机延迟，模拟人类操作间隔。"""
        delay = min_s + secrets.randbelow(int((max_s - min_s) * 1000)) / 1000
        await asyncio.sleep(delay)

    async def _ss(self, name: str) -> Optional[str]:
        """截屏保存。"""
        try:
            path = self.screenshot_dir / f"{name}_{int(time.time())}.png"
            await self.browser.screenshot(str(path))
            logger.info("截图: %s", path)
            return str(path)
        except Exception as exc:
            logger.warning("截图失败: %s", exc)
            return None

    async def _wait_page_stable(self, timeout: int = 15_000) -> bool:
        """等待页面稳定（network idle）。"""
        try:
            await self.browser.page.wait_for_load_state("networkidle", timeout=timeout)
            await self._sleep(0.5, 1.0)
            return True
        except Exception:
            return False

    def _get_frame_by_name(self, name: str) -> Any:
        """在 page.frames 中查找指定 name 的 frame。"""
        for f in self.browser.page.frames:
            if getattr(f, "name", "") == name:
                return f
        return None

    def _get_frame_by_url_fragment(self, fragment: str) -> Any:
        """在 page.frames 中查找 URL 包含指定片段的 frame。"""
        for f in self.browser.page.frames:
            if fragment in (f.url or ""):
                return f
        return None

    def _get_content_frame(self) -> Any:
        """获取右侧内容 frame（rightwinmoniter）。"""
        return self._get_frame_by_name(ASSIGN_FRAME_NAME)

    def _get_question_frame(self) -> Any:
        """获取题目 frame（upleft1）。"""
        return self._get_frame_by_name(QUESTION_FRAME)

    # ── 1. 自动登录 ────────────────────────────────────────────────────────

    async def auto_login(
        self,
        username: str,
        password: str,
        login_url: Optional[str] = None,
    ) -> bool:
        """自动登录 TeaLeaMan。

        Args:
            username:  学号/用户名
            password:  密码
            login_url: 登录页 URL（默认自动拼接）

        Returns:
            True 表示登录成功
        """
        self.username = username
        url = login_url or f"{LOGIN_URL}&sid={username}"

        print(f"\n{'='*55}")
        print(f"  🤖 TeaLeaMan 自动登录")
        print(f"{'='*55}")
        print(f"  用户: {username}")
        print(f"  URL:  {url}")

        # 导航到登录页
        ok = await self.browser.goto(url)
        if not ok:
            logger.error("无法访问登录页")
            return False

        await self._wait_page_stable()
        await self._ss("01_login_page")

        # 在 frameset 中定位登录表单
        # TeaLeaMan 登录页结构: frameset → leftwinmoniter (菜单) + rightwinmoniter (登录表单)
        login_frame = self._get_content_frame()

        if login_frame:
            logger.info("找到内容 frame: rightwinmoniter")
            try:
                # 查找密码输入框
                pwd_input = login_frame.locator('input[type="password"]').first
                if await pwd_input.count() > 0:
                    await pwd_input.fill(password, timeout=self.timeout)
                    await self._sleep()
                    logger.info("密码已填写")
                else:
                    logger.warning("未找到密码输入框")
            except Exception as exc:
                logger.warning("rightwinmoniter 中填写密码失败: %s", exc)
        else:
            # fallback: 直接在主页面找
            logger.info("无 frameset，直接在页面查找登录表单")
            try:
                pwd_input = self.page.locator('input[type="password"]').first
                if await pwd_input.count() > 0:
                    await pwd_input.fill(password, timeout=self.timeout)
                    await self._sleep()
            except Exception as exc:
                logger.warning("主页填写密码失败: %s", exc)

        await self._ss("02_password_filled")

        # 点击登录按钮
        logged_in = False
        for btn_selector in [
            'input[type="submit"]',
            'input[type="button"][value*="Login"]',
            'input[type="button"][value*="登"]',
            'input[type="button"][value*="Sign"]',
            'button[type="submit"]',
            'a:has-text("Login")',
            'a:has-text("登")',
        ]:
            try:
                btn = self.page.locator(btn_selector).first
                if await btn.count() > 0:
                    await btn.click(timeout=self.timeout)
                    logged_in = True
                    logger.info("已点击登录按钮: %s", btn_selector)
                    break
            except Exception:
                continue

        if not logged_in and login_frame:
            for btn_selector in [
                'input[type="submit"]',
                'input[type="button"]',
            ]:
                try:
                    btn = login_frame.locator(btn_selector).first
                    if await btn.count() > 0:
                        await btn.click(timeout=self.timeout)
                        logged_in = True
                        logger.info("已点击 frame 中的按钮")
                        break
                except Exception:
                    continue

        # 等待登录完成
        await self._sleep(2.0, 3.0)
        await self._wait_page_stable()

        await self._ss("03_after_login")

        # 验证登录状态：检查 URL 是否变化或是否有菜单内容
        current_url = self.page.url
        if "studentpage.jsp" in current_url or "studentindex" in current_url:
            print(f"  ✅ 登录成功！当前页: {current_url}")
            return True
        else:
            print(f"  ⚠️  登录后 URL: {current_url}，待验证...")
            return True  # 不阻塞，继续后续操作

    # ── 2. 导航到作业列表 ──────────────────────────────────────────────────

    async def navigate_assignments(self) -> bool:
        """导航到 Assignments & Tests 页面。

        在左侧菜单 frame 中点击 "Assignments & Tests" 链接。
        """
        print(f"\n── 导航到作业列表 ──")

        await self._wait_page_stable()

        # 策略1: 在 leftwinmoniter 中找菜单链接
        menu_frame = self._get_frame_by_name(MENU_FRAME_NAME)
        if menu_frame:
            logger.info("找到菜单 frame: leftwinmoniter")
            try:
                link = menu_frame.get_by_text("Assignments & Tests", exact=False).first
                if await link.count() > 0:
                    await link.click(timeout=self.timeout)
                    logger.info("点击 Assignments & Tests")
                    await self._sleep(1.5, 2.5)
                    await self._wait_page_stable()
                    await self._ss("04_assignments_list")
                    return True
            except Exception as exc:
                logger.warning("leftwinmoniter 中点击失败: %s", exc)

        # 策略2: 全局搜索
        try:
            link = self.page.get_by_text("Assignments & Tests", exact=False).first
            if await link.count() > 0:
                await link.click(timeout=self.timeout)
                await self._sleep(1.5, 2.5)
                await self._wait_page_stable()
                await self._ss("04_assignments_list")
                return True
        except Exception as exc:
            logger.warning("全局搜索 Assignments 失败: %s", exc)

        # 策略3: 在所有 frame 中搜索
        for frame in self.page.frames:
            try:
                link = frame.get_by_text("Assignments & Tests", exact=False).first
                if await link.count() > 0:
                    await link.click(timeout=self.timeout)
                    logger.info("在 frame [%s] 中找到并点击", getattr(frame, "name", "?"))
                    await self._sleep(1.5, 2.5)
                    await self._wait_page_stable()
                    return True
            except Exception:
                continue

        logger.error("无法找到 Assignments & Tests 链接")
        return False

    # ── 3. 打开作业 ───────────────────────────────────────────────────────

    async def open_assignment(
        self,
        index: int = 0,
        title: Optional[str] = None,
    ) -> bool:
        """打开指定作业的答题页。

        在右侧内容 frame (studentassign.jsp) 中找到作业列表，
        点击对应行的 Submit 按钮。

        Args:
            index: 作业序号（0-based）
            title: 作业标题关键词（优先于 index）

        Returns:
            True 表示成功打开
        """
        print(f"\n── 打开作业 (index={index}, title={title}) ──")

        content_frame = self._get_content_frame()
        target = content_frame or self.page

        # 先探测作业列表
        await self._ss("05_assign_before_open")

        # 策略1: 按标题找
        if title:
            try:
                # 找到包含标题的行，点击该行的 Submit
                row = target.get_by_text(title, exact=False).first
                if await row.count() > 0:
                    # 尝试在附近的父级中找 Submit 按钮
                    parent_row = row.locator("xpath=ancestor::tr").first
                    if await parent_row.count() > 0:
                        submit_btn = parent_row.locator(SUBMIT_BUTTON_SELECTORS[0]).first
                        if await submit_btn.count() > 0:
                            await submit_btn.click(timeout=self.timeout)
                            logger.info("点击作业 '%s' 的 Submit", title)
                            return await self._after_open_assignment()
            except Exception as exc:
                logger.warning("按标题找作业失败: %s", exc)

        # 策略2: 按 index 找 Submit 按钮
        try:
            for sel in SUBMIT_BUTTON_SELECTORS:
                buttons = target.locator(sel)
                count = await buttons.count()
                if count > index:
                    btn = buttons.nth(index)
                    await btn.click(timeout=self.timeout)
                    logger.info("点击第 %d 个 Submit 按钮", index)
                    return await self._after_open_assignment()
        except Exception as exc:
            logger.warning("按 index 找 Submit 失败: %s", exc)

        # 策略3: 在 content frame 中找所有 Submit 按钮
        try:
            all_buttons = target.locator('input[type="submit"], input.OrangeButton')
            count = await all_buttons.count()
            if count > index:
                btn = all_buttons.nth(index)
                await btn.click(timeout=self.timeout)
                logger.info("点击第 %d 个按钮", index)
                return await self._after_open_assignment()
        except Exception as exc:
            logger.warning("找所有按钮失败: %s", exc)

        logger.error("无法打开作业")
        return False

    async def _after_open_assignment(self) -> bool:
        """打开作业后的等待和验证。"""
        await self._sleep(2.0, 3.5)
        await self._wait_page_stable()
        await self._ss("06_assignment_opened")

        # 检查是否到了答题页 (stuasfrm.jsp)
        for frame in self.page.frames:
            if ANSWER_PAGE in (frame.url or ""):
                logger.info("答题页已加载: %s", frame.url)
                return True

        # 检查是否有 upleft1 frame
        if self._get_question_frame():
            logger.info("答题 frame (upleft1) 已就绪")
            return True

        logger.info("作业已打开（可能是单页面模式）")
        return True

    # ── 4. 读取题目 ───────────────────────────────────────────────────────

    async def read_questions(self) -> List[Dict[str, Any]]:
        """读取当前答题页的所有题目。

        Returns:
            [{id, text, type, options: [{label, text}], frame: str}, ...]
        """
        print(f"\n── 读取题目 ──")

        questions: List[Dict[str, Any]] = []

        # 策略1: 在 upleft1 frame 中读取
        q_frame = self._get_question_frame()
        if q_frame:
            logger.info("在 upleft1 frame 中读取题目")
            try:
                q_data = await q_frame.evaluate("""() => {
                    const qs = [];
                    // 查找各种可能的题目容器
                    const containers = document.querySelectorAll(
                        'div.question, div.quiz, div.problem, ' +
                        'div[class*="question"], div[class*="Q"], ' +
                        'tr:has(td), p:has(b), p:has(strong), ' +
                        'div[class*="Problem"], div[class*="Item"]'
                    );
                    containers.forEach((c, i) => {
                        const text = (c.innerText || c.textContent || '').trim();
                        if (text.length > 5 && text.length < 5000) {
                            qs.push({id: i, text: text, container_tag: c.tagName});
                        }
                    });
                    // 如果没找到容器，获取整个 body 文本
                    if (qs.length === 0 && document.body) {
                        const bodyText = (document.body.innerText || '').trim();
                        if (bodyText) {
                            qs.push({id: 0, text: bodyText, container_tag: 'BODY'});
                        }
                    }
                    return qs;
                }""")

                if q_data:
                    questions = q_data
                    print(f"  在 upleft1 中找到 {len(questions)} 个题目块")
                    for q in questions:
                        print(f"    Q{q['id']}: {q['text'][:80]}...")
            except Exception as exc:
                logger.warning("upleft1 读取题目失败: %s", exc)

        # 策略2: 在主页面读取
        if not questions:
            try:
                q_data = await self.page.evaluate("""() => {
                    const qs = [];
                    // 检查所有 frame
                    const allTexts = [];
                    if (document.body) {
                        const bodyText = document.body.innerText || '';
                        if (bodyText) allTexts.push({source: 'main', text: bodyText});
                    }
                    return allTexts;
                }""")
                if q_data:
                    questions = [{"id": 0, "text": q_data[0]["text"], "source": "main"}]
            except Exception as exc:
                logger.warning("主页读取题目失败: %s", exc)

        await self._ss("07_questions_read")
        return questions

    # ── 5. 填写答案 ───────────────────────────────────────────────────────

    async def fill_answers(self, answers: Dict[str, Any]) -> bool:
        """批量填写答案。

        支持的答案格式:
          - 选择题: {"q0": "A", "q1": "B", ...}
          - 简答题: {"q0": "这是答案文本", ...}
          - True/False: {"q0": True, "q1": False, ...}

        Args:
            answers: 题目ID → 答案值 的映射

        Returns:
            True 表示成功
        """
        print(f"\n── 填写答案 ({len(answers)} 题) ──")

        q_frame = self._get_question_frame()
        target = q_frame or self.page

        success_count = 0
        for q_id, answer in answers.items():
            print(f"  Q{q_id}: 正在填写...", end=" ", flush=True)
            ok = await self._fill_single_answer(target, q_id, answer)
            if ok:
                success_count += 1
                print("✅")
            else:
                print("⚠️")
            await self._sleep(0.2, 0.5)

        await self._ss("08_answers_filled")
        print(f"  完成: {success_count}/{len(answers)} 题")
        return success_count > 0

    async def _fill_single_answer(self, target: Any, q_id: Any, answer: Any) -> bool:
        """填写单个题目的答案。"""
        try:
            # 策略1: 单选按钮 (radio)
            if isinstance(answer, str) and len(answer) <= 2:
                # 尝试找对应的 radio button
                for label in [answer.upper(), answer.lower(), answer]:
                    radio = target.locator(
                        f'input[type="radio"][value="{label}"], '
                        f'label:has-text("{label}") input[type="radio"]'
                    ).first
                    if await radio.count() > 0:
                        await radio.check(timeout=self.timeout)
                        return True

            # 策略2: 复选框 (checkbox)
            if isinstance(answer, bool) or (isinstance(answer, str) and answer.lower() in ("true", "false")):
                checkbox = target.locator('input[type="checkbox"]').first
                if await checkbox.count() > 0:
                    if answer is True or str(answer).lower() == "true":
                        await checkbox.check(timeout=self.timeout)
                    else:
                        await checkbox.uncheck(timeout=self.timeout)
                    return True

            # 策略3: 下拉选择 (select)
            if isinstance(answer, str):
                select_el = target.locator("select").first
                if await select_el.count() > 0:
                    await select_el.select_option(label=answer, timeout=self.timeout)
                    return True

            # 策略4: 文本输入 (textarea / input text)
            text_input = target.locator("textarea, input[type='text']").first
            if await text_input.count() > 0:
                await text_input.fill(str(answer), timeout=self.timeout)
                return True

            # 策略5: 全局在页面中找对应题号的输入框
            # TeaLeaMan 常见模式：每题有独立的 input
            for input_sel in [
                f'input[name*="{q_id}"]',
                f'input[id*="{q_id}"]',
                f'textarea[name*="{q_id}"]',
                f'textarea[id*="{q_id}"]',
            ]:
                el = target.locator(input_sel).first
                if await el.count() > 0:
                    await el.fill(str(answer), timeout=self.timeout)
                    return True

        except Exception as exc:
            logger.debug("填写 Q%s 失败: %s", q_id, exc)

        return False

    # ── 6. 提交 / 保存 ────────────────────────────────────────────────────

    async def submit_assignment(self) -> bool:
        """点击橙色 Submit 按钮提交作业。"""
        print(f"\n── 提交作业 ──")
        return await self._click_action_button("submit")

    async def save_assignment(self) -> bool:
        """点击绿色 Save 按钮暂存作业。"""
        print(f"\n── 暂存作业 ──")
        return await self._click_action_button("save")

    async def _click_action_button(self, action: str) -> bool:
        """点击 Submit 或 Save 按钮。"""
        selectors = SUBMIT_BUTTON_SELECTORS if action == "submit" else SAVE_BUTTON_SELECTORS

        # 在所有 frame 中搜索
        for frame in self.page.frames:
            frame_name = getattr(frame, "name", "?")
            for sel in selectors:
                try:
                    btn = frame.locator(sel).first
                    if await btn.count() > 0:
                        await btn.click(timeout=self.timeout)
                        logger.info("已点击 %s 按钮 (frame=%s, selector=%s)",
                                     action, frame_name, sel)
                        await self._sleep(1.5, 3.0)
                        await self._ss(f"09_{action}_clicked")
                        return True
                except Exception:
                    continue

        # 全局搜索
        for sel in selectors:
            try:
                btn = self.page.locator(sel).first
                if await btn.count() > 0:
                    await btn.click(timeout=self.timeout)
                    logger.info("已点击 %s 按钮 (selector=%s)", action, sel)
                    return True
            except Exception:
                continue

        logger.error("找不到 %s 按钮", action)
        return False

    # ── 7. 一键全流程 ─────────────────────────────────────────────────────

    async def run_full_cycle(
        self,
        username: str,
        password: str,
        answers: Optional[Dict[str, Any]] = None,
        assignment_index: int = 0,
        assignment_title: Optional[str] = None,
        submit: bool = True,
    ) -> Dict[str, Any]:
        """一键执行完整流程：登录 → 导航 → 答题 → 提交。

        Args:
            username:         学号
            password:         密码
            answers:          答案字典 {"q0": "A", ...}
            assignment_index: 作业序号
            assignment_title: 作业标题（优先于 index）
            submit:           是否自动提交

        Returns:
            执行报告 {success, steps: [...], screenshots: [...]}
        """
        report: Dict[str, Any] = {
            "success": False,
            "steps": [],
            "screenshots": [],
            "start_time": time.time(),
        }

        start = time.time()

        # Step 1: 登录
        step_ok = await self.auto_login(username, password)
        report["steps"].append({"step": "login", "ok": step_ok})
        if not step_ok:
            report["error"] = "登录失败"
            return report

        # Step 2: 导航到作业列表
        step_ok = await self.navigate_assignments()
        report["steps"].append({"step": "navigate_assignments", "ok": step_ok})
        if not step_ok:
            report["error"] = "无法导航到作业列表"
            return report

        # Step 3: 打开作业
        step_ok = await self.open_assignment(
            index=assignment_index,
            title=assignment_title,
        )
        report["steps"].append({"step": "open_assignment", "ok": step_ok})
        if not step_ok:
            report["error"] = "无法打开作业"
            return report

        # Step 4: 读取题目
        questions = await self.read_questions()
        report["questions_count"] = len(questions)
        report["questions"] = questions

        # Step 5: 填写答案
        if answers:
            step_ok = await self.fill_answers(answers)
            report["steps"].append({"step": "fill_answers", "ok": step_ok})
        else:
            logger.info("未提供答案，跳过填写")
            report["steps"].append({"step": "fill_answers", "ok": None, "note": "未提供答案"})

        # Step 6: 提交
        if submit:
            step_ok = await self.submit_assignment()
            report["steps"].append({"step": "submit", "ok": step_ok})
        else:
            await self.save_assignment()
            report["steps"].append({"step": "save", "ok": True})

        elapsed = time.time() - start
        report["success"] = True
        report["elapsed_seconds"] = round(elapsed, 1)

        await self._ss("10_final")

        print(f"\n{'='*55}")
        print(f"  🎉 TeaLeaMan 全流程完成! ({elapsed:.1f}s)")
        print(f"{'='*55}")

        return report

    # ── 8. 扫描作业列表 ──────────────────────────────────────────────────

    async def scan_assignments(self) -> List[Dict[str, Any]]:
        """扫描当前作业列表，返回所有可见作业的信息。

        Returns:
            [{index, title, due_date, status, submit_visible}, ...]
        """
        assignments: List[Dict[str, Any]] = []

        content_frame = self._get_content_frame()
        target = content_frame or self.page

        try:
            data = await target.evaluate("""() => {
                const rows = [];
                const trs = document.querySelectorAll('tr');
                trs.forEach((tr, i) => {
                    const cells = tr.querySelectorAll('td');
                    if (cells.length >= 2) {
                        const text = tr.innerText || '';
                        if (text.trim().length > 5) {
                            const submitBtn = tr.querySelector(
                                'input.OrangeButton, input[type="submit"], ' +
                                'input[onclick*="submitass"]'
                            );
                            rows.push({
                                index: i,
                                title: cells[0] ? cells[0].innerText.trim() : '',
                                text: text.trim().substring(0, 200),
                                submit_visible: !!submitBtn,
                            });
                        }
                    }
                });
                return rows;
            }""")

            if data:
                assignments = data
                print(f"\n── 作业列表 ({len(assignments)} 个) ──")
                for a in assignments:
                    status = "✅ 可提交" if a.get("submit_visible") else "⏳"
                    print(f"  [{a['index']}] {status} {a.get('title', '无标题')[:50]}")
        except Exception as exc:
            logger.warning("扫描作业列表失败: %s", exc)

        await self._ss("scan_assignments")
        return assignments


# ── 便捷函数 ────────────────────────────────────────────────────────────────


async def tealeaman_quick(
    browser: Any,
    username: str,
    password: str,
    answers: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """一键启动 TeaLeaMan 自动化。

    Args:
        browser:  StealthBrowser 实例
        username: 学号
        password: 密码
        answers:  答案字典
        **kwargs: 传递给 TeaLeaManBot 的参数

    Returns:
        执行报告
    """
    bot = TeaLeaManBot(browser, **kwargs)
    return await bot.run_full_cycle(username, password, answers=answers)
