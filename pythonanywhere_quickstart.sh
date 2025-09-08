#!/bin/bash
# PythonAnywhere Quick Start Script
# Run this script on PythonAnywhere to quickly set up your Comic Book Collection Manager

echo "🚀 Comic Book Collection Manager - PythonAnywhere Quick Start"
echo "=============================================================="

# Check if we're in the right directory
if [ ! -d "app" ]; then
    echo "❌ Error: app directory not found. Please run this script from the project root."
    exit 1
fi

# Get PythonAnywhere username
echo "📝 Please enter your PythonAnywhere username:"
read PA_USERNAME

if [ -z "$PA_USERNAME" ]; then
    echo "❌ Username cannot be empty"
    exit 1
fi

echo "👤 Using username: $PA_USERNAME"

# Update wsgi.py with correct username
echo "🔧 Updating wsgi.py with your username..."
sed -i "s/YOUR_USERNAME/$PA_USERNAME/g" wsgi.py

# Create virtual environment
echo "📦 Creating virtual environment..."
python3.12 -m venv venv
source venv/bin/activate

# Install dependencies
echo "📥 Installing dependencies..."
pip install -r requirements.txt

# Set up environment file
echo "🔧 Setting up environment configuration..."
if [ ! -f ".env" ]; then
    if [ -f "env.production" ]; then
        cp env.production .env
        echo "✅ Created .env file from production template"
        echo "⚠️  Please edit .env file with your actual configuration values"
    else
        echo "❌ env.production template not found"
    fi
fi

# Initialize database
echo "🗄️ Setting up database..."
flask db init
flask db migrate -m "Initial migration"
flask db upgrade

# Create admin user
echo "👤 Creating admin user..."
python3 -c "
from app import create_app, db
from app.models import User
from werkzeug.security import generate_password_hash

app = create_app()
with app.app_context():
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        admin = User(
            username='admin',
            email='admin@example.com',
            password_hash=generate_password_hash('admin123'),
            is_active=True
        )
        db.session.add(admin)
        db.session.commit()
        print('✅ Admin user created successfully!')
        print('   Username: admin')
        print('   Password: admin123')
        print('   Email: admin@example.com')
    else:
        print('ℹ️  Admin user already exists')
"

# Set up directories
echo "📁 Setting up directories..."
mkdir -p instance/uploads
mkdir -p app/static/uploads

echo ""
echo "🎉 Setup completed successfully!"
echo ""
echo "📋 Next steps:"
echo "1. Edit .env file with your actual configuration:"
echo "   - Set SECRET_KEY (use: python generate_secret_key.py)"
echo "   - Configure email settings"
echo ""
echo "2. In PythonAnywhere Web tab:"
echo "   - Set source code directory: /home/$PA_USERNAME/ComicbookMgr"
echo "   - Set working directory: /home/$PA_USERNAME/ComicbookMgr"
echo "   - Set virtualenv: /home/$PA_USERNAME/ComicbookMgr/venv"
echo "   - Set WSGI file: /home/$PA_USERNAME/ComicbookMgr/wsgi.py"
echo ""
echo "3. Configure static files:"
echo "   - URL: /static/"
echo "   - Directory: /home/$PA_USERNAME/ComicbookMgr/app/static/"
echo ""
echo "4. Configure media files:"
echo "   - URL: /uploads/"
echo "   - Directory: /home/$PA_USERNAME/ComicbookMgr/instance/uploads/"
echo ""
echo "5. Reload your web app"
echo ""
echo "🔗 Your app will be available at: https://$PA_USERNAME.pythonanywhere.com"
echo ""
echo "🔐 Default admin credentials:"
echo "   Username: admin"
echo "   Password: admin123"
echo "   (Change these after first login!)"
