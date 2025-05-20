from collections import Counter
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
import json

@dataclass
class LoraModel:
    """LoRA model information"""
    name: str
    source_type: str = "local"  # "local" or "link"
    path: str = ""  # Local path
    url: str = ""  # External URL for link-based LoRAs
    trigger_words: List[str] = field(default_factory=list)
    strength: float = 0.7  # Default strength value
    
    @property
    def is_local(self):
        """Check if LoRA is locally stored"""
        return self.source_type == "local"
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            "name": self.name,
            "source_type": self.source_type,
            "path": self.path,
            "url": self.url,
            "trigger_words": self.trigger_words,
            "strength": self.strength
        }
    
    @classmethod
    def from_dict(cls, data):
        """Create LoraModel from dictionary"""
        return cls(
            name=data.get("name", "Unknown"),
            source_type=data.get("source_type", "local"),
            path=data.get("path", ""),
            url=data.get("url", ""),
            trigger_words=data.get("trigger_words", []),
            strength=data.get("strength", 0.7)
        )

@dataclass
class GenreAnalysis:
    """
    Improved genre analysis that ensures percentages add up to 100%
    """
    top_genres: List[str] = field(default_factory=list)
    all_genres: List[str] = field(default_factory=list)
    genres_with_counts: List[tuple] = field(default_factory=list)
    mood: str = "balanced"
    
    @classmethod
    def from_genre_list(cls, genres: List[str]):
        """Create a GenreAnalysis object from a list of genres."""
        if not genres:
            return cls()
        
        # Count and sort genres by frequency
        genre_counter = Counter(genres)
        top_genres = [genre for genre, _ in genre_counter.most_common(10)]
        genres_with_counts = genre_counter.most_common(20)
        
        # Determine overall mood based on genres
        mood = "balanced"  # Default mood
        
        # Simple genre-based mood classification
        mood_keywords = {
            "euphoric": ["edm", "dance", "house", "electronic", "pop", "party"],
            "energetic": ["rock", "metal", "punk", "trap", "dubstep"],
            "peaceful": ["ambient", "classical", "chill", "lo-fi", "instrumental"],
            "melancholic": ["sad", "slow", "ballad", "emotional", "soul", "blues"],
            "upbeat": ["happy", "funk", "disco", "pop", "tropical"],
            "relaxed": ["acoustic", "folk", "indie", "soft", "ambient"]
        }
        
        # Count genre matches for each mood
        mood_scores = {mood: 0 for mood in mood_keywords}
        
        for genre in genres:
            for mood_name, keywords in mood_keywords.items():
                if any(keyword in genre.lower() for keyword in keywords):
                    mood_scores[mood_name] += 1
        
        # Pick highest scoring mood if we have matches
        if any(mood_scores.values()):
            mood = max(mood_scores.items(), key=lambda x: x[1])[0]
        
        return cls(
            top_genres=top_genres,
            all_genres=genres,
            genres_with_counts=genres_with_counts,
            mood=mood
        )
    
    def get_style_elements(self):
        """Get style elements based on genres."""
        style_elements = []
        genres_lower = [g.lower() for g in self.top_genres]
        
        if any("rock" in g for g in genres_lower) or any("metal" in g for g in genres_lower):
            style_elements.append("dramatic lighting, bold contrasts")
        elif any("electronic" in g for g in genres_lower) or any("techno" in g for g in genres_lower):
            style_elements.append("futuristic, digital elements, abstract patterns")
        elif any("hip hop" in g for g in genres_lower) or any("rap" in g for g in genres_lower):
            style_elements.append("urban aesthetic, stylish, street art influence")
        elif any("jazz" in g for g in genres_lower) or any("blues" in g for g in genres_lower):
            style_elements.append("smoky atmosphere, classic vibe, vintage feel")
        elif any("folk" in g for g in genres_lower) or any("acoustic" in g for g in genres_lower):
            style_elements.append("organic textures, natural elements, warm tones")
        
        return style_elements
    
    def get_percentages(self, max_genres=5):
        """
        Calculate percentage distribution of genres, ensuring the total adds up to 100%.
        Takes top max_genres genres, and adjusts percentages to total 100%.
        """
        if not self.all_genres:
            return []
        
        # Count genres
        genre_counter = Counter(self.all_genres)
        total_count = sum(genre_counter.values())
        
        # Sort and get top genres
        sorted_genres = genre_counter.most_common(max_genres)
        
        # Get sum of just the top genres we're showing
        top_genres_count = sum(count for _, count in sorted_genres)
        
        # Calculate raw percentages for top genres
        raw_percentages = [
            {"name": genre, "raw_percentage": (count / top_genres_count) * 100, "count": count} 
            for genre, count in sorted_genres
        ]
        
        # Calculate total raw percentage
        total_raw_percentage = sum(item["raw_percentage"] for item in raw_percentages)
        
        # Adjust percentages to ensure they sum to 100%
        adjusted_percentages = []
        for item in raw_percentages:
            # Round to nearest integer but ensure percentage distribution adds to 100
            adjusted_percentage = round((item["raw_percentage"] / total_raw_percentage) * 100)
            adjusted_percentages.append({
                "name": item["name"],
                "percentage": adjusted_percentage,
                "count": item["count"]
            })
        
        # Ensure percentages add up to 100 by adjusting the largest value if needed
        total_adjusted = sum(item["percentage"] for item in adjusted_percentages)
        if total_adjusted != 100 and adjusted_percentages:
            # Find the genre with the highest count to adjust
            adjusted_percentages.sort(key=lambda x: x["count"], reverse=True)
            diff = 100 - total_adjusted
            adjusted_percentages[0]["percentage"] += diff
        
        # Sort back by percentage (highest first)
        adjusted_percentages.sort(key=lambda x: x["percentage"], reverse=True)
        
        return adjusted_percentages
    
