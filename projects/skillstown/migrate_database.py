#!/usr/bin/env python3
"""
Database migration script for SkillsTown application
Run this script to add missing columns to existing tables
"""

import os
import sys
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.exc import SQLAlchemyError

def get_database_url():
    """Get database URL from environment or use default"""
    db_url = os.environ.get('DATABASE_URL')
    if db_url and db_url.startswith('postgres://'):
        db_url = db_url.replace('postgres://', 'postgresql://')
    return db_url or 'sqlite:///skillstown.db'

def migrate_skillstown_tables():
    """Add missing columns to SkillsTown tables"""
    db_url = get_database_url()
    engine = create_engine(db_url)
    
    try:
        with engine.connect() as conn:
            # Check if we're using PostgreSQL or SQLite
            is_postgres = 'postgresql' in db_url
            
            print(f"Connected to database: {'PostgreSQL' if is_postgres else 'SQLite'}")
            
            # Get table inspector
            inspector = inspect(engine)
            
            # Check if skillstown_user_profiles table exists
            if 'skillstown_user_profiles' in inspector.get_table_names():
                print("Found skillstown_user_profiles table")
                
                # Get existing columns
                columns = [col['name'] for col in inspector.get_columns('skillstown_user_profiles')]
                print(f"Existing columns: {columns}")
                
                # Add job_description column if missing
                if 'job_description' not in columns:
                    print("Adding job_description column...")
                    try:
                        conn.execute(text("ALTER TABLE skillstown_user_profiles ADD COLUMN job_description TEXT"))
                        conn.commit()
                        print("✓ Successfully added job_description column")
                    except SQLAlchemyError as e:
                        print(f"✗ Error adding job_description column: {e}")
                        conn.rollback()
                else:
                    print("✓ job_description column already exists")
                
                # Add any other missing columns here
                missing_columns = []
                expected_columns = {
                    'id': 'INTEGER PRIMARY KEY',
                    'user_id': 'INTEGER NOT NULL',
                    'cv_text': 'TEXT',
                    'job_description': 'TEXT',
                    'skills': 'TEXT',
                    'skill_analysis': 'TEXT',
                    'uploaded_at': 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP'
                }
                
                for col_name, col_type in expected_columns.items():
                    if col_name not in columns:
                        missing_columns.append((col_name, col_type))
                
                # Add missing columns
                for col_name, col_type in missing_columns:
                    if col_name != 'job_description':  # Already handled above
                        print(f"Adding {col_name} column...")
                        try:
                            conn.execute(text(f"ALTER TABLE skillstown_user_profiles ADD COLUMN {col_name} {col_type}"))
                            conn.commit()
                            print(f"✓ Successfully added {col_name} column")
                        except SQLAlchemyError as e:
                            print(f"✗ Error adding {col_name} column: {e}")
                            conn.rollback()
            
            else:
                print("skillstown_user_profiles table not found - will be created by Flask app")
            
            # Check skillstown_user_courses table
            if 'skillstown_user_courses' in inspector.get_table_names():
                print("\nFound skillstown_user_courses table")
                courses_columns = [col['name'] for col in inspector.get_columns('skillstown_user_courses')]
                print(f"Existing columns: {courses_columns}")
                
                expected_courses_columns = {
                    'id': 'INTEGER PRIMARY KEY',
                    'user_id': 'INTEGER NOT NULL',
                    'category': 'VARCHAR(100) NOT NULL',
                    'course_name': 'VARCHAR(255) NOT NULL',
                    'status': 'VARCHAR(50) DEFAULT \'enrolled\'',
                    'created_at': 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP'
                }
                
                for col_name, col_type in expected_courses_columns.items():
                    if col_name not in courses_columns:
                        print(f"Adding {col_name} column to user_courses...")
                        try:
                            conn.execute(text(f"ALTER TABLE skillstown_user_courses ADD COLUMN {col_name} {col_type}"))
                            conn.commit()
                            print(f"✓ Successfully added {col_name} column")
                        except SQLAlchemyError as e:
                            print(f"✗ Error adding {col_name} column: {e}")
                            conn.rollback()
            
            else:
                print("skillstown_user_courses table not found - will be created by Flask app")
            
            print("\n✓ Migration completed successfully!")
            
    except SQLAlchemyError as e:
        print(f"✗ Database connection error: {e}")
        return False
    
    return True

def verify_migration():
    """Verify that the migration was successful"""
    db_url = get_database_url()
    engine = create_engine(db_url)
    
    try:
        with engine.connect() as conn:
            inspector = inspect(engine)
            
            # Check skillstown_user_profiles
            if 'skillstown_user_profiles' in inspector.get_table_names():
                columns = [col['name'] for col in inspector.get_columns('skillstown_user_profiles')]
                required_columns = ['id', 'user_id', 'cv_text', 'job_description', 'skills', 'skill_analysis', 'uploaded_at']
                
                missing = [col for col in required_columns if col not in columns]
                if missing:
                    print(f"✗ Missing columns in skillstown_user_profiles: {missing}")
                    return False
                else:
                    print("✓ skillstown_user_profiles table structure is correct")
            
            # Check skillstown_user_courses
            if 'skillstown_user_courses' in inspector.get_table_names():
                columns = [col['name'] for col in inspector.get_columns('skillstown_user_courses')]
                required_columns = ['id', 'user_id', 'category', 'course_name', 'status', 'created_at']
                
                missing = [col for col in required_columns if col not in columns]
                if missing:
                    print(f"✗ Missing columns in skillstown_user_courses: {missing}")
                    return False
                else:
                    print("✓ skillstown_user_courses table structure is correct")
                    
            return True
            
    except SQLAlchemyError as e:
        print(f"✗ Verification error: {e}")
        return False

def main():
    """Main migration function"""
    print("SkillsTown Database Migration Tool")
    print("=" * 40)
    
    # Run migration
    if migrate_skillstown_tables():
        print("\nVerifying migration...")
        if verify_migration():
            print("\n🎉 Migration completed and verified successfully!")
            print("\nYou can now run your Flask application.")
        else:
            print("\n⚠️  Migration completed but verification failed.")
            print("Please check the database manually.")
    else:
        print("\n❌ Migration failed. Please check the error messages above.")
        sys.exit(1)

if __name__ == '__main__':
    main()