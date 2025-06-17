# Spotify Cover Generator - Setup Guide

## Prerequisites

### System Requirements
- **Python:** 3.9 or higher
- **PostgreSQL:** 12 or higher
- **Redis:** 6 or higher (optional, for caching)
- **Git:** Latest version
- **Operating System:** Linux, macOS, or Windows

### Required API Keys
Before setting up the application, obtain the following API keys:

1. **Spotify Developer Account**
   - Visit: https://developer.spotify.com/dashboard
   - Create a new app
   - Note down Client ID and Client Secret

2. **Google Gemini API**
   - Visit: https://makersuite.google.com/app/apikey
   - Generate API key for Gemini

3. **Stability AI API**
   - Visit: https://platform.stability.ai/account/keys
   - Generate API key for image generation

## Local Development Setup

### 1. Clone the Repository
```bash
git clone https://github.com/yourusername/spotify-cover-generator.git
cd spotify-cover-generator
```

### 2. Create Virtual Environment
```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate
```

### 3. Install Dependencies
```bash
# Install Python dependencies
pip install -r requirements.txt

# Install development dependencies (optional)
pip install -r requirements-dev.txt
```

### 4. Database Setup

#### Option A: Local PostgreSQL
```bash
# Install PostgreSQL (Ubuntu/Debian)
sudo apt-get update
sudo apt-get install postgresql postgresql-contrib

# Create database and user
sudo -u postgres psql
CREATE DATABASE spotify_cover_gen;
CREATE USER spotify_user WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE spotify_cover_gen TO spotify_user;
\q
```

#### Option B: Docker PostgreSQL
```bash
# Run PostgreSQL in Docker
docker run --name postgres-spotify \
  -e POSTGRES_DB=spotify_cover_gen \
  -e POSTGRES_USER=spotify_user \
  -e POSTGRES_PASSWORD=your_password \
  -p 5432:5432 \
  -d postgres:13
```

### 5. Redis Setup (Optional)

#### Option A: Local Redis
```bash
# Install Redis (Ubuntu/Debian)
sudo apt-get install redis-server

# Start Redis
sudo systemctl start redis-server
sudo systemctl enable redis-server
```

#### Option B: Docker Redis
```bash
# Run Redis in Docker
docker run --name redis-spotify \
  -p 6379:6379 \
  -d redis:6-alpine
```

### 6. Environment Configuration
Create a `.env` file in the project root:

```bash
# Copy example environment file
cp .env.example .env
```

Edit `.env` with your configuration:
```env
# Flask Configuration
FLASK_SECRET_KEY=your-super-secret-key-here
FLASK_ENV=development
DEBUG=True

# Database Configuration
DATABASE_URL=postgresql://spotify_user:your_password@localhost:5432/spotify_cover_gen

# Redis Configuration (optional)
REDIS_URL=redis://localhost:6379/0

# Spotify API Configuration
SPOTIFY_CLIENT_ID=your_spotify_client_id
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
SPOTIFY_REDIRECT_URI=http://localhost:5000/callback

# Google Gemini API
GEMINI_API_KEY=your_gemini_api_key

# Stability AI Configuration
STABILITY_API_KEY=your_stability_api_key
STABILITY_HOST=https://api.stability.ai

# File Storage Configuration
UPLOAD_FOLDER=uploads
LORA_MODELS_FOLDER=lora_models

# Monitoring Configuration
SENTRY_DSN=your_sentry_dsn_here (optional)
LOG_LEVEL=INFO

# Rate Limiting
RATE_LIMIT_ENABLED=True
RATE_LIMIT_PER_MINUTE=10
```

### 7. Database Migration
```bash
# Initialize database
python -c "from app import db; db.create_all()"

# Run any pending migrations
python manage.py db upgrade
```

### 8. LoRA Models Setup (Optional)
```bash
# Create LoRA models directory
mkdir -p lora_models

# Download sample LoRA models (if you have any)
# Place .safetensors files in the lora_models directory
```

### 9. Run the Application
```bash
# Start the development server
python app.py

# Or use Flask CLI
flask run --debug

# Application will be available at http://localhost:5000
```

## Production Deployment

### 1. Environment Preparation
```bash
# Create production environment file
cp .env.example .env.production

# Update with production values
nano .env.production
```

### 2. Production Environment Variables
```env
FLASK_ENV=production
DEBUG=False
DATABASE_URL=postgresql://user:pass@prod-db-host:5432/spotify_cover_gen
REDIS_URL=redis://prod-redis-host:6379/0
# ... other production values
```

### 3. Docker Deployment

#### Build Docker Image
```bash
# Build production image
docker build -t spotify-cover-generator .

# Tag for registry
docker tag spotify-cover-generator your-registry/spotify-cover-generator:latest
```

