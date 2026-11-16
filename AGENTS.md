# Agent notes

This file is for coding agents working in this repository.

## Current phase

Phase 2: the SQLite build library, inspector, history, comparison, safe edits, and XML export, on top of the Phase 1 engine. Do not start the knowledge base, trade client, or optimiser. Do not change the pinned Path of Building checkout. The upfront cost round in `CalcOffence.lua` stays.

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

## Verification

`./scripts/test.sh` must pass on the pinned checkout. A UI change also needs the Next.js console exercised against that same process.
