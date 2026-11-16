# Testing

Run `./scripts/test.sh` from the repository root after `./scripts/bootstrap_engine.sh`. The suite installs the engine package into `.venv` and runs pytest. The Phase 1 tests start LuaJIT. They fail if the checkout or the interpreter is missing. They do not skip.

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

The Life numbers are locks for this pin. The service does not contain them. If a future PoB commit changes the result, the test fails and the pin has to move with a new measurement.

## What was not run

- Desktop Path of Building on Windows, so there is no GUI-versus-headless diff.
- Share codes, pobb.in, and pathofexile.com character import.
- Support-gem compatibility, aura reservation, attribute-requirement failures, cluster jewels, and timeless jewels.
- Optimiser cancel, budget enforcement, and tool-argument schemas for the later agent. Those tests belong to the phase that adds the feature.

`engine/adapter.lua` has no self-test switch. The pytest process is the check.

## Fixture

`fixtures/builds/scion-baseline.xml` is the XML `SaveDB` produced for a fresh level 1 Scion on this pin. Do not hand-edit the stat cache and treat the file as a new oracle. If you regenerate it, do it by exporting from the engine and say so in the commit.
