"""add tags and note to protocols

Revision ID: f316f0e748c4
Revises: 20260428_protocols_owner
Create Date: 2026-04-28 19:09:26.358131

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "f316f0e748c4"
down_revision = "20260428_protocols_owner"
branch_labels = None
depends_on = None

#: The tag/assignee arrays these migrations create. Spelled out rather
#: than imported from the models: a migration describes the schema as
#: it was, and the model has since stopped having a type for it.
TEXT_ARRAY = postgresql.ARRAY(sa.Text())


def upgrade():
    op.add_column(
        "protocols",
        sa.Column("tags", TEXT_ARRAY, server_default="{}", nullable=False),
    )
    op.add_column("protocols", sa.Column("note", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("protocols", "note")
    op.drop_column("protocols", "tags")
