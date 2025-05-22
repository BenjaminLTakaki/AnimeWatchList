from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

# Initialize SQLAlchemy without app (will be registered in factory pattern)
db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'skillstown_users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    courses = db.relationship('UserCourse', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    @property
    def enrolled_courses_count(self):
        return self.courses.count()
    
    @property
    def completed_courses_count(self):
        return self.courses.filter_by(status='completed').count()

class UserCourse(db.Model):
    __tablename__ = 'skillstown_user_courses'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('skillstown_users.id'), nullable=False)
    category = db.Column(db.String(100), nullable=False)
    course_name = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(50), default='enrolled')
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    
    __table_args__ = (
        db.UniqueConstraint('user_id', 'course_name', name='user_course_unique'),
    )