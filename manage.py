# c:\Users\benta\Personal_Website\AnimeWatchList\manage.py
import os
import sys
from dotenv import load_dotenv

# Load environment variables from .env if you have one
load_dotenv()

# Add projects directory to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
projects_dir = os.path.join(project_root, 'projects')
if projects_dir not in sys.path:
    sys.path.insert(0, projects_dir)

# Import the app factory from skillstown.app
# The skillstown_app's create_app function already initializes Flask-Migrate.
from skillstown.app import create_app as create_skillstown_app

# Create an app instance using the factory.
# This instance will have Flask-Migrate initialized.
# We name it 'app' so FLASK_APP=manage.py can find it by default.
app = create_skillstown_app(os.getenv('FLASK_CONFIG') or 'development')

# If you need to run shell commands with app context, you can do it here, e.g.:
# if __name__ == '__main__':
# with app.app_context():
# pass # Example: db.create_all() or other setup
