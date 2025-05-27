import os
import datetime
import json
import re
import sys
import PyPDF2
import requests
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from sqlalchemy import inspect, text
from jinja2 import ChoiceLoader, FileSystemLoader
from flask_migrate import Migrate

# Production detection
is_production = os.environ.get('RENDER', False) or os.environ.get('FLASK_ENV') == 'production'

# Gemini API configuration
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1/models/gemini-2.0-flash:generateContent"

def get_url_for(*args, **kwargs):
    url = url_for(*args, **kwargs)
    if is_production and not url.startswith('/skillstown'):
        url = f"/skillstown{url}"
    return url

# Import and initialize auth system from animewatchlist
animewatchlist_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'animewatchlist')
sys.path.insert(0, animewatchlist_path)

try:
    from auth import init_auth, User
    from user_data import get_status_counts
except ImportError as e:
    print(f"Warning: Could not import auth system: {e}")
    # Create fallback classes
    class User:
        pass
    def init_auth(app, url_func, stats_func):
        from flask_sqlalchemy import SQLAlchemy
        return SQLAlchemy(app)
    def get_status_counts(user_id):
        return {'total': 0, 'watching': 0, 'completed': 0, 'on_hold': 0, 'dropped': 0, 'plan_to_watch': 0}

# Gemini API configuration
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1/models/gemini-2.0-flash:generateContent"

def analyze_skills_with_gemini(cv_text, job_description=None):
    """Use Gemini API to analyze CV and optionally match against job description"""
    if not GEMINI_API_KEY:
        print("Warning: GEMINI_API_KEY not set, using fallback skill extraction")
        return extract_skills_fallback(cv_text)
    
    # Create the prompt based on whether we have a job description
    if job_description and job_description.strip():
        prompt = f"""
Analyze this CV and job description to extract skills and provide career guidance.

CV TEXT:
{cv_text[:3000]}

JOB DESCRIPTION:
{job_description[:2000]}

Please provide a JSON response with:
1. "current_skills": Array of technical and professional skills found in the CV
2. "job_requirements": Array of skills/requirements from the job description
3. "skill_gaps": Array of skills needed for the job but missing from CV
4. "matching_skills": Array of skills that match between CV and job
5. "learning_recommendations": Array of specific courses/skills to focus on
6. "career_advice": Brief advice on how to bridge the gap
7. "skill_categories": Object categorizing skills (e.g. "programming": [...], "data": [...])
8. "experience_level": Estimated experience level (entry/mid/senior)

Focus on technical skills, programming languages, frameworks, tools, certifications, and professional competencies.
Return only valid JSON without markdown formatting.
"""
    else:
        prompt = f"""
Analyze this CV to extract skills and provide learning recommendations.

CV TEXT:
{cv_text[:4000]}

Please provide a JSON response with:
1. "current_skills": Array of technical and professional skills found in the CV
2. "skill_categories": Object categorizing skills (e.g. "programming": [...], "data": [...], "management": [...])
3. "experience_level": Estimated experience level (entry/mid/senior)
4. "learning_recommendations": Array of suggested areas for skill development
5. "career_paths": Array of potential career directions based on current skills

Focus on technical skills, programming languages, frameworks, tools, certifications, and professional competencies.
Return only valid JSON without markdown formatting.
"""
    
    try:
        headers = {"Content-Type": "application/json"}
        data = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.3,
                "maxOutputTokens": 2000,
                "topP": 0.8
            }
        }
        
        url = f"{GEMINI_API_URL}?key={GEMINI_API_KEY}"
        response = requests.post(url, headers=headers, json=data, timeout=30)
        
        if response.status_code == 200:
            response_json = response.json()
            if 'candidates' in response_json and len(response_json['candidates']) > 0:
                text_content = response_json['candidates'][0]['content']['parts'][0]['text']
                
                # Try to extract JSON from the response
                try:
                    # Remove any markdown formatting
                    text_content = text_content.strip()
                    
                    # Find JSON in the response
                    json_match = re.search(r'```json\s*(.*?)\s*```', text_content, re.DOTALL)
                    if json_match:
                        json_str = json_match.group(1)
                    else:
                        # Try to find JSON without code blocks
                        json_match = re.search(r'\{.*\}', text_content, re.DOTALL)
                        if json_match:
                            json_str = json_match.group(0)
                        else:
                            json_str = text_content
                    
                    result = json.loads(json_str)
                    
                    # Validate the result
                    if isinstance(result, dict) and 'current_skills' in result:
                        return result
                    else:
                        print(f"Invalid result structure from Gemini API")
                        return extract_skills_fallback(cv_text)
                        
                except json.JSONDecodeError as e:
                    print(f"Failed to parse JSON from Gemini response: {e}")
                    print(f"Response content: {text_content}")
                    return extract_skills_fallback(cv_text)
        else:
            print(f"Gemini API error: {response.status_code} - {response.text}")
            return extract_skills_fallback(cv_text)
            
    except Exception as e:
        print(f"Error calling Gemini API: {e}")
        return extract_skills_fallback(cv_text)

