# heavymetal/migrations/versions/190f9bf14a7f_reconcile_prod_drift_server_defaults_.py
"""reconcile prod drift: server defaults + drop orphan role_type enum

Revision ID: 190f9bf14a7f
Revises: 6926966c934c
Create Date: 2026-06-25 16:49:16.731210

Reconciles two pieces of drift the squashed baseline surfaced once `db check`
was tightened with compare_type / compare_server_default:

1. Server defaults that existed only in the physical prod/dev databases
   (legacy) and were absent from BOTH the model and the squashed baseline.
   A from-scratch rebuild would have silently dropped them. We make the
   default authoritative here so a fresh build reproduces prod exactly. The
   alters are no-ops on prod/dev (the default already matches) and only take
   effect on a fresh build.
2. An orphan `role_type` enum left in prod from a removed roles concept; no
   column references it. Dropped with IF EXISTS so it's idempotent on dev /
   fresh builds that never had it.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "190f9bf14a7f"
down_revision = "6926966c934c"
branch_labels = None
depends_on = None


# (table, column, existing_type, server_default) — values mirror the model and
# the live databases.
SERVER_DEFAULTS = [
    ("users", "role", sa.String(length=20), sa.text("'user'")),
    ("users", "is_active", sa.Boolean(), sa.text("true")),
    ("measurements", "source", sa.String(length=50), sa.text("'manual'")),
    ("measurements", "confidence_flag", sa.Boolean(), sa.text("true")),
    ("body_measurements", "source", sa.String(length=20), sa.text("'manual'")),
    ("consistency_logs", "weight_tracked", sa.Boolean(), sa.text("false")),
    ("consistency_logs", "calories_tracked", sa.Boolean(), sa.text("false")),
    ("consistency_logs", "sleep_tracked", sa.Boolean(), sa.text("false")),
    ("consistency_logs", "steps_tracked", sa.Boolean(), sa.text("false")),
    ("consistency_logs", "body_measured", sa.Boolean(), sa.text("false")),
    ("consistency_logs", "goal_met", sa.Boolean(), sa.text("false")),
    ("workout_plan_exercises", "order_index", sa.Integer(), sa.text("0")),
]


def upgrade():
    for table, column, existing_type, default in SERVER_DEFAULTS:
        op.alter_column(
            table, column, existing_type=existing_type, server_default=default
        )
    op.execute("DROP TYPE IF EXISTS role_type")


def downgrade():
    op.execute("CREATE TYPE role_type AS ENUM ('user', 'admin')")
    for table, column, existing_type, _default in SERVER_DEFAULTS:
        op.alter_column(table, column, existing_type=existing_type, server_default=None)
