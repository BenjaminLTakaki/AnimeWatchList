import os
import json
import requests
import time
import random
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory

# Determine if running in production or locally
is_production = os.environ.get('RENDER', False)

# Configure Flask app
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


# Helper function to handle URLs in production vs development
def get_url_for(*args, **kwargs):
    url = url_for(*args, **kwargs)
    if is_production and not url.startswith('/animewatchlist'):
        url = f"/animewatchlist{url}"
    return url

# Set application root if in production
if is_production:
    app.config['APPLICATION_ROOT'] = '/projects/animewatchlist'
    # Also add this to help with URL generation
    app.config['PREFERRED_URL_SCHEME'] = 'https'

# Global anime queue to serve one anime at a time
anime_queue = []

# Directory and file paths for status tracking
DATA_DIR = "projects/animewatchlist/data"
os.makedirs(DATA_DIR, exist_ok=True)
WATCHED_FILE = os.path.join(DATA_DIR, "watched.json")
NOT_WATCHED_FILE = os.path.join(DATA_DIR, "not_watched.json")

# Jikan API base URL (no authentication needed)
JIKAN_API_BASE = "https://api.jikan.moe/v4"

def ensure_status_files():
    """Ensure that status JSON files exist and are properly initialized."""
    for file in [WATCHED_FILE, NOT_WATCHED_FILE]:
        if not os.path.exists(file) or os.path.getsize(file) == 0:
            with open(file, "w", encoding="utf-8") as f:
                json.dump([], f, indent=2)

ensure_status_files()

