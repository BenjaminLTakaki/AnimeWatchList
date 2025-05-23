import os
import json
import requests
import time
import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_login import login_required, current_user
from dotenv import load_dotenv
from sqlalchemy import inspect
from flask_migrate import Migrate # ADDED

# Load environment variables
load_dotenv()

# Configure Flask app
is_production = os.environ.get('RENDER', False)
app = Flask(
    __name__,
    static_url_path='/static' if not is_production else '/animewatchlist/static',
    template_folder='templates'
)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "anime_tracker_secret")

if is_production:
    app.config['APPLICATION_ROOT'] = '/animewatchlist'
    app.config['PREFERRED_URL_SCHEME'] = 'https'
    app.static_url_path = '/animewatchlist/static'
else:
    app.static_url_path = '/static'

# Define helper function for URL generation
def get_url_for(*args, **kwargs):
    url = url_for(*args, **kwargs)
    if is_production and not url.startswith('/animewatchlist'):
        url = f"/animewatchlist{url}"
    return url

# Add context processor to inject variables into all templates
@app.context_processor
def inject_template_vars():
    return {
        'current_year': datetime.datetime.now().year
    }

# Import and initialize auth system
from auth import init_auth
db = init_auth(app, get_url_for, lambda user_id: (0, 0))  # Temporary function, will be replaced
migrate = Migrate(app, db) # ADDED: Initialize Flask-Migrate

# Create tables explicitly
with app.app_context():
    db.create_all()  # Create user tables

# Now that the database is initialized, we can import the User model
from auth import User

# Import and initialize user data AFTER db is initialized
from user_data import init_user_data, get_user_anime_list, get_status_counts
from user_data import mark_anime_for_user, change_anime_status_for_user, get_anime_status_for_user

# Initialize user data models with the database from auth
Anime, UserAnimeList = init_user_data(db)

# Now that user_data is initialized with the real get_status_counts,
# let's update auth's reference to it
import auth
auth.get_status_counts = get_status_counts

# Create all tables again to ensure all models are registered
with app.app_context():
    db.create_all()

# Global anime queue to serve one anime at a time
anime_queue = []

# Make sure data directory exists
os.makedirs('data', exist_ok=True)

# Jikan API base URL
JIKAN_API_BASE = "https://api.jikan.moe/v4"

# Debug route to manually create tables if needed
@app.route("/debug/create_tables")
def create_tables():
    """Manual route to create database tables."""
    try:
        with app.app_context():
            # Create auth tables
            db.create_all()
            
            # Create user data tables explicitly if needed
            inspector = inspect(db.engine)
            if 'anime' not in inspector.get_table_names():
                db.Anime.__table__.create(db.engine)
            if 'user_anime_list' not in inspector.get_table_names():
                db.UserAnimeList.__table__.create(db.engine)
                
        flash("Database tables created successfully!")
    except Exception as e:
        flash(f"Error creating tables: {e}")
    return redirect(url_for('index'))

def fetch_more_anime():
    """
    Fetch a batch of most popular anime from the Jikan API with persistent page tracking.
    """
    global anime_queue
    print("Fetching popular anime...")
    
    # File to store the current page
    PAGE_TRACKER_FILE = os.path.join('data', "page_tracker.json")
    
    # Load the current page from file for persistence
    try:
        if os.path.exists(PAGE_TRACKER_FILE):
            with open(PAGE_TRACKER_FILE, 'r') as f:
                current_page = json.load(f).get('current_page', 1)
        else:
            current_page = 1
    except Exception:
        current_page = 1
    
    print(f"Current page: {current_page}")
    
    # Set up the request to get popular anime
    url = f"{JIKAN_API_BASE}/top/anime"
    params = {
        "page": current_page,
        "limit": 20  # Fetch 20 anime at a time
    }
    
    try:
        print(f"Requesting page {current_page} of top anime")
        response = requests.get(url, params=params)
        
        # Handle rate limiting
        if response.status_code == 429:
            print("Rate limited, waiting 2 seconds...")
            time.sleep(2)
            response = requests.get(url, params=params)
        
        response.raise_for_status()
        data = response.json()
        
        # Increment the page for next time
        current_page += 1
        
        # Save the updated page number to file
        os.makedirs(os.path.dirname(PAGE_TRACKER_FILE), exist_ok=True)
        with open(PAGE_TRACKER_FILE, 'w') as f:
            json.dump({'current_page': current_page}, f)
        
        # Get user's anime IDs to avoid duplicates
        user_anime_ids = []
        if current_user.is_authenticated:
            watched_list = get_user_anime_list(current_user.id, 'watched')
            not_watched_list = get_user_anime_list(current_user.id, 'not_watched')
            user_anime_ids = [a["id"] for a in watched_list + not_watched_list]
        
        queue_ids = [a["id"] for a in anime_queue]
        
        # Track how many new anime we add
        added_count = 0
        
        # Process each anime entry
        for item in data.get("data", []):
            anime_id = item.get("mal_id")
            
            # Skip if already in our lists or queue
            if (anime_id in user_anime_ids or anime_id in queue_ids):
                continue
            
            # Format the anime data
            anime = {
                "id": anime_id,
                "title": item.get("title", "Unknown Title"),
                "episodes": item.get("episodes") if item.get("episodes") is not None else "N/A",
                "main_picture": {
                    "medium": item.get("images", {}).get("jpg", {}).get("image_url", "")
                },
                "score": item.get("score", "N/A")
            }
            
            # Add to queue
            anime_queue.append(anime)
            added_count += 1
        
        print(f"Added {added_count} new anime to queue")
        if added_count > 0:
            flash(f"Successfully fetched {added_count} new popular anime!")
        else:
            flash("No new anime found to add. Try again later.")
            
    except Exception as e:
        print(f"Error fetching anime: {e}")
        flash(f"Error fetching anime: {e}")

