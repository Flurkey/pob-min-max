#!/usr/bin/env bash
# Build LuaJIT and lua-utf8, and check out the pinned Path of Building source.
# Runtime Lua libraries are already vendored under engine/vendor/runtime.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PIN="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["commit"])' "$ROOT/engine/pin.json")"
LUAJIT_PIN="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["luajit"]["commit"])' "$ROOT/engine/pin.json")"
UTF8_PIN="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["luaUtf8"]["commit"])' "$ROOT/engine/pin.json")"
DEST="$ROOT/.pob"

mkdir -p "$DEST/bin" "$DEST/utf8"

if [[ ! -x "$DEST/LuaJIT/src/luajit" ]]; then
  rm -rf "$DEST/LuaJIT"
  git clone --depth 1 https://github.com/LuaJIT/LuaJIT.git "$DEST/LuaJIT"
  git -C "$DEST/LuaJIT" fetch --depth 1 origin "$LUAJIT_PIN"
  git -C "$DEST/LuaJIT" checkout --detach "$LUAJIT_PIN"
  make -C "$DEST/LuaJIT" -j"$(nproc)"
fi
ln -sfn "$DEST/LuaJIT/src/luajit" "$DEST/bin/luajit"

if [[ ! -f "$DEST/utf8/lua-utf8.so" ]]; then
  rm -rf "$DEST/luautf8"
  git clone --depth 1 https://github.com/starwing/luautf8.git "$DEST/luautf8"
  git -C "$DEST/luautf8" fetch --depth 1 origin "$UTF8_PIN"
  git -C "$DEST/luautf8" checkout --detach "$UTF8_PIN"
  gcc -shared -fPIC -O2 -I"$DEST/LuaJIT/src" -o "$DEST/utf8/lua-utf8.so" "$DEST/luautf8/lutf8lib.c"
fi

if [[ ! -f "$DEST/PathOfBuilding/src/HeadlessWrapper.lua" ]]; then
  rm -rf "$DEST/PathOfBuilding"
  git clone --filter=blob:none --sparse https://github.com/PathOfBuildingCommunity/PathOfBuilding.git "$DEST/PathOfBuilding"
  git -C "$DEST/PathOfBuilding" fetch --depth 1 origin "$PIN"
  git -C "$DEST/PathOfBuilding" checkout --detach "$PIN"
  git -C "$DEST/PathOfBuilding" sparse-checkout set --skip-checks src manifest.xml runtime/lua
fi

"$DEST/bin/luajit" -v
"$DEST/bin/luajit" -e 'local a=1; a+=2; if a ~= 3 then error("compound assignment missing") end'
git -C "$DEST/PathOfBuilding" rev-parse HEAD
test "$(git -C "$DEST/PathOfBuilding" rev-parse HEAD)" = "$PIN"
echo "Engine checkout ready at $DEST"
