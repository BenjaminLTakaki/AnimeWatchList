import os
import datetime
from flask import Flask, redirect, url_for, flash, render_template, request, current_app
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, BooleanField
from wtforms.validators import DataRequired, Length, Email, EqualTo, ValidationError

__all__ = ['init_auth', 'User', 'db']

# Initialize SQLAlchemy
db = SQLAlchemy()

# Define User model - Make it globally available
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# Registration form - Make it globally available
class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=4, max=25)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Sign Up')
    
    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user:
            raise ValidationError('That username is taken. Please choose a different one.')
            
    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError('That email is taken. Please choose a different one.')

# Login form - Make it globally available
class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember = BooleanField('Remember Me')
    submit = SubmitField('Login')

# Global store for auth route functions (remains for now, but consider app-specific storage if needed)
auth_routes = {}

def init_auth(app, get_url_for_func, get_status_counts_func):
    """
    Initialize authentication system with the main app.
    
    Args:
        app: Flask application instance
        get_url_for_func: Function to generate URLs (imported from main app)
        get_status_counts_func: Function to get status counts (imported from user_data)
    """
    # Configure database - ONLY use environment variables
    database_uri = os.environ.get('DATABASE_URL')
    
    # If DATABASE_URL is not set, log an error
    if not database_uri:
        print("ERROR: DATABASE_URL environment variable is not set!")
        print("Please set the DATABASE_URL environment variable with your PostgreSQL connection string.")
        # Fallback to a development database for local use only
        database_uri = 'sqlite:///test.db'
    
    # Fix for Render PostgreSQL URLs
    if database_uri and database_uri.startswith('postgres://'):
        database_uri = database_uri.replace('postgres://', 'postgresql://', 1)
    
    print(f"Using database URI: {database_uri}")  # Log the full URI for debugging
    
    app.config['SQLALCHEMY_DATABASE_URI'] = database_uri
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Initialize database with app
    db.init_app(app)
    
    # Store the app-specific functions in app.config
    app.config['AUTH_GET_URL_FOR'] = get_url_for_func
    app.config['AUTH_GET_STATUS_COUNTS'] = get_status_counts_func
    
    # Initialize LoginManager
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'login'  # Endpoint name for the login view
    login_manager.login_message_category = 'info'
    
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Create database tables
    with app.app_context():
        try:
            db.create_all()
            print("Database tables created successfully!")
        except Exception as e:
            print(f"Error creating database tables: {e}")
    
    # Register routes
    # Views will now use current_app.config to get their specific get_url_for and get_status_counts

    app.add_url_rule('/register', endpoint='register', view_func=register, methods=['GET', 'POST'])
    app.add_url_rule('/login', endpoint='login', view_func=login, methods=['GET', 'POST'])
    app.add_url_rule('/logout', endpoint='logout', view_func=logout, methods=['GET', 'POST'])
    app.add_url_rule('/profile', endpoint='profile', view_func=profile, methods=['GET', 'POST'])


    # Store auth route functions in a global dict for access from outside
    # This part might also need rethinking if multiple apps have different auth views for same names.
    # For now, assuming endpoint names like 'register', 'login' are consistent in what they point to functionally.
    global auth_routes
    auth_routes = {
        'register': register,
        'login': login,
        'logout': logout,
        'profile': profile
    }
    
    return db

# Route handlers
def register():
    guf = current_app.config['AUTH_GET_URL_FOR']
    if current_user.is_authenticated:
        return redirect(guf('profile'))  # Use guf
    form = RegistrationForm()
    if request.method == 'POST':
        print(f"Registration form submitted. Validating... Data: {form.data}") # DEBUG
        if form.validate_on_submit():
            print("Form validation successful.") # DEBUG
            user = User(username=form.username.data, email=form.email.data)
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()
            flash('Your account has been created! You are now able to log in.', 'success')
            login_user(user) # Log in the user automatically after registration
            return redirect(guf('profile'))  # Use guf
        else:
            print(f"Form validation failed. Errors: {form.errors}") # DEBUG
            # Explicitly flash errors if any for debugging, though template should show them
            for field, errors in form.errors.items():
                for error in errors:
                    flash(f"Error in {getattr(form, field).label.text}: {error}", 'danger')

    return render_template('register.html', title='Register', form=form, get_url_for=guf) # Use guf

def login():
    guf = current_app.config['AUTH_GET_URL_FOR']
    if current_user.is_authenticated:
        return redirect(guf('profile'))  # Use guf
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and user.check_password(form.password.data):
            login_user(user, remember=form.remember.data)
            next_page = request.args.get('next')
            flash('Login successful!', 'success')
            return redirect(guf(next_page[1:] if next_page and next_page.startswith('/') else 'profile')) # Use guf, ensure next_page is safe
        else:
            flash('Login unsuccessful. Please check email and password.', 'danger')
    return render_template('login.html', title='Login', form=form, get_url_for=guf) # Use guf

@login_required
def logout():
    guf = current_app.config['AUTH_GET_URL_FOR']
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(guf('login'))  # Use guf

@login_required
def profile():
    guf = current_app.config['AUTH_GET_URL_FOR']
    gsc = current_app.config['AUTH_GET_STATUS_COUNTS']
    # ... existing profile logic using gsc if needed ...
    status_counts = gsc(current_user.id) # Example usage of gsc
    return render_template('profile.html', title='Profile', status_counts=status_counts, get_url_for=guf) # Use guf