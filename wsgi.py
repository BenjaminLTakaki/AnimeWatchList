import os
import sys
import datetime
from flask import Flask, send_from_directory, redirect, request

# Create a main application to serve both static files and the AnimeWatchList app
main_app = Flask(__name__, static_folder='.')

# Set production flag for the anime app
os.environ['RENDER'] = 'true'

# Set the Python path to include the animewatchlist directory
animewatchlist_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'projects/animewatchlist')
sys.path.insert(0, animewatchlist_path)

# Define the path to ensure it exists before import
os.makedirs(os.path.join(animewatchlist_path, 'data'), exist_ok=True)

# Import the AnimeWatchList app
from projects.animewatchlist.app import app as anime_app

# Create a standard context processor to inject variables into all templates
@anime_app.context_processor
def inject_template_vars():
    return {
        'current_year': datetime.datetime.now().year
    }

# Configure anime_app
anime_app.config['APPLICATION_ROOT'] = '/animewatchlist'
anime_app.config['PREFERRED_URL_SCHEME'] = 'https'

# Define static folders explicitly
ANIME_APP_STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'projects/animewatchlist/static')

# Set up routes for the main application to serve static files
@main_app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@main_app.route('/<path:path>')
def serve_static(path):
    if os.path.exists(path):
        return send_from_directory('.', path)
    return "File not found", 404

# Create a direct route to the AnimeWatchList app
@main_app.route('/projects/animewatchlist')
@main_app.route('/projects/animewatchlist/')
def anime_redirect():
    return redirect('/animewatchlist/')

# CRITICAL: Handle anime app's static files from the main app
@main_app.route('/animewatchlist/static/<path:filename>')
def anime_static(filename):
    print(f"Serving static file: {filename} from {ANIME_APP_STATIC_DIR}")
    if os.path.exists(os.path.join(ANIME_APP_STATIC_DIR, filename)):
        return send_from_directory(ANIME_APP_STATIC_DIR, filename)
    else:
        print(f"Static file not found: {filename}")
        # Fallback: check if the file exists in the root static folder
        if os.path.exists(os.path.join('static', filename)):
            return send_from_directory('static', filename)
        return f"Static file {filename} not found", 404

# Class to handle routing to the anime app
class AnimeAppDispatcher:
    def __init__(self, app):
        self.app = app
        
    def __call__(self, environ, start_response):
        # Handle requests to the anime app
        path_info = environ.get('PATH_INFO', '')
        
        # Special handling for static files
        if path_info.startswith('/animewatchlist/static/'):
            # Rewrite the request to use our special static file handler
            environ['PATH_INFO'] = path_info
            return main_app(environ, start_response)
            
        # For all other /animewatchlist paths, route to the anime app
        if path_info.startswith('/animewatchlist'):
            script_name = '/animewatchlist'
            environ['SCRIPT_NAME'] = script_name
            environ['PATH_INFO'] = path_info[len(script_name):]
            return anime_app(environ, start_response)
            
        # Everything else goes to the main app
        return main_app(environ, start_response)

# Set up the WSGI application with our custom dispatcher
application = AnimeAppDispatcher(main_app)

# Create CSS files in required locations if they don't exist
def ensure_static_files_exist():
    """Make sure required static files exist in the appropriate directories."""
    # Define source and destination directories
    css_source = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'projects/animewatchlist/static/style.css')
    js_source = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'projects/animewatchlist/static/script.js')
    
    # Create directories if they don't exist
    os.makedirs(ANIME_APP_STATIC_DIR, exist_ok=True)
    
    # Create style.css if it doesn't exist
    if not os.path.exists(css_source):
        print(f"Creating missing CSS file at {css_source}")
        with open(css_source, 'w') as f:
            # Copy content from existing CSS file
            try:
                with open('projects/animewatchlist/static/style.css', 'r') as source:
                    f.write(source.read())
            except:
                # Fallback: write basic CSS
                f.write("""/* static/style.css */
body {
    font-family: Arial, sans-serif;
    margin: 0;
    padding: 0;
    background: #f5f5f5;
    color: #333;
    line-height: 1.6;
}

header {
    background: #2E51A2; /* MAL blue */
    color: white;
    padding: 1em;
    text-align: center;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

header h1 {
    margin: 0;
    font-size: 1.8em;
}

/* Rest of your existing CSS or new CSS */
""")
    
    # Create script.js if it doesn't exist
    if not os.path.exists(js_source):
        print(f"Creating missing JS file at {js_source}")
        with open(js_source, 'w') as f:
            # Copy content from existing JS file or write basic JS
            try:
                with open('projects/animewatchlist/static/script.js', 'r') as source:
                    f.write(source.read())
            except:
                # Fallback: write basic JS
                f.write("""// static/script.js
document.addEventListener("DOMContentLoaded", function () {
    console.log("Anime Tracker loaded.");
});
""")

# Run this function to ensure static files exist
ensure_static_files_exist()

if __name__ == "__main__":
    from werkzeug.serving import run_simple
    # Set the hostname and port for local development
    run_simple('localhost', 5000, application, use_reloader=True)