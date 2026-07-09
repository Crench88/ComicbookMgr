"""Add is_admin flag and search performance indexes

Revision ID: e5f9a2b3c4d5
Revises: d4e8f1a2b3c4
Create Date: 2026-07-02 22:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'e5f9a2b3c4d5'
down_revision = 'd4e8f1a2b3c4'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('is_admin', sa.Boolean(), nullable=False, server_default='0')
        )

    with op.batch_alter_table('series', schema=None) as batch_op:
        batch_op.create_index('ix_series_name', ['name'], unique=False)

    with op.batch_alter_table('series_issue', schema=None) as batch_op:
        batch_op.create_index('ix_series_issue_issue_number', ['issue_number'], unique=False)

    with op.batch_alter_table('comic', schema=None) as batch_op:
        batch_op.create_index('ix_comic_user_id_series', ['user_id', 'series'], unique=False)


def downgrade():
    with op.batch_alter_table('comic', schema=None) as batch_op:
        batch_op.drop_index('ix_comic_user_id_series')

    with op.batch_alter_table('series_issue', schema=None) as batch_op:
        batch_op.drop_index('ix_series_issue_issue_number')

    with op.batch_alter_table('series', schema=None) as batch_op:
        batch_op.drop_index('ix_series_name')

    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('is_admin')
