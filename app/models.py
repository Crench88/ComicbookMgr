"""
Database models for Comic Book Collection Manager.
Defines User and Comic models with their relationships and methods.
"""

from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

# Import db from app module
try:
    from . import db
except ImportError:
    # For testing purposes, create a mock db
    db = SQLAlchemy()

class User(UserMixin, db.Model):
    """
    User model for authentication and user management.
    Inherits from UserMixin for Flask-Login compatibility.
    """
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    dark_mode_preference = db.Column(db.Boolean, default=False)  # Dark mode preference
    
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
        from datetime import datetime, timedelta
        
        self.reset_token = secrets.token_urlsafe(32)
        self.reset_token_expires = datetime.utcnow() + timedelta(hours=1)  # Token expires in 1 hour
        return self.reset_token
    
    def is_reset_token_valid(self, token):
        """Check if the reset token is valid and not expired."""
        return (self.reset_token == token and 
                self.reset_token_expires and 
                self.reset_token_expires > datetime.utcnow())
    
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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    issues = db.relationship('SeriesIssue', backref='series', cascade='all, delete-orphan', lazy=True)

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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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


class Comic(db.Model):
    """
    Comic model for storing comic book information.
    Contains all fields for comprehensive comic book data.
    """
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)  # Full display title (e.g., "The Amazing Spider-Man: Worldwide #1")
    series = db.Column(db.String(200))  # Series name (e.g., "The Amazing Spider-Man")
    issue_title = db.Column(db.String(200))  # Individual issue title (e.g., "Worldwide")
    issue_number = db.Column(db.String(20), nullable=False)
    publisher = db.Column(db.String(100), nullable=False)
    characters = db.Column(db.Text)  # Comma-separated list of characters
    genre = db.Column(db.String(100))
    release_date = db.Column(db.Date)
    upc = db.Column(db.String(20))  # Universal Product Code (12 digits)
    isbn = db.Column(db.String(20))  # International Standard Book Number (13 digits)
    condition = db.Column(db.String(50))  # Mint, Near Mint, Very Fine, Fine, Good, etc.
    estimated_value = db.Column(db.Float, default=0.0)
    notes = db.Column(db.Text)
    cover_image = db.Column(db.LargeBinary)  # BLOB storage for primary cover image
    cover_image_mime = db.Column(db.String(100))  # MIME type of the image
    additional_covers = db.Column(db.Text)  # JSON string of additional cover images with BLOB data
    is_wishlist = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Foreign key to user
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
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
    
    def get_additional_covers(self):
        """Return additional covers as a list of dictionaries with BLOB data."""
        import json
        if self.additional_covers:
            try:
                return json.loads(self.additional_covers)
            except (json.JSONDecodeError, TypeError):
                return []
        return []
    
    def set_additional_covers(self, covers_list):
        """Set additional covers from a list of dictionaries with BLOB data."""
        import json
        if covers_list:
            self.additional_covers = json.dumps(covers_list)
        else:
            self.additional_covers = None
    
    def get_all_covers(self):
        """Return all covers including the primary cover with BLOB data."""
        covers = []
        if self.cover_image:
            # Convert BLOB data to base64 for JSON serialization
            import base64
            blob_base64 = base64.b64encode(self.cover_image).decode('utf-8')
            covers.append({
                'blob_data': blob_base64,
                'mime_type': self.cover_image_mime or 'image/jpeg',
                'label': 'Primary Cover',
                'is_primary': True
            })
        
        additional_covers = self.get_additional_covers()
        covers.extend(additional_covers)
        
        return covers
    
    def has_cover_image(self):
        """Check if comic has a cover image."""
        return self.cover_image is not None
    
    def __repr__(self):
        return f'<Comic {self.title} #{self.issue_number}>'
