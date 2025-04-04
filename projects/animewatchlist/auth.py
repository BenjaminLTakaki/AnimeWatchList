import os
import datetime
from flask import Flask, redirect, url_for, flash, render_template, request
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

# Initialize globals that will be set by init_auth
get_url_for = None
get_status_counts = None
auth_routes = {}

def init_auth(app, get_url_for_func, get_status_counts_func):
    """
    Initialize authentication system with the main app.
    
    Args:
        app: Flask application instance
        get_url_for_func: Function to generate URLs (imported from main app)
        get_status_counts_func: Function to get status counts (imported from user_data)
    """
    # Configure database
    database_uri = os.environ.get('DATABASE_URL', 'postgresql://postgres:password@localhost/animewatchlist')
    
    # Fix for Render PostgreSQL URLs
    if database_uri.startswith('postgres://'):
        database_uri = database_uri.replace('postgres://', 'postgresql://', 1)
    
    app.config['SQLALCHEMY_DATABASE_URI'] = database_uri
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Initialize database with app
    db.init_app(app)
    
    # Store the functions as globals accessible within this module
    global get_url_for, get_status_counts
    get_url_for = get_url_for_func
    get_status_counts = get_status_counts_func
    
    # Initialize LoginManager
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'login'
    login_manager.login_message_category = 'info'
    
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
    
    # Create database tables
    with app.app_context():
        db.create_all()
    
    # Register routes
    app.add_url_rule('/register', view_func=register, methods=['GET', 'POST'])
    app.add_url_rule('/login', view_func=login, methods=['GET', 'POST'])
    app.add_url_rule('/logout', view_func=logout)
    app.add_url_rule('/profile', view_func=profile)
    
    # Store auth route functions in a global dict for access from outside
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
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(username=form.username.data, email=form.email.data)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('Your account has been created! You can now log in.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html', title='Register', form=form, get_url_for=get_url_for)

def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and user.check_password(form.password.data):
            login_user(user, remember=form.remember.data)
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('index'))
        else:
            flash('Login unsuccessful. Please check your email and password.', 'danger')
    
    return render_template('login.html', title='Login', form=form, get_url_for=get_url_for)

def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

@login_required
def profile():
    watched_count, not_watched_count = get_status_counts(current_user.id)
    return render_template('profile.html', 
                          title='Profile', 
                          user=current_user, 
                          watched_count=watched_count, 
                          not_watched_count=not_watched_count, 
                          get_url_for=get_url_for)