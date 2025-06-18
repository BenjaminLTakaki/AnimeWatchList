# projects/spotify-cover-generator/spotify_routes/routes.py
from flask import current_app, redirect, url_for, render_template, flash, request, jsonify, session
import secrets
import datetime
from datetime import timedelta
import requests # For Spotify API calls
import os # For os.path.exists, os.remove, os.path.getsize
from werkzeug.utils import secure_filename # For file uploads
from pathlib import Path # For path manipulations if needed

from ..extensions import db, limiter
from ..models import User, LoraModelDB, SpotifyState, GenerationResultDB # Added GenerationResultDB
from ..decorators import login_required
from ..auth_utils import get_current_user # For routes that might not be @login_required but need user

from . import bp

@bp.route('/spotify/api/upload_lora', methods=['POST'])
@login_required
@limiter.limit("5 per hour") # Assuming limiter is correctly initialized
def upload_lora(user):
    try:
        if not user.is_premium_user(): # Assuming User model has is_premium_user method
            return jsonify({"success": False, "error": "File uploads are only available for premium users."}), 403

        if 'file' not in request.files:
            return jsonify({"success": False, "error": "No file uploaded"}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({"success": False, "error": "No file selected"}), 400

        filename = secure_filename(file.filename)
        if not filename.lower().endswith(('.safetensors', '.ckpt', '.pt')):
            return jsonify({"success": False, "error": "Invalid file type. Only .safetensors, .ckpt, and .pt files are allowed."}), 400

        lora_name = filename.rsplit('.', 1)[0]

        existing = LoraModelDB.query.filter_by(name=lora_name).first()
        if existing:
            return jsonify({"success": False, "error": f"LoRA with name '{lora_name}' already exists"}), 400

        # Use app.config for directory paths
        lora_dir = Path(current_app.config.get('LORA_DIR', current_app.config.get('BASE_DIR') / "loras"))
        lora_dir.mkdir(parents=True, exist_ok=True) # Ensure directory exists

        file_path = lora_dir / filename
        file.save(str(file_path))
        file_size = os.path.getsize(str(file_path))

        new_lora = LoraModelDB(
            name=lora_name, source_type="local", path=str(file_path),
            file_size=file_size, uploaded_by=user.id
        )
        db.session.add(new_lora)
        db.session.commit()

        return jsonify({"success": True, "message": f"LoRA '{lora_name}' uploaded successfully"})
    except Exception as e:
        current_app.logger.error(f"Error uploading LoRA: {e}")
        return jsonify({"success": False, "error": "Internal server error"}), 500

@bp.route('/spotify/api/loras')
def get_loras_api(): # Renamed to avoid conflict if 'get_loras' is a helper elsewhere
    try:
        # user = get_current_user() # Use this if endpoint is not @login_required
        # For now, assume it's public or auth is handled differently if needed
        db_loras = LoraModelDB.query.filter_by(source_type="local").all()
        loras_list = []

        # Potentially get current user to mark their LoRAs, even if endpoint is public
        current_user_obj = get_current_user()

        for db_lora in db_loras:
            if db_lora.path and os.path.exists(db_lora.path):
                lora_data = {
                    "name": db_lora.name, "source_type": "local",
                    "file_size": db_lora.file_size or 0,
                    "uploaded_at": db_lora.uploaded_at.isoformat() if db_lora.uploaded_at else None,
                    "can_delete": False, # Default
                    "uploaded_by_current_user": False # Default
                }
                if current_user_obj: # Add user-specific info if a user is logged in
                    lora_data["uploaded_by_current_user"] = (db_lora.uploaded_by == current_user_obj.id)
                    lora_data["can_delete"] = (db_lora.uploaded_by == current_user_obj.id or current_user_obj.is_admin()) # Example admin check

                loras_list.append(lora_data)
        return jsonify({"loras": loras_list})
    except Exception as e:
        current_app.logger.error(f"Error getting LoRAs: {e}")
        return jsonify({"loras": []}) # Return empty list on error

@bp.route('/spotify/api/delete_lora', methods=['DELETE'])
@login_required
@limiter.limit("10 per hour")
def delete_lora(user):
    try:
        data = request.get_json()
        lora_name = data.get('name', '').strip()
        if not lora_name:
            return jsonify({"success": False, "error": "LoRA name is required"}), 400

        lora_record = LoraModelDB.query.filter_by(name=lora_name).first()
        if not lora_record:
            return jsonify({"success": False, "error": "LoRA not found"}), 404

        # Assuming User model has is_admin() method
        if not user.is_admin() and lora_record.uploaded_by != user.id:
            return jsonify({"success": False, "error": "You do not have permission to delete this LoRA."}), 403

        if lora_record.path and os.path.exists(lora_record.path):
            try:
                os.remove(lora_record.path)
            except Exception as e:
                current_app.logger.warning(f"Could not delete file {lora_record.path}: {e}")

        db.session.delete(lora_record)
        db.session.commit()
        return jsonify({"success": True, "message": f"LoRA '{lora_name}' deleted successfully"})
    except Exception as e:
        current_app.logger.error(f"Error deleting LoRA: {e}")
        db.session.rollback()
        return jsonify({"success": False, "error": "Internal server error"}), 500

@bp.route('/spotify-login')
def spotify_login():
    spotify_client_id = current_app.config.get('SPOTIFY_CLIENT_ID')
    spotify_redirect_uri = current_app.config.get('SPOTIFY_REDIRECT_URI')

    if not spotify_client_id:
        flash('Spotify integration is not configured.', 'error')
        return redirect(url_for('main.generate')) # Redirect to main blueprint's generate

    try:
        state = secrets.token_urlsafe(32)
        oauth_state = SpotifyState(state=state)
        db.session.add(oauth_state)
        db.session.commit()

        scope = 'playlist-read-private playlist-modify-public playlist-modify-private ugc-image-upload user-read-email user-read-private'
        auth_url = (
            'https://accounts.spotify.com/authorize?'
            f'client_id={spotify_client_id}&response_type=code&'
            f'redirect_uri={spotify_redirect_uri}&scope={scope}&state={state}'
        )
        return redirect(auth_url)
    except Exception as e:
        current_app.logger.error(f"Spotify login error: {e}")
        flash('Failed to initiate Spotify login. Please try again.', 'error')
        return redirect(url_for('main.generate')) # Redirect to main blueprint

@bp.route('/spotify-callback')
def spotify_callback():
    spotify_client_id = current_app.config.get('SPOTIFY_CLIENT_ID')
    spotify_client_secret = current_app.config.get('SPOTIFY_CLIENT_SECRET')
    spotify_redirect_uri = current_app.config.get('SPOTIFY_REDIRECT_URI')

    try:
        code = request.args.get('code')
        state = request.args.get('state')
        error = request.args.get('error')

        if error:
            flash(f'Spotify authorization failed: {error}', 'error')
            return redirect(url_for('main.generate'))
        if not code or not state:
            flash('Invalid Spotify callback parameters.', 'error')
            return redirect(url_for('main.generate'))

        oauth_state = SpotifyState.query.filter_by(state=state, used=False).first()
        if not oauth_state or oauth_state.created_at < datetime.datetime.utcnow() - timedelta(minutes=10):
            flash('Invalid or expired state parameter for Spotify OAuth.', 'error')
            return redirect(url_for('main.generate'))

        oauth_state.used = True
        db.session.commit() # Commit early to mark state as used

        token_data = {
            'grant_type': 'authorization_code', 'code': code, 'redirect_uri': spotify_redirect_uri,
            'client_id': spotify_client_id, 'client_secret': spotify_client_secret
        }
        response = requests.post('https://accounts.spotify.com/api/token', data=token_data)
        if response.status_code != 200:
            flash('Failed to retrieve Spotify access tokens.', 'error')
            current_app.logger.error(f"Spotify token exchange failed: {response.text}")
            return redirect(url_for('main.generate'))

        tokens = response.json()
        access_token = tokens['access_token']
        refresh_token = tokens.get('refresh_token')
        expires_in = tokens.get('expires_in', 3600)

        headers = {'Authorization': f'Bearer {access_token}'}
        user_response = requests.get('https://api.spotify.com/v1/me', headers=headers)
        if user_response.status_code != 200:
            flash('Failed to retrieve Spotify user information.', 'error')
            return redirect(url_for('main.generate'))

        spotify_user_data = user_response.json()
        spotify_id = spotify_user_data['id']

        user = User.query.filter_by(spotify_id=spotify_id).first()
        if not user:
            user = User(
                spotify_id=spotify_id,
                spotify_username=spotify_user_data.get('id'), # Spotify ID is often used as username
                display_name=spotify_user_data.get('display_name', spotify_user_data.get('id')),
                email=spotify_user_data.get('email'), # Email might be null
                is_premium=False # Default, can be updated based on subscription if available
            )
            db.session.add(user)
        else: # Update existing user details
            user.display_name = spotify_user_data.get('display_name', user.display_name)
            if spotify_user_data.get('email'): # Only update email if provided
                 user.email = spotify_user_data.get('email')

        user.spotify_access_token = access_token
        user.spotify_refresh_token = refresh_token
        user.spotify_token_expires = datetime.datetime.utcnow() + timedelta(seconds=expires_in)
        user.last_login = datetime.datetime.utcnow()

        # Create a new login session for this Spotify login
        session_token_val = secrets.token_urlsafe(32)
        new_login_session = LoginSession(
            user_id=user.id, session_token=session_token_val,
            expires_at=datetime.datetime.utcnow() + timedelta(days=30), # Align with cookie expiry
            ip_address=request.remote_addr, user_agent=request.headers.get('User-Agent', '')
        )
        db.session.add(new_login_session)
        db.session.commit()

        session['user_id'] = user.id
        session['user_session'] = session_token_val # Store new session token

        resp = make_response(redirect(url_for('main.generate'))) # Redirect to main blueprint
        resp.set_cookie('session_token', session_token_val, max_age=30*24*60*60, httponly=True, samesite='Lax')

        flash_message = '🌟 Welcome back, Premium user! You have unlimited generations.' if user.is_premium_user() else 'Successfully connected to Spotify! You have 2 daily generations.'
        flash(flash_message, 'success')
        return resp

    except Exception as e:
        current_app.logger.error(f"Spotify callback error: {e}")
        db.session.rollback() # Rollback any partial DB changes on error
        flash('An error occurred during Spotify authorization. Please try again.', 'error')
        return redirect(url_for('main.generate'))


@bp.route('/spotify/api/upload_info')
@login_required
def get_upload_info(user):
    try:
        # User object is passed by @login_required
        current_lora_count = LoraModelDB.query.filter_by(source_type="local", uploaded_by=user.id).count()

        # Max LoRAs for non-premium could be defined in app.config
        max_loras_non_premium = current_app.config.get('MAX_LORAS_NON_PREMIUM', 2)

        if user.is_premium_user():
            can_upload = True
            limit_desc = "unlimited"
        else:
            can_upload = current_lora_count < max_loras_non_premium
            limit_desc = str(max_loras_non_premium)

        return jsonify({
            "can_upload": can_upload,
            "current_count": current_lora_count,
            "limit": limit_desc,
            "is_premium": user.is_premium_user()
        })
    except Exception as e:
        current_app.logger.error(f"Error getting upload info for user {user.id}: {e}")
        return jsonify({"error": "Internal server error"}), 500
