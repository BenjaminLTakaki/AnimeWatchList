import os
import json
import requests
import time
import datetime
import traceback # Added for detailed error logging
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_login import login_required, current_user
from dotenv import load_dotenv
from sqlalchemy import inspect
from flask_migrate import Migrate

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
db = init_auth(app, get_url_for, lambda user_id: (0, 0))
migrate = Migrate(app, db)

# Create tables explicitly
with app.app_context():
    try:
        db.create_all()
    except Exception as e:
        print(f"Warning: Could not create tables: {e}")

# Now that the database is initialized, we can import the User model
from auth import User

# Import and initialize user data AFTER db is initialized
from user_data import init_user_data, get_user_anime_list, get_status_counts, get_user_stats
from user_data import mark_anime_for_user, change_anime_status_for_user, get_anime_status_for_user

# Initialize user data models with the database from auth
try:
    Anime, UserAnimeList = init_user_data(db)
except Exception as e:
    print(f"Warning: Could not initialize user data models: {e}")
    Anime = None
    UserAnimeList = None

# Now that user_data is initialized with the real get_status_counts,
# let's update auth's reference to it
import auth
auth.get_status_counts = get_status_counts

# Create all tables again to ensure all models are registered
with app.app_context():
    try:
        db.create_all()
    except Exception as e:
        print(f"Warning: Could not create all tables: {e}")

# Global anime queue to serve one anime at a time
anime_queue = []

# Make sure data directory exists
os.makedirs('data', exist_ok=True)

# Jikan API base URL
JIKAN_API_BASE = "https://api.jikan.moe/v4"

def check_enhanced_features():
    """Check if the database has enhanced features enabled."""
    try:
        inspector = inspect(db.engine)
        columns = [col['name'] for col in inspector.get_columns('anime')]
        return 'episodes_int' in columns and 'score_float' in columns
    except:
        return False

def fetch_anime_details(anime_id):
    """Fetch detailed anime information from MAL API."""
    try:
        url = f"{JIKAN_API_BASE}/anime/{anime_id}/full"
        response = requests.get(url)
        
        if response.status_code == 429:
            time.sleep(2)
            response = requests.get(url)
        
        response.raise_for_status()
        return response.json().get("data", {})
    except Exception as e:
        print(f"Error fetching anime details for ID {anime_id}: {e}")
        return None

def fetch_more_anime():
    """Fetch a batch of most popular anime from the Jikan API with persistent page tracking."""
    global anime_queue
    print("Fetching popular anime...")
    
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
        "limit": 20
    }
    
    try:
        print(f"Requesting page {current_page} of top anime")
        response = requests.get(url, params=params)
        
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
            try:
                watched_list = get_user_anime_list(current_user.id)
                user_anime_ids = [a["id"] for a in watched_list]
            except Exception as e:
                print(f"Warning: Could not get user anime list: {e}")
        
        queue_ids = [a["id"] for a in anime_queue]
        
        # Track how many new anime we add
        added_count = 0
        
        # Process each anime entry
        for item in data.get("data", []):
            anime_id = item.get("mal_id")
            
            # Skip if already in our lists or queue
            if anime_id in user_anime_ids or anime_id in queue_ids:
                continue
            
            # Format the anime data with basic info
            anime = {
                "id": anime_id,
                "title": item.get("title", "Unknown Title"),
                "episodes": item.get("episodes") if item.get("episodes") is not None else "N/A",
                "main_picture": {
                    "medium": item.get("images", {}).get("jpg", {}).get("image_url", "")
                },
                "score": item.get("score", "N/A")
            }
            
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

def skip_current_anime():
    """Skip the current anime by removing it from the queue."""
    global anime_queue
    if anime_queue:
        skipped_anime = anime_queue.pop(0)
        print(f"Skipped anime: {skipped_anime.get('title', 'Unknown')}")
        return skipped_anime
    return None

