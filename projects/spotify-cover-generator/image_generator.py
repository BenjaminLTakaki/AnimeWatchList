import requests
import json
import os
import base64
from PIL import Image, ImageDraw, ImageFont
import io
import time
import random
import ssl
from config import STABILITY_API_KEY, DEFAULT_NEGATIVE_PROMPT, COVERS_DIR

# Monitoring and Fault Handling Imports
from .monitoring_system import app_logger, monitor_api_calls
from .fault_handling import (
    fault_tolerant_api_call,
    GracefulDegradation,
    http_client, # For send_generation_request
    circuit_breakers, # Potentially for http_client if it uses them
    retry_with_exponential_backoff # Potentially for http_client or direct use
)

app_logger.info("Successfully imported monitoring, fault_handling, and config modules in image_generator.")

def create_prompt_from_data(playlist_data, user_mood=None):
    """Create optimized prompt for stable diffusion"""
    genres_str = ", ".join(playlist_data.get("genres", ["various"]))
    mood = playlist_data.get("mood_descriptor", "balanced")
    
    style_elements = playlist_data.get("style_elements", [])
    
    prompt = (
        f"album cover art, {genres_str} music, professional artwork, "
        f"highly detailed, 8k"
    )
    
    # Add user-specified mood as a direct addition to the prompt if provided
    if user_mood:
        prompt += f", {user_mood}"
    
    if style_elements:
        prompt += ", " + ", ".join(style_elements)
    
    return prompt

def send_generation_request(url, params):
    """Send request to Stability API using http_client with multipart/form-data."""
    if not STABILITY_API_KEY:
        app_logger.error("stability_api_key_missing")
        return None
        
    headers = {
        "Authorization": f"Bearer {STABILITY_API_KEY}",
        "Accept": "application/json"
        # Content-Type is usually set automatically by requests/http_client for multipart
    }
    
    # Convert params to multipart/form-data format for http_client's 'files' parameter
    # http_client expects 'files' in a format like {'fieldname': (filename, data, content_type)}
    # For simple key-value text parameters as multipart, it's often {'fieldname': (None, value_str)}
    files_for_upload = {}
    for key, value in params.items():
        if isinstance(value, (int, float)):
            files_for_upload[key] = (None, str(value))
        elif isinstance(value, str):
            files_for_upload[key] = (None, value)
        else:
            # If there are other types (like actual files), they need specific handling
            app_logger.warning("unhandled_param_type_in_send_generation_request", param_key=key, param_type=type(value))
            files_for_upload[key] = (None, str(value)) # Default to string conversion

    try:
        # http_client is expected to handle retries, timeouts, and SSL issues internally
        response = http_client.request(
            method='POST',
            url=url,
            headers=headers,
            files=files_for_upload # Use 'files' for multipart/form-data
        )
        
        # http_client.request should raise an exception for HTTP errors (4xx, 5xx) by default
        # or return a response object that can be checked. Assuming it raises for now.
        # If not, manual status code check is needed:
        if response.status_code != 200:
            app_logger.error("stability_api_error_status",
                             status_code=response.status_code,
                             response_text=response.text,
                             url=url)
            return None # Or raise an exception to be caught by fault_tolerant_api_call

        return response.json()
    
    except Exception as e:
        # This will catch exceptions from http_client (e.g., connection, timeout, non-2xx if configured to raise)
        app_logger.error("send_generation_request_exception",
                         error=str(e),
                         url=url,
                         exc_info=True) # exc_info=True logs stack trace
        return None

