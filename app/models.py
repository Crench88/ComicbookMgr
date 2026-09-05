"""
Database models for Comic Book Collection Manager.
Defines User and Comic models with their relationships and methods.
"""

from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from sqlalchemy.orm import query_expression
from werkzeug.security import generate_password_hash, check_password_hash

# Import db from app module
try:
    from . import db
except ImportError:
    # For testing purposes, create a mock db
    db = SQLAlchemy()


def utcnow():
    """Current UTC time as a naive value for existing DateTime columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(UserMixin, db.Model):
    """
    User model for authentication and user management.
    Inherits from UserMixin for Flask-Login compatibility.
    """
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)
    is_active = db.Column(db.Boolean, default=True)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    dark_mode_preference = db.Column(db.Boolean, default=False)  # Legacy; synced from preferred_theme
    preferred_theme = db.Column(db.String(10), default='system', nullable=False)  # light, dark, system

    THEME_CHOICES = ('light', 'dark', 'system')

    def get_preferred_theme(self):
        """Return validated theme preference."""
        theme = (self.preferred_theme or 'system').lower()
        return theme if theme in self.THEME_CHOICES else 'system'

    def set_preferred_theme(self, theme):
        """Set theme preference and keep legacy column in sync."""
        theme = (theme or 'system').lower()
        if theme not in self.THEME_CHOICES:
            theme = 'system'
        self.preferred_theme = theme
        self.dark_mode_preference = theme == 'dark'
    
    # Password reset fields
    reset_token = db.Column(db.String(100), unique=True, nullable=True)
    reset_token_expires = db.Column(db.DateTime, nullable=True)
    
    # Relationship to comics
    comics = db.relationship('Comic', backref='owner', lazy=True, cascade='all, delete-orphan')
    
    def set_password(self, password):
        """Hash and set the user's password."""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Check if the provided password matches the stored hash."""
        return check_password_hash(self.password_hash, password)
    
    def generate_reset_token(self):
        """Generate a password reset token."""
        import secrets
        from datetime import timedelta
        
        self.reset_token = secrets.token_urlsafe(32)
        self.reset_token_expires = utcnow() + timedelta(hours=1)  # Token expires in 1 hour
        return self.reset_token
    
    def is_reset_token_valid(self, token):
        """Check if the reset token is valid and not expired."""
        return (self.reset_token == token and 
                self.reset_token_expires and 
                self.reset_token_expires > utcnow())
    
    def clear_reset_token(self):
        """Clear the reset token after successful password reset."""
        self.reset_token = None
        self.reset_token_expires = None
    
    def __repr__(self):
        return f'<User {self.username}>'

class Series(db.Model):
    """
    Series model for maintaining canonical comic series and volume information.
    """
    __tablename__ = 'series'
    __table_args__ = (
        db.UniqueConstraint('name', 'volume', name='uq_series_name_volume'),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    volume = db.Column(db.String(50))
    publisher = db.Column(db.String(100))
    date_range = db.Column(db.String(200))
    notes = db.Column(db.Text)
    comicvine_volume_id = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)
    issues = db.relationship('SeriesIssue', backref='series', cascade='all, delete-orphan', lazy=True)
    owned_comics = db.relationship('Comic', back_populates='catalog_series', lazy='dynamic')

    @property
    def display_name(self):
        """Return a friendly display name such as 'Amazing Spider-Man Vol. 1'."""
        if self.volume:
            volume = self.volume.strip()
            if volume.lower().startswith('vol'):
                return f"{self.name} {volume}"
            return f"{self.name} Vol. {volume}"
        return self.name

    def __repr__(self):
        if self.volume:
            return f"<Series {self.display_name}>"
        return f"<Series {self.name}>"


