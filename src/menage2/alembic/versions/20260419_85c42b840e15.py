"""remove trailing-colon einkaufen tags from ingredients and todos

Revision ID: 85c42b840e15
Revises: 33475679c961
Create Date: 2026-04-19 20:18:49.429110

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '85c42b840e15'
down_revision = '33475679c961'
branch_labels = None
depends_on = None

def upgrade():
    # Remove empty-subtag tokens like 'einkaufen:supermarkt:' (trailing colon)
    # from the ingredients comma-separated text column.
    op.execute(r"""
        UPDATE ingredients
        SET tags = trim(BOTH ',' FROM regexp_replace(
            regexp_replace(
                tags,
                '(^|,)einkaufen:supermarkt:(,|$)',
                ',',
                'g'
            ),
            ',+', ',', 'g'
        ))
        WHERE tags ~ '(^|,)einkaufen:supermarkt:(,|$)'
    """)

    # Remove the same bad tag from the todos PostgreSQL ARRAY column.
    op.execute("""
        UPDATE todos
        SET tags = array_remove(tags, 'einkaufen:supermarkt:')
        WHERE 'einkaufen:supermarkt:' = ANY(tags)
    """)


def downgrade():
    pass
