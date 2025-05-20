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
    from projects.animewatchlist.auth import db, User
    
    # Configure database
    database_url = os.environ.get('DATABASE_URL')
    
    # If DATABASE_URL is not set, log an error
    if not database_url:
        print("ERROR: DATABASE_URL environment variable is not set!")
        print("Please set the DATABASE_URL environment variable with your PostgreSQL connection string.")
        # Fallback to a development database for local use only
        database_url = 'sqlite:///test.db'
    
    # Fix for Render PostgreSQL URLs
    if database_url and database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    
    print(f"Using database URL: {database_url}")
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Initialize database with app
    db.init_app(app)
    
    # Create tables
    with app.app_context():
        print("Creating database tables...")
        try:
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
        except Exception as e:
            print(f"Error creating tables: {e}")
    
    print("Database initialization complete!")
except Exception as e:
    print(f"Error initializing database: {e}")
    print("Please ensure PostgreSQL is running and configured correctly.")
    
    # Print environment variables for debugging (hide sensitive parts)
    print("\nEnvironment Variables (for debugging):")
    if 'DATABASE_URL' in os.environ:
        parts = os.environ['DATABASE_URL'].split('@')
        if len(parts) >= 2:
            masked_url = f"...@{parts[1]}"
            print(f"DATABASE_URL is set and contains hostname: {masked_url}")
        else:
            print("DATABASE_URL is set but in an unexpected format")
    else:
        print("DATABASE_URL is not set")