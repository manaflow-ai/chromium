#!/usr/bin/env python3
"""Validate a GitHub release before a reviewed runtime is published."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from pathlib import Path


class ReleaseMetadataError(ValueError):
    """Raised when release metadata or assets do not match the reviewed build."""


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    values: dict[str, object] = {}
    for key, value in pairs:
        if key in values:
            raise ReleaseMetadataError(f"release JSON contains duplicate key: {key}")
        values[key] = value
    return values


def _require_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ReleaseMetadataError(
            f"release field {field!r} must be a non-empty string"
        )
    return value


def load_release(path: Path) -> dict[str, object]:
    try:
        raw = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
        )
    except ReleaseMetadataError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ReleaseMetadataError(f"cannot read release JSON: {error}") from error
    if not isinstance(raw, dict):
        raise ReleaseMetadataError("release JSON must be an object")
    return raw


def validate_release(
    release: object,
    *,
    expected_tag: str,
    expected_title: str,
    expected_assets: Mapping[str, str],
    require_complete: bool,
) -> None:
    if not expected_assets or len(set(expected_assets)) != len(expected_assets):
        raise ReleaseMetadataError(
            "expected release assets must be unique and non-empty"
        )
    if not isinstance(release, dict):
        raise ReleaseMetadataError("release metadata must be an object")
    if _require_string(release.get("tag_name"), "tag_name") != expected_tag:
        raise ReleaseMetadataError("release tag does not match the reviewed tag")
    if _require_string(release.get("name"), "name") != expected_title:
        raise ReleaseMetadataError("release title does not match the reviewed build")

    draft = release.get("draft")
    if not isinstance(draft, bool):
        raise ReleaseMetadataError("release field 'draft' must be a boolean")
    if release.get("prerelease") is not False:
        raise ReleaseMetadataError("prerelease releases are not allowed")

    raw_assets = release.get("assets")
    if not isinstance(raw_assets, list):
        raise ReleaseMetadataError("release assets must be a JSON array")
    assets: dict[str, dict[str, object]] = {}
    for raw_asset in raw_assets:
        if not isinstance(raw_asset, dict):
            raise ReleaseMetadataError("release asset entries must be objects")
        name = _require_string(raw_asset.get("name"), "asset.name")
        if name in assets:
            raise ReleaseMetadataError(f"release contains duplicate asset: {name}")
        assets[name] = raw_asset

    expected_names = set(expected_assets)
    unexpected = sorted(set(assets) - expected_names)
    if unexpected:
        raise ReleaseMetadataError(
            "release contains unexpected assets: " + ", ".join(unexpected)
        )
    if require_complete or not draft:
        missing = sorted(expected_names - set(assets))
        if missing:
            raise ReleaseMetadataError(
                "release is missing expected assets: " + ", ".join(missing)
            )

    for name, expected_digest in expected_assets.items():
        asset = assets.get(name)
        if asset is None:
            continue
        if asset.get("digest") != expected_digest:
            raise ReleaseMetadataError(
                f"release asset has an unexpected digest: {name}"
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-json", type=Path, required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--archive-name", required=True)
    parser.add_argument("--archive-digest", required=True)
    parser.add_argument("--checksum-name", required=True)
    parser.add_argument("--checksum-digest", required=True)
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args(argv)
    try:
        release = load_release(args.release_json)
        validate_release(
            release,
            expected_tag=args.tag,
            expected_title=args.title,
            expected_assets={
                args.archive_name: args.archive_digest,
                args.checksum_name: args.checksum_digest,
            },
            require_complete=args.require_complete,
        )
    except ReleaseMetadataError as error:
        print(f"release metadata rejected: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
