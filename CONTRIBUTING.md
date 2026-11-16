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
- Run `./scripts/test.sh` before opening a pull request. For UI changes, run the web app against a live engine and click the flow, not only the empty page.

## Secrets

No API keys in this phase. When providers arrive, keys go in an uncommitted config file. Never commit `.env`.
