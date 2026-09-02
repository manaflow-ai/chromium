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
REQUIRED_ROOT_DIRECTORIES = frozenset(
    {
        "Content Shell.app",
        "Content Shell Helper.app",
        "Content Shell Helper (GPU).app",
        "Content Shell Helper (Renderer).app",
    }
)
REQUIRED_ROOT_FILES = REQUIRED_ROOT_ENTRIES - REQUIRED_ROOT_DIRECTORIES
REQUIRED_NONEMPTY_ROOT_FILES = frozenset({"libowl_fresh_mojo_runtime.dylib"})
REQUIRED_EXECUTABLES = frozenset(
    {
        "Content Shell.app/Contents/MacOS/Content Shell",
        "Content Shell Helper.app/Contents/MacOS/Content Shell Helper",
        "Content Shell Helper (GPU).app/Contents/MacOS/Content Shell Helper (GPU)",
        "Content Shell Helper (Renderer).app/Contents/MacOS/Content Shell Helper (Renderer)",
    }
)
EXPECTED_TARGETS = ["content_shell", "owl_fresh_mojo_runtime"]


class ArchiveError(ValueError):
    """Raised when an archive member or manifest is unsafe."""


def _reject_duplicate_manifest_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    values: dict[str, object] = {}
    for key, value in pairs:
        if key in values:
            raise ArchiveError(f"runtime manifest contains duplicate key: {key}")
        values[key] = value
    return values


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
    if not member.linkname or "\\" in member.linkname or "\x00" in member.linkname:
        raise ArchiveError(f"unsafe link target for {member.name!r}")
    target = PurePosixPath(member.linkname)
    if member.islnk():
        resolved = _safe_member_name(member.linkname, package_name)
    else:
        if target.is_absolute():
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
) -> tuple[set[str], dict[str, object] | None, dict[str, tarfile.TarInfo]]:
    seen: set[str] = set()
    root_entries: set[str] = set()
    manifest: dict[str, object] | None = None
    members: dict[str, tarfile.TarInfo] = {}
    for member in archive:
        path = _safe_member_name(member.name, package_name)
        canonical_name = path.as_posix()
        if canonical_name in seen:
            raise ArchiveError(f"duplicate archive member: {member.name!r}")
        seen.add(canonical_name)
        members[canonical_name] = member
        if member.mode & (stat.S_ISUID | stat.S_ISGID):
            raise ArchiveError(f"setuid/setgid member is not allowed: {member.name!r}")
        if not (member.isdir() or member.isreg() or member.issym() or member.islnk()):
            raise ArchiveError(f"special file is not allowed: {member.name!r}")
        if len(path.parts) == 1 and not member.isdir():
            raise ArchiveError("package root must be a directory")
        if len(path.parts) == 2:
            root_entry = path.parts[1]
            root_entries.add(root_entry)
            if root_entry in REQUIRED_ROOT_DIRECTORIES and not member.isdir():
                raise ArchiveError(
                    f"runtime root entry must be a directory: {member.name!r}"
                )
            if root_entry in REQUIRED_ROOT_FILES and not member.isreg():
                raise ArchiveError(
                    f"runtime root entry must be a regular file: {member.name!r}"
                )
        if member.issym() or member.islnk():
            _safe_link_target(member, path, package_name)
        if path == PurePosixPath(package_name, "owl-runtime-manifest.json"):
            if not member.isreg() or member.size > 128 * 1024:
                raise ArchiveError("runtime manifest must be a small regular file")
            stream = archive.extractfile(member)
            if stream is None:
                raise ArchiveError("runtime manifest cannot be read")
            try:
                manifest = json.loads(
                    stream.read(128 * 1024 + 1).decode("utf-8"),
                    object_pairs_hook=_reject_duplicate_manifest_keys,
                )
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ArchiveError(
                    f"runtime manifest is not valid UTF-8 JSON: {error}"
                ) from error
            if not isinstance(manifest, dict):
                raise ArchiveError("runtime manifest must be a JSON object")
    for member in members.values():
        if not member.islnk():
            continue
        target_path = _safe_member_name(member.linkname, package_name).as_posix()
        target_member = members.get(target_path)
        if target_member is None or not target_member.isreg():
            raise ArchiveError(
                f"hard link target must be an archived regular file: {member.name!r}"
            )
    return root_entries, manifest, members


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
            root_entries, manifest, members = _scan_members(archive, package_name)
    except (OSError, tarfile.TarError) as error:
        raise ArchiveError(f"cannot read archive: {error}") from error

    missing = REQUIRED_ROOT_ENTRIES - root_entries
    if missing:
        raise ArchiveError(
            "archive is missing required root entries: " + ", ".join(sorted(missing))
        )
    if manifest is None:
        raise ArchiveError("archive does not contain a runtime manifest")
    for root_file in REQUIRED_NONEMPTY_ROOT_FILES:
        member = members.get(f"{package_name}/{root_file}")
        if member is None or not member.isreg() or member.size <= 0:
            raise ArchiveError(
                f"required runtime file is missing or empty: {root_file!r}"
            )
    for executable in REQUIRED_EXECUTABLES:
        member = members.get(f"{package_name}/{executable}")
        if (
            member is None
            or not member.isreg()
            or member.size <= 0
            or not member.mode & 0o111
        ):
            raise ArchiveError(
                f"runtime executable is missing, empty, or not executable: {executable!r}"
            )
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
