import os
import sys
import datetime
from flask import Flask, send_from_directory, redirect, request
from dotenv import load_dotenv
from flask_migrate import Migrate

load_dotenv()

main_app = Flask(__name__, static_folder='.')

# Local safety guard: if you're running on a developer machine with a Render
# DATABASE_URL in .env, prefer local SQLite unless explicitly disabled.
_render_flag = os.environ.get('RENDER', '').lower()
_is_render = _render_flag not in ('', '0', 'false', 'no')
if not _is_render and os.environ.get('FORCE_REMOTE_DB', '0') != '1':
    _env_db_url = os.environ.get('DATABASE_URL', '')
    if 'render.com' in _env_db_url:
        os.environ.pop('DATABASE_URL', None)
        print('Local mode: ignoring Render DATABASE_URL and using local SQLite databases.')

project_root = os.path.dirname(os.path.abspath(__file__))
projects_dir = os.path.join(project_root, 'projects')
if projects_dir not in sys.path:
    sys.path.insert(0, projects_dir)

# ── SkillsTown ────────────────────────────────────────────────────────────────
skillstown_path  = os.path.join(projects_dir, 'skillstown')
os.makedirs(os.path.join(skillstown_path, 'uploads'), exist_ok=True)
os.makedirs(os.path.join(skillstown_path, 'static', 'data'), exist_ok=True)
os.makedirs(os.path.join(skillstown_path, 'static'), exist_ok=True)

skillstown_error = None
try:
    from skillstown.app import create_app
    skillstown_app = create_app(os.environ.get('FLASK_CONFIG', 'development'))
    print("SkillsTown app imported successfully")
except Exception as e:
    skillstown_error = str(e)
    print(f"Could not import SkillsTown app: {skillstown_error}")
    skillstown_app = Flask("skillstown_stub")

    @skillstown_app.route('/')
    def skillstown_index():
        return f"SkillsTown is currently unavailable. Error: {skillstown_error}"

# ── AnimeWatchList (new unified app) ─────────────────────────────────────────
animewatchlist_path = os.path.join(projects_dir, 'animewatchlist')
if animewatchlist_path not in sys.path:
    sys.path.insert(0, animewatchlist_path)

try:
    from animewatchlist.app import create_app as create_animewatchlist_app

    # Re-strip Render DATABASE_URL in case app.py's load_dotenv() re-added it
    if not _is_render and os.environ.get('FORCE_REMOTE_DB', '0') != '1':
        _reloaded = os.environ.get('DATABASE_URL', '')
        if 'render.com' in _reloaded:
            os.environ.pop('DATABASE_URL', None)

    animewatchlist_app = Flask("animewatchlist.app", root_path=animewatchlist_path)
    _db_url = os.environ.get('DATABASE_URL', '')
    if _db_url.startswith('postgres://'):
        _db_url = _db_url.replace('postgres://', 'postgresql://', 1)

    animewatchlist_app.config['SECRET_KEY'] = os.environ.get(
        'FLASK_SECRET_KEY', os.environ.get('SECRET_KEY', 'change-me')
    )
    animewatchlist_app.config['SQLALCHEMY_DATABASE_URI']        = _db_url or 'sqlite:///animewatchlist.db'
    animewatchlist_app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    animewatchlist_app = create_animewatchlist_app(animewatchlist_app)

    # MAL OAuth credentials forwarded from environment
    animewatchlist_app.config['MAL_CLIENT_ID']     = os.environ.get('MAL_CLIENT_ID', '')
    animewatchlist_app.config['MAL_CLIENT_SECRET']  = os.environ.get('MAL_CLIENT_SECRET', '')
    animewatchlist_app.config['MAL_REDIRECT_URI']   = os.environ.get(
        'MAL_REDIRECT_URI',
        'https://benjamintakaki.com/auth/mal/callback'
    )

    from animewatchlist.app import db as animewatchlist_db
    with animewatchlist_app.app_context():
        animewatchlist_db.create_all()

    print("AnimeWatchList app loaded successfully")
    has_animewatchlist_app = True
    animewatchlist_error = None

