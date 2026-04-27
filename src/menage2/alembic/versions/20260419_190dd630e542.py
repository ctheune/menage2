"""Lowercase weekday and month enum values on production

Revision ID: 190dd630e542
Revises: 85c42b840e15
Create Date: 2026-04-19 21:59:44.695683

Production DB has uppercase enum values (MONDAY, TUESDAY, …) while the
model uses values_callable to store lowercase (monday, tuesday, …).
This migration renames them to lowercase so queries match.

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "190dd630e542"
down_revision = "85c42b840e15"
branch_labels = None
depends_on = None


def upgrade():
    # Guard: only rename if the uppercase variants still exist (prod).
    # Dev DB was already created with lowercase values, so the DO block
    # is a no-op there.
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_enum
                WHERE enumlabel = 'MONDAY'
                  AND enumtypid = 'weekday'::regtype
            ) THEN
                ALTER TYPE weekday RENAME VALUE 'MONDAY'    TO 'monday';
                ALTER TYPE weekday RENAME VALUE 'TUESDAY'   TO 'tuesday';
                ALTER TYPE weekday RENAME VALUE 'WEDNESDAY' TO 'wednesday';
                ALTER TYPE weekday RENAME VALUE 'THURSDAY'  TO 'thursday';
                ALTER TYPE weekday RENAME VALUE 'FRIDAY'    TO 'friday';
                ALTER TYPE weekday RENAME VALUE 'SATURDAY'  TO 'saturday';
                ALTER TYPE weekday RENAME VALUE 'SUNDAY'    TO 'sunday';
            END IF;
        END $$;
    """)
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_enum
                WHERE enumlabel = 'JANUARY'
                  AND enumtypid = 'month'::regtype
            ) THEN
                ALTER TYPE month RENAME VALUE 'JANUARY'   TO 'january';
                ALTER TYPE month RENAME VALUE 'FEBRUARY'  TO 'february';
                ALTER TYPE month RENAME VALUE 'MARCH'     TO 'march';
                ALTER TYPE month RENAME VALUE 'APRIL'     TO 'april';
                ALTER TYPE month RENAME VALUE 'MAY'       TO 'may';
                ALTER TYPE month RENAME VALUE 'JUNE'      TO 'june';
                ALTER TYPE month RENAME VALUE 'JULY'      TO 'july';
                ALTER TYPE month RENAME VALUE 'AUGUST'    TO 'august';
                ALTER TYPE month RENAME VALUE 'SEPTEMBER' TO 'september';
                ALTER TYPE month RENAME VALUE 'OCTOBER'   TO 'october';
                ALTER TYPE month RENAME VALUE 'NOVEMBER'  TO 'november';
                ALTER TYPE month RENAME VALUE 'DECEMBER'  TO 'december';
            END IF;
        END $$;
    """)


def downgrade():
    pass
