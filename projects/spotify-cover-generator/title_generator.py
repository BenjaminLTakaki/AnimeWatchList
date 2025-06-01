import requests
import json
import random
import re
from collections import Counter
from typing import List, Dict, Tuple, Optional
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

from config import GEMINI_API_KEY, GEMINI_API_URL, SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET

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

class LiveSpotifyTitleGenerator:
    def __init__(self):
        """Initialize with Spotify client and caching"""
        self.sp = None
        self.album_cache = {}
        self.artist_cache = {}
        self._initialize_spotify()
        
    def _initialize_spotify(self):
        """Initialize Spotify client"""
        try:
            if SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET:
                auth_manager = SpotifyClientCredentials(
                    client_id=SPOTIFY_CLIENT_ID,
                    client_secret=SPOTIFY_CLIENT_SECRET
                )
                self.sp = spotipy.Spotify(auth_manager=auth_manager)
                print("✓ Spotify client initialized for live album titles")
            else:
                print("⚠️ Spotify credentials missing - AI generation only")
        except Exception as e:
            print(f"⚠️ Spotify initialization failed: {e}")

    def extract_artist_ids_from_playlist_data(self, playlist_data: Dict) -> List[str]:
        """Extract artist IDs from playlist data"""
        artist_ids = []
        
        # Check if artist IDs are directly available (from updated PlaylistData)
        if 'artist_ids' in playlist_data:
            return playlist_data['artist_ids']
            
        # Handle case where playlist_data is a PlaylistData object
        if hasattr(playlist_data, 'artist_ids'):
            return playlist_data.artist_ids
            
        # Convert PlaylistData object to dict if needed
        if hasattr(playlist_data, 'to_dict'):
            data_dict = playlist_data.to_dict()
            if 'artist_ids' in data_dict:
                return data_dict['artist_ids']
        
        return artist_ids

    def fetch_albums_for_artists(self, artist_ids: List[str], limit_per_artist: int = 15) -> List[str]:
        """Fetch real album titles from Spotify for given artists"""
        if not self.sp or not artist_ids:
            return []
        
        album_titles = []
        
        for artist_id in artist_ids[:10]:  # Limit to avoid too many API calls
            cache_key = f"artist_{artist_id}_{limit_per_artist}"
            if cache_key in self.album_cache:
                album_titles.extend(self.album_cache[cache_key])
                continue
                
            try:
                # Fetch albums for this artist
                results = self.sp.artist_albums(
                    artist_id, 
                    album_type='album,single', 
                    limit=limit_per_artist,
                    market='US'
                )
                
                artist_albums = []
                for album in results.get('items', []):
                    name = album.get('name')
                    if name and self._is_good_title(name):
                        artist_albums.append(name)
                
                self.album_cache[cache_key] = artist_albums
                album_titles.extend(artist_albums)
                
            except Exception as e:
                print(f"Error fetching albums for artist {artist_id}: {e}")
                continue
        
        return list(set(album_titles))  # Remove duplicates

    def fetch_similar_artists_albums(self, artist_ids: List[str], limit: int = 50) -> List[str]:
        """Fetch albums from similar artists to expand the pool"""
        if not self.sp or not artist_ids:
            return []
            
        similar_albums = []
        
        for artist_id in artist_ids[:5]:  # Limit to avoid quota issues
            try:
                # Get related artists
                related = self.sp.artist_related_artists(artist_id)
                related_artist_ids = [artist['id'] for artist in related.get('artists', [])[:5]]
                
                # Fetch albums from related artists
                related_albums = self.fetch_albums_for_artists(related_artist_ids, limit_per_artist=8)
                similar_albums.extend(related_albums)
                
            except Exception as e:
                print(f"Error fetching related artists for {artist_id}: {e}")
                continue
                
        return list(set(similar_albums))

    def fetch_genre_albums(self, genres: List[str], limit: int = 30) -> List[str]:
        """Fetch albums by searching for genre-specific content"""
        if not self.sp or not genres:
            return []
            
        genre_albums = []
        
        for genre in genres[:3]:  # Limit genres to avoid too many calls
            cache_key = f"genre_{genre.lower()}_{limit}"
            if cache_key in self.album_cache:
                genre_albums.extend(self.album_cache[cache_key])
                continue
                
            try:
                # Search for albums in this genre
                search_terms = [
                    f'genre:"{genre}"',
                    f'tag:"{genre}"',
                    genre  # Simple genre search
                ]
                
                found_albums = []
                for search_term in search_terms:
                    try:
                        results = self.sp.search(
                            q=search_term, 
                            type='album', 
                            limit=10,
                            market='US'
                        )
                        
                        for album in results.get('albums', {}).get('items', []):
                            name = album.get('name')
                            if name and self._is_good_title(name):
                                found_albums.append(name)
                                
                    except Exception:
                        continue
                
                self.album_cache[cache_key] = list(set(found_albums))
                genre_albums.extend(found_albums)
                
            except Exception as e:
                print(f"Error searching albums for genre {genre}: {e}")
                continue
        
        return list(set(genre_albums))

    def _is_good_title(self, title: str) -> bool:
        """Filter out bad/unsuitable album titles"""
        if not title or len(title.strip()) == 0:
            return False
            
        # Clean the title first
        clean_title = re.sub(r'\([^)]*\)', '', title).strip()  # Remove (Deluxe Edition) etc.
        clean_title = re.sub(r'\[[^\]]*\]', '', clean_title).strip()  # Remove [Explicit] etc.
        
        if len(clean_title) < 2:
            return False
            
        # Filter criteria
        if len(clean_title) > 60:  # Too long
            return False
            
        if clean_title.isdigit():  # Just a number
            return False
            
        if re.match(r'^\d{4}$', clean_title):  # Just a year
            return False
            
        # Filter out generic/bad titles
        bad_titles = {
            'untitled', 'album', 'mixtape', 'ep', 'single', 'compilation',
            'greatest hits', 'best of', 'the collection', 'anthology'
        }
        if clean_title.lower() in bad_titles:
            return False
            
        # Filter out titles that are mostly special characters
        if len(re.sub(r'[^a-zA-Z0-9\s]', '', clean_title)) < len(clean_title) * 0.5:
            return False
            
        return True

    def score_title_relevance(self, title: str, genres: List[str], mood: str) -> float:
        """Score how relevant a title is to the given context"""
        score = 1.0  # Base score
        title_lower = title.lower()
        
        # Mood relevance
        if mood:
            mood_words = mood.lower().split()
            for word in mood_words:
                if word in title_lower:
                    score += 2.0
                elif any(word in t_word for t_word in title_lower.split()):
                    score += 1.0
        
        # Genre relevance (basic keyword matching)
        genre_keywords = {
            'rock': ['rock', 'stone', 'fire', 'electric', 'loud', 'rebel'],
            'electronic': ['digital', 'electric', 'future', 'space', 'neon', 'cyber'],
            'hip hop': ['street', 'city', 'real', 'truth', 'life', 'soul'],
            'pop': ['love', 'heart', 'dream', 'star', 'shine', 'perfect'],
            'jazz': ['blue', 'smooth', 'night', 'soul', 'cool', 'swing'],
            'indie': ['heart', 'home', 'wild', 'young', 'free', 'real'],
            'folk': ['home', 'road', 'heart', 'old', 'country', 'song']
        }
        
        for genre in genres:
            genre_lower = genre.lower()
            if genre_lower in genre_keywords:
                keywords = genre_keywords[genre_lower]
                for keyword in keywords:
                    if keyword in title_lower:
                        score += 1.5
        
        # Length preference (2-4 words is ideal)
        word_count = len(title.split())
        if 2 <= word_count <= 4:
            score += 1.0
        elif word_count == 1 or word_count == 5:
            score += 0.5
        else:
            score -= 0.5
            
        return score

    def select_best_titles(self, titles: List[str], genres: List[str], mood: str, 
                          count: int = 5) -> List[str]:
        """Select the best titles from the pool"""
        if not titles:
            return []
            
        # Score all titles
        scored_titles = []
        for title in titles:
            score = self.score_title_relevance(title, genres, mood)
            scored_titles.append((title, score))
        
        # Sort by score
        scored_titles.sort(key=lambda x: x[1], reverse=True)
        
        # Get top titles with some randomness
        top_count = min(count * 3, len(scored_titles))
        top_titles = scored_titles[:top_count]
        
        # Randomly select from top titles
        selected = random.choices(
            [t[0] for t in top_titles],
            weights=[t[1] for t in top_titles],
            k=min(count, len(top_titles))
        )
        
        return selected

    def generate_ai_title_with_context(self, genres: List[str], mood: str, 
                                     sample_titles: List[str]) -> str:
        """Generate AI title using real album titles as context"""
        if not GEMINI_API_KEY:
            return ""
            
        # Use sample titles as inspiration for the AI
        context_titles = sample_titles[:10] if sample_titles else []
        genres_str = ", ".join(genres) if genres else "various"
        
        prompt = f"""You are creating an album title inspired by these real album titles: {', '.join(context_titles)}

Create a unique album title (2-3 words) for {genres_str} music with mood: {mood}

Requirements:
- 2-3 words maximum  
- Original (not copying the examples exactly)
- Evocative and memorable
- Suitable for {genres_str} genre
- Captures the mood: {mood}

Respond with ONLY the title, no quotes or explanation:"""

        return self._call_gemini_api(prompt)

    def _call_gemini_api(self, prompt: str) -> str:
        """Call Gemini API for title generation"""
        try:
            headers = {"Content-Type": "application/json"}
            data = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.7,
                    "maxOutputTokens": 15,
                    "topP": 0.8
                }
            }
            
            url = f"{GEMINI_API_URL}?key={GEMINI_API_KEY}"
            response = requests.post(url, headers=headers, json=data, timeout=30)
            
            if response.status_code == 200:
                response_json = response.json()
                if 'candidates' in response_json and len(response_json['candidates']) > 0:
                    text = response_json['candidates'][0]['content']['parts'][0]['text']
                    return self._clean_title(text)
            
            return ""
        except Exception as e:
            print(f"Error calling Gemini API: {e}")
            return ""

    def _clean_title(self, raw_title: str) -> str:
        """Clean and validate title"""
        if not raw_title:
            return ""
        
        title = raw_title.strip().replace('"', '').replace("'", "")
        title = ' '.join(word.capitalize() for word in title.split())
          # Validate length and word count
        if len(title) > 50 or len(title) < 3:
            return ""
            
        word_count = len(title.split())
        if word_count > 4 or word_count < 1:
            return ""
        
        return title

    @monitor_api_calls("gemini")
    @fault_tolerant_api_call("gemini")
    def generate_title(self, playlist_data: Dict, mood: str = "") -> str:
        """Main title generation using live Spotify data"""
        try:
            print("🎵 Generating title using live Spotify data...")
            
            genres = playlist_data.get("genres", [])
            all_titles = []
            
            # Extract artist IDs from your playlist data structure
            artist_ids = self.extract_artist_ids_from_playlist_data(playlist_data)
            
            if not artist_ids:
                print("⚠️ No artist IDs found in playlist data")
                # Try to get them from track names or other data if needed
                # This depends on your playlist_data structure
            
            # Method 1: Get albums from the playlist's artists
            if artist_ids and self.sp:
                artist_albums = self.fetch_albums_for_artists(artist_ids)
                if artist_albums:
                    all_titles.extend(artist_albums)
                    print(f"✓ Found {len(artist_albums)} albums from playlist artists")
                
                # Method 2: Get albums from similar artists
                similar_albums = self.fetch_similar_artists_albums(artist_ids)
                if similar_albums:
                    all_titles.extend(similar_albums)
                    print(f"✓ Found {len(similar_albums)} albums from similar artists")
            
            # Method 3: Get albums by genre
            if genres and self.sp:
                genre_albums = self.fetch_genre_albums(genres)
                if genre_albums:
                    all_titles.extend(genre_albums)
                    print(f"✓ Found {len(genre_albums)} albums from genre search")
            
            # Remove duplicates
            all_titles = list(set(all_titles))
            
            if all_titles:
                print(f"🎵 Total pool: {len(all_titles)} unique album titles")
                
                # Select best candidates
                candidates = self.select_best_titles(all_titles, genres, mood, count=10)
                
                if candidates:
                    # Method A: Use a real title directly (70% chance)
                    if random.random() < 0.7:
                        chosen_title = random.choice(candidates[:5])  # Pick from top 5
                        print(f"✓ Selected real album title: '{chosen_title}'")
                        return chosen_title
                    
                    # Method B: Generate AI title inspired by real titles (30% chance)
                    else:
                        ai_title = self.generate_ai_title_with_context(genres, mood, candidates)
                        if ai_title and self._is_good_title(ai_title):
                            print(f"✓ Generated AI-inspired title: '{ai_title}'")
                            return ai_title
                        else:
                            # Fallback to real title
                            chosen_title = random.choice(candidates[:3])
                            print(f"✓ AI failed, using real title: '{chosen_title}'")
                            return chosen_title
            
            # Ultimate fallback: Generate with AI only
            print("⚠️ No Spotify titles found, using AI generation only")
            ai_title = self.generate_ai_title_with_context(genres, mood, [])
            if ai_title:
                return ai_title
            
            # Last resort
            return self._ultimate_fallback(genres, mood)
            
        except Exception as e:
            print(f"❌ Error in title generation: {e}")
            return self._ultimate_fallback(playlist_data.get("genres", []), mood)

    def _ultimate_fallback(self, genres: List[str], mood: str) -> str:
        """Final fallback when everything else fails"""
        if mood:
            words = mood.split()[:2]
            return ' '.join(word.capitalize() for word in words)
        elif genres:
            return f"New {genres[0].replace('_', ' ').title()}"
        else:
            return random.choice([
                "New Horizons", "Fresh Perspective", "Next Chapter", 
                "New Dawn", "Open Roads", "Clear Skies"
            ])

# Updated main function
@monitor_api_calls("gemini")
@fault_tolerant_api_call("gemini")
def generate_title(playlist_data, mood=""):
    """Generate title using live Spotify album data"""
    generator = LiveSpotifyTitleGenerator()
    return generator.generate_title(playlist_data, mood)