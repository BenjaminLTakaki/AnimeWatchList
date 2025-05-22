import os
import sys
from flask import Flask
from flask_login import LoginManager, current_user
from datetime import datetime

# Add the current directory to Python path to allow proper imports
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

from config import config
from models import db, User
from utils.url_helpers import get_url_for

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
    
    # Register blueprints
    from routes.main import main_bp
    from routes.auth import auth_bp
    from routes.assessment import assessment_bp
    from routes.courses import courses_bp
    
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(assessment_bp, url_prefix='/assessment')
    app.register_blueprint(courses_bp, url_prefix='/courses')
    
    # Context processors
    @app.context_processor
    def inject_globals():
        return {
            'get_url_for': get_url_for,
            'enrolled_courses_count': current_user.enrolled_courses_count if current_user.is_authenticated else 0,
            'current_year': datetime.now().year
        }
    
    # Create tables
    with app.app_context():
        db.create_all()
    
    return app

# Create app instance for direct running
app = create_app()

# Run the app if executed directly
if __name__ == '__main__':
    app.run(debug=True)

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        flash('No file selected', 'error')
        return redirect(get_url_for('assessment'))
    
    file = request.files['file']
    if file.filename == '':
        flash('No file selected', 'error')
        return redirect(get_url_for('assessment'))
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        try:
            # Process file
            text = extract_text(filepath)
            skills_data = analyze_cv(text)
            recommendations = recommend_courses(skills_data)
            
            # Clean up file
            os.remove(filepath)
            
            return render_template('results.html',
                                 skills_data=skills_data,
                                 recommendations=recommendations,
                                 filename=filename)
        except Exception as e:
            flash(f'Error processing file: {str(e)}', 'error')
            return redirect(get_url_for('assessment'))
    
    flash('Invalid file type. Please upload PDF, DOCX, or TXT.', 'error')
    return redirect(get_url_for('assessment'))

@app.route('/search')
def search():
    query = request.args.get('query', '')
    results = search_courses(query) if query else []
    
    if query and not results:
        flash('No courses found. Try different keywords.', 'info')
    
    return render_template('search.html', results=results, query=query)

@app.route('/enrolled-courses')
@login_required
def enrolled_courses():
    courses = current_user.courses.all()
    return render_template('enrolled_courses.html', courses=courses)

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
    
    return redirect(get_url_for('enrolled_courses'))

@app.route('/remove-course/<int:course_id>', methods=['POST'])
@login_required
def remove_course(course_id):
    course = UserCourse.query.filter_by(id=course_id, user_id=current_user.id).first_or_404()
    db.session.delete(course)
    db.session.commit()
    flash('Course removed successfully', 'success')
    
    return redirect(get_url_for('enrolled_courses'))

@app.route('/about')
def about():
    return render_template('about.html')

if __name__ == '__main__':
    app.run(debug=True)