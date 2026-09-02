#!/usr/bin/env python3
"""Validate the reviewed inputs used by the OWL Chromium release workflow."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import TextIO

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
REQUIRED_POLICY_KEYS = {
    "source_repository",
    "source_ref",
    "approved_source_commits",
    "runner_labels",
    "runner_names",
    "depot_tools_repository",
    "depot_tools_commit",
    "release_tag_prefix",
}


class PolicyError(ValueError):
    """Raised when the checked-in release policy is malformed or unsafe."""


def _require_cli_value(value: str | None, name: str) -> str:
    if value is None:
        raise PolicyError(f"workflow invocation must provide: {name}")
    return value


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    values: dict[str, object] = {}
    for key, value in pairs:
        if key in values:
            raise PolicyError(f"policy contains duplicate key: {key}")
        values[key] = value
    return values


def _require_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise PolicyError(f"{field} must be a non-empty string")
    if "\n" in value or "\r" in value:
        raise PolicyError(f"{field} must not contain a newline")
    return value


def load_policy(path: Path) -> dict[str, object]:
    try:
        raw = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_keys
        )
    except PolicyError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PolicyError(f"cannot read policy: {error}") from error
    if not isinstance(raw, dict):
        raise PolicyError("policy must be a JSON object")
    if set(raw) != REQUIRED_POLICY_KEYS:
        missing = sorted(REQUIRED_POLICY_KEYS - set(raw))
        extra = sorted(set(raw) - REQUIRED_POLICY_KEYS)
        details = []
        if missing:
            details.append(f"missing {', '.join(missing)}")
        if extra:
            details.append(f"unknown {', '.join(extra)}")
        raise PolicyError("invalid policy keys: " + "; ".join(details))

    source_repository = _require_string(raw["source_repository"], "source_repository")
    if source_repository != "https://github.com/manaflow-ai/chromium-src.git":
        raise PolicyError("source_repository must be the approved chromium-src URL")
    source_ref = _require_string(raw["source_ref"], "source_ref")
    if not re.fullmatch(r"[A-Za-z0-9._/-]+", source_ref) or source_ref.startswith("/"):
        raise PolicyError("source_ref contains unsupported characters")

    commits = raw["approved_source_commits"]
    if (
        not isinstance(commits, list)
        or not commits
        or any(not isinstance(item, str) for item in commits)
    ):
        raise PolicyError("approved_source_commits must be a non-empty list of strings")
    if len(set(commits)) != len(commits) or any(
        not SHA_RE.fullmatch(item) for item in commits
    ):
        raise PolicyError(
            "approved_source_commits must contain unique lowercase full SHAs"
        )

    labels = raw["runner_labels"]
    if (
        not isinstance(labels, list)
        or not labels
        or any(not isinstance(item, str) for item in labels)
    ):
        raise PolicyError("runner_labels must be a non-empty list of strings")
    if len(set(labels)) != len(labels):
        raise PolicyError("runner_labels must not contain duplicates")
    if labels != ["self-hosted", "macOS", "ARM64", "chromium"]:
        raise PolicyError("runner_labels must identify the isolated Chromium runner")
    runner_names = raw["runner_names"]
    if (
        not isinstance(runner_names, list)
        or not runner_names
        or any(not isinstance(item, str) for item in runner_names)
    ):
        raise PolicyError("runner_names must be a non-empty list of strings")
    if len(set(runner_names)) != len(runner_names) or any(
        not item.strip() for item in runner_names
    ):
        raise PolicyError("runner_names must contain unique non-empty names")
    if runner_names != ["aws-m1-ultra-chromium-1"]:
        raise PolicyError("runner_names must identify the isolated Chromium runner")

    depot_repository = _require_string(
        raw["depot_tools_repository"], "depot_tools_repository"
    )
    if (
        depot_repository
        != "https://chromium.googlesource.com/chromium/tools/depot_tools.git"
    ):
        raise PolicyError("depot_tools_repository must be the approved upstream URL")
    depot_commit = _require_string(raw["depot_tools_commit"], "depot_tools_commit")
    if not SHA_RE.fullmatch(depot_commit):
        raise PolicyError("depot_tools_commit must be a lowercase full SHA")

    tag_prefix = _require_string(raw["release_tag_prefix"], "release_tag_prefix")
    if tag_prefix != "owl-chromium-":
        raise PolicyError("release_tag_prefix must be owl-chromium-")

    return raw


def validate_inputs(
    policy: dict[str, object],
    *,
    source_repository: str,
    source_ref: str,
    source_commit: str,
    runner_json: str,
    runner_name: str,
    release_tag: str,
) -> dict[str, str]:
    """Return normalized values only when every release input is allowlisted."""

    expected_repository = str(policy["source_repository"])
    expected_ref = str(policy["source_ref"])
    approved_commits = policy["approved_source_commits"]
    expected_labels = policy["runner_labels"]
    expected_runner_names = policy["runner_names"]
    assert isinstance(approved_commits, list)
    assert isinstance(expected_labels, list)
    assert isinstance(expected_runner_names, list)

    if source_repository != expected_repository:
        raise PolicyError("source repository is not allowlisted")
    if source_ref != expected_ref:
        raise PolicyError("source ref is not allowlisted")
    if source_commit not in approved_commits:
        raise PolicyError("source commit is not in the reviewed allowlist")
    if not SHA_RE.fullmatch(source_commit):
        raise PolicyError("source commit must be a lowercase full SHA")

    try:
        labels = json.loads(runner_json)
    except json.JSONDecodeError as error:
        raise PolicyError(f"runner_json is not valid JSON: {error}") from error
    if labels != expected_labels:
        raise PolicyError("runner labels are not the isolated Chromium labels")
    if runner_name not in expected_runner_names:
        raise PolicyError("runner name is not allowlisted")

    expected_tag = f"{policy['release_tag_prefix']}{source_commit}"
    if release_tag != expected_tag:
        raise PolicyError("release tag must bind exactly to the approved source commit")
    if not re.fullmatch(r"owl-chromium-[0-9a-f]{40}", release_tag):
        raise PolicyError("release tag has an invalid immutable format")

    return {
        "source_repository": expected_repository,
        "source_ref": expected_ref,
        "source_commit": source_commit,
        "depot_tools_repository": str(policy["depot_tools_repository"]),
        "depot_tools_commit": str(policy["depot_tools_commit"]),
        "short_sha": source_commit[:12],
        "release_tag": release_tag,
    }


def write_outputs(values: dict[str, str], output: TextIO) -> None:
    for key, value in values.items():
        if "\n" in value or "\r" in value:
            raise PolicyError(f"output {key} contains a newline")
        print(f"{key}={value}", file=output)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--source-repository")
    parser.add_argument("--source-ref")
    parser.add_argument("--source-commit")
    parser.add_argument("--runner-json")
    parser.add_argument("--runner-name")
    parser.add_argument("--release-tag")
    parser.add_argument("--output", type=argparse.FileType("w"), default=sys.stdout)
    args = parser.parse_args(argv)
    try:
        policy = load_policy(args.policy)
        approved_commits = policy["approved_source_commits"]
        if not isinstance(approved_commits, list) or len(approved_commits) != 1:
            raise PolicyError(
                "workflow invocation must select exactly one approved source commit"
            )
        source_repository = _require_cli_value(
            args.source_repository, "source_repository"
        )
        source_ref = _require_cli_value(args.source_ref, "source_ref")
        source_commit = _require_cli_value(args.source_commit, "source_commit")
        runner_json = _require_cli_value(args.runner_json, "runner_json")
        runner_name = _require_cli_value(args.runner_name, "runner_name")
        release_tag = _require_cli_value(args.release_tag, "release_tag")
        values = validate_inputs(
            policy,
            source_repository=source_repository,
            source_ref=source_ref,
            source_commit=source_commit,
            runner_json=runner_json,
            runner_name=runner_name,
            release_tag=release_tag,
        )
        write_outputs(values, args.output)
    except PolicyError as error:
        print(f"release policy rejected: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