#### Docker Compose Production
```yaml
# docker-compose.prod.yml
version: '3.8'
services:
  web:
    image: your-registry/spotify-cover-generator:latest
    ports:
      - "80:5000"
    environment:
      - FLASK_ENV=production
      - DATABASE_URL=postgresql://user:pass@db:5432/spotify_cover_gen
    depends_on:
      - db
      - redis
    restart: unless-stopped
    
  db:
    image: postgres:13
    environment:
      POSTGRES_DB: spotify_cover_gen
      POSTGRES_USER: user
      POSTGRES_PASSWORD: secure_password
    volumes:
      - postgres_data:/var/lib/postgresql/data
    restart: unless-stopped
    
  redis:
    image: redis:6-alpine
    restart: unless-stopped

volumes:
  postgres_data:
```

### 4. Render.com Deployment
```bash
# Create render.yaml for automatic deployment
cat > render.yaml << EOF
services:
  - type: web
    name: spotify-cover-generator
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: gunicorn --bind 0.0.0.0:$PORT app:app
    envVars:
      - key: FLASK_ENV
        value: production
      - key: DATABASE_URL
        fromDatabase:
          name: spotify-db
          property: connectionString
      # Add other environment variables
    
databases:
  - name: spotify-db
    databaseName: spotify_cover_gen
    user: spotify_user
EOF
```

### 5. Heroku Deployment
```bash
# Install Heroku CLI and login
heroku login

# Create Heroku app
heroku create your-app-name

# Add PostgreSQL addon
heroku addons:create heroku-postgresql:hobby-dev

# Add Redis addon
heroku addons:create heroku-redis:hobby-dev

# Set environment variables
heroku config:set FLASK_SECRET_KEY=your-secret-key
heroku config:set SPOTIFY_CLIENT_ID=your-client-id
# ... set other variables

# Deploy
git push heroku main
```

## Development Workflow

### 1. Running Tests
```bash
# Run all tests
pytest

# Run specific test file
pytest tests/unit/test_models.py

# Run with coverage
pytest --cov=. --cov-report=html

# Run linting
flake8 .

# Run formatting check
black --check .
```

### 2. Code Quality Checks
```bash
# Run security scan
bandit -r . -x tests/

# Check dependencies
safety check

# Type checking (if using mypy)
mypy .
```

### 3. Database Operations
```bash
# Create new migration
python manage.py db migrate -m "Description of changes"

# Apply migrations
python manage.py db upgrade

# Rollback migration
python manage.py db downgrade
```

### 4. Debugging
```bash
# Enable debug mode
export FLASK_ENV=development
export DEBUG=True

# Run with verbose logging
export LOG_LEVEL=DEBUG
python app.py
```

## Monitoring Setup

### 1. Health Checks
The application includes built-in health checks at `/health`:
```bash
# Check application health
curl http://localhost:5000/health
```

### 2. Logging Configuration
```python
# logging.conf
[loggers]
keys=root,app

[handlers]
keys=console,file

[formatters]
keys=standard

[logger_root]
level=INFO
handlers=console

[logger_app]
level=DEBUG
handlers=console,file
qualname=app
propagate=0

[handler_console]
class=StreamHandler
level=INFO
formatter=standard
args=(sys.stdout,)

[handler_file]
class=handlers.RotatingFileHandler
level=DEBUG
formatter=standard
args=('app.log', 'a', 1000000, 5)

[formatter_standard]
format=%(asctime)s [%(levelname)s] %(name)s: %(message)s
```

### 3. Performance Monitoring
```bash
# Install monitoring tools
pip install psutil prometheus_client

# Add monitoring endpoints
# /metrics - Prometheus metrics
# /health - Health status
```

## Troubleshooting

### Common Issues

#### 1. Database Connection Error
```bash
# Check PostgreSQL status
sudo systemctl status postgresql

# Check connection
psql -h localhost -U spotify_user -d spotify_cover_gen
```

#### 2. Redis Connection Error
```bash
# Check Redis status
redis-cli ping

# Should return PONG
```

#### 3. API Key Issues
- Verify all API keys are correctly set in `.env`
- Check API key permissions and quotas
- Ensure Spotify redirect URI matches your configuration

#### 4. Import Errors
```bash
# Reinstall dependencies
pip install --force-reinstall -r requirements.txt

# Check Python path
python -c "import sys; print(sys.path)"
```

#### 5. File Permission Issues
```bash
# Fix file permissions
chmod +x scripts/*.sh
mkdir -p uploads lora_models
chmod 755 uploads lora_models
```

### Performance Issues
1. **Slow API Responses:** Check external API rate limits
2. **High Memory Usage:** Optimize image processing and caching
3. **Database Slow Queries:** Add database indexes and optimize queries

### Security Checklist
- [ ] All sensitive data in environment variables
- [ ] HTTPS enabled in production
- [ ] Database credentials secure
- [ ] API keys not in version control
- [ ] CORS properly configured
- [ ] Rate limiting enabled

## Additional Resources

### Documentation
- [Flask Documentation](https://flask.palletsprojects.com/)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [