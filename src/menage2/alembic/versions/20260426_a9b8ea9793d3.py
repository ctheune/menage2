"""todo: recurrence rules

Revision ID: a9b8ea9793d3
Revises: 44458231bd57
Create Date: 2026-04-26 20:17:41.589420

Adds the recurrence_rules table and links Todo to it via recurrence_id.
recurred_from_id is a self-FK forming the spawn-history chain.
"""

import sqlalchemy as sa
from alembic import op

revision = "a9b8ea9793d3"
down_revision = "44458231bd57"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "recurrence_rules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "kind", sa.Enum("after", "every", name="recurrencekind"), nullable=False
        ),
        sa.Column("interval_value", sa.Integer(), nullable=False),
        sa.Column(
            "interval_unit",
            sa.Enum("day", "week", "month", "year", name="recurrenceunit"),
            nullable=False,
        ),
        sa.Column("weekday", sa.Integer(), nullable=True),
        sa.Column("month_day", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recurrence_rules")),
    )

    op.add_column("todos", sa.Column("recurrence_id", sa.Integer(), nullable=True))
    op.add_column("todos", sa.Column("recurred_from_id", sa.Integer(), nullable=True))
    op.create_index("ix_todos_recurrence_id", "todos", ["recurrence_id"], unique=False)
    op.create_foreign_key(
        op.f("fk_todos_recurrence_id_recurrence_rules"),
        "todos",
        "recurrence_rules",
        ["recurrence_id"],
        ["id"],
    )
    op.create_foreign_key(
        op.f("fk_todos_recurred_from_id_todos"),
        "todos",
        "todos",
        ["recurred_from_id"],
        ["id"],
    )


def downgrade():
    op.drop_constraint(
        op.f("fk_todos_recurred_from_id_todos"), "todos", type_="foreignkey"
    )
    op.drop_constraint(
        op.f("fk_todos_recurrence_id_recurrence_rules"), "todos", type_="foreignkey"
    )
    op.drop_index("ix_todos_recurrence_id", table_name="todos")
    op.drop_column("todos", "recurred_from_id")
    op.drop_column("todos", "recurrence_id")
    op.drop_table("recurrence_rules")
    op.execute("DROP TYPE IF EXISTS recurrencekind")
    op.execute("DROP TYPE IF EXISTS recurrenceunit")
