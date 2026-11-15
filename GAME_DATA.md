# Game data

Phase 1 uses the game data that ships inside the pinned Path of Building checkout. This repo does not carry its own item or passive database.

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

Those figures are regression locks in `services/engine/tests/test_phase1.py`. They are not constants the service returns instead of calculating.

## Patches

Selecting a league and invalidating stale notes is Phase 3. Until then, a calculation is true for this PoB commit and this tree only. If `dev` moves, update `engine/pin.json` and re-run the tests. Do not assume the August 2.67.2 release contains the 3.30 tree.
