"""tags become rows

Revision ID: c3a7e5109b6d
Revises: f2c60d8b7a15
Create Date: 2026-09-21

A tag existed only because something spelled it. The vocabulary lived in
four array columns and one comma-separated string, so listing it meant
reading all five and merging in Python, and renaming one meant rewriting
every row that carried it.

The whole vocabulary moves into `tags`, and carrying one becomes a row in
`item_tags`. The hierarchy stays in the name: `einkaufen:supermarkt` is one
tag, because that is what the marker language types and what the tag tree
reads back.

Ingredients are parsed out of their comma-separated string here, the same
way 245e10c85a50 parsed links out of theirs.
"""

import sqlalchemy as sa
from alembic import op

revision = "c3a7e5109b6d"
down_revision = "f2c60d8b7a15"
branch_labels = None
depends_on = None

#: Every table that carried tags, and how.
_ARRAYS = ("todos", "protocols", "protocol_items", "protocol_run_items")


def upgrade():
    connection = op.get_bind()

    op.create_table(
        "tags",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tags")),
        sa.UniqueConstraint("name", name=op.f("uq_tags_name")),
    )
    op.create_table(
        "item_tags",
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["item_id"],
            ["items.id"],
            name=op.f("fk_item_tags_item_id_items"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tag_id"],
            ["tags.id"],
            name=op.f("fk_item_tags_tag_id_tags"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("item_id", "tag_id", name=op.f("pk_item_tags")),
    )
    op.create_index("ix_item_tags_tag_id", "item_tags", ["tag_id"])

    for table in _ARRAYS:
        op.execute(
            "INSERT INTO tags (name) "  # noqa: S608 -- fixed list
            f"SELECT DISTINCT t FROM {table}, unnest(assignees_placeholder) t "
            "ON CONFLICT (name) DO NOTHING".replace("assignees_placeholder", "tags")
        )
        op.execute(
            "INSERT INTO item_tags (item_id, tag_id) "  # noqa: S608
            f"SELECT c.id, tags.id FROM {table} c, unnest(c.tags) t "
            "JOIN tags ON tags.name = t "
            "ON CONFLICT DO NOTHING"
        )

    # Ingredients spelled theirs as one comma-separated string.
    op.execute(
        "INSERT INTO tags (name) "
        "SELECT DISTINCT btrim(t) FROM ingredients, "
        "     unnest(string_to_array(coalesce(tags, ''), ',')) t "
        " WHERE btrim(t) <> '' ON CONFLICT (name) DO NOTHING"
    )
    op.execute(
        "INSERT INTO item_tags (item_id, tag_id) "
        "SELECT i.id, tags.id FROM ingredients i, "
        "     unnest(string_to_array(coalesce(i.tags, ''), ',')) t "
        "JOIN tags ON tags.name = btrim(t) "
        "ON CONFLICT DO NOTHING"
    )

    for table in _ARRAYS:
        op.drop_column(table, "tags")
    op.drop_column("ingredients", "tags")

    vocabulary = connection.execute(sa.text("SELECT count(*) FROM tags")).scalar()
    uses = connection.execute(sa.text("SELECT count(*) FROM item_tags")).scalar()
    print(f"tags: {vocabulary} in the vocabulary, {uses} uses")


def downgrade():
    for table in _ARRAYS:
        op.add_column(
            table,
            sa.Column(
                "tags",
                sa.dialects.postgresql.ARRAY(sa.Text()),
                nullable=False,
                server_default="{}",
            ),
        )
        op.execute(
            f"UPDATE {table} SET tags = coalesce(named.names, '{{}}') FROM ("  # noqa: S608
            "  SELECT it.item_id, array_agg(tags.name ORDER BY tags.name) AS names"
            "    FROM item_tags it JOIN tags ON tags.id = it.tag_id"
            "   GROUP BY it.item_id"
            f") AS named WHERE named.item_id = {table}.id"
        )
    op.add_column("ingredients", sa.Column("tags", sa.Text(), nullable=True))
    op.execute(
        "UPDATE ingredients SET tags = named.names FROM ("
        "  SELECT it.item_id, string_agg(tags.name, ',' ORDER BY tags.name) AS names"
        "    FROM item_tags it JOIN tags ON tags.id = it.tag_id"
        "   GROUP BY it.item_id"
        ") AS named WHERE named.item_id = ingredients.id"
    )
    op.drop_table("item_tags")
    op.drop_table("tags")
