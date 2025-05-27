import os
import datetime
import json
import re
import sys
import PyPDF2
import requests  # ADDED - Missing import
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from sqlalchemy import text
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
from auth import init_auth, User
from user_data import get_status_counts

# Fallback skill extraction

def extract_skills_fallback(cv_text):
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
        for match in re.finditer(pattern, cv_text, re.IGNORECASE):
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

# Analysis with Gemini

def analyze_skills_with_gemini(cv_text, job_description=None):
    if not GEMINI_API_KEY:
        return extract_skills_fallback(cv_text)
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
    headers = {"Content-Type": "application/json"}
    data = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 2000, "topP": 0.8}
    }
    try:
        response = requests.post(f"{GEMINI_API_URL}?key={GEMINI_API_KEY}", headers=headers, json=data, timeout=30)
        response.raise_for_status()
        candidates = response.json().get('candidates', [])
        if not candidates:
            return extract_skills_fallback(cv_text)
        text_content = candidates[0]['content']['parts'][0]['text'].strip()
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', text_content, re.DOTALL) or re.search(r'\{.*\}', text_content, re.DOTALL)
        json_str = (json_match.group(1) if json_match else text_content)
        result = json.loads(json_str)
        if isinstance(result, dict) and 'current_skills' in result:
            return result
        return extract_skills_fallback(cv_text)
    except Exception:
        return extract_skills_fallback(cv_text)