@app.route("/")
def index():
    """Display one anime at a time along with total watched count."""
    current_anime = get_next_anime()
    
    watched_count = 0
    
    if current_user.is_authenticated:
        try:
            watched_count, _ = get_status_counts(current_user.id)
        except Exception as e:
            print(f"Error getting status counts: {e}")
            flash("There was an issue accessing your anime lists.")
    
    return render_template("index.html", 
                           anime=current_anime,
                           watched_count=watched_count,
                           get_url_for=get_url_for,
                           is_authenticated=current_user.is_authenticated)

@app.route("/skip")
def skip():
    """Skip the current anime without marking it."""
    skipped_anime = skip_current_anime()
    if skipped_anime:
        flash(f"Skipped '{skipped_anime.get('title', 'Unknown anime')}'")
    else:
        flash("No anime to skip")
    
    # If the queue is empty after skipping, fetch more
    if not anime_queue:
        fetch_more_anime()
    
    return redirect(get_url_for("index"))

@app.route("/mark", methods=["POST"])
@login_required
def mark():
    """Mark the current anime as watched only."""
    status = request.form.get("status")
    anime_json = request.form.get("anime")
    
    if status != "watched":
        flash("Only 'watched' status is supported")
        return redirect(get_url_for("index"))
        
    if not anime_json:
        flash("Error: No anime data provided")
        return redirect(get_url_for("index"))
    
    try:
        anime_data = json.loads(anime_json)
        
        # Fetch detailed anime information from MAL API if enhanced features are available
        if check_enhanced_features():
            detailed_anime = fetch_anime_details(anime_data["id"])
            if detailed_anime:
                anime_data.update(detailed_anime)
        
        # Mark the anime for the current user
        mark_anime_for_user(current_user.id, anime_data, status)
        flash(f"Added '{anime_data['title']}' to your watched list!")
        
        # Remove the marked anime from the queue
        global anime_queue
        anime_queue = [a for a in anime_queue if a["id"] != anime_data["id"]]
        
        # If the queue is empty, try to fetch more anime
        if not anime_queue:
            fetch_more_anime()
            
    except json.decoder.JSONDecodeError as e:
        flash(f"Error: Invalid anime data format: {e}")
        return redirect(get_url_for("index"))
    except Exception as e:
        flash(f"Error marking anime: {e}")
        return redirect(get_url_for("index"))
    
    return redirect(get_url_for("index"))

@app.route("/direct_mark/<int:anime_id>/<status>")
@login_required
def direct_mark(anime_id, status):
    """Alternative method to mark anime by ID directly."""
    if status != "watched":
        flash("Only 'watched' status is supported")
        return redirect(get_url_for("index"))
    
    # Check if this anime is in our queue
    global anime_queue
    anime = next((a for a in anime_queue if a["id"] == anime_id), None)
    
    if not anime:
        # If not in queue, fetch it from the API
        try:
            if check_enhanced_features():
                detailed_anime = fetch_anime_details(anime_id)
                if detailed_anime:
                    anime = {
                        "id": detailed_anime.get("mal_id"),
                        "title": detailed_anime.get("title"),
                        "episodes": detailed_anime.get("episodes") if detailed_anime.get("episodes") is not None else "N/A",
                        "main_picture": {
                            "medium": detailed_anime.get("images", {}).get("jpg", {}).get("image_url", "")
                        },
                        "score": detailed_anime.get("score", "N/A")
                    }
                    anime.update(detailed_anime)
                else:
                    flash("Error fetching anime details")
                    return redirect(get_url_for("index"))
            else:
                # Basic fetch without enhanced details
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
    else:
        # Fetch detailed information for anime in queue if enhanced features are available
        if check_enhanced_features():
            detailed_anime = fetch_anime_details(anime_id)
            if detailed_anime:
                anime.update(detailed_anime)
    
    # Mark the anime for the current user
    mark_anime_for_user(current_user.id, anime, status)
    flash(f"Added '{anime['title']}' to your watched list!")
    
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
    print(f"User {current_user.id} attempting to access /watched route.") # New log
    try:
        print(f"Calling get_user_anime_list for user {current_user.id}.") # New log
        watched_list = get_user_anime_list(current_user.id)
        print(f"Successfully retrieved watched_list for user {current_user.id}. Count: {len(watched_list)}") # New log
        return render_template("list.html",  # Changed "watched.html" to "list.html"
                             anime_list=watched_list, 
                             list_type="Watched", # Added list_type for context in the template
                             get_url_for=get_url_for)
    except Exception as e:
        detailed_error = traceback.format_exc()
        print(f"Error in /watched route for user {current_user.id}: {e}\n{detailed_error}") # Updated log
        flash("Error loading your watched list. Please try again.")
        return redirect(get_url_for("index"))

