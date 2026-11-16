# Roadmap

Phase 1 is the gate. Later phases start only after this engine path stays reliable.

## Phase 1 — Engine foundation

Status: implemented against Path of Building dev `e5917f81` (tree 3.30).

- Monorepo layout, docs, and project rules.
- Launch the real engine under LuaJIT.
- Import XML, edit equipment, edit passives, recalculate, compare, export.
- Ignore stored `<PlayerStat>` values.
- Record the git revision and tree version.
- Tests that drive the engine.

Not in Phase 1: share-code decode, pobb.in import, account import, cluster jewels, gem links, and a desktop-PoB pixel comparison. Those need a follow-up once this process is the default path. Desktop PoB was not available in the Linux environment used to verify this phase.

## Phase 2 — Build management

Library, inspector, history, side-by-side comparison, safe editing, and export of XML plus supported share codes. Revisions from Phase 1 are the storage model.

## Phase 3 — Knowledge engine

Items, the passive tree as a graph, gems, and patch notes, with provenance on mechanics that are easy to confuse (damage, life loss, reservation, costs).

## Phase 4 — AI agent

One orchestrator and specialist roles. Models propose changes. The engine accepts or rejects them. No model call per passive node.

## Phase 5 — Optimisation

Candidate generation, deterministic search, caching by build hash plus PoB revision, multi-objective scores, and budgets. Cancel and iteration limits.

## Phase 6 — Build discovery

Interaction graph, synergies, conflicts, and original builds that the engine validates.

## Phase 7 — Economy and progression

Trade, pricing, crafting steps, and staged builds. Prices come from a source with a timestamp, not from the model.

## Phase 8 — Advanced endgame

Timeless jewels, cluster jewels, attribute stacking, defence layers, and Valdo modifiers supplied by the user. A voided map is never reported as guaranteed safe.

## Reference experiment

After Phase 1 is trustworthy: a current-league Juggernaut stacking Light Radius, Strength, and Accuracy, using the items and keystones named in the project brief, compared with Kinetic Blast variants and a conventional Strength stacker on the same budget. The experiment is there to prove, disprove, or change the idea. It is not assumed to be viable.
