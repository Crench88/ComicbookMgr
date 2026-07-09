"""Add preferred_theme column to user model

Revision ID: f6a1b2c3d4e5
Revises: e5f9a2b3c4d5
Create Date: 2026-07-02 22:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'f6a1b2c3d4e5'
down_revision = 'e5f9a2b3c4d5'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('preferred_theme', sa.String(length=10), nullable=False, server_default='system')
        )

    conn = op.get_bind()
    conn.execute(sa.text(
        "UPDATE user SET preferred_theme = 'dark' WHERE dark_mode_preference = 1"
    ))
    conn.execute(sa.text(
        "UPDATE user SET preferred_theme = 'light' WHERE dark_mode_preference = 0 OR dark_mode_preference IS NULL"
    ))


def downgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('preferred_theme')
