"""give users and teams a shared namespace of principals

Revision ID: f3c8b2e71d45
Revises: e4a9d13f6b02
Create Date: 2026-09-21

`@matti` and `@eltern` are written the same way and mean a user and a team,
so the two have always shared one namespace -- enforced by two admin views
remembering to look, which is not enforcement. One row per user and per
team, one unique index over the name, and the database says it instead.
"""

import sqlalchemy as sa
from alembic import op

revision = "f3c8b2e71d45"
down_revision = "e4a9d13f6b02"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "principals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("team_id", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "(kind = 'user' AND user_id IS NOT NULL AND team_id IS NULL)"
            " OR (kind = 'team' AND team_id IS NOT NULL AND user_id IS NULL)",
            name=op.f("ck_principals_owner"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_principals_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["team_id"],
            ["teams.id"],
            name=op.f("fk_principals_team_id_teams"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_principals")),
        sa.UniqueConstraint("name", name=op.f("uq_principals_name")),
        sa.UniqueConstraint("user_id", name=op.f("uq_principals_user_id")),
        sa.UniqueConstraint("team_id", name=op.f("uq_principals_team_id")),
    )

    op.execute(
        "INSERT INTO principals (name, kind, user_id) "
        "SELECT username, 'user', id FROM users"
    )
    op.execute(
        "INSERT INTO principals (name, kind, team_id) "
        "SELECT name, 'team', id FROM teams"
    )

    connection = op.get_bind()
    counted = connection.execute(
        sa.text("SELECT kind, count(*) FROM principals GROUP BY kind ORDER BY kind")
    ).all()
    print(f"principals: {dict(counted)}")


def downgrade():
    op.drop_table("principals")