class SeriesIssue(db.Model):
    """
    Canonical comic data stored per series (issue metadata).
    """
    __tablename__ = 'series_issue'

    id = db.Column(db.Integer, primary_key=True)
    series_id = db.Column(db.Integer, db.ForeignKey('series.id'), nullable=False)
    issue_number = db.Column(db.String(50), nullable=False)
    title = db.Column(db.String(255))
    cover_date = db.Column(db.String(100))
    featured_characters = db.Column(db.Text)
    writer = db.Column(db.String(200))
    artist = db.Column(db.String(200))
    story_arc = db.Column(db.String(200))
    comicvine_issue_id = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    def __repr__(self):
        return f"<SeriesIssue {self.issue_number} - {self.title or ''}>"

    @property
    def sort_key(self):
        """Sort key for ordering issues numeric then suffix."""
        issue = (self.issue_number or '').strip()
        if not issue:
            return (float('inf'), '')
        import re
        match = re.match(r'(\d+(?:\.\d+)?)\s*(.*)', issue)
        if match:
            num = float(match.group(1))
            suffix = (match.group(2) or '').strip().lower()
            return (num, suffix)
        return (float('inf'), issue.lower())



comic_tags = db.Table(
    'comic_tags',
    db.Column('comic_id', db.Integer, db.ForeignKey('comic.id'), primary_key=True),
    db.Column('tag_id', db.Integer, db.ForeignKey('tag.id'), primary_key=True),
)


