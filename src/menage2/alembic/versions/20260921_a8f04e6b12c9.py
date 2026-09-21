"""run items join the family, and lose a status of their own

Revision ID: a8f04e6b12c9
Revises: d71b5c93a4e8
Create Date: 2026-09-21

A run item's `pending`/`done`/`sent_to_todo` was a second vocabulary for
the same three things every item has. `pending` is `todo` and both of the
others are `done`; a line that was sent off is done here and waiting
elsewhere, which `sent_todo_id` already says. So the column and its enum
type go, and `protocolrunitemstatus` goes with them.

Run items take their run's spawn time as their creation time, since they
are snapshotted when the run is first opened and have none of their own.
"""

import sqlalchemy as sa
from alembic import op

revision = "a8f04e6b12c9"
down_revision = "d71b5c93a4e8"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "CREATE TEMP TABLE run_item_map AS "
        "SELECT id AS old_id, nextval('items_id_seq') AS new_id "
        "FROM protocol_run_items ORDER BY id"
    )
    op.execute(
        "INSERT INTO items (id, kind, text, note, created_at, status) "
        "SELECT m.new_id, 'protocol_run_item', i.text, i.note, r.spawned_at, "
        "       CASE i.status WHEN 'pending' THEN 'todo'::todostatus "
        "                     ELSE 'done'::todostatus END "
        "  FROM protocol_run_items i "
        "  JOIN run_item_map m ON m.old_id = i.id "
        "  JOIN protocol_runs r ON r.id = i.run_id"
    )
    op.execute(
        "UPDATE protocol_run_items SET id = m.new_id "
        "FROM run_item_map m WHERE protocol_run_items.id = m.old_id"
    )

    for column in ("text", "note", "status"):
        op.drop_column("protocol_run_items", column)
    op.execute("DROP TYPE IF EXISTS protocolrunitemstatus")
    op.execute("ALTER TABLE protocol_run_items ALTER COLUMN id DROP DEFAULT")
    op.execute("DROP SEQUENCE IF EXISTS protocol_run_items_id_seq")
    op.create_foreign_key(
        op.f("fk_protocol_run_items_id_items"),
        "protocol_run_items",
        "items",
        ["id"],
        ["id"],
        ondelete="CASCADE",
    )

    connection = op.get_bind()
    counted = connection.execute(
        sa.text("SELECT kind, count(*) FROM items GROUP BY kind ORDER BY kind")
    ).all()
    print(f"items: {dict(counted)}")


def downgrade():
    op.execute(
        "CREATE TYPE protocolrunitemstatus AS ENUM ('pending', 'done', 'sent_to_todo')"
    )
    op.add_column("protocol_run_items", sa.Column("text", sa.Text(), nullable=True))
    op.add_column("protocol_run_items", sa.Column("note", sa.Text(), nullable=True))
    op.add_column(
        "protocol_run_items",
        sa.Column(
            "status",
            sa.Enum("pending", "done", "sent_to_todo", name="protocolrunitemstatus"),
            nullable=True,
        ),
    )
    op.execute(
        "UPDATE protocol_run_items SET text = i.text, note = i.note, "
        "status = CASE WHEN i.status = 'todo' THEN 'pending'::protocolrunitemstatus "
        "              WHEN protocol_run_items.sent_todo_id IS NOT NULL "
        "                   THEN 'sent_to_todo'::protocolrunitemstatus "
        "              ELSE 'done'::protocolrunitemstatus END "
        "FROM items i WHERE i.id = protocol_run_items.id"
    )
    op.alter_column("protocol_run_items", "text", nullable=False)
    op.alter_column("protocol_run_items", "status", nullable=False)
    op.drop_constraint(
        op.f("fk_protocol_run_items_id_items"),
        "protocol_run_items",
        type_="foreignkey",
    )
    op.execute("DELETE FROM items WHERE kind = 'protocol_run_item'")
    op.execute(
        "CREATE SEQUENCE protocol_run_items_id_seq OWNED BY protocol_run_items.id"
    )
    op.execute(
        "SELECT setval('protocol_run_items_id_seq', "
        "coalesce((SELECT max(id) FROM protocol_run_items), 0) + 1, false)"
    )
    op.execute(
        "ALTER TABLE protocol_run_items ALTER COLUMN id "
        "SET DEFAULT nextval('protocol_run_items_id_seq')"
    )