@fault_tolerant_api_call("stability_api", fallback_func=GracefulDegradation.handle_stability_failure)
# @monitor_api_calls("stability") # This is often bundled into fault_tolerant_api_call or http_client logging
def generate_cover_image(prompt, lora=None, output_path=None, negative_prompt=None):
    """Generate album cover image using Stability AI SD 3.5 Large API"""
    # Check if we have API key
    if not STABILITY_API_KEY:
        app_logger.error("stability_api_key_missing_in_generate_cover_image")
        return create_placeholder_image(output_path, "Stability API key missing.")
    
    app_logger.info("generate_cover_image_start", input_prompt=prompt, lora=lora, output_path=str(output_path))
    
    # If no custom negative prompt is provided, use the default
    if negative_prompt is None or negative_prompt.strip() == "":
        negative_prompt = DEFAULT_NEGATIVE_PROMPT
    
    # Check if we have a LoRA model
    if lora:
        lora_prompt = ""
        if isinstance(lora, dict):
            lora_name = lora.get("name", "")
            trigger_words = lora.get("trigger_words", [])
            
            # Add trigger words to the prompt
            if trigger_words:
                lora_prompt = ", ".join(trigger_words)
            else:
                lora_prompt = f"in the style of {lora_name}"
        else:
            # If it's just a string, use it as a style reference
            lora_prompt = f"in the style of {lora}"
        
        if lora_prompt:
            prompt = f"{prompt}, {lora_prompt}"
            app_logger.info("prompt_enhanced_with_lora", final_prompt=prompt)
    
    url = "https://api.stability.ai/v2beta/stable-image/generate/sd3"
    
    seed = random.randint(1, 1000000)
    
    # Prepare parameters for the API
    params = {
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "aspect_ratio": "1:1",  # Square aspect ratio for album covers
        "seed": seed,
        "output_format": "png",
        "model": "sd3.5-large",  # Using the flagship model
        "mode": "text-to-image"
    }
    
    try:
        # Send the request
        response_data = send_generation_request(url, params)
        
        # Check if we got a valid response
        if not response_data:
            # Try with backup URL if the main one fails
            backup_url = "https://api.stability.ai/v1/generation/stable-diffusion-v1-5/text-to-image" # SD 1.5, different API
            app_logger.warning("stability_main_api_failed_trying_backup", main_api_url=url)
            
            # Adjust parameters for backup API if needed (SD 1.5 takes different params)
            # This backup logic might need to be more robust or use a different fault_tolerant_api_call
            # as it's a different API endpoint with different expected request/response.
            # For now, just logging and proceeding with existing logic.
            backup_params = {
                "text_prompts": [{"text": prompt}],
                "height": 512,
                "width": 512,
                "samples": 1,
                "steps": 30,
            }
            
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Bearer {STABILITY_API_KEY}"
            }
            
            try:
                response = requests.post(
                    backup_url,
                    headers=headers,
                    json=backup_params,
                    timeout=60
                )
                
                if response.status_code != 200:
                    app_logger.error("stability_backup_api_error",
                                     status_code=response.status_code,
                                     response_text=response.text,
                                     url=backup_url)
                    return create_placeholder_image(output_path, "Backup API failed.")
                
                response_data = response.json()
                
                # Extract image from backup API response
                if "artifacts" in response_data and len(response_data["artifacts"]) > 0:
                    image_base64 = response_data["artifacts"][0]["base64"]
                    image_bytes = response_data["artifacts"][0]["base64"]
                    
                    # Create image from bytes
                    image = Image.open(io.BytesIO(image_bytes))
                    
                    # Save image if output path is specified
                    if output_path:
                        # Make sure directory exists
                        os.makedirs(os.path.dirname(str(output_path)), exist_ok=True)
                        image.save(output_path)
                        app_logger.info("image_saved_from_backup_api", path=str(output_path))
                    
                    return image
                else:
                    app_logger.warning("no_image_data_in_backup_api_response", response_keys=list(response_data.keys()))
                    return create_placeholder_image(output_path, "Backup API returned no image.")
            
            except Exception as e:
                app_logger.error("stability_backup_api_exception", error=str(e), exc_info=True)
                return create_placeholder_image(output_path, "Backup API exception.")
            
        # Extract image data from main API response
        if "image" in response_data:
            image_base64 = response_data["image"]
            image_bytes = base64.b64decode(image_base64)
            
            # Create image from bytes
            image = Image.open(io.BytesIO(image_bytes))
            
            # Save image if output path is specified
            if output_path:
                # Make sure directory exists
                os.makedirs(os.path.dirname(str(output_path)), exist_ok=True)
                image.save(output_path)
                app_logger.info("image_saved_from_main_api", path=str(output_path))
            
            return image
        else:
            app_logger.warning("no_image_data_in_main_api_response", response_keys=list(response_data.keys()))
            # Log more details for debugging if needed, e.g. response_data itself if not too large
            return create_placeholder_image(output_path, "Main API returned no image.")
            
    except Exception as e:
        app_logger.error("generate_cover_image_exception", error=str(e), exc_info=True)
        return create_placeholder_image(output_path, "General exception in image generation.")

def create_placeholder_image(output_path=None, reason="Image generation failed."):
    """Create a placeholder image when generation fails"""
    app_logger.info("creating_placeholder_image", reason=reason, output_path=str(output_path))
    try:
        # Create a placeholder image
        width, height = 512, 512
        image = Image.new('RGB', (width, height), color='#3A506B')
        
        # Add text to the placeholder image
        draw = ImageDraw.Draw(image)
        
        # Try to load a font, use default if not available
        try:
            font = ImageFont.truetype("arial.ttf", 20)
        except:
            font = ImageFont.load_default()
        
        # Draw message
        draw.text((20, 240), "Image Generation Failed", fill="white", font=font)
        draw.text((20, 270), "Using placeholder image", fill="white", font=font)
        
        # Save if output path is specified
        if output_path:
            # Make sure directory exists
            os.makedirs(os.path.dirname(str(output_path)), exist_ok=True)
            image.save(output_path)
            app_logger.info("placeholder_image_saved", path=str(output_path))
        
        return image
    except Exception as draw_error:
        app_logger.error("create_placeholder_image_failed", error=str(draw_error), exc_info=True)
        # Return a minimal image if even the placeholder creation fails
        return Image.new('RGB', (512, 512), color='#FF0000') # Basic fallback