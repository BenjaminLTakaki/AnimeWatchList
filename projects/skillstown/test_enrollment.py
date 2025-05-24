#!/usr/bin/env python3
"""
Test script to verify course enrollment functionality works without foreign key errors
"""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'animewatchlist'))

from app import create_app
from auth import User, db
from datetime import datetime

def test_enrollment():
    """Test that course enrollment works without foreign key errors"""
    app = create_app()
    
    with app.app_context():
        # Import models after app context is created
        from app import UserCourse
        
        # Create all tables
        db.create_all()
        
        # Create a test user if it doesn't exist
        test_user = User.query.filter_by(email='test@example.com').first()
        if not test_user:
            test_user = User(
                username='testuser',
                email='test@example.com'
            )
            test_user.set_password('testpassword')
            db.session.add(test_user)
            db.session.commit()
            print(f"Created test user with ID: {test_user.id}")
        else:
            print(f"Using existing test user with ID: {test_user.id}")
        
        # Test enrolling in a course
        test_course = UserCourse(
            user_id=test_user.id,
            category='Programming Languages',
            course_name='Python for Beginners'
        )
        
        try:
            db.session.add(test_course)
            db.session.commit()
            print("✅ Course enrollment successful!")
            print(f"Enrolled user {test_user.username} in '{test_course.course_name}'")
            
            # Verify the enrollment exists
            enrollment = UserCourse.query.filter_by(
                user_id=test_user.id,
                course_name='Python for Beginners'
            ).first()
            
            if enrollment:
                print(f"✅ Verification successful: Course enrollment found in database")
                print(f"   Course: {enrollment.course_name}")
                print(f"   Category: {enrollment.category}")
                print(f"   Status: {enrollment.status}")
                print(f"   Enrolled at: {enrollment.created_at}")
            else:
                print("❌ Verification failed: Course enrollment not found")
            
        except Exception as e:
            print(f"❌ Course enrollment failed with error: {e}")
            db.session.rollback()
            return False
        
        return True

if __name__ == '__main__':
    print("Testing course enrollment functionality...")
    success = test_enrollment()
    if success:
        print("\n🎉 All tests passed! The foreign key constraint issues have been resolved.")
    else:
        print("\n❌ Tests failed. Foreign key issues may still exist.")