@dataclass
class PlaylistData:
    item_name: str = "Unknown Playlist"
    track_names: List[str] = field(default_factory=list)
    genre_analysis: GenreAnalysis = field(default_factory=GenreAnalysis)
    spotify_url: str = ""
    found_genres: bool = False
    
    def to_dict(self):
        """Convert to dictionary."""
        return {
            "item_name": self.item_name,
            "track_names": self.track_names,
            "genres": self.genre_analysis.top_genres,
            "all_genres": self.genre_analysis.all_genres,
            "genres_with_counts": self.genre_analysis.genres_with_counts,
            "mood_descriptor": self.genre_analysis.mood,
            "spotify_url": self.spotify_url,
            "found_genres": self.found_genres,
            "style_elements": self.genre_analysis.get_style_elements()
        }
    
    @classmethod
    def from_dict(cls, data):
        """Create PlaylistData from dictionary."""
        genre_analysis = GenreAnalysis(
            top_genres=data.get("genres", []),
            all_genres=data.get("all_genres", []),
            genres_with_counts=data.get("genres_with_counts", []),
            mood=data.get("mood_descriptor", "balanced")
        )
        
        return cls(
            item_name=data.get("item_name", "Unknown Playlist"),
            track_names=data.get("track_names", []),
            genre_analysis=genre_analysis,
            spotify_url=data.get("spotify_url", ""),
            found_genres=data.get("found_genres", False)
        )

@dataclass
class GenerationResult:
    title: str
    output_path: str
    playlist_data: PlaylistData
    user_mood: str = ""
    lora_name: str = ""
    lora_type: str = ""  # "local" or "link"
    lora_url: str = ""   # URL for link-based LoRAs
    data_file: str = ""
    timestamp: str = ""
    
    def to_dict(self):
        """Convert to dictionary."""
        result = {
            "title": self.title,
            "output_path": self.output_path,
            "item_name": self.playlist_data.item_name,
            "genres": self.playlist_data.genre_analysis.top_genres,
            "all_genres": self.playlist_data.genre_analysis.all_genres,
            "style_elements": self.playlist_data.genre_analysis.get_style_elements(),
            "mood": self.user_mood if self.user_mood else self.playlist_data.genre_analysis.mood,
            "timestamp": self.timestamp,
            "spotify_url": self.playlist_data.spotify_url,
            "data_file": self.data_file
        }
        
        # Add LoRA information if present
        if self.lora_name:
            result["lora_name"] = self.lora_name
            result["lora_type"] = self.lora_type
            if self.lora_url:
                result["lora_url"] = self.lora_url
                
        return result