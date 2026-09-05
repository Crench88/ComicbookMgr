"""Add comic.user_id index and character_mention table.

Revision ID: q7l2m3n4o5p6
Revises: p6k1g2h3i4j5
Create Date: 2026-09-04 19:00:00.000000
"""
import re

from alembic import op
import sqlalchemy as sa


revision = 'q7l2m3n4o5p6'
down_revision = 'p6k1g2h3i4j5'
branch_labels = None
depends_on = None


def _parse_character_names(text):
    if not text:
        return []
    seen = set()
    names = []
    for part in re.split(r'[,;]', str(text)):
        name = ' '.join(part.strip().split())[:200]
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        names.append(name)
    return names


def upgrade():
    with op.batch_alter_table('comic', schema=None) as batch_op:
        batch_op.create_index('ix_comic_user_id', ['user_id'], unique=False)

    op.create_table(
        'character_mention',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('user.id'), nullable=False),
        sa.Column(
            'comic_id',
            sa.Integer(),
            sa.ForeignKey('comic.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint(
            'user_id',
            'comic_id',
            'name',
            name='uq_character_mention_user_comic_name',
        ),
    )
    op.create_index('ix_character_mention_user_id', 'character_mention', ['user_id'])
    op.create_index('ix_character_mention_comic_id', 'character_mention', ['comic_id'])
    op.create_index(
        'ix_character_mention_user_name',
        'character_mention',
        ['user_id', 'name'],
    )

    conn = op.get_bind()
    rows = conn.execute(sa.text(
        'SELECT id, user_id, characters FROM comic '
        'WHERE characters IS NOT NULL AND TRIM(characters) != \'\''
    ))
    insert = sa.text(
        'INSERT INTO character_mention (user_id, comic_id, name) '
        'VALUES (:user_id, :comic_id, :name)'
    )
    for row in rows:
        comic_id, user_id, characters = row[0], row[1], row[2]
        for name in _parse_character_names(characters):
            conn.execute(
                insert,
                {'user_id': user_id, 'comic_id': comic_id, 'name': name},
            )


def downgrade():
    op.drop_index('ix_character_mention_user_name', table_name='character_mention')
    op.drop_index('ix_character_mention_comic_id', table_name='character_mention')
    op.drop_index('ix_character_mention_user_id', table_name='character_mention')
    op.drop_table('character_mention')
    with op.batch_alter_table('comic', schema=None) as batch_op:
        batch_op.drop_index('ix_comic_user_id')
