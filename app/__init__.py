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
from flask_wtf.csrf import CSRFProtect
from markupsafe import Markup, escape
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

DEFAULT_MAX_REQUEST_SIZE = 64 * 1024 * 1024
DEFAULT_READER_CACHE_SIZE = 512 * 1024 * 1024


def _resolve_database_uri(raw_uri, instance_path):
    """
    Point relative sqlite URLs at the instance folder so WSGI hosts
    (PythonAnywhere) do not create comicbook.db in a random cwd.
    Absolute sqlite paths (sqlite:////...) and non-sqlite URLs are unchanged.
    """
    if not raw_uri:
        raw_uri = 'sqlite:///comicbook.db'
    if raw_uri.startswith('sqlite:///') and not raw_uri.startswith('sqlite:////'):
        relative = raw_uri[len('sqlite:///'):]
        if relative and not os.path.isabs(relative):
            return 'sqlite:///' + os.path.join(instance_path, relative).replace('\\', '/')
    return raw_uri


def _request_size_limit():
    """Return the configured request limit, falling back to 64 MB."""
    try:
        return int(os.environ.get('MAX_CONTENT_LENGTH', DEFAULT_MAX_REQUEST_SIZE))
    except (TypeError, ValueError):
        return DEFAULT_MAX_REQUEST_SIZE


def _reader_cache_size_limit():
    """Byte cap for the extracted reader page cache."""
    try:
        return int(os.environ.get('READER_CACHE_SIZE_LIMIT', DEFAULT_READER_CACHE_SIZE))
    except (TypeError, ValueError):
        return DEFAULT_READER_CACHE_SIZE


# Initialize extensions
db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()
mail = Mail()
csrf = CSRFProtect()

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
        flask_env = os.environ.get('FLASK_ENV', 'development').lower()
        secret_key = os.environ.get('SECRET_KEY')
        if flask_env == 'production' and not secret_key:
            raise RuntimeError('SECRET_KEY must be configured in production.')
        secret_key = secret_key or 'dev-secret-key-change-in-production'
        
        app.config.from_mapping(
            SECRET_KEY=secret_key,
            SQLALCHEMY_DATABASE_URI=_resolve_database_uri(
                os.environ.get('DATABASE_URL', 'sqlite:///comicbook.db'),
                app.instance_path,
            ),
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
            SESSION_COOKIE_HTTPONLY=True,
            SESSION_COOKIE_SAMESITE='Lax',
            SESSION_COOKIE_SECURE=(flask_env == 'production'),
            UPLOAD_FOLDER=os.path.join(app.instance_path, 'uploads'),
            COVERS_FOLDER=os.environ.get('COVERS_FOLDER', os.path.join(app.instance_path, 'covers')),
            COVERS_KEEP_BLOB=os.environ.get('COVERS_KEEP_BLOB', 'true').lower() in ['1', 'true', 'yes', 'on'],
            DIGITAL_FOLDER=os.environ.get('DIGITAL_FOLDER', os.path.join(app.instance_path, 'digital')),
            READER_CACHE_DIR=os.environ.get(
                'READER_CACHE_DIR', os.path.join(app.instance_path, 'reader_cache')
            ),
            READER_CACHE_SIZE_LIMIT=_reader_cache_size_limit(),
            # Cover variants are submitted as Base64 data, which can be much
            # larger than one uploaded image. Keep both parsing limits aligned.
            MAX_CONTENT_LENGTH=_request_size_limit(),
            MAX_FORM_MEMORY_SIZE=_request_size_limit(),
            COMICVINE_API_KEY=os.environ.get('COMICVINE_API_KEY', ''),
            MARVEL_API_KEY=os.environ.get('MARVEL_API_KEY', ''),
            MARVEL_PRIVATE_KEY=os.environ.get('MARVEL_PRIVATE_KEY', ''),
            UPC_DATABASE_API_KEY=os.environ.get('UPC_DATABASE_API_KEY', ''),
            BARCODE_LOOKUP_API_KEY=os.environ.get('BARCODE_LOOKUP_API_KEY', ''),
            # Price comparables. EBAY_CA is eBay Canada, priced in CAD.
            EBAY_CLIENT_ID=os.environ.get('EBAY_CLIENT_ID', ''),
            EBAY_CLIENT_SECRET=os.environ.get('EBAY_CLIENT_SECRET', ''),
            EBAY_MARKETPLACE_ID=os.environ.get('EBAY_MARKETPLACE_ID', 'EBAY_CA'),
            EBAY_ENVIRONMENT=os.environ.get('EBAY_ENVIRONMENT', 'production'),
            EBAY_COMIC_CATEGORY_ID=os.environ.get('EBAY_COMIC_CATEGORY_ID', ''),
            PRICE_ASK_TO_SOLD_RATIO=os.environ.get('PRICE_ASK_TO_SOLD_RATIO', '0.8'),
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
        app.config.setdefault('COVERS_FOLDER', os.path.join(app.instance_path, 'covers'))
        app.config.setdefault('COVERS_KEEP_BLOB', True)
        app.config.setdefault('DIGITAL_FOLDER', os.path.join(app.instance_path, 'digital'))
        app.config.setdefault(
            'READER_CACHE_DIR', os.path.join(app.instance_path, 'reader_cache')
        )
        app.config.setdefault('READER_CACHE_SIZE_LIMIT', DEFAULT_READER_CACHE_SIZE)
    
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

    try:
        os.makedirs(app.config['COVERS_FOLDER'])
    except OSError:
        pass

    try:
        os.makedirs(app.config['DIGITAL_FOLDER'])
    except OSError:
        pass
    
    # Initialize extensions with app
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    mail.init_app(app)
    csrf.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'

    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        response.headers.setdefault('X-Frame-Options', 'DENY')
        response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
        response.headers.setdefault(
            'Permissions-Policy',
            'camera=(), microphone=(), geolocation=()',
        )
        return response
    
    # Import and register blueprints
    from .auth import auth_bp
    from .main import main_bp
    from .comics import comics_bp
    from .dashboard import dashboard_bp
    from .admin import admin_bp
    from .reader import reader_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(comics_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(reader_bp)
    
    # Import models for database creation
    from .models import User, Comic, ComicCover, ComicFile, ReadingProgress, Series, SeriesIssue, Tag
    
    # User loader for Flask-Login
    @login_manager.user_loader
    def load_user(user_id):
        try:
            return db.session.get(User, int(user_id))
        except (TypeError, ValueError):
            return None

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

    return app
