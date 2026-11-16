# Game data

Character calculations still use the data inside the pinned Path of Building checkout. Phase 3 also copies that checkout's item bases, unique text, modifier lines, skill gems, and passive tree into a generated SQLite file so other code can query them without starting a second calculation process. The file is `data/knowledge.sqlite` (override `POB_KNOWLEDGE`). It is not committed, and it is not a substitute for `CalcsTab:BuildOutput`.

## Version that actually loads

| Field | Value | Where it comes from |
| --- | --- | --- |
| PoB commit | `e5917f81fd64c10d9bc816c410da395ed18e57ba` | `git rev-parse` of the checkout |
| Commit time | 2026-11-15 16:41:48 -0600 | `Support Polaric Devastation (#10415)` |
| Manifest `Version number` | `2.67.2` | `manifest.xml` on that commit |
| Latest skill tree | `3_30` (displayed as 3.30) | `latestTreeVersion` in `src/GameVersions.lua`, read back from the running process |
| Latest release tag | `v2.67.2`, published 2026-08-07 | GitHub Releases. It is behind `dev`. |

The manifest number was not bumped when the 3.30 tree landed. Reporting "PoB 2.67.2" as the game version would be wrong. The engine service returns both the manifest number and the tree version, and the pin file records that they differ.

`GameVersions.lua` on this commit lists trees through `3_30` and `3_30_ruthless`. A new build from `HeadlessWrapper` comes up as a level 1 Scion on tree `3_30`.

## What the checkout contains

- `src/Data/` — bases, modifiers, skills, uniques, stat descriptions.
- `src/TreeData/3_30/tree.lua` — the passive graph the allocator walks.
- `runtime/lua/` — XML and JSON libraries. Copies used at runtime are vendored in this repo so a test does not depend on a second download. See `engine/vendor/README.md`.

Tree images and `Data/TimelessJewelData` are not required for the Phase 1 Scion fixture. The headless image stub does not read PNG files. Timeless jewels are out of scope until a fixture actually sockets one; the adapter still installs a real zlib `Inflate` so a later jewel file is not replaced with an empty buffer.

## Measured baseline

On 15 Nov 2026 the pinned engine reported:

- Level 1 Scion, no items, class start only: Life **60**
- Same character with a rare Glorious Plate that has `+100 to maximum Life`: Life **160**
- After allocating the connected "Life" notable (node **15073**, `5% increased maximum Life`) and the nodes on its path, with auto-level enabled: Life **256**

Those figures are regression locks in `services/engine/tests/test_phase1.py` and again in the Phase 5 search. They are not constants the service returns instead of calculating.

## Knowledge import

`services/knowledge` reads the checkout with LuaJIT. The reader loads the same data files `Modules/Data.lua` lists, plus `TreeData/<latestTreeVersion>/tree.lua`. It does not load `HeadlessWrapper.lua`, and it does not write into `.pob/`.

| Data | Source files |
| --- | --- |
| Item bases | `src/Data/Bases/*.lua` |
| Unique text | `src/Data/Uniques/*.lua` and `src/Data/Uniques/Special/race.lua` |
| Modifier lines | The modifier tables `Modules/Data.lua` loads, including `src/Data/Uniques/Special/WatchersEye.lua` |
| Skill gems | `src/Data/Gems.lua` and the skill files it grants |
| Passive graph | `src/TreeData/3_30/tree.lua` on this pin |

`Data/Uniques/Special/Generated.lua` and `New.lua` are not executed. They synthesize text and need the full data environment. Watcher's Eye modifiers come from the source table instead.

Each import row stores:

- `source`: `PathOfBuildingCommunity/PathOfBuilding`
- `sourceCommit` and the GitHub tree URL for that commit
- `gameVersion`: the tree display (`3.30`), not the manifest
- `treeVersion`: `3_30`
- `manifestVersion`: `2.67.2` on this pin
- `retrievalDate`: the UTC date of the import

The passive graph keeps a node when PoB would: it has a group, the group is not a proxy, the node is not a proxy, and it is not an expansion-jewel parent. Edges come from each node's `in` and `out` lists. Class starts and the selected ascendancy start are allocated for free. Mastery nodes do not connect other nodes. Ascendancy nodes are not a path through the main tree. An allocation that cannot reach the matching start is rejected. The point cap is `points.totalPoints` (123) and `points.ascendancyPoints` (8), plus any passive points the allocated nodes themselves grant.

`./.venv/bin/pob-knowledge import` writes the database. `show` prints one base, unique, or gem.

`services/discovery` reads this database. It pairs lines that already share a phrase and reports conflicts that the text or a modifier `group` already states. It does not add rows and it does not invent a modifier.

## Patches

Patch-note ingestion is not implemented. A calculation and an imported record are true for this PoB commit and this tree only. If `dev` moves, update `engine/pin.json` and re-run the tests. Do not assume the August 2.67.2 release contains the 3.30 tree.
