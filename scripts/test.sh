#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  python3 -m venv "$ROOT/.venv"
fi
"$ROOT/.venv/bin/pip" install -q -e "$ROOT/services/engine[dev]" -e "$ROOT/services/knowledge[dev]" -e "$ROOT/services/agent[dev]" -e "$ROOT/services/optimisation[dev]" -e "$ROOT/services/discovery[dev]"
"$ROOT/.venv/bin/pytest" -q "$ROOT/services/engine/tests" "$ROOT/services/knowledge/tests" "$ROOT/services/agent/tests" "$ROOT/services/optimisation/tests" "$ROOT/services/discovery/tests"
