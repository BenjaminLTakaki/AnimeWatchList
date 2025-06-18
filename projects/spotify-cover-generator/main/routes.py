# projects/spotify-cover-generator/main/routes.py
from flask import (current_app, redirect, url_for, render_template,
                   send_from_directory, jsonify, request, session) # Added session
import datetime # For current_year in context processor, and guest logic
import uuid # For guest logic
import os # For os.path.basename in generate()
import traceback # For error handling in generate()

# Assuming get_current_user_or_guest_global_ref is correctly set up in factory
# and provides the necessary user/guest information.
from ..factory import get_current_user_or_guest_global_ref as get_current_user_or_guest

from ..extensions import db, limiter
from ..models import GenerationResultDB, User # User might be needed for type checking.
from sqlalchemy import text # For health_check

# Import monitor_performance (dummy or real) from factory or a shared utils
try:
    from ..factory import monitor_performance
except ImportError:
    print("⚠️ main/routes.py: 'monitor_performance' not found in factory, using dummy.")
    def monitor_performance(f): # Dummy decorator
        import functools
        @functools.wraps(f)
        def decorated_function(*args, **kwargs):
            return f(*args, **kwargs)
        return decorated_function
try:
    # These might be specific objects or just flags in app.config
    from ..fault_handling import FaultContext, create_user_friendly_error_messages
except ImportError:
    print("⚠️ main/routes.py: Fault handling utilities not found, error handlers will be simpler.")
    FaultContext = None
    create_user_friendly_error_messages = None

try:
    from ..monitoring_system import app_logger
except ImportError:
    print("⚠️ main/routes.py: 'app_logger' not found in monitoring_system, using current_app.logger.")
    # app_logger will be current_app.logger by default if not specifically set up
    pass


from . import bp

# --- Guest Session Helper Functions ---
# These are needed by the generate route if a guest makes a POST request.
def get_or_create_guest_session():
    if 'guest_session_id' not in session:
        session['guest_session_id'] = str(uuid.uuid4())
        session['guest_created'] = datetime.datetime.utcnow().isoformat()
        session['guest_generations_today'] = 0
        session['guest_last_generation'] = None
    return session['guest_session_id']

def get_guest_generations_today():
    if 'guest_session_id' not in session: # Ensure session is available
        get_or_create_guest_session() # Initialize if not found

    if session.get('guest_last_generation'):
        try:
            last_gen_date = datetime.datetime.fromisoformat(session['guest_last_generation']).date()
            if last_gen_date != datetime.datetime.utcnow().date():
                session['guest_generations_today'] = 0
        except ValueError:
            session['guest_generations_today'] = 0
            session['guest_last_generation'] = None

    return session.get('guest_generations_today', 0)

def track_guest_generation():
    if 'guest_session_id' not in session:
        get_or_create_guest_session()
    current_gens = get_guest_generations_today()
    session['guest_generations_today'] = current_gens + 1
    session['guest_last_generation'] = datetime.datetime.utcnow().isoformat()

# --- Routes ---
@bp.route("/")
def root():
    return redirect(url_for('main.generate')) # Updated for blueprint

