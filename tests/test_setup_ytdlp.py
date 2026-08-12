"""验证 yt-dlp 官方资产选择和校验文件解析。"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "setup_ytdlp.py"
SPEC = importlib.util.spec_from_file_location("setup_ytdlp", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class SetupYtdlpTests(unittest.TestCase):
    """覆盖主流平台映射和精确 SHA-256 匹配。"""

    def test_official_asset_mapping(self) -> None:
        self.assertEqual(MODULE.official_asset_name("Windows", "AMD64"), "yt-dlp.exe")
        self.assertEqual(MODULE.official_asset_name("Windows", "ARM64"), "yt-dlp_arm64.exe")
        self.assertEqual(MODULE.official_asset_name("Darwin", "arm64"), "yt-dlp_macos")
        self.assertEqual(MODULE.official_asset_name("Linux", "x86_64"), "yt-dlp_linux")
        self.assertEqual(MODULE.official_asset_name("Linux", "aarch64"), "yt-dlp_linux_aarch64")

    def test_unknown_platform_requires_explicit_asset(self) -> None:
        self.assertIsNone(MODULE.official_asset_name("FreeBSD", "x86_64"))

    def test_parse_sha256_uses_exact_asset_name(self) -> None:
        digest = "a" * 64
        text = f"{'b' * 64}  yt-dlp_arm64.exe\n{digest} *yt-dlp.exe\n"
        self.assertEqual(MODULE.parse_sha256(text, "yt-dlp.exe"), digest)

    def test_socks_proxy_uses_remote_dns(self) -> None:
        self.assertEqual(
            MODULE.normalized_curl_proxy("socks5://127.0.0.1:10808"),
            "socks5h://127.0.0.1:10808",
        )

    def test_http_proxy_is_unchanged(self) -> None:
        self.assertEqual(
            MODULE.normalized_curl_proxy("http://127.0.0.1:10808"),
            "http://127.0.0.1:10808",
        )


if __name__ == "__main__":
    unittest.main()
