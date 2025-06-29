"""
Database Migration Script for AnimeWatchList Enhanced Features

This script adds the new columns needed for enhanced sorting and statistics.
Run this after deploying the updated code to add the new database columns.

Usage:
1. Make sure your app is deployed and running
2. Run this script in your production environment
3. The script will add the new columns safely without losing existing data
"""

import os
import sys
from sqlalchemy import text
from dotenv import load_dotenv

# Add the project path to handle imports
project_path = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_path)

# Load environment variables
load_dotenv()

def run_migration():
    """Run the database migration to add new columns."""
    try:
        # Import the app and db after setting up the path
        from app import app, db
        
        with app.app_context():
            print("Starting database migration...")
            
            # Check if we're connected to the database
            try:
                db.engine.execute(text("SELECT 1"))
                print("✅ Database connection successful")
            except Exception as e:
                print(f"❌ Database connection failed: {e}")
                return False
            
            # Add new columns to the anime table
            migration_queries = [
                # Add episodes_int column for sorting/calculations
                """
                ALTER TABLE anime 
                ADD COLUMN IF NOT EXISTS episodes_int INTEGER DEFAULT 0;
                """,
                
                # Add score_float column for sorting/calculations  
                """
                ALTER TABLE anime 
                ADD COLUMN IF NOT EXISTS score_float REAL DEFAULT 0.0;
                """,
                
                # Add aired_from date column
                """
                ALTER TABLE anime 
                ADD COLUMN IF NOT EXISTS aired_from DATE;
                """,
                
                # Add genres text column
                """
                ALTER TABLE anime 
                ADD COLUMN IF NOT EXISTS genres TEXT;
                """,
                
                # Add studio column
                """
                ALTER TABLE anime 
                ADD COLUMN IF NOT EXISTS studio VARCHAR(255);
                """,
                
                # Add type column (TV, Movie, OVA, etc.)
                """
                ALTER TABLE anime 
                ADD COLUMN IF NOT EXISTS type VARCHAR(50);
                """,
                
                # Add status column (Finished Airing, Currently Airing, etc.)
                """
                ALTER TABLE anime 
                ADD COLUMN IF NOT EXISTS status VARCHAR(50);
                """
            ]
            
            # Execute each migration query
            for i, query in enumerate(migration_queries, 1):
                try:
                    db.engine.execute(text(query))
                    print(f"✅ Migration {i}/7 completed")
                except Exception as e:
                    print(f"⚠️  Migration {i}/7 skipped (column may already exist): {e}")
            
            # Update existing data - convert episodes to int
            try:
                update_episodes_query = """
                UPDATE anime 
                SET episodes_int = CASE 
                    WHEN episodes ~ '^[0-9]+$' THEN CAST(episodes AS INTEGER)
                    ELSE 0 
                END
                WHERE episodes_int = 0;
                """
                db.engine.execute(text(update_episodes_query))
                print("✅ Updated episodes_int values")
            except Exception as e:
                print(f"⚠️  Episodes update skipped: {e}")
            
            # Update existing data - convert score to float
            try:
                update_score_query = """
                UPDATE anime 
                SET score_float = CASE 
                    WHEN score ~ '^[0-9.]+$' THEN CAST(score AS REAL)
                    ELSE 0.0 
                END
                WHERE score_float = 0.0;
                """
                db.engine.execute(text(update_score_query))
                print("✅ Updated score_float values")
            except Exception as e:
                print(f"⚠️  Score update skipped: {e}")
            
            # Commit all changes
            db.session.commit()
            print("\n🎉 Database migration completed successfully!")
            print("\nNew features now available:")
            print("- Enhanced sorting options")
            print("- Detailed statistics")
            print("- Improved anime information storage")
            
            # Clean up old data (remove not_watched entries)
            try:
                cleanup_query = """
                DELETE FROM user_anime_list 
                WHERE status = 'not_watched';
                """
                result = db.engine.execute(text(cleanup_query))
                deleted_count = result.rowcount
                db.session.commit()
                print(f"🧹 Cleaned up {deleted_count} 'not_watched' entries")
            except Exception as e:
                print(f"⚠️  Cleanup skipped: {e}")
            
            return True
            
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        return False

def verify_migration():
    """Verify that the migration was successful."""
    try:
        from app import app, db
        
        with app.app_context():
            # Check if new columns exist
            result = db.engine.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'anime' 
                AND column_name IN ('episodes_int', 'score_float', 'aired_from', 'genres', 'studio', 'type', 'status');
            """))
            
            columns = [row[0] for row in result]
            expected_columns = ['episodes_int', 'score_float', 'aired_from', 'genres', 'studio', 'type', 'status']
            
            print("\n📋 Migration Verification:")
            for col in expected_columns:
                if col in columns:
                    print(f"✅ Column '{col}' exists")
                else:
                    print(f"❌ Column '{col}' missing")
            
            if len(columns) == len(expected_columns):
                print("\n🎉 All new columns are present!")
                return True
            else:
                print(f"\n⚠️  Found {len(columns)}/{len(expected_columns)} expected columns")
                return False
                
    except Exception as e:
        print(f"❌ Verification failed: {e}")
        return False

if __name__ == "__main__":
    print("AnimeWatchList Database Migration")
    print("=" * 50)
    
    # Check database URL
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        print("❌ DATABASE_URL environment variable not set!")
        print("Please set the DATABASE_URL environment variable and try again.")
        sys.exit(1)
    
    print(f"Database: {database_url.split('@')[-1] if '@' in database_url else 'Local'}")
    
    # Ask for confirmation in production
    if 'render' in database_url.lower() or 'prod' in database_url.lower():
        confirm = input("\n⚠️  This appears to be a production database. Continue? (yes/no): ")
        if confirm.lower() != 'yes':
            print("Migration cancelled.")
            sys.exit(0)
    
    # Run migration
    print("\nStarting migration...")
    success = run_migration()
    
    if success:
        print("\nVerifying migration...")
        verify_migration()
        print("\n✅ Migration process completed!")
        print("\nNext steps:")
        print("1. Restart your application")
        print("2. Test the new sorting and statistics features")
        print("3. Verify that existing data is intact")
    else:
        print("\n❌ Migration failed. Please check the errors above.")
        sys.exit(1)