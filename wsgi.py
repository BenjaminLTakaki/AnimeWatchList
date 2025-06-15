import os
import sys
import datetime
from flask import Flask, send_from_directory, redirect, request, jsonify
from dotenv import load_dotenv
from flask_migrate import Migrate
from werkzeug.middleware.dispatcher import DispatcherMiddleware

# Load environment variables
load_dotenv()

# Create a main application to serve static files
main_app = Flask(__name__, static_folder='.')

# Set the Python path to include the project directories
project_root = os.path.dirname(os.path.abspath(__file__))

# Add projects directory to Python path
projects_path = os.path.join(project_root, 'projects')
if projects_path not in sys.path:
    sys.path.insert(0, projects_path)

print(f"Project root: {project_root}")

# External CMS Configuration
CMS_URL = os.getenv('CMS_URL', 'https://your-cms-domain.com')  # Update this when you deploy the CMS
CMS_API_KEY = os.getenv('CMS_API_KEY', 'your-api-key-here')  # Get this from the CMS after creating a portfolio

# SkillsTown app setup
skillstown_path = os.path.join(project_root, 'projects/skillstown')
sys.path.insert(0, skillstown_path)

# Define the paths to ensure they exist before import
os.makedirs(os.path.join(skillstown_path, 'uploads'), exist_ok=True)
os.makedirs(os.path.join(skillstown_path, 'static', 'data'), exist_ok=True)
os.makedirs(os.path.join(skillstown_path, 'static'), exist_ok=True)

# Import SkillsTown app with factory pattern
skillstown_error = None
try:
    from skillstown.app import create_app
    skillstown_app = create_app('production')
    print("✅ SkillsTown app imported successfully")
except Exception as e:
    skillstown_error = str(e)
    print(f"❌ Could not import SkillsTown app: {skillstown_error}")
    print("Creating a stub SkillsTown app")
    skillstown_app = Flask("skillstown_stub")
    
    @skillstown_app.route('/')
    def skillstown_index():
        return f"SkillsTown is currently unavailable. Error: {skillstown_error}"

# AnimeWatchList app setup
animewatchlist_path = os.path.join(project_root, 'projects/animewatchlist')
sys.path.insert(0, animewatchlist_path)

# Import the AnimeWatchList app with error handling
try:
    from projects.animewatchlist.app import app as animewatchlist_app, db as animewatchlist_db
    Migrate(animewatchlist_app, animewatchlist_db)
    print("✅ AnimeWatchList app imported successfully")
    has_animewatchlist_app = True
except Exception as e:
    print(f"❌ Could not import AnimeWatchList app: {e}")
    print("Creating a stub AnimeWatchList app")
    animewatchlist_app = Flask("animewatchlist_stub")
    
    @animewatchlist_app.route('/')
    def animewatchlist_index():
        return "AnimeWatchList is currently unavailable. Database connection issues. Please check your PostgreSQL setup."
    
    has_animewatchlist_app = True

# Spotify Cover Generator app setup
spotify_path = os.path.join(project_root, 'projects/spotify-cover-generator')

# Import Spotify app
try:
    print(f"Setting up Spotify app from path: {spotify_path}")
    
    original_sys_path = sys.path.copy()
    
    if spotify_path not in sys.path:
        sys.path.insert(0, spotify_path)
    
    old_cwd = os.getcwd()
    os.chdir(spotify_path)
    
    try:
        from app import app as spotify_app
        print("✅ Spotify app imported successfully")
        has_spotify_app = True
    finally:
        os.chdir(old_cwd)
        
except Exception as e:
    print(f"❌ Could not import Spotify app: {e}")
    has_spotify_app = False
    sys.path = original_sys_path

# Configure context processors
@skillstown_app.context_processor
def inject_skillstown_vars():
    return {
        'current_year': datetime.datetime.now().year
    }

@animewatchlist_app.context_processor
def inject_animewatchlist_vars():
    return {
        'current_year': datetime.datetime.now().year
    }

if has_spotify_app:
    @spotify_app.context_processor
    def inject_spotify_vars():
        return {
            'current_year': datetime.datetime.now().year
        }

# Configure app roots
skillstown_app.config['APPLICATION_ROOT'] = '/skillstown'
skillstown_app.config['PREFERRED_URL_SCHEME'] = 'https'

animewatchlist_app.config['APPLICATION_ROOT'] = '/animewatchlist'
animewatchlist_app.config['PREFERRED_URL_SCHEME'] = 'https'

if has_spotify_app:
    spotify_app.config['APPLICATION_ROOT'] = '/spotify'
    spotify_app.config['PREFERRED_URL_SCHEME'] = 'https'

# Define static folders explicitly
SKILLSTOWN_APP_STATIC_DIR = os.path.join(skillstown_path, 'static')
ANIMEWATCHLIST_APP_STATIC_DIR = os.path.join(animewatchlist_path, 'static')
if has_spotify_app:
    SPOTIFY_APP_STATIC_DIR = os.path.join(spotify_path, 'static')

# External CMS Content API Endpoint (now proxies to external CMS)
@main_app.route('/api/content')
def get_content():
    """
    Proxy endpoint to fetch content from external CMS
    This maintains compatibility with existing frontend code
    """
    try:
        import requests
        
        # Fetch content from external CMS
        response = requests.get(f'{CMS_URL}/api/content/{CMS_API_KEY}', timeout=10)
        
        if response.status_code == 200:
            cms_data = response.json()
            
            # Transform the response to match the expected format
            return jsonify({
                'site_content': {
                    'hero': cms_data['content'].get('hero', {}),
                    'projects': cms_data['content'].get('projects', {}),
                    'contact': cms_data['content'].get('contact', {})
                },
                'about_content': cms_data['content'].get('about', {}),
                'images': cms_data['content'].get('images', {})
            })
        else:
            print(f"CMS API returned status {response.status_code}")
            return get_fallback_content()
            
    except Exception as e:
        print(f"Error fetching from external CMS: {e}")
        return get_fallback_content()

