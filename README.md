# PoE Forge

Local-first theorycrafting for Path of Exile 1. Character numbers come from the real [Path of Building](https://github.com/PathOfBuildingCommunity/PathOfBuilding) calculation engine.

This repository is the PoE Forge app. It is not a build importer and it does not copy community builds into the answer.

## Phase 5

The optimisation package (`services/optimisation`) searches a library build without editing the original import. It copies the revision, then tries equipment and passive candidates through the agent tools. Each kept copy is recalculated by the Path of Building engine. A disconnected passive set, or one over the tree's point budget or a caller point budget, is rejected. Results are ranked by a stated objective, such as Life. Identical builds are cached by their canonical hash, the PoB revision, and the configuration profile. A search stops at a max iteration count or when a cancel token is set.

The Scion fixture is the regression case: baseline Life 60, Glorious Plate 160, and that plate plus the Life node 256. Those numbers come from the engine on this pin.

The package does not call a model. API keys stay out of the repo.

## Phase 4

The agent package (`services/agent`) exposes typed tools over the engine and the knowledge database: import, inspect, calculate, compare, search uniques, gems, and passive nodes, find a passive path, allocate, equip, and export.

`equip_item` and `allocate_passives` copy the revision first. The imported XML stays as it was. Character numbers in a tool result come from the running engine. Catalogue rows come from the imported checkout, with the source commit on each record.

OpenAI, OpenAI-compatible endpoints, Anthropic, Gemini, and Ollama have a request interface. This package does not open a network connection. Keys stay in an uncommitted local file. The tests use a fake provider.

Research workflows and recommendation ranking are not in this slice.

## Phase 3

The knowledge package imports the pinned checkout's game data into SQLite (`data/knowledge.sqlite`, or `POB_KNOWLEDGE`):

- Item bases, unique-item text, and modifier lines.
- Skill gems and the granted-effect tables those gems name.
- The passive tree as a graph. An allocation that does not connect to the class start is rejected. The point cap is the tree file's own budget.

Every imported record carries provenance: source repository, commit, tree version, manifest version, and the UTC retrieval date. The importer reads the Lua data files. It does not start the calculation runtime and it does not write into the checkout.

```bash
./.venv/bin/pob-knowledge import
./.venv/bin/pob-knowledge show "Glorious Plate"
```

Patch-note ingestion is not part of this import.

## Phase 2

The web app is a local build library:

- Builds are stored in SQLite (`data/library.sqlite`, or `POB_LIBRARY`). That file is not a Path of Building save folder.
- The inspector shows stats from `CalcsTab:BuildOutput` for the selected revision.
- Version history lists every revision of a build.
- Comparison recalculates two revisions and shows the engine's deltas.
- Equipment and passive edits are written to a working copy. The stored revision changes only when you save.
- Export returns Path of Building XML for the selected revision.

## Phase 1

The engine service can:

1. Launch the pinned Path of Building dev source under LuaJIT.
2. Import a real build XML file.
3. Replace a piece of equipment and allocate passives.
4. Recalculate with `CalcsTab:BuildOutput`. Stored `<PlayerStat>` tags are not the result.
5. Compare two fresh calculations.
6. Export XML that the same engine can import again.

The pinned checkout is dev `e5917f81fd64c10d9bc816c410da395ed18e57ba` (15 Nov 2026). Its manifest still says `2.67.2`. The skill tree it loads is **3.30**.

## Layout

| Path | Role |
| --- | --- |
| `apps/web` | Next.js console |
| `services/engine` | FastAPI service and build store |
| `services/knowledge` | Item, gem, and passive-tree import |
| `services/agent` | Typed agent tools and the model-provider interface |
| `services/optimisation` | Deterministic candidate search over engine calculations |
| `engine/adapter.lua` | Stdio driver for an unmodified PoB checkout |
| `engine/vendor/runtime` | PoB's Lua libraries (`xml`, `dkjson`, …) |
| `fixtures/builds` | XML exported by the pinned engine |
| `.pob/` | Local LuaJIT, lua-utf8, and PoB checkout (not committed) |

## Run

Requirements: git, gcc, make, Python 3.11+, Node.js 20+.

```bash
./scripts/bootstrap_engine.sh
./scripts/test.sh
./.venv/bin/python -m pob_engine
```

In another shell:

```bash
cd apps/web
npm install
npm run dev
```

Open the console at `http://127.0.0.1:3000`. The page proxies `/api` to the engine on port 8000.

`POB_SRC`, `POB_LUA`, `POB_UTF8_DIR`, `POB_RUNTIME`, `POB_USER`, `POB_LIBRARY`, and `POB_KNOWLEDGE` override the defaults from `.env.example`.

## Docs

- [ARCHITECTURE.md](ARCHITECTURE.md)
- [ROADMAP.md](ROADMAP.md)
- [GAME_DATA.md](GAME_DATA.md)
- [POB_INTEGRATION.md](POB_INTEGRATION.md)
- [AGENTS.md](AGENTS.md)
- [TESTING.md](TESTING.md)
- [CONTRIBUTING.md](CONTRIBUTING.md)
