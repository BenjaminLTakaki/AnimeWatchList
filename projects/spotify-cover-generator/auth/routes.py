from flask import (current_app, redirect, url_for, render_template,
                   session, flash, request, make_response)
import secrets
import datetime
from datetime import timedelta # Ensure timedelta is imported
from werkzeug.security import generate_password_hash, check_password_hash

from extensions import db
from models import User, LoginSession, GenerationResultDB # GenerationResultDB for profile stats
from ..decorators import login_required
# get_current_user is used by login_required, but if we need user obj directly without login_required:
from ..auth_utils import get_current_user

from . import bp
from ..models import LoginSession
from flask import make_response
@bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        if not username or not password:
            flash('Please enter both username and password', 'error')
            return render_template('login.html')

        try:
            user = User.query.filter_by(username=username).first()
            if user and user.password_hash and check_password_hash(user.password_hash, password):
                session_token = secrets.token_urlsafe(32)
                login_session = LoginSession(
                    user_id=user.id, session_token=session_token,
                    expires_at=datetime.datetime.utcnow() + timedelta(days=30),
                    ip_address=request.remote_addr,
                    user_agent=request.headers.get('User-Agent', '')
                )
                db.session.add(login_session)
                user.last_login = datetime.datetime.utcnow()
                db.session.commit()

                session['user_id'] = user.id # For session-based user loading
                session['user_session'] = session_token # For cookie-based user loading

                resp = make_response(redirect(url_for('main.generate'))) # Redirect to main.generate
                resp.set_cookie('session_token', session_token, max_age=30*24*60*60, httponly=True, samesite='Lax')

                flash('Logged in successfully!', 'success')
                return resp
            else:
                flash('Invalid username or password', 'error')
        except Exception as e:
            current_app.logger.error(f"Login error: {e}")
            flash('Login failed. Please try again.', 'error')

    return render_template('login.html')

@bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

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
            if User.query.filter_by(email=email).first():
                flash('Email already registered.', 'error')
                return render_template('register.html')
            if User.query.filter_by(username=username).first():
                flash('Username already taken.', 'error')
                return render_template('register.html')

            password_hash = generate_password_hash(password)
            new_user = User(
                email=email, username=username,
                display_name=username, password_hash=password_hash
            )
            db.session.add(new_user)
            db.session.commit()

            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('auth.login')) # Redirect to auth.login

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Registration error: {e}")
            flash('Registration failed. Please try again.', 'error')

    return render_template('register.html')

@bp.route('/logout')
def logout():
    try:
        if 'user_session' in session:
            session_token = session['user_session']
            login_session_obj = LoginSession.query.filter_by(session_token=session_token).first()
            if login_session_obj:
                login_session_obj.is_active = False
                db.session.commit()

        session.clear()
        resp = make_response(redirect(url_for('main.generate'))) # Redirect to main.generate
        resp.set_cookie('session_token', '', expires=0)
        flash('You have been logged out.', 'info')
        return resp

    except Exception as e:
        current_app.logger.error(f"Logout error: {e}")
        session.clear() # Ensure session is cleared even on error
        # Redirect to a safe page, main.generate is a good default
        resp = make_response(redirect(url_for('main.generate')))
        resp.set_cookie('session_token', '', expires=0) # Attempt to clear cookie even on error
        flash('An error occurred during logout. Your session has been cleared.', 'warning')
        return resp


@bp.route('/profile')
@login_required # This decorator passes the 'user' object
def profile(user): # user object is passed by login_required
    try:
        # The 'user' object is already provided by the @login_required decorator
        total_generations = GenerationResultDB.query.filter_by(user_id=user.id).count()
        # User methods should be available on the user object
        generations_today = user.get_generations_today()
        daily_limit = user.get_daily_generation_limit()
        can_generate_today = user.can_generate_today()

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
            'can_generate': can_generate_today,
            'recent_generations': recent_generations,
            'spotify_connected': bool(user.spotify_access_token),
            'is_premium': user.is_premium_user()
        }
        return render_template('profile.html', **profile_data)

    except Exception as e:
        current_app.logger.error(f"Profile error for user {user.id if user else 'Unknown'}: {e}")
        flash('Error loading profile. Please try again.', 'error')
        return redirect(url_for('main.generate')) # Redirect to main.generate

from ..decorators import admin_required # Ensure this is imported

@bp.route('/admin-only-test')
@login_required
@admin_required # Uses the decorator we want to test
def admin_only_page(user): # Will receive user from login_required/admin_required
    return "Admin Page Content", 200
