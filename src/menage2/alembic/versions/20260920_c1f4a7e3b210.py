"""write recurrence chains forwards

A predecessor pointer cannot keep a chain straight: two requests spawning
from the same item each insert their own row, nothing collides, and the
chain becomes a tree. Written forwards there is one column per item to hold
a successor, and UNIQUE stops two items claiming the same one.

Where the old data already forked, the newest child wins, and the branches
that lose are removed: they are copies nobody asked for, and left alone each
one goes on repeating by itself. A todo that also stands in for a protocol
run is kept — it is that run's only todo — and counted separately in what
the upgrade prints.

Revision ID: c1f4a7e3b210
Revises: a9df32556402
Create Date: 2026-09-20 11:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "c1f4a7e3b210"
down_revision = "a9df32556402"
branch_labels = None
depends_on = None


#: Every todo that carries a rule but is not on the chain its newest instance
#: is on. Ids only go up, so the newest is the tip of the chain the rule is
#: actually up to, and walking back from it along the successor pointer gives
#: the rest of that chain. Everything else with the same rule is a branch.
#: Three schema facts, named rather than spelled, so the tests can run this
#: very SQL against the schema of the day rather than a copy of it. All three
#: are `todos` columns when this migration runs, which is what it was written
#: against; each has moved since. `rules` holds `recurrence_id`, `rows` is
#: what a todo is deleted from, and `runs` says which todos stand for a
#: protocol run and must be kept where they are.
_BRANCHES_SQL = """
WITH RECURSIVE tips AS (
        SELECT recurrence_id, MAX(id) AS id
          FROM {rules}
         WHERE recurrence_id IS NOT NULL
      GROUP BY recurrence_id
), chain AS (
        SELECT todos.id
          FROM todos JOIN tips ON todos.id = tips.id
         UNION ALL
        SELECT earlier.id
          FROM todos AS earlier JOIN chain ON earlier.recurred_into_id = chain.id
), branches AS (
        SELECT todos.id,
               (todos.id IN ({runs})) AS is_run
          FROM todos JOIN {rules} AS rule ON rule.id = todos.id
         WHERE rule.recurrence_id IS NOT NULL
           AND todos.id NOT IN (SELECT id FROM chain)
)
"""

_RUNS = "SELECT id FROM todos WHERE protocol_run_id IS NOT NULL"

_BRANCHES = _BRANCHES_SQL.format(rules="todos", runs=_RUNS)

_RUN_TODOS_SQL = "SELECT COUNT(*) FROM branches WHERE is_run"

#: Nothing may still point at a row that is about to go, including a kept
#: item whose successor was on a branch.
_UNLINK_SQL = """
UPDATE todos
   SET recurred_into_id = NULL
 WHERE recurred_into_id IN (SELECT id FROM branches WHERE NOT is_run)
"""

_DELETE_SQL = """
DELETE FROM {rows}
 WHERE id IN (SELECT id FROM branches WHERE NOT is_run)
"""


def prune_branches(
    bind, rules: str = "todos", rows: str = "todos", runs: str = _RUNS
) -> int:
    """Remove the branches, returning how many todos went. Used by the test.

    See `_BRANCHES_SQL` for what `rules` and `rows` name. The defaults are
    the schema this migration runs against.
    """
    branches = _BRANCHES_SQL.format(rules=rules, runs=runs)
    bind.execute(sa.text(branches + _UNLINK_SQL))
    return bind.execute(sa.text(branches + _DELETE_SQL.format(rows=rows))).rowcount


def upgrade():
    op.add_column("todos", sa.Column("recurred_into_id", sa.Integer(), nullable=True))

    # One successor per parent: where several children claim the same parent,
    # keep the newest and let the others fall out of the chain.
    op.execute(
        """
        UPDATE todos AS parent
           SET recurred_into_id = newest.child_id
          FROM (
                SELECT recurred_from_id AS parent_id, MAX(id) AS child_id
                  FROM todos
                 WHERE recurred_from_id IS NOT NULL
              GROUP BY recurred_from_id
               ) AS newest
         WHERE parent.id = newest.parent_id
        """
    )

    op.create_unique_constraint(
        "uq_todos_recurred_into_id", "todos", ["recurred_into_id"]
    )
    op.create_foreign_key(
        "fk_todos_recurred_into_id_todos",
        "todos",
        "todos",
        ["recurred_into_id"],
        ["id"],
    )

    # The old column goes before anything is deleted. Every branch is still
    # pointed at by whatever spawned it, and that foreign key would refuse
    # the delete — the successor links are the only ones left to clear.
    op.drop_column("todos", "recurred_from_id")

    bind = op.get_bind()
    kept_for_runs = bind.execute(sa.text(_BRANCHES + _RUN_TODOS_SQL)).scalar()
    bind.execute(sa.text(_BRANCHES + _UNLINK_SQL))
    removed = bind.execute(
        sa.text(_BRANCHES + _DELETE_SQL.format(rows="todos"))
    ).rowcount
    print(
        f"Recurrence branches: removed {removed} todo(s)"
        + (
            f", kept {kept_for_runs} belonging to protocol runs"
            if kept_for_runs
            else ""
        )
        + "."
    )


def downgrade():
    op.add_column("todos", sa.Column("recurred_from_id", sa.Integer(), nullable=True))
    op.execute(
        """
        UPDATE todos AS child
           SET recurred_from_id = parent.id
          FROM todos AS parent
         WHERE parent.recurred_into_id = child.id
        """
    )
    op.create_foreign_key(
        "fk_todos_recurred_from_id_todos",
        "todos",
        "todos",
        ["recurred_from_id"],
        ["id"],
    )
    op.drop_constraint("uq_todos_recurred_into_id", "todos", type_="unique")
    op.drop_column("todos", "recurred_into_id")
