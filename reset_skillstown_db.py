#!/usr/bin/env python3
"""
Database reset script for SkillsTown production environment.

This script will:
1. Drop existing SkillsTown tables with incorrect foreign key constraints
2. Recreate them with correct foreign key references to the 'user' table
3. Preserve user data in the 'user' table
"""

import os
import sys
from sqlalchemy import text

# Add project paths
project_root = os.path.dirname(os.path.abspath(__file__))
animewatchlist_path = os.path.join(project_root, 'projects/animewatchlist')
skillstown_path = os.path.join(project_root, 'projects/skillstown')

sys.path.insert(0, animewatchlist_path)
sys.path.insert(0, skillstown_path)

def reset_skillstown_tables():
    """Reset SkillsTown tables with correct foreign key constraints."""
    
    # Import after setting up paths
    from skillstown.app import create_app
    from animewatchlist.auth import db
    
    print("Creating SkillsTown app...")
    app = create_app('production')
    
    with app.app_context():
        print("Connected to database.")
        
        # Drop existing SkillsTown tables (but preserve user table)
        print("Dropping existing SkillsTown tables...")
        
        # Drop tables in reverse order of dependencies
        drop_commands = [
            "DROP TABLE IF EXISTS skillstown_user_courses CASCADE;",
            "DROP TABLE IF EXISTS skillstown_user_profiles CASCADE;", 
            "DROP TABLE IF EXISTS skillstown_courses CASCADE;"
        ]
        
        for command in drop_commands:
            try:
                db.session.execute(text(command))
                print(f"Executed: {command}")
            except Exception as e:
                print(f"Warning: {command} failed with: {e}")
        
        db.session.commit()
        print("Dropped existing SkillsTown tables.")
        
        # Recreate all tables (this will create SkillsTown tables with correct foreign keys)
        print("Creating tables with correct foreign key constraints...")
        db.create_all()
        print("Tables created successfully!")
        
        # Verify table creation
        print("Verifying table structure...")
        result = db.session.execute(text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name LIKE 'skillstown_%'
            ORDER BY table_name;
        """))
        
        tables = result.fetchall()
        print(f"SkillsTown tables found: {[table[0] for table in tables]}")
        
        # Check foreign key constraints
        result = db.session.execute(text("""
            SELECT 
                tc.constraint_name, 
                tc.table_name, 
                kcu.column_name, 
                ccu.table_name AS foreign_table_name,
                ccu.column_name AS foreign_column_name 
            FROM 
                information_schema.table_constraints AS tc 
                JOIN information_schema.key_column_usage AS kcu
                  ON tc.constraint_name = kcu.constraint_name
                JOIN information_schema.constraint_column_usage AS ccu
                  ON ccu.constraint_name = tc.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY' 
            AND tc.table_name LIKE 'skillstown_%';
        """))
        
        constraints = result.fetchall()
        print("\nForeign key constraints:")
        for constraint in constraints:
            print(f"  {constraint[1]}.{constraint[2]} -> {constraint[3]}.{constraint[4]}")
        
        print("\nDatabase reset completed successfully!")

if __name__ == "__main__":
    print("SkillsTown Database Reset Script")
    print("=" * 40)
    
    # Confirm we're in production mode
    if os.environ.get('RENDER'):
        print("Production environment detected (Render)")
    else:
        print("Local environment detected")
    
    # Check if DATABASE_URL is set
    if not os.environ.get('DATABASE_URL'):
        print("ERROR: DATABASE_URL environment variable not set!")
        sys.exit(1)
    
    response = input("This will drop and recreate SkillsTown tables. Continue? (yes/no): ")
    if response.lower() != 'yes':
        print("Operation cancelled.")
        sys.exit(0)
    
    try:
        reset_skillstown_tables()
        print("\n✅ Database reset completed successfully!")
        print("The SkillsTown application should now work correctly.")
    except Exception as e:
        print(f"\n❌ Error during database reset: {e}")
        sys.exit(1)
