import requests
import json
import os
import base64
from PIL import Image, ImageDraw, ImageFont
import io
import time
import random
import ssl
import tempfile

# Import config with fallback
try:
    from config import STABILITY_API_KEY, DEFAULT_NEGATIVE_PROMPT, COVERS_DIR
    CONFIG_AVAILABLE = True
except ImportError:
    print("⚠️ Config import failed, using environment variables")
    CONFIG_AVAILABLE = False
    STABILITY_API_KEY = os.environ.get('STABILITY_API_KEY')
    DEFAULT_NEGATIVE_PROMPT = """
    painting, extra fingers, mutated hands, poorly drawn hands, poorly drawn face, deformed, ugly, blurry, bad anatomy, 
    bad proportions, extra limbs, cloned face, skinny, glitchy, double torso, extra arms, extra hands, mangled fingers, 
    missing lips, ugly face, distorted face, extra legs, anime
    """
    COVERS_DIR = os.path.join(os.path.dirname(__file__), "generated_covers")

# Monitoring imports with fallback
try:
    from monitoring_system import monitor_api_calls
    from fault_handling import fault_tolerant_api_call
    MONITORING_AVAILABLE = True
except ImportError:
    MONITORING_AVAILABLE = False
    def monitor_api_calls(service_name):
        def decorator(func):
            return func
        return decorator
    def fault_tolerant_api_call(service_name, fallback_func=None):
        def decorator(func):
            return func
        return decorator

def create_prompt_from_data(playlist_data, user_mood=None):
    """Create optimized prompt for stable diffusion with fallback handling"""
    try:
        # Handle both dict and object inputs
        if isinstance(playlist_data, dict):
            genres = playlist_data.get("genres", ["various"])
            mood = playlist_data.get("mood_descriptor", "balanced")
            style_elements = playlist_data.get("style_elements", [])
        else:
            # Assume it's a PlaylistData object
            genres = getattr(playlist_data, 'genres', ["various"])
            mood = getattr(playlist_data, 'mood_descriptor', "balanced")
            style_elements = getattr(playlist_data, 'style_elements', [])
        
        genres_str = ", ".join(genres) if genres else "music"
        
        prompt = (
            f"album cover art, {genres_str} music, professional artwork, "
            f"highly detailed, 8k resolution, modern design"
        )
        
        # Add user-specified mood as a direct addition to the prompt if provided
        if user_mood and user_mood.strip():
            prompt += f", {user_mood.strip()}"
        
        if style_elements:
            prompt += ", " + ", ".join(style_elements)
        
        return prompt
        
    except Exception as e:
        print(f"⚠️ Error creating prompt: {e}")
        # Fallback prompt
        return "album cover art, music, professional artwork, highly detailed, modern design"

def create_robust_session():
    """Create a requests session with proper SSL and retry configuration"""
    session = requests.Session()
    
    # Configure retries
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    
    retry_strategy = Retry(
        total=3,
        status_forcelist=[429, 500, 502, 503, 504],
        method_whitelist=["HEAD", "GET", "POST"],
        backoff_factor=1
    )
    
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    return session

def send_generation_request(url, params, max_retries=3):
    """Send request to Stability API with comprehensive error handling"""
    if not STABILITY_API_KEY:
        print("❌ Missing Stability API key. Please set STABILITY_API_KEY in your environment variables.")
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
    
    session = create_robust_session()
    
    for attempt in range(max_retries):
        try:
            print(f"🎨 Attempting image generation (attempt {attempt + 1}/{max_retries})...")
            
            response = session.post(
                url, 
                files=files, 
                headers=headers, 
                timeout=90  # Increased timeout for image generation
            )
            
            print(f"📡 API Response Status: {response.status_code}")
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 429:
                print("⚠️ Rate limit hit, waiting before retry...")
                time.sleep(10 * (attempt + 1))  # Exponential backoff
                continue
            elif response.status_code == 400:
                print(f"❌ Bad request: {response.text}")
                return None
            elif response.status_code == 401:
                print("❌ Unauthorized - check your API key")
                return None
            elif response.status_code == 402:
                print("❌ Insufficient credits")
                return None
            else:
                print(f"⚠️ API error {response.status_code}: {response.text}")
                if attempt < max_retries - 1:
                    time.sleep(5 * (attempt + 1))
                    continue
                return None
                
        except requests.exceptions.SSLError as e:
            print(f"⚠️ SSL Error on attempt {attempt + 1}: {e}")
            if attempt < max_retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            else:
                print("❌ SSL Error after all retries")
                return None
                
        except requests.exceptions.Timeout as e:
            print(f"⚠️ Timeout on attempt {attempt + 1}: {e}")
            if attempt < max_retries - 1:
                time.sleep(5 * (attempt + 1))
                continue
            else:
                print("❌ Timeout after all retries")
                return None
                
        except Exception as e:
            print(f"⚠️ Unexpected error on attempt {attempt + 1}: {e}")
            if attempt < max_retries - 1:
                time.sleep(3 * (attempt + 1))
                continue
            else:
                print("❌ Failed after all retries")
                return None
    
    return None

