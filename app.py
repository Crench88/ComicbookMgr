"""
Comic Book Collection Manager - Main Application
A Flask web application for managing personal comic book collections.
"""

import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize extensions
db = SQLAlchemy()
login_manager = LoginManager()

def create_app(test_config=None):
    """
    Application factory pattern for creating Flask app instances.
    
    Args:
        test_config: Configuration for testing environment
        
    Returns:
        Flask app instance
    """
    app = Flask(__name__, instance_relative_config=True)
    
    # Configuration
    if test_config is None:
        app.config.from_mapping(
            SECRET_KEY=os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production'),
            SQLALCHEMY_DATABASE_URI=os.environ.get('DATABASE_URL', 'sqlite:///comicbook.db'),
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
            UPLOAD_FOLDER=os.path.join(app.instance_path, 'uploads'),
            MAX_CONTENT_LENGTH=16 * 1024 * 1024  # 16MB max file size
        )
    else:
        app.config.from_mapping(test_config)
    
    # Ensure instance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass
    
    # Ensure upload folder exists
    try:
        os.makedirs(app.config['UPLOAD_FOLDER'])
    except OSError:
        pass
    
    # Initialize extensions with app
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'
    
    # Import and register blueprints
    from .auth import auth_bp
    from .main import main_bp
    from .comics import comics_bp
    from .dashboard import dashboard_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(comics_bp)
    app.register_blueprint(dashboard_bp)
    
    # Import models for database creation
    from .models import User, Comic
    
    # User loader for Flask-Login
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
    
    # Create database tables
    with app.app_context():
        db.create_all()
    
    return app