def extract_skills_fallback(cv_text):
    """Fallback skill extraction when Gemini API is not available"""
    # Basic skill patterns
    skill_patterns = [
        r'\b(?:Python|Java|JavaScript|C\+\+|C#|PHP|Ruby|Swift|Kotlin|Go|Rust)\b',
        r'\b(?:HTML|CSS|React|Angular|Vue|Node\.js|Express|Django|Flask)\b',
        r'\b(?:SQL|MySQL|PostgreSQL|MongoDB|SQLite|Oracle|Redis)\b',
        r'\b(?:Git|Docker|Kubernetes|AWS|Azure|GCP|Jenkins|CI/CD)\b',
        r'\b(?:Machine Learning|AI|Data Science|Analytics|TensorFlow|PyTorch)\b',
        r'\b(?:Project Management|Agile|Scrum|Leadership|Communication)\b',
    ]
    
    skills = []
    for pattern in skill_patterns:
        matches = re.finditer(pattern, cv_text, re.IGNORECASE)
        for match in matches:
            skill = match.group().strip()
            if skill not in skills:
                skills.append(skill)
    
    return {
        "current_skills": skills,
        "skill_categories": {"technical": skills},
        "experience_level": "unknown",
        "learning_recommendations": ["Based on your skills, consider learning complementary technologies"],
        "career_paths": ["Continue developing in your current domain"]
    }