def try_backup_stability_api(prompt, negative_prompt):
    """Try the backup Stability API endpoint"""
    print("🔄 Trying backup Stability API...")
    
    backup_url = "https://api.stability.ai/v1/generation/stable-diffusion-v1-5/text-to-image"
    
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {STABILITY_API_KEY}"
    }
    
    backup_params = {
        "text_prompts": [
            {"text": prompt, "weight": 1.0},
            {"text": negative_prompt, "weight": -1.0}
        ],
        "height": 512,
        "width": 512,
        "samples": 1,
        "steps": 30,
        "cfg_scale": 7,
        "sampler": "K_DPM_2_ANCESTRAL"
    }
    
    try:
        session = create_robust_session()
        response = session.post(
            backup_url,
            headers=headers,
            json=backup_params,
            timeout=90
        )
        
        if response.status_code == 200:
            response_data = response.json()
            
            if "artifacts" in response_data and len(response_data["artifacts"]) > 0:
                image_base64 = response_data["artifacts"][0]["base64"]
                image_bytes = base64.b64decode(image_base64)
                image = Image.open(io.BytesIO(image_bytes))
                print("✅ Backup API generation successful")
                return image
            else:
                print("❌ No image data in backup API response")
                return None
        else:
            print(f"❌ Backup API error: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ Backup API failed: {e}")
        return None

@monitor_api_calls("stability")
@fault_tolerant_api_call("stability")
def generate_cover_image(prompt, lora=None, output_path=None, negative_prompt=None):
    """Generate album cover image using Stability AI with comprehensive fallbacks"""
    
    # Validate API key
    if not STABILITY_API_KEY:
        print("❌ Missing Stability API key")
        return create_placeholder_image(output_path, "API Key Missing")
    
    print(f"🎨 Generating with prompt: {prompt[:100]}...")
    
    # Set default negative prompt if none provided
    if negative_prompt is None or negative_prompt.strip() == "":
        negative_prompt = DEFAULT_NEGATIVE_PROMPT
    
    # Process LoRA if provided
    enhanced_prompt = prompt
    if lora:
        lora_prompt = ""
        if isinstance(lora, dict):
            lora_name = lora.get("name", "")
            trigger_words = lora.get("trigger_words", [])
            
            if trigger_words:
                lora_prompt = ", ".join(trigger_words)
            else:
                lora_prompt = f"in the style of {lora_name}"
        else:
            lora_prompt = f"in the style of {lora}"
        
        if lora_prompt:
            enhanced_prompt = f"{prompt}, {lora_prompt}"
            print(f"🎭 Enhanced prompt with LoRA: {enhanced_prompt[:100]}...")
    
    # Try main Stability API first
    main_url = "https://api.stability.ai/v2beta/stable-image/generate/sd3"
    
    seed = random.randint(1, 1000000)
    
    params = {
        "prompt": enhanced_prompt,
        "negative_prompt": negative_prompt,
        "aspect_ratio": "1:1",
        "seed": seed,
        "output_format": "png",
        "model": "sd3.5-large",
        "mode": "text-to-image"
    }
    
    try:
        print("🚀 Attempting main Stability API...")
        response_data = send_generation_request(main_url, params)
        
        if response_data and "image" in response_data:
            try:
                image_base64 = response_data["image"]
                image_bytes = base64.b64decode(image_base64)
                image = Image.open(io.BytesIO(image_bytes))
                
                # Save image if output path is specified
                if output_path:
                    os.makedirs(os.path.dirname(str(output_path)), exist_ok=True)
                    image.save(output_path)
                    print(f"✅ Image saved to {output_path}")
                
                return image
                
            except Exception as e:
                print(f"❌ Error processing main API response: {e}")
        
        # Try backup API
        print("🔄 Main API failed, trying backup...")
        backup_image = try_backup_stability_api(enhanced_prompt, negative_prompt)
        
        if backup_image:
            if output_path:
                os.makedirs(os.path.dirname(str(output_path)), exist_ok=True)
                backup_image.save(output_path)
                print(f"✅ Backup image saved to {output_path}")
            return backup_image
        
        # If both APIs fail, create placeholder
        print("❌ Both APIs failed, creating placeholder")
        return create_placeholder_image(output_path, "Generation Failed")
        
    except Exception as e:
        print(f"❌ Unexpected error in image generation: {e}")
        return create_placeholder_image(output_path, "Unexpected Error")

