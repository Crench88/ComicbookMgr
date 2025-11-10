"""Add series table

Revision ID: b7d6a8d4a6b2
Revises: af5dc61a8bf3
Create Date: 2025-11-09 20:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b7d6a8d4a6b2'
down_revision = 'af5dc61a8bf3'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'series',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('volume', sa.String(length=50), nullable=True),
        sa.Column('publisher', sa.String(length=100), nullable=True),
        sa.Column('date_range', sa.String(length=200), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', 'volume', name='uq_series_name_volume')
    )


def downgrade():
    op.drop_table('series')

