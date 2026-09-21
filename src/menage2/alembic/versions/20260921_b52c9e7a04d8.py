"""links and attachments belong to items, not only to todos

Revision ID: b52c9e7a04d8
Revises: d0fa81b4e739
Create Date: 2026-09-21

A photo could be attached to a todo and to nothing else, so an ingredient
could not carry a picture of the packaging and a checklist line could not
carry a link. Both tables move to `items.id`.

Nothing is rewritten: a todo's id has been its item's id since
b64e8a0c5d31, so all 222 links and 41 attachments already point at the
right number. This is a rename and a foreign key.
"""

from alembic import op

revision = "b52c9e7a04d8"
down_revision = "d0fa81b4e739"
branch_labels = None
depends_on = None

#: (old table, new table, old index on the owning column)
_TABLES = (
    ("todo_links", "item_links", "ix_todo_links_todo_id"),
    ("todo_attachments", "item_attachments", "ix_todo_attachments_todo_id"),
)


def upgrade():
    for old, new, index in _TABLES:
        op.rename_table(old, new)
        op.alter_column(new, "todo_id", new_column_name="item_id")
        op.execute(f"ALTER INDEX {index} RENAME TO ix_{new}_item_id")
        op.execute(f'ALTER TABLE {new} RENAME CONSTRAINT "pk_{old}" TO "pk_{new}"')
        op.drop_constraint(f"fk_{old}_todo_id_todos", new, type_="foreignkey")
        op.create_foreign_key(
            op.f(f"fk_{new}_item_id_items"),
            new,
            "items",
            ["item_id"],
            ["id"],
            ondelete="CASCADE",
        )
    op.execute(
        "ALTER INDEX ix_todo_attachments_uuid RENAME TO ix_item_attachments_uuid"
    )


def downgrade():
    op.execute(
        "ALTER INDEX ix_item_attachments_uuid RENAME TO ix_todo_attachments_uuid"
    )
    for old, new, index in _TABLES:
        op.drop_constraint(op.f(f"fk_{new}_item_id_items"), new, type_="foreignkey")
        op.execute(f'ALTER TABLE {new} RENAME CONSTRAINT "pk_{new}" TO "pk_{old}"')
        op.execute(f"ALTER INDEX ix_{new}_item_id RENAME TO {index}")
        op.alter_column(new, "item_id", new_column_name="todo_id")
        op.rename_table(new, old)
        op.create_foreign_key(
            f"fk_{old}_todo_id_todos",
            old,
            "todos",
            ["todo_id"],
            ["id"],
            ondelete="CASCADE",
        )
