#!/usr/bin/env python3
"""检测或从 yt-dlp 官方 GitHub Release 下载并校验平台二进制。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path


OFFICIAL_REPOSITORY = "yt-dlp/yt-dlp"
LATEST_RELEASE_API = f"https://api.github.com/repos/{OFFICIAL_REPOSITORY}/releases/latest"
CHECKSUM_ASSET = "SHA2-256SUMS"


def managed_tool_path(system: str | None = None) -> Path:
    """返回不依赖 Skill 安装目录的用户级工具路径。"""
    system = system or platform.system()
    filename = "yt-dlp.exe" if system == "Windows" else "yt-dlp"
    if system == "Windows":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "starline" / "tools" / "yt-dlp" / filename


def official_asset_name(system: str, machine: str) -> str | None:
    """按官方 Release 资产命名映射主流系统架构。"""
    arch = machine.lower().replace("amd64", "x86_64")
    if system == "Windows":
        if arch in {"x86_64", "x64"}:
            return "yt-dlp.exe"
        if arch in {"arm64", "aarch64"}:
            return "yt-dlp_arm64.exe"
        if arch in {"x86", "i386", "i686"}:
            return "yt-dlp_x86.exe"
    if system == "Darwin" and arch in {"x86_64", "x64", "arm64", "aarch64"}:
        return "yt-dlp_macos"
    if system == "Linux":
        if arch in {"x86_64", "x64"}:
            return "yt-dlp_linux"
        if arch in {"arm64", "aarch64"}:
            return "yt-dlp_linux_aarch64"
    return None


def parse_sha256(text: str, asset: str) -> str:
    """从官方 SHA2-256SUMS 精确读取目标资产校验值。"""
    for line in text.splitlines():
        parts = line.strip().split(maxsplit=1)
        if len(parts) == 2 and parts[1].lstrip("*") == asset:
            digest = parts[0].lower()
            if len(digest) == 64 and all(char in "0123456789abcdef" for char in digest):
                return digest
    raise RuntimeError(f"官方校验文件中没有资产：{asset}")


def normalized_curl_proxy(proxy: str) -> str:
    """让 SOCKS5 的 DNS 解析也经过代理，避免本地 DNS 泄漏或失败。"""
    return proxy.replace("socks5://", "socks5h://", 1)


def request_bytes(url: str, proxy: str | None = None) -> bytes:
    """按显式代理或标准环境访问官方 GitHub，并拒绝非 HTTPS 初始地址。"""
    if not url.startswith("https://"):
        raise RuntimeError(f"拒绝非 HTTPS 下载地址：{url}")
    if proxy:
        curl = shutil.which("curl.exe") or shutil.which("curl")
        if not curl:
            raise RuntimeError("显式代理下载需要系统 curl；未找到 curl/curl.exe")
        result = subprocess.run(
            [
                curl,
                "--location",
                "--fail",
                "--silent",
                "--show-error",
                "--connect-timeout", "30",
                "--max-time", "180",
                "--proxy", normalized_curl_proxy(proxy),
                "--header", "Accept: application/vnd.github+json",
                "--user-agent", "starline-flux-video-director",
                url,
            ],
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            message = result.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"通过显式代理访问 GitHub 失败：{message[:300]}")
        return result.stdout
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "starline-flux-video-director"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def latest_release(proxy: str | None = None) -> dict:
    """读取 yt-dlp 官方最新 Release 元数据。"""
    return json.loads(request_bytes(LATEST_RELEASE_API, proxy).decode("utf-8"))


def find_asset(release: dict, name: str) -> dict:
    """从官方 Release 精确选择一个资产。"""
    matches = [asset for asset in release.get("assets", []) if asset.get("name") == name]
    if len(matches) != 1:
        raise RuntimeError(f"官方 Release 中不存在唯一资产：{name}")
    url = matches[0].get("browser_download_url", "")
    expected = f"https://github.com/{OFFICIAL_REPOSITORY}/releases/download/"
    if not url.startswith(expected):
        raise RuntimeError(f"资产地址不属于 yt-dlp 官方 Release：{name}")
    return matches[0]


def executable_version(path: Path) -> str | None:
    """运行 yt-dlp --version，返回可用版本。"""
    try:
        result = subprocess.run([str(path), "--version"], capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def detect_existing(explicit: Path | None) -> tuple[Path | None, str | None]:
    """按显式路径、PATH、托管路径检测现有工具。"""
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(explicit.expanduser().resolve())
    path_tool = shutil.which("yt-dlp.exe") or shutil.which("yt-dlp")
    if path_tool:
        candidates.append(Path(path_tool))
    candidates.append(managed_tool_path())
    for candidate in candidates:
        if candidate.is_file():
            version = executable_version(candidate)
            if version:
                return candidate, version
    return None, None


def install(asset_name: str, target: Path, force: bool, proxy: str | None = None) -> str:
    """下载官方二进制和校验文件，验证后原子安装。"""
    if target.exists() and not force:
        raise RuntimeError(f"目标已存在：{target}；如需更新请显式使用 --force")
    release = latest_release(proxy)
    binary_asset = find_asset(release, asset_name)
    checksum_asset = find_asset(release, CHECKSUM_ASSET)
    checksums = request_bytes(checksum_asset["browser_download_url"], proxy).decode("utf-8")
    expected_digest = parse_sha256(checksums, asset_name)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix="yt-dlp-", suffix=".download", dir=target.parent, delete=False) as handle:
        temporary = Path(handle.name)
        payload = request_bytes(binary_asset["browser_download_url"], proxy)
        handle.write(payload)
    try:
        actual_digest = hashlib.sha256(temporary.read_bytes()).hexdigest()
        if actual_digest != expected_digest:
            raise RuntimeError(f"SHA-256 校验失败：期望 {expected_digest}，实际 {actual_digest}")
        if platform.system() != "Windows":
            temporary.chmod(temporary.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        os.replace(temporary, target)
        version = executable_version(target)
        if not version:
            target.unlink(missing_ok=True)
            raise RuntimeError("二进制校验通过，但执行 --version 失败，已移除目标文件")
        return version
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    """默认只检测；只有 --install 才联网下载。"""
    parser = argparse.ArgumentParser(description="Detect or securely install official yt-dlp release binary.")
    parser.add_argument("--install", action="store_true", help="从 yt-dlp 官方 GitHub Release 联网下载并校验")
    parser.add_argument("--force", action="store_true", help="显式覆盖托管路径的现有版本；必须与 --install 同用")
    parser.add_argument("--target", type=Path, help="安装到指定路径；默认使用用户级 Starline 工具目录")
    parser.add_argument("--asset", help="显式选择官方 Release 资产；仅用于自动识别不支持的平台")
    parser.add_argument("--proxy", help="仅本次下载使用的代理，例如 socks5://127.0.0.1:10808；不保存、不打印")
    args = parser.parse_args()
    if args.force and not args.install:
        raise SystemExit("--force 必须与 --install 同时使用")
    existing, version = detect_existing(args.target)
    if existing and not (args.install and args.force):
        print(f"yt-dlp 已就绪：{existing}")
        print(f"版本：{version}")
        return 0
    asset = args.asset or official_asset_name(platform.system(), platform.machine())
    if not asset:
        print("无法自动识别当前系统架构；请从 yt-dlp 官方 Release 名单确认后使用 --asset。", file=sys.stderr)
        return 2
    target = (args.target or managed_tool_path()).expanduser().resolve()
    if not args.install:
        print("未检测到可用 yt-dlp。默认不会联网下载。")
        print(f"官方资产：{asset}")
        print(f"计划安装位置：{target}")
        print("用户确认联网安装后运行：python scripts/setup_ytdlp.py --install")
        return 2
    try:
        installed_version = install(asset, target, args.force, args.proxy)
    except Exception as exc:
        print(f"yt-dlp 安装失败：{exc}", file=sys.stderr)
        return 3
    print(f"yt-dlp 已从官方 Release 安装并通过 SHA-256/执行验证：{target}")
    print(f"版本：{installed_version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
