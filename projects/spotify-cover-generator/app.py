import os
import sys
import random
import json
import datetime
import traceback
import uuid 
import time
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlparse
from functools import wraps

# Ensure the project's own directory is prioritized for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

import requests
import base64
import secrets
from collections import Counter

from flask import (Flask, request, render_template, send_from_directory, jsonify,
                   session, redirect, url_for, flash, make_response)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_sqlalchemy import SQLAlchemy 
from flask_migrate import Migrate 
from flask_limiter import Limiter 
from flask_limiter.util import get_remote_address
from sqlalchemy import text

# Import create_app from the package __init__
from spotify_cover_generator.factory import create_app

# Import necessary Flask components and other utilities
from flask import request, render_template, send_from_directory, jsonify, session, redirect, url_for, flash, make_response # Added Flask here
from werkzeug.security import generate_password_hash, check_password_hash # Keep for routes
from werkzeug.utils import secure_filename # Keep for routes

from spotify_cover_generator.extensions import db, limiter # Keep for @limiter.limit decorator
from spotify_cover_generator.models import User, LoginSession, LoraModelDB, GenerationResultDB, SpotifyState # Keep for route logic
from spotify_cover_generator.auth_utils import get_current_user # Keep for route logic, though get_current_user_or_guest is in factory
from spotify_cover_generator.decorators import login_required, admin_required, permission_required # Keep for route decorators

app = create_app()

try:
    from spotify_cover_generator.monitoring_system import (
        setup_monitoring, monitor_performance, monitor_api_calls,
        app_logger, alert_manager, system_monitor
    )
    MONITORING_AVAILABLE = True
    print("✅ Monitoring system imported successfully")
except ImportError as e:
    print(f"⚠️ Monitoring system import failed: {e}")
    MONITORING_AVAILABLE = False
    
    # Define dummy decorators as fallback
    def monitor_performance(func):
        return func
    def monitor_api_calls(service_name):
        def decorator(func):
            return func
        return decorator

# Import fault handling with fallback
try:
    from spotify_cover_generator.fault_handling import (
        fault_tolerant_api_call, GracefulDegradation, db_failover,
        create_user_friendly_error_messages, FaultContext, http_client
    )
    FAULT_HANDLING_AVAILABLE = True
    print("✅ Fault handling imported successfully")
except ImportError as e:
    print(f"⚠️ Fault handling import failed: {e}")
    FAULT_HANDLING_AVAILABLE = False
    
    def fault_tolerant_api_call(service_name, fallback_func=None):
        def decorator(func):
            return func
        return decorator

# ROUTES SECTION - FIXED IMPLEMENTATIONS

@app.route("/")
def root():
    """Root route - redirect to generate"""
    return redirect(url_for('generate'))

