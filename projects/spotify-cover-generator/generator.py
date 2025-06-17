import os
import sys
import datetime
import base64
import io
from pathlib import Path
from PIL import Image

# Ensure the project's own directory is prioritized for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# Import modules with proper error handling
try:
    from spotify_client import extract_playlist_data
    SPOTIFY_CLIENT_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ spotify_client import failed: {e}")
    SPOTIFY_CLIENT_AVAILABLE = False

try:
    from image_generator import create_prompt_from_data, generate_cover_image
    IMAGE_GENERATOR_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ image_generator import failed: {e}")
    IMAGE_GENERATOR_AVAILABLE = False

try:
    from title_generator import generate_title
    TITLE_GENERATOR_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ title_generator import failed: {e}")
    TITLE_GENERATOR_AVAILABLE = False

try:
    from chart_generator import generate_genre_chart
    CHART_GENERATOR_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ chart_generator import failed: {e}")
    CHART_GENERATOR_AVAILABLE = False

try:
    from utils import create_image_filename, get_available_loras
    UTILS_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ utils import failed: {e}")
    UTILS_AVAILABLE = False

try:
    from models import GenerationResult
    MODELS_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ models import failed: {e}")
    MODELS_AVAILABLE = False
    
    # Create fallback GenerationResult class
    class GenerationResult:
        def __init__(self, title="", output_path="", playlist_data=None, user_mood="", 
                     lora_name="", lora_type="", lora_url="", data_file="", timestamp=""):
            self.title = title
            self.output_path = output_path
            self.playlist_data = playlist_data
            self.user_mood = user_mood
            self.lora_name = lora_name
            self.lora_type = lora_type
            self.lora_url = lora_url
            self.data_file = data_file
            self.timestamp = timestamp
        
        def to_dict(self):
            result = {
                "title": self.title,
                "output_path": self.output_path,
                "mood": self.user_mood,
                "timestamp": self.timestamp,
                "data_file": self.data_file
            }
            
            if self.playlist_data:
                if hasattr(self.playlist_data, 'to_dict'):
                    playlist_dict = self.playlist_data.to_dict()
                    result.update({
                        "item_name": playlist_dict.get("item_name", ""),
                        "genres": playlist_dict.get("genres", []),
                        "all_genres": playlist_dict.get("all_genres", []),
                        "style_elements": playlist_dict.get("style_elements", []),
                        "spotify_url": playlist_dict.get("spotify_url", "")
                    })
                else:
                    result.update({
                        "item_name": getattr(self.playlist_data, 'item_name', ''),
                        "genres": [],
                        "all_genres": [],
                        "style_elements": [],
                        "spotify_url": ""
                    })
            
            if self.lora_name:
                result.update({
                    "lora_name": self.lora_name,
                    "lora_type": self.lora_type,
                    "lora_url": self.lora_url
                })
                
            return result

from config import COVERS_DIR

# Monitoring imports with fallback
try:
    from monitoring_system import monitor_performance
except ImportError:
    def monitor_performance(func):
        return func

def save_generation_data_with_user(data, user_id=None):
    """Save generation data to database with user tracking"""
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
                lora_url=data.get("lora_url", ""),
                user_id=user_id
            )
            
            db.session.add(new_result)
            db.session.commit()
            
            return str(new_result.id)
    except Exception as e:
        print(f"Error saving data to database: {e}")
        
        # Fall back to saving to a JSON file if database fails
        try:
            from config import DATA_DIR
            import json
            
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

def create_fallback_image(output_path, title="Generated Cover"):
    """Create a simple fallback image when generation fails"""
    try:
        # Create a simple placeholder image
        width, height = 512, 512
        image = Image.new('RGB', (width, height), color='#2a2a2a')
        
        # Save the placeholder
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        image.save(output_path)
        
        print(f"Created fallback image at {output_path}")
        return image
    except Exception as e:
        print(f"Error creating fallback image: {e}")
        return None

def fallback_title_generation(genres, mood):
    """Generate a simple fallback title"""
    if mood:
        words = mood.split()[:2]
        return ' '.join(word.capitalize() for word in words)
    elif genres:
        return f"New {genres[0].replace('_', ' ').title()}"
    else:
        import random
        return random.choice([
            "New Horizons", "Fresh Perspective", "Next Chapter", 
            "New Dawn", "Open Roads", "Clear Skies"
        ])

def fallback_prompt_generation(playlist_data, user_mood):
    """Generate a simple fallback prompt"""
    genres = playlist_data.get("genres", ["music"]) if isinstance(playlist_data, dict) else ["music"]
    mood = user_mood or "balanced"
    
    prompt = f"album cover art, {', '.join(genres)} music, professional artwork, highly detailed"
    if mood:
        prompt += f", {mood}"
    
    return prompt

