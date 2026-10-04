"""the items table, with todos as its first subtype

Revision ID: b64e8a0c5d31
Revises: c58f3a0b9e17
Create Date: 2026-09-21

Todos, checklists, checklist items and ingredients all carry text, a note,
tags and assignees, each in their own columns -- which is why attachments
exist on todos and nowhere else. `items` owns what they share; each kind
becomes a joined-table subtype whose own table keeps only what is its own.

Todos keep their ids. They are the most pointed-at thing in the schema
(todo_links, todo_attachments, protocol_run_items.sent_todo_id,
todos.recurred_into_id, todos.protocol_run_id) and they are in every URL,
so `items` is seeded from them one id at a time and the shared sequence
starts after the last of them. The other subtypes, which almost nothing
points at, draw new ids when their turn comes.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b64e8a0c5d31"
down_revision = "c58f3a0b9e17"
branch_labels = None
depends_on = None

#: Columns that stop being a todo's and become an item's.
_MOVED = (
    "text",
    "note",
    "created_at",
    "owner_id",
    "due_date",
    "status",
    "done_at",
    "on_hold_at",
    "recurrence_id",
)

_STATUS = postgresql.ENUM(
    "todo", "done", "on_hold", name="todostatus", create_type=False
)


def upgrade():
    op.create_table(
        "items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("status", _STATUS, nullable=True),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("on_hold_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recurrence_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name=op.f("fk_items_owner_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["recurrence_id"],
            ["recurrence_rules.id"],
            name=op.f("fk_items_recurrence_id_recurrence_rules"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_items")),
    )
    op.create_index("ix_items_kind", "items", ["kind"])
    op.create_index("ix_items_owner_id", "items", ["owner_id"])
    op.create_index("ix_items_recurrence_id", "items", ["recurrence_id"])
    op.create_index(
        "ix_items_status_due",
        "items",
        ["status", "due_date"],
        postgresql_where=sa.text("status IS NOT NULL"),
    )

    columns = ", ".join(_MOVED)
    op.execute(
        f"INSERT INTO items (id, kind, {columns}) SELECT id, 'todo', {columns} FROM todos"
    )
    op.execute(
        "SELECT setval('items_id_seq', coalesce((SELECT max(id) FROM items), 0) + 1, false)"
    )

    # The subtype no longer numbers itself; the id comes from `items`.
    op.execute("ALTER TABLE todos ALTER COLUMN id DROP DEFAULT")
    op.execute("DROP SEQUENCE IF EXISTS todos_id_seq")
    op.create_foreign_key(
        op.f("fk_todos_id_items"), "todos", "items", ["id"], ["id"], ondelete="CASCADE"
    )

    for column in _MOVED:
        op.drop_column("todos", column)

    connection = op.get_bind()
    moved = connection.execute(sa.text("SELECT count(*) FROM items")).scalar()
    print(f"items: {moved} todos are now items")


def downgrade():
    op.add_column("todos", sa.Column("text", sa.Text(), nullable=True))
    op.add_column("todos", sa.Column("note", sa.Text(), nullable=True))
    op.add_column(
        "todos", sa.Column("created_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("todos", sa.Column("owner_id", sa.Integer(), nullable=True))
    op.add_column("todos", sa.Column("due_date", sa.Date(), nullable=True))
    op.add_column("todos", sa.Column("status", _STATUS, nullable=True))
    op.add_column(
        "todos", sa.Column("done_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "todos", sa.Column("on_hold_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("todos", sa.Column("recurrence_id", sa.Integer(), nullable=True))

    assignments = ", ".join(f"{c} = i.{c}" for c in _MOVED)
    op.execute(f"UPDATE todos SET {assignments} FROM items i WHERE i.id = todos.id")

    op.alter_column("todos", "text", nullable=False)
    op.alter_column("todos", "created_at", nullable=False)
    op.alter_column("todos", "status", nullable=False)

    op.drop_constraint(op.f("fk_todos_id_items"), "todos", type_="foreignkey")
    op.create_foreign_key(
        op.f("fk_todos_owner_id_users"), "todos", "users", ["owner_id"], ["id"]
    )
    op.create_foreign_key(
        op.f("fk_todos_recurrence_id_recurrence_rules"),
        "todos",
        "recurrence_rules",
        ["recurrence_id"],
        ["id"],
    )
    op.create_index("ix_todos_due_date", "todos", ["due_date"])
    op.create_index("ix_todos_owner_id", "todos", ["owner_id"])
    op.create_index("ix_todos_recurrence_id", "todos", ["recurrence_id"])
    op.execute("CREATE SEQUENCE todos_id_seq OWNED BY todos.id")
    op.execute(
        "SELECT setval('todos_id_seq', coalesce((SELECT max(id) FROM todos), 0) + 1, false)"
    )
    op.execute("ALTER TABLE todos ALTER COLUMN id SET DEFAULT nextval('todos_id_seq')")

    op.drop_table("items")
