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
    
    # If DATABASE_URL is not set, try alternative variables
    if not database_url:
        # Try to build the connection string from individual components
        db_host = os.environ.get('DB_HOST', 'dpg-d0me7lbuibrs73ekuqt0-a')
        db_port = os.environ.get('DB_PORT', '5432')
        db_name = os.environ.get('DB_NAME', 'animewatchlist_db')
        db_user = os.environ.get('DB_USER', 'animewatchlist_db_user')
        db_password = os.environ.get('DB_PASSWORD', 'zvKOo9pIfbHbcv0sBym8mtaUyUuX9dkP')  # Default password
        
        if db_password:
            database_url = f'postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}'
        else:
            # Fallback to a default for local development
            database_url = 'postgresql://postgres:password@localhost/animewatchlist'
    
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