def get_next_anime():
    """Return the next anime from the queue; fetch more if needed."""
    global anime_queue
    if not anime_queue:
        fetch_more_anime()
    return anime_queue[0] if anime_queue else None

@app.route("/")
def index():
    """Display one anime at a time along with total watched and not watched counts."""
    current_anime = get_next_anime()
    
    watched_count = 0
    not_watched_count = 0
    
    if current_user.is_authenticated:
        try:
            watched_count, not_watched_count = get_status_counts(current_user.id)
        except Exception as e:
            print(f"Error getting status counts: {e}")
            flash("There was an issue accessing your anime lists. Try visiting the debug page.")
    
    return render_template("index.html", 
                           anime=current_anime,
                           watched_count=watched_count, 
                           not_watched_count=not_watched_count,
                           get_url_for=get_url_for,
                           is_authenticated=current_user.is_authenticated)

@app.route("/mark", methods=["POST"])
@login_required
def mark():
    """
    Mark the current anime as watched or not watched.
    Remove it from the queue and then redirect back to the home page.
    """
    status = request.form.get("status")  # expected: "watched" or "not_watched"
    anime_json = request.form.get("anime")
    
    if not status:
        flash("Error: No status provided")
        return redirect(get_url_for("index"))
        
    if not anime_json:
        flash("Error: No anime data provided")
        return redirect(get_url_for("index"))
    
    try:
        anime = json.loads(anime_json)
        
        # Mark the anime for the current user
        mark_anime_for_user(current_user.id, anime, status)
        flash(f"Successfully marked '{anime['title']}' as {status}!")
        
        # Remove the marked anime from the queue
        global anime_queue
        anime_queue = [a for a in anime_queue if a["id"] != anime["id"]]
        
        # If the queue is empty, try to fetch more anime
        if not anime_queue:
            fetch_more_anime()
            
    except json.decoder.JSONDecodeError as e:
        flash(f"Error: Invalid anime data format: {e}")
        print(f"JSON decode error: {e}")
        return redirect(get_url_for("index"))
    except Exception as e:
        flash(f"Error marking anime: {e}")
        print(f"Unexpected error: {e}")
        return redirect(get_url_for("index"))
    
    return redirect(get_url_for("index"))

@app.route("/direct_mark/<int:anime_id>/<status>")
@login_required
def direct_mark(anime_id, status):
    """
    Alternative method to mark anime by ID directly.
    This provides a fallback if the form submission isn't working.
    """
    if status not in ["watched", "not_watched"]:
        flash("Invalid status. Must be 'watched' or 'not_watched'.")
        return redirect(get_url_for("index"))
    
    # Check if this anime is in our queue
    global anime_queue
    anime = next((a for a in anime_queue if a["id"] == anime_id), None)
    
    if not anime:
        # If not in queue, fetch it from the API
        try:
            url = f"{JIKAN_API_BASE}/anime/{anime_id}"
            response = requests.get(url)
            response.raise_for_status()
            data = response.json().get("data", {})
            
            anime = {
                "id": data.get("mal_id"),
                "title": data.get("title"),
                "episodes": data.get("episodes") if data.get("episodes") is not None else "N/A",
                "main_picture": {
                    "medium": data.get("images", {}).get("jpg", {}).get("image_url", "")
                },
                "score": data.get("score", "N/A")
            }
        except Exception as e:
            flash(f"Error fetching anime details: {e}")
            return redirect(get_url_for("index"))
    
    # Mark the anime for the current user
    mark_anime_for_user(current_user.id, anime, status)
    flash(f"Successfully marked '{anime['title']}' as {status}!")
    
    # Remove from queue if present
    anime_queue = [a for a in anime_queue if a["id"] != anime_id]
    
    # If the queue is empty, try to fetch more anime
    if not anime_queue:
        fetch_more_anime()
    
    return redirect(get_url_for("index"))

