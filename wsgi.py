import os
import sys
from flask import Flask, send_from_directory, redirect, url_for
from werkzeug.middleware.dispatcher import DispatcherMiddleware

# Create a main application to serve both static files and the AnimeWatchList app
main_app = Flask(__name__, static_folder='.')

# Import the AnimeWatchList app
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'projects/animewatchlist'))
from app import app as anime_app

# Configure the anime app for the proper URL prefix
anime_app.config['APPLICATION_ROOT'] = '/animewatchlist'

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
def anime_index_redirect():
    return redirect('/animewatchlist')

# Define routes for the anime app with subpaths
@main_app.route('/projects/animewatchlist/<path:subpath>')
def anime_redirect(subpath):
    # Redirect to the AnimeWatchList app with the correct subpath
    return redirect(f'/animewatchlist/{subpath}')

# Mount the anime_app at the /animewatchlist prefix
application = DispatcherMiddleware(main_app, {
    '/animewatchlist': anime_app
})

if __name__ == "__main__":
    from werkzeug.serving import run_simple
    run_simple('localhost', 5000, application, use_reloader=True)