def create_placeholder_image(output_path=None, reason="Generation Failed"):
    """Create a professional-looking placeholder image when generation fails"""
    try:
        print(f"🎨 Creating placeholder image: {reason}")
        
        # Create image with better design
        width, height = 512, 512
        
        # Create gradient background
        image = Image.new('RGB', (width, height), color='#1a1a1a')
        draw = ImageDraw.Draw(image)
        
        # Create a subtle gradient effect
        for y in range(height):
            alpha = int(255 * (1 - y / height) * 0.3)
            color = (26 + alpha, 26 + alpha, 26 + alpha)
            draw.line([(0, y), (width, y)], fill=color)
        
        # Try to load fonts
        try:
            title_font = ImageFont.truetype("arial.ttf", 32)
            subtitle_font = ImageFont.truetype("arial.ttf", 18)
            small_font = ImageFont.truetype("arial.ttf", 14)
        except:
            try:
                title_font = ImageFont.load_default()
                subtitle_font = ImageFont.load_default()
                small_font = ImageFont.load_default()
            except:
                title_font = None
                subtitle_font = None
                small_font = None
        
        # Draw main content
        if title_font:
            # Main title
            title_text = "Album Cover"
            title_bbox = draw.textbbox((0, 0), title_text, font=title_font)
            title_width = title_bbox[2] - title_bbox[0]
            title_x = (width - title_width) // 2
            draw.text((title_x, 180), title_text, fill="#1DB954", font=title_font)
            
            # Subtitle
            subtitle_text = "Generation in Progress"
            if "Failed" in reason or "Error" in reason:
                subtitle_text = "Generation Unavailable"
            
            subtitle_bbox = draw.textbbox((0, 0), subtitle_text, font=subtitle_font)
            subtitle_width = subtitle_bbox[2] - subtitle_bbox[0]
            subtitle_x = (width - subtitle_width) // 2
            draw.text((subtitle_x, 230), subtitle_text, fill="#ffffff", font=subtitle_font)
            
            # Status message
            status_text = "Please try again later"
            if small_font:
                status_bbox = draw.textbbox((0, 0), status_text, font=small_font)
                status_width = status_bbox[2] - status_bbox[0]
                status_x = (width - status_width) // 2
                draw.text((status_x, 270), status_text, fill="#cccccc", font=small_font)
        
        # Add some geometric elements for visual appeal
        # Draw circles
        for i in range(3):
            center_x = width // 2
            center_y = 120
            radius = 20 + i * 15
            draw.ellipse([
                center_x - radius, center_y - radius,
                center_x + radius, center_y + radius
            ], outline="#1DB954", width=2)
        
        # Draw lines for texture
        for i in range(0, width, 40):
            draw.line([(i, 0), (i, height)], fill="#2a2a2a", width=1)
        for i in range(0, height, 40):
            draw.line([(0, i), (width, i)], fill="#2a2a2a", width=1)
        
        # Save the placeholder if path provided
        if output_path:
            try:
                os.makedirs(os.path.dirname(str(output_path)), exist_ok=True)
                image.save(output_path)
                print(f"📁 Placeholder saved to {output_path}")
            except Exception as save_error:
                print(f"⚠️ Could not save placeholder: {save_error}")
        
        return image
        
    except Exception as e:
        print(f"❌ Error creating placeholder image: {e}")
        # Ultimate fallback - solid color image
        try:
            fallback_image = Image.new('RGB', (512, 512), color='#2a2a2a')
            if output_path:
                fallback_image.save(output_path)
            return fallback_image
        except:
            return None

def test_stability_api():
    """Test Stability API functionality"""
    print("🧪 Testing Stability API...")
    
    if not STABILITY_API_KEY:
        print("❌ No API key configured")
        return False
    
    # Test with a simple prompt
    test_prompt = "album cover art, simple geometric design, minimalist"
    test_path = os.path.join(COVERS_DIR, "test_image.png")
    
    try:
        result = generate_cover_image(test_prompt, output_path=test_path)
        
        if result and hasattr(result, 'mode'):  # PIL Image
            print("✅ Stability API test successful")
            return True
        else:
            print("⚠️ Stability API returned placeholder")
            return False
            
    except Exception as e:
        print(f"❌ Stability API test failed: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Testing image generator standalone...")
    
    # Create test directory
    os.makedirs(COVERS_DIR, exist_ok=True)
    
    if test_stability_api():
        print("✅ Image generator tests passed")
    else:
        print("❌ Image generator tests failed")