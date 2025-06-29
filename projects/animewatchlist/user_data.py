from flask_sqlalchemy import SQLAlchemy
import datetime
from sqlalchemy import inspect

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

def check_column_exists(table_name, column_name):
    """Check if a column exists in the database table."""
    try:
        inspector = inspect(db.engine)
        columns = [col['name'] for col in inspector.get_columns(table_name)]
        return column_name in columns
    except:
        return False

# Functions for user-specific anime data management
def get_anime_by_mal_id(mal_id):
    """Get anime by MyAnimeList ID or return None if not found."""
    return db.Anime.query.filter_by(mal_id=mal_id).first()

def add_anime_to_db(anime_data):
    """Add anime to database if it doesn't exist and return the Anime object."""
    mal_id = anime_data.get("id")
    anime = get_anime_by_mal_id(mal_id)
    
    if not anime:
        # Basic anime data (always supported)
        anime_kwargs = {
            'mal_id': mal_id,
            'title': anime_data.get("title", "Unknown Title"),
            'episodes': str(anime_data.get("episodes", "N/A")),
            'image_url': anime_data.get("main_picture", {}).get("medium", ""),
            'score': str(anime_data.get("score", "N/A"))
        }
        
        # Enhanced data (only if columns exist)
        if check_column_exists('anime', 'episodes_int'):
            episodes = anime_data.get("episodes")
            if episodes is None or episodes == "N/A":
                episodes_int = 0
            else:
                try:
                    episodes_int = int(episodes)
                except (ValueError, TypeError):
                    episodes_int = 0
            anime_kwargs['episodes_int'] = episodes_int
        
        if check_column_exists('anime', 'score_float'):
            score = anime_data.get("score")
            if score is None or score == "N/A":
                score_float = 0.0
            else:
                try:
                    score_float = float(score)
                except (ValueError, TypeError):
                    score_float = 0.0
            anime_kwargs['score_float'] = score_float
        
        if check_column_exists('anime', 'aired_from'):
            aired_from = None
            if anime_data.get("aired", {}).get("from"):
                try:
                    aired_from = datetime.datetime.fromisoformat(
                        anime_data["aired"]["from"].replace("Z", "+00:00")
                    ).date()
                except:
                    aired_from = None
            anime_kwargs['aired_from'] = aired_from
        
        if check_column_exists('anime', 'genres'):
            genres = []
            if anime_data.get("genres"):
                genres = [genre["name"] for genre in anime_data["genres"]]
            elif anime_data.get("genre"):
                genres = anime_data["genre"]
            anime_kwargs['genres'] = ",".join(genres) if genres else ""
        
        if check_column_exists('anime', 'studio'):
            studio = ""
            if anime_data.get("studios") and len(anime_data["studios"]) > 0:
                studio = anime_data["studios"][0]["name"]
            anime_kwargs['studio'] = studio
        
        if check_column_exists('anime', 'type'):
            anime_kwargs['type'] = anime_data.get("type", "")
        
        if check_column_exists('anime', 'status'):
            anime_kwargs['status'] = anime_data.get("status", "")
        
        anime = db.Anime(**anime_kwargs)
        db.session.add(anime)
        db.session.commit()
    
    return anime

