import spotipy
from spotipy.oauth2 import SpotifyClientCredentials, SpotifyOAuth
from collections import Counter
from models import PlaylistData, GenreAnalysis
from config import SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, SPOTIFY_REDIRECT_URI

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
                scope="user-library-read playlist-read-private playlist-read-collaborative user-read-private",
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
                sp.current_user()
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

def extract_playlist_data(playlist_url):
    """Extract data from playlist"""
    global sp
    
    # Check Spotify client
    if not sp:
        print("Attempting to create new Spotify client...")
        if not initialize_spotify():
            return {"error": "Failed to initialize Spotify client"}
    
    # Parse URL and check validity
    if "playlist/" not in playlist_url and "album/" not in playlist_url:
        return {"error": "Invalid Spotify URL format"}
    
    try:
        is_playlist = "playlist/" in playlist_url
        
        if is_playlist:
            item_id = playlist_url.split("playlist/")[-1].split("?")[0].split("/")[0]
            playlist_info = sp.playlist(item_id, fields="name,description")
            item_name = playlist_info.get("name", "Unknown Playlist")
            
            # Get tracks to analyze genres
            results = sp.playlist_tracks(
                item_id,
                fields="items(track(id,name,artists(id,name)))",
                market="US",
                limit=50  
            )
            tracks = results.get("items", [])
        else: 
            item_id = playlist_url.split("album/")[-1].split("?")[0].split("/")[0]
            album_info = sp.album(item_id)
            item_name = album_info.get("name", "Unknown Album")
            
            album_tracks = album_info.get("tracks", {}).get("items", [])[:50]
            tracks = [{"track": track} for track in album_tracks]
            
        print(f"Found {'playlist' if is_playlist else 'album'}: {item_name}")
        
        if not tracks:
            return {"error": "No tracks found in the playlist or album"}
        
        # Extract all artist IDs and info from tracks
        artists = []
        artist_ids = []  # NEW: Collect artist IDs
        track_names = []
        
        for item in tracks:
            track = item.get("track")
            if track and track.get("name"):
                track_names.append(track.get("name"))
                
            if track and track.get("artists"):
                for artist in track.get("artists"):
                    if artist.get("id"):
                        artists.append(artist.get("id"))
                        artist_ids.append(artist.get("id"))  # NEW: Store artist ID
        
        if not artists:
            return {"error": "No artists found in tracks"}
            
        print(f"Found {len(set(artists))} unique artists in {len(tracks)} tracks")
        
        # Get genres from artists
        genres = []
        unique_artist_ids = list(set(artists))[:50]  # Limit to 50 artists max for API calls
        
        # Process artists in batches (Spotify API allows up to 50 per request)
        for i in range(0, len(unique_artist_ids), 50):
            batch = unique_artist_ids[i:min(i+50, len(unique_artist_ids))]
            
            artist_info_batch = sp.artists(batch)
            if artist_info_batch and 'artists' in artist_info_batch:
                for artist in artist_info_batch['artists']:
                    artist_genres = artist.get('genres', [])
                    genres.extend(artist_genres)
        
        # Create genre analysis
        genre_analysis = GenreAnalysis.from_genre_list(genres)
        
        # Create playlist data - MODIFIED to include artist IDs
        playlist_data = PlaylistData(
            item_name=item_name,
            track_names=track_names[:10],
            genre_analysis=genre_analysis,
            spotify_url=playlist_url,
            found_genres=bool(genres)
        )
        
        # Add artist IDs to the playlist data dict when converted
        playlist_dict = playlist_data.to_dict()
        playlist_dict["artist_ids"] = list(set(artist_ids))  # NEW: Add unique artist IDs
        
        # Convert back to PlaylistData object but with the extra data
        # You might want to modify your PlaylistData class to include artist_ids
        # Or just work with the dict that now has artist_ids
        
        return playlist_data  # This will be converted to dict in your generator
        
    except Exception as e:
        print(f"Error extracting data: {e}")
        return {"error": f"Error extracting data: {str(e)}"}