@app.route("/stats")
@login_required
def stats():
    """Display comprehensive statistics for the user."""
    try:
        user_stats = get_user_stats(current_user.id)
        return render_template("stats.html", stats=user_stats, get_url_for=get_url_for)
    except Exception as e:
        print(f"Error getting user stats: {e}")
        flash("Error loading statistics. Please try again later.")
        return redirect(get_url_for("index"))

@app.route("/remove_anime/<int:anime_id>")
@login_required
def remove_anime(anime_id):
    """Remove an anime from the user's watched list."""
    try:
        success = change_anime_status_for_user(current_user.id, anime_id, 'remove')
        
        if success:
            if Anime:
                anime = Anime.query.filter_by(mal_id=anime_id).first()
                anime_title = anime.title if anime else "the anime"
            else:
                anime_title = "the anime"
            flash(f"Removed '{anime_title}' from your watched list!")
        else:
            flash("Could not remove anime. Anime not found in your list.")
    except Exception as e:
        print(f"Error removing anime: {e}")
        flash("Error removing anime. Please try again.")
    
    return redirect(request.referrer or get_url_for("watched"))

@app.route("/search", methods=["GET", "POST"])
def search():
    """Search for anime by title."""
    results = []
    query = request.args.get("query", "") or request.form.get("query", "")
    
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
                    try:
                        anime["status"] = get_anime_status_for_user(current_user.id, anime["id"])
                    except Exception as e:
                        print(f"Error getting anime status: {e}")
                
                results.append(anime)
                
            if not results:
                flash("No results found. Try a different search term.")
        except Exception as e:
            flash(f"Error searching for anime: {e}")
    
    return render_template("search.html", results=results, query=query, get_url_for=get_url_for)

@app.route("/mark_search", methods=["POST"])
@login_required
def mark_search():
    """Mark an anime from search results as watched."""
    anime_id = request.form.get("anime_id")
    status = request.form.get("status")
    query = session.get('search_query', '')
    
    if not anime_id or status != "watched":
        flash("Missing required parameters or invalid status")
        return redirect(url_for('search', query=query))
    
    try:
        # Fetch detailed anime information if enhanced features are available
        if check_enhanced_features():
            detailed_anime = fetch_anime_details(anime_id)
            if detailed_anime:
                mark_anime_for_user(current_user.id, detailed_anime, status)
                flash(f"Added anime to your watched list!")
            else:
                flash("Error fetching anime details")
        else:
            # Basic functionality
            url = f"{JIKAN_API_BASE}/anime/{anime_id}"
            response = requests.get(url)
            response.raise_for_status()
            data = response.json().get("data", {})
            
            anime_data = {
                "id": data.get("mal_id"),
                "title": data.get("title"),
                "episodes": data.get("episodes") if data.get("episodes") is not None else "N/A",
                "main_picture": {
                    "medium": data.get("images", {}).get("jpg", {}).get("image_url", "")
                },
                "score": data.get("score", "N/A")
            }
            
            mark_anime_for_user(current_user.id, anime_data, status)
            flash(f"Added anime to your watched list!")
    except Exception as e:
        flash(f"Error marking anime: {e}")
        
    return redirect(url_for('search', query=query))

if __name__ == "__main__":
    app.run(debug=True)