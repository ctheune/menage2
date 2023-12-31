"""add planner

Revision ID: a6f2d1215b8b
Revises: acdb4d095c72
Create Date: 2023-08-07 14:45:16.973882

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a6f2d1215b8b'
down_revision = 'acdb4d095c72'
branch_labels = None
depends_on = None

def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('recipe_weekdays',
    sa.Column('recipe_id', sa.Integer(), nullable=False),
    sa.Column('weekday', sa.Enum('monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday', name='weekday'), nullable=False),
    sa.ForeignKeyConstraint(['recipe_id'], ['recipes.id'], name=op.f('fk_recipe_weekdays_recipe_id_recipes')),
    sa.PrimaryKeyConstraint('recipe_id', 'weekday', name=op.f('pk_recipe_weekdays'))
    )
    op.create_table('recipes_seasons',
    sa.Column('recipe_id', sa.Integer(), nullable=False),
    sa.Column('month', sa.Enum('january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december', name='month'), nullable=False),
    sa.ForeignKeyConstraint(['recipe_id'], ['recipes.id'], name=op.f('fk_recipes_seasons_recipe_id_recipes')),
    sa.PrimaryKeyConstraint('recipe_id', 'month', name=op.f('pk_recipes_seasons'))
    )
    op.create_table('schedules',
    sa.Column('recipe_id', sa.Integer(), nullable=False),
    sa.Column('frequency', sa.Integer(), server_default='90', nullable=True),
    sa.ForeignKeyConstraint(['recipe_id'], ['recipes.id'], name=op.f('fk_schedules_recipe_id_recipes')),
    sa.PrimaryKeyConstraint('recipe_id', name=op.f('pk_schedules'))
    )
    # ### end Alembic commands ###

def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('schedules')
    op.drop_table('recipes_seasons')
    op.drop_table('recipe_weekdays')
    # ### end Alembic commands ###
