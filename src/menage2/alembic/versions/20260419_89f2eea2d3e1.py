"""add exclude_from_shopping to planner_days

Revision ID: 89f2eea2d3e1
Revises: acd134b0e75d
Create Date: 2026-04-19 18:59:01.751595

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '89f2eea2d3e1'
down_revision = 'acd134b0e75d'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('planner_days', sa.Column('exclude_from_shopping', sa.Boolean(), server_default='false', nullable=False))

def downgrade():
    op.drop_column('planner_days', 'exclude_from_shopping')
