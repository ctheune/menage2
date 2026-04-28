"""protocols: migrate owner_id to first admin, make NOT NULL

Revision ID: 20260428_protocols_owner
Revises: 20260428_teams
Create Date: 2026-04-28

"""

from alembic import op

revision = "20260428_protocols_owner"
down_revision = "20260428_teams"
branch_labels = None
depends_on = None


def upgrade():
    # Assign any ownerless protocols to the first admin user.
    op.execute(
        """
        UPDATE protocols
        SET owner_id = (
            SELECT id FROM users
            WHERE is_admin = true
            ORDER BY id
            LIMIT 1
        )
        WHERE owner_id IS NULL
        """
    )

    op.alter_column("protocols", "owner_id", nullable=False)


def downgrade():
    op.alter_column("protocols", "owner_id", nullable=True)
