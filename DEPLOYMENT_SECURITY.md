# Deployment Security Guide

## Secret Key Management for Production

### 🔐 Critical Security Requirements

1. **NEVER** commit secret keys to version control
2. **ALWAYS** use environment variables for secrets in production
3. **GENERATE** a unique, cryptographically secure secret key for each environment

### 🚀 Pre-Deployment Checklist

#### 1. Generate a Secure Secret Key
```bash
# Generate a 64-character hex secret key
python -c "import secrets; print(secrets.token_hex(32))"

# Or generate a URL-safe base64 key
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

#### 2. Set Environment Variables
For your hosting platform, set these environment variables:

**Required:**
- `SECRET_KEY` - Your generated secret key
- `FLASK_ENV=production`
- `FLASK_DEBUG=False`

**Optional but recommended:**
- `DATABASE_URL` - Production database connection string
- `COMICVINE_API_KEY` - Your ComicVine API key
- `MARVEL_API_KEY` - Your Marvel API key
- `MARVEL_PRIVATE_KEY` - Your Marvel private key

### 🌐 Platform-Specific Instructions

#### Heroku
```bash
heroku config:set SECRET_KEY="your-generated-secret-key"
heroku config:set FLASK_ENV=production
heroku config:set FLASK_DEBUG=False
```

#### Railway
Set environment variables in the Railway dashboard under your project settings.

#### DigitalOcean App Platform
Add environment variables in the App Spec or through the dashboard.

#### AWS/Google Cloud/Azure
Use their respective secrets management services:
- AWS: AWS Secrets Manager or Parameter Store
- Google Cloud: Secret Manager
- Azure: Key Vault

### 🔒 Additional Security Measures

1. **Use HTTPS** - Always deploy with SSL/TLS certificates
2. **Database Security** - Use strong database passwords and connection strings
3. **API Key Rotation** - Regularly rotate your API keys
4. **Environment Separation** - Use different secret keys for dev/staging/production
5. **Access Control** - Limit who has access to production environment variables

### ⚠️ Common Mistakes to Avoid

- ❌ Using the same secret key across environments
- ❌ Committing `.env` files to version control
- ❌ Using weak or predictable secret keys
- ❌ Running with `debug=True` in production
- ❌ Exposing secret keys in logs or error messages

### 🧪 Testing Your Configuration

Before deploying, test that your app starts correctly with production settings:

```bash
# Set production environment variables locally
export SECRET_KEY="your-generated-secret-key"
export FLASK_ENV=production
export FLASK_DEBUG=False

# Test the application
python run_production.py
```

### 📝 Environment Variable Template

Create a secure `.env.production` file (never commit this):

```env
# Production Environment Variables
SECRET_KEY=your-generated-64-character-secret-key
FLASK_ENV=production
FLASK_DEBUG=False
DATABASE_URL=postgresql://user:password@host:port/database
COMICVINE_API_KEY=your-comicvine-api-key
MARVEL_API_KEY=your-marvel-api-key
MARVEL_PRIVATE_KEY=your-marvel-private-key
```

Remember: This file should never be committed to version control!
