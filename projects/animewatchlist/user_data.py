from flask_sqlalchemy import SQLAlchemy
import datetime

# This will be initialized with the db imported from auth.py
db = None

# Define models for anime storage - will use SQLAlchemy instance from auth.py
class Anime(object):
    id = None
    mal_id = None
    title = None
    episodes = None
    image_url = None
    score = None
    
    def to_dict(self):
        return {
            "id": self.mal_id,
            "title": self.title,
            "episodes": self.episodes,
            "main_picture": {
                "medium": self.image_url
            },
            "score": self.score
        }

class UserAnimeList(object):
    id = None
    user_id = None
    anime_id = None
    status = None
    created_at = None

# Functions for user-specific anime data management
def get_anime_by_mal_id(mal_id):
    """Get anime by MyAnimeList ID or return None if not found."""
    return db.Anime.query.filter_by(mal_id=mal_id).first()

def add_anime_to_db(anime_data):
    """Add anime to database if it doesn't exist and return the Anime object."""
    mal_id = anime_data.get("id")
    anime = get_anime_by_mal_id(mal_id)
    
    if not anime:
        # Parse episodes - handle various formats
        episodes = anime_data.get("episodes")
        if episodes is None or episodes == "N/A":
            episodes_int = 0
        else:
            try:
                episodes_int = int(episodes)
            except (ValueError, TypeError):
                episodes_int = 0
        
        # Parse score
        score = anime_data.get("score")
        if score is None or score == "N/A":
            score_float = 0.0
        else:
            try:
                score_float = float(score)
            except (ValueError, TypeError):
                score_float = 0.0
        
        # Parse air date
        aired_from = None
        if anime_data.get("aired", {}).get("from"):
            try:
                # MAL API returns dates in ISO format
                aired_from = datetime.datetime.fromisoformat(
                    anime_data["aired"]["from"].replace("Z", "+00:00")
                ).date()
            except:
                aired_from = None
        
        # Parse genres
        genres = []
        if anime_data.get("genres"):
            genres = [genre["name"] for genre in anime_data["genres"]]
        elif anime_data.get("genre"):  # Alternative format
            genres = anime_data["genre"]
        genres_str = ",".join(genres) if genres else ""
        
        # Parse studio
        studio = ""
        if anime_data.get("studios") and len(anime_data["studios"]) > 0:
            studio = anime_data["studios"][0]["name"]
        
        anime = db.Anime(
            mal_id=mal_id,
            title=anime_data.get("title", "Unknown Title"),
            episodes=str(episodes),
            episodes_int=episodes_int,
            image_url=anime_data.get("main_picture", {}).get("medium", ""),
            score=str(score),
            score_float=score_float,
            aired_from=aired_from,
            genres=genres_str,
            studio=studio,
            type=anime_data.get("type", ""),
            status=anime_data.get("status", "")
        )
        db.session.add(anime)
        db.session.commit()
    
    return anime

def get_user_anime_list(user_id, sort_by="date_added", sort_order="desc"):
    """Get user's watched anime list with sorting options."""
    query = db.UserAnimeList.query.filter_by(user_id=user_id, status='watched')
    
    # Join with Anime table for sorting
    query = query.join(db.Anime)
    
    # Apply sorting
    if sort_by == "title":
        if sort_order == "asc":
            query = query.order_by(db.Anime.title.asc())
        else:
            query = query.order_by(db.Anime.title.desc())
    elif sort_by == "score":
        if sort_order == "desc":
            query = query.order_by(db.Anime.score_float.desc())
        else:
            query = query.order_by(db.Anime.score_float.asc())
    elif sort_by == "episodes":
        if sort_order == "desc":
            query = query.order_by(db.Anime.episodes_int.desc())
        else:
            query = query.order_by(db.Anime.episodes_int.asc())
    elif sort_by == "aired_date":
        if sort_order == "desc":
            query = query.order_by(db.Anime.aired_from.desc().nulls_last())
        else:
            query = query.order_by(db.Anime.aired_from.asc().nulls_last())
    else:  # Default: date_added
        if sort_order == "desc":
            query = query.order_by(db.UserAnimeList.created_at.desc())
        else:
            query = query.order_by(db.UserAnimeList.created_at.asc())
    
    user_animes = query.all()
    return [user_anime.anime.to_dict() for user_anime in user_animes]

def get_status_counts(user_id):
    """Return count for watched anime only."""
    watched_count = db.UserAnimeList.query.filter_by(user_id=user_id, status='watched').count()
    return watched_count, 0  # Return 0 for not_watched since we're removing that feature

