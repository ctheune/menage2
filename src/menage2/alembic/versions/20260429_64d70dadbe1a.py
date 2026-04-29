"""add todo links column

Revision ID: 64d70dadbe1a
Revises: de613bd28fbf
Create Date: 2026-04-29 07:58:31.494161

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

# revision identifiers, used by Alembic.
revision = "64d70dadbe1a"
down_revision = "de613bd28fbf"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "todos",
        sa.Column("links", ARRAY(sa.Text()), server_default="{}", nullable=False),
    )


def downgrade():
    op.drop_column("todos", "links")
