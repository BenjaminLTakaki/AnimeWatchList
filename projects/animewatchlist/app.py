import os
import json
import requests
import time
import datetime
import traceback
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_login import login_required, current_user
from dotenv import load_dotenv
from sqlalchemy import inspect
from flask_migrate import Migrate

# Import the MAL API functions
from anime_series_grouper import get_anime_details, get_top_anime, search_anime, get_mal_headers

# Load environment variables
load_dotenv()

# MAL API base URL (replacing Jikan)
MAL_API_BASE = "https://api.myanimelist.net/v2"

def create_app(config=None):
    """Create and configure the Flask application."""
    is_production = os.environ.get('RENDER', False)
    
    app = Flask(
        __name__,
        static_url_path='/static' if not is_production else '/animewatchlist/static',
        template_folder='templates'
    )
    
    # Default configuration
    app.secret_key = os.environ.get("FLASK_SECRET_KEY", "anime_tracker_secret")
    
    if is_production:
        app.config['APPLICATION_ROOT'] = '/animewatchlist'
        app.config['PREFERRED_URL_SCHEME'] = 'https'
        app.static_url_path = '/animewatchlist/static'
    else:
        app.static_url_path = '/static'

    # Apply external configuration if provided
    if config:
        app.config.update(config)

    # Define helper function for URL generation
    def get_url_for(*args, **kwargs):
        url = url_for(*args, **kwargs)
        if app.config.get('APPLICATION_ROOT') and not url.startswith(app.config['APPLICATION_ROOT']):
            url = f"{app.config['APPLICATION_ROOT']}{url}"
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

    with app.app_context():
        try:
            db.create_all()
        except Exception as e:
            print(f"Warning: Could not create tables: {e}")

    # Now that the database is initialized, we can import the User model
    from auth import User

    # Import and initialize user data AFTER db is initialized
    from user_data import init_user_data, get_user_anime_list, get_status_counts, get_user_stats
    from user_data import (mark_anime_for_user, change_anime_status_for_user, get_anime_status_for_user,
                           update_anime_rating_for_user, rate_and_mark_anime_for_user, get_anime_rating_for_user)

    # Import the recommendation engine
    from recommendation_engine import get_recommendations

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

    def check_enhanced_features():
        """Check if the database has enhanced features enabled."""
        try:
            inspector = inspect(db.engine)
            columns = [col['name'] for col in inspector.get_columns('anime')]
            return 'episodes_int' in columns and 'score_float' in columns
        except:
            return False

    def check_rating_feature():
        """Check if the database has rating feature enabled."""
        try:
            inspector = inspect(db.engine)
            columns = [col['name'] for col in inspector.get_columns('user_anime_list')]
            return 'user_rating' in columns
        except:
            return False

    def fetch_anime_details(anime_id):
        """Fetch detailed anime information from MAL API - UPDATED FOR MAL API."""
        return get_anime_details(anime_id)

    def fetch_more_anime():
        """Fetch a batch of popular anime from MAL API - UPDATED FOR MAL API."""
        nonlocal anime_queue
        print("Fetching popular anime from MAL API...")
        
        PAGE_TRACKER_FILE = os.path.join('data', "page_tracker.json")
        
        # Load the current page from file for persistence
        try:
            if os.path.exists(PAGE_TRACKER_FILE):
                with open(PAGE_TRACKER_FILE, 'r') as f:
                    current_page = json.load(f).get('current_page', 0)
            else:
                current_page = 0
        except Exception:
            current_page = 0
        
        print(f"Current offset: {current_page}")
        
        # MAL API ranking types to cycle through
        ranking_types = ['all', 'airing', 'tv', 'movie', 'bypopularity']
        ranking_type = ranking_types[current_page % len(ranking_types)]
        
        try:
            print(f"Requesting {ranking_type} anime")
            
            # Use the helper function to get top anime WITH OFFSET
            offset = (current_page // len(ranking_types)) * 20
            top_anime_list = get_top_anime(ranking_type=ranking_type, limit=20, offset=offset)

            
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
            
            # Process each anime entry from MAL API
            for item in top_anime_list:
                anime_id = item.get("mal_id")
                
                # Skip if already in our lists or queue
                if anime_id in user_anime_ids or anime_id in queue_ids:
                    continue
                
                # Format the anime data to match the expected structure
                anime = {
                    "id": anime_id,
                    "title": item.get("title", "Unknown Title"),
                    "episodes": item.get("episodes") if item.get("episodes") is not None else "N/A",
                    "main_picture": {
                        "medium": item.get("main_picture", {}).get("medium", "")
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
        nonlocal anime_queue
        if not anime_queue:
            fetch_more_anime()
        return anime_queue[0] if anime_queue else None

    def skip_current_anime():
        """Skip the current anime by removing it from the queue."""
        nonlocal anime_queue
        if anime_queue:
            skipped_anime = anime_queue.pop(0)
            print(f"Skipped anime: {skipped_anime.get('title', 'Unknown')}")
            return skipped_anime
        return None

    @app.route("/")
    def index():
        """Display one anime at a time along with total watched count and rating option."""
        current_anime = get_next_anime()
        
        watched_count = 0
        current_rating = None
        
        if current_user.is_authenticated:
            try:
                watched_count, _ = get_status_counts(current_user.id)
                if current_anime and check_rating_feature():
                    current_rating = get_anime_rating_for_user(current_user.id, current_anime['id'])
            except Exception as e:
                print(f"Error getting status counts: {e}")
                flash("There was an issue accessing your anime lists.")
        
        return render_template("index.html", 
                               anime=current_anime,
                               watched_count=watched_count,
                               current_rating=current_rating,
                               has_rating_feature=check_rating_feature(),
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
            nonlocal anime_queue
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

    @app.route("/rate_anime", methods=["POST"])
    @login_required
    def rate_anime():
        """Rate an anime and optionally mark it as watched."""
        if not check_rating_feature():
            return jsonify({"success": False, "message": "Rating feature not available"})
        
        try:
            anime_id = request.form.get("anime_id")
            rating = request.form.get("rating")
            
            if not anime_id:
                return jsonify({"success": False, "message": "Anime ID required"})
            
            # Validate rating
            try:
                rating = int(rating) if rating is not None else None
                if rating is not None and not (0 <= rating <= 5):
                    return jsonify({"success": False, "message": "Rating must be between 0 and 5"})
            except ValueError:
                return jsonify({"success": False, "message": "Invalid rating format"})
            
            anime_id = int(anime_id)
            marked_as_watched = False
            
            # Check if anime is already in user's list
            current_status = get_anime_status_for_user(current_user.id, anime_id)
            
            if current_status == 'watched':
                # Update existing rating
                success = update_anime_rating_for_user(current_user.id, anime_id, rating)
                if not success:
                    return jsonify({"success": False, "message": "Failed to update rating"})
            else:
                # If rating > 0, mark as watched automatically
                if rating and rating > 0:
                    # Fetch anime data to mark as watched
                    anime_data = None
                    
                    # First check if it's in our queue
                    nonlocal anime_queue
                    anime_data = next((a for a in anime_queue if a["id"] == anime_id), None)
                    
                    if not anime_data:
                        # Fetch from API
                        anime_data = fetch_anime_details(anime_id)
                    
                    if anime_data:
                        mark_anime_for_user(current_user.id, anime_data, 'watched', rating)
                        marked_as_watched = True
                        
                        # Remove from queue if it was there
                        anime_queue = [a for a in anime_queue if a["id"] != anime_id]
                    else:
                        return jsonify({"success": False, "message": "Could not fetch anime data"})
                else:
                    # Just update rating without marking as watched (for rating 0 or None)
                    # But anime needs to exist in watched list to have a rating
                    if rating == 0:
                        success = update_anime_rating_for_user(current_user.id, anime_id, None)
                        if not success:
                            return jsonify({"success": False, "message": "Anime not in your watched list"})
                    else:
                        return jsonify({"success": False, "message": "Anime must be watched to rate it"})
            
            return jsonify({
                "success": True, 
                "message": "Rating saved successfully",
                "marked_as_watched": marked_as_watched
            })
            
        except Exception as e:
            print(f"Error in rate_anime: {e}")
            traceback.print_exc()
            return jsonify({"success": False, "message": "Internal server error"})

    @app.route("/direct_mark/<int:anime_id>/<status>")
    @login_required
    def direct_mark(anime_id, status):
        """Alternative method to mark anime by ID directly."""
        if status != "watched":
            flash("Only 'watched' status is supported")
            return redirect(get_url_for("index"))
        
        # Check if this anime is in our queue
        nonlocal anime_queue
        anime = next((a for a in anime_queue if a["id"] == anime_id), None)
        
        if not anime:
            # If not in queue, fetch it from the API
            try:
                anime = fetch_anime_details(anime_id)
                if not anime:
                    flash("Error fetching anime details")
                    return redirect(get_url_for("index"))
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
        """Display the list of anime marked as watched with ratings."""
        print(f"User {current_user.id} attempting to access /watched route.")
        try:
            # Get sorting parameters
            sort_by = request.args.get('sort_by', 'date_added')
            sort_order = request.args.get('sort_order', 'desc')
            
            print(f"Calling get_user_anime_list for user {current_user.id} with sorting: {sort_by} {sort_order}")
            watched_list = get_user_anime_list(current_user.id, sort_by, sort_order)
            print(f"Successfully retrieved watched_list for user {current_user.id}. Count: {len(watched_list)}")
            
            return render_template("list.html",
                                 anime_list=watched_list, 
                                 list_type="Watched",
                                 has_rating_feature=check_rating_feature(),
                                 sort_by=sort_by,
                                 sort_order=sort_order,
                                 get_url_for=get_url_for)
        except Exception as e:
            detailed_error = traceback.format_exc()
            print(f"Error in /watched route for user {current_user.id}: {e}\n{detailed_error}")
            flash("Error loading your watched list. Please try again.")
            return redirect(get_url_for("index"))

    @app.route("/recommendations")
    @login_required
    def recommendations():
        """Display personalized anime recommendations."""
        try:
            # Get user's watched list, which includes ratings
            # The recommendation engine needs the 'mal_id' and 'user_rating' keys
            watched_list = get_user_anime_list(current_user.id)

            if not watched_list:
                flash("You need to watch and rate some anime before we can provide recommendations.", "info")
                return render_template("recommendations.html", recommendations=[])

            # Generate recommendations
            # Using test_mode=True to limit API calls during testing.
            # For production, this should be False.
            recs = get_recommendations(watched_list, test_mode=True)

            return render_template("recommendations.html", recommendations=recs, get_url_for=get_url_for)
        except Exception as e:
            print(f"Error generating recommendations: {e}")
            traceback.print_exc()
            flash("Sorry, there was an error generating recommendations. Please try again later.", "danger")
            return redirect(get_url_for("index"))

    @app.route("/stats")
    @login_required
    def stats():
        """Display comprehensive statistics for the user including rating stats."""
        try:
            user_stats = get_user_stats(current_user.id)
            return render_template("stats.html", 
                                 stats=user_stats, 
                                 has_rating_feature=check_rating_feature(),
                                 get_url_for=get_url_for)
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
        """Search for anime by title with rating display - UPDATED FOR MAL API."""
        results = []
        query = request.args.get("query", "") or request.form.get("query", "")
        
        if query:
            session['search_query'] = query
        
        if query:
            try:
                # Use MAL API search instead of Jikan
                search_results = search_anime(query, limit=20)
                
                for item in search_results:
                    anime = {
                        "id": item.get("mal_id"),
                        "title": item.get("title"),
                        "episodes": item.get("episodes") if item.get("episodes") is not None else "N/A",
                        "main_picture": {
                            "medium": item.get("main_picture", {}).get("medium", "")
                        },
                        "score": item.get("score", "N/A"),
                        "status": None,
                        "user_rating": None
                    }
                    
                    # Check if the user is authenticated and get the anime status and rating
                    if current_user.is_authenticated:
                        try:
                            anime["status"] = get_anime_status_for_user(current_user.id, anime["id"])
                            if check_rating_feature():
                                anime["user_rating"] = get_anime_rating_for_user(current_user.id, anime["id"])
                        except Exception as e:
                            print(f"Error getting anime status/rating: {e}")
                    
                    results.append(anime)
                    
                if not results:
                    flash("No results found. Try a different search term.")
            except Exception as e:
                flash(f"Error searching for anime: {e}")
        
        return render_template("search.html", 
                             results=results, 
                             query=query, 
                             has_rating_feature=check_rating_feature(),
                             get_url_for=get_url_for)

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
            anime_data = fetch_anime_details(anime_id)
            if anime_data:
                mark_anime_for_user(current_user.id, anime_data, status)
                flash(f"Added anime to your watched list!")
            else:
                flash("Error fetching anime details")
        except Exception as e:
            flash(f"Error marking anime: {e}")
            
        return redirect(url_for('search', query=query))

    return app, db

if __name__ == "__main__":
    app, _ = create_app()
    app.run(debug=True)