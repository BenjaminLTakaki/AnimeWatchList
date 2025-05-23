# filepath: c:\Users\benta\Personal_Website\AnimeWatchList\projects\skillstown\app.py
"""
SkillsTown Course Finder - Database-Integrated Application

This Flask application provides course search, CV analysis, user authentication,
and course enrollment functionality using a shared PostgreSQL database.
"""

import os
import datetime
import json
import re
import sys
import PyPDF2
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from sqlalchemy import inspect

# Production detection
is_production = os.getenv('RENDER') == 'true' or os.getenv('VERCEL') == '1'

def get_url_for(*args, **kwargs):
    url = url_for(*args, **kwargs)
    if is_production and not url.startswith('/skillstown'):
        url = f"/skillstown{url}"
    return url

# Import and initialize auth system from animewatchlist
animewatchlist_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'animewatchlist')
sys.path.insert(0, animewatchlist_path)

from auth import init_auth, User
from user_data import get_status_counts

# Create the Flask app
app = Flask(__name__)

# Configure the app
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'uploads')

# Set up static folder for production
if is_production:
    app.static_url_path = '/skillstown/static'

@app.context_processor
def inject_template_vars():
    return {
        'current_year': datetime.datetime.now().year,
        'get_url_for': get_url_for
    }

# Function to get SkillsTown user statistics (will be properly defined after models)
def get_skillstown_stats(user_id):
    """Get user statistics for SkillsTown courses"""
    # Placeholder function - will be redefined after models are created
    return {
        'total': 0,
        'enrolled': 0,
        'in_progress': 0,
        'completed': 0,
        'completion_percentage': 0
    }

# Initialize auth with skillstown-specific functions
db = init_auth(app, get_url_for, lambda user_id: get_skillstown_stats(user_id))

# Create base tables
with app.app_context():
    db.create_all()

# Define SkillsTown-specific models
class SkillsTownCourse(db.Model):
    __tablename__ = 'skillstown_courses'
    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(100), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    url = db.Column(db.String(500))
    provider = db.Column(db.String(100), default='SkillsTown')
    skills_taught = db.Column(db.Text)  # JSON string of skills
    difficulty_level = db.Column(db.String(20))  # Beginner, Intermediate, Advanced
    duration = db.Column(db.String(50))
    keywords = db.Column(db.Text)  # For search functionality
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

class UserCourse(db.Model):
    __tablename__ = 'skillstown_user_courses'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    category = db.Column(db.String(100), nullable=False)
    course_name = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(50), default='enrolled')  # enrolled, in_progress, completed
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    
    # Define relationship
    user = db.relationship('User', backref='skillstown_courses')
    
    __table_args__ = (
        db.UniqueConstraint('user_id', 'course_name', name='skillstown_user_course_unique'),
    )

class UserProfile(db.Model):
    __tablename__ = 'skillstown_user_profiles'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    cv_text = db.Column(db.Text)
    skills = db.Column(db.Text)  # JSON string of extracted skills
    uploaded_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    
    # Define relationship
    user = db.relationship('User', backref='skillstown_profile')

# Create SkillsTown tables
with app.app_context():
    db.create_all()

# Now properly redefine the stats function
def get_skillstown_stats(user_id):
    """Get user statistics for SkillsTown courses"""
    total = UserCourse.query.filter_by(user_id=user_id).count()
    enrolled = UserCourse.query.filter_by(user_id=user_id, status='enrolled').count()
    in_progress = UserCourse.query.filter_by(user_id=user_id, status='in_progress').count()
    completed = UserCourse.query.filter_by(user_id=user_id, status='completed').count()
    
    return {
        'total': total,
        'enrolled': enrolled,
        'in_progress': in_progress,
        'completed': completed,
        'completion_percentage': (completed / total * 100) if total > 0 else 0
    }

# Course service functions
COURSE_CATALOG_PATH = os.path.join(os.path.dirname(__file__), 'static', 'data', 'course_catalog.json')

