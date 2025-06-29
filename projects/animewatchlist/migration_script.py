"""
Simple Database Migration Script for AnimeWatchList

This script safely adds new columns to the anime table and cleans up old data.
Run this after deploying the updated code.
"""

import os
import sys
from sqlalchemy import text, inspect
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def run_simple_migration():
    """Run a simple, safe migration to add new columns."""
    try:
        # Import the app after environment is loaded
        from app import app, db
        
        with app.app_context():
            print("Starting simple database migration...")
            
            # Test database connection
            try:
                result = db.engine.execute(text("SELECT 1 as test"))
                print("✅ Database connection successful")
            except Exception as e:
                print(f"❌ Database connection failed: {e}")
                return False
            
            # Check current table structure
            inspector = inspect(db.engine)
            existing_columns = [col['name'] for col in inspector.get_columns('anime')]
            print(f"📋 Current columns in anime table: {existing_columns}")
            
            # Define new columns to add
            new_columns = [
                ('episodes_int', 'INTEGER DEFAULT 0'),
                ('score_float', 'REAL DEFAULT 0.0'),
                ('aired_from', 'DATE'),
                ('genres', 'TEXT'),
                ('studio', 'VARCHAR(255)'),
                ('type', 'VARCHAR(50)'),
                ('status', 'VARCHAR(50)')
            ]
            
            # Add new columns if they don't exist
            for column_name, column_def in new_columns:
                if column_name not in existing_columns:
                    try:
                        query = f"ALTER TABLE anime ADD COLUMN {column_name} {column_def};"
                        db.engine.execute(text(query))
                        print(f"✅ Added column: {column_name}")
                    except Exception as e:
                        print(f"⚠️  Failed to add column {column_name}: {e}")
                else:
                    print(f"✅ Column {column_name} already exists")
            
            # Update existing data if new columns were added
            if 'episodes_int' in [col[0] for col in new_columns]:
                try:
                    # Update episodes_int from episodes string
                    update_episodes = """
                    UPDATE anime 
                    SET episodes_int = CASE 
                        WHEN episodes ~ '^[0-9]+$' THEN CAST(episodes AS INTEGER)
                        ELSE 0 
                    END
                    WHERE episodes_int = 0 OR episodes_int IS NULL;
                    """
                    db.engine.execute(text(update_episodes))
                    print("✅ Updated episodes_int values")
                except Exception as e:
                    print(f"⚠️  Could not update episodes_int: {e}")
            
            if 'score_float' in [col[0] for col in new_columns]:
                try:
                    # Update score_float from score string
                    update_score = """
                    UPDATE anime 
                    SET score_float = CASE 
                        WHEN score ~ '^[0-9.]+$' THEN CAST(score AS REAL)
                        ELSE 0.0 
                    END
                    WHERE score_float = 0 OR score_float IS NULL;
                    """
                    db.engine.execute(text(update_score))
                    print("✅ Updated score_float values")
                except Exception as e:
                    print(f"⚠️  Could not update score_float: {e}")
            
            # Clean up old not_watched entries
            try:
                cleanup_result = db.engine.execute(text("""
                    DELETE FROM user_anime_list 
                    WHERE status = 'not_watched';
                """))
                deleted_count = cleanup_result.rowcount
                print(f"🧹 Cleaned up {deleted_count} 'not_watched' entries")
            except Exception as e:
                print(f"⚠️  Cleanup warning: {e}")
            
            # Commit all changes
            db.session.commit()
            print("\n🎉 Migration completed successfully!")
            
            # Show final table structure
            final_columns = [col['name'] for col in inspector.get_columns('anime')]
            print(f"📋 Final anime table columns: {final_columns}")
            
            return True
            
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def verify_migration():
    """Verify the migration was successful."""
    try:
        from app import app, db
        
        with app.app_context():
            inspector = inspect(db.engine)
            columns = [col['name'] for col in inspector.get_columns('anime')]
            
            required_columns = ['id', 'mal_id', 'title', 'episodes', 'image_url', 'score']
            optional_columns = ['episodes_int', 'score_float', 'aired_from', 'genres', 'studio', 'type', 'status']
            
            print("\n📋 Migration Verification:")
            
            # Check required columns
            missing_required = [col for col in required_columns if col not in columns]
            if missing_required:
                print(f"❌ Missing required columns: {missing_required}")
                return False
            else:
                print("✅ All required columns present")
            
            # Check optional columns
            present_optional = [col for col in optional_columns if col in columns]
            print(f"✅ Optional columns present: {present_optional}")
            
            # Test basic functionality
            try:
                result = db.engine.execute(text("SELECT COUNT(*) FROM anime"))
                anime_count = result.scalar()
                print(f"✅ Anime table accessible with {anime_count} records")
            except Exception as e:
                print(f"❌ Could not access anime table: {e}")
                return False
            
            return True
            
    except Exception as e:
        print(f"❌ Verification failed: {e}")
        return False

if __name__ == "__main__":
    print("AnimeWatchList Simple Migration")
    print("=" * 40)
    
    # Check if we're in the right directory
    if not os.path.exists('app.py'):
        print("❌ Migration script must be run from the animewatchlist directory")
        print("Please cd to projects/animewatchlist and run again")
        sys.exit(1)
    
    # Check database URL
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        print("❌ DATABASE_URL environment variable not set!")
        sys.exit(1)
    
    print(f"📍 Working directory: {os.getcwd()}")
    print(f"🗄️  Database: {database_url.split('@')[-1] if '@' in database_url else 'Local'}")
    
    # Run migration
    print("\n🚀 Starting migration...")
    success = run_simple_migration()
    
    if success:
        print("\n🔍 Verifying migration...")
        if verify_migration():
            print("\n✅ Migration and verification completed!")
            print("\nNext steps:")
            print("1. Refresh your application")
            print("2. Test the new sorting features")
            print("3. Check the statistics page")
        else:
            print("\n⚠️  Migration completed but verification failed")
    else:
        print("\n❌ Migration failed. Check the errors above.")
        sys.exit(1)