@monitor_performance
def generate_cover(url, user_mood=None, lora_input=None, output_path=None, negative_prompt=None, user_id=None):
    """Generate album cover and title from Spotify URL with comprehensive error handling"""
    print(f"🎵 Processing Spotify URL: {url}")
    
    # Check module availability
    if not SPOTIFY_CLIENT_AVAILABLE:
        return {"error": "Spotify client module not available. Please check your installation."}
    
    # Extract playlist/album data
    try:
        playlist_data = extract_playlist_data(url)
        if isinstance(playlist_data, dict) and "error" in playlist_data:
            return {"error": playlist_data["error"]}
        
        print(f"✓ Successfully extracted data for: {playlist_data.item_name}")
        print(f"Top genres identified: {', '.join(playlist_data.genre_analysis.top_genres)}")
    except Exception as e:
        print(f"❌ Error extracting playlist data: {e}")
        return {"error": f"Failed to extract playlist data: {str(e)}"}
    
    # Convert playlist data to dictionary
    try:
        data = playlist_data.to_dict()
    except Exception as e:
        print(f"⚠️ Error converting playlist data to dict: {e}")
        # Create minimal data structure
        data = {
            "item_name": getattr(playlist_data, 'item_name', 'Unknown Playlist'),
            "genres": [],
            "all_genres": [],
            "style_elements": [],
            "spotify_url": url
        }
    
    # Generate title
    try:
        if TITLE_GENERATOR_AVAILABLE:
            title = generate_title(data, user_mood)
        else:
            title = fallback_title_generation(data.get("genres", []), user_mood)
        print(f"✓ Generated title: {title}")
    except Exception as e:
        print(f"⚠️ Error generating title: {e}")
        title = fallback_title_generation(data.get("genres", []), user_mood)
        print(f"✓ Using fallback title: {title}")
    
    # Add title to data
    data["title"] = title
    
    # Create image prompt
    try:
        if IMAGE_GENERATOR_AVAILABLE:
            base_image_prompt = create_prompt_from_data(data, user_mood)
        else:
            base_image_prompt = fallback_prompt_generation(data, user_mood)
        
        image_prompt = f"{base_image_prompt}, representing the album '{title}'"
        print(f"Generated image prompt: {image_prompt[:100]}...")
    except Exception as e:
        print(f"⚠️ Error creating image prompt: {e}")
        image_prompt = fallback_prompt_generation(data, user_mood)
    
    # Determine output path
    if not output_path:
        try:
            if UTILS_AVAILABLE:
                img_filename = create_image_filename(title)
            else:
                # Fallback filename creation
                safe_title = "".join(c for c in title if c.isalnum() or c in [' ', '-', '_']).strip()
                safe_title = safe_title.replace(' ', '_')
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                img_filename = f"{timestamp}_{safe_title}.png"
            
            output_path = COVERS_DIR / img_filename
        except Exception as e:
            print(f"⚠️ Error creating filename: {e}")
            output_path = COVERS_DIR / f"cover_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    
    # Make sure the output directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Process LoRA input
    lora = None
    lora_name = ""
    lora_type = "none"
    lora_url = ""
    
    if lora_input and UTILS_AVAILABLE:
        try:
            if isinstance(lora_input, str):
                lora_input = lora_input.strip()
                
                # Find in available LoRAs
                available_loras = get_available_loras()
                for available_lora in available_loras:
                    if available_lora.name == lora_input:
                        lora = available_lora.__dict__
                        lora_name = available_lora.name
                        lora_type = available_lora.source_type
                        break
                        
                if not lora:
                    lora = lora_input
                    lora_name = lora_input
                    lora_type = "local"
            else:
                # Assume it's already a LoraModel
                lora = lora_input
                if hasattr(lora_input, 'name'):
                    lora_name = lora_input.name
                    lora_type = lora_input.source_type
                elif isinstance(lora_input, dict):
                    lora_name = lora_input.get('name', '')
                    lora_type = lora_input.get('source_type', 'local')
        except Exception as e:
            print(f"⚠️ Error processing LoRA input: {e}")
            lora = None
            lora_name = ""
    
    # Generate cover image
    try:
        if IMAGE_GENERATOR_AVAILABLE:
            image_result = generate_cover_image(image_prompt, lora, output_path, negative_prompt)
        else:
            print("⚠️ Image generator not available, creating fallback image")
            image_result = create_fallback_image(output_path, title)
        
        if image_result is None or (isinstance(image_result, bool) and not image_result):
            print("⚠️ Image generation failed, creating fallback")
            image_result = create_fallback_image(output_path, title)
            
    except Exception as e:
        print(f"❌ Error generating image: {e}")
        image_result = create_fallback_image(output_path, title)
    
    # Process the image result
    try:
        if hasattr(image_result, 'mode'):  # It's a PIL Image
            image = image_result
        else:
            # Try to load image from file
            if os.path.exists(output_path):
                image = Image.open(output_path)
            else:
                # Create a basic fallback
                image = create_fallback_image(output_path, title)
        
        # Convert image to base64
        buffered = io.BytesIO()
        image.save(buffered, format="PNG")
        img_base64 = base64.b64encode(buffered.getvalue()).decode()
        
    except Exception as e:
        print(f"❌ Error processing image: {e}")
        return {"error": f"Failed to process generated image: {str(e)}"}
    
    # Create result object
    timestamp = str(datetime.datetime.now())
    
    if MODELS_AVAILABLE:
        result = GenerationResult(
            title=title,
            output_path=str(output_path),
            playlist_data=playlist_data,
            user_mood=user_mood,
            lora_name=lora_name,
            lora_type=lora_type,
            lora_url=lora_url,
            timestamp=timestamp
        )
        result_dict = result.to_dict()
    else:
        # Fallback result creation
        result_dict = {
            "title": title,
            "output_path": str(output_path),
            "item_name": data.get("item_name", ""),
            "genres": data.get("genres", []),
            "all_genres": data.get("all_genres", []),
            "style_elements": data.get("style_elements", []),
            "mood": user_mood or "balanced",
            "timestamp": timestamp,
            "spotify_url": url,
            "lora_name": lora_name,
            "lora_type": lora_type,
            "lora_url": lora_url
        }
    
    # Add the base64 data to the result dict
    result_dict["image_data_base64"] = img_base64
    
    # Save data to database with user tracking
    try:
        data_file = save_generation_data_with_user(result_dict, user_id)
        if data_file:
            result_dict["data_file"] = data_file
    except Exception as e:
        print(f"⚠️ Error saving generation data: {e}")
    
    print(f"✅ Successfully generated cover: {title}")
    return result_dict