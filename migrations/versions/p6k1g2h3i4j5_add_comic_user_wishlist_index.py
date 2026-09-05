"""Add (user_id, is_wishlist) index for dashboard filters.

Revision ID: p6k1g2h3i4j5
Revises: o5j0f1a2b3c4
Create Date: 2026-09-04 18:10:00.000000
"""
from alembic import op


revision = 'p6k1g2h3i4j5'
down_revision = 'o5j0f1a2b3c4'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('comic', schema=None) as batch_op:
        batch_op.create_index(
            'ix_comic_user_id_is_wishlist',
            ['user_id', 'is_wishlist'],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table('comic', schema=None) as batch_op:
        batch_op.drop_index('ix_comic_user_id_is_wishlist')
