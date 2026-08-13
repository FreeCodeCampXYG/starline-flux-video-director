"""把 FLUX 多镜头项目复制为有序、可校验的剪辑交付目录。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from datetime import date
from pathlib import Path
from typing import Any


WINDOWS_DEFAULT_ROOT = Path(r"D:\data\AI资料")
INVALID_WINDOWS_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def load_project(project_path: Path) -> dict[str, Any]:
    """读取项目 JSON，并确保顶层是对象。"""
    with project_path.open("r", encoding="utf-8-sig") as handle:
        project = json.load(handle)
    if not isinstance(project, dict):
        raise ValueError("项目 JSON 顶层必须是对象")
    return project


def resolve_path(value: str | Path, base_dir: Path) -> Path:
    """把相对路径按项目 JSON 所在目录解析为绝对路径。"""
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()


def safe_filename(value: str) -> str:
    """生成保留中文、兼容 Windows 的单段文件名。"""
    cleaned = INVALID_WINDOWS_CHARS.sub("-", value).strip().rstrip(". ")
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned:
        raise ValueError("交付文件名不能为空")
    return cleaned


def sha256_file(path: Path) -> str:
    """流式计算文件 SHA-256，避免大视频一次读入内存。"""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def resolve_target_root(args: argparse.Namespace, delivery: dict[str, Any], base_dir: Path) -> Path:
    """按命令、项目配置、环境变量和 Windows 默认值解析交付根目录。"""
    configured = args.target_root or delivery.get("target_root") or os.getenv(
        "STARLINE_VIDEO_DELIVERY_ROOT"
    )
    if configured:
        return resolve_path(configured, base_dir)
    if os.name == "nt":
        return WINDOWS_DEFAULT_ROOT
    raise ValueError(
        "非 Windows 平台必须使用 --target-root、delivery.target_root 或 "
        "STARLINE_VIDEO_DELIVERY_ROOT 指定交付根目录"
    )


def find_shot_video(clips_dir: Path, shot_id: str) -> Path:
    """按规范路径定位镜头视频，必要时接受镜头目录内唯一 MP4。"""
    shot_dir = clips_dir / shot_id
    canonical = shot_dir / f"{shot_id}.mp4"
    if canonical.is_file():
        return canonical
    candidates = sorted(shot_dir.glob("*.mp4")) if shot_dir.is_dir() else []
    if len(candidates) == 1:
        return candidates[0]
    raise FileNotFoundError(f"无法唯一定位镜头视频：{shot_id}（目录：{shot_dir}）")


def copy_verified(source: Path, destination: Path, execute: bool, overwrite: bool) -> str:
    """复制并核对哈希；同内容幂等跳过，不静默覆盖异内容文件。"""
    if not source.is_file():
        raise FileNotFoundError(f"源文件不存在：{source}")
    source_hash = sha256_file(source)
    if destination.exists():
        destination_hash = sha256_file(destination)
        if destination_hash == source_hash:
            return "已存在且校验一致"
        if not overwrite:
            raise FileExistsError(f"目标同名但内容不同，拒绝覆盖：{destination}")
    if not execute:
        return "计划复制"
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".part")
    if temporary.exists():
        temporary.unlink()
    shutil.copy2(source, temporary)
    if sha256_file(temporary) != source_hash:
        temporary.unlink(missing_ok=True)
        raise OSError(f"复制后 SHA-256 校验失败：{destination}")
    temporary.replace(destination)
    return "复制并校验完成"


def build_items(
    project: dict[str, Any],
    project_path: Path,
    args: argparse.Namespace,
    folder_name: str,
) -> list[tuple[Path, str, str]]:
    """根据项目镜头顺序构建源文件、交付文件名和类型列表。"""
    base_dir = project_path.parent
    delivery = project.get("delivery") or {}
    output_dir = resolve_path(project.get("output_dir", "./generated"), base_dir)
    clips_dir = output_dir / "clips"
    shot_titles = delivery.get("shot_titles") or {}
    shots = project.get("shots")
    if not isinstance(shots, list) or not shots:
        raise ValueError("项目 JSON 必须包含非空 shots 数组")

    items: list[tuple[Path, str, str]] = []
    cover_value = args.cover or delivery.get("cover")
    if cover_value:
        cover = resolve_path(cover_value, base_dir)
        items.append((cover, f"00-封面-{safe_filename(folder_name)}{cover.suffix.lower()}", "cover"))

    for index, shot in enumerate(shots, start=1):
        if not isinstance(shot, dict) or not shot.get("id"):
            raise ValueError(f"第 {index} 个镜头缺少 id")
        shot_id = str(shot["id"])
        title = str(shot_titles.get(shot_id) or shot.get("delivery_title") or shot_id)
        title = re.sub(r"^\d{1,3}[-_ ]+", "", title)
        source = find_shot_video(clips_dir, shot_id)
        items.append((source, f"{index:02d}-{safe_filename(title)}.mp4", "shot"))

    for extra in args.test_clip:
        source = resolve_path(extra, Path.cwd())
        items.append((source, f"99-测试片-{safe_filename(source.stem)}{source.suffix.lower()}", "test"))
    return items


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """解析交付打包命令行参数。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path, help="FLUX 项目 JSON")
    parser.add_argument("--target-root", help="交付根目录；Windows 默认 D:\\data\\AI资料")
    parser.add_argument("--delivery-date", help="日期目录，格式 YYYYMMDD")
    parser.add_argument("--folder", help="项目交付文件夹名称")
    parser.add_argument("--cover", help="封面图片路径")
    parser.add_argument("--test-clip", action="append", default=[], help="额外测试片，可重复传入")
    parser.add_argument("--execute", action="store_true", help="真实复制；默认只预览计划")
    parser.add_argument("--overwrite", action="store_true", help="显式覆盖同名异内容文件")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """预览或执行交付打包，并输出逐文件校验状态。"""
    args = parse_args(argv)
    project_path = args.project.expanduser().resolve()
    project = load_project(project_path)
    delivery = project.get("delivery") or {}
    delivery_date = args.delivery_date or delivery.get("date") or date.today().strftime("%Y%m%d")
    if not re.fullmatch(r"\d{8}", str(delivery_date)):
        raise ValueError("交付日期必须是 YYYYMMDD 格式")
    folder_name = safe_filename(args.folder or delivery.get("folder") or project.get("project") or "FLUX-video")
    target_root = resolve_target_root(args, delivery, project_path.parent)
    target_dir = target_root / str(delivery_date) / folder_name
    items = build_items(project, project_path, args, folder_name)

    print(f"交付目录：{target_dir}")
    if not any(kind == "cover" for _, _, kind in items):
        print("警告：未配置封面；建议使用 --cover 或 delivery.cover。", file=sys.stderr)
    for source, filename, _kind in items:
        destination = target_dir / filename
        status = copy_verified(source, destination, args.execute, args.overwrite)
        print(f"[{status}] {source} -> {destination}")
    if not args.execute:
        print("当前为预览；确认顺序和命名后追加 --execute。")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"交付打包失败：{exc}", file=sys.stderr)
        raise SystemExit(1)
