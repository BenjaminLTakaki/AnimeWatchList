from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
import os
import sys
import json
import re
from werkzeug.utils import secure_filename
import PyPDF2
import docx
from collections import Counter, defaultdict
from flask_login import LoginManager, current_user, login_required, login_user
import google.generativeai as genai
import requests

# Add animewatchlist path to import its modules
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
animewatchlist_path = os.path.join(project_root, 'animewatchlist')
sys.path.insert(0, animewatchlist_path)

# Import auth system from animewatchlist
try:
    from auth import User, db
except ImportError:
    print("ERROR: Could not import auth system from animewatchlist.")
    print("Make sure the animewatchlist project is properly set up.")
    # Create fallback auth for development
    from flask_sqlalchemy import SQLAlchemy
    db = SQLAlchemy()
    class User:
        pass

# Check if running in the portfolio environment
is_production = os.environ.get('RENDER', False)
app = Flask(
    __name__,
    static_url_path='/static' if not is_production else '/skillstown/static',
    template_folder='templates'
)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "skillstown_secret")

# Configure upload folder
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf', 'docx', 'txt'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Define the path to user_courses.json
DATA_DIR = os.path.join('data')
USER_COURSES_FILE = os.path.join(DATA_DIR, 'user_courses.json')

# Ensure required directories exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

# Initialize Google Generative AI with API key
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
else:
    print("WARNING: GEMINI_API_KEY not set. CV analysis will be limited.")

# Database configuration
database_url = os.environ.get('DATABASE_URL')
# If DATABASE_URL is not set, log an error
if not database_url:
    print("ERROR: DATABASE_URL environment variable is not set!")
    # Fallback to a development database for local use only
    database_url = 'sqlite:///test.db'

# Fix for Render PostgreSQL URLs
if database_url and database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

# Initialize LoginManager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Custom DB model for enrolling in user courses
class UserCourse(db.Model):
    __tablename__ = 'user_courses'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    category = db.Column(db.String(100), nullable=False)
    course_name = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(50), default='enrolled') # enrolled, in_progress, completed
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    
    # Define relationship
    user = db.relationship('User', backref='enrolled_courses')
    
    __table_args__ = (
        db.UniqueConstraint('user_id', 'course_name', name='user_course_unique'),
    )

# Define helper function for URL generation
def get_url_for(*args, **kwargs):
    url = url_for(*args, **kwargs)
    if is_production and not url.startswith('/skillstown'):
        url = f"/skillstown{url}"
    return url

# Add context processor to inject variables into all templates
@app.context_processor
def inject_template_vars():
    enrolled_courses_count = 0
    if current_user.is_authenticated:
        enrolled_courses_count = UserCourse.query.filter_by(user_id=current_user.id).count()
    
    return {
        'get_url_for': get_url_for,
        'is_authenticated': lambda: current_user.is_authenticated,
        'enrolled_courses_count': enrolled_courses_count
    }

