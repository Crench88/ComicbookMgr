# 🚀 PythonAnywhere Deployment Guide

## 📋 Prerequisites

1. **PythonAnywhere Account**: Sign up at [pythonanywhere.com](https://www.pythonanywhere.com)
2. **GitHub Repository**: Your code should be pushed to GitHub
3. **Domain Name** (optional): For custom domain setup

## 🔧 Step 1: Prepare Your Application

### 1.1 Update Requirements for Production

Your `requirements.txt` is already well-configured, but let's ensure it's production-ready:

```txt
Flask==2.3.3
Flask-Login==0.6.3
Flask-Mail==0.9.1
Flask-Migrate==4.0.5
Flask-SQLAlchemy==3.0.5
Flask-WTF==1.1.1
WTForms==3.0.1
Werkzeug==2.3.7
Pillow==10.0.1
python-dotenv==1.0.0
email-validator==2.0.0
gunicorn==21.2.0
requests==2.31.0
```

### 1.2 Create Production Configuration

Create a production-specific configuration file.

## 🏗️ Step 2: PythonAnywhere Setup

### 2.1 Create a New Web App

1. Log into PythonAnywhere
2. Go to **Web** tab
3. Click **Add a new web app**
4. Choose **Manual configuration**
5. Select **Python 3.12** (matches your local version)

### 2.2 Clone Your Repository

In the **Consoles** tab, open a Bash console:

```bash
# Clone your repository
git clone https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
cd YOUR_REPO_NAME

# Create virtual environment
python3.12 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2.3 Configure Web App

In the **Web** tab, edit your WSGI configuration file:

```python
import sys
import os

# Add your project directory to Python path
path = '/home/YOUR_USERNAME/YOUR_REPO_NAME'
if path not in sys.path:
    sys.path.append(path)

# Set environment variables
os.environ['FLASK_ENV'] = 'production'
os.environ['FLASK_DEBUG'] = 'False'

# Import your application
from app import create_app
application = create_app()
```

## 🔐 Step 3: Environment Variables

### 3.1 Create .env File

In your project directory, create a `.env` file:

```bash
# Production Configuration
FLASK_ENV=production
FLASK_DEBUG=False

# Generate a secure secret key
SECRET_KEY=your-super-secure-secret-key-here

# Database Configuration
DATABASE_URL=sqlite:///instance/comicbook.db

# Email Configuration (for password reset)
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-password
MAIL_DEFAULT_SENDER=your-email@gmail.com
```

### 3.2 Generate Secure Secret Key

Use the provided script to generate a secure key:

```bash
python generate_secret_key.py
```

## 📁 Step 4: Static Files Configuration

### 4.1 Configure Static Files

In the **Web** tab, set up static files mapping:

- **URL**: `/static/`
- **Directory**: `/home/YOUR_USERNAME/YOUR_REPO_NAME/app/static/`

### 4.2 Configure Media Files

- **URL**: `/uploads/`
- **Directory**: `/home/YOUR_USERNAME/YOUR_REPO_NAME/instance/uploads/`

## 🗄️ Step 5: Database Setup

### 5.1 Initialize Database

In the Bash console:

```bash
# Activate virtual environment
source venv/bin/activate

# Initialize database
flask db init
flask db migrate -m "Initial migration"
flask db upgrade

# Create admin user
python -c "
from app import create_app, db
from app.models import User
from werkzeug.security import generate_password_hash

app = create_app()
with app.app_context():
    # Create admin user
    admin = User(
        username='admin',
        email='admin@example.com',
        password_hash=generate_password_hash('admin123'),
        is_active=True
    )
    db.session.add(admin)
    db.session.commit()
    print('Admin user created!')
"
```

## 📧 Step 6: Email Configuration

### 6.1 Gmail Setup (Recommended)

1. Enable 2-factor authentication on your Gmail account
2. Generate an App Password:
   - Go to Google Account settings
   - Security → 2-Step Verification → App passwords
   - Generate password for "Mail"
3. Use the app password in your `.env` file

### 6.2 Alternative Email Providers

- **SendGrid**: Professional email service
- **Mailgun**: Developer-friendly email API
- **Amazon SES**: AWS email service

## 🌐 Step 7: Domain Configuration

### 7.1 Custom Domain (Optional)

1. In **Web** tab, add your domain
2. Update DNS records to point to PythonAnywhere
3. Configure SSL certificate

### 7.2 Default Domain

Your app will be available at: `https://YOUR_USERNAME.pythonanywhere.com`

## 🔄 Step 8: Deployment Process

### 8.1 Initial Deployment

1. **Reload Web App**: Click the reload button in Web tab
2. **Test Application**: Visit your domain
3. **Check Logs**: Monitor error logs for issues

### 8.2 Updates and Maintenance

```bash
# Pull latest changes
git pull origin main

# Update dependencies
pip install -r requirements.txt

# Run migrations if needed
flask db upgrade

# Reload web app
```

## 🚨 Step 9: Security Considerations

### 9.1 Production Security

- ✅ Secret key is properly configured
- ✅ Debug mode is disabled
- ✅ Environment variables are set
- ✅ Database is properly configured
- ✅ Email is configured for password reset

### 9.2 Additional Security

- Use HTTPS (PythonAnywhere provides free SSL)
- Regular backups of database
- Monitor error logs
- Keep dependencies updated

## 📊 Step 10: Monitoring and Maintenance

### 10.1 Log Monitoring

- **Error logs**: Check for application errors
- **Access logs**: Monitor traffic and performance
- **Server logs**: System-level issues

### 10.2 Performance Optimization

- Enable gzip compression
- Optimize images
- Use CDN for static files (optional)
- Monitor database performance

## 🆘 Troubleshooting

### Common Issues

1. **Import Errors**: Check Python path in WSGI file
2. **Database Errors**: Ensure migrations are run
3. **Static Files**: Verify static file mappings
4. **Email Issues**: Check SMTP configuration
5. **Permission Errors**: Verify file permissions

### Debug Steps

1. Check error logs in Web tab
2. Test in Bash console
3. Verify environment variables
4. Test database connection
5. Check file permissions

## 📞 Support

- **PythonAnywhere Help**: [help.pythonanywhere.com](https://help.pythonanywhere.com)
- **Flask Documentation**: [flask.palletsprojects.com](https://flask.palletsprojects.com)
- **Your Application Logs**: Check Web tab → Error logs

## 🎉 Success Checklist

- [ ] Web app is accessible
- [ ] Database is working
- [ ] User registration/login works
- [ ] Password reset emails work
- [ ] Static files load correctly
- [ ] Comic management functions work
- [ ] Error logs are clean
- [ ] SSL certificate is active

---

**Ready to deploy?** Follow these steps and your Comic Book Collection Manager will be live on PythonAnywhere! 🚀
