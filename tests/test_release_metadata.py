from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts import validate_release_metadata as metadata

TAG = "owl-chromium-" + "7" * 40
TITLE = "OWL Chromium runtime 777777777777"
ARCHIVE_NAME = "owl-chromium-runtime-macos-arm64-777777777777.tar.gz"
CHECKSUM_NAME = ARCHIVE_NAME + ".sha256"
EXPECTED_ASSETS = {
    ARCHIVE_NAME: "sha256:" + "a" * 64,
    CHECKSUM_NAME: "sha256:" + "b" * 64,
}


def _asset(name: str, digest: str) -> dict[str, str]:
    return {"name": name, "digest": digest}


def _release(assets: list[dict[str, str]]) -> dict[str, object]:
    return {
        "tag_name": TAG,
        "name": TITLE,
        "draft": True,
        "prerelease": False,
        "assets": assets,
    }


class ReleaseMetadataTests(unittest.TestCase):
    def _validate(
        self,
        release: object,
        *,
        require_complete: bool = False,
        expected_assets: dict[str, str] = EXPECTED_ASSETS,
    ) -> None:
        metadata.validate_release(
            release,
            expected_tag=TAG,
            expected_title=TITLE,
            expected_assets=expected_assets,
            require_complete=require_complete,
        )

    def test_accepts_draft_with_missing_expected_assets(self) -> None:
        self._validate(_release([]))

    def test_accepts_complete_release(self) -> None:
        assets = [_asset(name, digest) for name, digest in EXPECTED_ASSETS.items()]
        self._validate(_release(assets), require_complete=True)

    def test_rejects_unexpected_asset(self) -> None:
        assets = [_asset(name, digest) for name, digest in EXPECTED_ASSETS.items()]
        assets.append(_asset("malicious.zip", "sha256:" + "c" * 64))
        with self.assertRaises(metadata.ReleaseMetadataError):
            self._validate(_release(assets))

    def test_rejects_duplicate_asset_name(self) -> None:
        assets = [_asset(ARCHIVE_NAME, EXPECTED_ASSETS[ARCHIVE_NAME])] * 2
        with self.assertRaises(metadata.ReleaseMetadataError):
            self._validate(_release(assets))

    def test_rejects_digest_mismatch(self) -> None:
        assets = [_asset(name, digest) for name, digest in EXPECTED_ASSETS.items()]
        assets[0]["digest"] = "sha256:" + "c" * 64
        with self.assertRaises(metadata.ReleaseMetadataError):
            self._validate(_release(assets))

    def test_rejects_missing_asset_when_complete(self) -> None:
        with self.assertRaises(metadata.ReleaseMetadataError):
            self._validate(
                _release([_asset(ARCHIVE_NAME, EXPECTED_ASSETS[ARCHIVE_NAME])]),
                require_complete=True,
            )

    def test_rejects_wrong_tag_or_title(self) -> None:
        release = _release([])
        release["tag_name"] = "other"
        with self.assertRaises(metadata.ReleaseMetadataError):
            self._validate(release)

        release = _release([])
        release["name"] = "other"
        with self.assertRaises(metadata.ReleaseMetadataError):
            self._validate(release)

    def test_rejects_prerelease(self) -> None:
        release = _release([])
        release["prerelease"] = True
        with self.assertRaises(metadata.ReleaseMetadataError):
            self._validate(release)

    def test_rejects_duplicate_json_keys(self) -> None:
        body = f'{{"tag_name":"{TAG}","tag_name":"{TAG}"}}'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "release.json"
            path.write_text(body, encoding="utf-8")
            with self.assertRaises(metadata.ReleaseMetadataError):
                metadata.load_release(path)


if __name__ == "__main__":
    unittest.main()
