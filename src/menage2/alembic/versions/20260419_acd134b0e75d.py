"""add todo note, rename shopping tags

Revision ID: acd134b0e75d
Revises: f12afd1240f1
Create Date: 2026-04-19 17:42:51.977464

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "acd134b0e75d"
down_revision = "f12afd1240f1"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("todos", sa.Column("note", sa.Text(), nullable=True))
    op.execute(
        "UPDATE ingredients SET tags = replace(tags, 'shopping:', 'einkaufen:') "
        "WHERE tags LIKE '%shopping:%'"
    )


def downgrade():
    op.drop_column("todos", "note")
    op.execute(
        "UPDATE ingredients SET tags = replace(tags, 'einkaufen:', 'shopping:') "
        "WHERE tags LIKE '%einkaufen:%'"
    )
