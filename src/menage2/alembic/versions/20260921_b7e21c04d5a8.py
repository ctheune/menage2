"""rename constraints to the naming convention

Revision ID: b7e21c04d5a8
Revises: d2b8c5f1a904
Create Date: 2026-09-21

``NAMING_CONVENTION`` has been declared in ``models/meta.py`` since the
project started, but ``Base`` never bound it, so it was never in effect and
every constraint name in the database was typed by hand. Binding it leaves
names disagreeing with what the convention generates, and which ones depends
on when the database was built: Postgres defaults from ``20260428_teams``,
three owner FKs created without the referred-table suffix, and two check
constraints prefixed twice. Reconcile whichever are present, so that from here on
``--autogenerate`` describes the schema truthfully instead of proposing to
drop and recreate constraints on every run.
"""

import sqlalchemy as sa
from alembic import op

revision = "b7e21c04d5a8"
down_revision = "d2b8c5f1a904"
branch_labels = None
depends_on = None

#: (table, name in the database, name the convention generates)
RENAMES = (
    ("teams", "teams_pkey", "pk_teams"),
    ("teams", "teams_name_key", "uq_teams_name"),
    ("team_members", "team_members_pkey", "pk_team_members"),
    ("team_members", "team_members_team_id_fkey", "fk_team_members_team_id_teams"),
    ("team_members", "team_members_user_id_fkey", "fk_team_members_user_id_users"),
    ("todos", "fk_todos_owner_id", "fk_todos_owner_id_users"),
    ("protocols", "fk_protocols_owner_id", "fk_protocols_owner_id_users"),
    (
        "protocol_runs",
        "fk_protocol_runs_owner_id",
        "fk_protocol_runs_owner_id_users",
    ),
    # The `ck_` template is the only one interpolating the constraint name,
    # so a name already spelled in full came back out prefixed twice. These
    # two exist in databases built while the convention was briefly in
    # effect; the migrations that make them now use `op.f`.
    (
        "team_members",
        "ck_team_members_ck_team_members_role",
        "ck_team_members_role",
    ),
    ("absences", "ck_absences_ck_absences_dates", "ck_absences_dates"),
)


def _rename(table: str, old: str, new: str) -> None:
    """Rename `old` to `new`, unless it was never called `old` here.

    Binding the convention changes what the *older* migrations produce: a
    database built from scratch today gets `pk_teams` out of
    `20260428_teams`\'s bare `sa.PrimaryKeyConstraint("id")`, while the
    databases built before the binding carry Postgres\' `teams_pkey`. Both
    arrive at the same place; only one of them has anything to rename.
    """
    exists = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT 1 FROM pg_constraint WHERE conname = :name "
                "AND conrelid = CAST(:table AS regclass)"
            ),
            {"name": old, "table": table},
        )
        .scalar()
    )
    if exists:
        op.execute(f'ALTER TABLE {table} RENAME CONSTRAINT "{old}" TO "{new}"')


def upgrade():
    for table, old, new in RENAMES:
        _rename(table, old, new)


def downgrade():
    for table, old, new in RENAMES:
        _rename(table, new, old)
