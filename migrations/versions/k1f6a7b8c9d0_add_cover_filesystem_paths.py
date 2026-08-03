"""Add filesystem path columns for comic covers.

Revision ID: k1f6a7b8c9d0
Revises: j0e5f6a7b8c9
Create Date: 2026-07-24 17:05:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'k1f6a7b8c9d0'
down_revision = 'j0e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('comic', schema=None) as batch_op:
        batch_op.add_column(sa.Column('cover_image_path', sa.String(length=500), nullable=True))

    with op.batch_alter_table('comic_cover', schema=None) as batch_op:
        batch_op.add_column(sa.Column('image_path', sa.String(length=500), nullable=True))
        batch_op.alter_column('image_data', existing_type=sa.LargeBinary(), nullable=True)


def downgrade():
    with op.batch_alter_table('comic_cover', schema=None) as batch_op:
        batch_op.alter_column('image_data', existing_type=sa.LargeBinary(), nullable=False)
        batch_op.drop_column('image_path')

    with op.batch_alter_table('comic', schema=None) as batch_op:
        batch_op.drop_column('cover_image_path')
