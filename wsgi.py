import os
import sys
from flask import Flask, send_from_directory, redirect
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from werkzeug.wrappers import Response

# Create a main application to serve both static files and the AnimeWatchList app
main_app = Flask(__name__, static_folder='.')

# Set production flag for the anime app
os.environ['RENDER'] = 'true'

# Import the AnimeWatchList app
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'projects/animewatchlist'))
from app import app as anime_app

# Configure anime_app to know it's mounted at /animewatchlist
anime_app.config['APPLICATION_ROOT'] = '/animewatchlist'
anime_app.config['PREFERRED_URL_SCHEME'] = 'https'

# Set static URL path for the anime app
anime_app.static_url_path = '/animewatchlist/static'
anime_app.static_folder = 'projects/animewatchlist/static'

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

# Fix for the static files in the AnimeWatchList app
@main_app.route('/animewatchlist/static/<path:filename>')
def anime_static(filename):
    return send_from_directory('projects/animewatchlist/static', filename)

# Custom middleware to handle the mounting properly
class PathFixMiddleware:
    def __init__(self, app, script_name):
        self.app = app
        self.script_name = script_name

    def __call__(self, environ, start_response):
        script_name = environ.get('SCRIPT_NAME', '')
        if script_name == self.script_name:
            environ['SCRIPT_NAME'] = self.script_name
            environ['PATH_INFO'] = environ['PATH_INFO'].replace(self.script_name, '', 1)
        return self.app(environ, start_response)

# Apply the PathFixMiddleware to anime_app
patched_anime_app = PathFixMiddleware(anime_app, '/animewatchlist')

# Mount the anime_app at the /animewatchlist prefix
application = DispatcherMiddleware(main_app, {
    '/animewatchlist': patched_anime_app
})

if __name__ == "__main__":
    from werkzeug.serving import run_simple
    # Set the hostname and port for local development
    run_simple('localhost', 5000, application, use_reloader=True)