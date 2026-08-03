"""Add in_collection and is_digital ownership flags.

Revision ID: n4i9e0f1a2b3
Revises: m3h8d9e0f1a2
Create Date: 2026-08-02 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'n4i9e0f1a2b3'
down_revision = 'm3h8d9e0f1a2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('comic', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('in_collection', sa.Boolean(), nullable=False, server_default='1')
        )
        batch_op.add_column(
            sa.Column('is_digital', sa.Boolean(), nullable=False, server_default='0')
        )

    # Wishlist comics are not "in collection"; comics with a digital file are digital.
    op.execute(
        sa.text(
            "UPDATE comic SET in_collection = CASE WHEN is_wishlist THEN 0 ELSE 1 END"
        )
    )
    op.execute(
        sa.text(
            "UPDATE comic SET is_digital = 1 WHERE id IN (SELECT comic_id FROM comic_file)"
        )
    )

    with op.batch_alter_table('comic', schema=None) as batch_op:
        batch_op.alter_column('in_collection', server_default=None)
        batch_op.alter_column('is_digital', server_default=None)


def downgrade():
    with op.batch_alter_table('comic', schema=None) as batch_op:
        batch_op.drop_column('is_digital')
        batch_op.drop_column('in_collection')