except Exception as e:
    import traceback
    print(f"Could not load AnimeWatchList app: {e}")
    print(traceback.format_exc())
    animewatchlist_error = str(e)
    animewatchlist_app = Flask("animewatchlist_stub")
    has_animewatchlist_app = False

    @animewatchlist_app.route('/')
    @animewatchlist_app.route('/<path:path>')
    def animewatchlist_stub(path=None):
        return f"AnimeWatchList unavailable: {animewatchlist_error}", 503

# ── Spotify Cover Generator ───────────────────────────────────────────────────
spotify_path  = os.path.join(projects_dir, 'spotify-cover-generator')
spotify_error = None

# Spotify config expects a writable LORA_DIR; /tmp/... is not valid on Windows.
if os.name == 'nt':
    _lora_dir = os.environ.get('LORA_DIR', '')
    if (not _lora_dir) or _lora_dir.startswith('/tmp'):
        os.environ['LORA_DIR'] = os.path.join(spotify_path, 'loras')
    os.makedirs(os.environ['LORA_DIR'], exist_ok=True)

def build_spotify_stub(error_message):
    stub = Flask("spotify_stub")

    @stub.route('/')
    @stub.route('/<path:path>')
    def spotify_unavailable(path=None):
        return f"<h1>Spotify Cover Generator unavailable</h1><p>{error_message}</p><p><a href='/'>Home</a></p>"

    return stub

def import_spotify_app():
    try:
        if not os.path.exists(spotify_path):
            return build_spotify_stub(f"Path not found: {spotify_path}"), False
        if spotify_path not in sys.path:
            sys.path.insert(0, spotify_path)
        from app import app as sp_app
        with sp_app.app_context():
            try:
                from extensions import db
                db.session.execute(db.text('SELECT 1'))
            except Exception as db_err:
                print(f"Spotify DB warning: {db_err}")
        print("Spotify app imported successfully")
        return sp_app, True
    except Exception as e:
        import traceback
        print(f"Spotify import failed: {e}")
        print(traceback.format_exc())
        return build_spotify_stub(str(e)), False

spotify_app, has_spotify_app = import_spotify_app()

if has_spotify_app:
    spotify_app.config['APPLICATION_ROOT']      = '/spotify'
    spotify_app.config['PREFERRED_URL_SCHEME']  = 'https'
    SPOTIFY_APP_STATIC_DIR = os.path.join(spotify_path, 'static')

    @main_app.route('/spotify/static/<path:filename>')
    def spotify_static(filename):
        if os.path.exists(os.path.join(SPOTIFY_APP_STATIC_DIR, filename)):
            return send_from_directory(SPOTIFY_APP_STATIC_DIR, filename)
        return f"Static file {filename} not found", 404

# ── Context processors ────────────────────────────────────────────────────────
@skillstown_app.context_processor
def _skillstown_ctx():
    return {'current_year': datetime.datetime.now().year}

@animewatchlist_app.context_processor
def _animewatchlist_ctx():
    return {'current_year': datetime.datetime.now().year}

# ── App roots ─────────────────────────────────────────────────────────────────
skillstown_app.config['APPLICATION_ROOT']     = '/skillstown'
skillstown_app.config['PREFERRED_URL_SCHEME'] = 'https'
animewatchlist_app.config['APPLICATION_ROOT'] = ''
animewatchlist_app.config['PREFERRED_URL_SCHEME'] = 'https'

SKILLSTOWN_APP_STATIC_DIR    = os.path.join(skillstown_path,    'static')
ANIMEWATCHLIST_APP_STATIC_DIR = os.path.join(animewatchlist_path, 'static')

# ── Main app routes ───────────────────────────────────────────────────────────
@main_app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@main_app.route('/<path:path>')
def serve_static(path):
    if os.path.exists(path):
        return send_from_directory('.', path)
    return "File not found", 404

@main_app.route('/projects/skillstown')
@main_app.route('/projects/skillstown/')
def skillstown_redirect():
    return redirect('/skillstown/')

