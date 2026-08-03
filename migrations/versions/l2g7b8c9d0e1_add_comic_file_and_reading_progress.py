"""Add comic_file and reading_progress for CBZ reader.

Revision ID: l2g7b8c9d0e1
Revises: k1f6a7b8c9d0
Create Date: 2026-07-24 17:10:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'l2g7b8c9d0e1'
down_revision = 'k1f6a7b8c9d0'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'comic_file',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('comic_id', sa.Integer(), sa.ForeignKey('comic.id'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('user.id'), nullable=False),
        sa.Column('storage_path', sa.String(length=500), nullable=False),
        sa.Column('format', sa.String(length=20), nullable=False),
        sa.Column('original_filename', sa.String(length=255), nullable=False),
        sa.Column('page_count', sa.Integer(), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=False),
        sa.Column('content_hash', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('comic_id', name='uq_comic_file_comic_id'),
    )
    op.create_index('ix_comic_file_comic_id', 'comic_file', ['comic_id'], unique=False)
    op.create_index('ix_comic_file_user_id', 'comic_file', ['user_id'], unique=False)

    op.create_table(
        'reading_progress',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('user.id'), nullable=False),
        sa.Column('comic_id', sa.Integer(), sa.ForeignKey('comic.id'), nullable=False),
        sa.Column('page_number', sa.Integer(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('user_id', 'comic_id', name='uq_reading_progress_user_comic'),
    )
    op.create_index('ix_reading_progress_user_id', 'reading_progress', ['user_id'], unique=False)
    op.create_index('ix_reading_progress_comic_id', 'reading_progress', ['comic_id'], unique=False)


def downgrade():
    op.drop_index('ix_reading_progress_comic_id', table_name='reading_progress')
    op.drop_index('ix_reading_progress_user_id', table_name='reading_progress')
    op.drop_table('reading_progress')
    op.drop_index('ix_comic_file_user_id', table_name='comic_file')
    op.drop_index('ix_comic_file_comic_id', table_name='comic_file')
    op.drop_table('comic_file')
