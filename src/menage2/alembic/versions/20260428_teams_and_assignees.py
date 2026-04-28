"""teams and assignees

Revision ID: 20260428_teams
Revises: 99632bc17522
Create Date: 2026-04-28 00:00:00.000000

Adds Team/TeamMember tables, owner_id + assignees to todos/protocols,
and assignees to protocol_items/protocol_run_items/protocol_runs.
Migrates existing todos to be owned by the first admin user.
"""

import sqlalchemy as sa
from alembic import op

import menage2.models.todo  # noqa: F401 — needed for TagSet type alias

revision = "20260428_teams"
down_revision = "99632bc17522"
branch_labels = None
depends_on = None


def upgrade():
    # --- Teams ---
    op.create_table(
        "teams",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "team_members",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("team_id", "user_id", name="uq_team_members_team_user"),
        sa.CheckConstraint(
            "role IN ('assignee', 'supervisor')", name="ck_team_members_role"
        ),
    )

    # --- Todos ---
    op.add_column("todos", sa.Column("owner_id", sa.Integer(), nullable=True))
    op.add_column(
        "todos",
        sa.Column(
            "assignees",
            menage2.models.todo.TagSet(),
            nullable=False,
            server_default="{}",
        ),
    )
    op.create_foreign_key("fk_todos_owner_id", "todos", "users", ["owner_id"], ["id"])
    op.create_index("ix_todos_owner_id", "todos", ["owner_id"])
    op.create_index(
        "ix_todos_assignees", "todos", ["assignees"], postgresql_using="gin"
    )

    # --- Protocols ---
    op.add_column("protocols", sa.Column("owner_id", sa.Integer(), nullable=True))
    op.add_column(
        "protocols",
        sa.Column(
            "assignees",
            menage2.models.todo.TagSet(),
            nullable=False,
            server_default="{}",
        ),
    )
    op.create_foreign_key(
        "fk_protocols_owner_id", "protocols", "users", ["owner_id"], ["id"]
    )

    # --- Protocol items ---
    op.add_column(
        "protocol_items",
        sa.Column(
            "assignees",
            menage2.models.todo.TagSet(),
            nullable=False,
            server_default="{}",
        ),
    )

    # --- Protocol runs ---
    op.add_column("protocol_runs", sa.Column("owner_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_protocol_runs_owner_id",
        "protocol_runs",
        "users",
        ["owner_id"],
        ["id"],
    )

    # --- Protocol run items ---
    op.add_column(
        "protocol_run_items",
        sa.Column(
            "assignees",
            menage2.models.todo.TagSet(),
            nullable=False,
            server_default="{}",
        ),
    )

    # --- Data migration: assign legacy todos to first admin ---
    op.execute(
        """
        UPDATE todos
        SET owner_id = (
            SELECT id FROM users
            WHERE is_admin = true
            ORDER BY id
            LIMIT 1
        )
        WHERE owner_id IS NULL
        """
    )


def downgrade():
    pass
