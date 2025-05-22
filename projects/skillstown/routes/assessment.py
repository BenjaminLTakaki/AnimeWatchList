"""Assessment blueprint for CV analysis and course recommendations."""
import os
import uuid
from flask import Blueprint, render_template, request, redirect, flash, current_app, url_for, session
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from services.cv_service import CVService
from services.course_service import CourseService
from utils.file_utils import allowed_file, extract_text
from utils.url_helpers import get_url_for
from projects.skillstown.forms import CVUploadForm

# Create blueprint
assessment_bp = Blueprint('assessment', __name__, template_folder='../templates/assessment')

@assessment_bp.route('/', methods=['GET', 'POST'])
@login_required
def upload_cv():
    """CV upload and processing route."""
    form = CVUploadForm()
    
    if form.validate_on_submit():
        file = form.cv_file.data
        
        # Process file
        if file and allowed_file(file.filename):
            # Create unique filename
            filename = secure_filename(file.filename)
            unique_filename = f"{uuid.uuid4()}_{filename}"
            file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_filename)
            
            # Save file
            file.save(file_path)
            
            # Extract text from file
            cv_text = extract_text(file_path)
            
            # Analyze CV
            analysis_results = CVService.analyze_cv_text(cv_text)
            
            # Get course recommendations
            recommendations = CVService.recommend_courses(analysis_results)
            
            # Store results in session
            session['analysis_results'] = analysis_results
            session['recommendations'] = recommendations
            
            return redirect(get_url_for('assessment.results'))
        
        flash('Invalid file type. Allowed file types: PDF, DOCX, TXT', 'danger')
        return redirect(request.url)
    
    return render_template('assessment/assessment.html', form=form)

@assessment_bp.route('/results')
@login_required
def results():
    """CV analysis results route."""
    analysis_results = session.get('analysis_results')
    recommendations = session.get('recommendations')
    
    if not analysis_results or not recommendations:
        flash('No analysis results found. Please upload your CV first.', 'warning')
        return redirect(get_url_for('assessment.upload_cv'))
    
    return render_template('assessment/results.html', 
                          analysis=analysis_results, 
                          recommendations=recommendations)

@assessment_bp.route('/enroll/<category>/<course_name>')
@login_required
def enroll_course(category, course_name):
    """Enroll in a recommended course."""
    # Decode URL params
    category = category.replace('_', ' ')
    course_name = course_name.replace('_', ' ')
    
    # Enroll in course
    enrollment = CourseService.enroll_user_in_course(current_user, category, course_name)
    
    if enrollment:
        flash(f'Successfully enrolled in {course_name}!', 'success')
    else:
        flash(f'You are already enrolled in {course_name}.', 'info')
        
    return redirect(get_url_for('courses.enrolled'))
