# projects/spotify_cover_generator/app.py
import os
import sys
from pathlib import Path

# Ensure the project's own directory is prioritized for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from factory import create_app

# Create the app
app = create_app()

# Import configurations that might be needed globally
from config import COVERS_DIR, SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, SPOTIFY_REDIRECT_URI

# Guest session helper functions (kept here for backward compatibility)
from flask import session
import datetime
import uuid

def get_current_user_or_guest():
    """Use the factory version"""
    from factory import get_current_user_or_guest_global_ref
    return get_current_user_or_guest_global_ref()

def track_guest_generation():
    """Track generation for guest"""
    if 'guest_session_id' not in session:
        session['guest_session_id'] = str(uuid.uuid4())
        session['guest_created'] = datetime.datetime.utcnow().isoformat()
        session['guest_generations_today'] = 0
        session['guest_last_generation'] = None

    current_gens = session.get('guest_generations_today', 0)
    session['guest_generations_today'] = current_gens + 1
    session['guest_last_generation'] = datetime.datetime.utcnow().isoformat()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=app.config.get("DEBUG", False), host="0.0.0.0", port=port)