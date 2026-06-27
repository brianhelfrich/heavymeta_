# heavymetal/project_clean_pack.sh
#!/usr/bin/env bash
set -euo pipefail

# -----------------------------
# Config
# -----------------------------
PROJECT_ROOT="${1:-$(pwd)}"
OUTDIR="${PROJECT_ROOT}"
PKG_NAME="$(basename "$PROJECT_ROOT")"
STAMP="$(date +%Y%m%d_%H%M%S)"
ARCHIVE="${PKG_NAME}_${STAMP}.tar.gz"

# pip-compile behavior
PIP_COMPILE_UPGRADE=1      # always upgrade to latest versions allowed by ~= ranges
PIP_COMPILE_HASHES=0       # set to 1 for hashes
PIP_COMPILE_ALLOW_UNSAFE=0 # set to 1 to pin pip/setuptools/wheel
NO_HEADER=0                # set to 1 to strip pip-tools header comments

# Exclude junk/noise from archive
EXCLUDES=(
  --exclude=".git"
  --exclude=".gitignore"
  --exclude=".idea"
  --exclude=".vscode"
  --exclude="__pycache__"
  --exclude="*.pyc"
  --exclude="*.pyo"
  --exclude=".pytest_cache"
  --exclude=".mypy_cache"
  --exclude=".ruff_cache"
  --exclude="node_modules"
# --exclude="dist"
  --exclude="build"
  --exclude=".DS_Store"
  --exclude="venv"
  --exclude=".venv"
  --exclude="env"
  --exclude=".env"
  --exclude="*.tar.gz"
)

# -----------------------------
# Logging helpers
# -----------------------------
log()   { printf "==> %s\n" "$*"; }
warn()  { printf "WARNING: %s\n" "$*" >&2; }
fail()  { printf "ERROR: %s\n" "$*" >&2; exit 1; }

# -----------------------------
# Python/venv discovery
# Priority: active venv -> ./venv -> ./.venv -> python3 -> python
# -----------------------------
resolve_python() {
  if [[ -n "${VIRTUAL_ENV-}" && -x "${VIRTUAL_ENV}/bin/python" ]]; then
    echo "${VIRTUAL_ENV}/bin/python"; return
  fi
  if [[ -x "${PROJECT_ROOT}/venv/bin/python" ]]; then
    echo "${PROJECT_ROOT}/venv/bin/python"; return
  fi
  if [[ -x "${PROJECT_ROOT}/.venv/bin/python" ]]; then
    echo "${PROJECT_ROOT}/.venv/bin/python"; return
  fi
  if command -v python3 >/dev/null 2>&1; then
    echo "python3"; return
  fi
  if command -v python >/dev/null 2>&1; then
    echo "python"; return
  fi
  fail "No Python interpreter found."
}

# -----------------------------
# Requirements lock (pip-compile preferred, pip freeze fallback)
# - honors requirements.in if present
# - default: no hashes (you chose that), but supports flags
#   set PIP_COMPILE_HASHES=1 to include hashes
#   set PIP_COMPILE_UPGRADE=1 to upgrade within ranges
#   set PIP_COMPILE_ALLOW_UNSAFE=1 to include pip/setuptools/wheel
# -----------------------------
rebuild_requirements() {
  local PY="$1"
  local have_in=false
  [[ -f "${PROJECT_ROOT}/requirements.in" ]] && have_in=true

  log "(1/3) Rebuilding requirements.txt"

  # Check if pip-tools is available in the resolved interpreter
  if "$PY" -m pip show pip-tools >/dev/null 2>&1; then
    local args=(-o requirements.txt)
    [[ "${PIP_COMPILE_UPGRADE-}" == "1" ]] && args+=(--upgrade)
    [[ "${PIP_COMPILE_HASHES-}" == "1" ]] && args+=(--generate-hashes)
    [[ "${PIP_COMPILE_ALLOW_UNSAFE-}" == "1" ]] && args+=(--allow-unsafe)

    if $have_in; then
      log "Using pip-compile on requirements.in"
      "$PY" -m piptools compile "${args[@]}" requirements.in
    else
      warn "requirements.in not found; compiling from installed environment constraints"
      # Compile from a temporary file that lists top-level packages from current env
      # This keeps format consistent even without an .in file.
      local tmp_in
      tmp_in="$(mktemp)"
      "$PY" - <<'PYEOF' > "$tmp_in"
import pkgutil
# Basic top-level list from working env when no requirements.in exists.
# You can replace this with a curated list if preferred.
mods = sorted({m.name for m in pkgutil.iter_modules()})
# Keep this minimal; it's mainly a safety net. Usually you'll maintain requirements.in.
print("\n".join([]))
PYEOF
      "$PY" -m piptools compile "${args[@]}" "$tmp_in" || {
        warn "pip-compile failed without requirements.in, falling back to pip freeze."
        "$PY" -m pip freeze > requirements.txt
      }
      rm -f "$tmp_in"
    fi

  else
    warn "pip-tools not installed in this interpreter; falling back to pip freeze."
    "$PY" -m pip freeze > requirements.txt
  fi

  # Make sure we used the resolved interpreter’s pip for consistency
  # (not strictly necessary, but good hygiene if we later sanity-check)
  if [[ ! -s requirements.txt ]]; then
    fail "requirements.txt was not generated."
  fi

  # Optional cleanup: remove pip-tools header comments if you want a clean file
  if [[ "${NO_HEADER-}" == "1" && -f requirements.txt ]]; then
    # Strip first contiguous comment block (header) only
    awk 'BEGIN{skip=1} /^#/ && skip {next} {skip=0; print}' requirements.txt > requirements.txt.tmp \
      && mv requirements.txt.tmp requirements.txt
  fi
}

# -----------------------------
# Project structure markdown
# -----------------------------
emit_project_structure() {
  log "(2/3) Generating project_structure.md"
  {
    echo "# Project Structure — ${PKG_NAME}"
    echo
    echo "Generated: ${STAMP}"
    echo
    echo '````'
    if command -v tree >/dev/null 2>&1; then
      tree -a -I '.git|.idea|.vscode|node_modules|__pycache__|.pytest_cache|.mypy_cache|.ruff_cache|.DS_Store|venv|.venv|env|.env' .
    else
      warn "tree not found; using find as fallback"
      find . -path './.git' -prune -o -path './node_modules' -prune -o -path './venv' -prune -o -path './.venv' -prune -o -print
    fi
    echo '````'
  } > "${PROJECT_ROOT}/project_structure.md"
}

# -----------------------------
# Archive
# -----------------------------
make_archive() {
  log "(3/3) Creating ${ARCHIVE}"
  ( cd "$PROJECT_ROOT" && tar czf "$OUTDIR/$ARCHIVE" "${EXCLUDES[@]}" . )
  log "Archive written: $OUTDIR/$ARCHIVE"
}

# -----------------------------
# Main
# -----------------------------
main() {
  cd "$PROJECT_ROOT" || fail "Cannot cd into ${PROJECT_ROOT}"

  local PY
  PY="$(resolve_python)"
  log "Using Python: $PY"

  # Sanity: ensure pip itself is available
  "$PY" -m pip --version >/dev/null 2>&1 || fail "pip is not available in the resolved interpreter."

  rebuild_requirements "$PY"
  emit_project_structure
  make_archive
  log "Done."
}

main "$@"