@bp.route("/generate", methods=["GET", "POST"])
@limiter.limit("10 per hour", methods=["POST"]) # Assuming limiter is available via extensions
@monitor_performance # Assuming this is correctly imported or defined
def generate():
    user_info = get_current_user_or_guest()

    loras = []
    if user_info['can_use_loras']:
        try:
            from ..utils import get_available_loras # utils might need current_app access
            loras = get_available_loras()
        except Exception as e:
            current_app.logger.warning(f"Error getting LoRAs: {e}")
            loras = []

    if request.method == "POST":
        if not user_info['can_generate']:
            return render_template(
                "index.html",
                error=f"Daily generation limit reached ({user_info['daily_limit']} per day). " +
                      ("Try again tomorrow!" if user_info['type'] == 'guest' else "Try again tomorrow or upgrade to premium!"),
                loras=loras,
                user_info=user_info # Pass user_info for template rendering
            )
        try:
            from .. import generator # Assuming generator is in the main package

            playlist_url = request.form.get("playlist_url", "").strip()
            user_mood = request.form.get("mood", "").strip()
            negative_prompt = request.form.get("negative_prompt", "").strip()
            lora_name = request.form.get("lora_name", "").strip()

            if not playlist_url:
                return render_template("index.html", error="Please enter a Spotify playlist or album URL.", loras=loras, user_info=user_info)

            if user_info['type'] == 'guest' and lora_name and lora_name != "none":
                return render_template("index.html", error="LoRA styles are only available for registered users.", loras=loras, user_info=user_info)

            lora_input = None
            if lora_name and lora_name != "none" and user_info['can_use_loras']:
                for lora_item in loras: # loras should be defined
                    if hasattr(lora_item, 'name') and lora_item.name == lora_name:
                        lora_input = lora_item
                        break

            user_id_for_gen = user_info['user'].id if user_info['type'] == 'user' and user_info['user'] else None

            result = generator.generate_cover(
                playlist_url, user_mood, lora_input,
                negative_prompt=negative_prompt, user_id=user_id_for_gen
            )

            if isinstance(result, dict) and "error" in result:
                return render_template("index.html", error=result["error"], loras=loras, user_info=user_info)

            if user_info['type'] == 'guest':
                track_guest_generation() # Uses session helpers defined above

            img_filename = os.path.basename(result["output_path"]) if result.get("output_path") else None

            # Chart generation might need to be a service or utility
            genres_chart_data = None
            genre_percentages_data = []
            try:
                from .. import chart_generator
                genres_chart_data = chart_generator.generate_genre_chart(result.get("all_genres", []))
            except Exception as e:
                current_app.logger.warning(f"Error generating genre chart: {e}")
            try:
                from ..utils import calculate_genre_percentages
                genre_percentages_data = calculate_genre_percentages(result.get("all_genres", []))
            except Exception as e:
                current_app.logger.warning(f"Error calculating genre percentages: {e}")

            playlist_id_val = None
            try:
                from ..utils import extract_playlist_id
                playlist_id_val = extract_playlist_id(playlist_url) if playlist_url and "playlist/" in playlist_url else None
            except Exception as e:
                current_app.logger.warning(f"Error extracting playlist ID: {e}")

            display_data = {
                "title": result.get("title", "Generated Album"), "image_file": img_filename,
                "image_data_base64": result.get("image_data_base64", ""),
                "genres": ", ".join(result.get("genres", [])), "mood": result.get("mood", ""),
                "playlist_name": result.get("item_name", "Your Music"),
                "found_genres": bool(result.get("genres", [])),
                "genres_chart": genres_chart_data, "genre_percentages": genre_percentages_data,
                "playlist_url": playlist_url, "user_mood": user_mood,
                "negative_prompt": negative_prompt, "lora_name": result.get("lora_name", ""),
                "lora_type": result.get("lora_type", ""), "lora_url": result.get("lora_url", ""),
                "user_info": user_info, "user": user_info.get('user'), # Pass user object if available
                "can_edit_playlist": user_info['can_edit_playlists'],
                "playlist_id": playlist_id_val, "timestamp": result.get("timestamp", "")
            }

            if user_info['type'] == 'user' and user_info['user']:
                try:
                    new_generation = GenerationResultDB(
                        title=result.get("title", ""), output_path=result.get("output_path", ""),
                        item_name=result.get("item_name", ""), genres=result.get("genres", []),
                        all_genres=result.get("all_genres", []), mood=user_mood,
                        spotify_url=playlist_url, lora_name=result.get("lora_name", ""),
                        user_id=user_info['user'].id
                    )
                    db.session.add(new_generation)
                    db.session.commit()
                except Exception as e:
                    current_app.logger.error(f"Error saving generation result to DB: {e}")
                    db.session.rollback()

            return render_template("result.html", **display_data)

        except Exception as e:
            current_app.logger.error(f"Server error processing generate request: {e}\n{traceback.format_exc()}")
            return render_template("index.html", error=f"An unexpected error occurred. Please try again.", loras=loras, user_info=user_info)
    else: # GET request
        return render_template("index.html", loras=loras, user_info=user_info)

