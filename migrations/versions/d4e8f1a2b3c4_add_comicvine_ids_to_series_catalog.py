"""Add ComicVine id fields to series catalog

Revision ID: d4e8f1a2b3c4
Revises: cc5f7c9d3e4a
Create Date: 2026-07-02 21:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'd4e8f1a2b3c4'
down_revision = 'cc5f7c9d3e4a'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('series', schema=None) as batch_op:
        batch_op.add_column(sa.Column('comicvine_volume_id', sa.Integer(), nullable=True))

    with op.batch_alter_table('series_issue', schema=None) as batch_op:
        batch_op.add_column(sa.Column('comicvine_issue_id', sa.Integer(), nullable=True))
        batch_op.create_index('ix_series_issue_comicvine_issue_id', ['comicvine_issue_id'], unique=False)


def downgrade():
    with op.batch_alter_table('series_issue', schema=None) as batch_op:
        batch_op.drop_index('ix_series_issue_comicvine_issue_id')
        batch_op.drop_column('comicvine_issue_id')

    with op.batch_alter_table('series', schema=None) as batch_op:
        batch_op.drop_column('comicvine_volume_id')
