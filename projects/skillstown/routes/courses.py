"""Courses blueprint for course management."""
from flask import Blueprint, render_template, request, redirect, flash, jsonify
from flask_login import login_required, current_user

from services.course_service import CourseService
from utils.url_helpers import get_url_for

# Create blueprint
courses_bp = Blueprint('courses', __name__, template_folder='../templates/courses')

@courses_bp.route('/search', methods=['GET', 'POST'])
def search():
    """Course search route."""
    results = []
    query = ""
    
    if request.method == 'POST':
        query = request.form.get('query', '').strip()
        if query:
            results = CourseService.search_courses(query)
    
    return render_template('search.html', results=results, query=query)

@courses_bp.route('/enrolled')
@login_required
def enrolled():
    """Enrolled courses route."""
    courses = CourseService.get_user_courses(current_user)
    return render_template('enrolled_courses.html', courses=courses)

@courses_bp.route('/saved')
@login_required
def saved():
    """Saved courses route."""
    courses = CourseService.get_user_courses(current_user, status='saved')
    return render_template('saved_courses.html', courses=courses)

@courses_bp.route('/enroll', methods=['POST'])
@login_required
def enroll():
    """AJAX endpoint for course enrollment."""
    data = request.json
    category = data.get('category')
    course_name = data.get('course_name')
    
    if not category or not course_name:
        return jsonify({"success": False, "message": "Missing required fields"}), 400
        
    enrollment = CourseService.enroll_user_in_course(current_user, category, course_name)
    
    if enrollment:
        return jsonify({"success": True, "message": f"Successfully enrolled in {course_name}"})
    else:
        return jsonify({"success": False, "message": f"You are already enrolled in {course_name}"}), 409

@courses_bp.route('/update-status', methods=['POST'])
@login_required
def update_status():
    """AJAX endpoint for updating course status."""
    data = request.json
    course_id = data.get('course_id')
    status = data.get('status')
    
    if not course_id or not status:
        return jsonify({"success": False, "message": "Missing required fields"}), 400
        
    if status not in ['enrolled', 'in_progress', 'completed', 'saved']:
        return jsonify({"success": False, "message": "Invalid status"}), 400
        
    success = CourseService.update_course_status(course_id, status, current_user.id)
    
    if success:
        return jsonify({"success": True, "message": "Status updated successfully"})
    else:
        return jsonify({"success": False, "message": "Course not found"}), 404
