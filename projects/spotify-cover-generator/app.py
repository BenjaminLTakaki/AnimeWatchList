import os
import sys
import random
import json
import datetime
from flask import Flask, request, render_template, send_from_directory, jsonify, session
from pathlib import Path
from urllib.parse import urlparse

# Import app modules
from spotify_client import initialize_spotify
from generator import generate_cover
from chart_generator import generate_genre_chart
from models import PlaylistData, GenreAnalysis, LoraModel
from utils import generate_random_string, get_available_loras
from config import BASE_DIR, COVERS_DIR, FLASK_SECRET_KEY, SPOTIFY_DB_URL
from flask_sqlalchemy import SQLAlchemy
from contextlib import contextmanager

# Initialize SQLAlchemy
db = SQLAlchemy()

# Define database models for the app
class LoraModelDB(db.Model):
    __tablename__ = 'spotify_lora_models'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    source_type = db.Column(db.String(20), default='local')  # 'local' or 'link'
    path = db.Column(db.String(500), default='')
    url = db.Column(db.String(500), default='')
    trigger_words = db.Column(db.JSON, default=list)
    strength = db.Column(db.Float, default=0.7)
    
    def to_lora_model(self):
        """Convert DB model to LoraModel object"""
        return LoraModel(
            name=self.name,
            source_type=self.source_type,
            path=self.path,
            url=self.url,
            trigger_words=self.trigger_words or [],
            strength=self.strength
        )

class GenerationResultDB(db.Model):
    __tablename__ = 'spotify_generation_results'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    output_path = db.Column(db.String(500), nullable=False)
    item_name = db.Column(db.String(200))
    genres = db.Column(db.JSON)
    all_genres = db.Column(db.JSON)
    style_elements = db.Column(db.JSON)
    mood = db.Column(db.String(50))
    energy_level = db.Column(db.String(50))
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())
    spotify_url = db.Column(db.String(500))
    lora_name = db.Column(db.String(100))
    lora_type = db.Column(db.String(20))
    lora_url = db.Column(db.String(500))

# Initialize Flask app
app = Flask(__name__, template_folder=str(BASE_DIR / "templates"), static_folder=str(BASE_DIR / "static"))
app.secret_key = FLASK_SECRET_KEY or generate_random_string(24)

# Global initialization flag
initialized = False

def initialize_app():
    """Initialize the application's dependencies"""
    global initialized
    
    # Configure database using SPOTIFY_DB_URL from config
    app.config['SQLALCHEMY_DATABASE_URI'] = SPOTIFY_DB_URL
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Initialize database
    db.init_app(app)
    
    # Create tables if they don't exist
    with app.app_context():
        db.create_all()
    
    # Initialize Spotify client
    spotify_initialized = initialize_spotify()
    
    # Check all required environment variables
    from config import SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, GEMINI_API_KEY, STABILITY_API_KEY
    env_vars_present = all([
        SPOTIFY_CLIENT_ID, 
        SPOTIFY_CLIENT_SECRET, 
        GEMINI_API_KEY, 
        STABILITY_API_KEY
    ])
    
    if not env_vars_present:
        missing = []
        if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
            missing.append("Spotify API credentials")
        if not GEMINI_API_KEY:
            missing.append("Gemini API key")
        if not STABILITY_API_KEY:
            missing.append("Stable Diffusion API key")
        print(f"⚠️ Missing environment variables: {', '.join(missing)}")
    
    initialized = spotify_initialized and env_vars_present
    return initialized

def calculate_genre_percentages(genres_list):
    """Calculate percentage distribution of genres"""
    if not genres_list:
        return []
    
    # Use GenreAnalysis to calculate percentages
    genre_analysis = GenreAnalysis.from_genre_list(genres_list)
    return genre_analysis.get_percentages(max_genres=5)

