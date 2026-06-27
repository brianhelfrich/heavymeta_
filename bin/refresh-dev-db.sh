# heavymetal/bin/refresh-dev-db.sh
#!/usr/bin/env bash
# heavymetal/bin/refresh-dev-db.sh
# (Re)create fitnessdb_dev as a fresh snapshot of prod fitnessdb. Safe to run
# anytime — it only ever drops/writes the *_dev database, never prod.
# Requires a ~/.pgpass entry covering the postgres maintenance DB (db field '*').
set -euo pipefail

cd /home/brian/projects/heavymetal
set -a
source .env
set +a

read -r HOST PORT DB <<<"$(python3 - <<'PY'
import os, urllib.parse as u
x = u.urlparse(os.environ["FITNESS_DB_URL"].replace("postgresql+psycopg", "postgresql"))
print(x.hostname, x.port or 5432, x.path.lstrip("/"))
PY
)"
DEVDB="${DB}_dev"

echo "Refreshing ${DEVDB} from ${DB} on ${HOST}:${PORT} ..."
psql -h "$HOST" -p "$PORT" -U postgres -d postgres -v ON_ERROR_STOP=1 \
  -c "DROP DATABASE IF EXISTS ${DEVDB} WITH (FORCE);"
psql -h "$HOST" -p "$PORT" -U postgres -d postgres -v ON_ERROR_STOP=1 \
  -c "CREATE DATABASE ${DEVDB} OWNER postgres;"
pg_dump -h "$HOST" -p "$PORT" -U postgres -d "$DB" --no-owner --no-privileges \
  | psql -h "$HOST" -p "$PORT" -U postgres -d "$DEVDB" -v ON_ERROR_STOP=1 -q

echo "Done. ${DEVDB} now mirrors ${DB}."
