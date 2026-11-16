# Architecture

The monorepo has four runnable parts. Later phases add agents and optimisation beside them. They do not replace the engine.

```text
apps/web  --->  services/engine  --->  engine/adapter.lua  --->  Path of Building src/
                 SQLite revisions                              CalcsTab:BuildOutput

services/knowledge  --->  LuaJIT data reader  --->  Path of Building src/Data and TreeData
                        SQLite items, gems, tree
```

## Web

`apps/web` is a Next.js app. It lists the SQLite library, inspects a revision, shows version history, compares two calculations, and exports XML. Equipment and passive edits run only on a working copy. It has no damage formulas.

The dev server rewrites `/api/*` to the Python process on `127.0.0.1:8000`.

## Engine service

`services/engine` owns the Path of Building process and the build library.

- One LuaJIT process stays open. Requests are JSON, one object per line.
- Each import or edit stores a new revision. The parent revision is left as it was.
- A build has one saved revision. Imports and explicit saves point `saved_revision_id` at a new row. Equipment edits, passive edits, and copies insert `draft` rows and leave that pointer where it was.
- Discard deletes one leaf draft. It refuses the saved revision and any revision that already has a child.
- SQLite keeps the XML, a search index (FTS5), and a log of calculations. The log is an audit trail. `calculate` and `inspect` always call the engine again.
- Compare loads each revision and calculates both. A stat table is rejected unless `source` is `pob-engine`.
- The default library file is `data/library.sqlite`. The headless process uses a temporary user directory and does not read Path of Building's Builds folder.

The service binds to loopback. There is no account system.

## Adapter

`engine/adapter.lua` runs with its working directory set to the PoB `src/` directory. It loads upstream `HeadlessWrapper.lua` without modifying that checkout.

It has to compensate for three host gaps:

- Current LuaJIT rejects the `#@` line PoB puts at the top of launcher files, so the adapter turns a leading `#` into a comment before `load`.
- PoB `require`s `lua-utf8`, `xml`, and `dkjson`, which live outside `src/`. `package.path` and `package.cpath` point at the vendored runtime and the built `lua-utf8.so`.
- The headless `Inflate` stub returns an empty string. The adapter replaces it with zlib `uncompress` so compressed data is not discarded.

After every edit, the adapter calls `BuildOutput`. When auto-level is on, it also runs `EstimatePlayerProgress` and calculates again if the level changed. That is the same level step the desktop frame applies. The adapter never reads `<PlayerStat>`.

`SaveDB` writes `<PlayerStat>` from `mainOutput` at export time. The next import still calculates from items, tree, skills, and configuration.

## Knowledge service

`services/knowledge` is a separate package. It reads item, gem, and passive-tree files from the pinned checkout and stores them in `data/knowledge.sqlite`.

- The reader is LuaJIT plus the vendored `dkjson`. It does not start `HeadlessWrapper` and it does not call `engine/adapter.lua`.
- It refuses a checkout whose commit or manifest version disagrees with `engine/pin.json`.
- The passive graph rejects an allocation that does not connect to the class start, and it rejects one that spends more points than the tree file allows.
- Public records include the source repository, commit, tree version, manifest version, and retrieval date.

The web app does not query this database yet.

## What is intentionally absent

AI providers, MCP tools, trade prices, patch-note ingestion, and the optimisation search are later work. The web console is the library, inspector, history, and comparison. It is not the full dashboard from the roadmap.
