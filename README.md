# manaflow-ai/chromium

Release artifacts for the cmux OWL Chromium runtime.

## Default release build

The default GitHub Actions workflow builds the pinned OWL Chromium fork:

- source repo: `https://github.com/manaflow-ai/chromium-src.git`
- source ref: `feat/owl-fresh-host`
- source commit: `7523a3a72320b403d509860f8ffaec9ac20d150e`
- default runner: `["self-hosted", "macOS", "ARM64", "chromium"]`
- default gclient cache: `/Users/ec2-user/.cache/owl-chromium-gclient`
- ninja targets: `content_shell owl_fresh_mojo_runtime`

The workflow uses `$RUNNER_TEMP/owl-chromium-<run-id>-<attempt>` for depot_tools,
Chromium source, and build output. It configures `gclient` directly against the
pinned source fork and syncs `src@<commit>`. It does not use `~/chromium`, so
separate runners can build in parallel without sharing a checkout. The default
AWS runners share only the gclient git cache.

Run it from GitHub Actions with the default inputs to produce an artifact. Set
`publish_release=true` to publish the archive and SHA-256 file as a GitHub
Release.

## Self-hosted runners

The `runner_json` workflow input controls the runner labels. The default is:

```json
["self-hosted", "macOS", "ARM64", "chromium"]
```

For a Warp managed runner, use labels such as:

```json
["warp-macos-26-arm64-6x"]
```

Parallel Chromium builds require multiple runner services or multiple machines.
One macOS runner service executes one job at a time. Running multiple runner
services on the same Mac is possible, but each service needs a separate runner
work directory and enough disk for an isolated Chromium checkout.

Self-hosted runners pass an absolute `gclient_cache_dir` input to reuse a local
git cache while still creating a fresh per-run working checkout. Leave it empty
for fully fresh release verification.

AWS runner setup must include Xcode first-launch initialization and the Metal
Toolchain component:

```bash
sudo xcodebuild -downloadComponent MetalToolchain
sudo xcodebuild -runFirstLaunch
```

## Artifact contents

The archive contains:

- `Content Shell.app`
- `Content Shell Helper.app`
- `Content Shell Helper (GPU).app`
- `Content Shell Helper (Renderer).app`
- `libowl_fresh_mojo_runtime.dylib`
- `owl-build-args.gn`
- `owl-runtime-manifest.json`

The manifest records source repo, source ref, source commit, workflow run ID,
runner, GN output directory, and ninja targets.
