# Fixed spotify_client.py - Comprehensive Spotify API integration

import sys
import os
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials, SpotifyOAuth
from collections import Counter

# Ensure the project's own directory is prioritized for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# Import models with comprehensive fallback
try:
    from models import PlaylistData, GenreAnalysis
    MODELS_AVAILABLE = True
except ImportError:
    print("⚠️ Models not available, creating fallback classes")
    MODELS_AVAILABLE = False
    
    class GenreAnalysis:
        def __init__(self, top_genres=None, all_genres=None, mood="balanced"):
            self.top_genres = top_genres or []
            self.all_genres = all_genres or []
            self.mood = mood
            
        @classmethod
        def from_genre_list(cls, genres):
            if not genres:
                return cls()
            
            genre_counter = Counter(genres)
            top_genres = [genre for genre, _ in genre_counter.most_common(10)]
            
            return cls(
                top_genres=top_genres,
                all_genres=genres,
                mood="balanced"
            )
            
        def get_style_elements(self):
            return []
    
    class PlaylistData:
        def __init__(self, item_name="", track_names=None, genre_analysis=None, 
                    spotify_url="", found_genres=False, artist_ids=None):
            self.item_name = item_name
            self.track_names = track_names or []
            self.genre_analysis = genre_analysis or GenreAnalysis()
            self.spotify_url = spotify_url
            self.found_genres = found_genres
            self.artist_ids = artist_ids or []
            
        def to_dict(self):
            return {
                "item_name": self.item_name,
                "track_names": self.track_names,
                "genres": self.genre_analysis.top_genres,
                "all_genres": self.genre_analysis.all_genres,
                "mood_descriptor": self.genre_analysis.mood,
                "spotify_url": self.spotify_url,
                "found_genres": self.found_genres,
                "style_elements": self.genre_analysis.get_style_elements(),
                "artist_ids": self.artist_ids
            }

# Import config with fallback
try:
    from config import SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, SPOTIFY_REDIRECT_URI
    CONFIG_AVAILABLE = True
except ImportError:
    print("⚠️ Config not available, using environment variables")
    CONFIG_AVAILABLE = False
    SPOTIFY_CLIENT_ID = os.environ.get('SPOTIFY_CLIENT_ID')
    SPOTIFY_CLIENT_SECRET = os.environ.get('SPOTIFY_CLIENT_SECRET')
    SPOTIFY_REDIRECT_URI = os.environ.get('SPOTIFY_REDIRECT_URI', 'http://localhost:5000/spotify-callback')

# Monitoring imports with fallback
try:
    from monitoring_system import monitor_api_calls
    from fault_handling import fault_tolerant_api_call
    MONITORING_AVAILABLE = True
except ImportError:
    MONITORING_AVAILABLE = False
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
    """Initialize Spotify API client with comprehensive error handling"""
    global sp
    
    print("🎵 Initializing Spotify client...")
    
    try:
        if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
            print("❌ Missing Spotify API credentials")
            print("Please set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET in your environment variables")
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
                print(f"✅ Spotify OAuth connection successful for user: {user_info.get('id', 'unknown')}")
            else:
                test_result = sp.search(q='test', limit=1)
                print("✅ Spotify API connection successful")
            return True
            
        except spotipy.exceptions.SpotifyException as e:
            print(f"❌ Spotify API authentication failed: {e}")
            if not use_oauth and "Invalid client" not in str(e):
                print("🔄 Trying OAuth authentication as fallback...")
                return initialize_spotify(use_oauth=True)
            return False
            
    except Exception as e:
        print(f"❌ Spotify API initialization failed: {e}")
        return False

