"""a rule can fire on several weekdays, and on one day of the year

Revision ID: 7c1e5a9d3b20
Revises: b52c9e7a04d8
Create Date: 2026-10-04

"every Monday, Friday, Sunday" needs a set of days where there was room
for one, so `weekday` becomes `weekdays`, an array; every rule that had a
day keeps it, as a list of one. "every October 31st" needs the month the
day belongs to, which is the new `month` column beside `month_day`.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "7c1e5a9d3b20"
down_revision = "b52c9e7a04d8"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "recurrence_rules",
        sa.Column("weekdays", postgresql.ARRAY(sa.Integer()), nullable=True),
    )
    op.execute(
        "UPDATE recurrence_rules SET weekdays = ARRAY[weekday] "
        "WHERE weekday IS NOT NULL"
    )
    op.drop_column("recurrence_rules", "weekday")
    op.add_column("recurrence_rules", sa.Column("month", sa.Integer(), nullable=True))


def downgrade():
    op.drop_column("recurrence_rules", "month")
    op.add_column("recurrence_rules", sa.Column("weekday", sa.Integer(), nullable=True))
    # A rule on several days keeps only its first: one is all `weekday` holds.
    op.execute(
        "UPDATE recurrence_rules SET weekday = weekdays[1] WHERE weekdays IS NOT NULL"
    )
    op.drop_column("recurrence_rules", "weekdays")
