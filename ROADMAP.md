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

Status: the tool layer is in place. A model can call typed tools. The engine calculates, and the knowledge import answers catalogue queries. Equipment and passive edits run on a library copy. Provider kinds are OpenAI, OpenAI-compatible, Anthropic, Gemini, and Ollama. This package does not call them. Tests use a fake provider.

Not in this slice: the orchestrator roles, research, and ranked recommendations. No model call per passive node.

## Phase 5 — Optimisation

Status: a deterministic search copies a library revision and tries equipment and passive candidates through the agent tools. Each kept copy is recalculated by the engine. Disconnected and over-budget trees are rejected. Ranking uses a weighted objective. The cache key is the canonical build hash, the PoB revision, and the configuration profile. Searches honour a max iteration count, a passive-point budget, and cancellation.

Not in this slice: the Optimisation Lab UI, trade prices, and a model choosing the candidates. The Scion proof is still Glorious Plate and the Life node, calculated by the pinned engine.

## Phase 6 — Build discovery

Status: a search over the imported unique items and modifier lines. A chain quotes two lines that share a phrase from that text. A conflict quotes a shared modifier group, Variant or Version headers, a forbidden status against a line that requires it, or an aura-disable line against a line that requires another aura named in the import. A citation that is not in the database is rejected. The search does not calculate stats and does not call a model.

Not in this slice: original builds, engine validation of a discovered chain, and the Build Discovery page.

## Phase 7 — Economy and progression

Status: a library build can be copied into three saved builds, one each for campaign, early maps, and endgame. The source revision is not updated. Crafting legality uses imported modifier type and group: a normal rare is 3 prefixes and 3 suffixes, a shared group in one modifier file is rejected, and a six-mod rare that is not that split is rejected. The import has no weights. A weight or a crafting cost is refused.

Not in this slice: trade prices, crafting steps, and a currency cost. Prices still have to come from a source with a timestamp.

## Phase 8 — Advanced endgame

Timeless jewels, cluster jewels, attribute stacking, defence layers, and Valdo modifiers supplied by the user. A voided map is never reported as guaranteed safe.

## Reference experiment

After Phase 1 is trustworthy: a current-league Juggernaut stacking Light Radius, Strength, and Accuracy, using the items and keystones named in the project brief, compared with Kinetic Blast variants and a conventional Strength stacker on the same budget. The experiment is there to prove, disprove, or change the idea. It is not assumed to be viable.
