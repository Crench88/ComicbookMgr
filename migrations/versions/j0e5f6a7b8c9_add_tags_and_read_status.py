"""Add per-user tags and comic read_status.

Revision ID: j0e5f6a7b8c9
Revises: i9d4e5f6a7b8
Create Date: 2026-07-24 16:55:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'j0e5f6a7b8c9'
down_revision = 'i9d4e5f6a7b8'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'tag',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('user.id'), nullable=False),
        sa.Column('name', sa.String(length=80), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('user_id', 'name', name='uq_tag_user_name'),
    )
    op.create_index('ix_tag_user_id', 'tag', ['user_id'], unique=False)

    op.create_table(
        'comic_tags',
        sa.Column('comic_id', sa.Integer(), sa.ForeignKey('comic.id'), primary_key=True),
        sa.Column('tag_id', sa.Integer(), sa.ForeignKey('tag.id'), primary_key=True),
    )

    with op.batch_alter_table('comic', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('read_status', sa.String(length=20), nullable=False, server_default='unread')
        )
        batch_op.create_index('ix_comic_read_status', ['read_status'], unique=False)

    # Keep DB clean: drop server default after backfill-friendly add.
    with op.batch_alter_table('comic', schema=None) as batch_op:
        batch_op.alter_column('read_status', server_default=None)


def downgrade():
    with op.batch_alter_table('comic', schema=None) as batch_op:
        batch_op.drop_index('ix_comic_read_status')
        batch_op.drop_column('read_status')

    op.drop_table('comic_tags')
    op.drop_index('ix_tag_user_id', table_name='tag')
    op.drop_table('tag')
