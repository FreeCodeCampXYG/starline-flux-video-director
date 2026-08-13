#!/usr/bin/env python3
"""用 Playwright 在人工登录后的 BFL Playground 中循环生成并提取末帧。"""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, sync_playwright


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CHROME = Path(r"D:\Programs\ChromeGo\TorBrowserPortable\chrome\Chrome-bin\chrome.exe")
DEFAULT_PROFILE = Path(r"D:\Programs\ChromeGo\TorBrowserPortable\v2rayn\v2rayn2025\chrome-data")
DEFAULT_PROXY = "socks5://127.0.0.1:10808"
if os.name == "nt":
    _YTDLP_DATA_HOME = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    DEFAULT_YTDLP = _YTDLP_DATA_HOME / "starline" / "tools" / "yt-dlp" / "yt-dlp.exe"
else:
    _YTDLP_DATA_HOME = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    DEFAULT_YTDLP = _YTDLP_DATA_HOME / "starline" / "tools" / "yt-dlp" / "yt-dlp"
DEFAULT_PROXY_BYPASS = "localhost;127.*;10.*;172.16.*;172.17.*;172.18.*;172.19.*;172.20.*;172.21.*;172.22.*;172.23.*;172.24.*;172.25.*;172.26.*;172.27.*;172.28.*;172.29.*;172.30.*;172.31.*;192.168.*"
PLAYGROUND_URL = "https://dashboard.bfl.ai/"
HUMAN_PACE_MIN_SECONDS = 1.0
HUMAN_PACE_MAX_SECONDS = 3.0
UPLOAD_SETTLE_MIN_SECONDS = 8.0
UPLOAD_SETTLE_MAX_SECONDS = 12.0
SUBMIT_FAILURE_MARKERS = (
    "system_error",
    "service issue",
    "bfl returned status",
    "over capacity",
    "temporarily shedding requests",
    "generation failed",
    "request failed",
    "rate limited",
    "sending requests too quickly",
)
SUBMIT_ACTIVE_MARKERS = ("queued", "generating", "cancel")


def human_pause(page: Page, multiplier: float = 1.0) -> None:
    """在配置范围内独立生成随机小数等待，模拟自然人工操作节奏。"""
    del multiplier  # 保留调用兼容性；所有交互严格限制在统一随机范围内。
    seconds = random.uniform(HUMAN_PACE_MIN_SECONDS, HUMAN_PACE_MAX_SECONDS)
    print(f"人工节奏等待：{seconds:.2f}s")
    page.wait_for_timeout(int(seconds * 1000))


def load_project(path: Path) -> dict:
    """读取项目导演配置。"""
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_prompt(project_path: Path, shot: dict) -> str:
    """优先读取外置长提示词；兼容 Markdown text 代码块与纯文本文件。"""
    prompt_file = shot.get("prompt_file")
    if not prompt_file:
        return shot["prompt"]
    prompt_path = (project_path.parent / prompt_file).resolve()
    text = prompt_path.read_text(encoding="utf-8")
    start = text.find("```text\n")
    if start >= 0:
        end = text.find("\n```", start + 8)
        if end < 0:
            raise RuntimeError(f"外置提示词代码块未闭合：{prompt_path}")
        prompt = text[start + 8:end].strip()
    else:
        prompt = text.strip()
    if not prompt:
        raise RuntimeError(f"外置提示词为空：{prompt_path}")
    return prompt


def first_visible(page: Page, selectors: list[str], timeout: int = 1500):
    """在多个页面版本选择器中返回第一个可见元素。"""
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            if locator.is_visible(timeout=timeout):
                return locator
        except PlaywrightTimeoutError:
            continue
    return None


def generate_button_candidates(page: Page):
    """优先返回 BFL 明确标注的 Generate 按钮；仅在缺少 aria-label 时按文字回退。"""
    primary = page.locator('button[aria-label="Generate"]')
    if primary.count() > 0:
        return primary
    return page.locator('button:has(span:text-is("Generate"))')


def generate_button_ready(button) -> bool:
    """按钮只有可见、非 busy、无 disabled 且 enabled 时才可提交。"""
    busy = (button.get_attribute("aria-busy") or "false").strip().lower()
    return (
        button.is_visible()
        and busy == "false"
        and button.get_attribute("disabled") is None
        and button.is_enabled()
    )


