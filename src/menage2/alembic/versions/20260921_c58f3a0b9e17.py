"""split assignee values that are really two names

Revision ID: c58f3a0b9e17
Revises: a1d9c47e2f83
Create Date: 2026-09-21

Production carries 211 assignees spelled "eltern @matti" or "matti @eltern"
-- one pill holding two names, posted by the assignee field's Enter
fallback, which appends whatever was typed rather than what was picked.
They address nobody, and they cannot be turned into a reference to a
principal, so they are split into the two names they were always meant to
be before that reference is what assignees are.

Anything that still does not name a principal afterwards is reported.
"""

import sqlalchemy as sa
from alembic import op

revision = "c58f3a0b9e17"
down_revision = "a1d9c47e2f83"
branch_labels = None
depends_on = None

#: Every table carrying assignees as an array.
_CARRIERS = ("todos", "protocols", "protocol_items", "protocol_run_items")


def upgrade():
    connection = op.get_bind()
    known = {
        name for (name,) in connection.execute(sa.text("SELECT name FROM principals"))
    }

    split = 0
    for table in _CARRIERS:
        rows = connection.execute(
            sa.text(
                f"SELECT id, assignees FROM {table} "  # noqa: S608 -- fixed list
                "WHERE EXISTS (SELECT 1 FROM unnest(assignees) a "
                "WHERE a LIKE '% %' OR a LIKE '%@%')"
            )
        ).all()
        for row_id, assignees in rows:
            names = sorted(
                {
                    word.lstrip("@")
                    for entry in assignees
                    for word in entry.split()
                    if word.strip("@")
                }
            )
            connection.execute(
                sa.text(
                    f"UPDATE {table} SET assignees = :names WHERE id = :id"  # noqa: S608
                ),
                {"names": names, "id": row_id},
            )
            split += 1

    unknown: dict[str, int] = {}
    for table in _CARRIERS:
        for name, count in connection.execute(
            sa.text(
                f"SELECT a, count(*) FROM {table}, unnest(assignees) a "  # noqa: S608
                "GROUP BY a"
            )
        ):
            if name not in known:
                unknown[name] = unknown.get(name, 0) + count

    print(f"assignees: {split} rows split")
    if unknown:
        print(f"assignees: naming no principal: {unknown}")


def downgrade():
    """Nothing to put back.

    Which two names a single "eltern @matti" had been is exactly what the
    split recorded; rejoining them would be inventing the mistake again.
    """
