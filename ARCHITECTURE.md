# Architecture

The monorepo has separate runnable parts. Later phases sit beside the engine. They do not replace it.

```text
apps/web  --->  services/engine  --->  engine/adapter.lua  --->  Path of Building src/
                 SQLite revisions                              CalcsTab:BuildOutput

services/knowledge  --->  LuaJIT data reader  --->  Path of Building src/Data and TreeData
                        SQLite items, gems, tree

services/agent  --->  engine service and knowledge store
                  model provider interface (no network in this package)

services/optimisation  --->  agent tools
                       copies, scores, and caches engine calculations

services/discovery  --->  knowledge store
                      chains and conflicts from imported unique and modifier text

services/progression  --->  engine library copies
                         knowledge store for modifier type and group
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

The web app does not query this database yet. The agent tools do.

## Agent tools

`services/agent` is a separate package. It does not calculate stats and it does not import Lua.

- Each tool has a typed argument schema. Unknown names and arguments that do not match the schema are rejected.
- `import_build`, `get_build_state`, `calculate_build`, `compare_builds`, `equip_item`, `allocate_passives`, and `export_build` call the engine service. A calculation is published only when its `source` is `pob-engine`.
- `search_unique_items`, `search_skill_gems`, `search_passive_nodes`, and `find_passive_path` read the knowledge database. Records keep the import's source commit.
- `equip_item` and `allocate_passives` copy the caller's revision, then edit the copy. A disconnected passive set or a point total above the tree file's budget is rejected before that copy is kept. The imported row is not updated.
- The provider interface can describe an OpenAI, OpenAI-compatible, Anthropic, Gemini, or Ollama request. `complete` sends only through a transport the caller supplies. With no transport it refuses. The tests use a fake provider, so a tool result cannot be a number the model wrote down.

## Optimisation

`services/optimisation` does not calculate stats and does not call a model. It asks the agent tools to copy, equip, allocate, and calculate.

- The stored import is copied first. Mutating tools then copy again, so the saved revision is not the edited parent.
- Passive candidates are checked on the imported graph before a copy is kept. A disconnected set, a set over the tree file's point budget, or a set over the caller's point budget is rejected.
- A result is ranked only when its `source` is `pob-engine`. The score reads those stats. A missing stat is not treated as zero.
- The cache key is a canonical hash of the build (items, skills, tree, and build attributes, without `<PlayerStat>`), the engine revision, and the active configuration profile. A second identical trial reuses the cached engine result.
- `max_iterations` stops the search. A cancel token does the same between candidates. If a hard minimum or maximum is never met, the result says the objective is impossible.

The web console is still the library, inspector, history, and comparison. It is not the Optimisation Lab.

## Discovery

`services/discovery` reads the knowledge database. It does not calculate stats and it does not call a model.

A chain is two cited lines that share a phrase copied from the import. The first line grants a skill or adds a stat. The second line names that skill, or says the stat's increases also apply, or scales for every point of it or per it. A conflict cites a shared modifier `group` (the field Path of Building uses to keep one mod from a group), two `Variant` or `Version` headers on one unique, a line that forbids a status and a line that requires it, or an aura-disable line and a line that requires a different aura named in that same text.

A step that names an item or a modifier the import does not contain, or quotes text that row does not contain, is rejected. Minion, ally, totem, and golem stats are not treated as the character's stat.

## Progression

`services/progression` calls the engine library and reads the knowledge database. It does not calculate a new stat of its own and it does not call a model.

`library_copy` inserts a new build whose saved revision is the source XML. The source build's saved revision is not moved. Progression asks for one such copy per stage: campaign, early maps, and endgame. Editing a stage uses the existing equipment path, which writes a draft of that stage's build.

A rare craft is checked against imported `modType` and `group`. The slot counts are the pinned item editor's: a rare that is not a jewel or a graft has six explicit mods, and the editor splits that limit into prefixes and suffixes. A group conflict is reported only when the imported rows carry the same group in the same file. Weights are not on those rows. The check refuses a weight and refuses a crafting cost.

## What is intentionally absent

Trade prices, crafting currency cost, patch-note ingestion, and recommendation workflows are later work. The discovery search does not build a character or run it through the engine.
