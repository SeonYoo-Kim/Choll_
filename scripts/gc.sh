#!/usr/bin/env bash
# Garbage collection: remove regenerable build artifacts and caches.
# Does NOT touch source, docs, or git-tracked files.
# Usage: bash scripts/gc.sh [--dry-run]
set -euo pipefail

DRY_RUN=0
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=1

# Repo root = parent of this script's directory.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Directories to remove wholesale.
DIRS=(
  "ros2_ws/build" "ros2_ws/install" "ros2_ws/log"
)

# Glob patterns of cache dirs / files anywhere in the tree.
PATTERNS=(
  "__pycache__" ".pytest_cache" ".ruff_cache" ".mypy_cache" "*.egg-info"
)

log() { printf '%s\n' "$*"; }

remove() {
  local path="$1"
  if [[ $DRY_RUN -eq 1 ]]; then
    log "[dry-run] would remove: $path"
  else
    rm -rf "$path"
    log "removed: $path"
  fi
}

log "== Garbage collection (root: $ROOT) =="

for d in "${DIRS[@]}"; do
  [[ -e "$d" ]] && remove "$d"
done

for p in "${PATTERNS[@]}"; do
  # -depth so nested matches are handled before parents.
  while IFS= read -r -d '' match; do
    remove "$match"
  done < <(find . -depth -name "$p" -not -path './.git/*' -print0 2>/dev/null)
done

if [[ $DRY_RUN -eq 1 ]]; then
  log "== dry-run complete (nothing deleted) =="
else
  log "== done =="
fi
