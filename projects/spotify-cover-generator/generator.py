import os
import datetime
from pathlib import Path

from spotify_client import extract_playlist_data
from image_generator import create_prompt_from_data, generate_cover_image
from title_generator import generate_title
from chart_generator import generate_genre_chart
from utils import save_generation_data, create_image_filename, get_available_loras
from models import GenerationResult
from config import COVERS_DIR

def generate_cover(url, user_mood=None, lora_input=None, output_path=None, negative_prompt=None):
    """Generate album cover and title from Spotify URL and save data"""
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
    success = generate_cover_image(image_prompt, lora, output_path, negative_prompt)
    
    if not success:
        return {"error": "Failed to generate cover image"}
    
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
    
    # Save data to JSON file
    data_file = save_generation_data(result_dict)
    if data_file:
        result_dict["data_file"] = data_file
    
    return result_dict