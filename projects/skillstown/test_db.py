#!/usr/bin/env python3
"""
Test script to verify SkillsTown database functionality
"""

from app import create_app
from flask_login import current_user
import json

def test_course_functionality():
    app = create_app()
    
    with app.app_context():
        # Import models here to ensure they're available in the app context
        from app import UserCourse, get_skillstown_stats, load_course_catalog, search_courses
        
        print("=== SkillsTown Database Test ===")
        
        # Test 1: Load course catalog
        print("\n1. Testing course catalog loading...")
        catalog = load_course_catalog()
        categories = catalog.get("categories", [])
        total_courses = sum(len(cat.get("courses", [])) for cat in categories)
        print(f"✓ Loaded {len(categories)} categories with {total_courses} total courses")
        
        # Test 2: Search functionality
        print("\n2. Testing course search...")
        search_results = search_courses("python")
        print(f"✓ Found {len(search_results)} courses for 'python' query")
        if search_results:
            print(f"  Top result: {search_results[0]['course']} (score: {search_results[0]['relevance_score']})")
        
        # Test 3: Database connection
        print("\n3. Testing database connection...")
        try:
            all_enrollments = UserCourse.query.all()
            print(f"✓ Database connected. Found {len(all_enrollments)} total course enrollments")
            
            # Test user stats (will be 0 since no current user)
            stats = get_skillstown_stats(1)  # Test with user ID 1
            print(f"✓ Stats function working: {stats}")
            
        except Exception as e:
            print(f"✗ Database error: {e}")
        
        print("\n=== Test Complete ===")

if __name__ == "__main__":
    test_course_functionality()