@monitor_api_calls("spotify")
@fault_tolerant_api_call("spotify")
def extract_playlist_data(playlist_url):
    """Extract data from playlist with comprehensive error handling"""
    global sp
    
    print(f"🎵 Processing Spotify URL: {playlist_url}")
    
    # Initialize client if needed
    if not sp:
        print("🔄 Spotify client not initialized, attempting to initialize...")
        if not initialize_spotify():
            return {"error": "Failed to initialize Spotify client. Please check your API credentials and try again."}
    
    # Validate URL format
    if not playlist_url or not isinstance(playlist_url, str):
        return {"error": "Invalid URL provided"}
    
    if "open.spotify.com" not in playlist_url:
        return {"error": "Please provide a valid Spotify URL (open.spotify.com)"}
    
    if "playlist/" not in playlist_url and "album/" not in playlist_url:
        return {"error": "URL must be a Spotify playlist or album URL"}
    
    try:
        is_playlist = "playlist/" in playlist_url
        
        if is_playlist:
            # Extract playlist ID
            try:
                if "playlist/" in playlist_url:
                    item_id = playlist_url.split("playlist/")[-1].split("?")[0].split("/")[0]
                    if len(item_id) < 20:  # Spotify IDs are typically 22 characters
                        return {"error": "Invalid playlist ID format"}
                else:
                    return {"error": "Invalid playlist URL format"}
                
                print(f"🎵 Processing playlist ID: {item_id}")
                
                # Get playlist info
                playlist_info = sp.playlist(item_id, fields="name,description,owner,public")
                item_name = playlist_info.get("name", "Unknown Playlist")
                
                # Check if playlist is accessible
                if not playlist_info.get("public", True) and not playlist_info.get("collaborative", False):
                    return {"error": "This playlist is private. Please make it public or use a different playlist."}
                
                print(f"✅ Found playlist: {item_name}")
                
                # Get tracks
                results = sp.playlist_tracks(
                    item_id,
                    fields="items(track(id,name,artists(id,name)))",
                    market="US",
                    limit=50
                )
                tracks = results.get("items", [])
                
                # Get additional tracks if playlist is large
                while results.get('next') and len(tracks) < 100:
                    results = sp.next(results)
                    tracks.extend(results.get("items", []))
                
            except spotipy.exceptions.SpotifyException as e:
                if e.http_status == 404:
                    return {"error": "Playlist not found. Please check if the playlist exists and is public."}
                elif e.http_status == 403:
                    return {"error": "Access denied. The playlist may be private or you may not have permission to access it."}
                elif e.http_status == 400:
                    return {"error": "Invalid playlist URL. Please check the URL format."}
                else:
                    return {"error": f"Spotify API error: {str(e)}"}
            except Exception as e:
                return {"error": f"Error processing playlist URL: {str(e)}"}
                
        else: 
            # Handle album
            try:
                if "album/" in playlist_url:
                    item_id = playlist_url.split("album/")[-1].split("?")[0].split("/")[0]
                    if len(item_id) < 20:
                        return {"error": "Invalid album ID format"}
                else:
                    return {"error": "Invalid album URL format"}
                
                print(f"💿 Processing album ID: {item_id}")
                
                album_info = sp.album(item_id)
                item_name = album_info.get("name", "Unknown Album")
                
                print(f"✅ Found album: {item_name}")
                
                album_tracks = album_info.get("tracks", {}).get("items", [])[:50]
                tracks = [{"track": track} for track in album_tracks]
                
            except spotipy.exceptions.SpotifyException as e:
                if e.http_status == 404:
                    return {"error": "Album not found. Please check if the album exists."}
                elif e.http_status == 403:
                    return {"error": "Access denied. You may not have permission to access this album."}
                elif e.http_status == 400:
                    return {"error": "Invalid album URL. Please check the URL format."}
                else:
                    return {"error": f"Spotify API error: {str(e)}"}
            except Exception as e:
                return {"error": f"Error processing album URL: {str(e)}"}
        
        if not tracks:
            return {"error": f"No tracks found in the {'playlist' if is_playlist else 'album'}. It may be empty or inaccessible."}
        
        print(f"📊 Found {len(tracks)} tracks")
        
        # Extract artist information
        artists = []
        artist_ids = []
        track_names = []
        
        for item in tracks:
            track = item.get("track")
            if not track:
                continue
                
            track_name = track.get("name")
            if track_name:
                track_names.append(track_name)
                
            track_artists = track.get("artists", [])
            for artist in track_artists:
                artist_id = artist.get("id")
                if artist_id:
                    artists.append(artist_id)
                    artist_ids.append(artist_id)
        
        if not artists:
            return {"error": "No artists found in tracks. Unable to analyze genres."}
            
        print(f"🎤 Found {len(set(artists))} unique artists in {len(tracks)} tracks")
        
        # Get genres from artists
        genres = []
        unique_artist_ids = list(set(artists))[:50]  # Limit to avoid API quota issues
        
        # Process artists in batches
        batch_size = 50
        for i in range(0, len(unique_artist_ids), batch_size):
            batch = unique_artist_ids[i:i+batch_size]
            
            try:
                artist_info_batch = sp.artists(batch)
                if artist_info_batch and 'artists' in artist_info_batch:
                    for artist in artist_info_batch['artists']:
                        if artist:
                            artist_genres = artist.get('genres', [])
                            genres.extend(artist_genres)
                            if artist_genres:
                                print(f"  🎭 {artist.get('name', 'Unknown')}: {', '.join(artist_genres[:3])}")
            except spotipy.exceptions.SpotifyException as e:
                print(f"⚠️ Error getting artist info for batch {i//batch_size + 1}: {e}")
                continue
            except Exception as e:
                print(f"⚠️ Unexpected error processing artist batch: {e}")
                continue
        
        print(f"🎯 Total genres collected: {len(genres)}")
        
        if genres:
            genre_counts = Counter(genres)
            print(f"📈 Top genres: {dict(genre_counts.most_common(5))}")
        else:
            print("⚠️ No genres found, using fallback analysis")
        
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
        
        print(f"✅ Successfully processed {item_name}")
        return playlist_data
        
    except spotipy.exceptions.SpotifyException as e:
        print(f"❌ Spotify API error: {e}")
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
        print(f"❌ Unexpected error extracting data: {e}")
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
            if len(playlist_id) < 20:  # Spotify playlist IDs are typically 22 characters
                return False, "Invalid playlist ID format"
        elif "album/" in url:
            album_id = url.split("album/")[-1].split("?")[0].split("/")[0]
            if len(album_id) < 20:  # Spotify album IDs are typically 22 characters
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
            print("  - Basic search: ✅ Working")
            
            # Test current user (if OAuth)
            try:
                user = sp.current_user()
                print(f"  - Current user: {user.get('id', 'Unknown')} ✅")
            except:
                print("  - Current user: Not available (Client Credentials mode)")
                
        except Exception as e:
            print(f"  - Connection test failed: {e}")
    else:
        print("  - Spotify client: Not initialized")

