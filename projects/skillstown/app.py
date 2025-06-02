import os
import datetime
import json
import re
import sys
import PyPDF2
import requests
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user, LoginManager, login_user, logout_user
from werkzeug.utils import secure_filename
from sqlalchemy import text
from jinja2 import ChoiceLoader, FileSystemLoader
from flask_migrate import Migrate
from werkzeug.security import generate_password_hash, check_password_hash

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

# Import models
from models import db, Company, Student, Category, ContentPage, Course, CourseContentPage, UserProfile, SkillsTownCourse, CourseDetail

# Fallback skill extraction
def extract_skills_fallback(cv_text):
    patterns = [
        r'\b(?:Python|Java|JavaScript|C\+\+|C#|PHP|Ruby|Swift|Kotlin|Go|Rust)\b',
        r'\b(?:HTML|CSS|React|Angular|Vue|Node\.js|Express|Django|Flask)\b',
        r'\b(?:SQL|MySQL|PostgreSQL|MongoDB|SQLite|Oracle|Redis)\b',
        r'\b(?:Git|Docker|Kubernetes|AWS|Azure|GCP|Jenkins|CI/CD)\b',
        r'\b(?:Machine Learning|AI|Data Science|Analytics|TensorFlow|PyTorch)\b',
        r'\b(?:Project Management|Agile|Scrum|Leadership|Communication)\b',
    ]
    skills = []
    for pat in patterns:
        for m in re.finditer(pat, cv_text, re.IGNORECASE):
            s = m.group().strip()
            if s not in skills:
                skills.append(s)
    return {
        "current_skills": skills,
        "skill_categories": {"technical": skills},
        "experience_level": "unknown",
        "learning_recommendations": ["Consider learning complementary technologies"],
        "career_paths": ["Continue developing in your current domain"]
    }

# Gemini-based analysis
def analyze_skills_with_gemini(cv_text, job_description=None):
    if not GEMINI_API_KEY:
        return extract_skills_fallback(cv_text)
    
    if job_description and job_description.strip():
        prompt = f"""
Analyze this CV and job description to extract skills and provide guidance.

CV TEXT:
{cv_text[:3000]}

JOB DESCRIPTION:
{job_description[:2000]}

Provide JSON with current_skills, job_requirements, skill_gaps, matching_skills,
learning_recommendations, career_advice, skill_categories, experience_level.
"""
    else:
        prompt = f"""
Analyze this CV to extract skills and provide recommendations.

CV TEXT:
{cv_text[:4000]}

Provide JSON with current_skills, skill_categories, experience_level,
learning_recommendations, career_paths.
"""
    
    payload = {
        "contents": [{"parts": [{"text": prompt}]}], 
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 2000,
            "topP": 0.8
        }
    }
    
    try:
        res = requests.post(
            f"{GEMINI_API_URL}?key={GEMINI_API_KEY}", 
            json=payload, 
            headers={"Content-Type": "application/json"}, 
            timeout=30
        )
        res.raise_for_status()
        cand = res.json().get('candidates', [])
        if not cand:
            return extract_skills_fallback(cv_text)
        
        txt = cand[0]['content']['parts'][0]['text'].strip()
        jm = re.search(r'```json\s*(\{.*?\})\s*```', txt, re.DOTALL) or re.search(r'\{.*\}', txt, re.DOTALL)
        js = jm.group(1) if jm else txt
        data = json.loads(js)
        return data if isinstance(data, dict) and 'current_skills' in data else extract_skills_fallback(cv_text)
    except Exception:
        return extract_skills_fallback(cv_text)

