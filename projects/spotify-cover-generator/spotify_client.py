import spotipy
from spotipy.oauth2 import SpotifyClientCredentials, SpotifyOAuth
from collections import Counter
from models import PlaylistData, GenreAnalysis
from config import SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, SPOTIFY_REDIRECT_URI

# Monitoring and Fault Handling Imports
from .monitoring_system import app_logger, monitor_api_calls
from .fault_handling import fault_tolerant_api_call, GracefulDegradation, circuit_breakers, retry_with_exponential_backoff

app_logger.info("Successfully imported monitoring and fault_handling modules in spotify_client.")

# Global Spotify client
sp = None

@monitor_api_calls("spotify_init") # More specific service name
@retry_with_exponential_backoff(max_retries=3)
def initialize_spotify(use_oauth=False):
    """Initialize Spotify API client"""
    global sp
    try:
        if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
            app_logger.error("spotify_credentials_missing", message="Missing Spotify API credentials.")
            return False
            
        if use_oauth:
            auth_manager = SpotifyOAuth(
                client_id=SPOTIFY_CLIENT_ID,
                client_secret=SPOTIFY_CLIENT_SECRET,
                redirect_uri=SPOTIFY_REDIRECT_URI,
                scope="user-library-read playlist-read-private playlist-read-collaborative user-read-private user-read-email playlist-modify-public playlist-modify-private ugc-image-upload",
                cache_path=".spotify_cache"
            )
        else:
            auth_manager = SpotifyClientCredentials(
                client_id=SPOTIFY_CLIENT_ID,
                client_secret=SPOTIFY_CLIENT_SECRET
            )
            
        sp = spotipy.Spotify(auth_manager=auth_manager, requests_timeout=60, retries=3)
        
        # Test the connection
        try:
            if use_oauth:
                user_info = sp.current_user() # Network call
                app_logger.info("spotify_oauth_connection_success", user_id=user_info.get('id', 'unknown'))
                # Debug premium status detection
                app_logger.debug("spotify_user_details_oauth",
                                 email=user_info.get('email'),
                                 user_id=user_info.get('id'),
                                 product=user_info.get('product'))
            else:
                sp.search(q='test', limit=1) # Network call
                app_logger.info("spotify_client_credentials_connection_success")
            return True
        except spotipy.exceptions.SpotifyException as e:
            app_logger.error("spotify_api_authentication_failed", error=str(e), exc_info=True, use_oauth=use_oauth)
            # If client credentials failed, try OAuth as fallback
            if not use_oauth:
                app_logger.info("spotify_auth_fallback_attempt_oauth")
                return initialize_spotify(use_oauth=True) # Recursive call, retry logic will apply
            return False
    except Exception as e:
        app_logger.error("spotify_api_initialization_failed", error=str(e), exc_info=True)
        return False

@monitor_api_calls("spotify_user_premium_status")
@retry_with_exponential_backoff()
def get_user_premium_status(access_token):
    """Get user's premium status from Spotify API"""
    try:
        import requests
        headers = {'Authorization': f'Bearer {access_token}'}
        response = requests.get('https://api.spotify.com/v1/me', headers=headers)
        
        if response.status_code == 200:
            user_data = response.json()
            app_logger.debug("spotify_user_data_for_premium_check",
                             user_id=user_data.get('id'),
                             email=user_data.get('email'),
                             product=user_data.get('product'),
                             display_name=user_data.get('display_name'))
            
            # Check our premium criteria
            email = user_data.get('email', '').lower()
            spotify_id = user_data.get('id', '').lower()
            
            is_premium_email = email == 'bentakaki7@gmail.com'
            is_premium_spotify = spotify_id == 'benthegamer'
            
            app_logger.debug("spotify_premium_check_details",
                             email_match=is_premium_email, current_email=email,
                             spotify_id_match=is_premium_spotify, current_spotify_id=spotify_id)
            
            return {
                'user_data': user_data,
                'is_premium_by_email': is_premium_email,
                'is_premium_by_spotify_id': is_premium_spotify,
                'is_premium': is_premium_email or is_premium_spotify
            }
        else:
            app_logger.error("fetch_spotify_user_data_failed", status_code=response.status_code, response_text=response.text)
            return None
    except Exception as e:
        app_logger.error("get_user_premium_status_exception", error=str(e), exc_info=True)
    return None

