import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
import tempfile

# Base paths - adjusted for Render deployment
BASE_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
COVERS_DIR = BASE_DIR / "generated_covers"
DATA_DIR = BASE_DIR / "data"

# For Render deployment - use temp directory for file uploads
if os.getenv("RENDER"):
    # On Render, use /tmp for temporary file storage
    TEMP_DIR = Path("/tmp")
    LORA_DIR = TEMP_DIR / "loras"
else:
    # Local development
    LORA_DIR = BASE_DIR / "loras"

# Create necessary directories
COVERS_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)
LORA_DIR.mkdir(exist_ok=True)

# Spotify API - use environment variables from Render
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")

# Dynamic redirect URI based on environment - FIXED
if os.getenv("RENDER"):
    # Production on Render - CORRECTED PATH
    SPOTIFY_REDIRECT_URI = "https://www.benjamintakaki.com/spotify/spotify-callback"
elif os.getenv("DEVELOPMENT") or not os.getenv("RENDER"):
    # Local development - CORRECTED PATH
    SPOTIFY_REDIRECT_URI = "http://localhost:5000/spotify/spotify-callback"
else:
    # Fallback
    SPOTIFY_REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI", "https://www.benjamintakaki.com/spotify/spotify-callback")

print(f"🔗 Using Spotify redirect URI: {SPOTIFY_REDIRECT_URI}")

# Also update any other config that might affect routing
BASE_URL = os.getenv("BASE_URL", "https://www.benjamintakaki.com" if os.getenv("RENDER") else "http://localhost:5000")
SPOTIFY_BASE_URL = f"{BASE_URL}/spotify"

# Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1/models/gemini-2.0-flash:generateContent"

# Stability AI API 
STABILITY_API_KEY = os.getenv("STABILITY_API_KEY")
SD_3_5_LARGE_ENGINE = "sd3.5-large"

# Flask configuration
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY")

# FIXED: Use single database URL for everything (Render-optimized)
# Render provides DATABASE_URL automatically
MAIN_DB_URL = os.getenv('DATABASE_URL')

if not MAIN_DB_URL:
    # Fallback for local development
    MAIN_DB_URL = 'postgresql://postgres:password@localhost/portfoliodb'
    print("⚠️ No DATABASE_URL found, using local fallback")
else:
    print(f"✅ Found DATABASE_URL from Render environment")

# Fix for Render's DATABASE_URL format (starts with postgres:// instead of postgresql://)
if MAIN_DB_URL and MAIN_DB_URL.startswith('postgres://'):
    MAIN_DB_URL = MAIN_DB_URL.replace('postgres://', 'postgresql://', 1)

# Use the same database for everything
SPOTIFY_DB_URL = MAIN_DB_URL

print(f"🔗 Using database: {MAIN_DB_URL[:50]}...")

# Default negative prompt
DEFAULT_NEGATIVE_PROMPT = """
painting, extra fingers, mutated hands, poorly drawn hands, poorly drawn face, deformed, ugly, blurry, bad anatomy, 
bad proportions, extra limbs, cloned face, skinny, glitchy, double torso, extra arms, extra hands, mangled fingers, 
missing lips, ugly face, distorted face, extra legs, anime
"""