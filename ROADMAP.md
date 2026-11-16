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

Status: implemented on the Phase 1 engine pin.

- SQLite library of builds, separate from Path of Building save files.
- Inspector for a fresh engine calculation of the selected revision.
- Version history of immutable revisions.
- Side-by-side comparison of two fresh calculations.
- Edits land on a working copy. The stored revision moves only on save.
- Export of Path of Building XML.

Not in Phase 2: share codes and pobb.in links. Those stay with the import work that Phase 1 deferred.

## Phase 3 — Knowledge engine

Status: item bases, unique text, modifier lines, skill gems, and the passive tree are imported from the pinned checkout. Each record stores source, commit, tree version, manifest version, and retrieval date. The passive graph rejects a disconnected allocation and a point total above the tree file's budget.

Not in this import: patch notes, and a mechanic ontology that distinguishes damage, life loss, reservation, and costs. Those still belong to Phase 3 and are not done.

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
