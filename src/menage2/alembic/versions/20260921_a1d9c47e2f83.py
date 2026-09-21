"""the name lives on the principal now

Revision ID: a1d9c47e2f83
Revises: f3c8b2e71d45
Create Date: 2026-09-21

`principals` has carried every user's and team's name since f3c8b2e71d45.
Two copies of a name is one too many -- they can disagree, and only one of
them has the unique index that keeps a team from taking a username -- so
the columns go and the principal is the only place a name is spelled.
"""

import sqlalchemy as sa
from alembic import op

revision = "a1d9c47e2f83"
down_revision = "f3c8b2e71d45"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    stale = connection.execute(
        sa.text(
            "SELECT count(*) FROM principals p LEFT JOIN users u ON u.id = p.user_id "
            "LEFT JOIN teams t ON t.id = p.team_id "
            "WHERE coalesce(u.username, t.name) IS DISTINCT FROM p.name"
        )
    ).scalar()
    if stale:
        raise RuntimeError(
            f"{stale} principals disagree with the name they were copied from; "
            "reconcile before dropping the columns"
        )

    op.drop_column("users", "username")
    op.drop_column("teams", "name")


def downgrade():
    op.add_column("users", sa.Column("username", sa.Text(), nullable=True))
    op.add_column("teams", sa.Column("name", sa.Text(), nullable=True))
    op.execute(
        "UPDATE users SET username = p.name FROM principals p WHERE p.user_id = users.id"
    )
    op.execute(
        "UPDATE teams SET name = p.name FROM principals p WHERE p.team_id = teams.id"
    )
    op.alter_column("users", "username", nullable=False)
    op.alter_column("teams", "name", nullable=False)
    op.create_unique_constraint(op.f("uq_users_username"), "users", ["username"])
    op.create_unique_constraint(op.f("uq_teams_name"), "teams", ["name"])
