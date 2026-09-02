from __future__ import annotations

import json
import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from scripts import chromium_release_policy as policy

SCRIPT_ROOT = Path(__file__).resolve().parents[1] / "scripts"
POLICY_PATH = SCRIPT_ROOT.parent / ".github" / "chromium-release-policy.json"
SOURCE_REPOSITORY = "https://github.com/manaflow-ai/chromium-src.git"
SOURCE_REF = "feat/owl-fresh-host"
SOURCE_COMMIT = "7523a3a72320b403d509860f8ffaec9ac20d150e"
RUNNER_JSON = '["self-hosted", "macOS", "ARM64", "chromium"]'
RUNNER_NAME = "aws-m1-ultra-chromium-1"
RELEASE_TAG = f"owl-chromium-{SOURCE_COMMIT}"


class ChromiumReleasePolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.loaded = policy.load_policy(POLICY_PATH)

    def test_reviewed_inputs_are_normalized(self) -> None:
        values = policy.validate_inputs(
            self.loaded,
            source_repository=SOURCE_REPOSITORY,
            source_ref=SOURCE_REF,
            source_commit=SOURCE_COMMIT,
            runner_json=RUNNER_JSON,
            runner_name=RUNNER_NAME,
            release_tag=RELEASE_TAG,
        )
        self.assertEqual(values["short_sha"], SOURCE_COMMIT[:12])
        self.assertEqual(values["release_tag"], RELEASE_TAG)
        self.assertEqual(
            values["depot_tools_commit"], "0833022c601133d858cbee4faf6bc5ce556afb14"
        )

    def test_rejects_unapproved_repository(self) -> None:
        with self.assertRaises(policy.PolicyError):
            self._validate(
                source_repository="https://github.com/attacker/chromium-src.git"
            )

    def test_rejects_unapproved_ref(self) -> None:
        with self.assertRaises(policy.PolicyError):
            self._validate(source_ref="refs/pull/1/head")

    def test_rejects_unapproved_commit(self) -> None:
        with self.assertRaises(policy.PolicyError):
            self._validate(source_commit="0" * 40)

    def test_rejects_arbitrary_runner_labels(self) -> None:
        with self.assertRaises(policy.PolicyError):
            self._validate(runner_json='["self-hosted", "production"]')

    def test_rejects_unallowlisted_runner_name(self) -> None:
        with self.assertRaises(policy.PolicyError):
            self._validate(runner_name="untrusted-runner")

    def test_rejects_release_tag_not_bound_to_commit(self) -> None:
        with self.assertRaises(policy.PolicyError):
            self._validate(release_tag="owl-chromium-" + "a" * 40)

    def test_rejects_duplicate_or_unknown_policy_keys(self) -> None:
        raw = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        raw["unexpected"] = True
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "policy.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(policy.PolicyError):
                policy.load_policy(path)

    def test_rejects_duplicate_policy_keys(self) -> None:
        text = POLICY_PATH.read_text(encoding="utf-8")
        duplicate = text.replace(
            '"source_repository": "https://github.com/manaflow-ai/chromium-src.git",',
            '"source_repository": "https://github.com/manaflow-ai/chromium-src.git",\n'
            '  "source_repository": "https://github.com/manaflow-ai/chromium-src.git",',
            1,
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "policy.json"
            path.write_text(duplicate, encoding="utf-8")
            with self.assertRaises(policy.PolicyError):
                policy.load_policy(path)

    def test_cli_requires_explicit_release_identity(self) -> None:
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            result = policy.main(
                [
                    "--policy",
                    str(POLICY_PATH),
                    "--runner-json",
                    RUNNER_JSON,
                    "--runner-name",
                    RUNNER_NAME,
                ]
            )
        self.assertEqual(result, 2)
        self.assertIn("source_repository", stderr.getvalue())

    def _validate(self, **overrides: str) -> None:
        values = {
            "source_repository": SOURCE_REPOSITORY,
            "source_ref": SOURCE_REF,
            "source_commit": SOURCE_COMMIT,
            "runner_json": RUNNER_JSON,
            "runner_name": RUNNER_NAME,
            "release_tag": RELEASE_TAG,
        }
        values.update(overrides)
        policy.validate_inputs(self.loaded, **values)


if __name__ == "__main__":
    unittest.main()
