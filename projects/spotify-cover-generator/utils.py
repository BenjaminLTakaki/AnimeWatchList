import random
import string
import json
import datetime
import re
import urllib.parse
from urllib.parse import urlparse
from pathlib import Path
import os
import requests
from collections import Counter
import uuid # For guest session functions
from flask import current_app, session # Added session for guest functions
from sqlalchemy import text # For db utils

# Local project imports
from config import DATA_DIR, LORA_DIR, COVERS_DIR
from .extensions import db
from .database_models import SpotifyState # For ensure_tables_exist
# This assumes 'models.py' (not database_models.py) contains GenreAnalysis for calculate_genre_percentages
from models import GenreAnalysis

def generate_random_string(size=10):
    """Generate a random string of letters and digits."""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=size))

def save_generation_data(data, output_path=None):
    """Save generation data to database and return ID."""
    try:
        # Import here to avoid circular imports
        from app import GenerationResultDB, db, app
        
        with app.app_context():
            # Create a new generation result record
            new_result = GenerationResultDB(
                title=data.get("title", "New Album"),
                output_path=data.get("output_path", ""),
                item_name=data.get("item_name", ""),
                genres=data.get("genres", []),
                all_genres=data.get("all_genres", []),
                style_elements=data.get("style_elements", []),
                mood=data.get("mood", ""),
                energy_level=data.get("energy_level", ""),
                spotify_url=data.get("spotify_url", ""),
                lora_name=data.get("lora_name", ""),
                lora_type=data.get("lora_type", ""),
                lora_url=data.get("lora_url", "")
            )
            
            db.session.add(new_result)
            db.session.commit()
            
            # Return the ID as a string
            return str(new_result.id)
    except Exception as e:
        print(f"Error saving data to database: {e}")
        
        # Fall back to saving to a JSON file if database fails
        try:
            # Create a unique filename based on timestamp
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_name = "".join(c for c in data.get("item_name", "") if c.isalnum() or c in [' ', '-', '_']).strip()
            safe_name = safe_name.replace(' ', '_')
            json_filename = f"{timestamp}_{safe_name}.json"
            
            with open(DATA_DIR / json_filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            print(f"Data saved to file {DATA_DIR / json_filename} (database failed)")
            
            return str(DATA_DIR / json_filename)
        except Exception as file_error:
            print(f"Error saving data to file: {file_error}")
            return None

def calculate_genre_percentages(genres_list):
    """Calculate percentage distribution of genres. Version from app.py."""
    if not genres_list:
        return []
    
    try:
        # Attempt to use the more structured GenreAnalysis if available
        # from models import GenreAnalysis # This import is now at the top of the file
        genre_analysis = GenreAnalysis.from_genre_list(genres_list)
        return genre_analysis.get_percentages(max_genres=5)
    except ImportError:
        # Fallback if models.py or GenreAnalysis is not available
        logger = current_app.logger if current_app else print
        logger("⚠️ models.GenreAnalysis not found, using fallback for calculate_genre_percentages.")
        if not isinstance(genres_list, list):
            return []
            
        genre_counter = Counter(genres_list)
        total_count = sum(genre_counter.values())
        if total_count == 0:
            return []
            
        sorted_genres = genre_counter.most_common(5)
        
        percentages = []
        for genre, count in sorted_genres:
            percentage = round((count / total_count) * 100)
            percentages.append({
                "name": genre,
                "percentage": percentage,
                "count": count
            })
        return percentages

def extract_playlist_id(playlist_url):
    """Extract playlist ID from Spotify URL. Version from app.py."""
    if not playlist_url or "playlist/" not in playlist_url:
        return None
    try:
        path_part = urlparse(playlist_url).path # urlparse imported at the top
        if "/playlist/" in path_part:
            return path_part.split("/playlist/")[-1].split("/")[0]
    except Exception as e:
        logger = current_app.logger if current_app else print
        logger(f"Error parsing playlist URL '{playlist_url}': {e}")
    return None

def get_available_loras():
    """Get list of available LoRAs from database and file system."""
    loras = []
    
    try:
        # First, get local LoRAs from the file system
        local_loras = []
        for ext in [".safetensors", ".ckpt", ".pt"]:
            local_loras.extend(list(LORA_DIR.glob(f"*{ext}")))
        
        # Import here to avoid circular imports
        from app import LoraModelDB, db, app
        from models import LoraModel
        
        # Convert file system LoRAs to LoraModel objects
        local_lora_names = []
        for lora in local_loras:
            local_lora_names.append(lora.stem)
            loras.append(LoraModel(
                name=lora.stem,
                source_type="local",
                path=str(lora),
                url="",
                trigger_words=[],
                strength=0.7
            ))
        
        # Get LoRAs from database (primarily link-type LoRAs)
        with app.app_context():
            db_loras = LoraModelDB.query.all()
            for db_lora in db_loras:                # Skip if we already have this from the file system
                if db_lora.source_type == "local" and db_lora.name in local_lora_names:
                    continue
                
                loras.append(LoraModel(
                    name=db_lora.name,
                    source_type=db_lora.source_type,
                    path=db_lora.path,
                    url="",  # No URL attribute in LoraModelDB
                    trigger_words=[],  # No trigger_words attribute in LoraModelDB
                    strength=0.7  # Default strength
                ))
        
        # Sort by name
        loras.sort(key=lambda x: x.name)
        return loras
    except Exception as e:
        print(f"Error getting LoRAs: {e}")
        # If database fails, try to get just file system LoRAs
        try:
            from models import LoraModel
            local_loras = []
            for ext in [".safetensors", ".ckpt", ".pt"]:
                local_loras.extend(list(LORA_DIR.glob(f"*{ext}")))
            
            return [LoraModel(
                name=lora.stem,
                source_type="local",
                path=str(lora),
                url="",
                trigger_words=[],
                strength=0.7
            ) for lora in local_loras]
        except Exception as inner_e:
            print(f"Error getting local LoRAs: {inner_e}")
            return []

def add_lora_link(name, url, trigger_words=None, strength=0.7):
    """Add a LoRA via link to the database."""
    try:
        # Make sure name is valid and unique
        name = name.strip()
        if not name:
            return False, "LoRA name cannot be empty"
        
        # Validate URL format
        if not is_valid_lora_url(url):
            return False, "Invalid LoRA URL format"
        
        # Import here to avoid circular imports
        from app import LoraModelDB, db, app
        
        with app.app_context():
            # Check if LoRA with this name already exists
            existing = LoraModelDB.query.filter_by(name=name).first()
            if existing:
                return False, f"LoRA with name '{name}' already exists"
            
            # Create new LoRA in database
            new_lora = LoraModelDB(
                name=name,
                source_type="link",
                path="",
                url=url,
                trigger_words=trigger_words or [],
                strength=float(strength)
            )
            
            db.session.add(new_lora)
            db.session.commit()
        
        return True, f"LoRA '{name}' added successfully"
    except Exception as e:
        print(f"Error adding LoRA link: {e}")
        return False, f"Error adding LoRA link: {str(e)}"

def is_valid_lora_url(url):
    """Validate if a URL is likely to be a valid LoRA URL."""
    # Check basic URL format
    try:
        result = urllib.parse.urlparse(url)
        if not all([result.scheme, result.netloc]):
            return False
        
        # Common LoRA hosting sites
        known_hosts = [
            'civitai.com', 
            'huggingface.co',
            'cloudflare.com',
            'discord.com',
            'githubusercontent.com'
        ]
        
        # Check if host is a common LoRA hosting site
        host_match = any(host in result.netloc for host in known_hosts)
        
        # Check file extension for direct file links
        path = result.path.lower()
        ext_match = path.endswith(('.safetensors', '.ckpt', '.pt', '.bin'))
        
        # If it's a known host or has a valid extension, consider it valid
        return host_match or ext_match
    except:
        return False

def create_image_filename(title):
    """Create a safe filename for the image."""
    safe_title = "".join(c for c in title if c.isalnum() or c in [' ', '-', '_']).strip()
    safe_title = safe_title.replace(' ', '_')
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{timestamp}_{safe_title}.png"

def extract_lora_id_from_civitai(url):
    """Extract the LoRA ID from a Civitai URL."""
    # Example: https://civitai.com/models/12345/my-lora
    try:
        match = re.search(r'/models/(\d+)', url)
        if match:
            return match.group(1)
        return None
    except:
        return None

def get_lora_details_from_civitai(lora_id):
    """Get LoRA details from Civitai API."""
    try:
        response = requests.get(f"https://civitai.com/api/v1/models/{lora_id}")
        if response.status_code == 200:
            data = response.json()
            
            # Extract relevant information
            name = data.get("name", "")
            description = data.get("description", "")
            
            # Get trigger words and download URL from the latest version
            trigger_words = []
            download_url = ""
            
            if "modelVersions" in data and len(data["modelVersions"]) > 0:
                latest_version = data["modelVersions"][0]
                
                # Get trigger words
                if "trainedWords" in latest_version:
                    trigger_words = latest_version["trainedWords"]
                
                # Get download URL - requires authentication, so we'll use the base URL
                download_url = f"https://civitai.com/models/{lora_id}"
            
            return {
                "name": name,
                "description": description,
                "trigger_words": trigger_words,
                "download_url": download_url
            }
        
        return None
    except Exception as e:
        print(f"Error fetching Civitai LoRA details: {e}")
        return None

def get_generation_by_id(generation_id):
    """Get a generation result by ID from the database."""
    try:
        # Import here to avoid circular imports
        from app import GenerationResultDB, db, app
        
        with app.app_context():
            result = GenerationResultDB.query.get(generation_id)
            if result:
                return {
                    "id": result.id,
                    "title": result.title,
                    "output_path": result.output_path,
                    "item_name": result.item_name,
                    "genres": result.genres,
                    "all_genres": result.all_genres,
                    "style_elements": result.style_elements,
                    "mood": result.mood,
                    "energy_level": result.energy_level,
                    "timestamp": result.timestamp.strftime("%Y-%m-%d %H:%M:%S") if result.timestamp else "",
                    "spotify_url": result.spotify_url,
                    "lora_name": result.lora_name,
                    "lora_type": result.lora_type,
                    "lora_url": result.lora_url
                }
            return None
    except Exception as e:
        print(f"Error getting generation by ID: {e}")
        return None

def list_recent_generations(limit=10):
    """List recent generation results from the database."""
    try:
        # Import here to avoid circular imports
        from app import GenerationResultDB, db, app
        
        with app.app_context():
            results = GenerationResultDB.query.order_by(GenerationResultDB.timestamp.desc()).limit(limit).all()
            return [{
                "id": result.id,
                "title": result.title,
                "output_path": result.output_path,
                "item_name": result.item_name,
                "timestamp": result.timestamp.strftime("%Y-%m-%d %H:%M:%S") if result.timestamp else "",
                "image_url": f"/spotifycovergenerator/generated_covers/{os.path.basename(result.output_path)}"
            } for result in results]
    except Exception as e:
            logger = current_app.logger if current_app else print
            logger(f"Error listing recent generations: {e}")
        return []

# --- Functions moved from app.py ---

def create_tables_manually():
    """
    Manually create tables using SQLAlchemy 2.0+ compatible syntax.
    Moved from app.py. Depends on db from extensions.
    """
    logger = current_app.logger if current_app else print
    logger("Attempting manual table creation...")
    # Simplified SQL commands for brevity, ensure these match the actual table structures needed
    sql_commands = [
        "CREATE TABLE IF NOT EXISTS spotify_users (id SERIAL PRIMARY KEY, email VARCHAR(120) UNIQUE, username VARCHAR(80) UNIQUE, password_hash VARCHAR(200), spotify_id VARCHAR(100) UNIQUE, spotify_username VARCHAR(100), spotify_access_token VARCHAR(500), spotify_refresh_token VARCHAR(500), spotify_token_expires TIMESTAMP, display_name VARCHAR(100), is_premium BOOLEAN DEFAULT FALSE, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, last_login TIMESTAMP, is_active BOOLEAN DEFAULT TRUE);",
        "CREATE TABLE IF NOT EXISTS spotify_login_sessions (id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES spotify_users(id) ON DELETE CASCADE, session_token VARCHAR(100) UNIQUE NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, expires_at TIMESTAMP NOT NULL, is_active BOOLEAN DEFAULT TRUE, ip_address VARCHAR(45), user_agent VARCHAR(500));",
        "CREATE TABLE IF NOT EXISTS spotify_oauth_states (id SERIAL PRIMARY KEY, state VARCHAR(100) UNIQUE NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, used BOOLEAN DEFAULT FALSE);",
        "CREATE TABLE IF NOT EXISTS spotify_lora_models (id SERIAL PRIMARY KEY, name VARCHAR(100) UNIQUE NOT NULL, source_type VARCHAR(20) DEFAULT 'local', path VARCHAR(500) DEFAULT '', file_size INTEGER DEFAULT 0, uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, uploaded_by INTEGER REFERENCES spotify_users(id) ON DELETE SET NULL);",
        "CREATE TABLE IF NOT EXISTS spotify_generation_results (id SERIAL PRIMARY KEY, title VARCHAR(500) NOT NULL, output_path VARCHAR(1000) NOT NULL, item_name VARCHAR(500), genres JSON, all_genres JSON, style_elements JSON, mood VARCHAR(1000), energy_level VARCHAR(50), timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP, spotify_url VARCHAR(1000), lora_name VARCHAR(200), lora_type VARCHAR(20), lora_url VARCHAR(1000), user_id INTEGER REFERENCES spotify_users(id) ON DELETE SET NULL);",
        "CREATE INDEX IF NOT EXISTS idx_users_email ON spotify_users(email);",
        "CREATE INDEX IF NOT EXISTS idx_users_spotify_id ON spotify_users(spotify_id);",
        "CREATE INDEX IF NOT EXISTS idx_sessions_token ON spotify_login_sessions(session_token);"
    ]
    with current_app.app_context():
        with db.engine.connect() as connection:
            for i, sql in enumerate(sql_commands):
                try:
                    connection.execute(text(sql))
                    connection.commit()
                    logger(f"SQL command {i+1} executed successfully.")
                except Exception as e:
                    logger(f"SQL command {i+1} failed: {e}")
                    pass # Continue attempting other commands

def ensure_tables_exist():
    """Ensure tables exist before any database operation. Moved from app.py."""
    logger = current_app.logger if current_app else print
    with current_app.app_context():
        try:
            # Check for a specific table (e.g., spotify_oauth_states which maps to SpotifyState model)
            with db.engine.connect() as connection: # Use db.engine for basic check
                connection.execute(text(f"SELECT 1 FROM {SpotifyState.__tablename__} LIMIT 1"))
            logger("Database tables seem to exist.")
        except Exception:
            logger("Tables missing or DB connection issue, attempting to create...")
            try:
                db.create_all()
                logger("db.create_all() executed.")
                # Verify again or run manual creation if needed
                with db.engine.connect() as connection:
                    connection.execute(text(f"SELECT 1 FROM {SpotifyState.__tablename__} LIMIT 1"))
                logger("Tables confirmed after db.create_all().")
            except Exception as e_create:
                logger(f"db.create_all() failed: {e_create}. Attempting manual table creation...")
                try:
                    create_tables_manually() # Fallback to manual creation
                except Exception as e_manual:
                    logger(f"Manual table creation also failed: {e_manual}")

# --- Guest Session Functions (Moved from app.py) ---
def get_or_create_guest_session():
    """Get or create a guest session for anonymous users."""
    if 'guest_session_id' not in session:
        session['guest_session_id'] = str(uuid.uuid4())
        session['guest_created'] = datetime.datetime.utcnow().isoformat()
        session['guest_generations_today'] = 0
        session['guest_last_generation'] = None
    return session['guest_session_id']

def get_guest_generations_today():
    """Get number of generations for guest today."""
    logger = current_app.logger if current_app else print
    if 'guest_session_id' not in session:
        get_or_create_guest_session()

    if 'guest_last_generation' in session and session['guest_last_generation']:
        try:
            last_gen_iso = session['guest_last_generation']
            if last_gen_iso:
                last_gen = datetime.datetime.fromisoformat(last_gen_iso)
                if last_gen.date() != datetime.datetime.utcnow().date():
                    session['guest_generations_today'] = 0
        except (TypeError, ValueError) as e:
            logger(f"Could not parse guest_last_generation: {session.get('guest_last_generation')}. Resetting count. Error: {e}")
            session['guest_last_generation'] = None
            session['guest_generations_today'] = 0
    return session.get('guest_generations_today', 0)

def increment_guest_generations():
    """Increment guest generation count."""
    session['guest_generations_today'] = get_guest_generations_today() + 1
    session['guest_last_generation'] = datetime.datetime.utcnow().isoformat()

def can_guest_generate():
    """Check if guest can generate."""
    # Guest limit can be configured in current_app.config if needed
    guest_limit = current_app.config.get('GUEST_DAILY_GENERATION_LIMIT', 1) if current_app else 1
    return get_guest_generations_today() < guest_limit

def track_guest_generation():
    """Track generation for guest."""
    logger = current_app.logger if current_app else print
    try:
        increment_guest_generations()
    except Exception as e:
        logger(f"Error tracking guest generation: {e}")