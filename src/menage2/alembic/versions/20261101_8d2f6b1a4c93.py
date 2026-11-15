"""holding an item is per user, and lapses after an hour

Revision ID: 8d2f6b1a4c93
Revises: 7c1e5a9d3b20
Create Date: 2026-11-01

"On hold" was a status of the item, so one person setting a task aside hid
it from everybody, and nothing ever brought it back. It becomes a row per
user and item, with the time it was set; a hold counts for an hour.

Items currently on hold become a hold of their owner, starting now, and go
back to "todo". (The `on_hold` value stays in the Postgres enum: removing a
value from one is not worth the rewrite, and nothing writes it any more.)
"""

import sqlalchemy as sa
from alembic import op

revision = "8d2f6b1a4c93"
down_revision = "7c1e5a9d3b20"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "item_holds",
        sa.Column(
            "item_id",
            sa.Integer(),
            sa.ForeignKey("items.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("held_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.execute(
        "INSERT INTO item_holds (item_id, user_id, held_at) "
        "SELECT id, owner_id, now() FROM items "
        "WHERE status = 'on_hold' AND owner_id IS NOT NULL"
    )
    op.execute("UPDATE items SET status = 'todo' WHERE status = 'on_hold'")
    op.drop_column("items", "on_hold_at")


def downgrade():
    op.add_column(
        "items", sa.Column("on_hold_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.execute(
        "UPDATE items SET status = 'on_hold', on_hold_at = h.held_at "
        "FROM item_holds h WHERE h.item_id = items.id "
        "AND h.user_id = items.owner_id AND items.status = 'todo'"
    )
    op.drop_table("item_holds")