def load_course_catalog():
    try:
        with open(COURSE_CATALOG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {"categories": []}

def search_courses(query, catalog=None):
    """Search courses with relevance scoring"""
    if not catalog:
        catalog = load_course_catalog()
    
    query = query.lower().strip()
    results = []
    
    for category in catalog.get("categories", []):
        for course in category.get("courses", []):
            score = calculate_relevance_score(query, course['name'], course.get('description', ''))
            
            if score > 0:
                results.append({
                    "category": category["name"],
                    "course": course["name"],
                    "description": course.get("description", ""),
                    "relevance_score": score
                })
    
    return sorted(results, key=lambda x: x["relevance_score"], reverse=True)

def calculate_relevance_score(query, title, description):
    """Calculate relevance score for a course"""
    score = 0
    query_words = query.split()
    
    for word in query_words:
        if word in title.lower():
            score += 3
        elif word in description.lower():
            score += 1
    
    return score

# Helper functions for CV processing
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() == 'pdf'

def extract_text_from_pdf(file_path):
    text = ""
    try:
        with open(file_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            for page in pdf_reader.pages:
                text += page.extract_text()
    except Exception as e:
        raise Exception(f"Error reading PDF: {str(e)}")
    return text

def extract_skills_from_text(text):
    # Common technical skills to look for
    skill_patterns = [
        r'\b(?:Python|Java|JavaScript|C\+\+|C#|PHP|Ruby|Swift|Kotlin)\b',
        r'\b(?:HTML|CSS|React|Angular|Vue|Node\.js|Express)\b',
        r'\b(?:SQL|MySQL|PostgreSQL|MongoDB|SQLite)\b',
        r'\b(?:Git|Docker|Kubernetes|AWS|Azure|GCP)\b',
        r'\b(?:Machine Learning|AI|Data Science|Analytics)\b',
        r'\b(?:Project Management|Agile|Scrum|Leadership)\b',
    ]
    
    skills = []
    
    for pattern in skill_patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            skill = match.group().strip()
            if skill not in skills:
                skills.append(skill)
    
    return skills

# Routes
@app.route("/")
def index():
    """Main SkillsTown index page"""
    catalog = load_course_catalog()
    categories = catalog.get("categories", [])[:6]  # Show first 6 categories
    
    return render_template('index.html', categories=categories, get_url_for=get_url_for)

@app.route("/search")
def search():
    """Search courses page"""
    query = request.args.get('query', '').strip()
    results = []
    
    if query:
        results = search_courses(query)
    
    return render_template('courses/search.html', 
                         query=query, 
                         results=results, 
                         get_url_for=get_url_for)

@app.route("/assessment")
@login_required
def assessment():
    """CV assessment page"""
    return render_template('assessment/assessment.html', get_url_for=get_url_for)

@app.route("/upload-cv", methods=['GET', 'POST'])
@login_required
def upload_cv():
    """Handle CV upload and analysis"""
    if request.method == 'POST':
        if 'cv_file' not in request.files:
            flash('No file selected.', 'danger')
            return redirect(request.url)
        
        file = request.files['cv_file']
        if file.filename == '':
            flash('No file selected.', 'danger')
            return redirect(request.url)
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            
            # Ensure upload directory exists
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            file.save(filepath)
            
            # Extract text from PDF
            try:
                cv_text = extract_text_from_pdf(filepath)
                skills = extract_skills_from_text(cv_text)
                
                # Save or update user profile
                profile = UserProfile.query.filter_by(user_id=current_user.id).first()
                if profile:
                    profile.cv_text = cv_text
                    profile.skills = json.dumps(skills)
                    profile.uploaded_at = db.func.current_timestamp()
                else:
                    profile = UserProfile(
                        user_id=current_user.id,
                        cv_text=cv_text,
                        skills=json.dumps(skills)
                    )
                    db.session.add(profile)
                
                db.session.commit()
                
                # Clean up uploaded file
                os.remove(filepath)
                
                flash('CV uploaded and analyzed successfully!', 'success')
                return redirect(url_for('cv_analysis'))
                
            except Exception as e:
                flash(f'Error processing CV: {str(e)}', 'danger')
                if os.path.exists(filepath):
                    os.remove(filepath)
        else:
            flash('Please upload a PDF file.', 'danger')
    
    return render_template('assessment/upload.html', get_url_for=get_url_for)

@app.route("/cv-analysis")
@login_required
def cv_analysis():
    """Show CV analysis results"""
    profile = UserProfile.query.filter_by(user_id=current_user.id).first()
    
    if not profile:
        flash('Please upload your CV first.', 'info')
        return redirect(url_for('upload_cv'))
    
    try:
        skills = json.loads(profile.skills) if profile.skills else []
    except:
        skills = []
    
    return render_template('assessment/results.html', 
                         profile=profile, 
                         skills=skills,
                         get_url_for=get_url_for)

@app.route("/my-courses")
@login_required
def my_courses():
    """User's enrolled courses"""
    courses = UserCourse.query.filter_by(user_id=current_user.id).order_by(UserCourse.created_at.desc()).all()
    stats = get_skillstown_stats(current_user.id)
    
    return render_template('courses/my_courses.html', 
                         courses=courses, 
                         stats=stats,
                         get_url_for=get_url_for)

@app.route("/enroll-course", methods=['POST'])
@login_required
def enroll_course():
    """Enroll in a course"""
    category = request.form.get('category')
    course_name = request.form.get('course')
    
    if not category or not course_name:
        return jsonify({'success': False, 'message': 'Missing course information'})
    
    # Check if already enrolled
    existing = UserCourse.query.filter_by(
        user_id=current_user.id,
        course_name=course_name
    ).first()
    
    if existing:
        return jsonify({'success': True, 'message': f'Already enrolled in {course_name}'})
    
    # Enroll
    course = UserCourse(
        user_id=current_user.id,
        category=category,
        course_name=course_name
    )
    db.session.add(course)
    db.session.commit()
    
    return jsonify({'success': True, 'message': f'Successfully enrolled in {course_name}!'})

@app.route("/update-course-status/<int:course_id>", methods=['POST'])
@login_required
def update_course_status(course_id):
    """Update course status"""
    status = request.form.get('status')
    
    course = UserCourse.query.filter_by(
        id=course_id,
        user_id=current_user.id
    ).first()
    
    if not course:
        flash('Course not found', 'error')
        return redirect(url_for('my_courses'))
    
    course.status = status
    db.session.commit()
    
    flash(f'Course status updated to {status}', 'success')
    return redirect(url_for('my_courses'))

@app.route("/dashboard")
@login_required
def dashboard():
    """User dashboard page"""
    stats = get_skillstown_stats(current_user.id)
    recent_courses = UserCourse.query.filter_by(user_id=current_user.id).order_by(UserCourse.created_at.desc()).limit(5).all()
    
    return render_template('profile.html', 
                         stats=stats,
                         recent_courses=recent_courses,
                         get_url_for=get_url_for)

@app.route("/about")
def about():
    """About page"""
    return render_template('about.html', get_url_for=get_url_for)

# Debug route to manually create tables if needed
@app.route("/debug/create_tables")
def create_tables_debug():
    """Manual route to create database tables."""
    try:
        with app.app_context():
            # Create auth tables
            db.create_all()
            
            # Create SkillsTown tables explicitly if needed
            inspector = inspect(db.engine)
            if 'skillstown_courses' not in inspector.get_table_names():
                SkillsTownCourse.__table__.create(db.engine)
            if 'skillstown_user_courses' not in inspector.get_table_names():
                UserCourse.__table__.create(db.engine)
            if 'skillstown_user_profiles' not in inspector.get_table_names():
                UserProfile.__table__.create(db.engine)
                
        flash("Database tables created successfully!")
    except Exception as e:
        flash(f"Error creating tables: {e}")
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