# Flask app factory
def create_app(config_name=None):
    global is_production
    if config_name == 'production':
        is_production = True
    elif config_name is not None:
        is_production = False

    app = Flask(__name__)
    skillstown_template_dir = os.path.join(os.path.dirname(__file__), 'templates')
    animewatchlist_template_dir = os.path.join(animewatchlist_path, 'templates')
    app.jinja_loader = ChoiceLoader([FileSystemLoader(skillstown_template_dir), FileSystemLoader(animewatchlist_template_dir)])
    app.config.update({
        'SECRET_KEY': os.environ.get('SECRET_KEY', 'dev-secret-key-change'),
        'UPLOAD_FOLDER': os.path.join(os.path.dirname(__file__), 'uploads'),
        'SQLALCHEMY_TRACK_MODIFICATIONS': False,
        'MAX_CONTENT_LENGTH': 10 * 1024 * 1024,
    })
    database_url = os.environ.get('DATABASE_URL')
    if database_url and database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://')
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url or 'sqlite:///skillstown.db'
    if is_production:
        app.static_url_path = '/skillstown/static'

    @app.context_processor
    def inject_template_vars():
        return {'current_year': datetime.datetime.now().year, 'get_url_for': get_url_for}

    # Initialize auth and migrations
    db = init_auth(app, get_url_for, lambda uid: get_skillstown_stats(uid))
    Migrate(app, db)
    with app.app_context():
        db.create_all()

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
        user_id = db.Column(db.Integer, nullable=False)
        category = db.Column(db.String(100), nullable=False)
        course_name = db.Column(db.String(255), nullable=False)
        status = db.Column(db.String(50), default='enrolled')
        created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
        __table_args__ = (db.UniqueConstraint('user_id', 'course_name', name='skillstown_user_course_unique'),)

    class UserProfile(db.Model):
        __tablename__ = 'skillstown_user_profiles'
        id = db.Column(db.Integer, primary_key=True)
        user_id = db.Column(db.Integer, nullable=False)
        cv_text = db.Column(db.Text)
        job_description = db.Column(db.Text)
        skills = db.Column(db.Text)
        skill_analysis = db.Column(db.Text)
        uploaded_at = db.Column(db.DateTime, default=db.func.current_timestamp())

    with app.app_context():
        db.create_all()

    # Helper functions (load/search, allowed_file, extract_text_from_pdf)
    COURSE_CATALOG_PATH = os.path.join(os.path.dirname(__file__), 'static', 'data', 'course_catalog.json')

    def load_course_catalog():
        try:
            with open(COURSE_CATALOG_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
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
        text = ''
        with open(file_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                try:
                    text += page.extract_text() or ''
                except:
                    continue
        return text.strip()

    # Stats
    def get_skillstown_stats(user_id):
        try:
            total = UserCourse.query.filter_by(user_id=user_id).count()
            completed = UserCourse.query.filter_by(user_id=user_id, status='completed').count()
            return {'total': total, 'enrolled': total, 'in_progress': 0, 'completed': completed,
                    'completion_percentage': (completed/total*100) if total else 0}
        except:
            return {'total':0,'enrolled':0,'in_progress':0,'completed':0,'completion_percentage':0}

    # Routes (index, search, assessment, upload_cv, cv_analysis, my_courses, enroll, update_course_status, profile, about, health)
    @app.route('/')
    def index():
        categories = load_course_catalog().get('categories', [])[:6]
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
        if request.method == 'GET':
            return redirect(url_for('assessment'))
        if 'cv_file' not in request.files:
            flash('No file selected.', 'danger')
            return redirect(url_for('assessment'))
        file = request.files['cv_file']
        job_description = request.form.get('job_description','').strip()
        if not file or file.filename == '' or not allowed_file(file.filename):
            flash('Please upload a PDF file.', 'danger')
            return redirect(url_for('assessment'))
        filename = secure_filename(file.filename)
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        try:
            file.save(filepath)
            cv_text = extract_text_from_pdf(filepath)
            if not cv_text:
                raise ValueError('No readable text in PDF')
            analysis = analyze_skills_with_gemini(cv_text, job_description)
            skills = analysis.get('current_skills', [])
            profile = UserProfile.query.filter_by(user_id=current_user.id).first()
            if profile:
                profile.cv_text = cv_text
                profile.job_description = job_description
                profile.skills = json.dumps(skills)
                profile.skill_analysis = json.dumps(analysis)
                profile.uploaded_at = datetime.datetime.utcnow()
            else:
                profile = UserProfile(user_id=current_user.id, cv_text=cv_text,
                                      job_description=job_description,
                                      skills=json.dumps(skills),
                                      skill_analysis=json.dumps(analysis))
                db.session.add(profile)
            db.session.commit()
            flash('CV uploaded and analyzed successfully!' +
                  (' Job description included.' if job_description else ''), 'success')
            return redirect(url_for('cv_analysis'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error processing CV: {e}', 'danger')
            return redirect(url_for('assessment'))
        finally:
            if os.path.exists(filepath): os.remove(filepath)

    @app.route('/cv-analysis')
    @login_required
    def cv_analysis():
        profile = UserProfile.query.filter_by(user_id=current_user.id).first()
        if not profile:
            flash('Please upload your CV first.', 'info')
            return redirect(url_for('upload_cv'))
        skills = json.loads(profile.skills or '[]')
        analysis = json.loads(profile.skill_analysis or '{}')
        skills_text = ' '.join(skills).lower()
        return render_template('assessment/results.html', profile=profile,
                               skills=skills, full_analysis=analysis,
                               has_programming_skills=bool(re.search(r'(python|java|javascript)', skills_text)),
                               has_data_skills=bool(re.search(r'(python|data|sql)', skills_text)),
                               has_web_skills=bool(re.search(r'(html|css|javascript|react)', skills_text)),
                               has_devops_skills=bool(re.search(r'(aws|docker|git)', skills_text)),
                               get_url_for=get_url_for)

    @app.route('/my-courses')
    @login_required
    def my_courses():
        courses = UserCourse.query.filter_by(user_id=current_user.id).order_by(UserCourse.created_at.desc()).all()
        return render_template('courses/my_courses.html', courses=courses,
                               stats=get_skillstown_stats(current_user.id), get_url_for=get_url_for)

    @app.route('/enroll-course', methods=['POST'])
    @login_required
    def enroll_course():
        category = request.form.get('category')
        course_name = request.form.get('course')
        if not category or not course_name:
            return jsonify(success=False, message='Missing course information')
        existing = UserCourse.query.filter_by(user_id=current_user.id, course_name=course_name).first()
        if existing:
            return jsonify(success=True, message=f'Already enrolled in {course_name}')
        course = UserCourse(user_id=current_user.id, category=category, course_name=course_name)
        db.session.add(course)
        db.session.commit()
        return jsonify(success=True, message=f'Successfully enrolled in {course_name}!')

    @app.route('/update-course-status/<int:course_id>', methods=['POST'])
    @login_required
    def update_course_status(course_id):
        status = request.form.get('status')
        course = UserCourse.query.filter_by(id=course_id, user_id=current_user.id).first()
        if not course:
            flash('Course not found', 'error')
            return redirect(url_for('my_courses'))
        course.status = status
        db.session.commit()
        flash(f'Course status updated to {status}', 'success')
        return redirect(url_for('my_courses'))

    @app.route('/profile')
    @login_required
    def skillstown_user_profile():
        recent = UserCourse.query.filter_by(user_id=current_user.id).order_by(UserCourse.created_at.desc()).limit(5).all()
        return render_template('profile.html', stats=get_skillstown_stats(current_user.id),
                               recent_courses=recent, get_url_for=get_url_for)

    @app.route('/about')
    def about():
        return render_template('about.html', get_url_for=get_url_for)

    @app.route('/admin/reset-skillstown-tables', methods=['POST'])
    @login_required
    def reset_skillstown_tables_route():
        if current_user.email != 'bentakaki7@gmail.com':
            flash('You are not authorized to perform this action.', 'danger')
            return redirect(get_url_for('skillstown_user_profile'))
        try:
            for cmd in [
                "DROP TABLE IF EXISTS skillstown_user_courses CASCADE;",
                "DROP TABLE IF EXISTS skillstown_user_profiles CASCADE;",
                "DROP TABLE IF EXISTS skillstown_courses CASCADE;"
            ]:
                db.session.execute(text(cmd))
            db.session.commit()
            flash('SkillsTown tables have been reset successfully!', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error resetting tables: {e}', 'danger')
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