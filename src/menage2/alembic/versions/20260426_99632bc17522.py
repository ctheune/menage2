"""protocols

Revision ID: 99632bc17522
Revises: a9b8ea9793d3
Create Date: 2026-04-26 21:12:01.126584

Adds the four protocol tables (template + items, run + run-items) and the
1-to-1 link from Todo via ``todos.protocol_run_id`` (UNIQUE).
"""
from alembic import op
import sqlalchemy as sa

import menage2.models.todo  # noqa: F401 — needed for TagSet type alias


revision = '99632bc17522'
down_revision = 'a9b8ea9793d3'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'protocols',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('recurrence_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ['recurrence_id'], ['recurrence_rules.id'],
            name=op.f('fk_protocols_recurrence_id_recurrence_rules'),
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_protocols')),
    )

    op.create_table(
        'protocol_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('protocol_id', sa.Integer(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('tags', menage2.models.todo.TagSet(sa.Text()), server_default='{}', nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ['protocol_id'], ['protocols.id'],
            name=op.f('fk_protocol_items_protocol_id_protocols'),
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_protocol_items')),
    )

    op.create_table(
        'protocol_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('protocol_id', sa.Integer(), nullable=False),
        sa.Column('spawned_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('opened_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ['protocol_id'], ['protocols.id'],
            name=op.f('fk_protocol_runs_protocol_id_protocols'),
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_protocol_runs')),
    )

    op.create_table(
        'protocol_run_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('run_id', sa.Integer(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('tags', menage2.models.todo.TagSet(sa.Text()), server_default='{}', nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column(
            'status',
            sa.Enum('pending', 'done', 'sent_to_todo', name='protocolrunitemstatus'),
            server_default='pending', nullable=False,
        ),
        sa.Column('sent_todo_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ['run_id'], ['protocol_runs.id'],
            name=op.f('fk_protocol_run_items_run_id_protocol_runs'),
        ),
        sa.ForeignKeyConstraint(
            ['sent_todo_id'], ['todos.id'],
            name=op.f('fk_protocol_run_items_sent_todo_id_todos'),
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_protocol_run_items')),
    )

    op.add_column('todos', sa.Column('protocol_run_id', sa.Integer(), nullable=True))
    op.create_unique_constraint(
        op.f('uq_todos_protocol_run_id'), 'todos', ['protocol_run_id'],
    )
    op.create_foreign_key(
        op.f('fk_todos_protocol_run_id_protocol_runs'),
        'todos', 'protocol_runs', ['protocol_run_id'], ['id'],
    )


def downgrade():
    op.drop_constraint(op.f('fk_todos_protocol_run_id_protocol_runs'), 'todos', type_='foreignkey')
    op.drop_constraint(op.f('uq_todos_protocol_run_id'), 'todos', type_='unique')
    op.drop_column('todos', 'protocol_run_id')
    op.drop_table('protocol_run_items')
    op.drop_table('protocol_runs')
    op.drop_table('protocol_items')
    op.drop_table('protocols')
    op.execute("DROP TYPE IF EXISTS protocolrunitemstatus")