# Load course catalog from JSON file
def load_course_catalog():
    try:
        with open('projects/skillstown/static/data/course_catalog.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        # Try alternative path
        try:
            with open('static/data/course_catalog.json', 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            # If the file doesn't exist, return an empty catalog
            return {"categories": []}

# Helper function to check allowed file extension
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Extract text from PDF files
def extract_text_from_pdf(file_path):
    text = ""
    with open(file_path, 'rb') as file:
        reader = PyPDF2.PdfReader(file)
        for page_num in range(len(reader.pages)):
            page = reader.pages[page_num]
            text += page.extract_text()
    return text

# Extract text from DOCX files
def extract_text_from_docx(file_path):
    doc = docx.Document(file_path)
    return " ".join([paragraph.text for paragraph in doc.paragraphs])

# Extract text from TXT files
def extract_text_from_txt(file_path):
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
        return file.read()

# Analysis of a CV using Gemini API
def analyze_cv_with_gemini(text):
    if not GEMINI_API_KEY:
        # Fallback to basic analysis if API key is not available
        return basic_cv_analysis(text)
    
    try:
        # Initialize the Gemini model
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # Prepare the prompt for Gemini
        prompt = f"""
        I need a professional analysis of this CV/resume text. Please:
        
        1. Identify all technical skills (programming languages, tools, frameworks, etc.)
        2. Identify all soft skills (communication, leadership, etc.)
        3. Identify all domain knowledge areas (finance, healthcare, etc.)
        4. Assess skill levels for each skill (beginner, intermediate, advanced, expert)
        5. Suggest 3-5 skill areas where the person could improve or expand their knowledge
        6. Recommend 3-5 career development paths based on their current skills
        
        Format the response as JSON with these exact keys:
        {{
            "technical_skills": [{{skill: "name", level: "level"}}],
            "soft_skills": [{{skill: "name", level: "level"}}],
            "domain_knowledge": [{{area: "name", level: "level"}}],
            "development_areas": ["area1", "area2"...],
            "career_paths": ["path1", "path2"...]
        }}
        
        Here's the CV text:
        
        {text}
        """
        
        # Generate the response
        response = model.generate_content(prompt)
        
        # Extract the JSON part from the response
        result_text = response.text
        
        # Sometimes the model includes "```json" and "```" around the JSON
        if "```json" in result_text:
            result_text = result_text.split("```json")[1].split("```")[0].strip()
        elif "```" in result_text:
            result_text = result_text.split("```")[1].split("```")[0].strip()
        
        # Parse the JSON
        result = json.loads(result_text)
        return result
    
    except Exception as e:
        print(f"Error with Gemini API: {e}")
        # Fallback to basic analysis if Gemini fails
        return basic_cv_analysis(text)

# Basic CV analysis as fallback if Gemini API is unavailable
def basic_cv_analysis(text):
    # Lowercase the text for better matching
    text = text.lower()
    
    # Simple skill extraction based on common terms
    skills = {
        "technical_skills": [],
        "soft_skills": [],
        "domain_knowledge": [],
        "development_areas": ["Data Analysis", "Project Management", "Cloud Computing"],
        "career_paths": ["Software Development", "Business Analysis", "IT Support"]
    }
    
    # Basic technical skills to check
    tech_skills = ["python", "java", "javascript", "html", "css", "sql", "excel", 
                  "word", "powerpoint", "data analysis", "machine learning"]
    
    # Basic soft skills to check
    soft_skills = ["communication", "leadership", "teamwork", "problem solving", 
                  "time management", "organization", "creativity"]
    
    # Basic domain knowledge areas
    domains = ["finance", "marketing", "sales", "healthcare", "education", 
              "manufacturing", "retail", "technology"]
    
    # Check for technical skills
    for skill in tech_skills:
        if re.search(r'\b' + re.escape(skill) + r'\b', text):
            # Simple logic to guess skill level based on how many times it appears
            count = len(re.findall(r'\b' + re.escape(skill) + r'\b', text))
            level = "beginner"
            if count > 3:
                level = "intermediate"
            if count > 6:
                level = "advanced"
            skills["technical_skills"].append({"skill": skill, "level": level})
    
    # Check for soft skills
    for skill in soft_skills:
        if re.search(r'\b' + re.escape(skill) + r'\b', text):
            skills["soft_skills"].append({"skill": skill, "level": "intermediate"})
    
    # Check for domain knowledge
    for domain in domains:
        if re.search(r'\b' + re.escape(domain) + r'\b', text):
            skills["domain_knowledge"].append({"area": domain, "level": "intermediate"})
    
    return skills

# Recommend courses based on extracted skills
def recommend_courses(skills_data, course_catalog):
    recommendations = []
    seen_courses = set()
    
    # Collect all skills from the analysis
    all_skills = []
    
    # Add technical skills
    for skill_info in skills_data.get("technical_skills", []):
        all_skills.append({"name": skill_info["skill"], "weight": 3})
    
    # Add soft skills
    for skill_info in skills_data.get("soft_skills", []):
        all_skills.append({"name": skill_info["skill"], "weight": 2})
    
    # Add domain knowledge
    for domain_info in skills_data.get("domain_knowledge", []):
        all_skills.append({"name": domain_info["area"], "weight": 2})
    
    # Add development areas (these should be prioritized)
    for area in skills_data.get("development_areas", []):
        all_skills.append({"name": area.lower(), "weight": 4})
    
    # For each category and course in the catalog
    for category in course_catalog["categories"]:
        category_name = category["name"]
        category_courses = category["courses"]
        
        for course in category_courses:
            course_name = course["name"]
            course_description = course.get("description", "")
            course_key = f"{category_name}:{course_name}"  # Create a unique key for the course
            
            # Skip if we've already added this course
            if course_key in seen_courses:
                continue
            
            # Check if any skill matches the course name or description
            match_score = 0
            matching_skills = []
            
            for skill in all_skills:
                skill_name = skill["name"].lower()
                skill_weight = skill["weight"]
                
                # Check for skill in course name (stronger match)
                if skill_name in course_name.lower():
                    match_score += 2 * skill_weight
                    matching_skills.append(skill_name)
                # Check for skill in course description
                elif course_description and skill_name in course_description.lower():
                    match_score += 1 * skill_weight
                    matching_skills.append(skill_name)
            
            # If we have a match, add to recommendations
            if match_score > 0 and matching_skills:
                recommendations.append({
                    "category": category_name,
                    "course": course_name,
                    "description": course_description,
                    "match_score": match_score,
                    "matching_skills": list(set(matching_skills))  # Remove duplicates
                })
                seen_courses.add(course_key)
    
    # Sort recommendations by match score (highest first)
    recommendations.sort(key=lambda x: x["match_score"], reverse=True)
    
    # Limit to top 15 recommendations
    return recommendations[:15]

# Search courses by keyword
def search_courses(query, course_catalog):
    results = []
    seen_courses = set()
    
    # Clean and normalize the query
    query = query.lower().strip()
    
    # For each category and course in the catalog
    for category in course_catalog["categories"]:
        category_name = category["name"]
        category_courses = category["courses"]
        
        for course in category_courses:
            course_name = course["name"]
            course_description = course.get("description", "")
            course_key = f"{category_name}:{course_name}"
            
            # Skip if we've already added this course
            if course_key in seen_courses:
                continue
            
            # Calculate relevance score
            relevance_score = 0
            
            # Exact match in course name (highest priority)
            if query == course_name.lower():
                relevance_score += 100
            # Query appears as a word or phrase in course name
            elif query in course_name.lower():
                relevance_score += 75
            # Query words all appear in course name
            elif all(word in course_name.lower() for word in query.split()):
                relevance_score += 50
            # Query appears in description
            elif course_description and query in course_description.lower():
                relevance_score += 25
            # Query words all appear in description
            elif course_description and all(word in course_description.lower() for word in query.split()):
                relevance_score += 15
            # Some query words appear in name or description
            else:
                query_words = query.split()
                name_matches = sum(1 for word in query_words if word in course_name.lower())
                desc_matches = 0
                if course_description:
                    desc_matches = sum(1 for word in query_words if word in course_description.lower())
                
                # Weight name matches higher than description matches
                word_score = (name_matches * 5) + (desc_matches * 2)
                if word_score > 0:
                    relevance_score += word_score
            
            # Only include results with non-zero relevance
            if relevance_score > 0:
                results.append({
                    "category": category_name,
                    "course": course_name,
                    "description": course_description,
                    "relevance_score": relevance_score
                })
                seen_courses.add(course_key)
    
    # Sort by relevance score
    results.sort(key=lambda x: x["relevance_score"], reverse=True)
    
    return results

# Get enrolled courses for a user
def get_enrolled_courses(user_id):
    user_courses = UserCourse.query.filter_by(user_id=user_id).all()
    return [
        {
            "id": course.id,
            "category": course.category,
            "course": course.course_name,
            "status": course.status,
            "created_at": course.created_at.strftime("%Y-%m-%d")
        }
        for course in user_courses
    ]

# Enroll in a course for a user
def enroll_in_course(user_id, category, course_name, status="enrolled"):
    # Check if already enrolled
    existing = UserCourse.query.filter_by(
        user_id=user_id, 
        course_name=course_name
    ).first()
    
    if existing:
        # Update status if it changed
        if existing.status != status:
            existing.status = status
            db.session.commit()
        return False  # Not a new enrollment
    
    # Create new enrollment
    user_course = UserCourse(
        user_id=user_id,
        category=category,
        course_name=course_name,
        status=status
    )
    
    db.session.add(user_course)
    db.session.commit()
    return True  # New enrollment

# Remove an enrolled course
def remove_enrolled_course(user_id, course_id):
    course = UserCourse.query.filter_by(id=course_id, user_id=user_id).first()
    if course:
        db.session.delete(course)
        db.session.commit()
        return True
    return False

# Update course status
def update_course_status(user_id, course_id, new_status):
    course = UserCourse.query.filter_by(id=course_id, user_id=user_id).first()
    if course:
        course.status = new_status
        db.session.commit()
        return True
    return False

# Create database tables
with app.app_context():
    try:
        db.create_all()
        print("Database tables created successfully!")
    except Exception as e:
        print(f"Error creating database tables: {e}")

# Import forms from animewatchlist
try:
    from auth import LoginForm, RegistrationForm
except ImportError:
    # Create fallback forms if import fails
    from flask_wtf import FlaskForm
    from wtforms import StringField, PasswordField, SubmitField, BooleanField
    from wtforms.validators import DataRequired, Length, Email, EqualTo
    
    class LoginForm(FlaskForm):
        email = StringField('Email', validators=[DataRequired(), Email()])
        password = PasswordField('Password', validators=[DataRequired()])
        remember = BooleanField('Remember Me')
        submit = SubmitField('Login')
    
    class RegistrationForm(FlaskForm):
        username = StringField('Username', validators=[DataRequired(), Length(min=4, max=25)])
        email = StringField('Email', validators=[DataRequired(), Email()])
        password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
        confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
        submit = SubmitField('Sign Up')

# Routes
@app.route('/')
def index():
    # If user is authenticated, get enrolled courses count
    enrolled_courses_count = 0
    if current_user.is_authenticated:
        enrolled_courses_count = UserCourse.query.filter_by(user_id=current_user.id).count()
    
    return render_template('index.html', enrolled_courses_count=enrolled_courses_count)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(get_url_for('index'))
    
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and user.check_password(form.password.data):
            login_user(user, remember=form.remember.data)
            next_page = request.args.get('next')
            flash('You have been logged in successfully!', 'success')
            return redirect(next_page) if next_page else redirect(get_url_for('index'))
        else:
            flash('Login unsuccessful. Please check your email and password.', 'danger')
    
    return render_template('login.html', form=form)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(get_url_for('index'))
    
    form = RegistrationForm()
    if form.validate_on_submit():
        # Check if username or email already exists
        existing_user = User.query.filter(
            (User.username == form.username.data) | 
            (User.email == form.email.data)
        ).first()
        
        if existing_user:
            if existing_user.username == form.username.data:
                flash('Username already exists. Please choose a different one.', 'danger')
            else:
                flash('Email already registered. Please use a different email or login.', 'danger')
        else:
            user = User(username=form.username.data, email=form.email.data)
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()
            flash('Your account has been created! You can now log in.', 'success')
            return redirect(get_url_for('login'))
    
    return render_template('register.html', form=form)

@app.route('/logout')
def logout():
    from flask_login import logout_user
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(get_url_for('index'))

@app.route('/profile')
@login_required
def profile():
    # Get user's course statistics
    enrolled_courses_count = UserCourse.query.filter_by(user_id=current_user.id).count()
    in_progress_count = UserCourse.query.filter_by(user_id=current_user.id, status='in_progress').count()
    completed_count = UserCourse.query.filter_by(user_id=current_user.id, status='completed').count()
    
    # Calculate completion percentage
    if enrolled_courses_count > 0:
        completion_percentage = round((completed_count / enrolled_courses_count) * 100)
    else:
        completion_percentage = 0
    
    # Get recent courses (last 5)
    recent_courses = UserCourse.query.filter_by(user_id=current_user.id)\
                                   .order_by(UserCourse.created_at.desc())\
                                   .limit(5).all()
    
    # Format recent courses for display
    recent_courses_data = []
    for course in recent_courses:
        recent_courses_data.append({
            'course': course.course_name,
            'category': course.category,
            'status': course.status,
            'created_at': course.created_at.strftime("%B %d, %Y")
        })
    
    # Get member since date (assuming we can get it from the user model)
    member_since = "January 2025"  # Placeholder - you might want to add a created_at field to User model
    
    return render_template('profile.html',
                         enrolled_courses_count=enrolled_courses_count,
                         in_progress_count=in_progress_count,
                         completed_count=completed_count,
                         completion_percentage=completion_percentage,
                         recent_courses=recent_courses_data,
                         member_since=member_since)

@app.route('/login_redirect')
def login_redirect():
    """Redirect to login page with next parameter"""
    return redirect(get_url_for('login', next=request.args.get('next', get_url_for('index'))))

@app.route('/upload', methods=['POST'])
def upload_file():
    # Check if a file was submitted
    if 'file' not in request.files:
        flash('No file part')
        return redirect(request.url)
    
    file = request.files['file']
    
    # Check if user submitted an empty form
    if file.filename == '':
        flash('No selected file')
        return redirect(request.url)
    
    # Check if the file has an allowed extension
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        
        # Extract text based on file type
        text = ""
        file_ext = filename.rsplit('.', 1)[1].lower()
        
        try:
            if file_ext == 'pdf':
                text = extract_text_from_pdf(file_path)
            elif file_ext == 'docx':
                text = extract_text_from_docx(file_path)
            elif file_ext == 'txt':
                text = extract_text_from_txt(file_path)
                
            # Analyze the CV
            skills_data = analyze_cv_with_gemini(text)
            
            # Load course catalog
            course_catalog = load_course_catalog()
            
            # Recommend courses based on extracted skills
            recommendations = recommend_courses(skills_data, course_catalog)
            
            return render_template('results.html', 
                                  skills_data=skills_data, 
                                  recommendations=recommendations,
                                  filename=filename)
        
        except Exception as e:
            flash(f'Error processing file: {str(e)}')
            return redirect(request.url)
    else:
        flash('File type not allowed. Please upload a PDF, DOCX, or TXT file.')
        return redirect(request.url)

@app.route('/search', methods=['GET', 'POST'])
def search():
    results = []
    query = request.args.get("query", "") or request.form.get("query", "")
    
    if query:
        # Load course catalog
        course_catalog = load_course_catalog()
        
        # Search courses
        results = search_courses(query, course_catalog)
        
        # No results message
        if not results:
            flash("No courses found matching your search term. Try a different term or upload your CV for personalized recommendations.")
    
    return render_template('search.html', results=results, query=query)

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/enrolled-courses')
@login_required
def enrolled_courses():
    courses = get_enrolled_courses(current_user.id)
    return render_template('enrolled_courses.html', courses=courses)

@app.route('/enroll-course', methods=['POST'])
@login_required
def enroll_course_route():
    category = request.form.get('category')
    course_name = request.form.get('course')
    
    if not category or not course_name:
        return jsonify({'success': False, 'message': 'Missing required information'})
    
    result = enroll_in_course(current_user.id, category, course_name)
    
    if result:
        message = f"Successfully enrolled in '{course_name}'!"
    else:
        message = f"You are already enrolled in '{course_name}'."
    
    return jsonify({'success': True, 'message': message})

@app.route('/remove-course/<int:course_id>', methods=['POST'])
@login_required
def remove_course(course_id):
    result = remove_enrolled_course(current_user.id, course_id)
    
    if result:
        flash("Course has been removed from your enrolled courses.")
    else:
        flash("Course not found or not associated with your account.")
    
    return redirect(url_for('enrolled_courses'))

@app.route('/update-course-status/<int:course_id>', methods=['POST'])
@login_required
def update_status(course_id):
    new_status = request.form.get('status')
    
    if not new_status or new_status not in ['saved', 'in_progress', 'completed']:
        flash("Invalid status selected.")
        return redirect(url_for('enrolled_courses'))
    
    result = update_course_status(current_user.id, course_id, new_status)
    
    if result:
        flash(f"Course status updated to: {new_status}")
    else:
        flash("Course not found or not associated with your account.")
    
    return redirect(url_for('saved_courses'))

@app.route('/assessment')
def assessment():
    """Show the CV assessment page"""
    return render_template('assessment.html')

if __name__ == '__main__':
    app.run(debug=True)