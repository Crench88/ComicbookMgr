"""Remove unused isbn column from comic.

Revision ID: o5j0f1a2b3c4
Revises: n4i9e0f1a2b3
Create Date: 2026-08-02 12:40:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'o5j0f1a2b3c4'
down_revision = 'n4i9e0f1a2b3'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('comic', schema=None) as batch_op:
        batch_op.drop_column('isbn')


def downgrade():
    with op.batch_alter_table('comic', schema=None) as batch_op:
        batch_op.add_column(sa.Column('isbn', sa.String(length=20), nullable=True))
