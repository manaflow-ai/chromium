from __future__ import annotations

import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path

from scripts import validate_runtime_archive as validator

PACKAGE_NAME = "owl-chromium-runtime-macos-arm64-7523a3a72320"
SOURCE_REPOSITORY = "https://github.com/manaflow-ai/chromium-src.git"
SOURCE_REF = "feat/owl-fresh-host"
SOURCE_COMMIT = "7523a3a72320b403d509860f8ffaec9ac20d150e"
ARTIFACT_REPOSITORY = "manaflow-ai/chromium"


def _manifest() -> dict[str, object]:
    return {
        "chromiumSourceRepo": SOURCE_REPOSITORY,
        "chromiumSourceRef": SOURCE_REF,
        "chromiumSourceCommit": SOURCE_COMMIT,
        "artifactRepo": ARTIFACT_REPOSITORY,
        "artifactWorkflow": "Build OWL Chromium Runtime",
        "artifactRunId": "123",
        "artifactRunAttempt": "1",
        "runnerName": "chromium-runner",
        "runnerOS": "macOS",
        "runnerArch": "ARM64",
        "gnOutDir": "out/owl-release",
        "ninjaTargets": ["content_shell", "owl_fresh_mojo_runtime"],
    }


def _write_archive(
    path: Path,
    *,
    extra: tuple[str, str] | None = None,
    link: tuple[str, str] | None = None,
    manifest: dict[str, object] | None = None,
    manifest_body: bytes | None = None,
    omit_root: str | None = None,
    extra_mode: int = 0o644,
    extra_type: bytes | None = None,
    root_type: bytes = tarfile.DIRTYPE,
) -> None:
    with tarfile.open(path, "w:gz") as archive:
        root = tarfile.TarInfo(f"{PACKAGE_NAME}/")
        root.type = root_type
        archive.addfile(root)
        for name in (
            "Content Shell.app/",
            "Content Shell Helper.app/",
            "Content Shell Helper (GPU).app/",
            "Content Shell Helper (Renderer).app/",
        ):
            if name.rstrip("/") == omit_root:
                continue
            item = tarfile.TarInfo(f"{PACKAGE_NAME}/{name}")
            item.type = tarfile.DIRTYPE
            archive.addfile(item)
        for name, body in (
            ("libowl_fresh_mojo_runtime.dylib", b"runtime"),
            ("owl-build-args.gn", b'target_cpu = "arm64"\n'),
            (
                "owl-runtime-manifest.json",
                manifest_body
                if manifest_body is not None
                else json.dumps(manifest or _manifest()).encode(),
            ),
        ):
            if name == omit_root:
                continue
            item = tarfile.TarInfo(f"{PACKAGE_NAME}/{name}")
            item.size = len(body)
            archive.addfile(item, io.BytesIO(body))
        if extra is not None:
            name, body = extra
            item = tarfile.TarInfo(name)
            item.mode = extra_mode
            item.type = extra_type or tarfile.REGTYPE
            if extra_type is not None:
                archive.addfile(item)
                return
            item.size = len(body.encode())
            archive.addfile(item, io.BytesIO(body.encode()))
        if link is not None:
            name, target = link
            item = tarfile.TarInfo(name)
            item.type = tarfile.SYMTYPE
            item.linkname = target
            archive.addfile(item)


class RuntimeArchiveTests(unittest.TestCase):
    def _validate(self, path: Path) -> None:
        validator.validate_archive(
            str(path),
            PACKAGE_NAME,
            source_repository=SOURCE_REPOSITORY,
            source_ref=SOURCE_REF,
            source_commit=SOURCE_COMMIT,
            artifact_repository=ARTIFACT_REPOSITORY,
        )

    def test_accepts_expected_archive(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runtime.tar.gz"
            _write_archive(path)
            self._validate(path)

    def test_rejects_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runtime.tar.gz"
            _write_archive(path, extra=(f"{PACKAGE_NAME}/../outside", "bad"))
            with self.assertRaises(validator.ArchiveError):
                self._validate(path)

    def test_rejects_link_escape(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runtime.tar.gz"
            _write_archive(path, link=(f"{PACKAGE_NAME}/escape", "../../outside"))
            with self.assertRaises(validator.ArchiveError):
                self._validate(path)

    def test_rejects_manifest_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runtime.tar.gz"
            manifest = _manifest()
            manifest["chromiumSourceCommit"] = "0" * 40
            _write_archive(path, manifest=manifest)
            with self.assertRaises(validator.ArchiveError):
                self._validate(path)

    def test_rejects_duplicate_normalized_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runtime.tar.gz"
            _write_archive(
                path,
                extra=(f"{PACKAGE_NAME}/./owl-build-args.gn", "replacement"),
            )
            with self.assertRaises(validator.ArchiveError):
                self._validate(path)

    def test_rejects_setuid_member(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runtime.tar.gz"
            _write_archive(
                path, extra=(f"{PACKAGE_NAME}/tool", "body"), extra_mode=0o4755
            )
            with self.assertRaises(validator.ArchiveError):
                self._validate(path)

    def test_rejects_special_member(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runtime.tar.gz"
            _write_archive(
                path,
                extra=(f"{PACKAGE_NAME}/fifo", ""),
                extra_type=tarfile.FIFOTYPE,
            )
            with self.assertRaises(validator.ArchiveError):
                self._validate(path)

    def test_rejects_missing_required_root_entry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runtime.tar.gz"
            _write_archive(path, omit_root="owl-build-args.gn")
            with self.assertRaises(validator.ArchiveError):
                self._validate(path)

    def test_rejects_oversized_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runtime.tar.gz"
            _write_archive(path, manifest_body=b"{" + b"x" * (128 * 1024) + b"}")
            with self.assertRaises(validator.ArchiveError):
                self._validate(path)

    def test_rejects_non_directory_package_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runtime.tar.gz"
            _write_archive(path, root_type=tarfile.REGTYPE)
            with self.assertRaises(validator.ArchiveError):
                self._validate(path)

    def test_rejects_unsafe_package_name(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runtime.tar.gz"
            _write_archive(path)
            with self.assertRaises(validator.ArchiveError):
                validator.validate_archive(
                    str(path),
                    "..",
                    source_repository=SOURCE_REPOSITORY,
                    source_ref=SOURCE_REF,
                    source_commit=SOURCE_COMMIT,
                    artifact_repository=ARTIFACT_REPOSITORY,
                )


if __name__ == "__main__":
    unittest.main()
