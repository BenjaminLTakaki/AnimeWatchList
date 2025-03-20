import os
import sys
from flask import Flask, send_from_directory, redirect

# Create a main application to serve both static files and the AnimeWatchList app
main_app = Flask(__name__, static_folder='.')

# Import the AnimeWatchList app
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'projects/animewatchlist'))
from app import app as anime_app

# Set up routes for the main application to serve static files
@main_app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@main_app.route('/<path:path>')
def serve_static(path):
    if os.path.exists(path):
        return send_from_directory('.', path)
    return "File not found", 404

# Route /projects/animewatchlist/app to the anime app
@main_app.route('/projects/animewatchlist/app')
@main_app.route('/projects/animewatchlist/app/<path:subpath>')
def anime_index(subpath=''):
    if subpath:
        return anime_app.handle_request('/'+subpath)
    return anime_app.handle_request('/')

# Mount the anime_app at the /projects/animewatchlist/app URL prefix
application = main_app

if __name__ == "__main__":
    application.run(debug=True)