def get_user_anime_list(user_id, sort_by="date_added", sort_order="desc"):
    """Get user's watched anime list with sorting options."""
    query = db.UserAnimeList.query.filter_by(user_id=user_id, status='watched')
    
    # Join with Anime table for sorting
    query = query.join(db.Anime)
    
    # Check which columns exist for sorting
    has_episodes_int = check_column_exists('anime', 'episodes_int')
    has_score_float = check_column_exists('anime', 'score_float')
    has_aired_from = check_column_exists('anime', 'aired_from')
    
    # Apply sorting based on available columns
    if sort_by == "title":
        if sort_order == "asc":
            query = query.order_by(db.Anime.title.asc())
        else:
            query = query.order_by(db.Anime.title.desc())
    elif sort_by == "score" and has_score_float:
        if sort_order == "desc":
            query = query.order_by(db.Anime.score_float.desc())
        else:
            query = query.order_by(db.Anime.score_float.asc())
    elif sort_by == "episodes" and has_episodes_int:
        if sort_order == "desc":
            query = query.order_by(db.Anime.episodes_int.desc())
        else:
            query = query.order_by(db.Anime.episodes_int.asc())
    elif sort_by == "aired_date" and has_aired_from:
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
    
    # Check which columns exist for stats calculation
    has_episodes_int = check_column_exists('anime', 'episodes_int')
    has_score_float = check_column_exists('anime', 'score_float')
    has_genres = check_column_exists('anime', 'genres')
    
    # Calculate total episodes
    if has_episodes_int:
        total_episodes = sum(getattr(anime.anime, 'episodes_int', 0) for anime in user_animes)
    else:
        # Fallback: try to parse from episodes string
        total_episodes = 0
        for user_anime in user_animes:
            try:
                episodes_str = user_anime.anime.episodes
                if episodes_str and episodes_str != "N/A":
                    total_episodes += int(episodes_str)
            except (ValueError, TypeError):
                pass
    
    estimated_hours = round(total_episodes * 0.4, 1)  # ~24 minutes per episode = 0.4 hours
    
    # Calculate average score
    if has_score_float:
        scores = [getattr(anime.anime, 'score_float', 0) for anime in user_animes if getattr(anime.anime, 'score_float', 0) > 0]
    else:
        # Fallback: try to parse from score string
        scores = []
        for user_anime in user_animes:
            try:
                score_str = user_anime.anime.score
                if score_str and score_str != "N/A":
                    score_val = float(score_str)
                    if score_val > 0:
                        scores.append(score_val)
            except (ValueError, TypeError):
                pass
    
    average_score = round(sum(scores) / len(scores), 2) if scores else 0
    
    # Count genres
    genre_count = {}
    if has_genres:
        for user_anime in user_animes:
            genres_str = getattr(user_anime.anime, 'genres', '')
            if genres_str:
                genres = genres_str.split(',')
                for genre in genres:
                    genre = genre.strip()
                    if genre:
                        genre_count[genre] = genre_count.get(genre, 0) + 1
    
    # Top 5 genres
    top_genres = sorted(genre_count.items(), key=lambda x: x[1], reverse=True)[:5]
    
    # Longest anime (by episodes)
    longest_anime = None
    if has_episodes_int:
        longest = max(user_animes, key=lambda x: getattr(x.anime, 'episodes_int', 0), default=None)
        if longest and getattr(longest.anime, 'episodes_int', 0) > 0:
            longest_anime = longest.anime.to_dict()
    
    # Highest rated anime
    highest_rated = None
    if has_score_float:
        highest = max(user_animes, key=lambda x: getattr(x.anime, 'score_float', 0), default=None)
        if highest and getattr(highest.anime, 'score_float', 0) > 0:
            highest_rated = highest.anime.to_dict()
    
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
    
    # Check which columns exist in the current database
    has_enhanced_columns = (
        check_column_exists('anime', 'episodes_int') and
        check_column_exists('anime', 'score_float')
    )
    
    # Define Anime model based on available columns
    if has_enhanced_columns:
        # Enhanced model with all new columns
        class Anime(db.Model):
            __tablename__ = 'anime'
            id = db.Column(db.Integer, primary_key=True)
            mal_id = db.Column(db.Integer, nullable=False)
            title = db.Column(db.String(255), nullable=False)
            episodes = db.Column(db.String(20), nullable=True)
            episodes_int = db.Column(db.Integer, default=0)
            image_url = db.Column(db.String(255), nullable=True)
            score = db.Column(db.String(10), nullable=True)
            score_float = db.Column(db.Float, default=0.0)
            aired_from = db.Column(db.Date, nullable=True)
            genres = db.Column(db.Text, nullable=True)
            studio = db.Column(db.String(255), nullable=True)
            type = db.Column(db.String(50), nullable=True)
            status = db.Column(db.String(50), nullable=True)
            
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
    else:
        # Basic model (backward compatible)
        class Anime(db.Model):
            __tablename__ = 'anime'
            id = db.Column(db.Integer, primary_key=True)
            mal_id = db.Column(db.Integer, nullable=False)
            title = db.Column(db.String(255), nullable=False)
            episodes = db.Column(db.String(20), nullable=True)
            image_url = db.Column(db.String(255), nullable=True)
            score = db.Column(db.String(10), nullable=True)
            
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