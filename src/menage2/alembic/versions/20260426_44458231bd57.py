"""todo: due_date column and on_hold rename

Revision ID: 44458231bd57
Revises: 375865678696
Create Date: 2026-04-26 19:18:21.120637

Renames the ``postponed`` status (and ``postponed_at`` column) to ``on_hold``,
preserving existing data. Adds a nullable ``due_date`` column with an index.
"""

import sqlalchemy as sa
from alembic import op

revision = "44458231bd57"
down_revision = "375865678696"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("todos", sa.Column("due_date", sa.Date(), nullable=True))
    op.create_index("ix_todos_due_date", "todos", ["due_date"], unique=False)

    op.alter_column("todos", "postponed_at", new_column_name="on_hold_at")

    # Postgres enum: rename the existing value in place so nothing is lost.
    op.execute("ALTER TYPE todostatus RENAME VALUE 'postponed' TO 'on_hold'")


def downgrade():
    op.execute("ALTER TYPE todostatus RENAME VALUE 'on_hold' TO 'postponed'")
    op.alter_column("todos", "on_hold_at", new_column_name="postponed_at")
    op.drop_index("ix_todos_due_date", table_name="todos")
    op.drop_column("todos", "due_date")