@main_app.route('/projects/animewatchlist')
@main_app.route('/projects/animewatchlist/')
def animewatchlist_redirect():
    return redirect('/animewatchlist/')

@main_app.route('/projects/spotify-cover-generator')
@main_app.route('/projects/spotify-cover-generator/')
def spotify_redirect():
    return redirect('/spotify/', code=302)

# ── The new SPA route: serve animewatchlist.html for all /animewatchlist/* ───
# This is separate from the API backend -- the React frontend is served here,
# and the API calls go to the same /animewatchlist prefix via the dispatcher.
# Since the React app is bundled as one file, Flask just needs to serve it
# at the root of the sub-app. All /api/* and /auth/* routes are handled by
# animewatchlist_app directly.

@main_app.route('/skillstown/static/<path:filename>')
def skillstown_static(filename):
    if os.path.exists(os.path.join(SKILLSTOWN_APP_STATIC_DIR, filename)):
        return send_from_directory(SKILLSTOWN_APP_STATIC_DIR, filename)
    if os.path.exists(os.path.join('static', filename)):
        return send_from_directory('static', filename)
    return f"Static file {filename} not found", 404

@main_app.route('/animewatchlist/static/<path:filename>')
def animewatchlist_static(filename):
    if os.path.exists(os.path.join(ANIMEWATCHLIST_APP_STATIC_DIR, filename)):
        return send_from_directory(ANIMEWATCHLIST_APP_STATIC_DIR, filename)
    return f"Static file {filename} not found", 404

# ── Health check ──────────────────────────────────────────────────────────────
@main_app.route('/health')
def health_check():
    return {
        'status': 'healthy',
        'apps': {
            'skillstown':     skillstown_error is None,
            'animewatchlist': has_animewatchlist_app,
            'spotify':        has_spotify_app,
        }
    }

# ── WSGI dispatcher ───────────────────────────────────────────────────────────
class AppDispatcher:
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        path_info = environ.get('PATH_INFO', '')

        # Fix double-path bug
        if '/animewatchlist/animewatchlist/' in path_info:
            path_info = path_info.replace('/animewatchlist/animewatchlist/', '/animewatchlist/')
            environ['PATH_INFO'] = path_info

        # Static file shortcuts -- handled by main_app routes above
        for prefix in ('/skillstown/static/', '/animewatchlist/static/'):
            if path_info.startswith(prefix):
                return main_app(environ, start_response)
        if has_spotify_app and path_info.startswith('/spotify/static/'):
            return main_app(environ, start_response)

        try:
            if path_info.startswith('/skillstown'):
                environ['SCRIPT_NAME'] = '/skillstown'
                environ['PATH_INFO']   = path_info[len('/skillstown'):]
                return skillstown_app(environ, start_response)

            elif path_info.startswith('/animewatchlist'):
                # AnimeWatchList already registers routes under /animewatchlist.
                # Keep PATH_INFO intact to avoid double-prefix routing issues.
                environ['SCRIPT_NAME'] = ''
                environ['PATH_INFO']   = path_info
                return animewatchlist_app(environ, start_response)

            elif path_info.startswith('/spotify'):
                environ['SCRIPT_NAME'] = '/spotify'
                environ['PATH_INFO']   = path_info[len('/spotify'):]
                if has_spotify_app:
                    old_cwd = os.getcwd()
                    try:
                        os.chdir(spotify_path)
                        return spotify_app(environ, start_response)
                    finally:
                        os.chdir(old_cwd)
                return spotify_app(environ, start_response)

            return main_app(environ, start_response)

        except Exception as e:
            print(f"AppDispatcher error: {e}")
            status  = '500 Internal Server Error'
            headers = [('Content-Type', 'text/html')]
            start_response(status, headers)
            return [f"<h1>500</h1><p>{e}</p><p><a href='/'>Home</a></p>".encode()]


application = AppDispatcher(main_app)

if __name__ == "__main__":
    from werkzeug.serving import run_simple
    run_simple('localhost', 5000, application, use_reloader=True)