def get_user_stats(user_id):
    """Get comprehensive statistics for user's watched anime."""
    user_animes = db.UserAnimeList.query.filter_by(user_id=user_id, status='watched').join(db.Anime).all()
    
    if not user_animes:
        return {
            'total_anime': 0,
            'total_episodes': 0,
            'estimated_hours': 0,
            'average_score': 0,
            'top_genres': [],
            'longest_anime': None,
            'highest_rated': None
        }
    
    total_anime = len(user_animes)
    total_episodes = sum(anime.anime.episodes_int for anime in user_animes)
    estimated_hours = round(total_episodes * 0.4, 1)  # ~24 minutes per episode = 0.4 hours
    
    # Calculate average score (excluding 0 scores)
    scores = [anime.anime.score_float for anime in user_animes if anime.anime.score_float > 0]
    average_score = round(sum(scores) / len(scores), 2) if scores else 0
    
    # Count genres
    genre_count = {}
    for user_anime in user_animes:
        if user_anime.anime.genres:
            genres = user_anime.anime.genres.split(',')
            for genre in genres:
                genre = genre.strip()
                if genre:
                    genre_count[genre] = genre_count.get(genre, 0) + 1
    
    # Top 5 genres
    top_genres = sorted(genre_count.items(), key=lambda x: x[1], reverse=True)[:5]
    
    # Longest anime (by episodes)
    longest_anime = max(user_animes, key=lambda x: x.anime.episodes_int, default=None)
    longest_anime = longest_anime.anime.to_dict() if longest_anime and longest_anime.anime.episodes_int > 0 else None
    
    # Highest rated anime
    highest_rated = max(user_animes, key=lambda x: x.anime.score_float, default=None)
    highest_rated = highest_rated.anime.to_dict() if highest_rated and highest_rated.anime.score_float > 0 else None
    
    return {
        'total_anime': total_anime,
        'total_episodes': total_episodes,
        'estimated_hours': estimated_hours,
        'average_score': average_score,
        'top_genres': top_genres,
        'longest_anime': longest_anime,
        'highest_rated': highest_rated
    }

def mark_anime_for_user(user_id, anime_data, status):
    """Mark anime as watched for a specific user. Ignore not_watched status."""
    if status != 'watched':
        return  # Only process watched anime
    
    # Add anime to database if it doesn't exist
    anime = add_anime_to_db(anime_data)
    
    # Check if there's already a record for this user and anime
    user_anime = db.UserAnimeList.query.filter_by(
        user_id=user_id, 
        anime_id=anime.id
    ).first()
    
    if user_anime:
        # Update existing status
        user_anime.status = status
    else:
        # Create new record
        user_anime = db.UserAnimeList(
            user_id=user_id,
            anime_id=anime.id,
            status=status
        )
        db.session.add(user_anime)
    
    db.session.commit()

def change_anime_status_for_user(user_id, mal_id, new_status):
    """Change an anime's status. Only support removing from watched list."""
    if new_status != 'remove':
        return False
    
    anime = get_anime_by_mal_id(mal_id)
    
    if not anime:
        return False
    
    user_anime = db.UserAnimeList.query.filter_by(
        user_id=user_id,
        anime_id=anime.id
    ).first()
    
    if user_anime:
        # Remove from list
        db.session.delete(user_anime)
        db.session.commit()
        return True
    
    return False

def get_anime_status_for_user(user_id, mal_id):
    """Get the status of an anime for a specific user."""
    anime = get_anime_by_mal_id(mal_id)
    
    if not anime:
        return None
    
    user_anime = db.UserAnimeList.query.filter_by(
        user_id=user_id,
        anime_id=anime.id
    ).first()
    
    return user_anime.status if user_anime else None

def init_user_data(database):
    """Initialize models with the database from auth.py"""
    global db
    db = database
    
    # Now define real models that use the db instance
    class Anime(db.Model):
        __tablename__ = 'anime'
        id = db.Column(db.Integer, primary_key=True)
        mal_id = db.Column(db.Integer, nullable=False)
        title = db.Column(db.String(255), nullable=False)
        episodes = db.Column(db.String(20), nullable=True)
        episodes_int = db.Column(db.Integer, default=0)  # For sorting/calculations
        image_url = db.Column(db.String(255), nullable=True)
        score = db.Column(db.String(10), nullable=True)
        score_float = db.Column(db.Float, default=0.0)  # For sorting/calculations
        aired_from = db.Column(db.Date, nullable=True)  # Air date
        genres = db.Column(db.Text, nullable=True)  # Comma-separated genres
        studio = db.Column(db.String(255), nullable=True)
        type = db.Column(db.String(50), nullable=True)  # TV, Movie, OVA, etc.
        status = db.Column(db.String(50), nullable=True)  # Finished Airing, Currently Airing, etc.
        
        def to_dict(self):
            return {
                "id": self.mal_id,
                "title": self.title,
                "episodes": self.episodes,
                "episodes_int": self.episodes_int,
                "main_picture": {
                    "medium": self.image_url
                },
                "score": self.score,
                "score_float": self.score_float,
                "aired_from": self.aired_from.isoformat() if self.aired_from else None,
                "genres": self.genres.split(',') if self.genres else [],
                "studio": self.studio,
                "type": self.type,
                "status": self.status
            }

    class UserAnimeList(db.Model):
        __tablename__ = 'user_anime_list'
        id = db.Column(db.Integer, primary_key=True)
        user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
        anime_id = db.Column(db.Integer, db.ForeignKey('anime.id'), nullable=False)
        status = db.Column(db.String(20), nullable=False)  # Only 'watched' now
        created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
        
        # Define relationship
        anime = db.relationship('Anime', backref='user_lists')
        user = db.relationship('User', backref='anime_lists')
        
        __table_args__ = (
            db.UniqueConstraint('user_id', 'anime_id', name='user_anime_unique'),
        )
    
    # Replace the placeholder classes with the real db models
    db.Anime = Anime
    db.UserAnimeList = UserAnimeList
    
    return Anime, UserAnimeList