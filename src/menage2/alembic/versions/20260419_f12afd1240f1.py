"""add todos

Revision ID: f12afd1240f1
Revises: b7f3043fad27
Create Date: 2026-04-19 11:39:17.018727

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

# revision identifiers, used by Alembic.
revision = "f12afd1240f1"
down_revision = "b7f3043fad27"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "todos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("tags", ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column(
            "status",
            sa.Enum("todo", "done", "postponed", name="todostatus"),
            nullable=False,
            server_default="todo",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("postponed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_todos")),
    )
    op.create_index("ix_todos_status", "todos", ["status"])


def downgrade():
    op.drop_index("ix_todos_status", "todos")
    op.drop_table("todos")
    sa.Enum(name="todostatus").drop(op.get_bind(), checkfirst=True)
