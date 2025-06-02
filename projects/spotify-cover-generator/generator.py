# Updated generator.py to include user tracking

import os
import datetime
import base64
import io
from pathlib import Path
from PIL import Image

from spotify_client import extract_playlist_data
from image_generator import create_prompt_from_data, generate_cover_image
from title_generator import generate_title
from chart_generator import generate_genre_chart
from utils import create_image_filename, get_available_loras
from models import GenerationResult
from config import COVERS_DIR

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
                user_id=user_id  # Add user tracking
            )
            
            db.session.add(new_result)
            db.session.commit()
            
            # Return the ID as a string
            return str(new_result.id)
    except Exception as e:
        print(f"Error saving data to database: {e}")
        
        # Fall back to saving to a JSON file if database fails
        try:
            from config import DATA_DIR
            import json
            
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

# Monitoring imports with fallback
try:
    from monitoring_system import monitor_performance
except ImportError:
    def monitor_performance(func):
        return func

@monitor_performance
def generate_cover(url, user_mood=None, lora_input=None, output_path=None, negative_prompt=None, user_id=None):
    """Generate album cover and title from Spotify URL with user tracking"""
    print(f"Processing Spotify URL: {url}")
    
    # Extract playlist/album data
    playlist_data = extract_playlist_data(url)
    if isinstance(playlist_data, dict) and "error" in playlist_data:
        return {"error": playlist_data["error"]}
    
    print(f"\nSuccessfully extracted data for: {playlist_data.item_name}")
    print(f"Top genres identified: {', '.join(playlist_data.genre_analysis.top_genres)}")
    
    # Convert playlist data to dictionary
    data = playlist_data.to_dict()
    
    # Create image prompt
    base_image_prompt = create_prompt_from_data(data, user_mood)
    
    # Generate title
    title = generate_title(data, user_mood)
    print(f"Generated title: {title}")
    
    # Add title to data
    data["title"] = title
    
    # Create final image prompt with title
    image_prompt = f"{base_image_prompt}, representing the album '{title}'"
    print(f"Final image prompt with title: {image_prompt}")
    
    # Determine output path
    if not output_path:
        img_filename = create_image_filename(title)
        output_path = COVERS_DIR / img_filename
    
    # Make sure the output directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Process LoRA input - simplified to only handle local LoRAs
    lora = None
    lora_name = ""
    lora_type = "none"
    lora_url = ""
    
    if lora_input:
        # If it's a string, it could be a local LoRA name
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
                
            # If not found, just use the name
            if not lora:
                lora = lora_input
                lora_name = lora_input
                lora_type = "local"
        else:
            # Assume it's already a LoraModel
            lora = lora_input
            if hasattr(lora_input, 'name'):
                # It's a LoraModel
                lora_name = lora_input.name
                lora_type = lora_input.source_type
            elif isinstance(lora_input, dict):
                # It's a dict
                lora_name = lora_input.get('name', '')
                lora_type = lora_input.get('source_type', 'local')
    
    # Generate cover image with the custom negative prompt if provided
    image_result = generate_cover_image(image_prompt, lora, output_path, negative_prompt)
    
    if image_result is None or (isinstance(image_result, bool) and not image_result):
        return {"error": "Failed to generate cover image"}
    
    # Check if image_result is a PIL Image or a boolean success value
    if hasattr(image_result, 'mode'):  # It's a PIL Image
        image = image_result
    else:
        # It's a success boolean, so load image from file
        try:
            image = Image.open(output_path)
        except Exception as e:
            print(f"Error opening generated image: {e}")
            return {"error": f"Failed to process generated image: {str(e)}"}
    
    # Convert image to base64 for embedding in HTML
    buffered = io.BytesIO()
    image.save(buffered, format="PNG")
    img_base64 = base64.b64encode(buffered.getvalue()).decode()
    
    # Current timestamp
    timestamp = str(datetime.datetime.now())
    
    # Create result object
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
    
    # Convert to dict for saving
    result_dict = result.to_dict()
    
    # Add the base64 data to the result dict
    result_dict["image_data_base64"] = img_base64
    
    # Save data to database with user tracking
    data_file = save_generation_data_with_user(result_dict, user_id)
    if data_file:
        result_dict["data_file"] = data_file
    
    return result_dict