@app.route("/generate", methods=["GET", "POST"])
@limiter.limit("10 per hour", methods=["POST"])
@monitor_performance
def generate():
    """FIXED Main generation route with comprehensive error handling"""
    user_info = get_current_user_or_guest()
    
    # Check generation limits
    if request.method == "POST" and not user_info['can_generate']:
        return render_template(
            "index.html",
            error=f"Daily generation limit reached ({user_info['daily_limit']} per day). " + 
                  ("Try again tomorrow!" if user_info['type'] == 'guest' else "Try again tomorrow or upgrade to premium!"),
            loras=[]
        )
    
    # Get available loras (only for logged-in users)
    loras = []
    if user_info['can_use_loras']:
        try:
            from spotify_cover_generator.utils import get_available_loras
            loras = get_available_loras()
        except Exception as e:
            print(f"⚠️ Error getting LoRAs: {e}")
            loras = []

    if request.method == "POST":
        try:
            # Import generator with error handling
            try:
                from spotify_cover_generator import generator
                GENERATOR_AVAILABLE = True
            except ImportError as e:
                print(f"❌ Generator import failed: {e}")
                return render_template(
                    "index.html",
                    error="Core generation modules are not available. Please contact support.",
                    loras=loras
                )
            
            # Get form data
            playlist_url = request.form.get("playlist_url", "").strip()
            user_mood = request.form.get("mood", "").strip()
            negative_prompt = request.form.get("negative_prompt", "").strip()
            lora_name = request.form.get("lora_name", "").strip()
            
            # Validate inputs
            if not playlist_url:
                return render_template(
                    "index.html", 
                    error="Please enter a Spotify playlist or album URL.",
                    loras=loras
                )
            
            # Restrict LoRA usage for guests
            if user_info['type'] == 'guest' and lora_name and lora_name != "none":
                return render_template(
                    "index.html", 
                    error="LoRA styles are only available for registered users. Please sign up for free to access advanced features!",
                    loras=loras
                )
            
            # Process LoRA input
            lora_input = None
            if lora_name and lora_name != "none" and user_info['can_use_loras']:
                for lora_item in loras:
                    if hasattr(lora_item, 'name') and lora_item.name == lora_name:
                        lora_input = lora_item
                        break
            
            # Generate the cover
            user_id = user_info['user'].id if user_info['type'] == 'user' else None
            
            try:
                result = generator.generate_cover(
                    playlist_url, 
                    user_mood, 
                    lora_input, 
                    negative_prompt=negative_prompt, 
                    user_id=user_id
                )
            except Exception as gen_error:
                print(f"❌ Generation error: {gen_error}")
                return render_template(
                    "index.html", 
                    error=f"Generation failed: {str(gen_error)}. Please try again with a different playlist or contact support.",
                    loras=loras
                )
            
            if isinstance(result, dict) and "error" in result:
                return render_template(
                    "index.html", 
                    error=result["error"],
                    loras=loras
                )
            
            # Increment generation count
            if user_info['type'] == 'guest':
                track_guest_generation()
            
            # Prepare image file name
            img_filename = os.path.basename(result["output_path"]) if result.get("output_path") else None
            
            # Generate charts with fallback
            genres_chart_data = None
            genre_percentages_data = []
            
            try:
                from spotify_cover_generator import chart_generator
                genres_chart_data = chart_generator.generate_genre_chart(result.get("all_genres", []))
            except Exception as e:
                print(f"⚠️ Error generating genre chart: {e}")

            try:
                from spotify_cover_generator.utils import calculate_genre_percentages
                genre_percentages_data = calculate_genre_percentages(result.get("all_genres", []))
            except Exception as e:
                print(f"⚠️ Error calculating genre percentages: {e}")
            
            # Extract playlist ID
            playlist_id = None
            try:
                from spotify_cover_generator.utils import extract_playlist_id
                playlist_id = extract_playlist_id(playlist_url) if playlist_url and "playlist/" in playlist_url else None
            except Exception as e:
                print(f"⚠️ Error extracting playlist ID: {e}")
            
            # Prepare display data
            display_data = {
                "title": result.get("title", "Generated Album"),
                "image_file": img_filename,
                "image_data_base64": result.get("image_data_base64", ""),
                "genres": ", ".join(result.get("genres", [])),
                "mood": result.get("mood", ""),
                "playlist_name": result.get("item_name", "Your Music"),
                "found_genres": bool(result.get("genres", [])),
                "genres_chart": genres_chart_data,
                "genre_percentages": genre_percentages_data,
                "playlist_url": playlist_url,
                "user_mood": user_mood,
                "negative_prompt": negative_prompt,
                "lora_name": result.get("lora_name", ""),
                "lora_type": result.get("lora_type", ""),
                "lora_url": result.get("lora_url", ""),
                "user_info": user_info,
                "user": user_info.get('user'),
                "can_edit_playlist": user_info['can_edit_playlists'],
                "playlist_id": playlist_id,
                "timestamp": result.get("timestamp", "")
            }
            
            # Record generation if user is logged in
            if user_info['type'] == 'user':
                try:
                    new_generation = GenerationResultDB(
                        title=result.get("title", ""),
                        output_path=result.get("output_path", ""),
                        item_name=result.get("item_name", ""),
                        genres=result.get("genres", []),
                        all_genres=result.get("all_genres", []),
                        mood=user_mood,
                        spotify_url=playlist_url,
                        lora_name=result.get("lora_name", ""),
                        user_id=user_info['user'].id
                    )
                    db.session.add(new_generation)
                    db.session.commit()
                except Exception as e:
                    print(f"⚠️ Error saving generation result to DB: {e}")

            return render_template("result.html", **display_data)
            
        except Exception as e:
            print(f"❌ Server error processing request: {e}")
            traceback.print_exc()
            return render_template(
                "index.html", 
                error=f"An unexpected error occurred: {str(e)}. Please try again.",
                loras=loras
            )
    else:
        # GET request - show the form
        return render_template("index.html", loras=loras)

