"""验证 FLUX 视频交付打包的命名、复制和冲突保护。"""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "package_delivery.py"
SPEC = importlib.util.spec_from_file_location("package_delivery", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class PackageDeliveryTests(unittest.TestCase):
    """覆盖有序命名、封面复制、哈希校验和幂等执行。"""

    def make_project(self, root: Path) -> Path:
        """创建一个包含两段镜头和封面的最小测试项目。"""
        generated = root / "generated"
        for shot_id, payload in (("01-start", b"video-one"), ("02-result", b"video-two")):
            shot_dir = generated / "clips" / shot_id
            shot_dir.mkdir(parents=True)
            (shot_dir / f"{shot_id}.mp4").write_bytes(payload)
        (root / "cover.png").write_bytes(b"cover")
        project = {
            "project": "test-project",
            "output_dir": "./generated",
            "delivery": {
                "folder": "测试项目",
                "cover": "./cover.png",
                "shot_titles": {
                    "01-start": "S危机-问题出现",
                    "02-result": "R结果-完成闭环",
                },
            },
            "shots": [{"id": "01-start"}, {"id": "02-result"}],
        }
        project_path = root / "project.json"
        project_path.write_text(json.dumps(project, ensure_ascii=False), encoding="utf-8")
        return project_path

    def test_execute_creates_ordered_verified_delivery(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project = self.make_project(root)
            target = root / "delivery"
            code = MODULE.main(
                [str(project), "--target-root", str(target), "--delivery-date", "20260812", "--execute"]
            )
            self.assertEqual(code, 0)
            output = target / "20260812" / "测试项目"
            self.assertEqual((output / "00-封面-测试项目.png").read_bytes(), b"cover")
            self.assertEqual((output / "01-S危机-问题出现.mp4").read_bytes(), b"video-one")
            self.assertEqual((output / "02-R结果-完成闭环.mp4").read_bytes(), b"video-two")
            self.assertFalse(any(output.glob("*.part")))

            # 第二次执行应幂等跳过同内容文件。
            self.assertEqual(
                MODULE.main(
                    [str(project), "--target-root", str(target), "--delivery-date", "20260812", "--execute"]
                ),
                0,
            )

    def test_conflicting_destination_is_not_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project = self.make_project(root)
            target = root / "delivery"
            output = target / "20260812" / "测试项目"
            output.mkdir(parents=True)
            conflict = output / "01-S危机-问题出现.mp4"
            conflict.write_bytes(b"user-file")
            with self.assertRaises(FileExistsError):
                MODULE.main(
                    [str(project), "--target-root", str(target), "--delivery-date", "20260812", "--execute"]
                )
            self.assertEqual(conflict.read_bytes(), b"user-file")


if __name__ == "__main__":
    unittest.main()
