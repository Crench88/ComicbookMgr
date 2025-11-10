"""Add series_issue table

Revision ID: cc5f7c9d3e4a
Revises: b7d6a8d4a6b2
Create Date: 2025-11-09 21:15:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'cc5f7c9d3e4a'
down_revision = 'b7d6a8d4a6b2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'series_issue',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('series_id', sa.Integer(), nullable=False),
        sa.Column('issue_number', sa.String(length=50), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=True),
        sa.Column('cover_date', sa.String(length=100), nullable=True),
        sa.Column('featured_characters', sa.Text(), nullable=True),
        sa.Column('writer', sa.String(length=200), nullable=True),
        sa.Column('artist', sa.String(length=200), nullable=True),
        sa.Column('story_arc', sa.String(length=200), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['series_id'], ['series.id'], ),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    op.drop_table('series_issue')