@bp.route("/generated_covers/<path:filename>")
def serve_image(filename):
    covers_dir = current_app.config.get('COVERS_DIR')
    if not covers_dir:
        current_app.logger.error("COVERS_DIR not configured.")
        return "Image serving misconfigured", 500
    try:
        return send_from_directory(covers_dir, filename)
    except Exception as e:
        current_app.logger.error(f"Error serving image {filename}: {e}")
        return "Image not found", 404

@bp.route('/health')
def health_check():
    try:
        db.session.execute(text('SELECT 1'))
        spotify_configured = bool(current_app.config.get('SPOTIFY_CLIENT_ID') and current_app.config.get('SPOTIFY_CLIENT_SECRET'))
        response_data = {
            "status": "healthy", "timestamp": datetime.datetime.utcnow().isoformat(),
            "database": "connected", "spotify_configured": spotify_configured
        }
        return jsonify(response_data), 200
    except Exception as e:
        return jsonify({
            "status": "error", "error": str(e),
            "timestamp": datetime.datetime.utcnow().isoformat()
        }), 500

# --- Error Handlers ---
@bp.app_errorhandler(404)
def handle_404_error(e):
    # Log the error using app_logger if available from monitoring_system, else current_app.logger
    logger = getattr(current_app, 'logger_instance', current_app.logger) # logger_instance was set in factory
    if current_app.config.get('MONITORING_AVAILABLE') and hasattr(logger, 'log_structured'):
        logger.log_structured("info", "page_not_found", path=request.path, method=request.method)
    else:
        logger.info(f"Page not found: {request.path} (Method: {request.method})")
    return render_template("error.html", error_message="Page not found (404)."), 404


@bp.app_errorhandler(500)
def handle_500_error(e):
    logger = getattr(current_app, 'logger_instance', current_app.logger)
    if current_app.config.get('MONITORING_AVAILABLE') and hasattr(logger, 'log_structured'):
        logger.log_structured("error", "server_error", error=str(e), path=request.path, method=request.method)
    else:
        logger.error(f"Server error: {e} for {request.path} (Method: {request.method})")
    return render_template("error.html", error_message="Internal server error (500). Please try again later."), 500

@bp.app_errorhandler(Exception)
def handle_generic_error(e):
    logger = getattr(current_app, 'logger_instance', current_app.logger)
    user_message = "An unexpected application error occurred. Please try again."

    if current_app.config.get('FAULT_HANDLING_AVAILABLE') and FaultContext and create_user_friendly_error_messages:
        user_info_for_fault = get_current_user_or_guest() # Ensure this is available and provides needed info
        user_id = None
        is_guest = True
        if user_info_for_fault and user_info_for_fault.get('type') == 'user' and user_info_for_fault.get('user'):
            user_id = str(user_info_for_fault['user'].id)
            is_guest = False

        context = FaultContext(
            function_name="web_request_generic_error", # General context
            attempt_number=1, error=e, user_id=user_id, is_guest=is_guest
        )
        user_message = create_user_friendly_error_messages(e, context)

    if current_app.config.get('MONITORING_AVAILABLE') and hasattr(logger, 'log_structured'):
        logger.log_structured("error", "unhandled_exception", error=str(e), path=request.path, method=request.method, traceback=traceback.format_exc())
    else:
        logger.error(f"Unhandled exception: {e} for {request.path} (Method: {request.method})\n{traceback.format_exc()}")

    # Avoid raising another exception if render_template itself fails
    try:
        return render_template('error.html', error_message=user_message, show_retry=True), 500
    except Exception:
        return "An critical error occurred. Please try again later.", 500
