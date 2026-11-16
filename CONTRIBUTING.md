# Contributing

## Setup

```bash
./scripts/bootstrap_engine.sh
./scripts/test.sh
```

Bootstrap writes only under `.pob/` (LuaJIT, lua-utf8, the PoB checkout). That directory is gitignored.

To point at a checkout you already have:

```bash
export POB_SRC=/path/to/PathOfBuilding/src
export POB_LUA=/path/to/luajit
export POB_UTF8_DIR=/path/to/dir/with/lua-utf8.so
```

`POB_SRC`'s git HEAD must be the commit in `engine/pin.json`. The tests check.

## Engine changes

- Change `engine/adapter.lua` if the host needs a new PoB call. Keep the checkout itself clean.
- If you move the pin, update `engine/pin.json`, re-vendor `engine/vendor/runtime` from that commit's `runtime/lua/`, regenerate the fixture by exporting from the engine, and re-measure the Life locks in `tests/test_phase1.py`.
- Do not read `<PlayerStat>` from the service. `xml_cache.py` exists so tests can show the cache and the calculation disagree.

## App changes

- UI work stays in `apps/web`.
- HTTP and persistence stay in `services/engine`.
- Item, gem, and passive-tree import stays in `services/knowledge`. Query the generated database. Do not copy data files into the repo, and do not invent a fixture item or node for a test.
- Agent tools stay in `services/agent`. They call the engine service and the knowledge store. A mutation copies a revision first.
- The search stays in `services/optimisation`. It calls those tools. Do not score a number that did not come from the engine, and do not call a model from that package.
- Interaction search stays in `services/discovery`. Cite imported rows. Do not add a modifier the import does not contain, and do not call a model from that package.
- Stage copies and crafting legality stay in `services/progression`. A stage is a new library build. Do not estimate a weight or a crafting cost from a row that does not store one.
- Run `./scripts/test.sh` before opening a pull request. For UI changes, run the web app against a live engine and click the flow, not only the empty page.

## Secrets

API keys stay in an uncommitted config file. The names are commented in `.env.example`. Never commit `.env` or a key. The test suite uses a fake provider and does not call a model API.
