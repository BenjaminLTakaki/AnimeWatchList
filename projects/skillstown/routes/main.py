"""Main routes blueprint for SkillsTown app."""
from flask import Blueprint, render_template, redirect, url_for
from flask_login import current_user
from utils.url_helpers import get_url_for

# Create blueprint
main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    """Home page route."""
    return render_template('index.html')

@main_bp.route('/about')
def about():
    """About page route."""
    return render_template('about.html')

@main_bp.route('/profile')
def profile():
    """User profile page route."""
    if not current_user.is_authenticated:
        return redirect(get_url_for('auth.login'))
    return render_template('profile.html')
