"""add_users_and_passkeys

Revision ID: 375865678696
Revises: 190dd630e542
Create Date: 2026-04-20 19:52:03.033500

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '375865678696'
down_revision = '190dd630e542'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('username', sa.Text(), nullable=False),
    sa.Column('real_name', sa.Text(), nullable=False),
    sa.Column('email', sa.Text(), nullable=False),
    sa.Column('password_hash', sa.Text(), nullable=True),
    sa.Column('is_admin', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('password_reset_token', sa.Text(), nullable=True),
    sa.Column('password_reset_token_expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users')),
    sa.UniqueConstraint('email', name=op.f('uq_users_email')),
    sa.UniqueConstraint('password_reset_token', name=op.f('uq_users_password_reset_token')),
    sa.UniqueConstraint('username', name=op.f('uq_users_username'))
    )
    op.create_table('passkeys',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('credential_id', sa.LargeBinary(), nullable=False),
    sa.Column('credential_public_key', sa.LargeBinary(), nullable=False),
    sa.Column('sign_count', sa.Integer(), server_default='0', nullable=False),
    sa.Column('device_name', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_passkeys_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_passkeys')),
    sa.UniqueConstraint('credential_id', name=op.f('uq_passkeys_credential_id'))
    )


def downgrade():
    op.drop_table('passkeys')
    op.drop_table('users')
