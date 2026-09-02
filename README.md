# manaflow-ai/chromium

Release artifacts for the cmux OWL Chromium runtime.

## Reviewed build policy

`.github/chromium-release-policy.json` is the only source of build inputs. It
currently allowlists `manaflow-ai/chromium-src.git` at
`feat/owl-fresh-host@7523a3a72320b403d509860f8ffaec9ac20d150e`, and pins
`depot_tools` to commit `0833022c601133d858cbee4faf6bc5ce556afb14`.

The workflow accepts one boolean dispatch input, `publish_release`. It must be
dispatched from `main` in this repository. Source URL, source ref, source
commit, runner labels, cache path, and release tag are not user inputs. The
runner labels are fixed to `["self-hosted", "macOS", "ARM64", "chromium"]`.
The runner name is also allowlisted as `aws-m1-ultra-chromium-1`; a renamed or
unexpected runner fails before source synchronization.
The policy validator fails closed if any value, including a future policy edit,
does not match its allowlist.

Builds use a randomly created mode-700 directory below `$RUNNER_TEMP`, an
ephemeral `HOME`, and an ephemeral gclient cache. The checked-out artifact
repository does not persist Git credentials. The Chromium source is resolved
through an exact branch ref, checked against the approved full commit, and
checked for a clean tree after `gclient sync`.

The build job has `contents: read`. Publication is a separate Ubuntu job with
`contents: write`, an `actions: read` artifact token, and the `release`
environment. Configure that environment with required reviews from
`@austinywang` and `@azooz2003-bit`,
disable administrator bypass, and enable GitHub immutable releases before
setting `publish_release=true`. Protect `main` with at least two approving
reviews, require code-owner review, and prevent administrator bypass. The
publisher creates only
`owl-chromium-<full-source-sha>`, refuses a tag that points at another commit,
and refuses conflicting or missing assets on an already published release.
An interrupted draft release can be resumed only when every existing asset has
the expected digest.

The archive validator rejects absolute or traversal paths, links that escape
the package root, duplicate entries, special files, setuid/setgid entries, and
manifests that do not match the reviewed source and targets.

## Self-hosted runner boundary

The `chromium` runner label must identify a dedicated, disposable macOS runner
with no user credentials, deployment keys, or unrelated repositories. Chromium
`DEPS` hooks execute during `gclient sync`, so the source commit allowlist and
runner isolation are both required. Do not add a persistent cache input or
reuse a runner for unrelated jobs.

The runner must have Xcode first-launch initialization and the Metal Toolchain:

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

The manifest records source repository, source ref and commit, workflow run,
runner metadata, GN output directory, and ninja targets. The sidecar checksum
always names the archive by basename, so it is portable between runners.

## Tests

Run the policy and archive tests with:

```bash
python3 -m unittest discover -s tests -v
```

`validate-release-workflow.yml` runs these tests on pull requests and on
changes to `main`.
