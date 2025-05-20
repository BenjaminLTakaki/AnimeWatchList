import os
import sys
from flask import Flask
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set up paths
project_root = os.path.dirname(os.path.abspath(__file__))
animewatchlist_path = os.path.join(project_root, 'projects/animewatchlist')
sys.path.insert(0, animewatchlist_path)

# Create a test Flask app
app = Flask(__name__)

print("Initializing database...")

try:
    # Import necessary modules
    from projects.animewatchlist.auth import db, User    # Configure database
    database_url = os.environ.get('DATABASE_URL')
    if database_url and database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    
    # Database URL adjustment to ensure correct database name
    if database_url:
        # If database name isn't already animewatchlist-db, modify it
        if '/animewatchlist-db' not in database_url:
            # Extract everything up to the last slash (if exists)
            if '/' in database_url.split('://')[1]:
                base_url = database_url.rsplit('/', 1)[0]
                database_url = f"{base_url}/animewatchlist-db"
            else:
                database_url = f"{database_url}/animewatchlist-db"
    else:
        # Fallback/default connection string with proper database name
        database_url = 'postgresql://postgres:YourPassword@localhost:5432/animewatchlist-db'
    
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    
    print(f"Using database URL: {database_url}")
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Initialize database with app
    db.init_app(app)
    
    # Create tables
    with app.app_context():
        print("Creating database tables...")
        db.create_all()
        print("Tables created successfully.")
        
        # Check if we have default user
        admin_user = User.query.filter_by(username='admin').first()
        if not admin_user:
            print("Creating default admin user...")
            admin = User(username='admin', email='admin@example.com')
            admin.set_password('password123')
            db.session.add(admin)
            db.session.commit()
            print("Default admin user created.")
    
    print("Database initialization complete!")
except Exception as e:
    print(f"Error initializing database: {e}")
    print("Please ensure PostgreSQL is running and configured correctly.")