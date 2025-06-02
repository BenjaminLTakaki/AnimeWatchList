from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
import uuid

db = SQLAlchemy()

class Company(db.Model):
    __tablename__ = 'companies'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(255), nullable=False)
    industry = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    
    # Relationship to students
    students = db.relationship('Student', backref='company', lazy=True)
    
    def __repr__(self):
        return f'<Company {self.name}>'

class Student(db.Model, UserMixin):
    __tablename__ = 'students'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(255), nullable=False, unique=True)
    enrolled_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    company_id = db.Column(db.String(36), db.ForeignKey('companies.id'), nullable=True)
    
    # For Flask-Login compatibility
    username = db.Column(db.String(255))
    password_hash = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True)
    date_joined = db.Column(db.DateTime, default=db.func.current_timestamp())
    
    # Relationships
    enrollments = db.relationship('Course', backref='student', lazy=True)
    profiles = db.relationship('UserProfile', backref='student', lazy=True)
    
    def get_id(self):
        return str(self.id)
    
    @property
    def is_authenticated(self):
        return True
    
    @property
    def is_anonymous(self):
        return False
    
    def __repr__(self):
        return f'<Student {self.name}>'

class Category(db.Model):
    __tablename__ = 'category'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    
    # Relationships
    content_pages = db.relationship('ContentPage', backref='category', lazy=True)
    courses = db.relationship('Course', backref='category_rel', lazy=True)
    
    def __repr__(self):
        return f'<Category {self.name}>'

class ContentPage(db.Model):
    __tablename__ = 'content_pages'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    category_id = db.Column(db.String(36), db.ForeignKey('category.id'), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    content = db.Column(db.Text)  # JSON format for rich content
    is_draft = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    
    def __repr__(self):
        return f'<ContentPage {self.title}>'

class Course(db.Model):
    __tablename__ = 'courses'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    student_id = db.Column(db.String(36), db.ForeignKey('students.id'), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    category_id = db.Column(db.String(36), db.ForeignKey('category.id'), nullable=False)
    published = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    
    # Status and progress tracking
    status = db.Column(db.String(50), default='enrolled')  # enrolled, in_progress, completed
    progress_percentage = db.Column(db.Integer, default=0)
    completed_at = db.Column(db.DateTime)
    
    def __repr__(self):
        return f'<Course {self.name}>'

class CourseContentPage(db.Model):
    __tablename__ = 'courses_content_pages'
    
    course_id = db.Column(db.String(36), db.ForeignKey('courses.id'), primary_key=True)
    content_page_id = db.Column(db.String(36), db.ForeignKey('content_pages.id'), primary_key=True)
    order_index = db.Column(db.Integer, nullable=False)
    is_required = db.Column(db.Boolean, default=True)
    
    # Relationships
    course = db.relationship('Course', backref=db.backref('course_content_pages', lazy=True))
    content_page = db.relationship('ContentPage', backref=db.backref('course_content_pages', lazy=True))
    
    def __repr__(self):
        return f'<CourseContentPage {self.course_id}:{self.content_page_id}>'

class UserProfile(db.Model):
    __tablename__ = 'skillstown_user_profiles'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(36), db.ForeignKey('students.id'), nullable=False)
    cv_text = db.Column(db.Text)
    job_description = db.Column(db.Text)
    skills = db.Column(db.Text)
    skill_analysis = db.Column(db.Text)
    uploaded_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    
    def __repr__(self):
        return f'<UserProfile {self.user_id}>'

class CourseDetail(db.Model):
    """Extended course details for existing UserCourse entries"""
    __tablename__ = 'skillstown_course_details'
    
    id = db.Column(db.Integer, primary_key=True)
    user_course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    description = db.Column(db.Text)
    progress_percentage = db.Column(db.Integer, default=0)
    completed_at = db.Column(db.DateTime)
    materials = db.Column(db.Text)  # JSON format for course materials
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    
    # Relationship to Course model
    course = db.relationship('Course', backref='details')

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
    
    def __repr__(self):
        return f'<SkillsTownCourse {self.name}>'