import spotipy
from spotipy.oauth2 import SpotifyClientCredentials, SpotifyOAuth
from collections import Counter

# Fix import path for models
try:
    from .models import PlaylistData, GenreAnalysis
except ImportError:
    from models import PlaylistData, GenreAnalysis

from config import SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, SPOTIFY_REDIRECT_URI

# Monitoring imports with fallback
try:
    from monitoring_system import monitor_api_calls
    from fault_handling import fault_tolerant_api_call
except ImportError:
    def monitor_api_calls(service_name):
        def decorator(func):
            return func
        return decorator
    def fault_tolerant_api_call(service_name, fallback_func=None):
        def decorator(func):
            return func
        return decorator

# Global Spotify client
sp = None

def initialize_spotify(use_oauth=False):
    """Initialize Spotify API client"""
    global sp
    try:
        if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
            print("ERROR: Missing Spotify API credentials. Please set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET in your .env file.")
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
                user_info = sp.current_user()
                print(f"✓ Spotify OAuth connection successful for user: {user_info.get('id', 'unknown')}")
                # Debug premium status detection
                print(f"🔍 User email: {user_info.get('email')}")
                print(f"🔍 User ID: {user_info.get('id')}")
                print(f"🔍 User product: {user_info.get('product')}")
            else:
                sp.search(q='test', limit=1)
                print("✓ Spotify API connection successful")
            return True
        except spotipy.exceptions.SpotifyException as e:
            print(f"✗ Spotify API authentication failed: {e}")
            # If client credentials failed, try OAuth as fallback
            if not use_oauth:
                print("Trying OAuth authentication instead...")
                return initialize_spotify(use_oauth=True)
            return False
    except Exception as e:
        print(f"✗ Spotify API initialization failed: {e}")
        return False

