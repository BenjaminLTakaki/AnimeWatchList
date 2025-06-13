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

# Monitoring and Fault Handling Imports
from .monitoring_system import app_logger, monitor_performance
# from .fault_handling import fault_tolerant_api_call, GracefulDegradation # If needed later

@monitor_performance
def save_generation_data_with_user(data, user_id=None):
    """Save generation data to database with user tracking"""
    try:
        # Import here to avoid circular imports if app calls this,
        # though ideally db operations are further abstracted or use current_app.
        from app import GenerationResultDB, db, app
        
        with app.app_context(): # Ensure app context for db operations
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
            app_logger.info("generation_data_saved_db", result_id=new_result.id, user_id=user_id)
            return str(new_result.id)
    except Exception as e:
        app_logger.error("save_generation_to_db_failed", error=str(e), user_id=user_id, exc_info=True)
        try:
            from config import DATA_DIR # Keep import local if only used here
            import json # Keep import local
            
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_name = "".join(c for c in data.get("item_name", "unknown_item") if c.isalnum() or c in [' ', '-', '_']).strip()
            safe_name = safe_name.replace(' ', '_')
            json_filename = f"{timestamp}_{safe_name}.json"
            
            data_file_path = Path(DATA_DIR) / json_filename
            with open(data_file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            app_logger.info("generation_data_saved_file_fallback", path=str(data_file_path), user_id=user_id)
            return str(data_file_path)
        except Exception as file_error:
            app_logger.error("save_generation_to_file_fallback_failed", error=str(file_error), user_id=user_id, exc_info=True)
            return None

# Removed old monitoring import fallback

@monitor_performance
def generate_cover(url, user_mood=None, lora_input=None, output_path=None, negative_prompt=None, user_id=None):
    """Generate album cover and title from Spotify URL with user tracking"""
    app_logger.info("generate_cover_start", spotify_url=url, user_id=user_id, user_mood=user_mood)
    
    # Extract playlist/album data
    playlist_data = extract_playlist_data(url) # This function should have its own logging/monitoring
    if isinstance(playlist_data, dict) and "error" in playlist_data:
        app_logger.error("playlist_data_extraction_failed", url=url, error=playlist_data["error"])
        return {"error": playlist_data["error"]}
    
    app_logger.info("playlist_data_extracted", item_name=playlist_data.item_name, user_id=user_id)
    app_logger.debug("playlist_genres", genres=playlist_data.genre_analysis.top_genres, user_id=user_id)

    # Convert playlist data to dictionary
    data = playlist_data.to_dict()
    
    # Create image prompt
    base_image_prompt = create_prompt_from_data(data, user_mood)
    
    # Generate title
    title = generate_title(data, user_mood) # This function should have its own logging/monitoring
    app_logger.info("title_generated", title=title, user_id=user_id)
    
    # Add title to data
    data["title"] = title
    
    # Create final image prompt with title
    image_prompt = f"{base_image_prompt}, representing the album '{title}'"
    app_logger.debug("final_image_prompt", prompt=image_prompt, user_id=user_id)
    
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
            app_logger.error("open_generated_image_failed", path=str(output_path), error=str(e), exc_info=True)
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