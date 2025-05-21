import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Base paths - adjusted for the portfolio structure
BASE_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
COVERS_DIR = BASE_DIR / "generated_covers"
DATA_DIR = BASE_DIR / "data"
LORA_DIR = BASE_DIR / "loras"

# Create necessary directories
COVERS_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)
LORA_DIR.mkdir(exist_ok=True)

# LoRA configuration file
LORA_CONFIG_PATH = BASE_DIR / "lora_config.json"

# Spotify API - use environment variables from Render
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
SPOTIFY_REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI", "http://localhost:8888/callback")

# Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1/models/gemini-2.0-flash:generateContent"

# Stability AI API 
STABILITY_API_KEY = os.getenv("STABILITY_API_KEY")
# Stable Diffusion 3.5 Large engine ID
SD_3_5_LARGE_ENGINE = "sd3.5-large"

# Civitai API - for fetching LoRA details
CIVITAI_API_ENABLED = os.getenv("CIVITAI_API_ENABLED", "True").lower() in ("true", "1", "yes")

# Flask configuration
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY")

# Database configuration - use SPOTIFY_DB_URL instead of DATABASE_URL
SPOTIFY_DB_URL = os.getenv('SPOTIFY_DB_URL', 'postgresql://postgres:password@localhost/portfoliodb')

# Default negative prompt for image generation
DEFAULT_NEGATIVE_PROMPT = """
painting, extra fingers, mutated hands, poorly drawn hands, poorly drawn face, deformed, ugly, blurry, bad anatomy, 
bad proportions, extra limbs, cloned face, skinny, glitchy, double torso, extra arms, extra hands, mangled fingers, 
missing lips, ugly face, distorted face, extra legs, anime
"""