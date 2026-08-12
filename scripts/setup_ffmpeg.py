#!/usr/bin/env python3
"""检测或通过当前平台包管理器安装 FFmpeg；只有 --install 才会联网执行安装。"""

from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
import sys


def find_tools() -> tuple[str | None, str | None]:
    """返回 PATH 中的 ffmpeg 与 ffprobe 可执行文件。"""
    return shutil.which("ffmpeg"), shutil.which("ffprobe")


def install_command(system: str) -> list[str] | None:
    """按操作系统选择可信包管理器的在线安装命令。"""
    if system == "Windows":
        if not shutil.which("winget"):
            return None
        return [
            "winget", "install", "--id", "Gyan.FFmpeg.Shared", "--exact",
            "--accept-package-agreements", "--accept-source-agreements",
        ]
    if system == "Darwin":
        if not shutil.which("brew"):
            return None
        return ["brew", "install", "ffmpeg"]
    if system == "Linux":
        if shutil.which("apt-get"):
            return ["sudo", "apt-get", "install", "-y", "ffmpeg"]
        if shutil.which("dnf"):
            return ["sudo", "dnf", "install", "-y", "ffmpeg"]
        if shutil.which("pacman"):
            return ["sudo", "pacman", "-S", "--needed", "ffmpeg"]
    return None


def main() -> int:
    """输出检测结果；用户明确传入 --install 后才执行下载与安装。"""
    parser = argparse.ArgumentParser(description="Detect or install FFmpeg for this skill.")
    parser.add_argument("--install", action="store_true", help="通过平台包管理器联网安装 FFmpeg")
    args = parser.parse_args()
    ffmpeg, ffprobe = find_tools()
    if ffmpeg and ffprobe:
        print(f"FFmpeg 已就绪：{ffmpeg}")
        print(f"FFprobe 已就绪：{ffprobe}")
        return 0
    system = platform.system()
    command = install_command(system)
    if not args.install:
        print("未检测到完整的 ffmpeg/ffprobe。")
        if command:
            print("运行以下命令进行联网安装：")
            print(" ".join(command))
            print("或运行：python scripts/setup_ffmpeg.py --install")
        else:
            print(f"当前系统 {system} 缺少受支持的包管理器；请先安装 winget、Homebrew 或系统包管理器。")
        return 2
    if not command:
        print(f"无法为 {system} 自动安装：缺少受支持的包管理器。", file=sys.stderr)
        return 2
    print("将通过平台包管理器联网安装 FFmpeg：", " ".join(command))
    result = subprocess.run(command, check=False)
    if result.returncode != 0:
        return result.returncode
    ffmpeg, ffprobe = find_tools()
    if not (ffmpeg and ffprobe):
        print("安装完成后当前终端仍未发现 ffmpeg/ffprobe；请重开终端后重试。", file=sys.stderr)
        return 3
    print(f"FFmpeg 安装并验证完成：{ffmpeg}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
