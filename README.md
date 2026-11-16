# PoE Forge

Local-first theorycrafting for Path of Exile 1. Character numbers come from the real [Path of Building](https://github.com/PathOfBuildingCommunity/PathOfBuilding) calculation engine.

This repository is the PoE Forge app. It is not a build importer and it does not copy community builds into the answer.

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

`POB_SRC`, `POB_LUA`, `POB_UTF8_DIR`, `POB_RUNTIME`, and `POB_USER` override the defaults from `.env.example`.

## Docs

- [ARCHITECTURE.md](ARCHITECTURE.md)
- [ROADMAP.md](ROADMAP.md)
- [GAME_DATA.md](GAME_DATA.md)
- [POB_INTEGRATION.md](POB_INTEGRATION.md)
- [AGENTS.md](AGENTS.md)
- [TESTING.md](TESTING.md)
- [CONTRIBUTING.md](CONTRIBUTING.md)
