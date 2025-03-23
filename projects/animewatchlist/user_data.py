from flask_sqlalchemy import SQLAlchemy

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
        anime = db.Anime(
            mal_id=mal_id,
            title=anime_data.get("title", "Unknown Title"),
            episodes=str(anime_data.get("episodes", "N/A")),
            image_url=anime_data.get("main_picture", {}).get("medium", ""),
            score=str(anime_data.get("score", "N/A"))
        )
        db.session.add(anime)
        db.session.commit()
    
    return anime

def get_user_anime_list(user_id, status):
    """Get user's anime list for specific status ('watched' or 'not_watched')."""
    user_animes = db.UserAnimeList.query.filter_by(user_id=user_id, status=status).all()
    return [user_anime.anime.to_dict() for user_anime in user_animes]

def get_status_counts(user_id):
    """Return counts for watched and not watched anime for a specific user."""
    watched_count = db.UserAnimeList.query.filter_by(user_id=user_id, status='watched').count()
    not_watched_count = db.UserAnimeList.query.filter_by(user_id=user_id, status='not_watched').count()
    return watched_count, not_watched_count

def mark_anime_for_user(user_id, anime_data, status):
    """Mark anime as watched or not watched for a specific user."""
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
    """Change an anime's status from watched to not watched or vice versa for a specific user."""
    anime = get_anime_by_mal_id(mal_id)
    
    if not anime:
        return False
    
    user_anime = db.UserAnimeList.query.filter_by(
        user_id=user_id,
        anime_id=anime.id
    ).first()
    
    if user_anime:
        # Update existing status
        user_anime.status = new_status
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
    global db, Anime, UserAnimeList
    db = database
    
    # Now define real models that use the db instance
    class Anime(db.Model):
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
        id = db.Column(db.Integer, primary_key=True)
        user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
        anime_id = db.Column(db.Integer, db.ForeignKey('anime.id'), nullable=False)
        status = db.Column(db.String(20), nullable=False)  # 'watched' or 'not_watched'
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