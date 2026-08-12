#!/usr/bin/env python3
"""用 Playwright 在人工登录后的 BFL Playground 中循环生成并提取末帧。"""

from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, sync_playwright


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CHROME = Path(r"D:\Programs\ChromeGo\TorBrowserPortable\chrome\Chrome-bin\chrome.exe")
DEFAULT_PROFILE = Path(r"D:\Programs\ChromeGo\TorBrowserPortable\v2rayn\v2rayn2025\chrome-data")
DEFAULT_PROXY = "socks5://127.0.0.1:10808"
DEFAULT_PROXY_BYPASS = "localhost;127.*;10.*;172.16.*;172.17.*;172.18.*;172.19.*;172.20.*;172.21.*;172.22.*;172.23.*;172.24.*;172.25.*;172.26.*;172.27.*;172.28.*;172.29.*;172.30.*;172.31.*;192.168.*"
PLAYGROUND_URL = "https://dashboard.bfl.ai/"
HUMAN_PACE_MIN_SECONDS = 1.0
HUMAN_PACE_MAX_SECONDS = 3.0
UPLOAD_SETTLE_MIN_SECONDS = 8.0
UPLOAD_SETTLE_MAX_SECONDS = 12.0


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
    """优先读取外置长提示词，避免将导演分镜压缩成单行 JSON。"""
    prompt_file = shot.get("prompt_file")
    if not prompt_file:
        return shot["prompt"]
    prompt_path = (project_path.parent / prompt_file).resolve()
    text = prompt_path.read_text(encoding="utf-8")
    start = text.find("```text\n")
    end = text.find("\n```", start + 8)
    if start < 0 or end < 0:
        raise RuntimeError(f"外置提示词格式无效：{prompt_path}")
    return text[start + 8:end].strip()


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


