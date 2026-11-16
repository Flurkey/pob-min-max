# Vendored Path of Building runtime libraries

These Lua files are copied from `PathOfBuildingCommunity/PathOfBuilding` commit `e5917f81fd64c10d9bc816c410da395ed18e57ba`, path `runtime/lua/`. They are not part of the `src/` tree. Headless startup `require`s them (`xml`, `dkjson`, `base64`, `sha1`).

The dev `manifest.xml` still lists older SHA-1 values from the 2.67.2 runtime catalogue. The copies here are the blobs in the pinned commit, which are the ones the dev source loads. Do not replace them with the manifest hashes.

`lua-profiler.lua` is optional. PoB prints "Unable to Load Profiler" without it and continues. It is included so the runtime directory matches upstream.

Path of Building is MIT licensed. `dkjson.lua` keeps its own license header.