@app.route("/fetch")
def fetch():
    """Manually trigger a fetch for more anime."""
    fetch_more_anime()
    flash("Fetched additional anime!")
    return redirect(get_url_for("index"))

@app.route("/watched")
@login_required
def watched():
    """Display the list of anime marked as watched."""
    watched_list = get_user_anime_list(current_user.id, 'watched')
    return render_template("list.html", title="Watched Anime", anime_list=watched_list, get_url_for=get_url_for)

@app.route("/not_watched")
@login_required
def not_watched():
    """Display the list of anime marked as not watched."""
    not_watched_list = get_user_anime_list(current_user.id, 'not_watched')
    return render_template("list.html", title="Not Watched Anime", anime_list=not_watched_list, get_url_for=get_url_for)

@app.route("/change_status/<int:anime_id>/<status>")
@login_required
def change_status(anime_id, status):
    """
    Route to change an anime's status.
    """
    if status not in ["watched", "not_watched"]:
        flash("Invalid status. Must be 'watched' or 'not_watched'.")
        return redirect(request.referrer or get_url_for("index"))
    
    success = change_anime_status_for_user(current_user.id, anime_id, status)
    
    # Store the search query if it exists in the session
    search_query = session.get('search_query', '')
    
    if success:
        # Get the anime title for the flash message
        anime = Anime.query.filter_by(mal_id=anime_id).first()
        anime_title = anime.title if anime else "the anime"
        
        status_text = "watched" if status == "watched" else "not watched"
        flash(f"Changed '{anime_title}' status to {status_text}!")
    else:
        flash(f"Could not change anime status. Anime not found or already in that status.")
    
    # Redirect back to the referring page
    if request.referrer and 'search' in request.referrer and search_query:
        return redirect(url_for('search', query=search_query))
    return redirect(request.referrer or get_url_for("index"))

@app.route("/search", methods=["GET", "POST"])
def search():
    """Search for anime by title."""
    results = []
    query = request.args.get("query", "") or request.form.get("query", "")
    
    # Save the query to session for later use when redirecting
    if query:
        session['search_query'] = query
    
    if query:
        try:
            url = f"{JIKAN_API_BASE}/anime"
            params = {"q": query, "limit": 20}
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            for item in data.get("data", []):
                anime = {
                    "id": item.get("mal_id"),
                    "title": item.get("title"),
                    "episodes": item.get("episodes") if item.get("episodes") is not None else "N/A",
                    "main_picture": {
                        "medium": item.get("images", {}).get("jpg", {}).get("image_url", "")
                    },
                    "score": item.get("score", "N/A"),
                    "status": None
                }
                
                # Check if the user is authenticated and get the anime status
                if current_user.is_authenticated:
                    anime["status"] = get_anime_status_for_user(current_user.id, anime["id"])
                
                results.append(anime)
                
            if not results:
                flash("No results found. Try a different search term.")
        except Exception as e:
            flash(f"Error searching for anime: {e}")
    
    return render_template("search.html", results=results, query=query, get_url_for=get_url_for)

@app.route("/mark_search", methods=["POST"])
@login_required
def mark_search():
    """Mark an anime from search results as watched or not watched."""
    anime_id = request.form.get("anime_id")
    status = request.form.get("status")
    query = session.get('search_query', '')
    
    if not anime_id or not status:
        flash("Missing required parameters")
        return redirect(url_for('search', query=query))
    
    try:
        # Fetch anime details from API
        url = f"{JIKAN_API_BASE}/anime/{anime_id}"
        response = requests.get(url)
        response.raise_for_status()
        data = response.json().get("data", {})
        
        anime = {
            "id": data.get("mal_id"),
            "title": data.get("title"),
            "episodes": data.get("episodes") if data.get("episodes") is not None else "N/A",
            "main_picture": {
                "medium": data.get("images", {}).get("jpg", {}).get("image_url", "")
            },
            "score": data.get("score", "N/A")
        }
        
        # Mark the anime for the current user
        mark_anime_for_user(current_user.id, anime, status)
        flash(f"Anime marked as {status}!")
    except Exception as e:
        flash(f"Error marking anime: {e}")
        
    return redirect(url_for('search', query=query))

if __name__ == "__main__":
    app.run(debug=True)