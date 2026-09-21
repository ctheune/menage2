"""checklists and their lines join the items family

Revision ID: d71b5c93a4e8
Revises: b64e8a0c5d31
Create Date: 2026-09-21

`protocols` and `protocol_items` give up title/text, note, created_at,
owner and recurrence to `items` and keep only what is theirs: a protocol's
archived_at, an item's protocol and position.

Both are renumbered from the shared sequence, because their ids overlap
with the todos already in `items`. Almost nothing points at them --
protocol_items.protocol_id and protocol_runs.protocol_id for a protocol,
nothing at all for an item -- and those follow through ON UPDATE CASCADE,
added for the length of the migration.

A protocol item has no creation time of its own, so it takes its
protocol's: it cannot have existed before the protocol did, and that is a
better answer than the moment this migration happened to run.
"""

import sqlalchemy as sa
from alembic import op

revision = "d71b5c93a4e8"
down_revision = "b64e8a0c5d31"
branch_labels = None
depends_on = None

#: (child table, column) that follow a protocol's id.
_PROTOCOL_CHILDREN = (
    ("protocol_items", "protocol_id", "fk_protocol_items_protocol_id_protocols"),
    ("protocol_runs", "protocol_id", "fk_protocol_runs_protocol_id_protocols"),
)


def _cascade(on: bool) -> None:
    for table, column, name in _PROTOCOL_CHILDREN:
        op.drop_constraint(name, table, type_="foreignkey")
        op.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT {name} "
            f"FOREIGN KEY ({column}) REFERENCES protocols(id)"
            + (" ON UPDATE CASCADE" if on else "")
        )


def upgrade():
    connection = op.get_bind()

    # --- protocols ---
    op.execute(
        "CREATE TEMP TABLE protocol_map AS "
        "SELECT id AS old_id, nextval('items_id_seq') AS new_id "
        "FROM protocols ORDER BY id"
    )
    op.execute(
        "INSERT INTO items (id, kind, text, note, created_at, owner_id, recurrence_id) "
        "SELECT m.new_id, 'protocol', p.title, p.note, p.created_at, p.owner_id, "
        "       p.recurrence_id "
        "  FROM protocols p JOIN protocol_map m ON m.old_id = p.id"
    )
    _cascade(True)
    op.execute(
        "UPDATE protocols SET id = m.new_id FROM protocol_map m WHERE id = m.old_id"
    )
    _cascade(False)

    for column in ("title", "note", "created_at", "owner_id", "recurrence_id"):
        op.drop_column("protocols", column)
    op.execute("ALTER TABLE protocols ALTER COLUMN id DROP DEFAULT")
    op.execute("DROP SEQUENCE IF EXISTS protocols_id_seq")
    op.create_foreign_key(
        op.f("fk_protocols_id_items"),
        "protocols",
        "items",
        ["id"],
        ["id"],
        ondelete="CASCADE",
    )

    # A protocol has always had to have an owner; the base column is
    # nullable because a checklist line does not.
    op.create_check_constraint(
        op.f("ck_items_protocol_has_owner"),
        "items",
        "kind <> 'protocol' OR owner_id IS NOT NULL",
    )

    # --- protocol items ---
    op.execute(
        "CREATE TEMP TABLE protocol_item_map AS "
        "SELECT id AS old_id, nextval('items_id_seq') AS new_id "
        "FROM protocol_items ORDER BY id"
    )
    op.execute(
        "INSERT INTO items (id, kind, text, note, created_at) "
        "SELECT m.new_id, 'protocol_item', i.text, i.note, p.created_at "
        "  FROM protocol_items i "
        "  JOIN protocol_item_map m ON m.old_id = i.id "
        "  JOIN items p ON p.id = i.protocol_id"
    )
    op.execute(
        "UPDATE protocol_items SET id = m.new_id "
        "FROM protocol_item_map m WHERE protocol_items.id = m.old_id"
    )
    for column in ("text", "note"):
        op.drop_column("protocol_items", column)
    op.execute("ALTER TABLE protocol_items ALTER COLUMN id DROP DEFAULT")
    op.execute("DROP SEQUENCE IF EXISTS protocol_items_id_seq")
    op.create_foreign_key(
        op.f("fk_protocol_items_id_items"),
        "protocol_items",
        "items",
        ["id"],
        ["id"],
        ondelete="CASCADE",
    )

    counted = connection.execute(
        sa.text("SELECT kind, count(*) FROM items GROUP BY kind ORDER BY kind")
    ).all()
    print(f"items: {dict(counted)}")


def downgrade():
    """The columns come back; the new ids stay.

    Renumbering back would mean knowing which id each row had before, and
    the map was temporary. Nothing outside the database points at a
    protocol by id, so a protocol numbered 4300 is only surprising to read.
    """
    op.drop_constraint(op.f("ck_items_protocol_has_owner"), "items", type_="check")

    op.add_column("protocol_items", sa.Column("text", sa.Text(), nullable=True))
    op.add_column("protocol_items", sa.Column("note", sa.Text(), nullable=True))
    op.execute(
        "UPDATE protocol_items SET text = i.text, note = i.note "
        "FROM items i WHERE i.id = protocol_items.id"
    )
    op.alter_column("protocol_items", "text", nullable=False)
    op.drop_constraint(
        op.f("fk_protocol_items_id_items"), "protocol_items", type_="foreignkey"
    )

    op.add_column("protocols", sa.Column("title", sa.Text(), nullable=True))
    op.add_column("protocols", sa.Column("note", sa.Text(), nullable=True))
    op.add_column(
        "protocols", sa.Column("created_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("protocols", sa.Column("owner_id", sa.Integer(), nullable=True))
    op.add_column("protocols", sa.Column("recurrence_id", sa.Integer(), nullable=True))
    op.execute(
        "UPDATE protocols SET title = i.text, note = i.note, "
        "created_at = i.created_at, owner_id = i.owner_id, "
        "recurrence_id = i.recurrence_id "
        "FROM items i WHERE i.id = protocols.id"
    )
    op.alter_column("protocols", "title", nullable=False)
    op.alter_column("protocols", "created_at", nullable=False)
    op.alter_column("protocols", "owner_id", nullable=False)
    op.drop_constraint(op.f("fk_protocols_id_items"), "protocols", type_="foreignkey")
    op.create_foreign_key(
        op.f("fk_protocols_owner_id_users"), "protocols", "users", ["owner_id"], ["id"]
    )
    op.create_foreign_key(
        op.f("fk_protocols_recurrence_id_recurrence_rules"),
        "protocols",
        "recurrence_rules",
        ["recurrence_id"],
        ["id"],
    )

    op.execute("DELETE FROM items WHERE kind IN ('protocol', 'protocol_item')")

    for table in ("protocols", "protocol_items"):
        op.execute(f"CREATE SEQUENCE {table}_id_seq OWNED BY {table}.id")
        op.execute(
            f"SELECT setval('{table}_id_seq', "
            f"coalesce((SELECT max(id) FROM {table}), 0) + 1, false)"
        )
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN id SET DEFAULT nextval('{table}_id_seq')"
        )