# Routes
@app.route("/", methods=["GET", "POST"])
def index():
    """Main route for the application"""
    global initialized
    
    # Ensure app is initialized
    if not initialized:
        if initialize_app():
            print("Application initialized successfully")
        else:
            print("Failed to initialize application")
    
    # Get available LoRAs
    loras = get_available_loras()
    
    if request.method == "POST":
        try:
            playlist_url = request.form.get("playlist_url")
            user_mood = request.form.get("mood", "").strip()
            negative_prompt = request.form.get("negative_prompt", "").strip()
            
            # Handle LoRA selection - only from dropdown now
            lora_name = request.form.get("lora_name", "").strip()
            
            # Determine which LoRA to use
            lora_input = None
            if lora_name and lora_name != "none":
                # Using a saved LoRA from the dropdown
                for lora in loras:
                    if lora.name == lora_name:
                        lora_input = lora
                        break
            
            if not playlist_url:
                return render_template(
                    "index.html", 
                    error="Please enter a Spotify playlist or album URL.",
                    loras=loras
                )
            
            # Generate cover
            result = generate_cover(playlist_url, user_mood, lora_input, negative_prompt=negative_prompt)
            
            # Handle errors
            if "error" in result:
                return render_template(
                    "index.html", 
                    error=result["error"],
                    loras=loras
                )
            
            # Get the filename part from the full path
            img_filename = os.path.basename(result["output_path"])
            
            # Generate genre chart
            genres_chart = generate_genre_chart(result.get("all_genres", []))
            
            # Calculate genre percentages for visualization
            genre_percentages = calculate_genre_percentages(result.get("all_genres", []))
            
            # Data for display
            display_data = {
                "title": result["title"],
                "image_file": img_filename,
                "genres": ", ".join(result.get("genres", [])),
                "mood": result.get("mood", ""),
                "playlist_name": result.get("item_name", "Your Music"),
                "found_genres": bool(result.get("genres", [])),
                "genres_chart": genres_chart,
                "genre_percentages": genre_percentages,
                "playlist_url": playlist_url,
                "user_mood": user_mood,
                "negative_prompt": negative_prompt,
                "lora_name": result.get("lora_name", ""),
                "lora_type": result.get("lora_type", ""),
                "lora_url": result.get("lora_url", "")
            }
            
            return render_template("result.html", **display_data)
        except Exception as e:
            print(f"Server error processing request: {e}")
            return render_template(
                "index.html", 
                error=f"An error occurred: {str(e)}",
                loras=loras
            )
    else:
        return render_template("index.html", loras=loras)

@app.route("/generated_covers/<path:filename>")
def serve_image(filename):
    """Serve generated images"""
    return send_from_directory(COVERS_DIR, filename)

@app.route("/status")
def status():
    """API endpoint to check system status"""
    # Check if Spotify is initialized
    from spotify_client import sp
    
    return jsonify({
        "initialized": initialized,
        "spotify_working": sp is not None,
        "loras_available": len(get_available_loras())
    })

@app.route("/api/generate", methods=["POST"])
def api_generate():
    """API endpoint to generate covers programmatically"""
    try:
        data = request.json
        if not data or "spotify_url" not in data:
            return jsonify({"error": "Missing spotify_url in request"}), 400
            
        spotify_url = data.get("spotify_url")
        user_mood = data.get("mood", "")
        negative_prompt = data.get("negative_prompt", "")
        
        # Handle LoRA - simplified to only use name
        lora_name = data.get("lora_name", "")
        
        # Determine which LoRA to use
        lora_input = None
        if lora_name:
            # Try to find in available LoRAs
            loras = get_available_loras()
            for lora in loras:
                if lora.name == lora_name:
                    lora_input = lora
                    break
        
        # Generate the cover
        result = generate_cover(spotify_url, user_mood, lora_input, negative_prompt=negative_prompt)
        
        if "error" in result:
            return jsonify({"error": result["error"]}), 400
            
        # Return result data
        return jsonify({
            "success": True,
            "title": result["title"],
            "image_path": result["output_path"],
            "image_url": f"/generated_covers/{os.path.basename(result['output_path'])}",
            "data_file": result.get("data_file"),
            "genres": result.get("genres", []),
            "mood": result.get("mood", ""),
            "playlist_name": result.get("item_name", ""),
            "lora_name": result.get("lora_name", ""),
            "lora_type": result.get("lora_type", "")
        })
    except Exception as e:
        print(f"API error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/regenerate", methods=["POST"])
