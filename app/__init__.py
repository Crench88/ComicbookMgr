"""
Comic Book Collection Manager - Main Application Package
A Flask web application for managing personal comic book collections.
"""

import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_mail import Mail
from markupsafe import Markup, escape
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

DEFAULT_MAX_REQUEST_SIZE = 64 * 1024 * 1024


def _request_size_limit():
    """Return the configured request limit, falling back to 64 MB."""
    try:
        return int(os.environ.get('MAX_CONTENT_LENGTH', DEFAULT_MAX_REQUEST_SIZE))
    except (TypeError, ValueError):
        return DEFAULT_MAX_REQUEST_SIZE


# Initialize extensions
db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()
mail = Mail()

def create_app(test_config=None):
    """
    Application factory pattern for creating Flask app instances.
    
    Args:
        test_config: Configuration for testing environment
        
    Returns:
        Flask app instance
    """
    app = Flask(__name__, instance_relative_config=True, 
                template_folder='templates', static_folder='static')
    
    # Configuration
    if test_config is None:
        # Simplified secret key configuration
        secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
        
        app.config.from_mapping(
            SECRET_KEY=secret_key,
            SQLALCHEMY_DATABASE_URI=os.environ.get('DATABASE_URL', 'sqlite:///comicbook.db'),
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
            UPLOAD_FOLDER=os.path.join(app.instance_path, 'uploads'),
            # Cover variants are submitted as Base64 data, which can be much
            # larger than one uploaded image. Keep both parsing limits aligned.
            MAX_CONTENT_LENGTH=_request_size_limit(),
            MAX_FORM_MEMORY_SIZE=_request_size_limit(),
            COMICVINE_API_KEY=os.environ.get('COMICVINE_API_KEY', ''),
            MARVEL_API_KEY=os.environ.get('MARVEL_API_KEY', ''),
            MARVEL_PRIVATE_KEY=os.environ.get('MARVEL_PRIVATE_KEY', ''),
            UPC_DATABASE_API_KEY=os.environ.get('UPC_DATABASE_API_KEY', ''),
            BARCODE_LOOKUP_API_KEY=os.environ.get('BARCODE_LOOKUP_API_KEY', ''),
            CACHE_DIR=os.environ.get('CACHE_DIR', os.path.join('instance', 'cache')),
            # Email configuration
            MAIL_SERVER=os.environ.get('MAIL_SERVER', 'smtp.gmail.com'),
            MAIL_PORT=int(os.environ.get('MAIL_PORT', 587)),
            MAIL_USE_TLS=os.environ.get('MAIL_USE_TLS', 'true').lower() in ['true', 'on', '1'],
            MAIL_USERNAME=os.environ.get('MAIL_USERNAME'),
            MAIL_PASSWORD=os.environ.get('MAIL_PASSWORD'),
            MAIL_DEFAULT_SENDER=os.environ.get('MAIL_DEFAULT_SENDER', os.environ.get('MAIL_USERNAME'))
        )
    else:
        app.config.from_mapping(test_config)
        app.config.setdefault('SECRET_KEY', 'test-secret-key')
        app.config.setdefault('UPLOAD_FOLDER', os.path.join(app.instance_path, 'uploads'))
    
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
    migrate.init_app(app, db)
    mail.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'
    
    # Import and register blueprints
    from .auth import auth_bp
    from .main import main_bp
    from .comics import comics_bp
    from .dashboard import dashboard_bp
    from .admin import admin_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(comics_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(admin_bp)
    
    # Import models for database creation
    from .models import User, Comic, ComicCover, Series, SeriesIssue
    
    # User loader for Flask-Login
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    @app.template_filter('nl2br')
    def nl2br_filter(value):
        """Convert newlines to <br> tags while escaping HTML."""
        if value is None:
            return ''
        escaped = escape(value)
        return Markup('<br>'.join(escaped.splitlines()))

    @app.context_processor
    def inject_theme():
        from flask_login import current_user
        from flask_wtf.csrf import generate_csrf
        if current_user.is_authenticated:
            theme_pref = current_user.get_preferred_theme()
        else:
            theme_pref = 'system'
        return {
            'user_theme_preference': theme_pref,
            'csrf_token': generate_csrf(),
        }

    # Create database tables
    with app.app_context():
        db.create_all()
    
    return app
