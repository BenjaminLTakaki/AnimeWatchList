#!/usr/bin/env python3
"""
Render-specific database migration script
This runs automatically when your Render service starts
"""

import os
import sys
from pathlib import Path

def setup_for_render():
    """Setup the environment for Render deployment"""
    # Render sets these automatically
    if not os.getenv('RENDER'):
        print("⚠️ Not running on Render, setting RENDER=true for testing")
        os.environ['RENDER'] = 'true'
    
    # Get database URL from Render environment
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print("❌ DATABASE_URL not found in environment")
        return False
    
    print(f"🔗 Using Render database: {database_url[:50]}...")
    return True

def migrate_database():
    """Run database migration suitable for Render"""
    try:
        from flask import Flask
        from flask_sqlalchemy import SQLAlchemy
        from sqlalchemy import text, inspect
        
        # Get database URL
        database_url = os.getenv('DATABASE_URL')
        
        # Fix postgres:// to postgresql:// if needed
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
        
        # Create minimal Flask app
        app = Flask(__name__)
        app.config['SQLALCHEMY_DATABASE_URI'] = database_url
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        
        db = SQLAlchemy(app)
        
        with app.app_context():
            print("📊 Connecting to Render database...")
            
            # Test connection
            try:
                with db.engine.connect() as conn:
                    conn.execute(text('SELECT 1'))
                print("✅ Database connection successful")
            except Exception as e:
                print(f"❌ Database connection failed: {e}")
                return False
            
            # Check PostgreSQL version for syntax compatibility
            try:
                result = db.session.execute(text("SELECT version()"))
                version_info = result.fetchone()[0]
                print(f"📋 PostgreSQL: {version_info.split(',')[0]}")
            except:
                pass
            
            # Create tables with Render-compatible SQL
            print("🔧 Creating missing tables...")
            
            tables_sql = [
                """
                CREATE TABLE IF NOT EXISTS spotify_users (
                    id SERIAL PRIMARY KEY,
                    email VARCHAR(120) UNIQUE,
                    username VARCHAR(80) UNIQUE,
                    password_hash VARCHAR(200),
                    spotify_id VARCHAR(100) UNIQUE,
                    spotify_username VARCHAR(100),
                    spotify_access_token VARCHAR(500),
                    spotify_refresh_token VARCHAR(500),
                    spotify_token_expires TIMESTAMP,
                    display_name VARCHAR(100),
                    is_premium BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP,
                    is_active BOOLEAN DEFAULT TRUE
                );
                """,
                
                """
                CREATE TABLE IF NOT EXISTS spotify_login_sessions (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    session_token VARCHAR(100) UNIQUE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL,
                    is_active BOOLEAN DEFAULT TRUE,
                    ip_address VARCHAR(45),
                    user_agent VARCHAR(500)
                );
                """,
                
                """
                CREATE TABLE IF NOT EXISTS spotify_oauth_states (
                    id SERIAL PRIMARY KEY,
                    state VARCHAR(100) UNIQUE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    used BOOLEAN DEFAULT FALSE
                );
                """,
                
                """
                CREATE TABLE IF NOT EXISTS spotify_lora_models (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100) UNIQUE NOT NULL,
                    source_type VARCHAR(20) DEFAULT 'local',
                    path VARCHAR(500) DEFAULT '',
                    file_size INTEGER DEFAULT 0,
                    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    uploaded_by INTEGER
                );
                """,
                
                """
                CREATE TABLE IF NOT EXISTS spotify_generation_results (
                    id SERIAL PRIMARY KEY,
                    title VARCHAR(500) NOT NULL,
                    output_path VARCHAR(1000) NOT NULL,
                    item_name VARCHAR(500),
                    genres JSON,
                    all_genres JSON,
                    style_elements JSON,
                    mood VARCHAR(1000),
                    energy_level VARCHAR(50),
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    spotify_url VARCHAR(1000),
                    lora_name VARCHAR(200),
                    lora_type VARCHAR(20),
                    lora_url VARCHAR(1000),
                    user_id INTEGER
                );
                """
            ]
            
            # Execute table creation
            for i, sql in enumerate(tables_sql, 1):
                try:
                    db.session.execute(text(sql))
                    db.session.commit()
                    print(f"✅ Table {i}/5 created/verified")
                except Exception as e:
                    print(f"⚠️ Table {i}/5 warning: {e}")
                    db.session.rollback()
            
            # Add missing user_id column if needed
            print("🔧 Checking for missing columns...")
            try:
                inspector = inspect(db.engine)
                gen_columns = [col['name'] for col in inspector.get_columns('spotify_generation_results')]
                
                if 'user_id' not in gen_columns:
                    print("Adding user_id column...")
                    db.session.execute(text("""
                        ALTER TABLE spotify_generation_results 
                        ADD COLUMN user_id INTEGER
                    """))
                    db.session.commit()
                    print("✅ Added user_id column")
                else:
                    print("✅ user_id column already exists")
            except Exception as e:
                print(f"⚠️ Column check warning: {e}")
                db.session.rollback()
            
            # Add foreign key constraints with error handling
            print("🔧 Adding foreign key constraints...")
            
            constraints = [
                """
                DO $$ 
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.table_constraints 
                        WHERE constraint_name = 'fk_login_sessions_user_id'
                    ) THEN
                        ALTER TABLE spotify_login_sessions 
                        ADD CONSTRAINT fk_login_sessions_user_id 
                        FOREIGN KEY (user_id) REFERENCES spotify_users(id) ON DELETE CASCADE;
                    END IF;
                END $$;
                """,
                """
                DO $$ 
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.table_constraints 
                        WHERE constraint_name = 'fk_generation_results_user_id'
                    ) THEN
                        ALTER TABLE spotify_generation_results 
                        ADD CONSTRAINT fk_generation_results_user_id 
                        FOREIGN KEY (user_id) REFERENCES spotify_users(id) ON DELETE SET NULL;
                    END IF;
                END $$;
                """,
                """
                DO $$ 
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.table_constraints 
                        WHERE constraint_name = 'fk_lora_models_uploaded_by'
                    ) THEN
                        ALTER TABLE spotify_lora_models 
                        ADD CONSTRAINT fk_lora_models_uploaded_by 
                        FOREIGN KEY (uploaded_by) REFERENCES spotify_users(id) ON DELETE SET NULL;
                    END IF;
                END $$;
                """
            ]
            
            for i, sql in enumerate(constraints, 1):
                try:
                    db.session.execute(text(sql))
                    db.session.commit()
                    print(f"✅ Constraint {i}/3 added")
                except Exception as e:
                    print(f"⚠️ Constraint {i}/3 warning: {e}")
                    db.session.rollback()
            
            # Create indexes for performance
            print("🔧 Creating indexes...")
            indexes = [
                "CREATE INDEX IF NOT EXISTS idx_users_email ON spotify_users(email);",
                "CREATE INDEX IF NOT EXISTS idx_users_spotify_id ON spotify_users(spotify_id);",
                "CREATE INDEX IF NOT EXISTS idx_sessions_token ON spotify_login_sessions(session_token);",
                "CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON spotify_login_sessions(user_id);",
                "CREATE INDEX IF NOT EXISTS idx_generations_user_id ON spotify_generation_results(user_id);"
            ]
            
            for sql in indexes:
                try:
                    db.session.execute(text(sql))
                    db.session.commit()
                except Exception as e:
                    print(f"⚠️ Index warning: {e}")
                    db.session.rollback()
            
            print("✅ Indexes created")
            
            # Final verification
            print("🔍 Verifying setup...")
            inspector = inspect(db.engine)
            tables = inspector.get_table_names()
            
            required_tables = [
                'spotify_users', 'spotify_login_sessions', 'spotify_oauth_states',
                'spotify_generation_results', 'spotify_lora_models'
            ]
            
            missing = [t for t in required_tables if t not in tables]
            if missing:
                print(f"❌ Still missing tables: {missing}")
                return False
            
            # Check user_id column
            gen_columns = [col['name'] for col in inspector.get_columns('spotify_generation_results')]
            if 'user_id' not in gen_columns:
                print("❌ user_id column still missing")
                return False
            
            print("🎉 Database migration completed successfully!")
            return True
            
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main function for Render deployment"""
    print("🚀 Render Database Migration Starting...")
    print("=" * 50)
    
    if not setup_for_render():
        return False
    
    success = migrate_database()
    
    if success:
        print("=" * 50)
        print("✅ Migration completed - your app should now work!")
    else:
        print("=" * 50)
        print("❌ Migration failed - check logs above")
    
    return success

if __name__ == "__main__":
    success = main()
    # Don't exit with error code on Render to allow app to continue starting
    # Render will restart the service if needed
    sys.exit(0)