# heavymetal/deploy/reload.sh
#!/usr/bin/env bash
# Rebuild CSS and (re)deploy the app — but only if the quality gate passes.
# Invoked by the file-watcher (heavymetal-watch.service) on any source change.
set -uo pipefail

cd /home/brian/projects/heavymetal

# Deploy only from main. The hook and watcher fire on every commit / file save
# regardless of branch, and this script serves the checked-out working tree — so
# without this guard, validating risky work on a feature branch would ship that
# branch straight to prod. Keeping main as the sole deploy source lets you check
# out a branch, validate locally, and never touch the running app. A detached
# HEAD (e.g. a checked-out tag) reports non-main here too, so it's also excluded.
BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo '?')"
if [ "$BRANCH" != "main" ]; then
  echo "reload: on branch '$BRANCH' (not main) — skipping deploy" >&2
  exit 0
fi

# Refuse to deploy a dirty working tree. The watcher fires on every file save,
# so without this a mid-edit or uncommitted state — a half-applied refactor, a
# linter rewrite mid-commit — could be promoted to prod. Deploy only a clean,
# committed snapshot. (Gitignored files like .env / output.css aren't "dirty".)
if [ -n "$(git status --porcelain)" ]; then
  echo "reload: working tree dirty — skipping deploy (commit to deploy a clean snapshot)" >&2
  exit 0
fi

# Quality gate: validate code + migrations on fitnessdb_dev, promote any pending
# migration to prod. If it fails, leave the running app on its last-good version
# (see backend/logs/gate/) and do NOT restart.
if ! bash bin/gate.sh deploy; then
  echo "reload: gate failed — app left on previous version (backend/logs/gate/latest.log)" >&2
  exit 0
fi

# Rebuild Tailwind so any new utility classes in templates take effect.
# output.css is gitignored and excluded from the watch, so this won't loop.
./bin/tailwindcss \
  -i frontend/static/css/style.css \
  -o frontend/static/css/output.css \
  --minify >/dev/null 2>&1 || true

# Defensively clear any latched `failed (start-limit-hit)` state before
# restarting, so a prior burst of restarts can never wedge the service out of
# the watcher's reach (belt-and-suspenders with StartLimitIntervalSec=0 in the
# unit). reset-failed is a harmless no-op when the service is healthy.
systemctl --user reset-failed heavymetal.service
systemctl --user restart heavymetal.service
