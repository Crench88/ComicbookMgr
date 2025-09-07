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
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

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
        # Ensure SECRET_KEY is set for production
        secret_key = os.environ.get('SECRET_KEY')
        if not secret_key:
            if app.debug:
                # Only allow default in development
                secret_key = 'dev-secret-key-change-in-production'
            else:
                raise RuntimeError('SECRET_KEY environment variable must be set for production')
        
        app.config.from_mapping(
            SECRET_KEY=secret_key,
            SQLALCHEMY_DATABASE_URI=os.environ.get('DATABASE_URL', 'sqlite:///comicbook.db'),
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
            UPLOAD_FOLDER=os.path.join(app.instance_path, 'uploads'),
            MAX_CONTENT_LENGTH=16 * 1024 * 1024,  # 16MB max file size
            COMICVINE_API_KEY=os.environ.get('COMICVINE_API_KEY', ''),
            MARVEL_API_KEY=os.environ.get('MARVEL_API_KEY', ''),
            MARVEL_PRIVATE_KEY=os.environ.get('MARVEL_PRIVATE_KEY', ''),
            UPC_DATABASE_API_KEY=os.environ.get('UPC_DATABASE_API_KEY', ''),
            BARCODE_LOOKUP_API_KEY=os.environ.get('BARCODE_LOOKUP_API_KEY', ''),
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
