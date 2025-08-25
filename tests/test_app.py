"""
Unit tests for Comic Book Collection Manager.
"""

import pytest
import tempfile
import os
from app import create_app, db
from models import User, Comic
from datetime import datetime

@pytest.fixture
def app():
    """Create and configure a new app instance for each test."""
    # Create a temporary file to isolate the database for each test
    db_fd, db_path = tempfile.mkstemp()
    
    app = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
        'WTF_CSRF_ENABLED': False
    })
    
    # Create the database and load test data
    with app.app_context():
        db.create_all()
        yield app
    
    # Clean up the temporary database
    os.close(db_fd)
    os.unlink(db_path)

@pytest.fixture
def client(app):
    """A test client for the app."""
    return app.test_client()

@pytest.fixture
def runner(app):
    """A test runner for the app's Click commands."""
    return app.test_cli_runner()

@pytest.fixture
def test_user(app):
    """Create a test user."""
    with app.app_context():
        user = User(username='testuser', email='test@example.com')
        user.set_password('password123')
        db.session.add(user)
        db.session.commit()
        return user

class TestAuth:
    """Test authentication functionality."""
    
    def test_register(self, client):
        """Test user registration."""
        response = client.post('/register', data={
            'username': 'newuser',
            'email': 'newuser@example.com',
            'password': 'password123',
            'confirm_password': 'password123'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        assert b'Registration successful' in response.data
    
    def test_login(self, client, test_user):
        """Test user login."""
        response = client.post('/login', data={
            'username': 'testuser',
            'password': 'password123'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        assert b'Login successful' in response.data
    
    def test_invalid_login(self, client):
        """Test invalid login credentials."""
        response = client.post('/login', data={
            'username': 'wronguser',
            'password': 'wrongpassword'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        assert b'Invalid username or password' in response.data

class TestComics:
    """Test comic book functionality."""
    
    def test_add_comic(self, client, test_user):
        """Test adding a new comic."""
        # Login first
        client.post('/login', data={
            'username': 'testuser',
            'password': 'password123'
        })
        
        # Add comic
        response = client.post('/comics/new', data={
            'title': 'Amazing Spider-Man',
            'issue_number': '1',
            'publisher': 'Marvel Comics',
            'characters': 'Spider-Man, Peter Parker',
            'genre': 'Superhero',
            'condition': 'Near Mint',
            'estimated_value': '50.00',
            'notes': 'First appearance of Spider-Man'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        assert b'Comic added successfully' in response.data
    
    def test_view_comics(self, client, test_user):
        """Test viewing comics list."""
        # Login first
        client.post('/login', data={
            'username': 'testuser',
            'password': 'password123'
        })
        
        response = client.get('/comics')
        assert response.status_code == 200
        assert b'My Comics' in response.data

class TestDashboard:
    """Test dashboard functionality."""
    
    def test_dashboard_access(self, client, test_user):
        """Test dashboard access for authenticated users."""
        # Login first
        client.post('/login', data={
            'username': 'testuser',
            'password': 'password123'
        })
        
        response = client.get('/dashboard')
        assert response.status_code == 200
        assert b'Dashboard' in response.data
    
    def test_dashboard_redirect(self, client):
        """Test dashboard redirect for unauthenticated users."""
        response = client.get('/dashboard', follow_redirects=True)
        assert response.status_code == 200
        assert b'Login' in response.data

class TestModels:
    """Test database models."""
    
    def test_user_password_hashing(self, app):
        """Test user password hashing."""
        with app.app_context():
            user = User(username='testuser', email='test@example.com')
            user.set_password('password123')
            
            assert user.check_password('password123')
            assert not user.check_password('wrongpassword')
    
    def test_comic_creation(self, app, test_user):
        """Test comic creation."""
        with app.app_context():
            comic = Comic(
                title='Amazing Spider-Man',
                issue_number='1',
                publisher='Marvel Comics',
                characters='Spider-Man, Peter Parker',
                genre='Superhero',
                condition='Near Mint',
                estimated_value=50.00,
                user_id=test_user.id
            )
            
            db.session.add(comic)
            db.session.commit()
            
            assert comic.id is not None
            assert comic.title == 'Amazing Spider-Man'
            assert comic.get_formatted_value() == '$50.00'
            assert 'Spider-Man' in comic.get_characters_list()
    
    def test_comic_characters_methods(self, app, test_user):
        """Test comic character methods."""
        with app.app_context():
            comic = Comic(
                title='Test Comic',
                issue_number='1',
                publisher='Test Publisher',
                user_id=test_user.id
            )
            
            # Test setting characters from list
            characters_list = ['Spider-Man', 'Mary Jane', 'Green Goblin']
            comic.set_characters_list(characters_list)
            
            assert comic.characters == 'Spider-Man, Mary Jane, Green Goblin'
            assert comic.get_characters_list() == characters_list