def ensure_playground(page: Page) -> None:
    """确认已进入 Playground；登录和验证码由用户完成。"""
    page.goto(PLAYGROUND_URL, wait_until="domcontentloaded")
    human_pause(page, 3.0)
    if first_visible(page, ["text=Sign in", "text=Log in", "text=登录"], timeout=800):
        print("请在打开的 ChromeGo 窗口完成 Google/BFL 登录，完成后回到终端按 Enter。")
        input()
        page.goto(PLAYGROUND_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(2500)
    # 首页可能落在 Dashboard；通过现有导航进入 Playground，保留当前组织/项目上下文。
    if not first_visible(page, ["textarea", "[contenteditable='true']"], timeout=1200):
        playground_link = first_visible(page, ["text=Playground", "a[href*='playground']"], timeout=2000)
        if playground_link:
            playground_link.click()
            human_pause(page, 3.0)
    ready_deadline = time.monotonic() + 60
    while time.monotonic() < ready_deadline:
        if first_visible(page, ["textarea", "[contenteditable='true']"], timeout=1200):
            break
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
        if not cancel_visible and not generating_visible:
            return
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


def apply_request_parameters(page: Page, defaults: dict) -> None:
    """按 BFL API 请求字段顺序同步 Playground 参数。"""
    mapping = [
        ("Aspect ratio", defaults.get("aspect_ratio")),
        ("Duration", defaults.get("duration")),
        ("Resolution", defaults.get("resolution")),
        ("Generate audio", defaults.get("generate_audio")),
        ("Draft", defaults.get("draft")),
    ]
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
                    final_src = thumbnail.first.get_attribute("src") or ""
                    generate = first_visible(page, ['button[aria-label=\"Generate\"]'], timeout=1500)
                    if final_src == verified_src and generate is not None and generate.is_enabled() and generate.get_attribute("disabled") is None:
                        print("Start frame 上传、页面同步和 Generate 可用状态均已稳定")
                        page.screenshot(path=str(PROJECT_ROOT / "work" / "start-frame-settled.png"), full_page=True)
                        return
                    verified_src = None
                    print("上传后页面状态发生变化，重新等待稳定证据")
        page.wait_for_timeout(500)
    page.screenshot(path=str(PROJECT_ROOT / "work" / "start-frame-upload-failed.png"), full_page=True)
    raise RuntimeError("Start frame 120 秒内未出现已上传缩略图；未点击 Generate")


def task_board_snapshot(page: Page) -> tuple[str, ...]:
    """采集右侧结果/队列卡片摘要，用于确认真实创建了新任务。"""
    cards = page.locator("article, [role='article']").evaluate_all(
        """els => els.map(el => (el.innerText || '').replace(/\\s+/g, ' ').trim())
            .filter(text => /(?:JUST NOW|\\d+\\s*(?:S|M|H)\\s*AGO|\\d{1,2}:\\d{2})\\s*[\\s\\u00b7.]\\s*(?:(?:TYPICAL LATENCY:[^\\u00b7.]*)[\\u00b7.]\\s*)?\\d+\\s+VIDEO/i.test(text))"""
    )
    if cards:
        return tuple(sorted(cards))
    lines = page.locator("body").inner_text().splitlines()
    return tuple(
        sorted(
            " ".join(line.split())
            for line in lines
            if "VIDEO" in line.upper() and (
                "AGO" in line.upper()
                or "JUST NOW" in line.upper()
                or "TYPICAL LATENCY" in line.upper()
            )
        )
    )


def wait_for_task_creation(page: Page, before: tuple[str, ...], settle_seconds: float) -> None:
    """等待右侧任务队列出现新证据并稳定，不把按钮瞬态当作已提交。"""
    deadline = time.monotonic() + 90
    evidence_at: float | None = None
    while time.monotonic() < deadline:
        board_changed = task_board_snapshot(page) != before
        if board_changed:
            if evidence_at is None:
                evidence_at = time.monotonic()
                print("已检测到右侧任务队列变化，开始稳定观察")
            elif time.monotonic() - evidence_at >= settle_seconds:
                print("任务队列已稳定，确认已提交")
                return
        else:
            evidence_at = None
        page.wait_for_timeout(500)
    page.screenshot(path=str(PROJECT_ROOT / "work" / "task-creation-unconfirmed.png"), full_page=True)
    raise RuntimeError("Generate 已点击，但 90 秒内未确认右侧任务队列创建；已保存截图且不会重复提交")


def click_generate(page: Page, settle_seconds: float) -> None:
    """点击 Generate，并在右侧任务区出现且稳定后才确认成功。"""
    # 当前 BFL DOM 的文字位于三层 span 内；实际点击目标必须向上解析到 button。
    # aria-label 是首选契约，精确文本 + 最近 button 是页面改版后的安全回退。
    candidates = page.locator(
        'button[aria-label="Generate"], button:has(span:text-is("Generate"))'
    )
    ranked: list[tuple[float, object, dict]] = []
    for index in range(candidates.count()):
        candidate = candidates.nth(index)
        if not candidate.is_visible() or not candidate.is_enabled() or candidate.get_attribute("disabled") is not None:
            continue
        candidate_box = candidate.bounding_box()
        if candidate_box is not None:
            ranked.append((candidate_box["x"], candidate, candidate_box))
    if not ranked:
        raise RuntimeError("未找到 Generate 按钮")
    _, button, selected_box = min(ranked, key=lambda item: item[0])
    board_before = task_board_snapshot(page)
    print(f"选择左侧 Generate：x={selected_box['x']:.1f}, y={selected_box['y']:.1f}, 候选数={len(ranked)}")
    # 右侧历史视频预览层可能拦截鼠标命中，但按钮仍是可用的；强制命中目标按钮。
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if button.is_enabled() and button.get_attribute("disabled") is None:
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
            finally:
                page.evaluate("""() => {
                    for (const [el, value] of (window.__bflPointerRestore || [])) el.style.pointerEvents = value;
                    delete window.__bflPointerRestore;
                    delete window.__bflBlockers;
                }""")
            generating_deadline = time.monotonic() + 15
            while time.monotonic() < generating_deadline:
                generating = page.get_by_role("button").filter(has_text="Generating")
                cancel = page.get_by_role("button", name="Cancel")
                if (generating.count() > 0 and generating.first.is_visible()) or (cancel.count() > 0 and cancel.first.is_visible()):
                    print("点击已被页面接收，等待右侧任务队列创建")
                    wait_for_task_creation(page, board_before, settle_seconds)
                    return
                page.wait_for_timeout(500)
            page.screenshot(path=str(PROJECT_ROOT / "work" / "submit-not-started.png"), full_page=True)
            raise RuntimeError("Generate 已点击，但页面未出现新任务状态")
        page.wait_for_timeout(500)
    page.screenshot(path=str(PROJECT_ROOT / "work" / "generate-disabled.png"), full_page=True)
    raise RuntimeError("Generate 仍为 disabled；未强制点击，已保存诊断截图")


def wait_and_download(page: Page, output: Path, timeout_ms: int) -> None:
    """等待页面视频结果并下载 MP4。"""
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        videos = page.locator("video")
        if videos.count() > 0:
            src = videos.last.get_attribute("src")
            if src and src.startswith("http"):
                output.parent.mkdir(parents=True, exist_ok=True)
                import urllib.request

                urllib.request.urlretrieve(src, output)
                if output.exists() and output.stat().st_size > 0:
                    return
        page.wait_for_timeout(5000)
    raise RuntimeError("等待视频结果超时")


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
    parser.add_argument("--shot-id", help="只运行指定镜头；用于断点续跑")
    parser.add_argument("--start-frame", type=Path, help="指定镜头的首帧文件；仅与 --shot-id 一起使用")
    parser.add_argument("--submit-stabilize-seconds", type=float, default=30.0, help="确认右侧任务创建后继续观察的秒数，默认 30")
    parser.add_argument("--chrome", type=Path, default=DEFAULT_CHROME)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE, help="必须使用 ChromeGo 已登录的 chrome-data 目录")
    parser.add_argument("--proxy", default=DEFAULT_PROXY)
    parser.add_argument("--timeout-ms", type=int, default=1800000)
    parser.add_argument("--pace-min", type=float, default=1.0, help="每步随机等待下限秒数，默认 1.0")
    parser.add_argument("--pace-max", type=float, default=3.0, help="每步随机等待上限秒数，默认 3.0")
    parser.add_argument("--upload-settle-min", type=float, default=8.0, help="首帧 CDN 缩略图出现后，提交前额外稳定等待下限秒数")
    parser.add_argument("--upload-settle-max", type=float, default=12.0, help="首帧 CDN 缩略图出现后，提交前额外稳定等待上限秒数")
    args = parser.parse_args()
    if args.pace_min < 0.5 or args.pace_max > 10 or args.pace_min > args.pace_max:
        raise SystemExit("人工节奏范围无效：要求 0.5 <= pace-min <= pace-max <= 10")
    if args.submit_stabilize_seconds < 5 or args.submit_stabilize_seconds > 120:
        raise SystemExit("任务稳定观察时长无效：要求 5 <= submit-stabilize-seconds <= 120")
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
        elif all_shots.index(selected[0]) > 0:
            raise SystemExit("续跑非首镜头必须提供 --start-frame")
    elif args.start_frame is not None:
        raise SystemExit("--start-frame 必须与 --shot-id 一起使用")
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
        wait_until_queue_idle(page, args.timeout_ms)
        for index, shot in enumerate(shots):
            shot_id = shot["id"]
            prompt = resolve_prompt(project_path, shot)
            print(f"镜头 {index + 1}/{len(shots)}：{shot_id}")
            reset_all_inputs(page)
            choose_model(page)
            fill_prompt(page, prompt)
            apply_request_parameters(page, project.get("defaults", {}))
            report_request_parameters(page)
            needs_start_frame = args.start_frame is not None or (not args.shot_id and index > 0)
            if needs_start_frame:
                if previous_frame is None:
                    raise SystemExit("缺少上一段末帧，停止自动化")
                set_file_if_needed(page, previous_frame)
            if not args.run:
                print("dry-run：已填入提示词但未点击 Generate；使用 --run 才会生成。")
                continue
            click_generate(page, args.submit_stabilize_seconds)
            if args.submit_only:
                print("已提交当前镜头，浏览器将保留生成任务；不等待视频下载。")
                context.close()
                return 0
            video = PROJECT_ROOT / project.get("output_dir", "generated") / "clips" / shot_id / f"{shot_id}.mp4"
            wait_and_download(page, video, args.timeout_ms)
            previous_frame = extract_last_frame(project, shot_id, video)
        context.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
