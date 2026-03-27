# manaflow-ai/chromium

Chromium content shell build for [cmux](https://github.com/manaflow-ai/cmux).

## For cmux developers

Download the prebuilt framework from [Releases](https://github.com/manaflow-ai/chromium/releases). No need to build Chromium locally.

## Building from source

Requires ~30GB disk and ~1 hour build time.

```bash
git clone https://chromium.googlesource.com/chromium/tools/depot_tools.git ~/depot_tools
export PATH="$HOME/depot_tools:$PATH"

mkdir ~/chromium && cd ~/chromium
fetch --no-history chromium

cp -r cmux-bridge/* ~/chromium/src/cmux/

cd ~/chromium/src
gn gen out/Release --args='target_cpu="arm64" is_debug=false is_component_build=false symbol_level=0 enable_nacl=false use_remoteexec=false'
autoninja -C out/Release content_shell
```
