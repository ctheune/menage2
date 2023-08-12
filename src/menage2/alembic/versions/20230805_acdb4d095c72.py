"""init

Revision ID: acdb4d095c72
Revises: 
Create Date: 2023-08-05 18:35:11.183599

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'acdb4d095c72'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('ingredients',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ingredients'))
    )
    op.create_table('planner_weeks',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_planner_weeks'))
    )
    op.create_table('recipes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('title', sa.Text(), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('source', sa.Text(), nullable=True),
    sa.Column('source_url', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_recipes'))
    )
    op.create_table('planner_days',
    sa.Column('day', sa.Date(), nullable=False),
    sa.Column('week_id', sa.Integer(), nullable=False),
    sa.Column('dinner_id', sa.Integer(), nullable=True),
    sa.Column('dinner_freestyle', sa.Text(), nullable=True),
    sa.Column('note', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['dinner_id'], ['recipes.id'], name=op.f('fk_planner_days_dinner_id_recipes')),
    sa.ForeignKeyConstraint(['week_id'], ['planner_weeks.id'], name=op.f('fk_planner_days_week_id_planner_weeks')),
    sa.PrimaryKeyConstraint('day', name=op.f('pk_planner_days'))
    )
    op.create_table('recipe_ingredients',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('recipe_id', sa.Integer(), nullable=False),
    sa.Column('ingredient_id', sa.Integer(), nullable=False),
    sa.Column('amount', sa.Text(), nullable=True),
    sa.Column('unit', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['ingredient_id'], ['ingredients.id'], name=op.f('fk_recipe_ingredients_ingredient_id_ingredients')),
    sa.ForeignKeyConstraint(['recipe_id'], ['recipes.id'], name=op.f('fk_recipe_ingredients_recipe_id_recipes')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_recipe_ingredients'))
    )
    # ### end Alembic commands ###

def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('recipe_ingredients')
    op.drop_table('planner_days')
    op.drop_table('recipes')
    op.drop_table('planner_weeks')
    op.drop_table('ingredients')
    # ### end Alembic commands ###