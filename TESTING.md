# Testing

Run `./scripts/test.sh` from the repository root after `./scripts/bootstrap_engine.sh`. The suite installs the engine and knowledge packages into `.venv` and runs pytest. The Phase 1 tests start LuaJIT. The Phase 3 tests import the pinned data files. They fail if the checkout or the interpreter is missing. They do not skip.

## What the suite does

| Test | What it proves |
| --- | --- |
| Pinned revision | The running process reports commit `e5917f81`, manifest `2.67.2`, and tree `3_30`. |
| Forged PlayerStat | XML Life `999999` still calculates as 60. |
| Poisoned SQLite cache | A calculations row overwritten with Life 1 is not what `calculate` returns. |
| Equipment | Glorious Plate `+100 to maximum Life` moves Life from 60 to 160. Compare reports delta 100 and `source: pob-engine`. |
| Passive | The engine allocates node 15073 and Life becomes 256. The node id is in the exported spec. |
| Round trip | Importing that export calculates 256 again. |
| Rollback | An unknown base and an unknown node id leave the import revision's Life at 60. |
| FTS | A revision name is findable through SQLite FTS5. |
| HTTP | `POST /api/builds` and the equipment route return the same Life values. |
| Compare guard | A stat table whose `source` is not `pob-engine` is rejected without launching a character. |
| Library store | A draft row does not replace the saved revision, and discarding a draft leaves the stored XML in place. |
| Safe edit | Import, copy, equip, and allocate leave the imported XML byte-for-byte unchanged. Save writes a new row. The original still calculates as Life 60. |
| Inspector | The stored revision and the edited revision each return `source: pob-engine`, with class and equipped items from the live build. |
| Export | The saved revision's export parses as `<PathOfBuilding>` and reimports at the same engine Life as the save. |
| PoB saves | A decoy XML in the headless user Builds directory is not a library entry. The checkout has no local modifications. |
| HTTP library | Library, history, save, discard refusal, inspect, compare, and export go through the API. |
| Knowledge pin | The importer refuses a checkout whose commit is not `engine/pin.json`. |
| Knowledge counts | The import has the bases, uniques, mods, gems, nodes, and edges of this pin. |
| Glorious Plate | Base armour and requirements, and Kaom's Heart raw text, match the data files. |
| Gems | Kinetic Blast and Inspiration keep their granted effects, tags, and level rows. |
| Modifier text | The Watcher's Eye Clarity mana-cost line is present, with its source path. |
| Passive graph | The Life node is reachable from the Scion start. Dropping the bridge, a lone node, an unknown id, and a pair that does not touch the start are rejected. |
| Point budget | 124 connected regular nodes are rejected. 123 are accepted. Nine Juggernaut points are rejected. Witch cannot take Juggernaut. |
| Checkout untouched | After the import, `git status` in the PoB checkout is clean, and `CalcOffence.lua` still rounds upfront costs after efficiency. |

The Life numbers and the knowledge counts are locks for this pin. Neither service contains them as a substitute for the checkout. If a future PoB commit changes the result, the test fails and the pin has to move with a new measurement.

Phase 3 tests build the SQLite file from the live checkout in a temporary directory. They do not use a hand-written item, gem, or node.

## What was not run

- Desktop Path of Building on Windows, so there is no GUI-versus-headless diff.
- Share codes, pobb.in, and pathofexile.com character import.
- Support-gem compatibility, aura reservation, attribute-requirement failures, cluster jewels, and timeless jewels.
- Optimiser cancel, budget enforcement, and tool-argument schemas for the later agent. Those tests belong to the phase that adds the feature.

`engine/adapter.lua` has no self-test switch. The pytest process is the check.

## Fixture

`fixtures/builds/scion-baseline.xml` is the XML `SaveDB` produced for a fresh level 1 Scion on this pin. Do not hand-edit the stat cache and treat the file as a new oracle. If you regenerate it, do it by exporting from the engine and say so in the commit.
