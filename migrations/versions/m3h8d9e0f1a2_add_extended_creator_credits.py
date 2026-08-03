"""Add the remaining ComicVine creator credit columns.

Revision ID: m3h8d9e0f1a2
Revises: l2g7b8c9d0e1
Create Date: 2026-07-24 21:52:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'm3h8d9e0f1a2'
down_revision = 'l2g7b8c9d0e1'
branch_labels = None
depends_on = None

_COLUMNS = (
    'penciler',
    'inker',
    'assistant_editor',
    'designer',
    'production',
    'translator',
    'other_credits',
)


def upgrade():
    with op.batch_alter_table('comic', schema=None) as batch_op:
        for name in _COLUMNS:
            batch_op.add_column(sa.Column(name, sa.String(length=500), nullable=True))


def downgrade():
    with op.batch_alter_table('comic', schema=None) as batch_op:
        for name in reversed(_COLUMNS):
            batch_op.drop_column(name)
