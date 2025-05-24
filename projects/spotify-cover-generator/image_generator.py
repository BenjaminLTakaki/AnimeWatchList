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
    """Send request to Stability API using multipart/form-data with SSL error handling"""
    if not STABILITY_API_KEY:
        print("ERROR: Missing Stability API key. Please set STABILITY_API_KEY in your .env file.")
        return None
        
    headers = {
        "Authorization": f"Bearer {STABILITY_API_KEY}",
        "Accept": "application/json"
    }
    
    # Convert params to multipart/form-data format
    files = {}
    for key, value in params.items():
        if isinstance(value, (int, float)):
            value = str(value)
        files[key] = (None, value)
    
    try:
        # Configure SSL context to try different protocols and ciphers
        session = requests.Session()
        # Retry mechanism
        retries = 3
        for attempt in range(retries):
            try:
                response = session.post(url, files=files, headers=headers, timeout=60)
                break
            except (requests.exceptions.SSLError, ssl.SSLError) as e:
                if "DECRYPTION_FAILED_OR_BAD_RECORD_MAC" in str(e):
                    print(f"SSL Error: {e}. Attempt {attempt+1}/{retries}")
                    if attempt < retries - 1:
                        time.sleep(2)  # Wait before retrying
                        continue
                    else:
                        raise Exception(f"SSL Error after {retries} attempts: {e}")
                else:
                    raise
            except Exception as e:
                if attempt < retries - 1:
                    print(f"Error during API request: {e}. Retrying {attempt+1}/{retries}")
                    time.sleep(2)
                    continue
                else:
                    raise
        
        if response.status_code != 200:
            print(f"Error: API returned status code {response.status_code}")
            print(f"Response: {response.text}")
            return None
        
        return response.json()
    
    except Exception as e:
        print(f"Error sending request: {e}")
        return None

def generate_cover_image(prompt, lora=None, output_path=None, negative_prompt=None):
    """Generate album cover image using Stability AI SD 3.5 Large API"""
    # Check if we have API key
    if not STABILITY_API_KEY:
        print("ERROR: Missing Stability API key. Please set STABILITY_API_KEY in your .env file.")
        return create_placeholder_image(output_path)
    
    print(f"Generating with prompt: {prompt}")
    
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
            print(f"Enhanced prompt with LoRA context: {prompt}")
    
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
            backup_url = "https://api.stability.ai/v1/generation/stable-diffusion-v1-5/text-to-image"
            print("Main API request failed, trying backup API...")
            
            # Adjust parameters for backup API if needed
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
                    print(f"Backup API error: {response.status_code}")
                    print(f"Response: {response.text}")
                    return create_placeholder_image(output_path)
                
                response_data = response.json()
                
                # Extract image from backup API response
                if "artifacts" in response_data and len(response_data["artifacts"]) > 0:
                    image_base64 = response_data["artifacts"][0]["base64"]
                    image_bytes = base64.b64decode(image_base64)
                    
                    # Create image from bytes
                    image = Image.open(io.BytesIO(image_bytes))
                    
                    # Save image if output path is specified
                    if output_path:
                        # Make sure directory exists
                        os.makedirs(os.path.dirname(str(output_path)), exist_ok=True)
                        image.save(output_path)
                        print(f"Image saved to {output_path} (using backup API)")
                    
                    return image
                else:
                    print("No image data found in backup API response")
                    return create_placeholder_image(output_path)
            
            except Exception as e:
                print(f"Error with backup API: {e}")
                return create_placeholder_image(output_path)
            
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
                print(f"Image saved to {output_path}")
            
            return image
        else:
            print("No image data found in the response.")
            print(f"Response structure: {json.dumps(list(response_data.keys()), indent=2)}")
            return create_placeholder_image(output_path)
            
    except Exception as e:
        print(f"Error generating image: {e}")
        return create_placeholder_image(output_path)

def create_placeholder_image(output_path=None):
    """Create a placeholder image when generation fails"""
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
            print(f"Placeholder image saved to {output_path}")
        
        return image
    except Exception as draw_error:
        print(f"Error creating placeholder image: {draw_error}")
        # Return a minimal image if even the placeholder creation fails
        return Image.new('RGB', (512, 512), color='#FF0000')