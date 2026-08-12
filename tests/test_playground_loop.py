"""验证 Playground 提交失败分类的纯逻辑边界。"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "playground_loop.py"
SPEC = importlib.util.spec_from_file_location("playground_loop", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class PlaygroundLoopTests(unittest.TestCase):
    """确保页面噪声不会触发重试，明确服务错误才会。"""

    def test_explicit_service_failure_is_failed(self) -> None:
        text = "system_error Service issue BFL returned status 503 over capacity"
        self.assertEqual(MODULE.classify_task_text(text), "failed")

    def test_rate_limited_card_is_failed(self) -> None:
        text = "system_error Rate limited You're sending requests too quickly. Retry"
        self.assertEqual(MODULE.classify_task_text(text), "failed")

    def test_queue_is_active(self) -> None:
        self.assertEqual(MODULE.classify_task_text("QUEUED · 1 VIDEO · Cancel"), "active")

    def test_console_noise_is_unknown(self) -> None:
        text = "Minified React error #418 preload CSP frame-src warning"
        self.assertEqual(MODULE.classify_task_text(text), "unknown")


if __name__ == "__main__":
    unittest.main()
