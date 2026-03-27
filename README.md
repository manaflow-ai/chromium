# manaflow-ai/chromium

Chromium content shell build for [cmux](https://github.com/manaflow-ai/cmux) browser engine.

## What is this?

cmux embeds a Chromium browser engine for web browsing alongside terminal sessions. This repo builds Chromium's `content_shell` as a framework that cmux loads at runtime.

## Architecture

Based on [OpenAI Atlas/OWL](https://openai.com/index/building-chatgpt-atlas/): raw Chromium content API with native NSView embedding. No CEF. Native input handling, context menus, IME, right-click all work out of the box.

## For cmux developers

Download the prebuilt framework from [Releases](https://github.com/manaflow-ai/chromium/releases). No need to build Chromium locally.

```bash
# Automatic download during cmux setup
./scripts/setup.sh
```

## Building from source

Requires ~30GB disk and ~1 hour build time.

```bash
# Install depot_tools
git clone https://chromium.googlesource.com/chromium/tools/depot_tools.git ~/depot_tools
export PATH="$HOME/depot_tools:$PATH"

# Fetch Chromium
mkdir ~/chromium && cd ~/chromium
fetch --no-history chromium

# Copy our bridge into the Chromium tree
cp -r cmux-bridge/* ~/chromium/src/cmux/

# Build
cd ~/chromium/src
gn gen out/Release --args='target_cpu="arm64" is_debug=false is_component_build=false symbol_level=0 enable_nacl=false use_remoteexec=false'
autoninja -C out/Release content_shell cmux_bridge
```

## Files

- `cmux-bridge/cmux_bridge.mm` - C bridge built against Chromium's content API
- `cmux-bridge/BUILD.gn` - GN build target
- `cmux-bridge/chromium_bridge.h` - C header for Swift interop
- `.github/workflows/build-chromium.yml` - CI build on Warpbuild
