import random
import string
import json
import datetime
import re
import urllib.parse
from pathlib import Path
import os
import requests
from collections import Counter
from config import DATA_DIR, LORA_DIR, COVERS_DIR

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
    """Calculate percentage distribution of genres"""
    if not genres_list:
        return []
    
    try:
        # Attempt to use the more structured GenreAnalysis if available
        from models import GenreAnalysis 
        genre_analysis = GenreAnalysis.from_genre_list(genres_list)
        return genre_analysis.get_percentages(max_genres=5)
    except ImportError:
        # Fallback if models.py or GenreAnalysis is not available
        print("⚠️ models.GenreAnalysis not found, using fallback for calculate_genre_percentages.")
        if not isinstance(genres_list, list): # Ensure it's a list
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
                "count": count  # Keep the count for potential display
            })
        return percentages

def extract_playlist_id(playlist_url):
    """Extract playlist ID from Spotify URL"""
    if not playlist_url or "playlist/" not in playlist_url:
        return None
    try:
        # Example: https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M?si=...
        #          -> 37i9dQZF1DXcBWIGoYBM5M
        path_part = urllib.parse.urlparse(playlist_url).path
        if "/playlist/" in path_part:
            return path_part.split("/playlist/")[-1].split("/")[0]
    except Exception as e:
        print(f"Error parsing playlist URL '{playlist_url}': {e}")
    return None

def get_available_loras():
    """Get list of available LoRAs from config, database, and file system."""
    loaded_loras_by_name = {}
    
    # Import here to avoid circular imports
    from app import LoraModelDB, db, app # app needed for app_context
    from models import LoraModel

    # 1. Load LoRAs from lora_config.json
    try:
        lora_config_path = Path(__file__).parent / "lora_config.json"
        if lora_config_path.exists():
            with open(lora_config_path, 'r') as f:
                config_data = json.load(f)
                if "loras" in config_data:
                    for lora_data_from_json in config_data["loras"]:
                        lora_model = LoraModel.from_dict(lora_data_from_json)
                        if lora_model.name not in loaded_loras_by_name:
                            loaded_loras_by_name[lora_model.name] = lora_model
                        else:
                            print(f"LoRA name conflict: '{lora_model.name}' from JSON config already loaded. Skipping.")
    except Exception as e:
        print(f"Error loading LoRAs from lora_config.json: {e}")

    # 2. Get local LoRAs from the file system
    try:
        fs_lora_files = []
        for ext in [".safetensors", ".ckpt", ".pt"]:
            fs_lora_files.extend(list(LORA_DIR.glob(f"*{ext}")))
        
        for lora_file_path in fs_lora_files:
            lora_name = lora_file_path.stem
            if lora_name not in loaded_loras_by_name:
                loaded_loras_by_name[lora_name] = LoraModel(
                    name=lora_name,
                    source_type="local",
                    path=str(lora_file_path),
                    trigger_words=[], # Default, can be enhanced if conventions exist
                    strength=0.7      # Default
                )
            else:
                # If name conflict, config one is kept. If existing is local, update path if current is local.
                # This prioritizes JSON config for metadata, but filesystem for path if both are "local".
                if loaded_loras_by_name[lora_name].source_type == "local":
                     loaded_loras_by_name[lora_name].path = str(lora_file_path) # Ensure path is from actual file

    except Exception as e:
        print(f"Error scanning filesystem for LoRAs: {e}")

    # 3. Get LoRAs from database
    try:
        with app.app_context():
            db_loras = LoraModelDB.query.all()
            for db_lora in db_loras:
                if db_lora.name not in loaded_loras_by_name:
                    # If it's a local LoRA from DB, ensure its file exists
                    if db_lora.source_type == "local":
                        if not db_lora.path or not os.path.exists(db_lora.path):
                            print(f"Local LoRA '{db_lora.name}' found in DB but file missing at path: {db_lora.path}. Skipping.")
                            continue

                    # For link types from DB, or valid local ones from DB.
                    # LoraModelDB doesn't have url, trigger_words, strength anymore.
                    # So, creating LoraModel from it will use defaults for those.
                    loaded_loras_by_name[db_lora.name] = LoraModel(
                        name=db_lora.name,
                        source_type=db_lora.source_type, # "local" or "link"
                        path=db_lora.path, # Stored path for "local"
                        # url, trigger_words, strength will take defaults from LoraModel constructor
                    )
                else:
                    # Name conflict: LoRA already loaded from JSON or filesystem.
                    # If DB one is local and existing one is local, ensure path from DB (if valid) is considered or updated.
                    # This part can be complex depending on desired override behavior.
                    # For now, if JSON/FS loaded it, that takes precedence.
                    # If the loaded one is "local" and from JSON (no path), and DB has a path:
                    if loaded_loras_by_name[db_lora.name].source_type == "local" and \
                       not loaded_loras_by_name[db_lora.name].path and \
                       db_lora.source_type == "local" and db_lora.path and os.path.exists(db_lora.path):
                        print(f"Updating path for LoRA '{db_lora.name}' from DB record.")
                        loaded_loras_by_name[db_lora.name].path = db_lora.path


    except Exception as e:
        print(f"Error getting LoRAs from database: {e}")

    # Convert dict values to list and sort
    final_lora_list = sorted(list(loaded_loras_by_name.values()), key=lambda x: x.name)
    return final_lora_list

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
        print(f"Error listing recent generations: {e}")
        return []