def create_app(config_name=None):
    """Create and configure the Flask application"""
    global is_production

    if config_name == 'production':
        is_production = True
    elif config_name is not None:
        is_production = False

    app = Flask(__name__)

    # Configure the Jinja2 loader
    skillstown_template_dir = os.path.join(os.path.dirname(__file__), 'templates')
    
    # Only add animewatchlist templates if the path exists
    loaders = [FileSystemLoader(skillstown_template_dir)]
    if os.path.exists(animewatchlist_path):
        animewatchlist_template_dir = os.path.join(animewatchlist_path, 'templates')
        if os.path.exists(animewatchlist_template_dir):
            loaders.append(FileSystemLoader(animewatchlist_template_dir))
    
    app.jinja_loader = ChoiceLoader(loaders)

    # Configure the app
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'uploads')
    
    # Database configuration
    database_url = os.environ.get('DATABASE_URL')
    if database_url:
        # Fix postgres:// to postgresql:// for SQLAlchemy
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://')
        app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    else:
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///skillstown.db'
    
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Add file upload size limit
    app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10MB limit

    # Set up static folder for production
    if is_production:
        app.static_url_path = '/skillstown/static'

    @app.context_processor
    def inject_template_vars():
        return {'current_year': datetime.datetime.now().year, 'get_url_for': get_url_for}

    # Function to get SkillsTown user statistics
    def get_skillstown_stats(user_id):
        """Get user statistics for SkillsTown courses"""
        try:
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
        except:
            return {
                'total': 0,
                'enrolled': 0,
                'in_progress': 0,
                'completed': 0,
                'completion_percentage': 0
            }
    
    # Initialize auth with skillstown-specific functions
    db = init_auth(app, get_url_for, lambda user_id: get_skillstown_stats(user_id))
    Migrate(app, db)

    # Create base tables
    with app.app_context():
        try:
            db.create_all()
        except Exception as e:
            print(f"Warning: Could not create base tables: {e}")

    # Define models (omitted for brevity, assume same as original but updated)
    class SkillsTownCourse(db.Model):
        __tablename__ = 'skillstown_courses'
        id = db.Column(db.Integer, primary_key=True)
        category = db.Column(db.String(100), nullable=False)
        name = db.Column(db.String(255), nullable=False)
        description = db.Column(db.Text)
        url = db.Column(db.String(500))
        provider = db.Column(db.String(100), default='SkillsTown')
        skills_taught = db.Column(db.Text)
        difficulty_level = db.Column(db.String(20))
        duration = db.Column(db.String(50))
        keywords = db.Column(db.Text)
        created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

    class UserCourse(db.Model):
        __tablename__ = 'skillstown_user_courses'
        id = db.Column(db.Integer, primary_key=True)
        user_id = db.Column(db.Integer, nullable=False)  # Remove foreign key constraint
        category = db.Column(db.String(100), nullable=False)
        course_name = db.Column(db.String(255), nullable=False)
        status = db.Column(db.String(50), default='enrolled')
        created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
        
        __table_args__ = (
            db.UniqueConstraint('user_id', 'course_name', name='skillstown_user_course_unique'),
        )

    class UserProfile(db.Model):
        __tablename__ = 'skillstown_user_profiles'
        id = db.Column(db.Integer, primary_key=True)
        user_id = db.Column(db.Integer, nullable=False)  # Remove foreign key constraint
        cv_text = db.Column(db.Text)
        job_description = db.Column(db.Text)
        skills = db.Column(db.Text)
        skill_analysis = db.Column(db.Text)
        uploaded_at = db.Column(db.DateTime, default=db.func.current_timestamp())

    # Create SkillsTown tables
    with app.app_context():
        try:
            db.create_all()
        except Exception as e:
            print(f"Warning: Could not create SkillsTown tables: {e}")

    # Course service functions
    COURSE_CATALOG_PATH = os.path.join(os.path.dirname(__file__), 'static', 'data', 'course_catalog.json')

    def load_course_catalog():
        try:
            with open(COURSE_CATALOG_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"Course catalog not found at {COURSE_CATALOG_PATH}")
            return {"categories": []}
        except json.JSONDecodeError as e:
            print(f"Error parsing course catalog: {e}")
            return {"categories": []}

    def calculate_relevance_score(query, title, description):
        score = 0
        for word in query.split():
            if word in title.lower(): score += 3
            elif word in description.lower(): score += 1
        return score

    def search_courses(query, catalog=None):
        if not catalog: catalog = load_course_catalog()
        q = query.lower().strip()
        results = []
        for cat in catalog.get('categories', []):
            for c in cat.get('courses', []):
                score = calculate_relevance_score(q, c['name'], c.get('description', ''))
                if score > 0:
                    results.append({'category': cat['name'], 'course': c['name'], 'description': c.get('description', ''), 'relevance_score': score})
        return sorted(results, key=lambda x: x['relevance_score'], reverse=True)

    def allowed_file(filename):
        return '.' in filename and filename.rsplit('.', 1)[1].lower() == 'pdf'

    def extract_text_from_pdf(file_path):
        text = ""
        try:
            with open(file_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                for page in pdf_reader.pages:
                    try:
                        text += page.extract_text() + "\n"
                    except Exception as e:
                        print(f"Warning: Could not extract text from page: {e}")
                        continue
        except Exception as e:
            raise Exception(f"Error reading PDF: {str(e)}")
        return text.strip()
    
    # Error handlers
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return render_template('errors/500.html'), 500

    @app.errorhandler(413)
    def too_large(error):
        return render_template('errors/413.html'), 413

    # Security headers
    @app.after_request
    def after_request(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        if request.is_secure:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        return response

    # Health check endpoint
    @app.route("/health")
    def health_check():
        try:
            # Test database connection
            db.session.execute(text('SELECT 1'))
            return jsonify({
                'status': 'healthy',
                'timestamp': datetime.datetime.utcnow().isoformat(),
                'database': 'connected'
            }), 200
        except Exception as e:
            return jsonify({
                'status': 'unhealthy',
                'timestamp': datetime.datetime.utcnow().isoformat(),
                'database': 'disconnected',
                'error': str(e)
            }), 500
    
    # Routes
    @app.route("/")
    def index():
        """Main SkillsTown index page"""
        catalog = load_course_catalog()
        categories = catalog.get("categories", [])[:6]
        
        return render_template('index.html', categories=categories, get_url_for=get_url_for)

    @app.route('/search')
    def search():
        query = request.args.get('query','').strip()
        return render_template('courses/search.html', query=query,
                               results=search_courses(query) if query else [],
                               get_url_for=get_url_for)

    @app.route('/assessment')
    @login_required
    def assessment():
        return render_template('assessment/assessment.html', get_url_for=get_url_for)

    @app.route('/upload-cv', methods=['GET','POST'])
    @login_required
    def upload_cv():
        """Handle CV upload and analysis with optional job description"""
        if request.method == 'POST':
            # Check if file was uploaded
            if 'cv_file' not in request.files:
                flash('No file selected.', 'danger')
                return redirect(request.url)
            
            file = request.files['cv_file']
            job_description = request.form.get('job_description', '').strip()
            
            if file.filename == '':
                flash('No file selected.', 'danger')
                return redirect(request.url)
            
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                
                # Ensure upload directory exists
                os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
                
                try:
                    # Save the uploaded file
                    file.save(filepath)
                    
                    # Extract text from PDF
                    cv_text = extract_text_from_pdf(filepath)
                    
                    if not cv_text.strip():
                        raise Exception("No text could be extracted from the PDF. Please ensure the PDF contains readable text.")
                    
                    # Analyze with Gemini API
                    analysis_result = analyze_skills_with_gemini(cv_text, job_description)
                    
                    # Extract skills for backward compatibility
                    skills = analysis_result.get('current_skills', [])
                    
                    # Save or update user profile
                    try:
                        profile = UserProfile.query.filter_by(user_id=current_user.id).first()
                        if profile:
                            profile.cv_text = cv_text
                            profile.job_description = job_description
                            profile.skills = json.dumps(skills)
                            profile.skill_analysis = json.dumps(analysis_result)
                            profile.uploaded_at = datetime.datetime.utcnow()
                        else:
                            profile = UserProfile(
                                user_id=current_user.id,
                                cv_text=cv_text,
                                job_description=job_description,
                                skills=json.dumps(skills),
                                skill_analysis=json.dumps(analysis_result)
                            )
                            db.session.add(profile)
                        
                        db.session.commit()
                    except Exception as e:
                        print(f"Database error: {e}")
                        db.session.rollback()
                    
                    # Clean up uploaded file
                    if os.path.exists(filepath):
                        os.remove(filepath)
                    
                    success_msg = 'CV uploaded and analyzed successfully!'
                    if job_description:
                        success_msg += ' Job description analysis included.'
                    flash(success_msg, 'success')
                    return redirect(url_for('cv_analysis'))
                    
                except Exception as e:
                    print(f"Error processing CV: {e}")
                    # Clean up file if it exists
                    if os.path.exists(filepath):
                        os.remove(filepath)
                    flash(f'Error processing CV: {str(e)}', 'danger')
                    return render_template('assessment/assessment.html', get_url_for=get_url_for)
            else:
                flash('Please upload a PDF file.', 'danger')
        
        return render_template('assessment/assessment.html', get_url_for=get_url_for)

    @app.route('/cv-analysis')
    @login_required
    def cv_analysis():
        """Show CV analysis results with enhanced job matching"""
        try:
            profile = UserProfile.query.filter_by(user_id=current_user.id).first()
        except:
            profile = None
        
        if not profile:
            flash('Please upload your CV first.', 'info')
            return redirect(url_for('upload_cv'))
        
        try:
            skills = json.loads(profile.skills) if profile.skills else []
            full_analysis = json.loads(profile.skill_analysis) if profile.skill_analysis else {}
        except:
            skills = []
            full_analysis = {}

        # Enhanced skill matching for categories
        skills_text = " ".join(skills).lower()

        has_programming_skills = bool(re.search(r'(python|java|javascript)', skills_text, re.IGNORECASE))
        has_data_skills = bool(re.search(r'(python|data|sql)', skills_text, re.IGNORECASE))
        has_web_skills = bool(re.search(r'(html|css|javascript|react)', skills_text, re.IGNORECASE))
        has_devops_skills = bool(re.search(r'(aws|docker|git)', skills_text, re.IGNORECASE))
        
        return render_template('assessment/results.html',
                             profile=profile,
                             skills=skills,
                             full_analysis=full_analysis,
                             has_programming_skills=has_programming_skills,
                             has_data_skills=has_data_skills,
                             has_web_skills=has_web_skills,
                             has_devops_skills=has_devops_skills,
                             get_url_for=get_url_for)

    @app.route('/my-courses')
    @login_required
    def my_courses():
        """User's enrolled courses"""
        try:
            courses = UserCourse.query.filter_by(user_id=current_user.id).order_by(UserCourse.created_at.desc()).all()
            stats = get_skillstown_stats(current_user.id)
        except:
            courses = []
            stats = {'total': 0, 'enrolled': 0, 'in_progress': 0, 'completed': 0, 'completion_percentage': 0}
        
        return render_template('courses/my_courses.html', 
                             courses=courses,
                             stats=stats,
                             get_url_for=get_url_for)

    @app.route('/enroll-course', methods=['POST'])
    @login_required
    def enroll_course():
        category = request.form.get('category')
        course_name = request.form.get('course')
        if not category or not course_name:
            return jsonify({'success': False, 'message': 'Missing course information'})
        
        try:
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
        except Exception as e:
            print(f"Enrollment error: {e}")
            db.session.rollback()
            return jsonify({'success': False, 'message': 'Error enrolling in course'})

    @app.route("/update-course-status/<int:course_id>", methods=['POST'])
    @login_required
    def update_course_status(course_id):
        status = request.form.get('status')
        
        try:
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
        except Exception as e:
            print(f"Status update error: {e}")
            db.session.rollback()
            flash('Error updating course status', 'error')
            
        return redirect(url_for('my_courses'))

    @app.route('/profile')
    @login_required
    def skillstown_user_profile():
        """User profile page"""
        stats = get_skillstown_stats(current_user.id)
        try:
            recent_courses = UserCourse.query.filter_by(user_id=current_user.id).order_by(UserCourse.created_at.desc()).limit(5).all()
        except:
            recent_courses = []
        
        return render_template('profile.html', 
                             stats=stats,
                             recent_courses=recent_courses,
                             get_url_for=get_url_for)

    @app.route('/about')
    def about():
        return render_template('about.html', get_url_for=get_url_for)

    @app.route("/debug/create_tables")
    def create_tables_debug():
        """Manual route to create database tables."""
        try:
            with app.app_context():
                db.create_all()
                    
            flash("Database tables created successfully!")
        except Exception as e:
            flash(f"Error creating tables: {e}")
        return redirect(url_for('index'))

    @app.route("/admin/reset-skillstown-tables", methods=['POST'])
    @login_required
    def reset_skillstown_tables_route():
        if current_user.email != 'bentakaki7@gmail.com':
            flash('You are not authorized to perform this action.', 'danger')
            return redirect(get_url_for('skillstown_user_profile'))
        try:
            drop_commands = [
                "DROP TABLE IF EXISTS skillstown_user_courses CASCADE;",
                "DROP TABLE IF EXISTS skillstown_user_profiles CASCADE;",
                "DROP TABLE IF EXISTS skillstown_courses CASCADE;"
            ]:
                db.session.execute(text(cmd))
            db.session.commit()
            db.create_all() 
            
            flash('SkillsTown tables have been reset successfully!', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error resetting tables: {str(e)}', 'danger')
            current_app.logger.error(f"Error resetting tables: {e}")

        return redirect(get_url_for('skillstown_user_profile'))

    @app.route('/health')
    def health_check():
        try:
            db.session.execute(text('SELECT 1'))
            return jsonify(status='healthy', timestamp=datetime.datetime.utcnow().isoformat(), database='connected'), 200
        except Exception as e:
            return jsonify(status='unhealthy', timestamp=datetime.datetime.utcnow().isoformat(), database='disconnected', error=str(e)), 500

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)