def get_user_premium_status(access_token):
    """Get user's premium status from Spotify API"""
    try:
        import requests
        headers = {'Authorization': f'Bearer {access_token}'}
        response = requests.get('https://api.spotify.com/v1/me', headers=headers)
        
        if response.status_code == 200:
            user_data = response.json()
            print(f"🔍 Spotify user data for premium check:")
            print(f"  - ID: {user_data.get('id')}")
            print(f"  - Email: {user_data.get('email')}")
            print(f"  - Product: {user_data.get('product')}")
            print(f"  - Display Name: {user_data.get('display_name')}")
            
            # Check our premium criteria
            email = user_data.get('email', '').lower()
            spotify_id = user_data.get('id', '').lower()
            
            is_premium_email = email == 'bentakaki7@gmail.com'
            is_premium_spotify = spotify_id == 'benthegamer'
            
            print(f"🔍 Premium check results:")
            print(f"  - Email match: {is_premium_email} (checking: {email})")
            print(f"  - Spotify ID match: {is_premium_spotify} (checking: {spotify_id})")
            
            return {
                'user_data': user_data,
                'is_premium_by_email': is_premium_email,
                'is_premium_by_spotify_id': is_premium_spotify,
                'is_premium': is_premium_email or is_premium_spotify
            }
        else:
            print(f"❌ Failed to get user data: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"❌ Error getting user premium status: {e}")
    return None

@monitor_api_calls("spotify")
@fault_tolerant_api_call("spotify")
def extract_playlist_data(playlist_url):
    """Extract data from playlist with enhanced error handling"""
    global sp
    
    # Check Spotify client
    if not sp:
        print("Attempting to create new Spotify client...")
        if not initialize_spotify():
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
                    return {"error": "Invalid playlist URL format"}
                
                print(f"🎵 Processing playlist ID: {item_id}")
                
                # Get playlist info
                playlist_info = sp.playlist(item_id, fields="name,description,owner")
                item_name = playlist_info.get("name", "Unknown Playlist")
                
                print(f"✓ Found playlist: {item_name}")
                
                # Get tracks to analyze genres
                results = sp.playlist_tracks(
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
                
                print(f"💿 Processing album ID: {item_id}")
                
                album_info = sp.album(item_id)
                item_name = album_info.get("name", "Unknown Album")
                
                print(f"✓ Found album: {item_name}")
                
                album_tracks = album_info.get("tracks", {}).get("items", [])[:50]
                tracks = [{"track": track} for track in album_tracks]
                
            except spotipy.exceptions.SpotifyException as e:
                if e.http_status == 404:
                    return {"error": "Album not found. Please check if the album exists."}
                elif e.http_status == 403:
                    return {"error": "Access denied. You may not have permission to access this album."}
                else:
                    return {"error": f"Spotify API error: {str(e)}"}
            except Exception as e:
                return {"error": f"Error processing album URL: {str(e)}"}
            
        print(f"Found {'playlist' if is_playlist else 'album'}: {item_name}")
        
        if not tracks:
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
            return {"error": "No artists found in tracks. Unable to analyze genres."}
            
        print(f"Found {len(set(artists))} unique artists in {len(tracks)} tracks")
        
        # Get genres from artists with enhanced error handling
        genres = []
        unique_artist_ids = list(set(artists))[:50]  # Limit to 50 artists max for API calls
        
        # Process artists in batches (Spotify API allows up to 50 per request)
        for i in range(0, len(unique_artist_ids), 50):
            batch = unique_artist_ids[i:min(i+50, len(unique_artist_ids))]
            
            try:
                artist_info_batch = sp.artists(batch)
                if artist_info_batch and 'artists' in artist_info_batch:
                    for artist in artist_info_batch['artists']:
                        if artist:  # Check if artist data is not None
                            artist_genres = artist.get('genres', [])
                            genres.extend(artist_genres)
                            if artist_genres:
                                print(f"  - {artist.get('name', 'Unknown')}: {', '.join(artist_genres[:3])}")
            except spotipy.exceptions.SpotifyException as e:
                print(f"⚠️ Error getting artist info for batch {i//50 + 1}: {e}")
                continue
            except Exception as e:
                print(f"⚠️ Unexpected error processing artist batch: {e}")
                continue
        
        print(f"Total genres collected: {len(genres)}")
        if genres:
            genre_counts = Counter(genres)
            print(f"Top genres: {dict(genre_counts.most_common(5))}")
        
        # Create genre analysis
        genre_analysis = GenreAnalysis.from_genre_list(genres)
        
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
        print(f"Spotify API error: {e}")
        if e.http_status == 429:
            return {"error": "Rate limit exceeded. Please try again in a few minutes."}
        elif e.http_status == 401:
            return {"error": "Authentication error. Please check your Spotify API credentials."}
        elif e.http_status == 403:
            return {"error": "Access forbidden. You may not have permission to access this content."}
        elif e.http_status == 404:
            return {"error": "Content not found. Please check if the URL is correct and the content exists."}
        else:
            return {"error": f"Spotify API error ({e.http_status}): {str(e)}"}
    except Exception as e:
        print(f"Unexpected error extracting data: {e}")
        import traceback
        traceback.print_exc()
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

def get_playlist_tracks_count(playlist_url):
    """Get the number of tracks in a playlist (for validation)"""
    global sp
    
    if not sp:
        if not initialize_spotify():
            return 0
    
    try:
        if "playlist/" in playlist_url:
            playlist_id = playlist_url.split("playlist/")[-1].split("?")[0].split("/")[0]
            playlist_info = sp.playlist(playlist_id, fields="tracks.total")
            return playlist_info.get("tracks", {}).get("total", 0)
        elif "album/" in playlist_url:
            album_id = playlist_url.split("album/")[-1].split("?")[0].split("/")[0]
            album_info = sp.album(album_id, market="US")
            return len(album_info.get("tracks", {}).get("items", []))
    except Exception as e:
        print(f"Error getting track count: {e}")
        return 0
    
    return 0

def search_spotify_content(query, content_type="playlist", limit=10):
    """Search for Spotify content (for potential future features)"""
    global sp
    
    if not sp:
        if not initialize_spotify():
            return []
    
    try:
        results = sp.search(q=query, type=content_type, limit=limit, market="US")
        
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
        print(f"Error searching Spotify content: {e}")
        return []
    
    return []

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