class Tag(db.Model):
    """Per-user tag used to organize owned comics."""
    __tablename__ = 'tag'
    __table_args__ = (
        db.UniqueConstraint('user_id', 'name', name='uq_tag_user_name'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    name = db.Column(db.String(80), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)

    def __repr__(self):
        return f'<Tag {self.name}>'


class Comic(db.Model):
    """
    Comic model for storing comic book information.
    Contains all fields for comprehensive comic book data.
    """
    __tablename__ = 'comic'
    __table_args__ = (
        db.Index('ix_comic_user_id_is_wishlist', 'user_id', 'is_wishlist'),
    )

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)  # Full display title (e.g., "The Amazing Spider-Man: Worldwide #1")
    series = db.Column(db.String(200))  # Free-text series label (kept for grouping / unmatched comics)
    series_id = db.Column(db.Integer, db.ForeignKey('series.id'), nullable=True, index=True)
    issue_title = db.Column(db.String(200))  # Individual issue title (e.g., "Worldwide")
    issue_number = db.Column(db.String(20), nullable=False)
    publisher = db.Column(db.String(100), nullable=False)
    characters = db.Column(db.Text)  # Comma-separated list of characters
    writer = db.Column(db.Text)
    artist = db.Column(db.Text)
    penciler = db.Column(db.String(500))
    inker = db.Column(db.String(500))
    colorist = db.Column(db.String(500))
    letterer = db.Column(db.String(500))
    editor = db.Column(db.String(500))
    assistant_editor = db.Column(db.String(500))
    cover_artist = db.Column(db.String(500))
    designer = db.Column(db.String(500))
    production = db.Column(db.String(500))
    translator = db.Column(db.String(500))
    other_credits = db.Column(db.String(500))
    teams = db.Column(db.Text)
    story_arc = db.Column(db.String(500))
    description = db.Column(db.Text)  # ComicVine synopsis / deck
    comicvine_issue_id = db.Column(db.Integer, nullable=True)
    comicvine_url = db.Column(db.String(500))
    genre = db.Column(db.String(100))
    release_date = db.Column(db.Date)
    upc = db.Column(db.String(20))  # Universal Product Code (12 digits)
    condition = db.Column(db.String(50))  # Mint, Near Mint, Very Fine, Fine, Good, etc.
    estimated_value = db.Column(db.Float, default=0.0)
    notes = db.Column(db.Text)
    cover_image = db.Column(db.LargeBinary)  # Legacy BLOB; dual-read with cover_image_path
    cover_image_path = db.Column(db.String(500))  # Relative path under instance/covers
    cover_image_mime = db.Column(db.String(100))  # MIME type of the image
    cover_available = query_expression()
    # Retained for migration compatibility. New alternate covers live in
    # ComicCover rows so adding a variant does not rewrite one large JSON blob.
    additional_covers = db.Column(db.Text)
    is_wishlist = db.Column(db.Boolean, default=False)
    in_collection = db.Column(db.Boolean, nullable=False, default=True)
    is_digital = db.Column(db.Boolean, nullable=False, default=False)
    read_status = db.Column(db.String(20), nullable=False, default='unread', index=True)
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)
    
    # Foreign key to user
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    catalog_series = db.relationship('Series', back_populates='owned_comics')
    tags = db.relationship(
        'Tag',
        secondary=comic_tags,
        lazy='select',
        backref=db.backref('comics', lazy='dynamic'),
    )
    character_mentions = db.relationship(
        'CharacterMention',
        backref='comic',
        lazy='select',
        cascade='all, delete-orphan',
    )
    cover_variants = db.relationship(
        'ComicCover',
        backref='comic',
        lazy='select',
        cascade='all, delete-orphan',
        order_by='ComicCover.position',
    )
    digital_file = db.relationship(
        'ComicFile',
        backref='comic',
        lazy='select',
        uselist=False,
        cascade='all, delete-orphan',
    )

    READ_STATUS_CHOICES = ('unread', 'reading', 'read')

    # Every creator column, in the order ComicVine lists credits. Kept in one
    # place so forms, pages, and importers cannot drift out of sync.
    CREDIT_FIELDS = (
        ('writer', 'Writer'),
        ('artist', 'Artist'),
        ('penciler', 'Penciler'),
        ('inker', 'Inker'),
        ('colorist', 'Colorist'),
        ('letterer', 'Letterer'),
        ('cover_artist', 'Cover Artist'),
        ('editor', 'Editor'),
        ('assistant_editor', 'Assistant Editor'),
        ('designer', 'Designer'),
        ('production', 'Production'),
        ('translator', 'Translator'),
        ('other_credits', 'Other'),
    )

    def credits(self):
        """Non-empty (label, names) pairs for display."""
        return [
            (label, getattr(self, field))
            for field, label in self.CREDIT_FIELDS
            if (getattr(self, field) or '').strip()
        ]

    @property
    def read_status_label(self):
        status = (self.read_status or 'unread').lower()
        return {
            'unread': 'Unread',
            'reading': 'Reading',
            'read': 'Read',
        }.get(status, 'Unread')

    def get_tags_text(self):
        """Comma-separated tag names for forms."""
        names = sorted({tag.name for tag in self.tags if tag.name}, key=str.lower)
        return ', '.join(names)

    @property
    def series_label(self):
        """Canonical series label for UI grouping and return URLs."""
        if self.catalog_series is not None:
            return self.catalog_series.display_name
        if self.series and str(self.series).strip():
            return str(self.series).strip()
        return 'Unknown Series'
    
    def get_characters_list(self):
        """Return characters as a list."""
        if self.characters:
            return [char.strip() for char in self.characters.split(',')]
        return []
    
    def set_characters_list(self, characters_list):
        """Set characters from a list."""
        if characters_list:
            self.characters = ', '.join(characters_list)
        else:
            self.characters = None
    
    def get_formatted_value(self):
        """Return estimated value formatted as currency."""
        return f"${self.estimated_value:.2f}" if self.estimated_value else "$0.00"
    
    def get_formatted_release_date(self):
        """Return release date formatted as string."""
        if self.release_date:
            return self.release_date.strftime('%B %Y')
        return "Unknown"
    
    def _safe_cover_url(self, endpoint, **values):
        """Build a cover URL when a Flask context exists; otherwise None."""
        from flask import url_for

        try:
            return url_for(endpoint, **values)
        except RuntimeError:
            return None

    def get_additional_covers(self, include_blob=False):
        """Return alternate covers. Prefer URLs; Base64 is opt-in for writers/tests."""
        import base64
        from .services.cover_storage import get_variant_cover_bytes

        covers = []
        for cover in self.cover_variants:
            if include_blob:
                image_data = get_variant_cover_bytes(cover)
                if not image_data:
                    continue
            elif not (cover.image_path or cover.image_data):
                continue
            else:
                image_data = None
            item = {
                'id': cover.id,
                'mime_type': cover.mime_type or 'image/jpeg',
                'label': cover.label or 'Cover',
                'is_primary': False,
                'url': self._safe_cover_url(
                    'comics.serve_cover_variant_image',
                    id=self.id,
                    cover_id=cover.id,
                    v=cover.image_version(),
                ) if self.id else None,
                'thumbnail_url': self._safe_cover_url(
                    'comics.serve_cover_variant_thumbnail',
                    id=self.id,
                    cover_id=cover.id,
                    v=cover.image_version(),
                ) if self.id else None,
            }
            if include_blob:
                item['blob_data'] = base64.b64encode(image_data).decode('utf-8')
            covers.append(item)
        return covers

    def set_additional_covers(self, covers_list):
        """Replace alternate cover rows from Base64 dictionaries."""
        import base64
        import binascii
        from .services.cover_storage import clear_variant_cover, persist_variant_cover

        for existing in list(self.cover_variants):
            clear_variant_cover(existing)
        self.cover_variants.clear()
        # Flush deletions before reusing positions. This matters on SQLite,
        # where inserting a replacement at position 1 can otherwise conflict
        # with the row scheduled for deletion at that same position.
        if self.id is not None:
            db.session.flush()
        for position, cover in enumerate(covers_list or [], start=1):
            try:
                image_data = base64.b64decode(cover.get('blob_data', ''), validate=True)
            except (ValueError, TypeError, binascii.Error):
                continue
            if image_data:
                variant = ComicCover(
                    image_data=image_data,
                    mime_type=(cover.get('mime_type') or 'image/jpeg')[:100],
                    label=(cover.get('label') or f'Cover {position}')[:200],
                    position=position,
                )
                self.cover_variants.append(variant)
                if self.id is not None:
                    persist_variant_cover(
                        variant,
                        image_data,
                        variant.mime_type,
                        user_id=self.user_id,
                        comic_id=self.id,
                    )
        self.additional_covers = None

    def get_all_covers(self, include_blob=False):
        """Return all covers. Prefer URLs; Base64 is opt-in for writers/tests."""
        import base64
        from .services.cover_storage import get_primary_cover_bytes

        covers = []
        if include_blob:
            primary = get_primary_cover_bytes(self)
            has_primary = bool(primary)
        else:
            primary = None
            has_primary = bool(self.cover_image_path or self.cover_image)
        if has_primary:
            item = {
                'id': None,
                'mime_type': self.cover_image_mime or 'image/jpeg',
                'label': 'Primary Cover',
                'is_primary': True,
                'url': self._safe_cover_url(
                    'comics.serve_cover_image',
                    id=self.id,
                    v=self.cover_version(),
                ) if self.id else None,
                'thumbnail_url': self._safe_cover_url(
                    'comics.serve_cover_thumbnail',
                    id=self.id,
                    v=self.cover_version(),
                ) if self.id else None,
            }
            if include_blob:
                item['blob_data'] = base64.b64encode(primary).decode('utf-8')
            covers.append(item)

        covers.extend(self.get_additional_covers(include_blob=include_blob))
        return covers

    def cover_version(self):
        """Cache-busting token for this comic's primary cover URL."""
        from .services.cover_storage import cover_version

        token = cover_version(self.cover_image_path) if self.cover_image_path else None
        if token:
            return token
        # Legacy BLOB-only rows: avoid loading the image just to version it.
        stamp = self.updated_at or self.created_at
        return str(int(stamp.timestamp())) if stamp else None

    def list_cover_summaries(self):
        """Lightweight cover metadata for templates (URLs, no Base64 payloads)."""
        covers = []
        if self.cover_image_path or self.cover_image:
            version = self.cover_version()
            covers.append({
                'id': None,
                'is_primary': True,
                'label': 'Primary Cover',
                'mime_type': self.cover_image_mime or 'image/jpeg',
                'version': version,
                'url': self._safe_cover_url(
                    'comics.serve_cover_image',
                    id=self.id,
                    v=version,
                ) if self.id else None,
                'thumbnail_url': self._safe_cover_url(
                    'comics.serve_cover_thumbnail',
                    id=self.id,
                    v=version,
                ) if self.id else None,
            })
        for cover in self.cover_variants:
            if not (cover.image_path or cover.image_data):
                continue
            version = cover.image_version()
            covers.append({
                'id': cover.id,
                'is_primary': False,
                'label': cover.label or 'Cover',
                'mime_type': cover.mime_type or 'image/jpeg',
                'version': version,
                'url': self._safe_cover_url(
                    'comics.serve_cover_variant_image',
                    id=self.id,
                    cover_id=cover.id,
                    v=version,
                ) if self.id else None,
                'thumbnail_url': self._safe_cover_url(
                    'comics.serve_cover_variant_thumbnail',
                    id=self.id,
                    cover_id=cover.id,
                    v=version,
                ) if self.id else None,
            })
        return covers

    def set_primary_cover_variant(self, cover_id):
        """Promote an alternate cover row to the primary cover image."""
        from .services.cover_storage import (
            clear_variant_cover,
            get_primary_cover_bytes,
            get_variant_cover_bytes,
            persist_primary_cover,
            persist_variant_cover,
        )

        variant = next((c for c in self.cover_variants if c.id == cover_id), None)
        if variant is None:
            return False

        old_primary_data = get_primary_cover_bytes(self)
        old_primary_mime = self.cover_image_mime or 'image/jpeg'
        # Primary covers carry no label of their own, so the demoted image needs
        # one that will not read as a second "Primary Cover" in the gallery.
        old_primary_label = 'Previous Primary Cover'

        new_primary_data = get_variant_cover_bytes(variant)
        new_primary_mime = variant.mime_type or 'image/jpeg'
        if not new_primary_data:
            return False

        remaining = []
        for cover in self.cover_variants:
            if cover.id == cover_id:
                continue
            data = get_variant_cover_bytes(cover)
            if not data:
                continue
            remaining.append({
                'image_data': data,
                'mime_type': cover.mime_type or 'image/jpeg',
                'label': cover.label or 'Cover',
            })

        for existing in list(self.cover_variants):
            clear_variant_cover(existing)
        self.cover_variants.clear()
        if self.id is not None:
            db.session.flush()

        persist_primary_cover(self, new_primary_data, new_primary_mime)

        position = 1
        if old_primary_data:
            demoted = ComicCover(
                image_data=old_primary_data,
                mime_type=old_primary_mime,
                label=old_primary_label,
                position=position,
            )
            self.cover_variants.append(demoted)
            persist_variant_cover(
                demoted,
                old_primary_data,
                old_primary_mime,
                user_id=self.user_id,
                comic_id=self.id,
            )
            position += 1

        for cover in remaining:
            variant_row = ComicCover(
                image_data=cover['image_data'],
                mime_type=cover['mime_type'],
                label=cover['label'],
                position=position,
            )
            self.cover_variants.append(variant_row)
            persist_variant_cover(
                variant_row,
                cover['image_data'],
                cover['mime_type'],
                user_id=self.user_id,
                comic_id=self.id,
            )
            position += 1

        self.additional_covers = None
        return True

    def has_cover_image(self):
        """Check if comic has a cover image on disk or as a legacy BLOB."""
        if self.cover_available is not None:
            return bool(self.cover_available)
        return bool(self.cover_image_path or self.cover_image)

    def has_digital_file(self):
        """True when a digital archive is attached."""
        return self.digital_file is not None

    @property
    def digital_active(self):
        """True when marked digital or a digital file is attached."""
        return bool(self.is_digital or self.has_digital_file())

    def sync_wishlist_flag(self):
        """Keep legacy wishlist flag aligned with ownership sliders."""
        self.is_wishlist = (not bool(self.in_collection)) and (not self.digital_active)

    def apply_ownership(self, in_collection=None, is_digital=None):
        """Update ownership sliders and sync wishlist."""
        if in_collection is not None:
            self.in_collection = bool(in_collection)
        if is_digital is not None:
            self.is_digital = bool(is_digital)
        self.sync_wishlist_flag()

    def ownership_status_tags(self):
        """Badges for collection / digital ownership."""
        digital = self.digital_active
        if self.in_collection and digital:
            return [
                {'key': 'collection', 'label': 'In Collection', 'class': 'bg-success'},
                {'key': 'digital', 'label': 'Digital', 'class': 'bg-info text-dark'},
            ]
        if self.in_collection:
            return [{'key': 'collection', 'label': 'In Collection', 'class': 'bg-success'}]
        if digital:
            return [{'key': 'digital-only', 'label': 'Digital only', 'class': 'bg-primary'}]
        return [{'key': 'wishlist', 'label': 'Wishlist', 'class': 'bg-warning text-dark'}]

    def __repr__(self):
        return f'<Comic {self.title} #{self.issue_number}>'


