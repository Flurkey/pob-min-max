# Path of Building integration

Phase 1 drives an unmodified PathOfBuildingCommunity checkout. The decision follows from running the candidates, not from their READMEs alone.

## What was reviewed

### PathOfBuildingCommunity/PathOfBuilding

- Default branch `dev`, commit `e5917f81fd64c10d9bc816c410da395ed18e57ba`, 15 Nov 2026.
- Latest GitHub release is `v2.67.2` (7 Aug 2026). That release is older than the 3.30 tree on `dev`.
- `src/HeadlessWrapper.lua` boots the program without the GUI, exposes `loadBuildFromXML` / `newBuild`, and leaves the build in the global `build`.
- Calculations are `build.calcsTab:BuildOutput()`, then `build.calcsTab.mainOutput`.
- Equipment goes through `ItemsTab:AddItem` and `ItemSlot:SetSelItemId`.
- Passives go through `PassiveSpec:AllocNode`, which allocates the path from the class start.
- `Build:SaveDB` returns XML. `<PlayerStat>` is written from `mainOutput` during save (`Modules/Build.lua`). A search of `src/` shows no reader of those tags. They are a cache.
- `new()` on this commit rejects constructor arguments. Items are `new("Item"):Item(raw)`.
- Launcher files start with `#@`. LuaJIT 2.1.1794386141 reports `unexpected symbol near '#'` for that line.
- `Modules/Common.lua` uses the global `bit` library and `require("lua-utf8")`. `xml` and `dkjson` are not in `src/`; they are in `runtime/lua/`.

This is the integration we run.

### ianderse/pob-mcp

- Pushed 15 Nov 2026. GPL-3.0. Actively maintained.
- README targets PoE 3.29 data and an unmodified PoB tree plus LuaJIT. Its `lua/pob_compat.lua` also notes that current dev (3.30) changed `new()`.
- The useful idea is real: stdio JSON, stock `HeadlessWrapper.lua`, a `#@` load shim, and a zlib `Inflate`. We confirmed that shape boots.
- We did not vendor the server. It is a large MCP product (trade, poe.ninja, optimisation) under GPL-3.0, and copying the adapter would put that license on this repo. The Lua in `engine/adapter.lua` is written for this project.

### coldino/pob_wrapper

- Last push 16 Aug 2022. No release since.
- Windows-oriented wrapper around an installed PoB. It can load a build and test a mod line.
- It does not speak the current `new("Item"):Item(raw)` constructor, the 3.30 tree, or a Linux LuaJIT host. Not used.

### Balenciaga69/pob-headless-runtime

- Version 0.2.1, 10 Apr 2026. MIT. Last push 24 Apr 2026.
- README: validated on Windows with LuaJIT against Path of Building **2.63.0**.
- The stable contract (load, save, stats, equip, config) is a good shape for a later API.
- It is not current for this commit. PoB 2.63 is several releases behind 2.67.2, and `dev` has moved on to tree 3.30 and a different `new()`. Reusing that tree as a dependency would mean maintaining a port we have not seen pass on 3.30. Not used.

## How this repo runs PoB

1. `scripts/bootstrap_engine.sh` builds LuaJIT `63c8f1a9` (compound assignment works; `#@` does not) and `lua-utf8` from starwing/luautf8 `a845c5b7`.
2. It checks out PoB `e5917f81` into `.pob/PathOfBuilding`.
3. `services/engine` starts `luajit engine/adapter.lua` with `cwd` at `src/`.
4. The adapter loads `HeadlessWrapper.lua`, then serves `import_xml`, `calculate`, `equip_item`, `allocate_node`, and `export_xml`.

`allocate_node` without an id picks the connected non-ascendancy node whose stat text grants player maximum life, whose path from the class start is shortest, and whose id is lowest on a tie. `pairs()` order is not stable, so the id tie-break is required. On this tree that is node 15073, "Life". The test locks the id so a silent change of target is visible.

## Compatibility check that was actually run

Linux, LuaJIT 2.1.1794386141, PoB `e5917f81`, tree 3.30:

- Import of an engine-exported level 1 Scion, after the Life cache was rewritten to `999999`, calculated Life **60**.
- A rare Glorious Plate with `+100 to maximum Life` calculated Life **160**.
- Allocating node 15073 and its path calculated Life **256**.
- Exporting that build and importing it again calculated Life **256**.
- An unknown base did not change the stored revision. A missing node id did not either.
- Startup left no `src/Builds` directory behind. Dev-mode autosave is disabled and the user path is a temp directory.

Desktop Path of Building was not run. There is no Windows GUI or Wine in the environment that produced this result, so there is no headless-versus-desktop diff yet. The round trip above is headless versus a second headless import of the file the first process saved.

## Phase 2

The library is this repo's SQLite file. Imports, drafts, and saves are rows in that file. The adapter still sets the headless user path to a temp directory and turns off dev autosave, so a calculation does not read or write a desktop Path of Building Builds folder.

The pin is unchanged. `CalcOffence.lua` on `e5917f81` still rounds an upfront non-percent cost to a whole number after cost efficiency and before the flat total. That round is not removed to match the 7 Aug 2026 desktop build.

## Phase 3

The knowledge importer reads `src/Data` and `src/TreeData` from the same checkout with LuaJIT. It does not launch `HeadlessWrapper.lua` and it does not modify the checkout. Provenance on each import is this commit, tree `3_30`, and manifest `2.67.2`. The `CalcOffence.lua` post-efficiency round is unchanged.

## Rejected shortcuts

- Treating `<PlayerStat>` as live.
- Parsing items in Python and adding a flat life number.
- Pinning the August 2.67.2 release and calling it the current patch.
- Copying pob-mcp's GPL adapter or dropping pob-headless-runtime in unchanged.