def ensure_playground(page: Page) -> None:
    """确认已进入 Playground；登录和验证码由用户完成。"""
    page.goto(PLAYGROUND_URL, wait_until="domcontentloaded")
    human_pause(page, 3.0)
    if first_visible(page, ["text=Sign in", "text=Log in", "text=登录"], timeout=800):
        print("请在打开的 ChromeGo 窗口完成 Google/BFL 登录，完成后回到终端按 Enter。")
        input()
        page.goto(PLAYGROUND_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(2500)
    # 首页可能落在组织 Dashboard；优先读取真实项目链接并直接导航，避免侧栏点击被遮挡或失焦。
    if not first_visible(page, ["textarea", "[contenteditable='true']"], timeout=1200):
        playground_link = first_visible(
            page,
            ["a[data-sidebar='menu-button'][href*='/playground']", "a[href*='/playground']", "text=Playground"],
            timeout=3000,
        )
        if playground_link:
            href = playground_link.get_attribute("href")
            if href:
                target = urljoin(page.url, href)
                print(f"从 Dashboard 进入 Playground：{target}")
                page.goto(target, wait_until="domcontentloaded")
            else:
                playground_link.click()
            human_pause(page, 3.0)
    ready_deadline = time.monotonic() + 60
    while time.monotonic() < ready_deadline:
        if first_visible(page, ["textarea", "[contenteditable='true']"], timeout=1200):
            break
        # 页面若因客户端 hydration 回到 Dashboard，再次解析当前项目的真实 Playground URL。
        fallback_link = first_visible(page, ["a[href*='/playground']"], timeout=600)
        if fallback_link:
            href = fallback_link.get_attribute("href")
            if href:
                page.goto(urljoin(page.url, href), wait_until="domcontentloaded")
        human_pause(page)
    if not first_visible(page, ["textarea", "[contenteditable='true']"], timeout=3000):
        page.screenshot(path=str(PROJECT_ROOT / "work" / "playground-not-ready.png"), full_page=True)
        raise RuntimeError("未找到 Playground 提示词输入框，已保存 work/playground-not-ready.png")


def fill_prompt(page: Page, prompt: str) -> None:
    """填入提示词。"""
    box = first_visible(page, ["textarea", "[contenteditable='true']"], timeout=3000)
    if box is None:
        raise RuntimeError("未找到提示词输入框")
    # 播放器预览层可能覆盖输入框，直接聚焦并填值，不依赖鼠标点击命中。
    box.focus()
    box.wait_for(state="visible", timeout=10000)
    box.scroll_into_view_if_needed()
    box.evaluate("""(el, value) => {
        const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
        setter.call(el, value);
        el.dispatchEvent(new InputEvent('input', {bubbles: true, inputType: 'insertText', data: value}));
        el.dispatchEvent(new Event('change', {bubbles: true}));
    }""", prompt)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if box.input_value() == prompt:
            page.wait_for_timeout(1200)
            if box.input_value() == prompt:
                human_pause(page, 2.0)
                page.screenshot(path=str(PROJECT_ROOT / "work" / "prompt-filled.png"), full_page=True)
                return
        page.wait_for_timeout(250)
    page.screenshot(path=str(PROJECT_ROOT / "work" / "prompt-fill-failed.png"), full_page=True)
    raise RuntimeError("提示词未完成写入，已保存 work/prompt-fill-failed.png")


def choose_model(page: Page) -> None:
    """选择 FLUX 3（若当前已选则保持）。"""
    current = first_visible(page, ["text=FLUX 3", "text=FLUX3"], timeout=1200)
    if current:
        return
    selector = first_visible(page, ["select", "[role='combobox']"], timeout=1500)
    if selector:
        try:
            selector.select_option(label="FLUX 3")
        except Exception:
            selector.click()
            option = first_visible(page, ["text=FLUX 3", "text=FLUX3"], timeout=1500)
            if option:
                option.click()
    else:
        raise RuntimeError("未找到模型选择器，请人工选择 FLUX 3")


def wait_until_queue_idle(page: Page, timeout_ms: int) -> None:
    """等待既有 Playground 任务结束，排队期间绝不重置或重复提交。"""
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        cancel = page.get_by_role("button", name="Cancel")
        generating = page.get_by_role("button").filter(has_text="Generating")
        cancel_visible = cancel.count() > 0 and cancel.first.is_visible()
        generating_visible = generating.count() > 0 and generating.first.is_visible()
        card_texts = page.locator("[data-entry-id], article, [role='article']").all_inner_texts()
        active_card_visible = any(classify_task_text(text) == "active" for text in card_texts)
        if not cancel_visible and not generating_visible and not active_card_visible:
            return
        print("检测到现有排队/生成任务，仅等待，不 Reset、不点击 Generate")
        page.wait_for_timeout(5000)
    raise RuntimeError("Playground 仍在生成或排队，未执行 Reset，也未重复提交")


def reset_all_inputs(page: Page) -> None:
    """真实点击 Reset，并确认提示词已清空。"""
    reset = page.get_by_role("button", name="Reset all inputs")
    if reset.count() == 0:
        raise RuntimeError("未找到 Reset all inputs")
    reset.first.click()
    human_pause(page, 2.0)
    box = page.locator("textarea").first
    box.wait_for(state="visible", timeout=10000)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if box.input_value() == "":
            page.wait_for_timeout(800)
            if box.input_value() == "":
                return
        page.wait_for_timeout(250)
    raise RuntimeError("Reset 后提示词没有归零，停止提交")


def close_parameter_panel(page: Page, label: str, button) -> None:
    """像人工操作一样关闭当前参数面板，并确认折叠状态。"""
    if button.get_attribute("aria-expanded") != "true":
        return
    close = page.get_by_role("button", name=f"Close {label}")
    if close.count() > 0 and close.first.is_visible():
        close.first.click()
    else:
        button.click()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if button.get_attribute("aria-expanded") != "true":
            human_pause(page, 1.0)
            return
        page.wait_for_timeout(250)
    raise RuntimeError(f"参数面板未能关闭：{label}")


def set_parameter(page: Page, label: str, value: object) -> None:
    """通过参数按钮选择目标值，并读取按钮文本确认状态。"""
    target = str(value).lower() if isinstance(value, bool) else str(value)
    button = page.get_by_role("button").filter(has_text=label).first
    if button.count() == 0:
        raise RuntimeError(f"未找到参数按钮：{label}")
    current = " ".join((button.inner_text() or "").split())
    if target.lower() in current.lower():
        close_parameter_panel(page, label, button)
        return
    button.click()
    human_pause(page, 1.0)
    number_input = page.locator("input[type='number']:visible").last
    if number_input.count() > 0:
        minimum = number_input.get_attribute("min")
        maximum = number_input.get_attribute("max")
        try:
            numeric_target = float(target)
            within_min = minimum is None or numeric_target >= float(minimum)
            within_max = maximum is None or numeric_target <= float(maximum)
        except ValueError:
            within_min = within_max = False
        if within_min and within_max:
            number_input.fill(target)
            human_pause(page, 0.75)
            number_input.press("Enter")
            human_pause(page, 1.0)
            updated = " ".join((button.inner_text() or "").split())
            if target.lower() in updated.lower():
                if label == "Duration":
                    slider = page.locator('[role="slider"][aria-valuemin="5"][aria-valuemax="20"]:visible').last
                    if number_input.input_value() != target or slider.count() == 0 or slider.get_attribute("aria-valuenow") != target:
                        raise RuntimeError("Duration 三重校验失败：按钮、数字框与滑杆未同步")
                close_parameter_panel(page, label, button)
                return
    candidates = [
        page.get_by_role("option", name=target, exact=True),
        page.get_by_role("menuitem", name=target, exact=True),
        page.get_by_role("radio", name=target, exact=True),
        page.get_by_text(target, exact=True),
    ]
    selected = False
    for candidate in candidates:
        if candidate.count() > 0 and candidate.last.is_visible():
            candidate.last.click()
            human_pause(page, 1.0)
            selected = True
            break
    if not selected:
        diagnostic = PROJECT_ROOT / "work" / f"parameter-{label.lower().replace(' ', '-')}.html"
        diagnostic.parent.mkdir(parents=True, exist_ok=True)
        diagnostic.write_text(page.content(), encoding="utf-8")
        page.screenshot(path=str(diagnostic.with_suffix(".png")), full_page=True)
        page.keyboard.press("Escape")
        raise RuntimeError(f"参数 {label} 未找到目标值：{target}；已保存诊断 HTML/截图")
    human_pause(page, 1.0)
    updated = " ".join((button.inner_text() or "").split())
    if target.lower() not in updated.lower():
        raise RuntimeError(f"参数 {label} 设置失败：期望 {target}，页面显示 {updated}")
    close_parameter_panel(page, label, button)


def apply_request_parameters(page: Page, defaults: dict, *, include_duration: bool = True) -> None:
    """同步 Playground 参数；媒体优先流程可把 Duration 留到最后单独设置。"""
    mapping = [
        ("Aspect ratio", defaults.get("aspect_ratio")),
        ("Resolution", defaults.get("resolution")),
        ("Generate audio", defaults.get("generate_audio")),
        ("Draft", defaults.get("draft")),
    ]
    if include_duration:
        mapping.insert(1, ("Duration", defaults.get("duration")))
    for label, value in mapping:
        if value is not None:
            set_parameter(page, label, value)
            human_pause(page, 0.5)
    tolerance = defaults.get("safety_tolerance")
    if tolerance is not None:
        advanced = page.get_by_role("button").filter(has_text="advanced")
        if advanced.count() > 0 and advanced.first.is_visible():
            advanced.first.click()
            human_pause(page, 1.0)
        set_parameter(page, "Safety tolerance", tolerance)
    human_pause(page, 3.0)
    page.screenshot(path=str(PROJECT_ROOT / "work" / "parameters-applied.png"), full_page=True)


def report_request_parameters(page: Page) -> None:
    """打印提交前页面实际显示的参数值，作为可见门禁。"""
    labels = ["Aspect ratio", "Duration", "Resolution", "Generate audio", "Draft", "Safety tolerance"]
    for label in labels:
        button = page.get_by_role("button").filter(has_text=label).first
        if button.count() > 0:
            print(f"页面参数：{' '.join((button.inner_text() or '').split())}")


def set_file_if_needed(page: Page, image: Path | None) -> None:
    """通过 Start frame 按钮上传末帧，并用页面缩略图状态做硬验证。"""
    if image is None:
        return
    image = image.resolve()
    if not image.is_file() or image.stat().st_size == 0:
        raise RuntimeError(f"Start frame 文件无效：{image}")
    attach = page.get_by_role("button", name="Attach start frame")
    if attach.count() == 0 or not attach.first.is_visible():
        raise RuntimeError("未找到 Attach start frame 按钮；未点击 Generate")
    with page.expect_file_chooser(timeout=10000) as chooser_info:
        attach.first.click()
    chooser_info.value.set_files(str(image))
    print(f"已向文件选择器提交 Start frame：{image.name}")
    deadline = time.monotonic() + 120
    verified_src: str | None = None
    while time.monotonic() < deadline:
        replace = page.get_by_role("button", name="Replace start frame")
        remove = page.get_by_role("button", name="Remove start frame")
        thumbnail = page.locator('img[alt="Input image"]')
        if replace.count() > 0 and remove.count() > 0 and thumbnail.count() > 0:
            src = thumbnail.first.get_attribute("src") or ""
            if src.startswith("https://cdn.bfl.ai/"):
                # CDN 缩略图出现只说明上传已返回；页面还可能在同步媒体状态。
                if verified_src is None:
                    verified_src = src
                    print("Start frame 已出现 BFL CDN 缩略图，开始上传后稳定观察")
                elif src == verified_src:
                    settle_seconds = random.uniform(UPLOAD_SETTLE_MIN_SECONDS, UPLOAD_SETTLE_MAX_SECONDS)
                    print(f"Start frame CDN 地址连续稳定；额外等待 {settle_seconds:.2f}s 后才允许 Generate")
                    page.wait_for_timeout(int(settle_seconds * 1000))
                    # React 可能在稳定等待期间重绘媒体芯片；旧 Locator 会等待已移除节点直到超时。
                    # 必须重新查询完整上传契约，元素短暂消失时回到观察循环，严禁误判为已上传。
                    final_thumbnail = page.locator('img[alt="Input image"]')
                    final_replace = page.get_by_role("button", name="Replace start frame")
                    final_remove = page.get_by_role("button", name="Remove start frame")
                    if (
                        final_thumbnail.count() == 0
                        or final_replace.count() == 0
                        or final_remove.count() == 0
                    ):
                        verified_src = None
                        print("稳定等待期间 Start frame 芯片被页面重绘，重新观察上传证据")
                        page.wait_for_timeout(500)
                        continue
                    final_src = final_thumbnail.first.get_attribute("src", timeout=2000) or ""
                    generate = first_visible(page, ['button[aria-label=\"Generate\"]'], timeout=1500)
                    if final_src == verified_src and generate is not None and generate_button_ready(generate):
                        print("Start frame 上传、页面同步和 Generate 可用状态均已稳定")
                        page.screenshot(path=str(PROJECT_ROOT / "work" / "start-frame-settled.png"), full_page=True)
                        return
                    verified_src = None
                    print("上传后页面状态发生变化，重新等待稳定证据")
        page.wait_for_timeout(500)
    page.screenshot(path=str(PROJECT_ROOT / "work" / "start-frame-upload-failed.png"), full_page=True)
    raise RuntimeError("Start frame 120 秒内未出现已上传缩略图；未点击 Generate")


def bfl_image_reuse_buttons(page: Page):
    """返回结果卡片内的站内图片复用入口；它不是 Start frame 上传成功证据。"""
    return page.locator('button[aria-label="Use in FLUX 3 Video"]')


def task_board_snapshot(page: Page) -> tuple[str, ...]:
    """采集右侧结果/队列卡片摘要，用于确认真实创建了新任务。"""
    cards = page.locator("[data-entry-id]").evaluate_all(
        """els => els.map(el => `id:${el.getAttribute('data-entry-id') || ''}`)
            .filter(value => value !== 'id:')"""
    )
    if cards:
        return tuple(sorted(cards))
    # 页面窄布局可能没有 data-entry-id；去掉不断变化的时间文本再建立卡片指纹。
    return tuple(
        sorted(page.locator("article, [role='article']").evaluate_all(
            """els => els.map(el => (el.innerText || '')
                .replace(/\\s+/g, ' ').trim()
                .replace(/(?:JUST NOW|\\d+\\s*(?:S|M|H)\\s*AGO|\\d{1,2}:\\d{2})/ig, '<time>'))
                .filter(text => text && /(?:PROMPT|VIDEO|system_error|Service issue|TYPICAL LATENCY)/i.test(text))"""
        ))
    )


def classify_task_text(text: str) -> str:
    """把任务卡文字归类为失败、活动、完成或未知，忽略控制台页面噪声。"""
    normalized = " ".join(text.lower().split())
    if any(marker in normalized for marker in SUBMIT_FAILURE_MARKERS):
        return "failed"
    if any(marker in normalized for marker in SUBMIT_ACTIVE_MARKERS):
        return "active"
    if "video" in normalized and ("download" in normalized or "latency" in normalized):
        return "complete"
    return "unknown"


def prompt_task_records(page: Page, prompt: str) -> tuple[tuple[str, str, str], ...]:
    """只读取与当前提示词开头匹配的右侧任务，避免历史任务干扰重试。"""
    needle = " ".join(prompt.split())[:120].lower()
    raw = page.locator("[data-entry-id], article, [role='article']").evaluate_all(
        """(els, needle) => els.map((el, index) => {
            const text = (el.innerText || '').replace(/\\s+/g, ' ').trim();
            const owner = el.closest('[data-entry-id]') || el;
            const id = owner.getAttribute && owner.getAttribute('data-entry-id');
            return {key: id ? `id:${id}` : `fallback:${index}:${text.slice(0, 240)}`, text};
        }).filter(item => item.text.toLowerCase().includes(needle))""",
        needle,
    )
    unique: dict[str, tuple[str, str, str]] = {}
    for item in raw:
        key = item["key"]
        text = item["text"]
        unique[key] = (key, classify_task_text(text), text)
    return tuple(unique.values())


def wait_for_task_creation(
    page: Page,
    before: tuple[str, ...],
    before_record_states: dict[str, str],
    prompt: str,
    settle_seconds: float,
    response_statuses: list[int],
) -> tuple[str, str]:
    """等待任务成功入队或明确失败；未知状态绝不转成可重试失败。"""
    deadline = time.monotonic() + 90
    evidence_at: float | None = None
    while time.monotonic() < deadline:
        failed_http = next((status for status in response_statuses if status in {502, 503, 504}), None)
        if failed_http is not None:
            return "failed", f"/api/playground/generate 返回 HTTP {failed_http}"
        records = prompt_task_records(page, prompt)
        new_records = [record for record in records if record[0] not in before_record_states]
        failed_record = next(
            (
                record for record in records
                if record[1] == "failed" and before_record_states.get(record[0]) != "failed"
            ),
            None,
        )
        if failed_record is not None:
            return "failed", failed_record[2][:300]
        board_changed = task_board_snapshot(page) != before
        # 队列整体变化可能来自其他历史任务；只有当前 Prompt 的新卡片才算本次创建成功。
        created = bool(new_records)
        if created:
            if evidence_at is None:
                evidence_at = time.monotonic()
                print("已检测到右侧任务队列变化，开始稳定观察")
            elif time.monotonic() - evidence_at >= settle_seconds:
                print("任务队列已稳定，确认已提交")
                return "submitted", "右侧任务卡已创建并稳定"
        else:
            evidence_at = None
            if board_changed:
                print("右侧队列有变化，但尚未匹配到当前 Prompt；继续观察，不判定成功")
        page.wait_for_timeout(500)
    page.screenshot(path=str(PROJECT_ROOT / "work" / "submission-state-unknown.png"), full_page=True)
    return "unknown", "90 秒内未确认右侧任务创建；已保存截图"


def wait_for_generate_retry_ready(page: Page, prompt: str, timeout_seconds: float = 120) -> None:
    """失败后等待按钮恢复，并确保当前提示词没有活动任务。"""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        active = any(record[1] == "active" for record in prompt_task_records(page, prompt))
        button = first_visible(page, ['button[aria-label="Generate"]'], timeout=800)
        if not active and button is not None and generate_button_ready(button):
            return
        page.wait_for_timeout(1000)
    raise RuntimeError("任务失败后 Generate 未在 120 秒内恢复，停止自动重试")


def click_generate(
    page: Page,
    prompt: str,
    settle_seconds: float,
    max_retries: int,
    retry_delay_min: float,
    retry_delay_max: float,
) -> None:
    """点击 Generate；仅在 502/503/504 或当前任务卡明确失败时有界重试。"""
    # 当前 BFL DOM 的文字位于三层 span 内；实际点击目标必须向上解析到 button。
    # aria-label 是首选契约，精确文本 + 最近 button 是页面改版后的安全回退。
    for attempt in range(max_retries + 1):
        candidates = generate_button_candidates(page)
        ranked: list[tuple[float, object, dict]] = []
        for index in range(candidates.count()):
            candidate = candidates.nth(index)
            if not generate_button_ready(candidate):
                continue
            candidate_box = candidate.bounding_box()
            if candidate_box is not None:
                ranked.append((candidate_box["x"], candidate, candidate_box))
        if not ranked:
            raise RuntimeError("未找到可用的 Generate 按钮；可能仍在生成或排队，未重复提交")
        _, button, selected_box = min(ranked, key=lambda item: item[0])
        board_before = task_board_snapshot(page)
        prompt_records_before = {record[0]: record[1] for record in prompt_task_records(page, prompt)}
        response_statuses: list[int] = []

        def record_generate_response(response) -> None:
            if "/api/playground/generate" in response.url:
                response_statuses.append(response.status)

        page.on("response", record_generate_response)
        print(f"选择左侧 Generate：x={selected_box['x']:.1f}, y={selected_box['y']:.1f}, 尝试={attempt + 1}/{max_retries + 1}")
        # 右侧历史视频预览层可能拦截鼠标命中，但按钮仍是可用的；强制命中目标按钮。
        deadline = time.monotonic() + 30
        clicked = False
        while time.monotonic() < deadline:
            if generate_button_ready(button):
                box = button.bounding_box()
                if box is None:
                    raise RuntimeError("无法读取 Generate 按钮坐标")
                click_x = box["x"] + box["width"] / 2
                click_y = box["y"] + box["height"] / 2
                # 动态找出当前坐标上真正拦截鼠标的元素，而不是依赖易变的 CSS 类名。
                button.evaluate("""(target, {x, y}) => {
                    window.__bflPointerRestore = [];
                    window.__bflBlockers = [];
                    for (let round = 0; round < 20; round++) {
                        const top = document.elementFromPoint(x, y);
                        if (!top || top === target || target.contains(top)) break;
                        window.__bflBlockers.push(`${top.tagName}.${String(top.className).slice(0, 160)}`);
                        window.__bflPointerRestore.push([top, top.style.pointerEvents]);
                        top.style.pointerEvents = 'none';
                    }
                }""", {"x": click_x, "y": click_y})
                human_pause(page)
                try:
                    hit = button.evaluate("""(target, {x, y}) => {
                        const top = document.elementFromPoint(x, y);
                        return Boolean(top && (top === target || target.contains(top)));
                    }""", {"x": click_x, "y": click_y})
                    if not hit:
                        blockers = page.evaluate("window.__bflBlockers || []")
                        print(f"Generate 坐标拦截元素：{blockers}")
                        raise RuntimeError("清理覆盖层后 Generate 仍未成为鼠标命中目标")
                    page.mouse.click(click_x, click_y)
                    clicked = True
                finally:
                    page.evaluate("""() => {
                        for (const [el, value] of (window.__bflPointerRestore || [])) el.style.pointerEvents = value;
                        delete window.__bflPointerRestore;
                        delete window.__bflBlockers;
                    }""")
                break
            page.wait_for_timeout(500)
        if not clicked:
            page.remove_listener("response", record_generate_response)
            page.screenshot(path=str(PROJECT_ROOT / "work" / "generate-disabled.png"), full_page=True)
            raise RuntimeError("Generate 仍为 disabled；未强制点击，已保存诊断截图")

        print("点击已被页面接收，等待右侧任务卡或明确失败响应")
        outcome, reason = wait_for_task_creation(
            page, board_before, prompt_records_before, prompt, settle_seconds, response_statuses
        )
        page.remove_listener("response", record_generate_response)
        if outcome == "submitted":
            return
        if outcome == "unknown":
            raise RuntimeError(f"提交状态不确定：{reason}；为避免重复任务，不自动重试")
        page.screenshot(path=str(PROJECT_ROOT / "work" / f"submit-failed-attempt-{attempt + 1}.png"), full_page=True)
        if attempt >= max_retries:
            raise RuntimeError(f"提交明确失败且已达到重试上限：{reason}")
        print(f"提交明确失败：{reason}")
        # HTTP 502/503/504 是通用网关/容量故障；只有当前页面明确渲染 Rate limited 卡片时才走 Retry 按钮。
        rate_limited = "rate limited" in reason.lower() or "too quickly" in reason.lower()
        if rate_limited:
            # 保留表单，只恢复当前错误卡；不得 Reset 或重新上传。
            click_rate_limit_retry(page, timeout_seconds=30)
            wait_main_generate_enabled(page)
            delay = random.uniform(10.0, 20.0)
            print(f"错误卡 Retry 已恢复表单；等待 {delay:.2f}s 后再点一次主 Generate")
            page.wait_for_timeout(int(delay * 1000))
        else:
            # 普通 5xx 没有 Retry 卡；等待当前任务无活动态且主按钮恢复后，按有界退避重试一次。
            wait_for_generate_retry_ready(page, prompt)
            delay = random.uniform(retry_delay_min, retry_delay_max)
            print(f"等待服务恢复：{delay:.2f}s；随后只重试一次当前提交")
            page.wait_for_timeout(int(delay * 1000))


def click_rate_limit_retry(page: Page, timeout_seconds: float = 20) -> None:
    """点击当前 Rate limited 错误卡内的 Retry，让页面恢复请求表单状态。"""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        error_panel = page.locator("div.rounded-md.border.p-4").filter(has_text="Rate limited").filter(has_text="sending requests too quickly")
        retry = error_panel.get_by_role("button", name="Retry", exact=True)
        for index in range(retry.count()):
            candidate = retry.nth(index)
            if candidate.is_visible() and candidate.is_enabled():
                candidate.scroll_into_view_if_needed()
                human_pause(page)
                candidate.click()
                print("已点击 Rate limited 错误卡内 Retry，等待主 Generate 恢复")
                return
        page.wait_for_timeout(500)
    raise RuntimeError("20 秒内未找到当前 Rate limited 卡片内可见 Retry；未点击主 Generate")


def wait_main_generate_enabled(page: Page, timeout_seconds: float = 60) -> None:
    """等待 Retry 完成页面恢复，主 Generate 必须真实 enabled。"""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        button = first_visible(page, ['button[aria-label="Generate"]'], timeout=800)
        if button is not None and generate_button_ready(button):
            return
        page.wait_for_timeout(1000)
    raise RuntimeError("点击错误卡 Retry 后主 Generate 未恢复 enabled；停止")


def retry_rate_limited_task(page: Page, prompt: str, cooldown_min: float, cooldown_max: float) -> None:
    """恢复已有 Rate limited 卡片，再按人工节奏点击一次主 Generate。"""
    box = page.locator("textarea").first
    if box.count() == 0 or box.input_value() != prompt:
        raise RuntimeError("当前页面 Prompt 与目标镜头不一致，禁止点击失败卡片 Retry")
    thumbnail = page.locator('img[alt="Input image"]').first
    if thumbnail.count() == 0 or not (thumbnail.get_attribute("src") or "").startswith("https://cdn.bfl.ai/"):
        raise RuntimeError("当前页面没有已稳定的 BFL Start frame，禁止点击失败卡片 Retry")
    click_rate_limit_retry(page)
    wait_main_generate_enabled(page)
    delay = random.uniform(cooldown_min, cooldown_max)
    print(f"主 Generate 已恢复；按人工节奏等待 {delay:.2f}s 后只点击一次")
    page.wait_for_timeout(int(delay * 1000))
    click_generate(page, prompt, 30.0, 0, cooldown_min, cooldown_max)


def prompt_task_video_sources(page: Page, prompt: str) -> tuple[str, ...]:
    """只提取当前 Prompt 对应任务卡内的视频地址，避免误下历史成片。"""
    needle = " ".join(prompt.split())[:120].lower()
    sources = page.locator("[data-entry-id], article, [role='article']").evaluate_all(
        r"""(els, needle) => els.flatMap(el => {
            const text = (el.innerText || '').replace(/\s+/g, ' ').trim().toLowerCase();
            if (!text.includes(needle)) return [];
            const owner = el.closest('[data-entry-id]') || el;
            return [...owner.querySelectorAll('video')]
                .map(video => video.currentSrc || video.src || '')
                .filter(src => /^https?:\/\//i.test(src));
        })""",
        needle,
    )
    return tuple(dict.fromkeys(sources))


def validate_downloaded_video(video: Path, ffprobe: str) -> None:
    """校验 MP4 容器头和可解码视频流，拒绝把错误页伪装成成片。"""
    if not video.is_file() or video.stat().st_size < 1024:
        raise RuntimeError("下载结果过小，不是有效视频")
    header = video.read_bytes()[:32]
    if b"ftyp" not in header:
        raise RuntimeError("下载结果缺少 MP4 ftyp 容器头，可能是 HTML/错误响应")
    probe = subprocess.run(
        [ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name,width,height", "-show_entries", "format=duration", "-of", "json", str(video)],
        capture_output=True,
        text=True,
        check=False,
    )
    if probe.returncode != 0:
        raise RuntimeError(f"FFprobe 无法解析下载结果：{probe.stderr.strip()[:300]}")
    payload = json.loads(probe.stdout or "{}")
    if not payload.get("streams") or float(payload.get("format", {}).get("duration", 0)) <= 0:
        raise RuntimeError("下载结果没有有效视频流或时长")


def download_via_browser(page: Page, url: str, target: Path, timeout_ms: int) -> None:
    """在已登录 Chrome 内 fetch 为 Blob，再触发原生下载，复用 Cookie 与 10808 代理。"""
    with page.expect_download(timeout=timeout_ms) as download_info:
        metadata = page.evaluate(
            """async ({url, filename}) => {
                const response = await fetch(url, {credentials: 'include', cache: 'no-store'});
                if (!response.ok) throw new Error(`video fetch HTTP ${response.status}`);
                const blob = await response.blob();
                if (blob.size < 1024) throw new Error(`video blob too small: ${blob.size}`);
                const objectUrl = URL.createObjectURL(blob);
                const link = document.createElement('a');
                link.href = objectUrl;
                link.download = filename;
                link.style.display = 'none';
                document.body.appendChild(link);
                link.click();
                link.remove();
                setTimeout(() => URL.revokeObjectURL(objectUrl), 60000);
                return {status: response.status, type: blob.type, size: blob.size};
            }""",
            {"url": url, "filename": target.name},
        )
    download = download_info.value
    download.save_as(target)
    print(f"浏览器会话下载完成：HTTP {metadata['status']}，{metadata['size']} bytes，{metadata['type'] or 'unknown type'}")


def download_via_ytdlp(url: str, target: Path, proxy: str, timeout_ms: int, ytdlp: Path) -> None:
    """浏览器 Blob 下载受限时，用 yt-dlp 经 SOCKS5H 代理下载准确的当前任务 URL。"""
    executable = str(ytdlp) if ytdlp.is_file() else (shutil.which("yt-dlp.exe") or shutil.which("yt-dlp"))
    if not executable:
        raise RuntimeError("未找到 yt-dlp，无法执行代理下载回退")
    proxy_url = proxy.replace("socks5://", "socks5h://", 1)
    output_template = str(target) + ".%(ext)s"
    result = subprocess.run(
        [
            executable,
            "--no-playlist",
            "--no-part",
            "--retries", "3",
            "--socket-timeout", str(max(30, min(180, timeout_ms // 1000))),
            "--proxy", proxy_url,
            "--output", output_template,
            "--print", "after_move:filepath",
            url,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp 代理下载失败：{(result.stderr or result.stdout).strip()[:300]}")
    paths = [Path(line.strip()) for line in result.stdout.splitlines() if line.strip()]
    actual = next((path for path in reversed(paths) if path.is_file()), None)
    if actual is None:
        candidates = sorted(target.parent.glob(target.name + ".*"), key=lambda path: path.stat().st_size, reverse=True)
        actual = candidates[0] if candidates else None
    if actual is None:
        raise RuntimeError("yt-dlp 返回成功，但没有找到实际下载文件")
    os.replace(actual, target)


def generation_button_is_disabled(page: Page) -> bool:
    """disabled、aria-busy 或 Playwright 非 enabled 都表示当前不能提交。"""
    button = page.locator('button[aria-label="Generate"]').first
    if button.count() == 0 or not button.is_visible():
        return False
    return not generate_button_ready(button)


def wait_and_download(
    page: Page,
    output: Path,
    timeout_ms: int,
    prompt: str,
    proxy: str,
    ffprobe: str,
    ytdlp: Path,
) -> None:
    """等待当前 Prompt 的视频，代理下载到临时文件并通过容器校验后原子落盘。"""
    deadline = time.monotonic() + timeout_ms / 1000
    stable_source: str | None = None
    stable_since: float | None = None
    while time.monotonic() < deadline:
        if generation_button_is_disabled(page):
            stable_source = None
            stable_since = None
            print("Generate 仍为 disabled：当前任务正在生成，只等待，不下载、不重复提交")
            page.wait_for_timeout(5000)
            continue
        sources = prompt_task_video_sources(page, prompt)
        if sources:
            if stable_source != sources[0]:
                stable_source = sources[0]
                stable_since = time.monotonic()
                print("当前任务已结束，视频地址出现；继续等待地址稳定")
                page.wait_for_timeout(3000)
                continue
            if stable_since is None or time.monotonic() - stable_since < 10:
                page.wait_for_timeout(2000)
                continue
            output.parent.mkdir(parents=True, exist_ok=True)
            partial = output.with_suffix(output.suffix + ".part")
            partial.unlink(missing_ok=True)
            errors: list[str] = []
            try:
                download_via_browser(page, sources[0], partial, timeout_ms)
                validate_downloaded_video(partial, ffprobe)
            except Exception as exc:
                errors.append(f"浏览器下载：{exc}")
                partial.unlink(missing_ok=True)
                try:
                    download_via_ytdlp(sources[0], partial, proxy, timeout_ms, ytdlp)
                    validate_downloaded_video(partial, ffprobe)
                except Exception as ytdlp_exc:
                    errors.append(f"yt-dlp 回退：{ytdlp_exc}")
                    partial.unlink(missing_ok=True)
                    raise RuntimeError("；".join(errors)) from ytdlp_exc
            os.replace(partial, output)
            print(f"已自动下载并验证当前镜头：{output}")
            return
        page.wait_for_timeout(5000)
    raise RuntimeError("等待当前 Prompt 对应的视频结果超时；未下载历史任务")


def wait_and_download_all_matches(
    page: Page,
    output: Path,
    timeout_ms: int,
    prompt: str,
    proxy: str,
    ffprobe: str,
    ytdlp: Path,
    expected_matches: int,
) -> tuple[Path, ...]:
    """只读等待同一 Prompt 的多个重复结果，并分别下载，绝不覆盖或重新提交。"""
    deadline = time.monotonic() + timeout_ms / 1000
    stable_sources: tuple[str, ...] = ()
    stable_since: float | None = None
    while time.monotonic() < deadline:
        if generation_button_is_disabled(page):
            stable_sources = ()
            stable_since = None
            print("仍有匹配任务正在生成；只等待两个候选，不点击 Generate")
            page.wait_for_timeout(5000)
            continue
        sources = prompt_task_video_sources(page, prompt)
        if len(sources) < expected_matches:
            stable_sources = ()
            stable_since = None
            print(f"当前找到 {len(sources)}/{expected_matches} 个匹配视频；继续只读等待")
            page.wait_for_timeout(5000)
            continue
        selected = sources[:expected_matches]
        if selected != stable_sources:
            stable_sources = selected
            stable_since = time.monotonic()
            print(f"已找到 {len(selected)} 个唯一候选地址；继续等待地址稳定")
            page.wait_for_timeout(3000)
            continue
        if stable_since is None or time.monotonic() - stable_since < 10:
            page.wait_for_timeout(2000)
            continue
        saved: list[Path] = []
        for index, source in enumerate(selected, start=1):
            candidate = output.with_name(f"{output.stem}-candidate-{index:02d}{output.suffix}")
            candidate.parent.mkdir(parents=True, exist_ok=True)
            partial = candidate.with_suffix(candidate.suffix + ".part")
            partial.unlink(missing_ok=True)
            errors: list[str] = []
            try:
                download_via_browser(page, source, partial, timeout_ms)
                validate_downloaded_video(partial, ffprobe)
            except Exception as exc:
                errors.append(f"浏览器下载：{exc}")
                partial.unlink(missing_ok=True)
                try:
                    download_via_ytdlp(source, partial, proxy, timeout_ms, ytdlp)
                    validate_downloaded_video(partial, ffprobe)
                except Exception as ytdlp_exc:
                    errors.append(f"yt-dlp 回退：{ytdlp_exc}")
                    partial.unlink(missing_ok=True)
                    raise RuntimeError("；".join(errors)) from ytdlp_exc
            os.replace(partial, candidate)
            saved.append(candidate)
            print(f"已下载并验证重复候选 {index}/{expected_matches}：{candidate}")
        return tuple(saved)
    raise RuntimeError(f"等待 {expected_matches} 个同 Prompt 视频结果超时；未提交新任务")


def extract_last_frame(project: dict, shot_id: str, video: Path) -> Path:
    """使用现有 FLAC loop 的 FFmpeg 配置提取末帧。"""
    ffmpeg = project.get("ffmpeg_path") or "ffmpeg"
    ffprobe = project.get("ffprobe_path") or "ffprobe"
    output_dir = Path(project.get("output_dir", "./generated"))
    if not output_dir.is_absolute():
        output_dir = PROJECT_ROOT / output_dir
    frame = output_dir / "continuity-frames" / f"{shot_id}-last.jpg"
    frame.parent.mkdir(parents=True, exist_ok=True)
    probe = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(video)], capture_output=True, text=True, check=True)
    duration = float(probe.stdout.strip())
    subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-sseof", "-0.08", "-i", str(video), "-frames:v", "1", "-q:v", "2", str(frame)], check=True)
    if not frame.exists():
        raise RuntimeError(f"未生成末帧：{frame}")
    print(f"已提取末帧（视频时长约 {duration:.2f}s）：{frame}")
    return frame


def main() -> int:
    """启动独立 ChromeGo 会话并按镜头循环；默认 dry-run。"""
    parser = argparse.ArgumentParser(description="人工登录后自动操作 BFL Playground")
    parser.add_argument("project", type=Path)
    parser.add_argument("--run", action="store_true", help="确认后自动点击 Generate")
    parser.add_argument("--submit-only", action="store_true", help="确认右侧任务队列后退出，不等待视频下载")
    parser.add_argument("--download-only", action="store_true", help="不填表、不提交，只等待并下载 --shot-id 对应的既有结果")
    parser.add_argument("--download-all-matches", action="store_true", help="与 --download-only 配合，分别下载同 Prompt 的全部预期重复结果")
    parser.add_argument("--expected-matches", type=int, default=2, help="--download-all-matches 期望的唯一结果数，默认 2")
    parser.add_argument("--retry-rate-limited", action="store_true", help="只恢复当前 Rate limited 任务卡，然后等待下载；不 Reset、不重填、不点主 Generate")
    parser.add_argument("--rate-limit-cooldown-min", type=float, default=10.0, help="点击错误卡 Retry 后、主 Generate 前的随机等待下限秒数")
    parser.add_argument("--rate-limit-cooldown-max", type=float, default=20.0, help="点击错误卡 Retry 后、主 Generate 前的随机等待上限秒数")
    parser.add_argument("--shot-id", help="只运行指定镜头；用于断点续跑")
    parser.add_argument("--start-frame", type=Path, help="指定镜头的首帧文件；仅与 --shot-id 一起使用")
    parser.add_argument("--output-video", type=Path, help="将当前单镜头成片保存到指定 MP4 路径")
    parser.add_argument("--submit-stabilize-seconds", type=float, default=30.0, help="确认右侧任务创建后继续观察的秒数，默认 30")
    parser.add_argument("--max-submit-retries", type=int, default=1, help="仅在明确 502/503/504 或当前任务卡失败时重试，默认最多 1 次")
    parser.add_argument("--retry-delay-min", type=float, default=20.0, help="明确失败后的随机退避下限秒数，默认 20")
    parser.add_argument("--retry-delay-max", type=float, default=40.0, help="明确失败后的随机退避上限秒数，默认 40")
    parser.add_argument("--pre-submit-cooldown-min", type=float, default=30.0, help="所有输入稳定后、点击 Generate 前的冷却下限秒数")
    parser.add_argument("--pre-submit-cooldown-max", type=float, default=45.0, help="所有输入稳定后、点击 Generate 前的冷却上限秒数")
    parser.add_argument("--chrome", type=Path, default=DEFAULT_CHROME)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE, help="必须使用 ChromeGo 已登录的 chrome-data 目录")
    parser.add_argument("--proxy", default=DEFAULT_PROXY)
    parser.add_argument("--yt-dlp", type=Path, default=DEFAULT_YTDLP, help="yt-dlp 可执行文件路径，用于自动下载回退")
    parser.add_argument("--timeout-ms", type=int, default=1800000)
    parser.add_argument("--pace-min", type=float, default=1.0, help="每步随机等待下限秒数，默认 1.0")
    parser.add_argument("--pace-max", type=float, default=3.0, help="每步随机等待上限秒数，默认 3.0")
    parser.add_argument("--upload-settle-min", type=float, default=8.0, help="首帧 CDN 缩略图出现后，提交前额外稳定等待下限秒数")
    parser.add_argument("--upload-settle-max", type=float, default=12.0, help="首帧 CDN 缩略图出现后，提交前额外稳定等待上限秒数")
    args = parser.parse_args()
    if args.download_only and (args.run or args.submit_only or args.retry_rate_limited):
        raise SystemExit("--download-only 不能与 --run/--submit-only/--retry-rate-limited 同时使用")
    if args.download_all_matches and not args.download_only:
        raise SystemExit("--download-all-matches 必须与 --download-only 一起使用")
    if args.expected_matches < 2 or args.expected_matches > 10:
        raise SystemExit("重复结果数量无效：要求 2 <= expected-matches <= 10")
    if args.retry_rate_limited and (args.run or args.submit_only):
        raise SystemExit("--retry-rate-limited 不能与 --run/--submit-only 同时使用")
    if (args.download_only or args.retry_rate_limited) and not args.shot_id:
        raise SystemExit("--download-only/--retry-rate-limited 必须指定 --shot-id")
    if args.rate_limit_cooldown_min < 5 or args.rate_limit_cooldown_max > 60 or args.rate_limit_cooldown_min > args.rate_limit_cooldown_max:
        raise SystemExit("Rate limited 节奏无效：要求 5 <= min <= max <= 60")
    if args.pace_min < 0.5 or args.pace_max > 10 or args.pace_min > args.pace_max:
        raise SystemExit("人工节奏范围无效：要求 0.5 <= pace-min <= pace-max <= 10")
    if args.submit_stabilize_seconds < 5 or args.submit_stabilize_seconds > 120:
        raise SystemExit("任务稳定观察时长无效：要求 5 <= submit-stabilize-seconds <= 120")
    if args.max_submit_retries < 0 or args.max_submit_retries > 2:
        raise SystemExit("提交重试上限无效：要求 0 <= max-submit-retries <= 2")
    if args.retry_delay_min < 5 or args.retry_delay_max > 180 or args.retry_delay_min > args.retry_delay_max:
        raise SystemExit("失败退避范围无效：要求 5 <= retry-delay-min <= retry-delay-max <= 180")
    if args.pre_submit_cooldown_min < 10 or args.pre_submit_cooldown_max > 180 or args.pre_submit_cooldown_min > args.pre_submit_cooldown_max:
        raise SystemExit("提交前冷却范围无效：要求 10 <= pre-submit-cooldown-min <= pre-submit-cooldown-max <= 180")
    if args.upload_settle_min < 5 or args.upload_settle_max > 60 or args.upload_settle_min > args.upload_settle_max:
        raise SystemExit("首帧上传稳定等待范围无效：要求 5 <= upload-settle-min <= upload-settle-max <= 60")
    global HUMAN_PACE_MIN_SECONDS, HUMAN_PACE_MAX_SECONDS, UPLOAD_SETTLE_MIN_SECONDS, UPLOAD_SETTLE_MAX_SECONDS
    HUMAN_PACE_MIN_SECONDS = args.pace_min
    HUMAN_PACE_MAX_SECONDS = args.pace_max
    UPLOAD_SETTLE_MIN_SECONDS = args.upload_settle_min
    UPLOAD_SETTLE_MAX_SECONDS = args.upload_settle_max
    project_path = args.project.resolve()
    project = load_project(project_path)
    all_shots = project["shots"]
    shots = all_shots
    previous_frame: Path | None = None
    if args.shot_id:
        selected = [shot for shot in all_shots if shot["id"] == args.shot_id]
        if len(selected) != 1:
            raise SystemExit(f"项目中不存在唯一镜头：{args.shot_id}")
        shots = selected
        if args.start_frame is not None:
            previous_frame = args.start_frame.resolve()
            if not previous_frame.is_file():
                raise SystemExit(f"指定首帧不存在：{previous_frame}")
        elif all_shots.index(selected[0]) > 0 and not args.download_only:
            raise SystemExit("续跑非首镜头必须提供 --start-frame")
    elif args.start_frame is not None:
        raise SystemExit("--start-frame 必须与 --shot-id 一起使用")
    if args.output_video is not None and not args.shot_id:
        raise SystemExit("--output-video 必须与 --shot-id 一起使用")
    if not args.chrome.is_file():
        raise SystemExit(f"Chrome 不存在：{args.chrome}")
    args.profile.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(
            str(args.profile),
            executable_path=str(args.chrome),
            headless=False,
            # 直接传给 Chrome，避免 Playwright 自动注入 host-resolver-rules 警告参数。
            args=["--start-maximized", f"--proxy-server={args.proxy}", f"--proxy-bypass-list={DEFAULT_PROXY_BYPASS}"],
            no_viewport=True,
            accept_downloads=True,
        )
        page = context.pages[0] if context.pages else context.new_page()
        ensure_playground(page)
        if args.retry_rate_limited:
            shot = shots[0]
            shot_id = shot["id"]
            prompt = resolve_prompt(project_path, shot)
            video = args.output_video.resolve() if args.output_video else PROJECT_ROOT / project.get("output_dir", "generated") / "clips" / shot_id / f"{shot_id}.mp4"
            retry_rate_limited_task(page, prompt, args.rate_limit_cooldown_min, args.rate_limit_cooldown_max)
            wait_and_download(page, video, args.timeout_ms, prompt, args.proxy, str(project.get("ffprobe_path") or "ffprobe"), args.yt_dlp)
            extract_last_frame(project, shot_id, video)
            context.close()
            return 0
        if args.download_only:
            shot = shots[0]
            shot_id = shot["id"]
            prompt = resolve_prompt(project_path, shot)
            video = args.output_video.resolve() if args.output_video else PROJECT_ROOT / project.get("output_dir", "generated") / "clips" / shot_id / f"{shot_id}.mp4"
            if args.download_all_matches:
                candidates = wait_and_download_all_matches(
                    page,
                    video,
                    args.timeout_ms,
                    prompt,
                    args.proxy,
                    str(project.get("ffprobe_path") or "ffprobe"),
                    args.yt_dlp,
                    args.expected_matches,
                )
                for index, candidate in enumerate(candidates, start=1):
                    extract_last_frame(project, f"{shot_id}-candidate-{index:02d}", candidate)
                context.close()
                return 0
            wait_and_download(page, video, args.timeout_ms, prompt, args.proxy, str(project.get("ffprobe_path") or "ffprobe"), args.yt_dlp)
            extract_last_frame(project, shot_id, video)
            context.close()
            return 0
        # 新任务前先让页面与账户请求窗口冷却，避免打开后立刻上传媒体触发服务端限流。
        startup_cooldown = random.uniform(30.0, 45.0)
        print(f"Playground 启动后冷却：{startup_cooldown:.2f}s；期间不 Reset、不上传")
        page.wait_for_timeout(int(startup_cooldown * 1000))
        wait_until_queue_idle(page, args.timeout_ms)
        for index, shot in enumerate(shots):
            shot_id = shot["id"]
            prompt = resolve_prompt(project_path, shot)
            print(f"镜头 {index + 1}/{len(shots)}：{shot_id}")
            reset_all_inputs(page)
            choose_model(page)
            after_reset_cooldown = random.uniform(10.0, 20.0)
            print(f"Reset 后冷却：{after_reset_cooldown:.2f}s；随后才上传首帧")
            page.wait_for_timeout(int(after_reset_cooldown * 1000))
            needs_start_frame = args.start_frame is not None or (not args.shot_id and index > 0)
            if needs_start_frame:
                if previous_frame is None:
                    raise SystemExit("缺少上一段末帧，停止自动化")
                set_file_if_needed(page, previous_frame)
            # BFL 页面容易在短时间连续同步大 Prompt、媒体和参数时返回 502；按人工顺序错峰写入。
            fill_prompt(page, prompt)
            defaults = project.get("defaults", {})
            apply_request_parameters(page, defaults, include_duration=False)
            duration = defaults.get("duration")
            if duration is not None:
                set_parameter(page, "Duration", duration)
                human_pause(page)
            report_request_parameters(page)
            if not args.run:
                print("dry-run：已填入提示词但未点击 Generate；使用 --run 才会生成。")
                continue
            cooldown = random.uniform(args.pre_submit_cooldown_min, args.pre_submit_cooldown_max)
            print(f"全部输入已稳定，提交前冷却：{cooldown:.2f}s")
            page.wait_for_timeout(int(cooldown * 1000))
            click_generate(
                page,
                prompt,
                args.submit_stabilize_seconds,
                args.max_submit_retries,
                args.retry_delay_min,
                args.retry_delay_max,
            )
            if args.submit_only:
                print("已提交当前镜头，浏览器将保留生成任务；不等待视频下载。")
                context.close()
                return 0
            video = args.output_video.resolve() if args.output_video else PROJECT_ROOT / project.get("output_dir", "generated") / "clips" / shot_id / f"{shot_id}.mp4"
            wait_and_download(
                page,
                video,
                args.timeout_ms,
                prompt,
                args.proxy,
                str(project.get("ffprobe_path") or "ffprobe"),
                args.yt_dlp,
            )
            previous_frame = extract_last_frame(project, shot_id, video)
        context.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
