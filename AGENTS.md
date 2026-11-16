# Agent notes

This file is for coding agents working in this repository.

## Current phase

Phase 4 tool layer, on top of the Phase 3 knowledge import and the Phase 2 library. Typed tools call the engine and the knowledge store. Mutations copy a revision first. Do not start patch-note ingestion, the trade client, the optimiser, or a live model call. Do not change the pinned Path of Building checkout. The upfront cost round in `CalcOffence.lua` stays. Do not commit API keys.

## Hard rules

- Character stats come from the running engine. Never from `<PlayerStat>`, a previous SQLite row, or a number written in a prompt.
- Do not modify files inside the Path of Building checkout. Drive `HeadlessWrapper.lua`.
- Do not copy code from `ianderse/pob-mcp` (GPL-3.0).
- Do not claim desktop PoB parity unless you actually ran desktop PoB and saved the diff.
- The pin is `engine/pin.json`. If `git -C "$POB_SRC" rev-parse HEAD` disagrees, stop and say so.
- Mutations create a new revision. Do not overwrite the parent's XML.
- The manifest version `2.67.2` is not the game version. The tree version is.

## Where to look

- Engine protocol: `engine/adapter.lua`
- Process and revision rules: `services/engine/src/pob_engine/service.py`
- Why the other integrations were rejected: `POB_INTEGRATION.md`
- Tests that must stay red when the engine is absent: `services/engine/tests/test_phase1.py`
- Game-data import: `services/knowledge`. It reads data files with LuaJIT. It does not start `HeadlessWrapper` and it does not vendor `src/` or `TreeData/`.
- Knowledge tests: `services/knowledge/tests/test_phase3.py`
- Agent tools and the fake provider: `services/agent`. Tool results must come from the engine or the imported data.

## Verification

`./scripts/test.sh` must pass on the pinned checkout. A UI change also needs the Next.js console exercised against that same process.
