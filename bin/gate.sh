# heavymetal/bin/gate.sh
#!/usr/bin/env bash
# heavymetal/bin/gate.sh <deploy|commit>
# Quality gate: validate code+migrations against fitnessdb_dev, and only on a
# clean pass let the change proceed. On `deploy`, also promote any pending
# migration to prod (with a pg_dump backup first). Exit 0 = pass, 1 = blocked.
set -uo pipefail

cd /home/brian/projects/heavymetal
TRIGGER="${1:-manual}"
# shellcheck disable=SC1091
source venv/bin/activate
set -a
source .env
set +a

read -r HOST PORT DB <<<"$(python3 - <<'PY'
import os, urllib.parse as u
x = u.urlparse(os.environ["FITNESS_DB_URL"].replace("postgresql+psycopg", "postgresql"))
print(x.hostname, x.port or 5432, x.path.lstrip("/"))
PY
)"
PROD_URL="$FITNESS_DB_URL"
DEV_URL="${FITNESS_DB_URL%/*}/${DB}_dev"

LOGDIR="backend/logs/gate"
BACKUPDIR="backend/logs/backups"
mkdir -p "$LOGDIR" "$BACKUPDIR"
TS="$(date +%Y-%m-%d_%H%M%S)"
TMP="$(mktemp)"
BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo '?')"
SHA="$(git rev-parse --short HEAD 2>/dev/null || echo '?')"

{
  echo "trigger : $TRIGGER"
  echo "time    : $TS"
  echo "git     : $BRANCH @ $SHA"
  echo "dev db  : ${DB}_dev"
  echo "==== apply migrations to dev ===="
} >"$TMP"

FAILED=0
FITNESS_DB_URL="$DEV_URL" flask db upgrade >>"$TMP" 2>&1 || FAILED=1
echo "==== pytest (against dev) ====" >>"$TMP"
# Coverage floor is intentionally HIGHER than CI's (90%, in .github/workflows/
# ci.yml). Commits here auto-deploy to prod, so the gate is the last checkpoint
# before serving — the extra margin nudges us to shore up coverage while it's
# still a git commit away, instead of discovering erosion at CI's cliff edge
# after prod already updated.
TEST_DATABASE_URL="$DEV_URL" python -m pytest --cov=backend --cov-fail-under=92 \
  >>"$TMP" 2>&1 || FAILED=1

if [ "$FAILED" -ne 0 ]; then
  cp "$TMP" "$LOGDIR/${TS}_${TRIGGER}_FAIL.log"
  { echo "RESULT  : FAIL"; cat "$TMP"; echo; echo "ACTION  : ${TRIGGER} BLOCKED"; } >"$LOGDIR/latest.log"
  rm -f "$TMP"
  echo "GATE FAIL ($TRIGGER) — see $LOGDIR/${TS}_${TRIGGER}_FAIL.log" >&2
  exit 1
fi

# ---- passed ----
ACTION="ok"
if [ "$TRIGGER" = "deploy" ]; then
  PROD_CUR="$(FITNESS_DB_URL="$PROD_URL" flask db current 2>/dev/null | grep -oE '[a-f0-9]{12}' | head -1 || true)"
  HEAD_REV="$(flask db heads 2>/dev/null | grep -oE '[a-f0-9]{12}' | head -1 || true)"
  if [ -n "$HEAD_REV" ] && [ "$PROD_CUR" != "$HEAD_REV" ]; then
    BACKUP="$BACKUPDIR/${DB}_${TS}_pre-${HEAD_REV}.sql.gz"
    echo "==== pending migration ($PROD_CUR -> $HEAD_REV): backup + migrate prod ====" >>"$TMP"
    pg_dump -h "$HOST" -p "$PORT" -U postgres -d "$DB" --no-owner --no-privileges \
      | gzip >"$BACKUP" 2>>"$TMP"
    FITNESS_DB_URL="$PROD_URL" flask db upgrade >>"$TMP" 2>&1
    ACTION="migrated prod $PROD_CUR -> $HEAD_REV (backup: $BACKUP)"
  else
    ACTION="no pending migration"
  fi
fi

{ echo "RESULT  : PASS"; cat "$TMP"; echo; echo "ACTION  : $ACTION"; } >"$LOGDIR/latest.log"
rm -f "$TMP"
exit 0
