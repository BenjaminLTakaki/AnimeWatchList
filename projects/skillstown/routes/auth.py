"""Authentication blueprint for user registration and login."""
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import current_user, login_required

try:
    from forms import LoginForm, RegistrationForm
    from services.auth_service import AuthService
    from utils.url_helpers import get_url_for
except ImportError:
    from skillstown.forms import LoginForm, RegistrationForm
    from skillstown.services.auth_service import AuthService
    from skillstown.utils.url_helpers import get_url_for

# Create blueprint
auth_bp = Blueprint('auth', __name__, template_folder='../templates/auth')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """User login route."""
    if current_user.is_authenticated:
        return redirect(get_url_for('main.index'))
    
    form = LoginForm()
    if form.validate_on_submit():
        success, user, error = AuthService.login_user(
            email=form.email.data,
            password=form.password.data,
            remember=form.remember.data
        )
        
        if success:
            next_page = request.args.get('next')
            flash('Login successful!', 'success')
            return redirect(next_page) if next_page else redirect(get_url_for('main.index'))
            
        flash(error, 'danger')
    
    return render_template('auth/login.html', form=form)

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """User registration route."""
    if current_user.is_authenticated:
        return redirect(get_url_for('main.index'))
    
    form = RegistrationForm()
    if form.validate_on_submit():
        user, error = AuthService.register_user(
            username=form.username.data,
            email=form.email.data,
            password=form.password.data
        )
        
        if user:
            flash('Registration successful! Please login.', 'success')
            return redirect(get_url_for('auth.login'))
            
        flash(error, 'danger')
    
    return render_template('auth/register.html', form=form)

@auth_bp.route('/logout')
@login_required
def logout():
    """User logout route."""
    AuthService.logout()
    flash('You have been logged out.', 'info')
    return redirect(get_url_for('main.index'))