import os
import sys

# Add the animewatchlist directory to Python path
app_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'projects/animewatchlist')
sys.path.insert(0, app_dir)

# Import the Flask app
from app import app as application

if __name__ == "__main__":
    application.run()