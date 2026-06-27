# heavymetal/migrations/versions/e05628b5210a_drop_consistency_logs_table.py
"""drop consistency_logs table

Revision ID: e05628b5210a
Revises: a977c0f339e8
Create Date: 2026-06-25 23:39:27.457302

Retires the unused `consistency_logs` table. Nothing ever wrote to it (no code
referenced the model), and consistency streaks will instead be derived from the
`measurements` data we already ingest. Dropping the table also removes the six
throwaway `false` server-defaults declared on its columns in 190f9bf14a7f
during the prod-drift reconciliation — they exist only to keep that legacy
table in sync and have no reason to outlive it.

Prod's table is empty, so the drop is data-lossless (gate.sh pg_dumps prod
before promoting any migration regardless). The downgrade faithfully recreates
the table in its post-drift state (server-defaults intact).
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "e05628b5210a"
down_revision = "a977c0f339e8"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_table("consistency_logs")


def downgrade():
    op.create_table(
        "consistency_logs",
        sa.Column("id", sa.INTEGER(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column("date", sa.DATE(), autoincrement=False, nullable=False),
        sa.Column(
            "weight_tracked",
            sa.BOOLEAN(),
            server_default=sa.text("false"),
            autoincrement=False,
            nullable=True,
        ),
        sa.Column(
            "calories_tracked",
            sa.BOOLEAN(),
            server_default=sa.text("false"),
            autoincrement=False,
            nullable=True,
        ),
        sa.Column(
            "sleep_tracked",
            sa.BOOLEAN(),
            server_default=sa.text("false"),
            autoincrement=False,
            nullable=True,
        ),
        sa.Column(
            "steps_tracked",
            sa.BOOLEAN(),
            server_default=sa.text("false"),
            autoincrement=False,
            nullable=True,
        ),
        sa.Column(
            "body_measured",
            sa.BOOLEAN(),
            server_default=sa.text("false"),
            autoincrement=False,
            nullable=True,
        ),
        sa.Column(
            "goal_met",
            sa.BOOLEAN(),
            server_default=sa.text("false"),
            autoincrement=False,
            nullable=True,
        ),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            autoincrement=False,
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("consistency_logs_user_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("consistency_logs_pkey")),
    )