@fault_tolerant_api_call("spotify_api", fallback_func=GracefulDegradation.handle_spotify_failure)
# @monitor_api_calls is implicitly handled by @fault_tolerant_api_call if it wraps it,
# or can be added explicitly if fault_tolerant_api_call doesn't already include performance monitoring.
# Assuming fault_tolerant_api_call includes or replaces monitor_api_calls for this function.
def extract_playlist_data(playlist_url):
    """Extract data from playlist with enhanced error handling"""
    global sp
    
    # Check Spotify client
    if not sp:
        app_logger.info("spotify_client_not_initialized_in_extract_data")
        if not initialize_spotify(): # initialize_spotify is now decorated
            app_logger.error("spotify_client_reinitialization_failed_in_extract_data")
            return {"error": "Failed to initialize Spotify client. Please check your API credentials."}
    
    # Parse URL and check validity
    if "playlist/" not in playlist_url and "album/" not in playlist_url:
        return {"error": "Invalid Spotify URL format. Please provide a valid Spotify playlist or album URL."}
    
    try:
        is_playlist = "playlist/" in playlist_url
        
        if is_playlist:
            # Extract playlist ID more robustly
            try:
                if "playlist/" in playlist_url:
                    item_id = playlist_url.split("playlist/")[-1].split("?")[0].split("/")[0]
                else:
                    app_logger.warning("invalid_playlist_url_format_extract", url=playlist_url)
                    return {"error": "Invalid playlist URL format"}
                
                app_logger.info("processing_playlist_id", item_id=item_id)
                
                # Get playlist info
                playlist_info = sp.playlist(item_id, fields="name,description,owner") # Network call
                item_name = playlist_info.get("name", "Unknown Playlist")
                
                app_logger.info("found_playlist_name", name=item_name)
                
                # Get tracks to analyze genres
                results = sp.playlist_tracks( # Network call
                    item_id,
                    fields="items(track(id,name,artists(id,name)))",
                    market="US",
                    limit=50  
                )
                tracks = results.get("items", [])
                
            except spotipy.exceptions.SpotifyException as e:
                if e.http_status == 404:
                    return {"error": "Playlist not found. Please check if the playlist exists and is public."}
                elif e.http_status == 403:
                    return {"error": "Access denied. The playlist may be private or you may not have permission to access it."}
                else:
                    return {"error": f"Spotify API error: {str(e)}"}
            except Exception as e:
                return {"error": f"Error processing playlist URL: {str(e)}"}
                
        else: 
            # Handle album
            try:
                if "album/" in playlist_url:
                    item_id = playlist_url.split("album/")[-1].split("?")[0].split("/")[0]
                else:
                    return {"error": "Invalid album URL format"}
                
                app_logger.info("processing_album_id", item_id=item_id)
                
                album_info = sp.album(item_id) # Network call
                item_name = album_info.get("name", "Unknown Album")
                
                app_logger.info("found_album_name", name=item_name)
                
                album_tracks = album_info.get("tracks", {}).get("items", [])[:50]
                tracks = [{"track": track} for track in album_tracks]
                
            except spotipy.exceptions.SpotifyException as e:
                app_logger.error("spotify_api_exception_album", item_id=item_id, error=str(e), status_code=e.http_status, exc_info=True)
                if e.http_status == 404:
                    return {"error": "Album not found. Please check if the album exists."}
                elif e.http_status == 403:
                    return {"error": "Access denied. You may not have permission to access this album."}
                else:
                    return {"error": f"Spotify API error: {str(e)}"}
            except Exception as e:
                app_logger.error("processing_album_url_failed", item_id=item_id, error=str(e), exc_info=True)
                return {"error": f"Error processing album URL: {str(e)}"}
            
        app_logger.info("item_type_processed", item_type='playlist' if is_playlist else 'album', item_name=item_name)
        
        if not tracks:
            app_logger.warning("no_tracks_found", item_name=item_name, item_type='playlist' if is_playlist else 'album')
            return {"error": f"No tracks found in the {'playlist' if is_playlist else 'album'}. The {'playlist' if is_playlist else 'album'} may be empty."}
        
        # Extract all artist IDs and info from tracks
        artists = []
        artist_ids = []
        track_names = []
        
        for item in tracks:
            track = item.get("track")
            if track and track.get("name"):
                track_names.append(track.get("name"))
                
            if track and track.get("artists"):
                for artist in track.get("artists"):
                    if artist.get("id"):
                        artists.append(artist.get("id"))
                        artist_ids.append(artist.get("id"))
        
        if not artists:
            app_logger.warning("no_artists_found_in_tracks", item_name=item_name)
            return {"error": "No artists found in tracks. Unable to analyze genres."}
            
        app_logger.info("artists_found_for_genre_analysis", unique_artist_count=len(set(artists)), track_count=len(tracks))
        
        # Get genres from artists with enhanced error handling
        genres = []
        unique_artist_ids = list(set(artists))[:50]  # Limit to 50 artists max for API calls
        
        # Process artists in batches (Spotify API allows up to 50 per request)
        for i in range(0, len(unique_artist_ids), 50):
            batch = unique_artist_ids[i:min(i+50, len(unique_artist_ids))]
            
            try:
                artist_info_batch = sp.artists(batch) # Network call
                if artist_info_batch and 'artists' in artist_info_batch:
                    for artist_data in artist_info_batch['artists']:
                        if artist_data:  # Check if artist data is not None
                            artist_genres = artist_data.get('genres', [])
                            genres.extend(artist_genres)
                            if artist_genres:
                                app_logger.debug("artist_genres_fetched", artist_name=artist_data.get('name', 'Unknown'), genres=artist_genres[:3])
            except spotipy.exceptions.SpotifyException as e:
                app_logger.warning("fetch_artist_info_batch_failed_spotify_exception", batch_num=(i//50 + 1), error=str(e), exc_info=True)
                continue
            except Exception as e:
                app_logger.warning("fetch_artist_info_batch_failed_unexpected", batch_num=(i//50 + 1), error=str(e), exc_info=True)
                continue
        
        app_logger.info("total_genres_collected", count=len(genres))
        if genres:
            genre_counts = Counter(genres)
            app_logger.debug("top_genres_collected", top_genres=dict(genre_counts.most_common(5)))
        
        # Create genre analysis
        genre_analysis = GenreAnalysis.from_genre_list(genres) # Local computation
        
        # Create playlist data
        playlist_data = PlaylistData(
            item_name=item_name,
            track_names=track_names[:10],  # Limit to first 10 track names
            genre_analysis=genre_analysis,
            spotify_url=playlist_url,
            found_genres=bool(genres),
            artist_ids=list(set(artist_ids))  # Store unique artist IDs
        )
        
        return playlist_data
        
    except spotipy.exceptions.SpotifyException as e:
        app_logger.error("extract_playlist_data_spotify_exception", url=playlist_url, error=str(e), status_code=e.http_status, exc_info=True)
        if e.http_status == 429:
            return {"error": "Rate limit exceeded. Please try again in a few minutes."}
        elif e.http_status == 401: # This might indicate token expiry if not using auto-refresh via auth_manager
            return {"error": "Authentication error. Please check your Spotify API credentials or try re-authenticating."}
        elif e.http_status == 403:
            return {"error": "Access forbidden. You may not have permission to access this content."}
        elif e.http_status == 404:
            return {"error": "Content not found. Please check if the URL is correct and the content exists."}
        else:
            return {"error": f"Spotify API error ({e.http_status}): {str(e)}"}
    except Exception as e:
        app_logger.error("extract_playlist_data_unexpected_error", url=playlist_url, error=str(e), exc_info=True)
        return {"error": f"An unexpected error occurred while processing your request: {str(e)}"}

def validate_spotify_url(url):
    """Validate if a URL is a valid Spotify playlist or album URL"""
    if not url:
        return False, "URL is empty"
    
    # Check if it's a Spotify URL
    if "open.spotify.com" not in url:
        return False, "Not a Spotify URL"
    
    # Check if it's a playlist or album
    if "playlist/" not in url and "album/" not in url:
        return False, "URL must be a Spotify playlist or album"
    
    # Try to extract ID
    try:
        if "playlist/" in url:
            playlist_id = url.split("playlist/")[-1].split("?")[0].split("/")[0]
            if len(playlist_id) != 22:  # Spotify playlist IDs are typically 22 characters
                return False, "Invalid playlist ID format"
        elif "album/" in url:
            album_id = url.split("album/")[-1].split("?")[0].split("/")[0]
            if len(album_id) != 22:  # Spotify album IDs are typically 22 characters
                return False, "Invalid album ID format"
    except Exception:
        return False, "Unable to parse Spotify ID from URL"
    
    return True, "Valid Spotify URL"

@monitor_api_calls("spotify_playlist_track_count")
@retry_with_exponential_backoff()
def get_playlist_tracks_count(playlist_url):
    """Get the number of tracks in a playlist (for validation)"""
    global sp
    
    if not sp:
        if not initialize_spotify(): # initialize_spotify is decorated
            app_logger.warning("spotify_client_not_initialized_for_track_count")
            return 0
    
    try:
        if "playlist/" in playlist_url:
            playlist_id = playlist_url.split("playlist/")[-1].split("?")[0].split("/")[0]
            playlist_info = sp.playlist(playlist_id, fields="tracks.total") # Network call
            return playlist_info.get("tracks", {}).get("total", 0)
        elif "album/" in playlist_url:
            album_id = playlist_url.split("album/")[-1].split("?")[0].split("/")[0]
            album_info = sp.album(album_id, market="US") # Network call
            return len(album_info.get("tracks", {}).get("items", []))
    except Exception as e:
        app_logger.error("get_playlist_tracks_count_failed", url=playlist_url, error=str(e), exc_info=True)
        return 0
    
    return 0 # Should not be reached if logic is correct

@monitor_api_calls("spotify_search")
@retry_with_exponential_backoff()
def search_spotify_content(query, content_type="playlist", limit=10):
    """Search for Spotify content (for potential future features)"""
    global sp
    
    if not sp:
        if not initialize_spotify(): # initialize_spotify is decorated
            app_logger.warning("spotify_client_not_initialized_for_search")
            return []
    
    try:
        results = sp.search(q=query, type=content_type, limit=limit, market="US") # Network call
        
        if content_type == "playlist":
            items = results.get("playlists", {}).get("items", [])
            return [{
                "name": item.get("name"),
                "id": item.get("id"),
                "url": item.get("external_urls", {}).get("spotify"),
                "description": item.get("description"),
                "tracks_total": item.get("tracks", {}).get("total", 0),
                "owner": item.get("owner", {}).get("display_name")
            } for item in items]
        elif content_type == "album":
            items = results.get("albums", {}).get("items", [])
            return [{
                "name": item.get("name"),
                "id": item.get("id"),
                "url": item.get("external_urls", {}).get("spotify"),
                "artist": ", ".join([artist.get("name") for artist in item.get("artists", [])]),
                "release_date": item.get("release_date"),
                "tracks_total": item.get("total_tracks", 0)
            } for item in items]
    except Exception as e:
        app_logger.error("search_spotify_content_failed", query=query, content_type=content_type, error=str(e), exc_info=True)
        return []
    
    # This line was outside the try block, seems like a typo.
    # return [] # If try block completes without returning, it implies empty results for other types.

# Helper function for debugging
def debug_spotify_connection():
    """Debug Spotify connection and credentials"""
    print("🔍 Debugging Spotify connection...")
    print(f"  - CLIENT_ID set: {'Yes' if SPOTIFY_CLIENT_ID else 'No'}")
    print(f"  - CLIENT_SECRET set: {'Yes' if SPOTIFY_CLIENT_SECRET else 'No'}")
    print(f"  - REDIRECT_URI: {SPOTIFY_REDIRECT_URI}")
    
    if sp:
        try:
            # Test basic search
            results = sp.search(q="test", type="track", limit=1)
            print("  - Basic search: ✓ Working")
            
            # Test current user (if OAuth)
            try:
                user = sp.current_user()
                print(f"  - Current user: {user.get('id', 'Unknown')} ✓")
            except:
                print("  - Current user: Not available (Client Credentials mode)")
                
        except Exception as e:
            print(f"  - Connection test failed: {e}")
    else:
        print("  - Spotify client: Not initialized")

if __name__ == "__main__":
    # Test the Spotify client
    print("Testing Spotify client...")
    debug_spotify_connection()
    
    if initialize_spotify():
        print("✓ Spotify client initialized successfully")
        
        # Test with a sample playlist
        test_url = "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M"
        print(f"\nTesting with playlist: {test_url}")
        
        is_valid, message = validate_spotify_url(test_url)
        print(f"URL validation: {message}")
        
        if is_valid:
            track_count = get_playlist_tracks_count(test_url)
            print(f"Track count: {track_count}")
            
            # Test extraction (uncomment to test)
            # result = extract_playlist_data(test_url)
            # print(f"Extraction result: {type(result)}")
    else:
        print(" Failed to initialize Spotify client")