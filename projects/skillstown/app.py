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

    app=Flask(__name__)
    # Templates
    tpl_dirs=[FileSystemLoader(os.path.join(os.path.dirname(__file__),'templates'))]
    if os.path.isdir(animewatchlist_path): tpl_dirs.append(FileSystemLoader(os.path.join(animewatchlist_path,'templates')))
    app.jinja_loader=ChoiceLoader(tpl_dirs)

    # Config
    app.config.update({
        'SECRET_KEY': os.environ.get('SECRET_KEY', 'dev-secret'),
        'UPLOAD_FOLDER': os.path.join(os.path.dirname(__file__), 'uploads'),
        'SQLALCHEMY_TRACK_MODIFICATIONS': False,
        'MAX_CONTENT_LENGTH': 10 * 1024 * 1024,
    })
    
    db_url = os.environ.get('DATABASE_URL')
    if db_url and db_url.startswith('postgres://'):
        db_url=db_url.replace('postgres://','postgresql://')
    app.config['SQLALCHEMY_DATABASE_URI']=db_url or 'sqlite:///skillstown.db'
    if is_production: app.static_url_path='/skillstown/static'

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
            total=UserCourse.query.filter_by(user_id=uid).count()
            enrolled=UserCourse.query.filter_by(user_id=uid,status='enrolled').count()
            in_p=UserCourse.query.filter_by(user_id=uid,status='in_progress').count()
            comp=UserCourse.query.filter_by(user_id=uid,status='completed').count()
            pct=(comp/total*100) if total else 0
            return {'total':total,'enrolled':enrolled,'in_progress':in_p,'completed':comp,'completion_percentage':pct}
        except:
            return {'total':0,'enrolled':0,'in_progress':0,'completed':0,'completion_percentage':0}

    db=init_auth(app,get_url_for,get_skillstown_stats)
    Migrate(app,db)
    with app.app_context(): db.create_all()

    # Models
    class SkillsTownCourse(db.Model):
        __tablename__='skillstown_courses'
        id=db.Column(db.Integer,primary_key=True)
        category=db.Column(db.String(100),nullable=False)
        name=db.Column(db.String(255),nullable=False)
        description=db.Column(db.Text)
        url=db.Column(db.String(500))
        provider=db.Column(db.String(100),default='SkillsTown')
        skills_taught=db.Column(db.Text)
        difficulty_level=db.Column(db.String(20))
        duration=db.Column(db.String(50))
        keywords=db.Column(db.Text)
        created_at=db.Column(db.DateTime,default=db.func.current_timestamp())

    class UserCourse(db.Model):
        __tablename__='skillstown_user_courses'
        id=db.Column(db.Integer,primary_key=True)
        user_id=db.Column(db.Integer,nullable=False)
        category=db.Column(db.String(100),nullable=False)
        course_name=db.Column(db.String(255),nullable=False)
        status=db.Column(db.String(50),default='enrolled')
        created_at=db.Column(db.DateTime,default=db.func.current_timestamp())
        __table_args__=(db.UniqueConstraint('user_id','course_name',name='skillstown_user_course_unique'),)

    class UserProfile(db.Model):
        __tablename__='skillstown_user_profiles'
        id=db.Column(db.Integer,primary_key=True)
        user_id=db.Column(db.Integer,nullable=False)
        cv_text=db.Column(db.Text)
        job_description=db.Column(db.Text)
        skills=db.Column(db.Text)
        skill_analysis=db.Column(db.Text)
        uploaded_at=db.Column(db.DateTime,default=db.func.current_timestamp())

    with app.app_context(): db.create_all()

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

    # Routes omitted for brevity; assume same structure with corrected syntax

    # Admin reset route correction
    @app.route('/admin/reset-skillstown-tables',methods=['POST'])
    @login_required
    def reset_skillstown_tables():
        if current_user.email != 'bentakaki7@gmail.com':
            flash('Not authorized', 'danger')
            return redirect(url_for('skillstown_user_profile'))
        
        try:
            cmds=[
                "DROP TABLE IF EXISTS skillstown_user_courses CASCADE;",
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
            flash('Tables reset successfully','success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error resetting tables: {e}','danger')
        return redirect(get_url_for('skillstown_user_profile'))

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)