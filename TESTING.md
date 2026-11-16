# Testing

Run `./scripts/test.sh` from the repository root after `./scripts/bootstrap_engine.sh`. The suite installs the engine, knowledge, agent, optimisation, and discovery packages into `.venv` and runs pytest. The Phase 1 tests start LuaJIT. The Phase 3 tests import the pinned data files. The Phase 4 tests do both, and they talk to a fake model provider. The Phase 5 tests search the Scion fixture with the real engine. The Phase 6 tests search that same import for chains and conflicts. They fail if the checkout or the interpreter is missing. They do not skip.

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
| Provider boundary | OpenAI, OpenAI-compatible, Anthropic, Gemini, and Ollama requests can be described. `complete` without a transport raises, and the agent package has no HTTP client. |
| Invalid tool arguments | A blank item, a string node id, an unknown tool, a disconnected node, a 124-point set, and an unknown item base leave the import revision's XML and Life where they were. |
| Fake provider | The script claims the forged PlayerStat Life. `import_build`, `get_build_state`, and `calculate_build` return the engine's Life. Equip and allocate run on copies and return the engine's later Life values. Compare reports those engine numbers. |
| Imported catalogue | Unique text, the Kinetic Blast gem, the Life node, and the path to it match the knowledge database and the checkout. The provider arguments do not contain that text. |
| Export copy | The edited copy's XML reimports at the same engine Life. The original import XML is still the forged file. |
| Build hash | A canonical hash ignores `<PlayerStat>` and changes when the tree changes. The configuration profile is a separate cache field. |
| Candidate order | Passive candidates from the imported tree are nearest-first, then lowest node id. Unique candidates keep the imported raw text. |
| Search | On the Scion fixture, the search's engine results include Life 60, the Glorious Plate at 160, and the plate plus the Life node at 256. The import XML is unchanged. |
| Rejection | A disconnected node set, a 124-point set, and an unknown item base are rejected. A one-point search budget rejects the Life path. |
| Cache | A second identical plate trial is served from the cache and matches the engine stats of the first trial. Calculating the unchanged import hits the same cache. |
| Limits | `max_iterations` of 1 stops after the plate. Cancel before the first candidate, and cancel between candidates, both stop without editing the import. |
| Impossible objective | A Life minimum of 1000000 is reported as impossible. The plate trial still shows the engine's Life. |
| Chains | Every chain step is an imported unique or modifier line. The shared phrase is in both excerpts. Grant, also-apply, for-every, and per-stat links are all present. A minion-only increase is not used as the character's stat. |
| Unknown citation | A unique name that is not in the import, a modifier id that is not in the import, an excerpt pasted onto a different unique, and a gem citation are rejected. |
| Conflicts | A status conflict quotes a forbid line and a `while` line from the import. A modifier-group conflict uses the imported `group` field. Variant and Version headers are quoted from the unique text. An aura-disable line is paired with a different aura the import names. |

The Life numbers and the knowledge counts are locks for this pin. Neither service contains them as a substitute for the checkout. If a future PoB commit changes the result, the test fails and the pin has to move with a new measurement.

Phase 3 tests build the SQLite file from the live checkout in a temporary directory. They do not use a hand-written item, gem, or node. Phase 6 searches that import. A chain is kept only when both excerpts are in the stored rows.

## What was not run

- Desktop Path of Building on Windows, so there is no GUI-versus-headless diff.
- Share codes, pobb.in, and pathofexile.com character import.
- Support-gem compatibility, aura reservation, attribute-requirement failures, cluster jewels, and timeless jewels.
- A desktop check of an equipment or passive edit on one of Neil's saved builds. Tool-argument rejection is covered with the agent tools. Search cancel and the point budget are covered with the Scion fixture.

`engine/adapter.lua` has no self-test switch. The pytest process is the check.

## Fixture

`fixtures/builds/scion-baseline.xml` is the XML `SaveDB` produced for a fresh level 1 Scion on this pin. Do not hand-edit the stat cache and treat the file as a new oracle. If you regenerate it, do it by exporting from the engine and say so in the commit.