def load_json_file(filepath):
    """Load JSON data from a file. Reinitialize the file if its content is invalid."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.decoder.JSONDecodeError:
        # If the file content is invalid, reinitialize it
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump([], f, indent=2)
        return []
    except Exception:
        return []

def save_json_file(filepath, data):
    """Save JSON data to a file."""
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def fetch_more_anime():
    """
    Fetch a batch of most popular anime from the Jikan API with persistent page tracking.
    """
    global anime_queue
    print("Fetching popular anime...")
    
    # File to store the current page
    PAGE_TRACKER_FILE = os.path.join(DATA_DIR, "page_tracker.json")
    
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
        with open(PAGE_TRACKER_FILE, 'w') as f:
            json.dump({'current_page': current_page}, f)
        
        # Load existing anime IDs to avoid duplicates
        watched_list = load_json_file(WATCHED_FILE)
        not_watched_list = load_json_file(NOT_WATCHED_FILE)
        watched_ids = [a["id"] for a in watched_list]
        not_watched_ids = [a["id"] for a in not_watched_list]
        queue_ids = [a["id"] for a in anime_queue]
        
        # Track how many new anime we add
        added_count = 0
        
        # Process each anime entry
        for item in data.get("data", []):
            anime_id = item.get("mal_id")
            
            # Skip if already in our lists or queue
            if (anime_id in watched_ids or 
                anime_id in not_watched_ids or 
                anime_id in queue_ids):
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

def mark_anime(anime, status):
    """Record the anime as watched or not watched by updating the appropriate JSON file."""
    filename = WATCHED_FILE if status == "watched" else NOT_WATCHED_FILE
    anime_list = load_json_file(filename)
    
    # Prevent duplicate entries
    if anime["id"] not in [a["id"] for a in anime_list]:
        anime_list.append(anime)
        save_json_file(filename, anime_list)

def get_status_counts():
    """Return counts for watched and not watched anime."""
    watched = load_json_file(WATCHED_FILE)
    not_watched = load_json_file(NOT_WATCHED_FILE)
    return len(watched), len(not_watched)

def change_anime_status(anime_id, new_status):
    """
    Change an anime's status from watched to not watched or vice versa.
    
    Args:
        anime_id: The ID of the anime to change
        new_status: The new status ('watched' or 'not_watched')
    
    Returns:
        bool: True if successful, False otherwise
    """
    if new_status not in ["watched", "not_watched"]:
        print(f"Invalid status: {new_status}")
        return False
    
    # Load both lists
    watched_list = load_json_file(WATCHED_FILE)
    not_watched_list = load_json_file(NOT_WATCHED_FILE)
    
    # Check if anime exists in watched list
    anime_in_watched = None
    for anime in watched_list:
        if anime["id"] == anime_id:
            anime_in_watched = anime
            break
    
    # Check if anime exists in not watched list
    anime_in_not_watched = None
    for anime in not_watched_list:
        if anime["id"] == anime_id:
            anime_in_not_watched = anime
            break
    
    print(f"Anime ID: {anime_id}")
    print(f"New status: {new_status}")
    print(f"Found in watched list: {anime_in_watched is not None}")
    print(f"Found in not watched list: {anime_in_not_watched is not None}")
    
    # Handle moving to watched
    if new_status == "watched":
        # If already in watched list, do nothing
        if anime_in_watched:
            print("Anime already in watched list")
            return True
        
        # If in not watched list, move it
        if anime_in_not_watched:
            # Remove from not watched list
            not_watched_list = [a for a in not_watched_list if a["id"] != anime_id]
            save_json_file(NOT_WATCHED_FILE, not_watched_list)
            
            # Add to watched list
            watched_list.append(anime_in_not_watched)
            save_json_file(WATCHED_FILE, watched_list)
            print("Moved anime from not watched to watched")
            return True
    
    # Handle moving to not watched
    elif new_status == "not_watched":
        # If already in not watched list, do nothing
        if anime_in_not_watched:
            print("Anime already in not watched list")
            return True
        
        # If in watched list, move it
        if anime_in_watched:
            # Remove from watched list
            watched_list = [a for a in watched_list if a["id"] != anime_id]
            save_json_file(WATCHED_FILE, watched_list)
            
            # Add to not watched list
            not_watched_list.append(anime_in_watched)
            save_json_file(NOT_WATCHED_FILE, not_watched_list)
            print("Moved anime from watched to not watched")
            return True
    
    # If we couldn't find the anime in either list, try to fetch it from API
    if not anime_in_watched and not anime_in_not_watched:
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
            
            # Add to appropriate list
            if new_status == "watched":
                watched_list.append(anime)
                save_json_file(WATCHED_FILE, watched_list)
                print("Added new anime to watched list")
            else:
                not_watched_list.append(anime)
                save_json_file(NOT_WATCHED_FILE, not_watched_list)
                print("Added new anime to not watched list")
                
            return True
        except Exception as e:
            print(f"Error fetching anime: {e}")
            return False
            
    return False

# Helper function to handle URLs in production vs development
def get_url_for(*args, **kwargs):
    """Generate URL considering the application root in production."""
    url = url_for(*args, **kwargs)
    if is_production:
        # Make sure the application root is properly prepended
        if not url.startswith('/animewatchlist'):
            url = f"/animewatchlist{url}"
    return url

@app.route("/change_status/<int:anime_id>/<status>")
def change_status(anime_id, status):
    """
    Route to change an anime's status.
    """
    if status not in ["watched", "not_watched"]:
        flash("Invalid status. Must be 'watched' or 'not_watched'.")
        return redirect(request.referrer or get_url_for("index"))
    
    success = change_anime_status(anime_id, status)
    
    if success:
        # Get the anime title for the flash message
        anime_title = "the anime"
        watched_list = load_json_file(WATCHED_FILE)
        not_watched_list = load_json_file(NOT_WATCHED_FILE)
        
        for anime in watched_list + not_watched_list:
            if anime["id"] == anime_id:
                anime_title = anime["title"]
                break
        
        status_text = "watched" if status == "watched" else "not watched"
        flash(f"Changed '{anime_title}' status to {status_text}!")
    else:
        flash(f"Could not change anime status. Anime not found or already in that status.")
    
    # Redirect back to the referring page
    return redirect(request.referrer or get_url_for("index"))

@app.route("/")
def index():
    """Display one anime at a time along with total watched and not watched counts."""
    current_anime = get_next_anime()
    watched_count, not_watched_count = get_status_counts()
    return render_template("index.html", 
                           anime=current_anime,
                           watched_count=watched_count, 
                           not_watched_count=not_watched_count,
                           get_url_for=get_url_for)

@app.route("/mark", methods=["POST"])
def mark():
    """
    Mark the current anime as watched or not watched.
    Remove it from the queue and then redirect back to the home page.
    """
    # Debug information
    print("Form data received:", request.form)
    
    status = request.form.get("status")  # expected: "watched" or "not_watched"
    anime_json = request.form.get("anime")
    
    if not status:
        flash("Error: No status provided")
        return redirect(get_url_for("index"))
        
    if not anime_json:
        flash("Error: No anime data provided")
        return redirect(get_url_for("index"))
    
    try:
        # Print the raw JSON string for debugging
        print("Raw anime JSON:", anime_json)
        anime = json.loads(anime_json)
        print("Parsed anime data:", anime)
        
        # Validate required fields
        if "id" not in anime or "title" not in anime:
            flash("Error: Invalid anime data (missing required fields)")
            return redirect(get_url_for("index"))
            
        # Ensure all required fields with defaults
        anime.setdefault("episodes", "N/A")
        anime.setdefault("score", "N/A")
        anime.setdefault("main_picture", {"medium": ""})
        
        # Mark the anime
        mark_anime(anime, status)
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

@app.route("/fetch")
def fetch():
    """Manually trigger a fetch for more anime."""
    fetch_more_anime()
    flash("Fetched additional anime!")
    return redirect(get_url_for("index"))

@app.route("/watched")
def watched():
    """Display the list of anime marked as watched."""
    watched_list = load_json_file(WATCHED_FILE)
    return render_template("list.html", title="Watched Anime", anime_list=watched_list, get_url_for=get_url_for)

@app.route("/not_watched")
def not_watched():
    """Display the list of anime marked as not watched."""
    not_watched_list = load_json_file(NOT_WATCHED_FILE)
    return render_template("list.html", title="Not Watched Anime", anime_list=not_watched_list, get_url_for=get_url_for)

@app.route("/search", methods=["GET", "POST"])
def search():
    """Search for anime by title."""
    results = []
    query = ""
    
    if request.method == "POST":
        query = request.form.get("query", "")
        if query:
            try:
                url = f"{JIKAN_API_BASE}/anime"
                params = {"q": query, "limit": 20}
                response = requests.get(url, params=params)
                response.raise_for_status()
                data = response.json()
                
                watched_list = load_json_file(WATCHED_FILE)
                not_watched_list = load_json_file(NOT_WATCHED_FILE)
                watched_ids = [a["id"] for a in watched_list]
                not_watched_ids = [a["id"] for a in not_watched_list]
                
                for item in data.get("data", []):
                    anime = {
                        "id": item.get("mal_id"),
                        "title": item.get("title"),
                        "episodes": item.get("episodes") if item.get("episodes") is not None else "N/A",
                        "main_picture": {
                            "medium": item.get("images", {}).get("jpg", {}).get("image_url", "")
                        },
                        "score": item.get("score", "N/A"),
                        "status": "watched" if item.get("mal_id") in watched_ids else 
                                   "not_watched" if item.get("mal_id") in not_watched_ids else None
                    }
                    results.append(anime)
                    
                if not results:
                    flash("No results found. Try a different search term.")
            except Exception as e:
                flash(f"Error searching for anime: {e}")
    
    return render_template("search.html", results=results, query=query, get_url_for=get_url_for)

@app.route("/mark_search", methods=["POST"])
def mark_search():
    """Mark an anime from search results as watched or not watched."""
    anime_id = request.form.get("anime_id")
    status = request.form.get("status")
    
    if not anime_id or not status:
        flash("Missing required parameters")
        return redirect(request.referrer or get_url_for("search"))
    
    # Always mark search results as not watched first
    if status == "watched":
        change_anime_status(int(anime_id), "not_watched")
        # Then if needed, mark as watched
        change_anime_status(int(anime_id), "watched")
    else:
        change_anime_status(int(anime_id), status)
    
    flash(f"Anime marked as {status}!")
    return redirect(request.referrer or get_url_for("search"))

@app.route("/direct_mark/<int:anime_id>/<status>")
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
    
    # Mark the anime
    mark_anime(anime, status)
    flash(f"Successfully marked '{anime['title']}' as {status}!")
    
    # Remove from queue if present
    anime_queue = [a for a in anime_queue if a["id"] != anime_id]
    
    # Get the next anime
    if not anime_queue:
        fetch_more_anime()
    
    return redirect(get_url_for("index"))

if __name__ == "__main__":
    app.run(debug=True)