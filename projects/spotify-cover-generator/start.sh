#!/bin/bash

# Render startup script for Spotify Cover Generator
# This runs before your main application starts

echo "🚀 Starting Spotify Cover Generator on Render..."
echo "=============================================="

# Check if we're on Render
if [ -z "$RENDER" ]; then
    echo "⚠️ RENDER environment variable not set"
    export RENDER=true
fi

echo "📍 Environment: Render"
echo "🐍 Python version: $(python --version)"
echo "📊 Database URL: ${DATABASE_URL:0:50}..."

# Step 1: Run database migration
echo ""
echo "📊 Step 1: Running database migration..."
python render_db_fix.py

if [ $? -eq 0 ]; then
    echo "✅ Database migration completed"
else
    echo "⚠️ Database migration had warnings, continuing..."
fi

# Step 2: Run database upgrade (Flask-Migrate)
echo ""
echo "📊 Step 2: Running Flask-Migrate upgrade..."
python -c "
try:
    from flask_migrate import upgrade
    from app import app
    with app.app_context():
        upgrade()
    print('✅ Flask-Migrate upgrade completed')
except Exception as e:
    print(f'⚠️ Flask-Migrate upgrade warning: {e}')
"

# Step 3: Quick verification
echo ""
echo "🔍 Step 3: Quick verification..."
python -c "
try:
    import os
    from sqlalchemy import create_engine, text, inspect
    
    db_url = os.getenv('DATABASE_URL')
    if db_url.startswith('postgres://'):
        db_url = db_url.replace('postgres://', 'postgresql://', 1)
    
    engine = create_engine(db_url)
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    
    required = ['spotify_users', 'spotify_login_sessions', 'spotify_oauth_states', 
                'spotify_generation_results', 'spotify_lora_models']
    missing = [t for t in required if t not in tables]
    
    if missing:
        print(f'⚠️ Missing tables: {missing}')
    else:
        print('✅ All required tables present')
        
    # Check user_id column
    gen_cols = [col['name'] for col in inspector.get_columns('spotify_generation_results')]
    if 'user_id' in gen_cols:
        print('✅ user_id column present')
    else:
        print('⚠️ user_id column missing')
        
except Exception as e:
    print(f'⚠️ Verification warning: {e}')
"

echo ""
echo "🎉 Startup preparation completed!"
echo "🚀 Starting main application..."
echo ""

# Step 4: Start the main application
# Render will use the command specified in your service configuration
# This is usually something like: gunicorn wsgi:application
# So we don't need to start it here, just ensure the prep is done

echo "✅ Ready for main application startup"