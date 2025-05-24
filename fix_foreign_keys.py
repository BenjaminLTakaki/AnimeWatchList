#!/usr/bin/env python3
"""
Fix foreign key constraints in existing Render database.
This script updates the foreign key constraints to point to the correct 'user' table.
"""

import os
import sys
import psycopg2
from urllib.parse import urlparse

def fix_foreign_keys():
    """Fix foreign key constraints in the existing database"""
    
    # Get database URL from environment
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        print("ERROR: DATABASE_URL environment variable not set!")
        return False
    
    # Parse the database URL
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    
    try:
        # Connect to database
        print("Connecting to database...")
        conn = psycopg2.connect(database_url)
        cursor = conn.cursor()
        
        print("Fixing foreign key constraints...")
        
        # Drop existing foreign key constraints
        cursor.execute("""
            ALTER TABLE skillstown_user_courses 
            DROP CONSTRAINT IF EXISTS skillstown_user_courses_user_id_fkey;
        """)
        
        cursor.execute("""
            ALTER TABLE skillstown_user_profiles 
            DROP CONSTRAINT IF EXISTS skillstown_user_profiles_user_id_fkey;
        """)
        
        # Add new foreign key constraints pointing to 'user' table
        cursor.execute("""
            ALTER TABLE skillstown_user_courses 
            ADD CONSTRAINT skillstown_user_courses_user_id_fkey 
            FOREIGN KEY (user_id) REFERENCES "user"(id);
        """)
        
        cursor.execute("""
            ALTER TABLE skillstown_user_profiles 
            ADD CONSTRAINT skillstown_user_profiles_user_id_fkey 
            FOREIGN KEY (user_id) REFERENCES "user"(id);
        """)
        
        # Commit changes
        conn.commit()
        print("✅ Foreign key constraints fixed successfully!")
        
        # Verify the constraints
        cursor.execute("""
            SELECT 
                tc.constraint_name, 
                tc.table_name, 
                kcu.column_name, 
                ccu.table_name AS foreign_table_name,
                ccu.column_name AS foreign_column_name 
            FROM information_schema.table_constraints AS tc 
            JOIN information_schema.key_column_usage AS kcu
                ON tc.constraint_name = kcu.constraint_name
                AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage AS ccu
                ON ccu.constraint_name = tc.constraint_name
                AND ccu.table_schema = tc.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY' 
            AND tc.table_name LIKE 'skillstown_%';
        """)
        
        constraints = cursor.fetchall()
        print("\n📋 Current foreign key constraints:")
        for constraint in constraints:
            print(f"  {constraint[1]}.{constraint[2]} -> {constraint[3]}.{constraint[4]}")
        
        cursor.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Error fixing foreign keys: {e}")
        return False

if __name__ == "__main__":
    if fix_foreign_keys():
        print("\n🎉 Database foreign key constraints have been fixed!")
        print("You can now try enrolling in courses again.")
    else:
        print("\n💥 Failed to fix foreign key constraints.")
        sys.exit(1)
