from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
import re
import math
from functools import lru_cache
import json
from .extensions import db
import datetime
from werkzeug.security import generate_password_hash, check_password_hash


class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True, nullable=True)
    username = db.Column(db.String(50), unique=True, nullable=True)
    display_name = db.Column(db.String(100))
    password_hash = db.Column(db.String(200))
    
    # Spotify OAuth fields
    spotify_id = db.Column(db.String(100), unique=True, nullable=True)
    spotify_username = db.Column(db.String(100))
    spotify_access_token = db.Column(db.Text)
    spotify_refresh_token = db.Column(db.Text)
    spotify_token_expires = db.Column(db.DateTime)
    
    # User status
    is_premium = db.Column(db.Boolean, default=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    last_login = db.Column(db.DateTime)
    
    # Relationships
    login_sessions = db.relationship('LoginSession', backref='user', lazy='dynamic')
    generation_results = db.relationship('GenerationResultDB', backref='user', lazy='dynamic')
    
    def is_premium_user(self):
        """Check if user has premium access"""
        if self.is_admin:
            return True
        if self.email and self.email.lower() == 'bentakaki7@gmail.com':
            return True
        if self.spotify_id and self.spotify_id.lower() == 'benthegamer':
            return True
        return self.is_premium
    
    def is_admin(self):
        """Check if user is admin"""
        return self.is_admin
    
    def get_daily_generation_limit(self):
        """Get daily generation limit based on user type"""
        if self.is_premium_user():
            return float('inf')  # Unlimited
        return 2  # Free user limit
    
    def get_generations_today(self):
        """Get number of generations done today"""
        today_start = datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        return self.generation_results.filter(
            GenerationResultDB.timestamp >= today_start
        ).count()
    
    def can_generate_today(self):
        """Check if user can generate today"""
        return self.get_generations_today() < self.get_daily_generation_limit()
    
    def has_permission(self, permission):
        """Check if user has specific permission"""
        # Implement permission logic as needed
        if self.is_admin:
            return True
        return False

class LoginSession(db.Model):
    __tablename__ = 'login_sessions'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    session_token = db.Column(db.String(100), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(200))
    is_active = db.Column(db.Boolean, default=True)

class LoraModelDB(db.Model):
    __tablename__ = 'lora_models'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    source_type = db.Column(db.String(20), nullable=False)  # 'local' or 'link'
    path = db.Column(db.Text, nullable=False)
    file_size = db.Column(db.Integer)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    uploaded_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)

class GenerationResultDB(db.Model):
    __tablename__ = 'generation_results'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255))
    output_path = db.Column(db.String(500))
    item_name = db.Column(db.String(255))
    genres = db.Column(db.JSON)
    all_genres = db.Column(db.JSON)
    style_elements = db.Column(db.JSON)
    mood = db.Column(db.String(100))
    energy_level = db.Column(db.String(50))
    spotify_url = db.Column(db.String(500))
    lora_name = db.Column(db.String(100))
    lora_type = db.Column(db.String(20))
    lora_url = db.Column(db.String(500))
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))