# App factory
def create_app(config_name=None):
    global is_production
    if config_name == 'production': 
        is_production = True
    elif config_name is not None: 
        is_production = False

    app = Flask(__name__)
    
    # Initialize database
    db.init_app(app)
    
    # Templates
    tpl_dirs = [FileSystemLoader(os.path.join(os.path.dirname(__file__), 'templates'))]
    app.jinja_loader = ChoiceLoader(tpl_dirs)

    # Config
    app.config.update({
        'SECRET_KEY': os.environ.get('SECRET_KEY', 'dev-secret'),
        'UPLOAD_FOLDER': os.path.join(os.path.dirname(__file__), 'uploads'),
        'SQLALCHEMY_TRACK_MODIFICATIONS': False,
        'MAX_CONTENT_LENGTH': 10 * 1024 * 1024,
    })
    
    db_url = os.environ.get('DATABASE_URL')
    if db_url and db_url.startswith('postgres://'):
        db_url = db_url.replace('postgres://', 'postgresql://')
    app.config['SQLALCHEMY_DATABASE_URI'] = db_url or 'sqlite:///skillstown.db'
    
    if is_production: 
        app.static_url_path = '/skillstown/static'

    # Initialize Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'login'
    login_manager.login_message = 'Please log in to access this page.'

    @login_manager.user_loader
    def load_user(user_id):
        return Student.query.get(user_id)

    @app.context_processor
    def inject(): 
        return {
            'current_year': datetime.datetime.now().year,
            'get_url_for': get_url_for
        }

    @app.template_filter('from_json')
    def from_json_filter(json_str):
        try:
            return json.loads(json_str) if json_str else {}
        except:
            return {}

    @app.template_filter('urlencode')
    def urlencode_filter(s):
        from urllib.parse import quote
        return quote(str(s)) if s else ''

    # Stats function
    def get_skillstown_stats(uid):
        try:
            total = Course.query.filter_by(student_id=uid).count()
            enrolled = Course.query.filter_by(student_id=uid, status='enrolled').count()
            in_p = Course.query.filter_by(student_id=uid, status='in_progress').count()
            comp = Course.query.filter_by(student_id=uid, status='completed').count()
            pct = (comp / total * 100) if total else 0
            return {
                'total': total,
                'enrolled': enrolled,
                'in_progress': in_p,
                'completed': comp,
                'completion_percentage': pct
            }
        except:
            return {
                'total': 0,
                'enrolled': 0,
                'in_progress': 0,
                'completed': 0,
                'completion_percentage': 0
            }

    Migrate(app, db)

    with app.app_context(): 
        db.create_all()

    # Helpers
    COURSE_CATALOG_PATH = os.path.join(os.path.dirname(__file__), 'static', 'data', 'course_catalog.json')
    
    def load_course_catalog():
        try:
            with open(COURSE_CATALOG_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {'categories': []}
    
    def calc_score(q, t, d): 
        return sum(3 for w in q.split() if w in t.lower()) + sum(1 for w in q.split() if w in d.lower())
    
    def search_courses(query, catalog=None):
        if not catalog: 
            catalog = load_course_catalog()
        q = query.lower().strip()
        res = []
        for cat in catalog.get('categories', []):
            for c in cat.get('courses', []):
                sc = calc_score(q, c['name'], c.get('description', ''))
                if sc > 0: 
                    res.append({
                        'category': cat['name'],
                        'course': c['name'],
                        'description': c.get('description', ''),
                        'relevance_score': sc
                    })
        return sorted(res, key=lambda x: x['relevance_score'], reverse=True)
    
    def allowed_file(fn): 
        return '.' in fn and fn.rsplit('.', 1)[1].lower() == 'pdf'
    
    def extract_text_from_pdf(fp):
        txt = ''
        try:
            with open(fp, 'rb') as f:
                r = PyPDF2.PdfReader(f)
                for p in r.pages:
                    try: 
                        txt += p.extract_text() or ''
                    except: 
                        continue
        except Exception as e:
            print(f"Error reading PDF: {e}")
        return txt.strip()

    # Routes
    @app.route('/')
    def index():
        """Landing page with overview and getting started"""
        return render_template('index.html')

    @app.route('/about')
    def about():
        return render_template('about.html')

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            email = request.form.get('email')
            password = request.form.get('password')
            
            student = Student.query.filter_by(email=email).first()
            
            if student and check_password_hash(student.password_hash, password):
                login_user(student)
                next_page = request.args.get('next')
                return redirect(next_page or url_for('index'))
            else:
                flash('Invalid email or password', 'error')
        
        return render_template('auth/login.html')

    @app.route('/register', methods=['GET', 'POST'])
    def register():
        if request.method == 'POST':
            name = request.form.get('name')
            email = request.form.get('email')
            password = request.form.get('password')
            
            if Student.query.filter_by(email=email).first():
                flash('Email already registered', 'error')
                return render_template('auth/register.html')
            
            student = Student(
                name=name,
                email=email,
                username=email,  # Use email as username
                password_hash=generate_password_hash(password)
            )
            
            db.session.add(student)
            db.session.commit()
            
            login_user(student)
            flash('Registration successful!', 'success')
            return redirect(url_for('index'))
        
        return render_template('auth/register.html')

    @app.route('/logout')
    @login_required
    def logout():
        logout_user()
        flash('You have been logged out.', 'info')
        return redirect(url_for('index'))

    @app.route('/search')
    def search():
        query = request.args.get('query', '')
        results = []
        if query:
            results = search_courses(query)
        return render_template('courses/search.html', query=query, results=results)

    @app.route('/assessment', methods=['GET', 'POST'])
    @login_required
    def assessment():
        """Main CV analysis page with upload and job description"""
        if request.method == 'POST':
            if 'cv_file' not in request.files:
                flash('No file selected', 'error')
                return redirect(request.url)
            
            file = request.files['cv_file']
            if file.filename == '':
                flash('No file selected', 'error')
                return redirect(request.url)
            
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                upload_folder = app.config['UPLOAD_FOLDER']
                os.makedirs(upload_folder, exist_ok=True)
                filepath = os.path.join(upload_folder, filename)
                file.save(filepath)
                
                try:
                    # Extract text from PDF
                    cv_text = extract_text_from_pdf(filepath)
                    job_description = request.form.get('job_description', '').strip()
                    
                    if not cv_text:
                        flash('Could not extract text from PDF. Please ensure the file is readable.', 'error')
                        return redirect(request.url)
                    
                    # Analyze with Gemini
                    analysis = analyze_skills_with_gemini(cv_text, job_description)
                    
                    # Save to database
                    profile = UserProfile(
                        user_id=current_user.id,
                        cv_text=cv_text,
                        job_description=job_description,
                        skills=json.dumps(analysis.get('current_skills', [])),
                        skill_analysis=json.dumps(analysis)
                    )
                    db.session.add(profile)
                    db.session.commit()
                    
                    flash('CV analyzed successfully!', 'success')
                    return redirect(url_for('analysis_results', profile_id=profile.id))
                    
                except Exception as e:
                    flash(f'Error analyzing CV: {str(e)}', 'error')
                    return redirect(request.url)
                finally:
                    # Clean up uploaded file
                    if os.path.exists(filepath):
                        os.remove(filepath)
            else:
                flash('Please upload a PDF file only', 'error')
        
        return render_template('assessment/assessment.html')

    @app.route('/analysis-results/<int:profile_id>')
    @login_required
    def analysis_results(profile_id):
        profile = UserProfile.query.filter_by(id=profile_id, user_id=current_user.id).first_or_404()
        
        try:
            skills = json.loads(profile.skills) if profile.skills else []
            full_analysis = json.loads(profile.skill_analysis) if profile.skill_analysis else {}
        except json.JSONDecodeError:
            skills = []
            full_analysis = {}
        
        # Determine skill types for recommendations
        has_programming_skills = any(skill.lower() in ['python', 'java', 'javascript', 'c++', 'c#'] 
                                   for skill in skills)
        has_data_skills = any(skill.lower() in ['python', 'sql', 'machine learning', 'data science', 'analytics'] 
                            for skill in skills)
        has_web_skills = any(skill.lower() in ['html', 'css', 'javascript', 'react', 'angular', 'vue'] 
                           for skill in skills)
        has_devops_skills = any(skill.lower() in ['docker', 'kubernetes', 'aws', 'azure', 'jenkins'] 
                              for skill in skills)
        
        return render_template('assessment/results.html', 
                             profile=profile, 
                             skills=skills,
                             full_analysis=full_analysis,
                             has_programming_skills=has_programming_skills,
                             has_data_skills=has_data_skills,
                             has_web_skills=has_web_skills,
                             has_devops_skills=has_devops_skills)

    @app.route('/my-courses')
    @login_required
    def my_courses():
        courses = Course.query.filter_by(student_id=current_user.id).order_by(
            Course.created_at.desc()
        ).all()
        stats = get_skillstown_stats(current_user.id)
        return render_template('courses/my_courses.html', courses=courses, stats=stats)

    @app.route('/course/<int:course_id>')
    @login_required
    def course_detail(course_id):
        """Course detail page with podcast and quiz options"""
        # Get the Course entry
        course = Course.query.filter_by(id=course_id, student_id=current_user.id).first_or_404()

        # Get or create course details
        course_details = CourseDetail.query.filter_by(user_course_id=course.id).first()
        if not course_details:
            sample_materials = {
                "materials": [
                    {
                        "title": f"{course.name} - Introduction",
                        "type": "lesson",
                        "duration": "1 hour",
                        "topics": ["Getting Started", "Overview", "Prerequisites"]
                    },
                    {
                        "title": f"{course.name} - Core Concepts",
                        "type": "lesson",
                        "duration": "2 hours",
                        "topics": ["Fundamentals", "Best Practices", "Common Patterns"]
                    },
                    {
                        "title": f"{course.name} - Practical Application",
                        "type": "workshop",
                        "duration": "3 hours",
                        "topics": ["Hands-on Practice", "Real-world Examples", "Project Work"]
                    }
                ]
            }
            course_details = CourseDetail(
                user_course_id=course.id,
                description=f"Complete {course.name} course covering essential concepts and practical applications.",
                materials=json.dumps(sample_materials),
                progress_percentage=50 if course.status == 'in_progress' else (100 if course.status == 'completed' else 0)
            )
            db.session.add(course_details)
            db.session.commit()

        # Parse materials JSON
        try:
            materials = json.loads(course_details.materials) if course_details.materials else {"materials": []}
        except:
            materials = {"materials": []}

        return render_template('courses/course_detail.html',
                               course=course,
                               course_details=course_details,
                               materials=materials)

    @app.route('/enroll-course', methods=['POST'])
    @login_required
    def enroll_course():
        category_name = request.form.get('category')
        course_name = request.form.get('course')
        
        if not category_name or not course_name:
            return jsonify({'success': False, 'message': 'Missing course information'})
        
        # Find or create category
        category = Category.query.filter_by(name=category_name).first()
        if not category:
            category = Category(name=category_name)
            db.session.add(category)
            db.session.flush()  # Get the ID
        
        # Check if already enrolled
        existing = Course.query.filter_by(
            student_id=current_user.id, 
            name=course_name
        ).first()
        
        if existing:
            return jsonify({'success': False, 'message': 'Already enrolled in this course'})
        
        try:
            new_course = Course(
                student_id=current_user.id,
                name=course_name,
                category_id=category.id,
                status='enrolled'
            )
            db.session.add(new_course)
            db.session.commit()
            return jsonify({'success': True, 'message': 'Successfully enrolled in course'})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': 'Error enrolling in course'})

    @app.route('/update-course-status/<int:course_id>', methods=['POST'])
    @login_required
    def update_course_status(course_id):
        course = Course.query.filter_by(id=course_id, student_id=current_user.id).first_or_404()
        status = request.form.get('status')
        if status in ['enrolled', 'in_progress', 'completed']:
            course.status = status
            # Update course details too
            course_details = CourseDetail.query.filter_by(user_course_id=course.id).first()
            if course_details:
                if status == 'completed':
                    course_details.completed_at = datetime.datetime.now()
                    course_details.progress_percentage = 100
                elif status == 'in_progress':
                    course_details.progress_percentage = 50
                elif status == 'enrolled':
                    course_details.progress_percentage = 0
            db.session.commit()
            flash(f'Course status updated to {status}', 'success')
        else:
            flash('Invalid status', 'error')
        return redirect(url_for('my_courses'))

    @app.route('/profile')
    @login_required
    def skillstown_user_profile():
        stats = get_skillstown_stats(current_user.id)
        recent_courses = Course.query.filter_by(student_id=current_user.id).order_by(
            Course.created_at.desc()
        ).limit(5).all()
        return render_template('profile.html', stats=stats, recent_courses=recent_courses)

    @app.route('/admin/reset-skillstown-tables', methods=['POST'])
    @login_required
    def reset_skillstown_tables():
        if current_user.email != 'bentakaki7@gmail.com':
            flash('Not authorized', 'danger')
            return redirect(url_for('skillstown_user_profile'))
        
        try:
            # Drop tables in correct order
            cmds = [
                "DROP TABLE IF EXISTS courses_content_pages CASCADE;",
                "DROP TABLE IF EXISTS courses CASCADE;",
                "DROP TABLE IF EXISTS content_pages CASCADE;",
                "DROP TABLE IF EXISTS skillstown_user_profiles CASCADE;",
                "DROP TABLE IF EXISTS students CASCADE;",
                "DROP TABLE IF EXISTS companies CASCADE;",
                "DROP TABLE IF EXISTS category CASCADE;",
                "DROP TABLE IF EXISTS skillstown_courses CASCADE;"
            ]
            for cmd in cmds: 
                db.session.execute(text(cmd))
            db.session.commit()
            db.create_all()
            flash('Tables reset successfully', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error resetting tables: {e}', 'danger')
        
        return redirect(url_for('skillstown_user_profile'))

    # Company-aware course recommendations
    def get_company_recommended_courses(student_id):
        """Get course recommendations based on company preferences"""
        student = Student.query.get(student_id)
        if not student or not student.company_id:
            return []
        
        # This would be expanded based on company preferences stored in the database
        # For now, return general recommendations
        company = Company.query.get(student.company_id)
        if company:
            if company.industry == 'Technology':
                return ['Python for Beginners', 'React Complete Course', 'AWS Cloud Practitioner']
            elif company.industry == 'Data Analytics':
                return ['Machine Learning Fundamentals', 'SQL for Data Analysis', 'Data Visualization with Tableau']
            elif company.industry == 'Cloud Computing':
                return ['AWS Cloud Practitioner', 'Docker and Containerization', 'DevOps Best Practices']
        
        return []

    # Error handlers
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('errors/404.html'), 404

    @app.errorhandler(413)
    def request_entity_too_large(error):
        return render_template('errors/413.html'), 413

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return render_template('errors/500.html'), 500

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)