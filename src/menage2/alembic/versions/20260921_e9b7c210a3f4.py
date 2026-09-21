"""ingredients join the items family

Revision ID: e9b7c210a3f4
Revises: a8f04e6b12c9
Create Date: 2026-09-21

An ingredient is a thing with a name and some tags, which is what every
other item here is. Joining the family is what lets it carry a photo of
the packaging, a note about which shop, and the same tag picker as
everything else -- none of which it could have while it was its own
little table.

`description` becomes the item's text, and stays readable under its old
name. It is nullable today and `items.text` is not, so empty stands in
for absent; on the production data none are empty.
"""

import sqlalchemy as sa
from alembic import op

revision = "e9b7c210a3f4"
down_revision = "a8f04e6b12c9"
branch_labels = None
depends_on = None

_CHILD = (
    "recipe_ingredients",
    "ingredient_id",
    "fk_recipe_ingredients_ingredient_id_ingredients",
)


def _cascade(on: bool) -> None:
    table, column, name = _CHILD
    op.drop_constraint(name, table, type_="foreignkey")
    op.execute(
        f"ALTER TABLE {table} ADD CONSTRAINT {name} "
        f"FOREIGN KEY ({column}) REFERENCES ingredients(id)"
        + (" ON UPDATE CASCADE" if on else "")
    )


def upgrade():
    connection = op.get_bind()
    unnamed = connection.execute(
        sa.text("SELECT count(*) FROM ingredients WHERE description IS NULL")
    ).scalar()

    op.execute(
        "CREATE TEMP TABLE ingredient_map AS "
        "SELECT id AS old_id, nextval('items_id_seq') AS new_id "
        "FROM ingredients ORDER BY id"
    )
    op.execute(
        "INSERT INTO items (id, kind, text, created_at) "
        "SELECT m.new_id, 'ingredient', coalesce(i.description, ''), now() "
        "  FROM ingredients i JOIN ingredient_map m ON m.old_id = i.id"
    )
    _cascade(True)
    op.execute(
        "UPDATE ingredients SET id = m.new_id "
        "FROM ingredient_map m WHERE ingredients.id = m.old_id"
    )
    _cascade(False)

    op.drop_column("ingredients", "description")
    op.execute("ALTER TABLE ingredients ALTER COLUMN id DROP DEFAULT")
    op.execute("DROP SEQUENCE IF EXISTS ingredients_id_seq")
    op.create_foreign_key(
        op.f("fk_ingredients_id_items"),
        "ingredients",
        "items",
        ["id"],
        ["id"],
        ondelete="CASCADE",
    )

    counted = connection.execute(
        sa.text("SELECT kind, count(*) FROM items GROUP BY kind ORDER BY kind")
    ).all()
    print(f"items: {dict(counted)} ({unnamed} ingredients had no description)")


def downgrade():
    op.add_column("ingredients", sa.Column("description", sa.Text(), nullable=True))
    op.execute(
        "UPDATE ingredients SET description = i.text "
        "FROM items i WHERE i.id = ingredients.id"
    )
    op.drop_constraint(
        op.f("fk_ingredients_id_items"), "ingredients", type_="foreignkey"
    )
    op.execute("DELETE FROM items WHERE kind = 'ingredient'")
    op.execute("CREATE SEQUENCE ingredients_id_seq OWNED BY ingredients.id")
    op.execute(
        "SELECT setval('ingredients_id_seq', "
        "coalesce((SELECT max(id) FROM ingredients), 0) + 1, false)"
    )
    op.execute(
        "ALTER TABLE ingredients ALTER COLUMN id SET DEFAULT nextval('ingredients_id_seq')"
    )
