import os
import sys
from flask import Flask, render_template, request, redirect, flash, jsonify
from flask_login import LoginManager, current_user, login_required
from datetime import datetime
from werkzeug.utils import secure_filename

# Add the current directory to Python path to allow proper imports
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

try:
    from config import config
    from models import db, User, UserCourse
except ImportError as e:
    print(f"Import error in app.py: {e}")
    # Try alternative import
    sys.path.insert(0, os.path.dirname(current_dir))
    from skillstown.config import config
    from skillstown.models import db, User, UserCourse

def create_app(config_name=None):
    """
    Application factory pattern.
    
    Args:
        config_name: Configuration to use (development, production, testing)
        
    Returns:
        Flask application instance
    """
    # Set default config
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')
    
    # Initialize app
    app = Flask(__name__)
    app.config.from_object(config[config_name])
    
    # Initialize extensions
    db.init_app(app)
    
    # Setup login manager
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'info'
    
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
    
    # Import blueprints here to avoid circular imports
    try:
        from routes.main import main_bp
        from routes.auth import auth_bp
        from routes.assessment import assessment_bp
        from routes.courses import courses_bp
    except ImportError:
        # Try alternative imports
        from skillstown.routes.main import main_bp
        from skillstown.routes.auth import auth_bp
        from skillstown.routes.assessment import assessment_bp
        from skillstown.routes.courses import courses_bp
    
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(assessment_bp, url_prefix='/assessment')
    app.register_blueprint(courses_bp, url_prefix='/courses')
    
    # Import helper functions
    try:
        from utils.url_helpers import get_url_for
        from utils.file_utils import allowed_file, extract_text
        from utils.text_processing import analyze_cv
        from services.course_service import CourseService
    except ImportError:
        from skillstown.utils.url_helpers import get_url_for
        from skillstown.utils.file_utils import allowed_file, extract_text
        from skillstown.utils.text_processing import analyze_cv
        from skillstown.services.course_service import CourseService
    
    # Context processors
    @app.context_processor
    def inject_globals():
        return {
            'get_url_for': get_url_for,
            'enrolled_courses_count': current_user.enrolled_courses.count() if current_user.is_authenticated else 0,
            'current_year': datetime.now().year
        }
    
    # Create tables
    with app.app_context():
        db.create_all()
    
    # Additional routes that were in the original app.py
    @app.route('/upload', methods=['POST'])
    @login_required
    def upload_file():
        if 'file' not in request.files:
            flash('No file selected', 'error')
            return redirect(get_url_for('assessment.upload_cv'))
        
        file = request.files['file']
        if file.filename == '':
            flash('No file selected', 'error')
            return redirect(get_url_for('assessment.upload_cv'))
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            try:
                # Process file
                text = extract_text(filepath)
                skills_data = analyze_cv(text)
                recommendations = CourseService.recommend_courses(skills_data)
                
                # Clean up file
                os.remove(filepath)
                
                return render_template('assessment/results.html',
                                     skills_data=skills_data,
                                     recommendations=recommendations,
                                     filename=filename)
            except Exception as e:
                flash(f'Error processing file: {str(e)}', 'error')
                return redirect(get_url_for('assessment.upload_cv'))
        
        flash('Invalid file type. Please upload PDF, DOCX, or TXT.', 'error')
        return redirect(get_url_for('assessment.upload_cv'))

    @app.route('/search')
    def search():
        query = request.args.get('query', '')
        results = CourseService.search_courses(query) if query else []
        
        if query and not results:
            flash('No courses found. Try different keywords.', 'info')
        
        return render_template('courses/search.html', results=results, query=query)

    @app.route('/enrolled-courses')
    @login_required
    def enrolled_courses():
        courses = current_user.enrolled_courses.all()
        return render_template('courses/enrolled_courses.html', courses=courses)

    @app.route('/enroll-course', methods=['POST'])
    @login_required
    def enroll_course():
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

    @app.route('/update-course-status/<int:course_id>', methods=['POST'])
    @login_required
    def update_course_status(course_id):
        course = UserCourse.query.filter_by(id=course_id, user_id=current_user.id).first_or_404()
        
        new_status = request.form.get('status')
        if new_status in ['enrolled', 'in_progress', 'completed']:
            course.status = new_status
            db.session.commit()
            flash(f'Course status updated to {new_status}', 'success')
        
        return redirect(get_url_for('courses.enrolled'))

    @app.route('/remove-course/<int:course_id>', methods=['POST'])
    @login_required
    def remove_course(course_id):
        course = UserCourse.query.filter_by(id=course_id, user_id=current_user.id).first_or_404()
        db.session.delete(course)
        db.session.commit()
        flash('Course removed successfully', 'success')
        
        return redirect(get_url_for('courses.enrolled'))

    @app.route('/about')
    def about():
        return render_template('about.html')
    
    return app

# Create app instance for direct running
if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)