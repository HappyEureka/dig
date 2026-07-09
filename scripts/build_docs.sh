#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

python - <<'PY'
import importlib.util
import sys

required = ["sphinx", "myst_parser", "furo"]
missing = [name for name in required if importlib.util.find_spec(name) is None]
if missing:
    print(
        "Missing docs dependencies: "
        + ", ".join(missing)
        + ". Install them once with: python -m pip install -e .",
        file=sys.stderr,
    )
    raise SystemExit(1)
PY

# Keep docs builds read-only with respect to the active environment. Editable
# installs race when multiple docs sites share one conda env.
rm -rf docs/_build/html
PYTHONPATH="$ROOT_DIR:${PYTHONPATH:-}" \
    python -m sphinx -E -b html docs docs/_build/html

echo "Built docs at docs/_build/html/index.html"