def get_fallback_content():
    """
    Fallback content in case external CMS is unavailable
    """
    return jsonify({
        'site_content': {
            'hero': {
                'name': 'Benjamin Takaki',
                'description': 'I am an ICT student passionate about programming and leveraging technology to solve real-world challenges.',
                'resume_btn_text': 'Get Resume',
                'learn_more_btn_text': 'Learn More'
            },
            'projects': {
                'title': 'My Projects',
                'project_1': {
                    'title': 'SkillsTown Course Recommender',
                    'description': 'A web application that analyzes your CV to recommend relevant courses from SkillsTown\'s catalog. Built with Python Flask and NLP technology to extract skills and provide personalized course suggestions.'
                },
                'project_2': {
                    'title': 'AnimeWatchList',
                    'description': 'A web application for tracking anime you\'ve watched and want to watch. Built with Python Flask, this app allows users to discover, search, and categorize anime series.'
                },
                'project_3': {
                    'title': 'Spotify Cover Generator',
                    'description': 'Generate custom album artwork and titles based on your Spotify playlists using AI. Analyze genres and create cover art that matches your music\'s style.'
                }
            },
            'contact': {
                'title': 'Contact Me',
                'description': 'If you\'d like to get in touch, feel free to send me a message!',
                'btn_text': 'Send Message'
            }
        },
        'about_content': {
            'title': 'About Me',
            'paragraphs': [
                'I am a first-year student at Fontys University of Applied Sciences, pursuing an ICT degree with a focus on programming and innovative technology. My educational journey, which includes graduating from the Lycée Français International de Tokyo and excelling in the American Section of the International Option of the French Baccalaureate, has honed my analytical thinking and problem-solving skills.',
                'In my studies, I have worked on Python projects such as labyrinth solvers, image pixelators, and a Space Invaders clone. I am interested in software development and how ICT can tackle real-world problems. International experiences and roles as a camp counselor and waiter have helped me develop strong interpersonal and cross-cultural communication skills.',
                'Fluent in English, French, and conversant in Japanese, I thrive in diverse environments. I am excited to continue growing my technical expertise and contributing to meaningful, innovative projects.'
            ]
        },
        'images': {
            'hero_image': 'styles/ben_photo.jpg',
            'favicon': '/favicon.ico'
        }
    })

# Set up routes for the main application to serve static files
@main_app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@main_app.route('/<path:path>')
def serve_static(path):
    if os.path.exists(path):
        return send_from_directory('.', path)
    return "File not found", 404

# CMS redirect routes - NOW REDIRECTS TO EXTERNAL CMS
@main_app.route('/cms')
@main_app.route('/cms/')
@main_app.route('/portfolio-cms')
@main_app.route('/portfolio-cms/')
def cms_redirect():
    """Redirect to external CMS"""
    return redirect(CMS_URL)

# Create direct routes to the apps
@main_app.route('/projects/skillstown')
@main_app.route('/projects/skillstown/')
def skillstown_redirect():
    return redirect('/skillstown/')

@main_app.route('/projects/animewatchlist')
@main_app.route('/projects/animewatchlist/')
def animewatchlist_redirect():
    return redirect('/animewatchlist/')

if has_spotify_app:
    @main_app.route('/projects/spotify-cover-generator')
    @main_app.route('/projects/spotify-cover-generator/')
    def spotify_redirect():
        return redirect('/spotify/')

# Handle static files from the main app
@main_app.route('/skillstown/static/<path:filename>')
def skillstown_static(filename):
    if os.path.exists(os.path.join(SKILLSTOWN_APP_STATIC_DIR, filename)):
        return send_from_directory(SKILLSTOWN_APP_STATIC_DIR, filename)
    else:
        if os.path.exists(os.path.join('static', filename)):
            return send_from_directory('static', filename)
        return f"Static file {filename} not found", 404

@main_app.route('/animewatchlist/static/<path:filename>')
def animewatchlist_static(filename):
    if os.path.exists(os.path.join(ANIMEWATCHLIST_APP_STATIC_DIR, filename)):
        return send_from_directory(ANIMEWATCHLIST_APP_STATIC_DIR, filename)
    else:
        return f"Static file {filename} not found", 404

if has_spotify_app:
    @main_app.route('/spotify/static/<path:filename>')
    def spotify_static(filename):
        if os.path.exists(os.path.join(SPOTIFY_APP_STATIC_DIR, filename)):
            return send_from_directory(SPOTIFY_APP_STATIC_DIR, filename)
        else:
            return f"Static file {filename} not found", 404

def create_wsgi_app():
    """Create the WSGI application with proper sub-app mounting"""
    
    # Create the dispatcher with main app as default
    app_map = {
        '/skillstown': skillstown_app,
        '/animewatchlist': animewatchlist_app,
    }
    
    if has_spotify_app:
        app_map['/spotify'] = spotify_app
    
    print(f"App mapping: {list(app_map.keys())}")
    print(f"CMS URL: {CMS_URL}")
    
    return DispatcherMiddleware(main_app, app_map)

# Create the application
application = create_wsgi_app()

if __name__ == "__main__":
    from werkzeug.serving import run_simple
    run_simple('localhost', 5000, application, use_reloader=True)