class CharacterMention(db.Model):
    """Indexed character name from Comic.characters for dashboard counts."""
    __tablename__ = 'character_mention'
    __table_args__ = (
        db.UniqueConstraint(
            'user_id', 'comic_id', 'name',
            name='uq_character_mention_user_comic_name',
        ),
        db.Index('ix_character_mention_user_name', 'user_id', 'name'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    comic_id = db.Column(
        db.Integer,
        db.ForeignKey('comic.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    name = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)

    def __repr__(self):
        return f'<CharacterMention {self.name}>'


class ComicCover(db.Model):
    """An alternate cover image belonging to a comic."""
    __tablename__ = 'comic_cover'
    __table_args__ = (
        db.UniqueConstraint('comic_id', 'position', name='uq_comic_cover_position'),
    )

    id = db.Column(db.Integer, primary_key=True)
    comic_id = db.Column(db.Integer, db.ForeignKey('comic.id'), nullable=False, index=True)
    image_data = db.Column(db.LargeBinary)  # Legacy BLOB; dual-read with image_path
    image_path = db.Column(db.String(500))  # Relative path under instance/covers
    mime_type = db.Column(db.String(100), nullable=False, default='image/jpeg')
    label = db.Column(db.String(200), nullable=False, default='Cover')
    position = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    def image_version(self):
        """Cache-busting token for this variant's cover URL."""
        from .services.cover_storage import cover_version

        return cover_version(self.image_path, self.image_data)


class ComicFile(db.Model):
    """Digital archive (CBZ) attached to a physical comic record."""
    __tablename__ = 'comic_file'
    __table_args__ = (
        db.UniqueConstraint('comic_id', name='uq_comic_file_comic_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    comic_id = db.Column(db.Integer, db.ForeignKey('comic.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    storage_path = db.Column(db.String(500), nullable=False)
    format = db.Column(db.String(20), nullable=False, default='cbz')
    original_filename = db.Column(db.String(255), nullable=False)
    page_count = db.Column(db.Integer, nullable=False, default=0)
    file_size = db.Column(db.Integer, nullable=False, default=0)
    content_hash = db.Column(db.String(64))
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    def __repr__(self):
        return f'<ComicFile comic={self.comic_id} format={self.format}>'


class ReadingProgress(db.Model):
    """Per-user last-read page for a comic digital file."""
    __tablename__ = 'reading_progress'
    __table_args__ = (
        db.UniqueConstraint('user_id', 'comic_id', name='uq_reading_progress_user_comic'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    comic_id = db.Column(db.Integer, db.ForeignKey('comic.id'), nullable=False, index=True)
    page_number = db.Column(db.Integer, nullable=False, default=1)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    def __repr__(self):
        return f'<ReadingProgress comic={self.comic_id} page={self.page_number}>'

