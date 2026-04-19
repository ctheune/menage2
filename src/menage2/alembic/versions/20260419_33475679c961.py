"""insert supermarkt infix into einkaufen tags

Revision ID: 33475679c961
Revises: 89f2eea2d3e1
Create Date: 2026-04-19 19:21:33.443016

"""
from alembic import op


revision = '33475679c961'
down_revision = '89f2eea2d3e1'
branch_labels = None
depends_on = None

def upgrade():
    # Insert :supermarkt: infix into all einkaufen: tags except einkaufen:asia-markt.
    # Matches "einkaufen:" followed by anything that is not "supermarkt:" or "asia-markt".
    op.execute("""
        UPDATE ingredients
        SET tags = regexp_replace(
            tags,
            'einkaufen:(?!(supermarkt:|asia-markt))([^,]*)',
            'einkaufen:supermarkt:\\2',
            'g'
        )
        WHERE tags ~ 'einkaufen:(?!(supermarkt:|asia-markt))[^,]+'
    """)


def downgrade():
    # Remove the :supermarkt: infix where it was inserted.
    op.execute("""
        UPDATE ingredients
        SET tags = regexp_replace(
            tags,
            'einkaufen:supermarkt:(?!asia-markt)([^,]*)',
            'einkaufen:\\1',
            'g'
        )
        WHERE tags ~ 'einkaufen:supermarkt:(?!asia-markt)[^,]+'
    """)
