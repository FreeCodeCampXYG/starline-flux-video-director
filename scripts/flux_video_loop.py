#!/usr/bin/env python3
"""按共享首尾帧安全编排 FLUX 3 连续视频。"""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import random
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TERMINAL_SUCCESS = {"Ready"}
TERMINAL_FAILURE = {
    "Error",
    "Request Moderated",
    "Content Moderated",
    "Task not found",
}
ACTIVE_STATUSES = {"Pending", "Reasoning", "Generating"}
ASPECT_RATIOS = {"auto", "21:9", "2:1", "16:9", "4:3", "1:1", "3:4", "9:16"}
RESOLUTIONS = {"hd", "fhd"}
ALLOWED_REQUEST_FIELDS = {
    "prompt",
    "mode",
    "aspect_ratio",
    "duration",
    "resolution",
    "generate_audio",
    "safety_tolerance",
    "draft",
    "version",
    "keyframes",
}
CONFIRMATIONS = {"FREE_PROMO_CONFIRMED", "PAID_RUN_CONFIRMED"}
SECRET_QUERY_KEYS = {"sig", "signature", "token", "key", "api_key", "x-key"}


class ProjectError(RuntimeError):
    """项目配置或本地状态不满足执行要求。"""


class APIError(RuntimeError):
    """BFL API 请求失败。"""

    def __init__(self, message: str, status_code: int | None = None, body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


def utc_now() -> str:
    """返回便于审计的 UTC 时间。"""
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    """读取 UTF-8 JSON 对象。"""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ProjectError(f"找不到项目文件：{path}") from exc
    except json.JSONDecodeError as exc:
        raise ProjectError(f"项目 JSON 无效：{exc}") from exc
    if not isinstance(data, dict):
        raise ProjectError("项目 JSON 顶层必须是对象")
    return data


def resolve_prompt(project_path: Path, shot: dict[str, Any]) -> str:
    """读取镜头提示词；长提示词可外置为 Markdown 的 text 代码块。"""
    prompt_file = shot.get("prompt_file")
    if not prompt_file:
        return str(shot.get("prompt", ""))
    source = (project_path.parent / str(prompt_file)).resolve()
    try:
        content = source.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ProjectError(f"找不到外置提示词：{source}") from exc
    match = re.search(r"```text\s*(.*?)\s*```", content, flags=re.DOTALL)
    return (match.group(1) if match else content).strip()


def write_json(path: Path, data: dict[str, Any]) -> None:
    """以原子替换方式写入 UTF-8 JSON。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def resolve_output_dir(project_path: Path, project: dict[str, Any]) -> Path:
    """解析项目输出目录，不依赖当前工作目录。"""
    raw = project.get("output_dir", "./generated")
    output = Path(raw)
    if not output.is_absolute():
        output = project_path.parent / output
    return output.resolve()


def resolve_media(project_path: Path, value: str) -> tuple[str, str]:
    """把本地图片转为内联媒体，返回 API 值和安全快照值。"""
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme in {"http", "https", "data"}:
        return value, redact_url(value)
    path = Path(value)
    if not path.is_absolute():
        path = project_path.parent / path
    path = path.resolve()
    if not path.is_file():
        raise ProjectError(f"关键帧文件不存在：{path}")
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    if mime not in {"image/jpeg", "image/png", "image/webp"}:
        raise ProjectError(f"不支持的关键帧格式：{path.name}")
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}", str(path)


def get_api_key() -> str:
    """从进程或 Windows 用户环境读取 Key，但绝不输出其内容。"""
    value = os.environ.get("BFL_API_KEY", "")
    if value.strip():
        return value
    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
                value, _ = winreg.QueryValueEx(key, "BFL_API_KEY")
                if isinstance(value, str) and value.strip():
                    return value
        except (FileNotFoundError, OSError):
            pass
    return ""


def resolve_executable(project: dict[str, Any], field: str, name: str) -> str:
    """从项目配置或 PATH 定位 FFmpeg 工具。"""
    configured = project.get(field)
    if configured:
        path = Path(str(configured)).expanduser().resolve()
        if path.is_file():
            return str(path)
        raise ProjectError(f"{field} 指向的文件不存在：{path}")
    found = shutil.which(name)
    if found:
        return found
    raise ProjectError(f"找不到 {name}；请在项目中设置 {field} 或加入 PATH")


def extract_last_frame(video: Path, output: Path, ffmpeg: str, ffprobe: str) -> None:
    """提取视频接近结尾的最后一个稳定可解码画面。"""
    probe = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(video)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if probe.returncode != 0:
        raise ProjectError(f"ffprobe 无法读取视频：{probe.stderr.strip()}")
    try:
        duration = float(probe.stdout.strip())
    except ValueError as exc:
        raise ProjectError("ffprobe 未返回有效视频时长") from exc
    seek = max(duration - 0.08, 0.0)
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_suffix(".tmp.jpg")
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(video),
        "-ss",
        f"{seek:.3f}",
        "-frames:v",
        "1",
        "-q:v",
        "2",
        str(temp),
    ]
    extracted = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    if extracted.returncode != 0 or not temp.is_file() or temp.stat().st_size == 0:
        temp.unlink(missing_ok=True)
        raise ProjectError(f"FFmpeg 末帧提取失败：{extracted.stderr.strip()}")
    temp.replace(output)


def redact_url(value: str) -> str:
    """隐藏 URL 查询参数中的短期访问凭据。"""
    if value.startswith("data:"):
        return "<inline-media-redacted>"
    parsed = urllib.parse.urlsplit(value)
    pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    safe_pairs = [(key, "<redacted>" if key.lower() in SECRET_QUERY_KEYS else val) for key, val in pairs]
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urllib.parse.urlencode(safe_pairs), parsed.fragment)
    )


def merged_shot(project: dict[str, Any], shot: dict[str, Any]) -> dict[str, Any]:
    """合并全局默认值与镜头级设置。"""
    merged = dict(project.get("defaults", {}))
    merged.update({key: value for key, value in shot.items() if key not in {"id", "star", "review", "prompt_file"}})
    return merged


def validate_project(project_path: Path, project: dict[str, Any], check_media: bool = True) -> list[str]:
    """验证共享边界帧项目，返回提示而不是隐藏修复。"""
    errors: list[str] = []
    shots = project.get("shots")
    max_submissions = project.get("max_submissions")
    if not isinstance(max_submissions, int) or max_submissions < 1:
        errors.append("max_submissions 必须是正整数")
    if not isinstance(shots, list) or not shots:
        errors.append("shots 必须是非空数组")
        return errors
    if isinstance(max_submissions, int) and len(shots) > max_submissions:
        errors.append(f"镜头数 {len(shots)} 超过 max_submissions={max_submissions}")

    seen_ids: set[str] = set()
    for index, shot in enumerate(shots):
        label = f"shots[{index}]"
        if not isinstance(shot, dict):
            errors.append(f"{label} 必须是对象")
            continue
        shot_id = shot.get("id")
        if not isinstance(shot_id, str) or not shot_id.strip():
            errors.append(f"{label}.id 必须是非空字符串")
        elif shot_id in seen_ids:
            errors.append(f"镜头 id 重复：{shot_id}")
        else:
            seen_ids.add(shot_id)

        request = merged_shot(project, shot)
        extra = sorted(set(request) - ALLOWED_REQUEST_FIELDS)
        if extra:
            errors.append(f"{label} 含 API 不支持字段：{', '.join(extra)}")
        expected_mode = "t2v" if index == 0 else "i2v"
        if request.get("mode") != expected_mode:
            errors.append(f"{label}.mode 必须为 {expected_mode}")
        prompt = request.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            errors.append(f"{label}.prompt 必须是非空字符串")
        keyframes = request.get("keyframes")
        if index == 0:
            if keyframes is not None:
                errors.append(f"{label} 为 t2v，不应设置 keyframes")
        elif keyframes != "auto_previous_last_frame":
            errors.append(f"{label}.keyframes 必须为 auto_previous_last_frame")

        aspect = request.get("aspect_ratio", "auto")
        if aspect not in ASPECT_RATIOS:
            errors.append(f"{label}.aspect_ratio 无效：{aspect}")
        resolution = request.get("resolution", "hd")
        if resolution not in RESOLUTIONS:
            errors.append(f"{label}.resolution 无效：{resolution}")
        duration = request.get("duration", "auto")
        if duration != "auto" and (not isinstance(duration, int) or isinstance(duration, bool) or not 5 <= duration <= 20):
            errors.append(f"{label}.duration 必须为 5–20 的整数或 auto")
        for boolean_key in ("generate_audio", "draft"):
            if boolean_key in request and not isinstance(request[boolean_key], bool):
                errors.append(f"{label}.{boolean_key} 必须是布尔值")
    return errors


def build_request(
    project_path: Path,
    project: dict[str, Any],
    shot: dict[str, Any],
    previous_last_frame: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """构建 API 请求和脱敏快照。"""
    request = merged_shot(project, shot)
    request["prompt"] = resolve_prompt(project_path, shot)
    safe = dict(request)
    if request.get("mode") == "i2v":
        if previous_last_frame is None:
            raise ProjectError("i2v 镜头缺少上一段末帧")
        api_value, safe_value = resolve_media(project_path, str(previous_last_frame))
        request["keyframes"] = api_value
        safe["keyframes"] = safe_value
    else:
        request.pop("keyframes", None)
        safe.pop("keyframes", None)
    return request, safe


def parse_response_body(raw: bytes) -> Any:
    """尽量把响应解析为 JSON。"""
    text = raw.decode("utf-8", errors="replace")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def request_json(
    method: str,
    url: str,
    api_key: str,
    payload: dict[str, Any] | None = None,
    timeout: int = 60,
) -> tuple[dict[str, Any], dict[str, str]]:
    """发送带认证的 JSON 请求，但绝不记录密钥。"""
    data = None if payload is None else json.dumps(payload, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", "X-Key": api_key, "User-Agent": "starline-flux-video-director/0.1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = parse_response_body(response.read())
            if not isinstance(body, dict):
                raise APIError("API 返回的不是 JSON 对象", response.status, body)
            return body, dict(response.headers.items())
    except urllib.error.HTTPError as exc:
        body = parse_response_body(exc.read())
        raise APIError(f"HTTP {exc.code}: {body}", exc.code, body) from exc
    except urllib.error.URLError as exc:
        raise APIError(f"网络错误：{exc.reason}") from exc


def retry_delay(attempt: int, headers: dict[str, str] | None = None) -> float:
    """计算有上限的指数退避。"""
    if headers:
        retry_after = headers.get("Retry-After") or headers.get("retry-after")
        if retry_after and retry_after.isdigit():
            return min(float(retry_after), 60.0)
    return min(2**attempt + random.random(), 60.0)


def submit(endpoint: str, api_key: str, payload: dict[str, Any], retries: int = 3) -> dict[str, Any]:
    """提交一次任务；只对未创建任务的可重试错误重交。"""
    for attempt in range(retries + 1):
        try:
            body, _ = request_json("POST", endpoint, api_key, payload, timeout=120)
            if not body.get("id") or not body.get("polling_url"):
                raise APIError("提交响应缺少 id 或 polling_url", body=body)
            return body
        except APIError as exc:
            if exc.status_code not in {429, 500, 502, 503, 504} or attempt >= retries:
                raise
            wait = retry_delay(attempt)
            print(f"提交暂时失败，{wait:.1f} 秒后重试（{attempt + 1}/{retries}）", flush=True)
            time.sleep(wait)
    raise APIError("提交失败")


def poll(polling_url: str, api_key: str, interval: int, timeout_seconds: int) -> dict[str, Any]:
    """轮询现有任务；任何轮询错误都不会触发重新提交。"""
    deadline = time.monotonic() + timeout_seconds
    transient_attempt = 0
    while time.monotonic() < deadline:
        try:
            body, _ = request_json("GET", polling_url, api_key, timeout=60)
            transient_attempt = 0
        except APIError as exc:
            if exc.status_code not in {429, 500, 502, 503, 504}:
                raise
            wait = retry_delay(transient_attempt)
            transient_attempt = min(transient_attempt + 1, 6)
            print(f"轮询暂时失败，保持同一任务，{wait:.1f} 秒后继续", flush=True)
            time.sleep(wait)
            continue
        status = body.get("status")
        print(f"任务状态：{status}", flush=True)
        if status in TERMINAL_SUCCESS:
            return body
        if status in TERMINAL_FAILURE:
            raise APIError(f"生成终止：{status}", body=body)
        if status not in ACTIVE_STATUSES:
            raise APIError(f"未知任务状态：{status}", body=body)
        time.sleep(interval)
    raise APIError(f"轮询超时（{timeout_seconds} 秒），任务仍可稍后续查")


def download_file(url: str, path: Path, timeout: int = 300) -> None:
    """立即下载短期签名成果并以原子方式保存。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "starline-flux-video-director/0.1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response, temp.open("wb") as handle:
            while chunk := response.read(1024 * 1024):
                handle.write(chunk)
    except Exception:
        temp.unlink(missing_ok=True)
        raise
    if temp.stat().st_size == 0:
        temp.unlink(missing_ok=True)
        raise APIError(f"下载结果为空：{path.name}")
    temp.replace(path)


def collect_artifacts(result_body: dict[str, Any], shot_dir: Path) -> list[dict[str, str]]:
    """下载全部视频和 draft cache，避免丢失多结果。"""
    result = result_body.get("result") or {}
    if not isinstance(result, dict):
        raise APIError("Ready 响应缺少 result 对象", body=result_body)
    artifacts: list[dict[str, str]] = []
    for field, extension in (("samples", ".mp4"), ("draft_caches", ".bin")):
        values = result.get(field) or []
        if isinstance(values, str):
            values = [values]
        if not isinstance(values, list):
            continue
        for index, item in enumerate(values, start=1):
            url = item.get("url") if isinstance(item, dict) else item
            if not isinstance(url, str):
                continue
            path = shot_dir / f"{field[:-1]}-{index:02d}{extension}"
            download_file(url, path)
            artifacts.append({"kind": field, "path": str(path.resolve()), "source_url": redact_url(url)})
    if not any(item["kind"] == "samples" for item in artifacts):
        raise APIError("Ready 响应没有可下载的 result.samples", body=result_body)
    return artifacts


def initial_state(project: dict[str, Any]) -> dict[str, Any]:
    """创建不含密钥的断点状态。"""
    return {
        "project": project.get("project"),
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "submission_count": 0,
        "shots": {},
    }


def load_state(path: Path, project: dict[str, Any]) -> dict[str, Any]:
    """读取断点状态或创建新状态。"""
    if not path.exists():
        return initial_state(project)
    state = read_json(path)
    state.setdefault("shots", {})
    state.setdefault("submission_count", 0)
    return state


def run_project(project_path: Path, project: dict[str, Any], args: argparse.Namespace) -> None:
    """按镜头顺序提交、轮询、下载并保存断点。"""
    if not args.execute:
        raise ProjectError("真实生成必须显式传入 --execute")
    if args.confirm_run not in CONFIRMATIONS:
        raise ProjectError("请用 --confirm-run FREE_PROMO_CONFIRMED 或 PAID_RUN_CONFIRMED 明确确认真实生成")
    api_key = get_api_key()
    if not api_key.strip():
        raise ProjectError("BFL_API_KEY 未设置；请在本机环境变量中设置，不要发送到聊天")

    output_dir = resolve_output_dir(project_path, project)
    state_path = output_dir / ".flux-video-state.json"
    requests_dir = output_dir / "requests"
    clips_dir = output_dir / "clips"
    frames_dir = output_dir / "continuity-frames"
    state = load_state(state_path, project)
    max_submissions = project["max_submissions"]
    ffmpeg = resolve_executable(project, "ffmpeg_path", "ffmpeg")
    ffprobe = resolve_executable(project, "ffprobe_path", "ffprobe")

    previous_last_frame: Path | None = None
    for shot_index, shot in enumerate(project["shots"]):
        shot_id = shot["id"]
        shot_state = state["shots"].setdefault(shot_id, {})
        if shot_state.get("status") == "Ready" and shot_state.get("artifacts"):
            print(f"跳过已完成镜头：{shot_id}", flush=True)
            last_frame_value = shot_state.get("last_frame")
            if last_frame_value and Path(last_frame_value).is_file():
                previous_last_frame = Path(last_frame_value)
            else:
                samples = [item for item in shot_state["artifacts"] if item.get("kind") == "samples"]
                if not samples:
                    raise ProjectError(f"已完成镜头缺少 MP4：{shot_id}")
                previous_last_frame = frames_dir / f"{shot_id}-last.jpg"
                extract_last_frame(Path(samples[0]["path"]), previous_last_frame, ffmpeg, ffprobe)
                shot_state["last_frame"] = str(previous_last_frame.resolve())
                write_json(state_path, state)
            continue

        # 允许第一段由 Dashboard 手工生成后导入，再从第二段继续 API 链。
        manual_video = clips_dir / shot_id / f"{shot_id}.mp4"
        if shot_index == 0 and not shot_state.get("polling_url") and manual_video.is_file():
            previous_last_frame = frames_dir / f"{shot_id}-last.jpg"
            extract_last_frame(manual_video, previous_last_frame, ffmpeg, ffprobe)
            shot_state.update(
                {
                    "status": "Ready",
                    "manual_import": True,
                    "completed_at": utc_now(),
                    "artifacts": [{"kind": "samples", "path": str(manual_video.resolve())}],
                    "last_frame": str(previous_last_frame.resolve()),
                }
            )
            state["updated_at"] = utc_now()
            write_json(state_path, state)
            print(f"已导入 Dashboard 首段并提取末帧：{manual_video}", flush=True)
            continue

        if shot_index > 0 and previous_last_frame is None:
            raise ProjectError(f"镜头 {shot_id} 缺少上一段末帧，不能保持连续性")
        request_body, safe_body = build_request(project_path, project, shot, previous_last_frame)
        write_json(requests_dir / f"{shot_id}.json", safe_body)

        polling_url = shot_state.get("polling_url")
        if polling_url:
            print(f"恢复轮询镜头：{shot_id}", flush=True)
        else:
            if state["submission_count"] >= max_submissions:
                raise ProjectError(f"已达到 max_submissions={max_submissions}，停止提交")
            print(f"提交镜头：{shot_id}", flush=True)
            submitted = submit(project["endpoint"], api_key, request_body, retries=args.submit_retries)
            state["submission_count"] += 1
            shot_state.update(
                {
                    "status": "Submitted",
                    "task_id": submitted["id"],
                    "polling_url": submitted["polling_url"],
                    "submitted_at": utc_now(),
                }
            )
            state["updated_at"] = utc_now()
            write_json(state_path, state)
            polling_url = submitted["polling_url"]

        try:
            result = poll(polling_url, api_key, args.poll_interval, args.poll_timeout)
            artifacts = collect_artifacts(result, clips_dir / shot_id)
            samples = [item for item in artifacts if item["kind"] == "samples"]
            previous_last_frame = frames_dir / f"{shot_id}-last.jpg"
            extract_last_frame(Path(samples[0]["path"]), previous_last_frame, ffmpeg, ffprobe)
            shot_state.update(
                {
                    "status": "Ready",
                    "completed_at": utc_now(),
                    "artifacts": artifacts,
                    "last_frame": str(previous_last_frame.resolve()),
                    "polling_url": polling_url,
                }
            )
        except Exception as exc:
            shot_state["last_error"] = str(exc)
            shot_state["updated_at"] = utc_now()
            state["updated_at"] = utc_now()
            write_json(state_path, state)
            raise
        state["updated_at"] = utc_now()
        write_json(state_path, state)
        print(f"镜头完成：{shot_id}", flush=True)


def print_plan(project_path: Path, project: dict[str, Any]) -> None:
    """打印不会触发 API 的执行计划。"""
    print(f"项目：{project.get('project')}")
    print(f"输出：{resolve_output_dir(project_path, project)}")
    print(f"镜头：{len(project['shots'])} / 上限 {project['max_submissions']}")
    for index, shot in enumerate(project["shots"], start=1):
        request = merged_shot(project, shot)
        continuity = "text-to-video opening" if index == 1 else "previous clip last frame"
        print(
            f"{index:02d}. {shot['id']} | STAR={shot.get('star', '-')} | "
            f"{request.get('duration', 'auto')}s {request.get('resolution', 'hd')} | "
            f"source={continuity}"
        )


def print_status(project_path: Path, project: dict[str, Any]) -> None:
    """显示本地断点状态。"""
    state_path = resolve_output_dir(project_path, project) / ".flux-video-state.json"
    if not state_path.exists():
        print("尚无执行状态")
        return
    state = read_json(state_path)
    print(f"已提交：{state.get('submission_count', 0)}")
    for shot in project["shots"]:
        item = state.get("shots", {}).get(shot["id"], {})
        print(f"{shot['id']}: {item.get('status', 'Not started')}")


def extract_last_frame_command(project_path: Path, project: dict[str, Any], shot_id: str, video: Path) -> None:
    """提取人工下载视频的末帧，并写入本地连续性目录。"""
    ffmpeg = resolve_executable(project, "ffmpeg_path", "ffmpeg")
    ffprobe = resolve_executable(project, "ffprobe_path", "ffprobe")
    output_dir = resolve_output_dir(project_path, project)
    output = output_dir / "continuity-frames" / f"{shot_id}-last.jpg"
    extract_last_frame(video.resolve(), output, ffmpeg, ffprobe)
    state_path = output_dir / ".flux-video-state.json"
    state = load_state(state_path, project)
    item = state["shots"].setdefault(shot_id, {})
    item.update(
        {
            "status": "Ready",
            "manual_import": True,
            "last_frame": str(output.resolve()),
            "artifacts": [{"kind": "samples", "path": str(video.resolve())}],
            "updated_at": utc_now(),
        }
    )
    state["updated_at"] = utc_now()
    write_json(state_path, state)
    print(f"末帧已提取：{output.resolve()}")


def build_parser() -> argparse.ArgumentParser:
    """构建命令行接口。"""
    parser = argparse.ArgumentParser(description="按共享首尾帧编排 FLUX 3 连续视频")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("validate", "plan", "status"):
        child = subparsers.add_parser(command)
        child.add_argument("project", type=Path)
    frame = subparsers.add_parser("extract-last-frame")
    frame.add_argument("project", type=Path)
    frame.add_argument("shot_id")
    frame.add_argument("video", type=Path)
    run = subparsers.add_parser("run")
    run.add_argument("project", type=Path)
    run.add_argument("--execute", action="store_true")
    run.add_argument("--confirm-run")
    run.add_argument("--poll-interval", type=int, default=6)
    run.add_argument("--poll-timeout", type=int, default=3600)
    run.add_argument("--submit-retries", type=int, default=3)
    return parser


def main() -> int:
    """执行命令并使用非零退出码暴露失败。"""
    args = build_parser().parse_args()
    project_path = args.project.resolve()
    try:
        project = read_json(project_path)
        errors = validate_project(project_path, project, check_media=args.command not in {"plan", "extract-last-frame"})
        if errors:
            for error in errors:
                print(f"错误：{error}", file=sys.stderr)
            return 2
        if args.command == "validate":
            print(f"验证通过：{len(project['shots'])} 个末帧接力镜头")
        elif args.command == "plan":
            print_plan(project_path, project)
        elif args.command == "status":
            print_status(project_path, project)
        elif args.command == "extract-last-frame":
            extract_last_frame_command(project_path, project, args.shot_id, args.video)
        elif args.command == "run":
            run_project(project_path, project, args)
        return 0
    except (ProjectError, APIError) as exc:
        print(f"失败：{exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("已中断；任务与下载状态已尽可能保存在项目输出目录", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
