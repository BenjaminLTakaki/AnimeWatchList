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

# Monitoring and Fault Handling Imports
from .monitoring_system import app_logger, monitor_performance, monitor_api_calls
from .fault_handling import (
    fault_tolerant_api_call,
    GracefulDegradation,
    http_client,
    circuit_breakers, # Potentially for http_client if it uses them
    retry_with_exponential_backoff
)

app_logger.info("Successfully imported monitoring, fault_handling, and config modules in title_generator.")

class LiveSpotifyTitleGenerator:
    def __init__(self):
        """Initialize with Spotify client and caching"""
        self.sp = None
        self.album_cache = {}
        self.artist_cache = {}
        self._initialize_spotify()
        
    def _initialize_spotify(self):
        """Use the global Spotify client instead of creating a new one"""
        try:
            from spotify_client import sp # Assuming sp is the initialized spotipy client from spotify_client.py
            if sp:
                self.sp = sp
                app_logger.info("title_generator_using_global_spotify_client")
            else:
                app_logger.warning("title_generator_global_spotify_client_not_available")
                self.sp = None
        except Exception as e:
            app_logger.error("title_generator_failed_to_access_global_spotify_client", error=str(e), exc_info=True)
            self.sp = None

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
                    limit=limit_per_artist
                )
                
                artist_albums = []
                for album in results.get('items', []):
                    name = album.get('name')
                    if name and self._is_good_title(name):
                        artist_albums.append(name)
                
                self.album_cache[cache_key] = artist_albums
                album_titles.extend(artist_albums)
                
            except Exception as e:
                app_logger.warning("fetch_albums_for_artist_failed", artist_id=artist_id, error=str(e), exc_info=True)
                continue
        
        return list(set(album_titles))  # Remove duplicates

    def fetch_similar_artists_albums(self, artist_ids: List[str], limit: int = 50) -> List[str]:
        """Fetch albums from similar artists to expand the pool"""
        if not self.sp or not artist_ids:
            return []
            
        similar_albums = []
        
        for artist_id in artist_ids[:5]:  # Limit to avoid quota issues
            try:
                # Get related artists with better error handling
                related = self.sp.artist_related_artists(artist_id)
                related_artist_ids = [artist['id'] for artist in related.get('artists', [])[:5]]
                
                # Fetch albums from related artists
                if related_artist_ids:  # Only if we found related artists
                    related_albums = self.fetch_albums_for_artists(related_artist_ids, limit_per_artist=8)
                    similar_albums.extend(related_albums)
                    
            except spotipy.exceptions.SpotifyException as e:
                if e.http_status == 404:
                    app_logger.info("fetch_related_artists_not_found", artist_id=artist_id)
                elif e.http_status == 403:
                    app_logger.warning("fetch_related_artists_forbidden", artist_id=artist_id)
                else:
                    app_logger.error("fetch_related_artists_spotify_exception", artist_id=artist_id, error=str(e), exc_info=True)
                continue
            except Exception as e:
                app_logger.error("fetch_related_artists_unexpected_error", artist_id=artist_id, error=str(e), exc_info=True)
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
                            limit=10
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
                app_logger.warning("search_albums_for_genre_failed", genre=genre, error=str(e), exc_info=True)
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

    @fault_tolerant_api_call("gemini_api", fallback_func=GracefulDegradation.handle_gemini_failure)
    def generate_ai_title_with_context(self, genres: List[str], mood: str, 
                                     sample_titles: List[str]) -> str:
        """Generate AI title using real album titles as context"""
        if not GEMINI_API_KEY: # Checked also in _call_gemini_api but good for early exit
            app_logger.error("gemini_api_key_missing_for_ai_title_generation")
            return "" # Fallback will be handled by decorator if this raises or returns specific value
            
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

    @monitor_api_calls("gemini_api")
    @retry_with_exponential_backoff()
    def _call_gemini_api(self, prompt: str) -> str:
        """Call Gemini API for title generation using http_client."""
        if not GEMINI_API_KEY:
            app_logger.error("gemini_api_key_missing")
            return ""
            
        headers = {"Content-Type": "application/json"}
        data = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 15, # Adjusted for typical title length
                "topP": 0.8
            }
        }

        url = f"{GEMINI_API_URL}?key={GEMINI_API_KEY}"

        try:
            # Using http_client from fault_handling module
            response = http_client.request(
                method='POST',
                url=url,
                headers=headers,
                json=data,
                timeout=30 # http_client should also respect this
            )
            
            # http_client.request should raise an exception for HTTP errors by default.
            # If not, or if specific non-200s are not exceptions:
            if response.status_code != 200:
                app_logger.error("gemini_api_error_status",
                                 status_code=response.status_code,
                                 response_text=response.text,
                                 url=url)
                return ""

            response_json = response.json()
            if 'candidates' in response_json and len(response_json['candidates']) > 0:
                part = response_json['candidates'][0].get('content', {}).get('parts', [{}])[0]
                if 'text' in part:
                    text = part['text']
                    return self._clean_title(text)
                else:
                    app_logger.warning("gemini_api_no_text_in_part", response_part=part)
                    return ""
            else:
                app_logger.warning("gemini_api_no_candidates", response_json=response_json)
                return ""
        except Exception as e:
            app_logger.error("gemini_api_call_exception", error=str(e), url=url, exc_info=True)
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

    @monitor_performance # Added monitor_performance, removed gemini specific decorators
    def generate_title(self, playlist_data: Dict, mood: str = "") -> str:
        """Main title generation using live Spotify data"""
        try:
            app_logger.info("live_spotify_title_generation_start", mood=mood)
            
            genres = playlist_data.get("genres", [])
            all_titles = []
            
            artist_ids = self.extract_artist_ids_from_playlist_data(playlist_data)
            
            if not artist_ids:
                app_logger.warning("no_artist_ids_found_for_title_generation", playlist_data_keys=list(playlist_data.keys()))
            
            if artist_ids and self.sp:
                artist_albums = self.fetch_albums_for_artists(artist_ids)
                if artist_albums:
                    all_titles.extend(artist_albums)
                    app_logger.info("fetched_artist_albums_for_titles", count=len(artist_albums))
                
                similar_albums = self.fetch_similar_artists_albums(artist_ids)
                if similar_albums:
                    all_titles.extend(similar_albums)
                    app_logger.info("fetched_similar_artist_albums_for_titles", count=len(similar_albums))
            
            if genres and self.sp:
                genre_albums = self.fetch_genre_albums(genres)
                if genre_albums:
                    all_titles.extend(genre_albums)
                    app_logger.info("fetched_genre_albums_for_titles", count=len(genre_albums))
            
            all_titles = list(set(all_titles))
            
            if all_titles:
                app_logger.info("total_album_title_pool_size", count=len(all_titles))
                candidates = self.select_best_titles(all_titles, genres, mood, count=10)
                
                if candidates:
                    if random.random() < 0.7: # 70% chance for real title
                        chosen_title = random.choice(candidates[:5])
                        app_logger.info("selected_real_album_title", title=chosen_title)
                        return chosen_title
                    else: # 30% chance for AI title
                        # generate_ai_title_with_context is now decorated with fault tolerance for Gemini
                        ai_title = self.generate_ai_title_with_context(genres, mood, candidates)
                        if ai_title and self._is_good_title(ai_title):
                            app_logger.info("generated_ai_inspired_title", title=ai_title)
                            return ai_title
                        else:
                            app_logger.warning("ai_title_generation_failed_or_bad_fallback_to_real", generated_title=ai_title)
                            chosen_title = random.choice(candidates[:3]) if len(candidates) >=3 else random.choice(candidates) if candidates else self._ultimate_fallback(genres, mood)
                            app_logger.info("fallback_to_real_album_title_after_ai_fail", title=chosen_title)
                            return chosen_title
            
            app_logger.warning("no_spotify_titles_found_using_ai_only_for_title")
            ai_title = self.generate_ai_title_with_context(genres, mood, []) # Decorated
            if ai_title and self._is_good_title(ai_title):
                app_logger.info("generated_ai_title_no_spotify_context", title=ai_title)
                return ai_title
            
            app_logger.warning("ai_only_title_generation_failed_using_ultimate_fallback")
            return self._ultimate_fallback(genres, mood)
            
        except Exception as e:
            app_logger.error("title_generation_pipeline_error", error=str(e), exc_info=True)
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
@monitor_performance # Added monitor_performance, removed gemini specific decorators
def generate_title(playlist_data, mood=""):
    """Generate title using live Spotify album data"""
    generator = LiveSpotifyTitleGenerator()
    return generator.generate_title(playlist_data, mood)