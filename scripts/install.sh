#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

usage() {
    cat <<'EOF'
Usage:
  ./scripts/install.sh [--force]

Installs the package editable into the ACTIVE
Python environment (3.10+) and builds the docs. Create and activate the
environment first, with whatever manager you like.

  --force   reinstall even if an editable install already points here
EOF
}

FORCE=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)
            usage
            exit 0
            ;;
        --force)
            FORCE=1
            shift
            ;;
        *)
            echo "error: unknown argument: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

PYTHON_CMD=(python)
DOCS_CMD=(bash "$ROOT_DIR/scripts/build_docs.sh")

"${PYTHON_CMD[@]}" - <<'PY'
import sys

if sys.version_info < (3, 10):
    version = ".".join(map(str, sys.version_info[:3]))
    raise SystemExit(f"Python 3.10 or newer is required; found {version}")
PY

has_distribution() {
    "${PYTHON_CMD[@]}" - "$1" <<'PY'
import importlib.metadata as metadata
import sys

try:
    metadata.distribution(sys.argv[1])
except metadata.PackageNotFoundError:
    raise SystemExit(1)
PY
}

install_editable() {
    "${PYTHON_CMD[@]}" -m pip install -e "$ROOT_DIR"
}

uninstall_distribution() {
    "${PYTHON_CMD[@]}" -m pip uninstall -y "$1"
}

is_editable_install() {
    "${PYTHON_CMD[@]}" - "$ROOT_DIR" <<'PY'
import importlib.metadata as metadata
import json
from pathlib import Path
import sys
from urllib.parse import unquote, urlparse

root = Path(sys.argv[1]).resolve()
try:
    dist = metadata.distribution("dig")
except metadata.PackageNotFoundError:
    raise SystemExit(1)

direct_url = dist.read_text("direct_url.json")
if direct_url is None:
    raise SystemExit(1)

data = json.loads(direct_url)
parsed = urlparse(data.get("url", ""))
editable = data.get("dir_info", {}).get("editable") is True
if parsed.scheme != "file" or not editable:
    raise SystemExit(1)

installed_path = Path(unquote(parsed.path)).resolve()
raise SystemExit(0 if installed_path == root else 1)
PY
}

if [[ "$FORCE" -eq 1 ]] || ! is_editable_install; then
    echo "Installing dig editable from $ROOT_DIR"
    install_editable
else
    echo "Editable install already points at $ROOT_DIR"
fi

"${DOCS_CMD[@]}"
