"""drop the orphaned todos.links column and the unused assignees index

Revision ID: e4a9d13f6b02
Revises: b7e21c04d5a8
Create Date: 2026-09-21

``todos.links`` was replaced by the ``todo_links`` table in 245e10c85a50 and
has been absent from the model ever since, but the column was never dropped.
It is not empty: the production database has twelve rows carrying one, and
six of those were written *after* that migration ran, so for those six the
array is the only record of the link. They are recovered into ``todo_links``
before the column goes.

``ix_todos_assignees`` is a GIN index over the assignees array that nothing
has ever queried -- every assignee rule in ``principals.py`` intersects
Python sets on rows already loaded. It only costs write time.
"""

import re

import sqlalchemy as sa
from alembic import op

revision = "e4a9d13f6b02"
down_revision = "b7e21c04d5a8"
branch_labels = None
depends_on = None

#: The '[label](url)' shape 245e10c85a50 wrote and this reads back.
_PARSE_LINK_RE = re.compile(r"^\[([^\]]*)\]\(([^)\s]+)\)$")


def _parse(link: str) -> tuple[str | None, str]:
    match = _PARSE_LINK_RE.match(link)
    if not match:
        return None, link
    return match.group(1) or None, match.group(2)


def upgrade():
    connection = op.get_bind()

    stranded = connection.execute(
        sa.text("SELECT id, links FROM todos WHERE links IS NOT NULL AND links <> '{}'")
    ).all()

    recovered = 0
    for todo_id, links in stranded:
        known = {
            url
            for (url,) in connection.execute(
                sa.text("SELECT url FROM todo_links WHERE todo_id = :id"),
                {"id": todo_id},
            )
        }
        position = connection.execute(
            sa.text(
                "SELECT coalesce(max(position), -1) + 1 FROM todo_links "
                "WHERE todo_id = :id"
            ),
            {"id": todo_id},
        ).scalar()
        for link in links:
            label, url = _parse(link)
            if url in known:
                continue
            connection.execute(
                sa.text(
                    "INSERT INTO todo_links (todo_id, label, url, position) "
                    "VALUES (:todo_id, :label, :url, :position)"
                ),
                {
                    "todo_id": todo_id,
                    "label": label,
                    "url": url,
                    "position": position,
                },
            )
            known.add(url)
            position += 1
            recovered += 1

    print(f"todos.links: {len(stranded)} rows seen, {recovered} links recovered")

    op.drop_column("todos", "links")
    op.drop_index("ix_todos_assignees", table_name="todos", if_exists=True)


def downgrade():
    """The column comes back empty.

    Which of the array entries were live links and which were fossils of a
    link since deleted is not recorded anywhere, so refilling it would be
    guessing. Everything it held is in ``todo_links``.
    """
    op.add_column(
        "todos",
        sa.Column(
            "links",
            sa.dialects.postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default="{}",
        ),
    )
    op.create_index(
        "ix_todos_assignees", "todos", ["assignees"], postgresql_using="gin"
    )
