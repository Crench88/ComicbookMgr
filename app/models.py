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
    
    # Relationship to comics
    comics = db.relationship('Comic', backref='owner', lazy=True, cascade='all, delete-orphan')
    
    def set_password(self, password):
        """Hash and set the user's password."""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Check if the provided password matches the stored hash."""
        return check_password_hash(self.password_hash, password)
    
    def __repr__(self):
        return f'<User {self.username}>'

class Comic(db.Model):
    """
    Comic model for storing comic book information.
    Contains all fields for comprehensive comic book data.
    """
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    issue_number = db.Column(db.String(20), nullable=False)
    publisher = db.Column(db.String(100), nullable=False)
    characters = db.Column(db.Text)  # Comma-separated list of characters
    genre = db.Column(db.String(100))
    release_date = db.Column(db.Date)
    condition = db.Column(db.String(50))  # Mint, Near Mint, Very Fine, Fine, Good, etc.
    estimated_value = db.Column(db.Float, default=0.0)
    notes = db.Column(db.Text)
    cover_image = db.Column(db.String(255))  # Path to uploaded image
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
    
    def __repr__(self):
        return f'<Comic {self.title} #{self.issue_number}>'