def api_regenerate():
    """API endpoint to regenerate cover art with the same playlist"""
    try:
        data = request.json
        if not data or "playlist_url" not in data:
            return jsonify({"error": "Missing playlist_url in request"}), 400
            
        spotify_url = data.get("playlist_url")
        user_mood = data.get("mood", "")
        negative_prompt = data.get("negative_prompt", "")
        
        # Handle LoRA - simplified to only use name
        lora_name = data.get("lora_name", "")
        
        # Determine which LoRA to use
        lora_input = None
        if lora_name:
            # Try to find in available LoRAs
            loras = get_available_loras()
            for lora in loras:
                if lora.name == lora_name:
                    lora_input = lora
                    break
        
        # Generate a new seed to ensure variation
        random_seed = random.randint(1, 1000000)
        
        # Generate the cover
        result = generate_cover(spotify_url, user_mood, lora_input, negative_prompt=negative_prompt)
        
        if "error" in result:
            return jsonify({"error": result["error"]}), 400
            
        # Return result data
        return jsonify({
            "success": True,
            "title": result["title"],
            "image_path": result["output_path"],
            "image_url": f"/generated_covers/{os.path.basename(result['output_path'])}",
            "data_file": result.get("data_file", ""),
            "lora_name": result.get("lora_name", ""),
            "lora_type": result.get("lora_type", "")
        })
    except Exception as e:
        print(f"API error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/loras", methods=["GET"])
def api_loras():
    """API endpoint to get available LoRAs"""
    loras = get_available_loras()
    return jsonify({
        "loras": [lora.to_dict() for lora in loras]
    })

@app.route("/api/upload_lora", methods=["POST"])
def api_upload_lora():
    """API endpoint to upload a new LoRA file"""
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No file part"}), 400
            
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({"error": "No selected file"}), 400
            
        # Check file extension
        allowed_extensions = {'.safetensors', '.ckpt', '.pt'}
        file_ext = os.path.splitext(file.filename)[1].lower()
        
        if file_ext not in allowed_extensions:
            return jsonify({"error": f"File must be one of: {', '.join(allowed_extensions)}"}), 400
            
        # Save the file
        from config import LORA_DIR
        filename = os.path.basename(file.filename)
        file.save(os.path.join(LORA_DIR, filename))
        
        return jsonify({
            "success": True,
            "message": f"LoRA file {filename} uploaded successfully",
            "loras": [lora.to_dict() for lora in get_available_loras()]
        })
    except Exception as e:
        print(f"API error: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    import sys
    
    # Check if running in CLI mode
    if len(sys.argv) > 1:
        if sys.argv[1] == "--generate" and len(sys.argv) >= 3:
            print(f"Starting Spotify Cover Generator in CLI mode")
            
            initialize_app()
            
            spotify_url = sys.argv[2]
            mood = sys.argv[3] if len(sys.argv) >= 4 else None
            
            # Handle LoRA from command line - simplified to only use name
            lora_input = None
            if len(sys.argv) >= 5:
                lora_arg = sys.argv[4]
                # Try to find in available LoRAs
                loras = get_available_loras()
                for lora in loras:
                    if lora.name == lora_arg:
                        lora_input = lora
                        break
                
                # If not found, just use the name
                if not lora_input:
                    lora_input = lora_arg
            
            print(f"Generating cover for: {spotify_url}")
            if mood:
                print(f"Using mood: {mood}")
            if lora_input:
                if isinstance(lora_input, LoraModel):
                    print(f"Using LoRA: {lora_input.name} ({lora_input.source_type})")
                else:
                    print(f"Using LoRA: {lora_input}")
                
            result = generate_cover(spotify_url, mood, lora_input)
            
            if "error" in result:
                print(f"Error: {result['error']}")
                sys.exit(1)
                
            print(f"\nGeneration complete!")
            print(f"Title: {result['title']}")
            print(f"Image saved to: {result['output_path']}")
            print(f"Data saved to: {result.get('data_file', 'Not saved')}")
            sys.exit(0)
            
        elif sys.argv[1] == "--help":
            print("Spotify Cover Generator CLI Usage:")
            print("  Generate a cover: python app.py --generate <spotify_url> [mood] [lora_name]")
            print("  Start web server: python app.py")
            print("  Show this help:   python app.py --help")
            sys.exit(0)
    
    # Default to web server mode
    print(f"Starting Spotify Cover Generator")
    
    initialize_app()
    app.run(debug=False, host="0.0.0.0", port=50)