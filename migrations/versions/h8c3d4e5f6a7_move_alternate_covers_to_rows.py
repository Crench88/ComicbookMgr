"""Store alternate comic covers in dedicated rows.

Revision ID: h8c3d4e5f6a7
Revises: g7b2c3d4e5f6
Create Date: 2026-07-09 15:20:00.000000
"""
import base64
import binascii
import json
from datetime import datetime

from alembic import op
import sqlalchemy as sa


revision = 'h8c3d4e5f6a7'
down_revision = 'g7b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    if not inspector.has_table('comic_cover'):
        op.create_table(
            'comic_cover',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('comic_id', sa.Integer(), sa.ForeignKey('comic.id'), nullable=False),
            sa.Column('image_data', sa.LargeBinary(), nullable=False),
            sa.Column('mime_type', sa.String(length=100), nullable=False),
            sa.Column('label', sa.String(length=200), nullable=False),
            sa.Column('position', sa.Integer(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.UniqueConstraint('comic_id', 'position', name='uq_comic_cover_position'),
        )
        op.create_index('ix_comic_cover_comic_id', 'comic_cover', ['comic_id'], unique=False)

    # Convert existing JSON/Base64 alternates without touching the primary
    # cover, which remains in comic.cover_image for compatibility.
    rows = connection.execute(sa.text(
        "SELECT id, additional_covers FROM comic "
        "WHERE additional_covers IS NOT NULL AND additional_covers != ''"
    )).mappings()
    now = datetime.utcnow()

    for row in rows:
        try:
            covers = json.loads(row['additional_covers'])
        except (TypeError, json.JSONDecodeError):
            continue

        for position, cover in enumerate(covers, start=1):
            try:
                image_data = base64.b64decode(cover.get('blob_data', ''), validate=True)
            except (TypeError, ValueError, binascii.Error):
                continue
            if not image_data:
                continue

            connection.execute(sa.text(
                "INSERT INTO comic_cover "
                "(comic_id, image_data, mime_type, label, position, created_at) "
                "VALUES (:comic_id, :image_data, :mime_type, :label, :position, :created_at)"
            ), {
                'comic_id': row['id'],
                'image_data': image_data,
                'mime_type': (cover.get('mime_type') or 'image/jpeg')[:100],
                'label': (cover.get('label') or f'Cover {position}')[:200],
                'position': position,
                'created_at': now,
            })

        connection.execute(
            sa.text("UPDATE comic SET additional_covers = NULL WHERE id = :id"),
            {'id': row['id']},
        )


def downgrade():
    connection = op.get_bind()
    rows = connection.execute(sa.text(
        "SELECT comic_id, image_data, mime_type, label, position "
        "FROM comic_cover ORDER BY comic_id, position"
    )).mappings()
    covers_by_comic = {}
    for row in rows:
        covers_by_comic.setdefault(row['comic_id'], []).append({
            'blob_data': base64.b64encode(row['image_data']).decode('ascii'),
            'mime_type': row['mime_type'] or 'image/jpeg',
            'label': row['label'] or 'Cover',
        })
    for comic_id, covers in covers_by_comic.items():
        connection.execute(
            sa.text(
                "UPDATE comic SET additional_covers = :covers WHERE id = :comic_id"
            ),
            {'covers': json.dumps(covers), 'comic_id': comic_id},
        )

    op.drop_index('ix_comic_cover_comic_id', table_name='comic_cover')
    op.drop_table('comic_cover')
