"""
Database Migration Script for Adding Rating System to AnimeWatchList
Fixed for SQLAlchemy 2.0+ compatibility

This script adds the user_rating column to the user_anime_list table.
Run this after deploying the updated code.
"""

import os
import sys
from sqlalchemy import text, inspect
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def add_rating_column():
    """Add user_rating column to user_anime_list table."""
    try:
        # Import the app after environment is loaded
        from app import app, db
        
        with app.app_context():
            print("Starting rating system migration...")
            
            # Test database connection (SQLAlchemy 2.0 compatible)
            try:
                with db.engine.connect() as connection:
                    result = connection.execute(text("SELECT 1 as test"))
                    test_row = result.fetchone()
                print("✅ Database connection successful")
            except Exception as e:
                print(f"❌ Database connection failed: {e}")
                return False
            
            # Check current table structure
            inspector = inspect(db.engine)
            existing_columns = [col['name'] for col in inspector.get_columns('user_anime_list')]
            print(f"📋 Current columns in user_anime_list table: {existing_columns}")
            
            # Add user_rating column if it doesn't exist
            if 'user_rating' not in existing_columns:
                try:
                    # Add user_rating column (nullable, 0-5 integer, NULL means not rated)
                    query = "ALTER TABLE user_anime_list ADD COLUMN user_rating INTEGER CHECK (user_rating >= 0 AND user_rating <= 5);"
                    
                    with db.engine.connect() as connection:
                        connection.execute(text(query))
                        connection.commit()
                    
                    print("✅ Added user_rating column")
                except Exception as e:
                    print(f"⚠️  Failed to add user_rating column: {e}")
                    return False
            else:
                print("✅ user_rating column already exists")
            
            # Commit all changes (if using session)
            try:
                db.session.commit()
            except:
                pass  # In case there's no active session
            
            print("\n🎉 Rating system migration completed successfully!")
            
            # Show final table structure
            final_columns = [col['name'] for col in inspector.get_columns('user_anime_list')]
            print(f"📋 Final user_anime_list table columns: {final_columns}")
            
            return True
            
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def verify_rating_migration():
    """Verify the rating migration was successful."""
    try:
        from app import app, db
        
        with app.app_context():
            inspector = inspect(db.engine)
            columns = [col['name'] for col in inspector.get_columns('user_anime_list')]
            
            print("\n📋 Rating Migration Verification:")
            
            if 'user_rating' in columns:
                print("✅ user_rating column present")
                
                # Test the constraint
                try:
                    # This should work
                    test_query = "SELECT COUNT(*) FROM user_anime_list WHERE user_rating IS NULL OR (user_rating >= 0 AND user_rating <= 5)"
                    
                    with db.engine.connect() as connection:
                        result = connection.execute(text(test_query))
                        count = result.scalar()
                    
                    print(f"✅ Rating constraint working, found {count} valid records")
                except Exception as e:
                    print(f"⚠️  Rating constraint check failed: {e}")
                    return False
            else:
                print("❌ user_rating column missing")
                return False
            
            return True
            
    except Exception as e:
        print(f"❌ Verification failed: {e}")
        return False

if __name__ == "__main__":
    print("AnimeWatchList Rating System Migration")
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
    success = add_rating_column()
    
    if success:
        print("\n🔍 Verifying migration...")
        if verify_rating_migration():
            print("\n✅ Migration and verification completed!")
            print("\nNext steps:")
            print("1. Refresh your application")
            print("2. Test the new rating features")
            print("3. Check that ratings are saved properly")
        else:
            print("\n⚠️  Migration completed but verification failed")
    else:
        print("\n❌ Migration failed. Check the errors above.")
        sys.exit(1)