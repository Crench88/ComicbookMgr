"""Add nullable comic.series_id FK to catalog Series.

Revision ID: i9d4e5f6a7b8
Revises: h8c3d4e5f6a7
Create Date: 2026-07-24 16:10:00.000000
"""
import re

from alembic import op
import sqlalchemy as sa


revision = 'i9d4e5f6a7b8'
down_revision = 'h8c3d4e5f6a7'
branch_labels = None
depends_on = None

_VOLUME_SUFFIX_RE = re.compile(
    r'^(?P<name>.+?)\s+(?:Vol\.?|Volume)\s*(?P<volume>\d+)\s*$',
    re.IGNORECASE,
)


def _normalize(text):
    return ' '.join((text or '').strip().lower().split())


def _display_name(name, volume):
    if volume and str(volume).strip():
        volume = str(volume).strip()
        if volume.lower().startswith('vol'):
            return f'{name} {volume}'
        return f'{name} Vol. {volume}'
    return name


def _volume_key(volume):
    volume = (volume or '').strip()
    digits = re.search(r'(\d+)', volume)
    return digits.group(1) if digits else _normalize(volume)


def _backfill_series_links(connection):
    series_table = sa.table(
        'series',
        sa.column('id', sa.Integer),
        sa.column('name', sa.String),
        sa.column('volume', sa.String),
        sa.column('publisher', sa.String),
        sa.column('comicvine_volume_id', sa.Integer),
    )
    comic_table = sa.table(
        'comic',
        sa.column('id', sa.Integer),
        sa.column('series', sa.String),
        sa.column('series_id', sa.Integer),
        sa.column('publisher', sa.String),
    )

    series_rows = list(connection.execute(sa.select(
        series_table.c.id,
        series_table.c.name,
        series_table.c.volume,
        series_table.c.publisher,
        series_table.c.comicvine_volume_id,
    )))
    if not series_rows:
        return

    catalog = []
    for row in series_rows:
        catalog.append({
            'id': row.id,
            'name': row.name or '',
            'volume': row.volume or '',
            'publisher': row.publisher or '',
            'comicvine_volume_id': row.comicvine_volume_id,
            'display_name': _display_name(row.name or '', row.volume),
            'name_key': _normalize(row.name),
            'display_key': _normalize(_display_name(row.name or '', row.volume)),
            'volume_key': _volume_key(row.volume),
            'publisher_key': _normalize(row.publisher),
        })

    comics = list(connection.execute(sa.select(
        comic_table.c.id,
        comic_table.c.series,
        comic_table.c.publisher,
    ).where(comic_table.c.series_id.is_(None))))

    for comic in comics:
        text = (comic.series or '').strip()
        if not text:
            continue
        text_key = _normalize(text)
        publisher_key = _normalize(comic.publisher)
        match = _VOLUME_SUFFIX_RE.match(text)
        parsed_name = match.group('name').strip() if match else text
        parsed_volume = match.group('volume').strip() if match else None
        name_key = _normalize(parsed_name)

        candidates = [row for row in catalog if row['display_key'] == text_key]
        if len(candidates) != 1 and parsed_volume:
            candidates = [
                row for row in catalog
                if row['name_key'] == name_key and row['volume_key'] == parsed_volume
            ]
        if len(candidates) != 1:
            candidates = [
                row for row in catalog
                if row['name_key'] == text_key or row['name_key'] == name_key
            ]
        if len(candidates) > 1 and publisher_key:
            narrowed = [row for row in candidates if row['publisher_key'] == publisher_key]
            if len(narrowed) == 1:
                candidates = narrowed
        if len(candidates) != 1:
            continue

        matched = candidates[0]
        connection.execute(
            comic_table.update()
            .where(comic_table.c.id == comic.id)
            .values(series_id=matched['id'], series=matched['display_name'])
        )


def upgrade():
    with op.batch_alter_table('comic', schema=None) as batch_op:
        batch_op.add_column(sa.Column('series_id', sa.Integer(), nullable=True))
        batch_op.create_index('ix_comic_series_id', ['series_id'], unique=False)
        batch_op.create_foreign_key(
            'fk_comic_series_id_series',
            'series',
            ['series_id'],
            ['id'],
        )

    _backfill_series_links(op.get_bind())


def downgrade():
    with op.batch_alter_table('comic', schema=None) as batch_op:
        batch_op.drop_constraint('fk_comic_series_id_series', type_='foreignkey')
        batch_op.drop_index('ix_comic_series_id')
        batch_op.drop_column('series_id')