class SpotifyState(db.Model):
    __tablename__ = 'spotify_oauth_states'
    
    id = db.Column(db.Integer, primary_key=True)
    state = db.Column(db.String(100), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    used = db.Column(db.Boolean, default=False)
    
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
    Enhanced genre analysis with human-like mood detection and cultural context
    """
    top_genres: List[str] = field(default_factory=list)
    all_genres: List[str] = field(default_factory=list)
    genres_with_counts: List[tuple] = field(default_factory=list)
    mood: str = "balanced"
    energy_level: str = "medium"  # low, medium, high, explosive
    emotional_depth: str = "neutral"  # surface, neutral, deep, profound
    cultural_context: List[str] = field(default_factory=list)
    confidence_score: float = 0.0  # How confident we are in our analysis
    
    # Enhanced mood categories with emotional intelligence
    MOOD_PROFILES = {
        "euphoric": {
            "keywords": ["edm", "dance", "house", "electronic", "trance", "techno", "eurodance", "hardcore"],
            "energy_weight": 0.9,
            "emotional_markers": ["uplifting", "festival", "rave", "club"],
            "cultural_context": ["nightclub", "festival", "celebration"],
            "antonyms": ["sad", "slow", "melancholic", "dark"]
        },
        "energetic": {
            "keywords": ["rock", "metal", "punk", "hardcore", "thrash", "speed", "power"],
            "energy_weight": 0.85,
            "emotional_markers": ["aggressive", "driving", "intense", "powerful"],
            "cultural_context": ["rebellion", "youth", "counterculture"],
            "antonyms": ["soft", "quiet", "ambient", "peaceful"]
        },
        "melancholic": {
            "keywords": ["sad", "slow", "ballad", "emotional", "soul", "blues", "torch", "tearjerker"],
            "energy_weight": 0.2,
            "emotional_markers": ["heartbreak", "longing", "nostalgia", "sorrow"],
            "cultural_context": ["introspection", "loss", "memory"],
            "antonyms": ["happy", "upbeat", "energetic", "party"]
        },
        "peaceful": {
            "keywords": ["ambient", "classical", "chill", "lo-fi", "instrumental", "meditation", "new age"],
            "energy_weight": 0.3,
            "emotional_markers": ["calming", "serene", "tranquil", "zen"],
            "cultural_context": ["relaxation", "study", "meditation"],
            "antonyms": ["aggressive", "loud", "harsh", "intense"]
        },
        "upbeat": {
            "keywords": ["happy", "funk", "disco", "pop", "tropical", "feel-good", "sunshine"],
            "energy_weight": 0.7,
            "emotional_markers": ["joyful", "optimistic", "cheerful", "bright"],
            "cultural_context": ["celebration", "positivity", "summer"],
            "antonyms": ["sad", "dark", "gloomy", "depressing"]
        },
        "contemplative": {
            "keywords": ["indie", "alternative", "art", "experimental", "progressive", "post"],
            "energy_weight": 0.5,
            "emotional_markers": ["thoughtful", "introspective", "complex", "layered"],
            "cultural_context": ["intellectualism", "artistry", "depth"],
            "antonyms": ["simple", "commercial", "mainstream"]
        },
        "nostalgic": {
            "keywords": ["retro", "vintage", "oldies", "classic", "throwback", "revival"],
            "energy_weight": 0.4,
            "emotional_markers": ["reminiscent", "wistful", "timeless", "memory"],
            "cultural_context": ["past eras", "golden age", "tradition"],
            "antonyms": ["modern", "futuristic", "cutting-edge"]
        },
        "rebellious": {
            "keywords": ["punk", "grunge", "riot", "protest", "underground", "anarchist"],
            "energy_weight": 0.8,
            "emotional_markers": ["defiant", "raw", "authentic", "uncompromising"],
            "cultural_context": ["counterculture", "social change", "authenticity"],
            "antonyms": ["conformist", "mainstream", "polished"]
        }
    }
    
    # Cultural and temporal context mapping
    CULTURAL_CONTEXTS = {
        "80s": ["synthwave", "new wave", "post-punk", "hair metal"],
        "90s": ["grunge", "britpop", "trip hop", "rave"],
        "2000s": ["emo", "nu metal", "garage", "crunk"],
        "latin": ["reggaeton", "salsa", "bossa nova", "tango", "mariachi"],
        "african": ["afrobeat", "highlife", "soukous", "mbaqanga"],
        "electronic": ["techno", "house", "drum and bass", "dubstep", "trance"],
        "urban": ["hip hop", "r&b", "trap", "drill", "grime"],
        "world": ["folk", "traditional", "ethnic", "world music"]
    }
    
    # Energy level indicators with more nuance
    ENERGY_INDICATORS = {
        "explosive": ["hardcore", "speedcore", "thrash", "death metal", "gabber"],
        "high": ["rock", "punk", "dance", "edm", "trap", "drum and bass"],
        "medium": ["pop", "indie", "alternative", "funk", "disco"],
        "low": ["ballad", "slow", "soft", "acoustic", "folk"],
        "minimal": ["ambient", "drone", "meditation", "sleep"]
    }
    
    @classmethod
    def from_genre_list(cls, genres: List[str]):
        """Create enhanced GenreAnalysis with human-like intelligence"""
        if not genres:
            return cls()
        
        # Clean and normalize genres
        normalized_genres = cls._normalize_genres(genres)
        
        # Count and analyze frequency
        genre_counter = Counter(normalized_genres)
        
        # Perform sophisticated mood analysis
        mood_analysis = cls._analyze_mood_with_context(normalized_genres, genre_counter)
        
        # Determine energy level with nuance
        energy_level = cls._calculate_energy_level(normalized_genres)
        
        # Assess cultural context
        cultural_context = cls._identify_cultural_context(normalized_genres)
        
        # Calculate emotional depth
        emotional_depth = cls._assess_emotional_depth(normalized_genres, genre_counter)
        
        return cls(
            top_genres=[genre for genre, _ in genre_counter.most_common(10)],
            all_genres=normalized_genres,
            genres_with_counts=genre_counter.most_common(20),
            mood=mood_analysis["primary_mood"],
            energy_level=energy_level,
            emotional_depth=emotional_depth,
            cultural_context=cultural_context,
            confidence_score=mood_analysis["confidence"]
        )
    
    @classmethod
    def _normalize_genres(cls, genres: List[str]) -> List[str]:
        """Clean and normalize genre names for better analysis"""
        normalized = []
        for genre in genres:
            # Convert to lowercase and clean
            clean_genre = genre.lower().strip()
            
            # Handle common variations and synonyms
            synonyms = {
                "hip-hop": "hip hop",
                "r&b": "rnb",
                "drum'n'bass": "drum and bass",
                "d&b": "drum and bass",
                "uk garage": "garage",
                "future bass": "bass",
                "melodic dubstep": "dubstep",
                "progressive house": "house progressive",
                "deep house": "house deep"
            }
            
            for original, replacement in synonyms.items():
                if original in clean_genre:
                    clean_genre = clean_genre.replace(original, replacement)
            
            normalized.append(clean_genre)
        
        return normalized
    
    @classmethod
    def _analyze_mood_with_context(cls, genres: List[str], genre_counter: Counter) -> Dict:
        """Advanced mood analysis with contextual understanding"""
        mood_scores = defaultdict(float)
        total_weight = 0
        
        for genre, count in genre_counter.items():
            genre_weight = math.log(count + 1)  # Logarithmic weighting for frequency
            total_weight += genre_weight
            
            # Score each mood profile
            for mood_name, profile in cls.MOOD_PROFILES.items():
                score = 0
                
                # Direct keyword matching with fuzzy logic
                for keyword in profile["keywords"]:
                    if keyword in genre:
                        score += 1.0
                    elif cls._fuzzy_match(keyword, genre):
                        score += 0.7
                
                # Emotional markers boost
                for marker in profile["emotional_markers"]:
                    if marker in genre:
                        score += 0.5
                
                # Antonym penalty - reduces score if conflicting moods present
                for antonym in profile["antonyms"]:
                    if antonym in genre:
                        score -= 0.3
                
                # Apply energy weighting
                energy_factor = profile["energy_weight"]
                weighted_score = score * energy_factor * genre_weight
                mood_scores[mood_name] += weighted_score
        
        # Normalize scores
        if total_weight > 0:
            for mood in mood_scores:
                mood_scores[mood] /= total_weight
        
        # Handle edge cases and conflicts
        primary_mood, confidence = cls._resolve_mood_conflicts(mood_scores, genres)
        
        return {
            "primary_mood": primary_mood,
            "confidence": confidence,
            "all_scores": dict(mood_scores)
        }
    
    @classmethod
    def _fuzzy_match(cls, keyword: str, genre: str, threshold: float = 0.7) -> bool:
        """Simple fuzzy matching for genre keywords"""
        # Check if keyword is a substring or vice versa
        if len(keyword) <= 3 or len(genre) <= 3:
            return keyword in genre or genre in keyword
        
        # Simple Jaccard similarity for longer strings
        set1 = set(keyword)
        set2 = set(genre)
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        
        return intersection / union >= threshold if union > 0 else False
    
    @classmethod
    def _resolve_mood_conflicts(cls, mood_scores: Dict[str, float], genres: List[str]) -> Tuple[str, float]:
        """Intelligently resolve conflicting moods with human-like reasoning"""
        if not mood_scores:
            return "balanced", 0.0
        
        # Sort moods by score
        sorted_moods = sorted(mood_scores.items(), key=lambda x: x[1], reverse=True)
        
        if not sorted_moods or sorted_moods[0][1] <= 0:
            return "balanced", 0.0
        
        primary_mood, primary_score = sorted_moods[0]
        
        # Calculate confidence based on score distribution
        if len(sorted_moods) == 1:
            confidence = min(primary_score, 0.9)
        else:
            second_score = sorted_moods[1][1]
            score_gap = primary_score - second_score
            confidence = min(score_gap / (primary_score + 0.1), 0.95)
        
        # Special case: mixed moods that commonly coexist
        mixed_mood_combinations = {
            ("melancholic", "contemplative"): "introspective",
            ("energetic", "rebellious"): "aggressive",
            ("peaceful", "contemplative"): "meditative",
            ("upbeat", "nostalgic"): "bittersweet",
            ("euphoric", "energetic"): "explosive"
        }
        
        # Check for meaningful mixed moods
        if len(sorted_moods) >= 2 and confidence < 0.6:
            top_two = tuple(sorted([sorted_moods[0][0], sorted_moods[1][0]]))
            if top_two in mixed_mood_combinations:
                return mixed_mood_combinations[top_two], confidence + 0.2
        
        return primary_mood, confidence
    
    @classmethod
    def _calculate_energy_level(cls, genres: List[str]) -> str:
        """Calculate energy level with musical understanding"""
        energy_scores = defaultdict(int)
        
        for genre in genres:
            for energy_level, indicators in cls.ENERGY_INDICATORS.items():
                for indicator in indicators:
                    if indicator in genre:
                        energy_scores[energy_level] += 1
        
        if not energy_scores:
            return "medium"
        
        # Weight by intensity
        energy_weights = {"explosive": 5, "high": 4, "medium": 3, "low": 2, "minimal": 1}
        weighted_total = sum(count * energy_weights[level] for level, count in energy_scores.items())
        total_genres = len(genres)
        
        average_energy = weighted_total / total_genres if total_genres > 0 else 3
        
        if average_energy >= 4.5:
            return "explosive"
        elif average_energy >= 3.5:
            return "high"
        elif average_energy >= 2.5:
            return "medium"
        elif average_energy >= 1.5:
            return "low"
        else:
            return "minimal"
    
    @classmethod
    def _identify_cultural_context(cls, genres: List[str]) -> List[str]:
        """Identify cultural and temporal contexts"""
        contexts = set()
        
        for genre in genres:
            for context, indicators in cls.CULTURAL_CONTEXTS.items():
                if any(indicator in genre for indicator in indicators):
                    contexts.add(context)
        
        return sorted(list(contexts))
    
    @classmethod
    def _assess_emotional_depth(cls, genres: List[str], genre_counter: Counter) -> str:
        """Assess the emotional complexity and depth"""
        depth_indicators = {
            "profound": ["classical", "opera", "symphony", "chamber", "art", "avant-garde"],
            "deep": ["progressive", "post", "experimental", "jazz", "blues", "soul"],
            "neutral": ["pop", "rock", "indie", "alternative"],
            "surface": ["commercial", "mainstream", "top 40", "radio"]
        }
        
        depth_scores = defaultdict(int)
        
        for genre in genres:
            for depth_level, indicators in depth_indicators.items():
                for indicator in indicators:
                    if indicator in genre:
                        depth_scores[depth_level] += 1
        
        if not depth_scores:
            return "neutral"
        
        return max(depth_scores.items(), key=lambda x: x[1])[0]
    
    def get_human_readable_description(self) -> str:
        """Generate a human-like description of the music analysis"""
        descriptions = []
        
        # Energy description
        energy_descriptions = {
            "explosive": "incredibly high-energy and intense",
            "high": "energetic and driving",
            "medium": "moderately paced",
            "low": "relaxed and laid-back",
            "minimal": "very calm and subdued"
        }
        
        # Mood description with personality
        mood_descriptions = {
            "euphoric": "designed to lift spirits and create pure joy",
            "energetic": "full of power and momentum",
            "melancholic": "emotionally rich with undertones of longing",
            "peaceful": "creating a sense of tranquility and calm",
            "upbeat": "radiating positivity and good vibes",
            "contemplative": "inviting deep thought and reflection",
            "nostalgic": "evoking memories and times past",
            "rebellious": "challenging conventions with raw authenticity",
            "introspective": "encouraging inner exploration",
            "aggressive": "intense and uncompromising",
            "meditative": "perfect for quiet contemplation",
            "bittersweet": "mixing joy with gentle melancholy",
            "explosive": "bursting with unstoppable energy"
        }
        
        base_description = f"This music is {energy_descriptions.get(self.energy_level, 'balanced')} and {mood_descriptions.get(self.mood, 'versatile in mood')}"
        
        # Add cultural context if present
        if self.cultural_context:
            context_str = ", ".join(self.cultural_context)
            base_description += f", drawing from {context_str} influences"
        
        # Add confidence indicator
        if self.confidence_score > 0.8:
            base_description += ". This analysis has high confidence."
        elif self.confidence_score > 0.6:
            base_description += ". This analysis is fairly confident."
        else:
            base_description += ". This music shows mixed influences that create a unique blend."
        
        return base_description
    
    def get_style_elements(self) -> List[str]:
        """Get enhanced style elements based on sophisticated analysis"""
        style_elements = []
        
        # Mood-based styling
        mood_styles = {
            "euphoric": ["vibrant colors", "dynamic movement", "celebration"],
            "energetic": ["bold contrasts", "dramatic lighting", "power"],
            "melancholic": ["muted tones", "emotional depth", "introspection"],
            "peaceful": ["soft gradients", "natural elements", "serenity"],
            "upbeat": ["bright colors", "playful elements", "joy"],
            "contemplative": ["abstract forms", "layered complexity", "thoughtfulness"],
            "nostalgic": ["vintage aesthetics", "warm tones", "memory"],
            "rebellious": ["raw textures", "urban elements", "authenticity"]
        }
        
        if self.mood in mood_styles:
            style_elements.extend(mood_styles[self.mood])
        
        # Energy-based styling
        energy_styles = {
            "explosive": ["extreme contrasts", "motion blur", "intensity"],
            "high": ["dynamic composition", "strong lines", "movement"],
            "medium": ["balanced composition", "moderate contrast"],
            "low": ["soft focus", "gentle curves", "calm"],
            "minimal": ["negative space", "simplicity", "zen"]
        }
        
        if self.energy_level in energy_styles:
            style_elements.extend(energy_styles[self.energy_level])
        
        # Cultural context styling
        cultural_styles = {
            "80s": ["neon colors", "geometric shapes", "retro-futurism"],
            "90s": ["grunge textures", "alternative aesthetics"],
            "latin": ["warm colors", "rhythmic patterns", "cultural richness"],
            "electronic": ["digital elements", "futuristic design", "synthetic textures"],
            "urban": ["street art influence", "modern cityscape", "contemporary edge"]
        }
        
        for context in self.cultural_context:
            if context in cultural_styles:
                style_elements.extend(cultural_styles[context])
        
        return list(set(style_elements))
    
    @staticmethod
    @lru_cache(maxsize=100)
    def _calculate_mood(genres_tuple):
        """Cached mood calculation for identical genre combinations"""
        genres = list(genres_tuple)
        
        # Simple genre-based mood classification
        mood_keywords = {
            "euphoric": ["edm", "dance", "house", "electronic", "pop", "party"],
            "energetic": ["rock", "metal", "punk", "trap", "dubstep"],
            "peaceful": ["ambient", "classical", "chill", "lo-fi", "instrumental"],
            "melancholic": ["sad", "slow", "ballad", "emotional", "soul", "blues"],
            "upbeat": ["happy", "funk", "disco", "pop", "tropical"],
            "relaxed": ["acoustic", "folk", "indie", "soft", "ambient"]
        }
        
        # Count genre matches for each mood (optimized single pass)
        mood_scores = {mood: 0 for mood in mood_keywords}
        genres_lower = [genre.lower() for genre in genres]
        
        for genre_lower in genres_lower:
            for mood_name, keywords in mood_keywords.items():
                if any(keyword in genre_lower for keyword in keywords):
                    mood_scores[mood_name] += 1
        
        # Pick highest scoring mood if we have matches
        if any(mood_scores.values()):
            return max(mood_scores.items(), key=lambda x: x[1])[0]
        
        return "balanced"

    @classmethod
    def from_genre_list(cls, genres: List[str]):
        """Create a GenreAnalysis object from a list of genres."""
        if not genres:
            return cls()
        
        # Count and sort genres by frequency
        genre_counter = Counter(genres)
        top_genres = [genre for genre, _ in genre_counter.most_common(10)]
        genres_with_counts = genre_counter.most_common(20)
        
        # Optimized mood calculation with caching
        genres_tuple = tuple(sorted(genres))  # Sort for consistent caching
        mood = cls._calculate_mood(genres_tuple)
        
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
        
        # Sort back to original order
        adjusted_percentages.sort(key=lambda x: self.all_genres.index(x["name"]))
        
        return adjusted_percentages
    
@dataclass
class PlaylistData:
    item_name: str = "Unknown Playlist"
    track_names: List[str] = field(default_factory=list)
    genre_analysis: GenreAnalysis = field(default_factory=GenreAnalysis)
    spotify_url: str = ""
    found_genres: bool = False
    artist_ids: List[str] = field(default_factory=list)  # NEW: Add artist IDs
    
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
            "style_elements": self.genre_analysis.get_style_elements(),
            "artist_ids": self.artist_ids  # NEW: Include artist IDs in dict
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
            found_genres=data.get("found_genres", False),
            artist_ids=data.get("artist_ids", [])  # NEW: Include artist IDs
        )
    
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