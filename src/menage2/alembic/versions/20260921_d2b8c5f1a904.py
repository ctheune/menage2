"""record periods of absence

Revision ID: d2b8c5f1a904
Revises: c1f4a7e3b210
Create Date: 2026-09-21 10:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "d2b8c5f1a904"
down_revision = "c1f4a7e3b210"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "absences",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("ends_on >= starts_on", name="ck_absences_dates"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_absences_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_absences"),
    )
    op.create_index("ix_absences_user_id", "absences", ["user_id"])
    # Every question asked of this table is "who is away on this day".
    op.create_index("ix_absences_dates", "absences", ["starts_on", "ends_on"])


def downgrade():
    op.drop_index("ix_absences_dates", table_name="absences")
    op.drop_index("ix_absences_user_id", table_name="absences")
    op.drop_table("absences")
