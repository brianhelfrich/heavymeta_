# heavymetal/migrations/versions/a977c0f339e8_add_measurements_unique_constraint_user_.py
"""add measurements unique constraint (user, date, type, unit)

Revision ID: a977c0f339e8
Revises: 190f9bf14a7f
Create Date: 2026-06-25 22:02:45.033076

Backs the natural key the ingest core upserts on so retries / concurrent POSTs
to /api/ingest can't create duplicate rows, and enables an atomic
INSERT … ON CONFLICT upsert. Prod has zero existing duplicates, so the
constraint applies cleanly.
"""

from alembic import op

revision = "a977c0f339e8"
down_revision = "190f9bf14a7f"
branch_labels = None
depends_on = None

_NAME = "uq_measurements_user_date_type_unit"


def upgrade():
    op.create_unique_constraint(
        _NAME, "measurements", ["user_id", "date", "measurement_type", "unit"]
    )


def downgrade():
    op.drop_constraint(_NAME, "measurements", type_="unique")
