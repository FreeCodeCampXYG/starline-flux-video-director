from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).parents[1] / "scripts" / "flux_video_loop.py"
SPEC = importlib.util.spec_from_file_location("flux_video_loop", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def project_with_frames(root: Path) -> dict:
    """创建首段文生视频、次段末帧接力的最小项目。"""
    frame_a = root / "a.jpg"
    frame_b = root / "b.jpg"
    frame_c = root / "c.jpg"
    for frame in (frame_a, frame_b, frame_c):
        frame.write_bytes(b"fake-jpeg-for-request-shape-test")
    return {
        "project": "test-film",
        "endpoint": "https://api.bfl.ai/v1/flux-3-video",
        "output_dir": "./generated",
        "max_submissions": 2,
        "defaults": {
            "aspect_ratio": "16:9",
            "duration": 20,
            "resolution": "fhd",
            "generate_audio": True,
            "safety_tolerance": 2,
            "draft": False,
        },
        "shots": [
            {"id": "01", "mode": "t2v", "prompt": "first movement"},
            {
                "id": "02",
                "mode": "i2v",
                "prompt": "second movement",
                "keyframes": "auto_previous_last_frame",
            },
        ],
    }


class FluxVideoLoopTests(unittest.TestCase):
    def test_valid_last_frame_relay_chain(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project = project_with_frames(root)
            project_path = root / "project.json"
            project_path.write_text(json.dumps(project), encoding="utf-8")
            self.assertEqual(MODULE.validate_project(project_path, project), [])

    def test_plan_validation_allows_missing_media(self) -> None:
        project = {
            "project": "plan-only",
            "endpoint": "https://api.bfl.ai/v1/flux-3-video",
            "output_dir": "./generated",
            "max_submissions": 1,
            "defaults": {"duration": 20, "resolution": "fhd"},
            "shots": [{"id": "01", "mode": "t2v", "prompt": "move"}],
        }
        self.assertEqual(MODULE.validate_project(Path("project.json"), project, check_media=False), [])

    def test_rejects_non_automatic_relay(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project = project_with_frames(root)
            project["shots"][1]["keyframes"] = str(root / "manual.jpg")
            errors = MODULE.validate_project(root / "project.json", project)
            self.assertTrue(any("auto_previous_last_frame" in error for error in errors))

    def test_build_request_inlines_local_frames_and_keeps_snapshot_safe(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project = project_with_frames(root)
            previous = root / "b.jpg"
            request, safe = MODULE.build_request(
                root / "project.json", project, project["shots"][1], previous
            )
            self.assertTrue(request["keyframes"].startswith("data:image/jpeg;base64,"))
            self.assertFalse(safe["keyframes"].startswith("data:"))
            self.assertNotIn("BFL_API_KEY", json.dumps(safe))

    def test_signed_url_is_redacted_in_snapshot(self) -> None:
        url = "https://cdn.example/video.jpg?sv=1&sig=secret&token=private"
        safe = MODULE.redact_url(url)
        self.assertNotIn("secret", safe)
        self.assertNotIn("private", safe)
        self.assertIn("redacted", safe)

    def test_real_run_requires_api_key_without_printing_value(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project = project_with_frames(root)
            args = mock.Mock(execute=True, confirm_run="FREE_PROMO_CONFIRMED")
            with mock.patch.object(MODULE, "get_api_key", return_value=""):
                with self.assertRaisesRegex(MODULE.ProjectError, "BFL_API_KEY 未设置"):
                    MODULE.run_project(root / "project.json", project, args)

    def test_resume_skips_completed_shot(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project = project_with_frames(root)
            project["shots"] = [project["shots"][0]]
            project["max_submissions"] = 1
            project["ffmpeg_path"] = "fake-ffmpeg"
            project["ffprobe_path"] = "fake-ffprobe"
            output = root / "generated"
            output.mkdir()
            artifact = output / "done.mp4"
            artifact.write_bytes(b"done")
            last_frame = output / "last.jpg"
            last_frame.write_bytes(b"frame")
            state = {
                "project": "test-film",
                "submission_count": 1,
                "shots": {
                    "01": {
                        "status": "Ready",
                        "artifacts": [{"kind": "samples", "path": str(artifact)}],
                        "last_frame": str(last_frame),
                    }
                },
            }
            MODULE.write_json(output / ".flux-video-state.json", state)
            args = mock.Mock(
                execute=True,
                confirm_run="FREE_PROMO_CONFIRMED",
                submit_retries=0,
                poll_interval=1,
                poll_timeout=1,
            )
            with mock.patch.object(MODULE, "get_api_key", return_value="never-print-this"):
                with mock.patch.object(MODULE, "resolve_executable", side_effect=["ffmpeg", "ffprobe"]):
                    with mock.patch.object(MODULE, "submit") as submit:
                        MODULE.run_project(root / "project.json", project, args)
                        submit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
