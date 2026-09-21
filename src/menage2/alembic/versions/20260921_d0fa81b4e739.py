"""assignees become references to principals

Revision ID: d0fa81b4e739
Revises: c3a7e5109b6d
Create Date: 2026-09-21

`assignees` was an array of strings, so a name that addressed nobody stored
as happily as one that addressed somebody -- which is how 211 values
spelled "eltern @matti" came to be there, cleaned up in c58f3a0b9e17. An
assignment becomes a row pointing at a principal, and the foreign key is
what stops the next one.

Anything still naming nobody by now would have to be dropped, so the
migration refuses to run instead and says which names it means.
"""

import sqlalchemy as sa
from alembic import op

revision = "d0fa81b4e739"
down_revision = "c3a7e5109b6d"
branch_labels = None
depends_on = None

_ARRAYS = ("todos", "protocols", "protocol_items", "protocol_run_items")


def upgrade():
    connection = op.get_bind()

    unknown: dict[str, int] = {}
    for table in _ARRAYS:
        for name, count in connection.execute(
            sa.text(
                f"SELECT a, count(*) FROM {table}, unnest(assignees) a "  # noqa: S608
                " WHERE NOT EXISTS (SELECT 1 FROM principals p WHERE p.name = a) "
                " GROUP BY a"
            )
        ):
            unknown[name] = unknown.get(name, 0) + count
    if unknown:
        raise RuntimeError(
            f"these assignees name no user or team: {unknown}; "
            "rename or remove them before they become references"
        )

    op.create_table(
        "item_assignees",
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("principal_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["item_id"],
            ["items.id"],
            name=op.f("fk_item_assignees_item_id_items"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["principal_id"],
            ["principals.id"],
            name=op.f("fk_item_assignees_principal_id_principals"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "item_id", "principal_id", name=op.f("pk_item_assignees")
        ),
    )
    op.create_index(
        "ix_item_assignees_principal_id", "item_assignees", ["principal_id"]
    )

    for table in _ARRAYS:
        op.execute(
            "INSERT INTO item_assignees (item_id, principal_id) "  # noqa: S608
            f"SELECT c.id, p.id FROM {table} c, unnest(c.assignees) a "
            "JOIN principals p ON p.name = a "
            "ON CONFLICT DO NOTHING"
        )
        op.drop_column(table, "assignees")

    written = connection.execute(
        sa.text("SELECT count(*) FROM item_assignees")
    ).scalar()
    print(f"assignees: {written} assignments, all naming a principal")


def downgrade():
    for table in _ARRAYS:
        op.add_column(
            table,
            sa.Column(
                "assignees",
                sa.dialects.postgresql.ARRAY(sa.Text()),
                nullable=False,
                server_default="{}",
            ),
        )
        op.execute(
            f"UPDATE {table} SET assignees = coalesce(named.names, '{{}}') FROM ("  # noqa: S608
            "  SELECT ia.item_id, array_agg(p.name ORDER BY p.name) AS names"
            "    FROM item_assignees ia JOIN principals p ON p.id = ia.principal_id"
            "   GROUP BY ia.item_id"
            f") AS named WHERE named.item_id = {table}.id"
        )
    op.drop_table("item_assignees")
