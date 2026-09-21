"""a run and the task that says it is due become one thing

Revision ID: f2c60d8b7a15
Revises: e9b7c210a3f4
Create Date: 2026-09-21

A ProtocolRun and the Todo paired with it 1-to-1 were the same thing
written twice: the todo held the run's text, tags, due date and status,
ticking the todo closed the run, and closing the run ticked the todo. A run
is a todo that has a checklist behind it.

The run takes over its todo's id, so nothing that pointed at the todo has
to move -- not its links, not its attachments, not a run item that was sent
to it. No column is copied either: the item row already holds everything
the run needs, because it was the todo's. `spawned_at` is `created_at` and
`closed_at` is `done_at`; both are checked against the rows before they go.

It can be undone. Which items were runs is exactly what `kind` says, and
the three dropped columns are all copies of the item's own -- so the
downgrade can hand each run a fresh id, point a todo back at it and put
the copies back. Only the run's original id is not recovered, and nothing
outside the database ever named one.
"""

import sqlalchemy as sa
from alembic import op

revision = "f2c60d8b7a15"
down_revision = "e9b7c210a3f4"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()

    runs = connection.execute(sa.text("SELECT count(*) FROM protocol_runs")).scalar()
    paired = connection.execute(
        sa.text("SELECT count(*) FROM todos WHERE protocol_run_id IS NOT NULL")
    ).scalar()
    if runs != paired:
        raise RuntimeError(
            f"{runs} runs but {paired} todos point at one; every run must have "
            "exactly one todo to become before this can go ahead"
        )

    # The two dates the run keeps duplicating must actually agree, or folding
    # them into the item's would quietly change what happened.
    disagreeing = connection.execute(
        sa.text(
            "SELECT count(*) FROM protocol_runs r "
            "  JOIN todos t ON t.protocol_run_id = r.id "
            "  JOIN items i ON i.id = t.id "
            " WHERE r.spawned_at IS DISTINCT FROM i.created_at "
            "    OR (r.closed_at IS NULL) <> (i.done_at IS NULL)"
        )
    ).scalar()
    if disagreeing:
        raise RuntimeError(
            f"{disagreeing} runs disagree with their todo about when they were "
            "spawned or closed; reconcile before folding them together"
        )

    # Nothing may point at a run-todo along the recurrence chain: a run's next
    # instance comes from the protocol's rule, not from the chain.
    chained = connection.execute(
        sa.text(
            "SELECT count(*) FROM todos "
            " WHERE recurred_into_id IN "
            "       (SELECT id FROM todos WHERE protocol_run_id IS NOT NULL)"
        )
    ).scalar()
    if chained:
        raise RuntimeError(f"{chained} todos name a run-todo as their successor")

    op.execute(
        "CREATE TEMP TABLE run_map AS "
        "SELECT r.id AS old_id, t.id AS new_id "
        "  FROM protocol_runs r JOIN todos t ON t.protocol_run_id = r.id"
    )

    op.drop_constraint(
        "fk_protocol_run_items_run_id_protocol_runs",
        "protocol_run_items",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_todos_protocol_run_id_protocol_runs", "todos", type_="foreignkey"
    )

    op.execute(
        "UPDATE protocol_runs SET id = m.new_id FROM run_map m WHERE id = m.old_id"
    )
    op.execute(
        "UPDATE protocol_run_items SET run_id = m.new_id "
        "FROM run_map m WHERE protocol_run_items.run_id = m.old_id"
    )
    op.execute(
        "UPDATE items SET kind = 'protocol_run' WHERE id IN (SELECT new_id FROM run_map)"
    )

    op.create_foreign_key(
        op.f("fk_protocol_run_items_run_id_protocol_runs"),
        "protocol_run_items",
        "protocol_runs",
        ["run_id"],
        ["id"],
    )
    op.drop_column("todos", "protocol_run_id")

    for column in ("spawned_at", "closed_at", "owner_id"):
        op.drop_column("protocol_runs", column)
    op.execute("ALTER TABLE protocol_runs ALTER COLUMN id DROP DEFAULT")
    op.execute("DROP SEQUENCE IF EXISTS protocol_runs_id_seq")
    op.create_foreign_key(
        op.f("fk_protocol_runs_id_todos"),
        "protocol_runs",
        "todos",
        ["id"],
        ["id"],
        ondelete="CASCADE",
    )

    counted = connection.execute(
        sa.text("SELECT kind, count(*) FROM items GROUP BY kind ORDER BY kind")
    ).all()
    print(f"items: {dict(counted)}")


def downgrade():
    op.add_column("todos", sa.Column("protocol_run_id", sa.Integer(), nullable=True))
    op.add_column("protocol_runs", sa.Column("spawned_at", sa.DateTime(timezone=True)))
    op.add_column("protocol_runs", sa.Column("closed_at", sa.DateTime(timezone=True)))
    op.add_column("protocol_runs", sa.Column("owner_id", sa.Integer()))

    op.drop_constraint(
        op.f("fk_protocol_runs_id_todos"), "protocol_runs", type_="foreignkey"
    )
    op.drop_constraint(
        op.f("fk_protocol_run_items_run_id_protocol_runs"),
        "protocol_run_items",
        type_="foreignkey",
    )

    op.execute("CREATE SEQUENCE protocol_runs_id_seq OWNED BY protocol_runs.id")
    op.execute(
        "CREATE TEMP TABLE unmerge AS "
        "SELECT id AS item_id, nextval('protocol_runs_id_seq') AS run_id "
        "FROM protocol_runs ORDER BY id"
    )
    op.execute(
        "UPDATE protocol_runs SET spawned_at = i.created_at, closed_at = i.done_at, "
        "owner_id = i.owner_id FROM items i WHERE i.id = protocol_runs.id"
    )
    op.execute(
        "UPDATE todos SET protocol_run_id = u.run_id FROM unmerge u WHERE todos.id = u.item_id"
    )
    op.execute(
        "UPDATE protocol_run_items SET run_id = u.run_id "
        "FROM unmerge u WHERE protocol_run_items.run_id = u.item_id"
    )
    op.execute(
        "UPDATE protocol_runs SET id = u.run_id FROM unmerge u WHERE id = u.item_id"
    )
    op.execute("UPDATE items SET kind = 'todo' WHERE kind = 'protocol_run'")

    op.alter_column("protocol_runs", "spawned_at", nullable=False)
    op.execute(
        "SELECT setval('protocol_runs_id_seq', "
        "coalesce((SELECT max(id) FROM protocol_runs), 0) + 1, false)"
    )
    op.execute(
        "ALTER TABLE protocol_runs ALTER COLUMN id SET DEFAULT nextval('protocol_runs_id_seq')"
    )
    op.create_foreign_key(
        op.f("fk_protocol_runs_owner_id_users"),
        "protocol_runs",
        "users",
        ["owner_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_protocol_run_items_run_id_protocol_runs",
        "protocol_run_items",
        "protocol_runs",
        ["run_id"],
        ["id"],
    )
    op.create_unique_constraint(
        op.f("uq_todos_protocol_run_id"), "todos", ["protocol_run_id"]
    )
    op.create_foreign_key(
        "fk_todos_protocol_run_id_protocol_runs",
        "todos",
        "protocol_runs",
        ["protocol_run_id"],
        ["id"],
    )
