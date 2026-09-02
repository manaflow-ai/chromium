#!/usr/bin/env python3
"""Validate an OWL Chromium runtime archive before it is published."""

from __future__ import annotations

import argparse
import json
import stat
import sys
import tarfile
from pathlib import PurePosixPath

REQUIRED_ROOT_ENTRIES = frozenset(
    {
        "Content Shell.app",
        "Content Shell Helper.app",
        "Content Shell Helper (GPU).app",
        "Content Shell Helper (Renderer).app",
        "libowl_fresh_mojo_runtime.dylib",
        "owl-build-args.gn",
        "owl-runtime-manifest.json",
    }
)
EXPECTED_TARGETS = ["content_shell", "owl_fresh_mojo_runtime"]


class ArchiveError(ValueError):
    """Raised when an archive member or manifest is unsafe."""


def _safe_member_name(name: str, package_name: str) -> PurePosixPath:
    if "\\" in name or "\x00" in name:
        raise ArchiveError(f"unsafe archive member name: {name!r}")
    path = PurePosixPath(name)
    if (
        path.is_absolute()
        or ".." in path.parts
        or not path.parts
        or path.parts[0] != package_name
    ):
        raise ArchiveError(f"archive member escapes package root: {name!r}")
    return path


def _safe_link_target(
    member: tarfile.TarInfo, path: PurePosixPath, package_name: str
) -> None:
    target = PurePosixPath(member.linkname)
    if (
        not member.linkname
        or target.is_absolute()
        or "\\" in member.linkname
        or "\x00" in member.linkname
    ):
        raise ArchiveError(f"unsafe link target for {member.name!r}")
    resolved = path.parent / target
    if (
        ".." in resolved.parts
        or not resolved.parts
        or resolved.parts[0] != package_name
    ):
        raise ArchiveError(f"link escapes package root: {member.name!r}")


def _scan_members(
    archive: tarfile.TarFile, package_name: str
) -> tuple[set[str], dict[str, object] | None]:
    seen: set[str] = set()
    root_entries: set[str] = set()
    manifest: dict[str, object] | None = None
    for member in archive:
        path = _safe_member_name(member.name, package_name)
        canonical_name = path.as_posix()
        if canonical_name in seen:
            raise ArchiveError(f"duplicate archive member: {member.name!r}")
        seen.add(canonical_name)
        if member.mode & (stat.S_ISUID | stat.S_ISGID):
            raise ArchiveError(f"setuid/setgid member is not allowed: {member.name!r}")
        if not (member.isdir() or member.isreg() or member.issym() or member.islnk()):
            raise ArchiveError(f"special file is not allowed: {member.name!r}")
        if len(path.parts) == 1 and not member.isdir():
            raise ArchiveError("package root must be a directory")
        if len(path.parts) == 2:
            root_entries.add(path.parts[1])
        if member.issym() or member.islnk():
            _safe_link_target(member, path, package_name)
        if path == PurePosixPath(package_name, "owl-runtime-manifest.json"):
            if not member.isreg() or member.size > 128 * 1024:
                raise ArchiveError("runtime manifest must be a small regular file")
            stream = archive.extractfile(member)
            if stream is None:
                raise ArchiveError("runtime manifest cannot be read")
            try:
                manifest = json.loads(stream.read(128 * 1024 + 1).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ArchiveError(
                    f"runtime manifest is not valid UTF-8 JSON: {error}"
                ) from error
            if not isinstance(manifest, dict):
                raise ArchiveError("runtime manifest must be a JSON object")
    return root_entries, manifest


def validate_archive(
    archive_path: str,
    package_name: str,
    *,
    source_repository: str,
    source_ref: str,
    source_commit: str,
    artifact_repository: str,
) -> None:
    if not package_name or "/" in package_name or package_name in {".", ".."}:
        raise ArchiveError("package name must be a single safe path component")
    try:
        with tarfile.open(archive_path, mode="r:gz") as archive:
            root_entries, manifest = _scan_members(archive, package_name)
    except (OSError, tarfile.TarError) as error:
        raise ArchiveError(f"cannot read archive: {error}") from error

    missing = REQUIRED_ROOT_ENTRIES - root_entries
    if missing:
        raise ArchiveError(
            "archive is missing required root entries: " + ", ".join(sorted(missing))
        )
    if manifest is None:
        raise ArchiveError("archive does not contain a runtime manifest")
    expected = {
        "chromiumSourceRepo": source_repository,
        "chromiumSourceRef": source_ref,
        "chromiumSourceCommit": source_commit,
        "artifactRepo": artifact_repository,
        "ninjaTargets": EXPECTED_TARGETS,
    }
    for key, expected_value in expected.items():
        if manifest.get(key) != expected_value:
            raise ArchiveError(
                f"runtime manifest field {key!r} does not match the reviewed build"
            )
    for key in (
        "artifactWorkflow",
        "artifactRunId",
        "artifactRunAttempt",
        "runnerName",
        "runnerOS",
        "runnerArch",
        "gnOutDir",
    ):
        value = manifest.get(key)
        if not isinstance(value, str) or not value:
            raise ArchiveError(
                f"runtime manifest field {key!r} must be a non-empty string"
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True)
    parser.add_argument("--package-name", required=True)
    parser.add_argument("--source-repository", required=True)
    parser.add_argument("--source-ref", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--artifact-repository", required=True)
    args = parser.parse_args(argv)
    try:
        validate_archive(
            args.archive,
            args.package_name,
            source_repository=args.source_repository,
            source_ref=args.source_ref,
            source_commit=args.source_commit,
            artifact_repository=args.artifact_repository,
        )
    except ArchiveError as error:
        print(f"runtime archive rejected: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
