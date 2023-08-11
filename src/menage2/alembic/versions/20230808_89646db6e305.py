"""add schedule for all recipes

Revision ID: 89646db6e305
Revises: 05f80527f85f
Create Date: 2023-08-08 10:32:54.308572

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "89646db6e305"
down_revision = "05f80527f85f"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("insert into schedules (recipe_id)  select id as recipe_id from recipes")


def downgrade():
    pass
