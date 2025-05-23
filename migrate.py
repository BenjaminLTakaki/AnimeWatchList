import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set up paths
project_root = os.path.dirname(os.path.abspath(__file__))
projects_path = os.path.join(project_root, 'projects')
sys.path.insert(0, projects_path)

# Import the SkillsTown app with the database and migration setup
from skillstown.app import create_app

# Create the app instance
app = create_app('production')

if __name__ == '__main__':
    with app.app_context():
        # This allows you to run: python migrate.py
        pass