def test_spotify_functionality():
    """Test basic Spotify functionality"""
    print("🧪 Testing Spotify functionality...")
    
    if not initialize_spotify():
        print("❌ Failed to initialize Spotify client")
        return False
    
    # Test search
    try:
        results = sp.search(q="The Beatles", type="artist", limit=1)
        if results.get("artists", {}).get("items"):
            print("✅ Artist search working")
        else:
            print("⚠️ Artist search returned no results")
    except Exception as e:
        print(f"❌ Artist search failed: {e}")
        return False
    
    # Test with a known public playlist
    test_url = "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M"  # Today's Top Hits
    print(f"🧪 Testing with playlist: {test_url}")
    
    is_valid, message = validate_spotify_url(test_url)
    print(f"URL validation: {message}")
    
    if is_valid:
        track_count = get_playlist_tracks_count(test_url)
        print(f"Track count: {track_count}")
        
        if track_count > 0:
            print("✅ Spotify functionality test passed")
            return True
        else:
            print("⚠️ Could not get track count")
            return False
    else:
        print("❌ URL validation failed")
        return False

# Auto-initialize on import
if __name__ == "__main__":
    print("🚀 Testing Spotify client standalone...")
    debug_spotify_connection()
    
    if test_spotify_functionality():
        print("✅ All Spotify tests passed")
    else:
        print("❌ Some Spotify tests failed")
else:
    # Auto-initialize when imported
    try:
        if SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET:
            if initialize_spotify():
                print("✅ Spotify client auto-initialized successfully")
            else:
                print("⚠️ Spotify client auto-initialization failed")
        else:
            print("⚠️ Spotify credentials not configured")
    except Exception as e:
        print(f"⚠️ Error during Spotify auto-initialization: {e}")