@app.route("/generated_covers/<path:filename>")
def serve_image(filename):
    """Serve generated images"""
    try:
        return send_from_directory(COVERS_DIR, filename)
    except Exception as e:
        print(f"Error serving image {filename}: {e}")
        # Return a 404 or placeholder image
        return "Image not found", 404

# FIXED API ENDPOINTS

@app.route('/spotify/api/upload_lora', methods=['POST'])
@login_required
@limiter.limit("5 per hour")
def upload_lora(user): # Added user argument
    """FIXED LoRA upload endpoint"""
    try:
        # user = get_current_user() # Removed: user is now passed as an argument
        if not user:
            return jsonify({"success": False, "error": "User not authenticated"}), 401
        
        if not user.is_premium_user():
            return jsonify({
                "success": False, 
                "error": "File uploads are only available for premium users."
            }), 403
        
        if 'file' not in request.files:
            return jsonify({"success": False, "error": "No file uploaded"}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({"success": False, "error": "No file selected"}), 400
        
        # Validate file
        filename = secure_filename(file.filename)
        if not filename.lower().endswith(('.safetensors', '.ckpt', '.pt')):
            return jsonify({
                "success": False, 
                "error": "Invalid file type. Only .safetensors, .ckpt, and .pt files are allowed."
            }), 400
        
        lora_name = filename.rsplit('.', 1)[0]
        
        # Check if exists
        existing = LoraModelDB.query.filter_by(name=lora_name).first()
        if existing:
            return jsonify({
                "success": False, 
                "error": f"LoRA with name '{lora_name}' already exists"
            }), 400
        
        # Create LoRA directory
        lora_dir = BASE_DIR / "loras"
        lora_dir.mkdir(exist_ok=True)
        
        # Save file
        file_path = lora_dir / filename
        file.save(str(file_path))
        file_size = os.path.getsize(str(file_path))
        
        # Add to database
        new_lora = LoraModelDB(
            name=lora_name,
            source_type="local",
            path=str(file_path),
            file_size=file_size,
            uploaded_by=user.id
        )
        
        db.session.add(new_lora)
        db.session.commit()
        
        return jsonify({
            "success": True, 
            "message": f"LoRA '{lora_name}' uploaded successfully"
        })
        
    except Exception as e:
        print(f"Error uploading LoRA: {e}")
        return jsonify({"success": False, "error": "Internal server error"}), 500

@app.route('/spotify/api/loras')
def get_loras():
    """FIXED Get available LoRAs endpoint"""
    try:
        user = get_current_user()
        loras = []
        
        # Get from database
        db_loras = LoraModelDB.query.filter_by(source_type="local").all()
        
        for db_lora in db_loras:
            if db_lora.path and os.path.exists(db_lora.path):
                lora_data = {
                    "name": db_lora.name,
                    "source_type": "local",
                    "file_size": db_lora.file_size or 0,
                    "uploaded_at": db_lora.uploaded_at.isoformat() if db_lora.uploaded_at else None,
                    "can_delete": False,
                    "uploaded_by_current_user": False
                }
                
                if user:
                    lora_data["uploaded_by_current_user"] = (db_lora.uploaded_by == user.id)
                    lora_data["can_delete"] = (
                        db_lora.uploaded_by == user.id or 
                        user.is_premium_user()
                    )
                
                loras.append(lora_data)
        
        return jsonify({"loras": loras})
        
    except Exception as e:
        print(f"Error getting LoRAs: {e}")
        return jsonify({"loras": []})

@app.route('/spotify/api/delete_lora', methods=['DELETE'])
@login_required
@limiter.limit("10 per hour")
def delete_lora(user): # Added user argument
    """FIXED Delete LoRA endpoint"""
    try:
        # user = get_current_user() # Removed: user is now passed as an argument
        if not user:
            return jsonify({"success": False, "error": "User not authenticated"}), 401
        
        data = request.get_json()
        lora_name = data.get('name', '').strip()
        
        if not lora_name:
            return jsonify({"success": False, "error": "LoRA name is required"}), 400
        
        lora_record = LoraModelDB.query.filter_by(name=lora_name).first()
        if not lora_record:
            return jsonify({"success": False, "error": "LoRA not found"}), 404
        
        if not user.is_premium_user() and lora_record.uploaded_by != user.id:
            return jsonify({"success": False, "error": "You can only delete LoRAs you uploaded"}), 403
        
        # Delete file
        if lora_record.path and os.path.exists(lora_record.path):
            try:
                os.remove(lora_record.path)
            except Exception as e:
                print(f"Could not delete file {lora_record.path}: {e}")
        
        # Delete from database
        db.session.delete(lora_record)
        db.session.commit()
        
        return jsonify({"success": True, "message": f"LoRA '{lora_name}' deleted successfully"})
        
    except Exception as e:
        print(f"Error deleting LoRA: {e}")
        return jsonify({"success": False, "error": "Internal server error"}), 500

# FIXED HELPER FUNCTIONS (Many of these are or should be moved to the factory or blueprints)

# get_current_user_or_guest is now in factory.py / __init__.py and registered via context_processor
# get_current_user is in auth_utils.py (still used by routes directly sometimes, or by the new get_current_user_or_guest)

# Guest session functions: These are problematic if app.py is not the main execution scope for session.
# For now, assuming they are called within Flask request context where 'session' is available.
# Ideally, these would be part of a UserSession class or similar, managed by the app.
# If get_current_user_or_guest (in factory) handles guest logic completely, these might not be directly called from app.py routes anymore.

# def get_or_create_guest_session(): ... # Potentially removed or refactored
# def get_guest_generations_today(): ... # Potentially removed or refactored
# def can_guest_generate(): ... # Potentially removed or refactored
# def track_guest_generation(): ... # Potentially removed or refactored
# These functions if still used by routes in app.py need to be evaluated.
# The generate() route uses get_current_user_or_guest() which is now from the factory.
# It also calls track_guest_generation(). This needs to be available.
# Let's keep guest session functions for now, but acknowledge they are a bit misplaced.

def get_or_create_guest_session():
    """Get or create a guest session"""
    if 'guest_session_id' not in session:
        session['guest_session_id'] = str(uuid.uuid4())
        session['guest_created'] = datetime.datetime.utcnow().isoformat()
        session['guest_generations_today'] = 0
        session['guest_last_generation'] = None
    return session['guest_session_id']

def get_guest_generations_today():
    """Get number of generations for guest today"""
    if 'guest_session_id' not in session: # Ensure session is available
        get_or_create_guest_session() # Initialize if not found
    
    # Reset daily count if new day
    if session.get('guest_last_generation'):
        try:
            last_gen_date = datetime.datetime.fromisoformat(session['guest_last_generation']).date()
            if last_gen_date != datetime.datetime.utcnow().date():
                session['guest_generations_today'] = 0
        except ValueError: # Handle malformed date string
            session['guest_generations_today'] = 0
            session['guest_last_generation'] = None # Clear malformed date
    
    return session.get('guest_generations_today', 0)

def can_guest_generate():
    """Check if guest can generate (based on a limit of 1 for this example)"""
    return get_guest_generations_today() < 1

def track_guest_generation():
    """Track generation for guest"""
    # Ensure session is initialized
    if 'guest_session_id' not in session:
        get_or_create_guest_session()

    current_gens = get_guest_generations_today() # Gets current count, handles daily reset
    session['guest_generations_today'] = current_gens + 1
    session['guest_last_generation'] = datetime.datetime.utcnow().isoformat()

# Health check endpoint
@app.route('/health')
def health_check():
    """FIXED Health check endpoint"""
    try:
        # Test database connection
        db.session.execute(text('SELECT 1'))
        
        response_data = {
            "status": "healthy",
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "database": "connected",
            "spotify_configured": bool(SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET)
        }
        
        return jsonify(response_data), 200
        
    except Exception as e:
        return jsonify({
            "status": "error", 
            "error": str(e),
            "timestamp": datetime.datetime.utcnow().isoformat()
        }), 500

# Error handlers
@app.errorhandler(404)
def handle_404_error(e):
    if MONITORING_AVAILABLE:
        try:
            app_logger.log_structured(
                "info",
                "page_not_found",
                path=request.path,
                method=request.method
            )
        except:
            pass
    return "Page not found", 404

@app.errorhandler(500)
def handle_500_error(e):
    if MONITORING_AVAILABLE:
        try:
            app_logger.log_structured(
                "error",
                "server_error",
                error=str(e),
                path=request.path,
                method=request.method
            )
        except:
            pass
    return "Internal Server Error", 500

@app.errorhandler(Exception)
def handle_generic_error(e):
    """Enhanced error handler"""
    try:
        if MONITORING_AVAILABLE:
            app_logger.log_structured(
                "error",
                "unhandled_exception",
                error=str(e),
                path=request.path,
                method=request.method
            )
        
        # Create user-friendly error message
        if FAULT_HANDLING_AVAILABLE:
            user_info = get_current_user_or_guest()
            context = FaultContext(
                function_name="web_request",
                attempt_number=1,
                error=e,
                user_id=str(user_info.get('user', {}).get('id', '')),
                is_guest=user_info.get('type') == 'guest'
            )
            user_message = create_user_friendly_error_messages(e, context)
        else:
            user_message = "An unexpected error occurred. Please try again."
        
        return render_template('error.html', 
                             error_message=user_message,
                             show_retry=True), 500
    except Exception:
        return "An error occurred. Please try again.", 500

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login route - handle both form login and Spotify OAuth"""
    if request.method == 'POST':
        # Handle form-based login
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        if not username or not password:
            flash('Please enter both username and password', 'error')
            return render_template('login.html')
        
        try:
            user = User.query.filter_by(username=username).first()
            if user and user.password_hash and check_password_hash(user.password_hash, password):
                # Create session
                session_token = secrets.token_urlsafe(32)
                login_session = LoginSession(
                    user_id=user.id,
                    session_token=session_token,
                    expires_at=datetime.datetime.utcnow() + timedelta(days=30),
                    ip_address=request.remote_addr,
                    user_agent=request.headers.get('User-Agent', '')
                )
                db.session.add(login_session)
                user.last_login = datetime.datetime.utcnow()
                db.session.commit()
                
                session['user_id'] = user.id
                session['user_session'] = session_token
                
                # Set cookie
                resp = make_response(redirect(url_for('generate')))
                resp.set_cookie('session_token', session_token, max_age=30*24*60*60)
                
                flash('Logged in successfully!', 'success')
                return resp
            else:
                flash('Invalid username or password', 'error')
        except Exception as e:
            print(f"Login error: {e}")
            flash('Login failed. Please try again.', 'error')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    """Register route"""
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        # Validation
        if not email or not username or not password:
            flash('All fields are required.', 'error')
            return render_template('register.html')
        
        if len(username) < 3:
            flash('Username must be at least 3 characters.', 'error')
            return render_template('register.html')
            
        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'error')
            return render_template('register.html')

        try:
            # Check if user already exists
            if User.query.filter_by(email=email).first():
                flash('Email already registered.', 'error')
                return render_template('register.html')
            
            if User.query.filter_by(username=username).first():
                flash('Username already taken.', 'error')
                return render_template('register.html')

            # Create new user
            password_hash = generate_password_hash(password)
            new_user = User(
                email=email, 
                username=username, 
                display_name=username,
                password_hash=password_hash
            )
            
            db.session.add(new_user)
            db.session.commit()
            
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))
            
        except Exception as e:
            db.session.rollback()
            print(f"Registration error: {e}")
            flash('Registration failed. Please try again.', 'error')
        
    return render_template('register.html')

@app.route('/logout')
def logout():
    """Logout route"""
    try:
        # Mark session as inactive
        if 'user_session' in session:
            session_token = session['user_session']
            login_session = LoginSession.query.filter_by(session_token=session_token).first()
            if login_session:
                login_session.is_active = False
                db.session.commit()
        
        # Clear session
        session.clear()
        
        # Clear cookie
        resp = make_response(redirect(url_for('generate')))
        resp.set_cookie('session_token', '', expires=0)
        
        flash('You have been logged out', 'info')
        return resp
        
    except Exception as e:
        print(f"Logout error: {e}")
        session.clear()
        return redirect(url_for('generate'))

@app.route('/profile')
@login_required
def profile(user): # Added user argument
    """User profile page"""
    try:
        # user = get_current_user() # Removed: user is now passed as an argument
        if not user: # Should not happen if login_required works
            return redirect(url_for('login'))
        
        # Get user statistics
        total_generations = GenerationResultDB.query.filter_by(user_id=user.id).count()
        generations_today = user.get_generations_today()
        daily_limit = user.get_daily_generation_limit()
        
        # Get recent generations
        recent_generations = (GenerationResultDB.query
                             .filter_by(user_id=user.id)
                             .order_by(GenerationResultDB.timestamp.desc())
                             .limit(10)
                             .all())
        
        profile_data = {
            'user': user,
            'total_generations': total_generations,
            'generations_today': generations_today,
            'daily_limit': daily_limit,
            'can_generate': user.can_generate_today(),
            'recent_generations': recent_generations,
            'spotify_connected': bool(user.spotify_access_token),
            'is_premium': user.is_premium_user()
        }
        
        return render_template('profile.html', **profile_data)
        
    except Exception as e:
        print(f"Profile error: {e}")
        flash('Error loading profile', 'error')
        return redirect(url_for('generate'))

# Spotify OAuth routes
@app.route('/spotify-login')
def spotify_login():
    """Initiate Spotify OAuth flow"""
    if not SPOTIFY_CLIENT_ID:
        flash('Spotify integration is not configured', 'error')
        return redirect(url_for('generate'))
    
    try:
        # Generate state for CSRF protection
        state = secrets.token_urlsafe(32)
        
        # Store state in database for verification
        oauth_state = SpotifyState(state=state)
        db.session.add(oauth_state)
        db.session.commit()
        
        # Spotify OAuth parameters
        scope = 'playlist-read-private playlist-modify-public playlist-modify-private ugc-image-upload user-read-email user-read-private'
        
        auth_url = (
            'https://accounts.spotify.com/authorize?'
            f'client_id={SPOTIFY_CLIENT_ID}&'
            f'response_type=code&'
            f'redirect_uri={SPOTIFY_REDIRECT_URI}&'
            f'scope={scope}&'
            f'state={state}'
        )
        
        return redirect(auth_url)
        
    except Exception as e:
        print(f"Spotify login error: {e}")
        flash('Failed to initiate Spotify login', 'error')
        return redirect(url_for('login'))

@app.route('/spotify-callback')
def spotify_callback():
    """Handle Spotify OAuth callback"""
    try:
        code = request.args.get('code')
        state = request.args.get('state')
        error = request.args.get('error')
        
        if error:
            flash(f'Spotify authorization failed: {error}', 'error')
            return redirect(url_for('generate'))
        
        if not code or not state:
            flash('Invalid Spotify callback', 'error')
            return redirect(url_for('generate'))
        
        # Verify state
        oauth_state = SpotifyState.query.filter_by(state=state, used=False).first()
        if not oauth_state or oauth_state.created_at < datetime.datetime.utcnow() - timedelta(minutes=10):
            flash('Invalid or expired state parameter', 'error')
            return redirect(url_for('generate'))
        
        # Mark state as used
        oauth_state.used = True
        db.session.commit()
        
        # Exchange code for tokens
        token_data = {
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': SPOTIFY_REDIRECT_URI,
            'client_id': SPOTIFY_CLIENT_ID,
            'client_secret': SPOTIFY_CLIENT_SECRET
        }
        
        response = requests.post('https://accounts.spotify.com/api/token', data=token_data)
        
        if response.status_code != 200:
            flash('Failed to get Spotify tokens', 'error')
            return redirect(url_for('generate'))
        
        tokens = response.json()
        access_token = tokens['access_token']
        refresh_token = tokens.get('refresh_token')
        expires_in = tokens.get('expires_in', 3600)
        
        # Get user info from Spotify
        headers = {'Authorization': f'Bearer {access_token}'}
        user_response = requests.get('https://api.spotify.com/v1/me', headers=headers)
        
        if user_response.status_code != 200:
            flash('Failed to get Spotify user info', 'error')
            return redirect(url_for('generate'))
        
        spotify_user = user_response.json()
        spotify_id = spotify_user['id']
        
        # Find or create user
        user = User.query.filter_by(spotify_id=spotify_id).first()
        
        if not user:
            # Create new user
            user = User(
                spotify_id=spotify_id,
                spotify_username=spotify_user.get('id'),
                display_name=spotify_user.get('display_name', spotify_user.get('id')),
                email=spotify_user.get('email'),
                is_premium=False
            )
            db.session.add(user)
        else:
            # Update existing user
            user.display_name = spotify_user.get('display_name', spotify_user.get('id'))
            user.email = spotify_user.get('email')
        
        # Update tokens
        user.spotify_access_token = access_token
        user.spotify_refresh_token = refresh_token
        user.spotify_token_expires = datetime.datetime.utcnow() + timedelta(seconds=expires_in)
        user.last_login = datetime.datetime.utcnow()
        
        db.session.commit()
        
        # Create login session
        session_token = secrets.token_urlsafe(32)
        login_session = LoginSession(
            user_id=user.id,
            session_token=session_token,
            expires_at=datetime.datetime.utcnow() + timedelta(days=30),
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent', '')
        )
        db.session.add(login_session)
        db.session.commit()
        
        # Set session
        session['user_id'] = user.id
        session['user_session'] = session_token
        
        # Create response with cookie
        resp = make_response(redirect(url_for('generate')))
        resp.set_cookie('session_token', session_token, max_age=30*24*60*60)
        
        # Show different messages based on premium status
        if user.is_premium_user():
            flash('🌟 Welcome back, Premium user! You have unlimited generations.', 'success')
        else:
            flash('Successfully connected to Spotify! You have 2 daily generations.', 'success')
        
        return resp
        
    except Exception as e:
        print(f"Spotify callback error: {e}")
        flash('An error occurred during Spotify authorization', 'error')
        return redirect(url_for('generate'))

# Additional missing models
# class SpotifyState(db.Model): # Removed: Moved to models.py
#     __tablename__ = 'spotify_oauth_states'
#     id = db.Column(db.Integer, primary_key=True)
#     state = db.Column(db.String(100), unique=True, nullable=False)
#     created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
#     used = db.Column(db.Boolean, default=False)

# Upload info route
@app.route('/spotify/api/upload_info')
@login_required
def get_upload_info(user): # Added user argument
    """Get user's upload information"""
    try:
        # user = get_current_user() # Removed: user is now passed as an argument
        if not user: # Should not happen if login_required works
            return jsonify({"error": "Not authenticated"}), 401
        
        # Get current count
        current_count = LoraModelDB.query.filter_by(source_type="local", uploaded_by=user.id).count()
        
        if user.is_premium_user():
            return jsonify({
                "can_upload": True, 
                "current_count": current_count, 
                "limit": "unlimited", 
                "is_premium": True
            })
        else:
            return jsonify({
                "can_upload": current_count < 2, 
                "current_count": current_count, 
                "limit": 2, 
                "is_premium": False
            })
            
    except Exception as e:
        print(f"Upload info error: {e}")
        return jsonify({"error": "Internal server error"}), 500


if __name__ == '__main__':

    port = int(os.environ.get("PORT", 5000))
    # Consider app.config for DEBUG settings as well
    app.run(debug=app.config.get("DEBUG", False), host="0.0.0.0", port=port)