"""Add ComicVine creative-team metadata columns to comic

Revision ID: g7b2c3d4e5f6
Revises: f6a1b2c3d4e5
Create Date: 2026-07-08 17:55:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'g7b2c3d4e5f6'
down_revision = 'f6a1b2c3d4e5'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('comic', schema=None) as batch_op:
        batch_op.add_column(sa.Column('writer', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('artist', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('colorist', sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column('letterer', sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column('editor', sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column('cover_artist', sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column('teams', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('story_arc', sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column('description', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('comicvine_issue_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('comicvine_url', sa.String(length=500), nullable=True))
        batch_op.create_index('ix_comic_comicvine_issue_id', ['comicvine_issue_id'], unique=False)


def downgrade():
    with op.batch_alter_table('comic', schema=None) as batch_op:
        batch_op.drop_index('ix_comic_comicvine_issue_id')
        batch_op.drop_column('comicvine_url')
        batch_op.drop_column('comicvine_issue_id')
        batch_op.drop_column('description')
        batch_op.drop_column('story_arc')
        batch_op.drop_column('teams')
        batch_op.drop_column('cover_artist')
        batch_op.drop_column('editor')
        batch_op.drop_column('letterer')
        batch_op.drop_column('colorist')
        batch_op.drop_column('artist')
        batch_op.drop_column('writer')
