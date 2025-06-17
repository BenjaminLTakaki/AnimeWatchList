"""
Flask-Migrate Management Script for SkillsTown CV Analyzer

This script creates a Flask app instance specifically for database migrations
using Flask-Migrate. It imports the SkillsTown app factory from the system directory.

Usage:
    flask db init      # Initialize migrations (first time only)
    flask db migrate   # Create new migration
    flask db upgrade   # Apply migrations to database

Environment Variables:
    FLASK_CONFIG: Configuration mode (development/production)
    FLASK_APP: Should be set to 'manage.py'

Updated: June 2025 - Refactored to match new workspace structure
"""

# pyright: reportMissingImports=false

# c:\Users\benta\Personal_Website\AnimeWatchList\manage.py
import os
import sys
from dotenv import load_dotenv

# Load environment variables from .env if you have one
load_dotenv()

# Add skillstown system directory to Python path (matches wsgi.py structure)
project_root = os.path.dirname(os.path.abspath(__file__))
skillstown_system_path = os.path.join(project_root, 'projects', 'skillstown', 'system')
if skillstown_system_path not in sys.path:
    sys.path.insert(0, skillstown_system_path)

# Import the app factory from the skillstown system directory with error handling
try:
    from app import create_app as create_skillstown_app
    print("✅ SkillsTown app factory imported successfully for manage.py")
except ImportError as e:
    print(f"❌ Could not import SkillsTown app factory: {e}")
    print(f"Make sure the SkillsTown app is properly set up in: {skillstown_system_path}")
    raise

# Create an app instance using the factory.
# This instance will have Flask-Migrate initialized.
# We name it 'app' so FLASK_APP=manage.py can find it by default.
try:
    app = create_skillstown_app(os.getenv('FLASK_CONFIG') or 'development')
    print("✅ SkillsTown app instance created successfully")
except Exception as e:
    print(f"❌ Could not create SkillsTown app instance: {e}")
    raise

# If you need to run shell commands with app context, you can do it here, e.g.:
# if __name__ == '__main__':
# with app.app_context():
# pass # Example: db.create_all() or other setup