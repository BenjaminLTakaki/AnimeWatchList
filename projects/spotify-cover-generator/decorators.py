# projects/spotify-cover-generator/decorators.py
from functools import wraps
from flask import redirect, url_for, flash, request, abort
# Import get_current_user from the new auth_utils.py
from .auth_utils import get_current_user

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if not user: # Check if user is None
            flash('Please log in to access this page.', 'info')
            return redirect(url_for('login', next=request.url)) # Assumes 'login' is your login route name
        return f(user, *args, **kwargs) # Pass user to the decorated function
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if not user:
            flash('Please log in to access this page.', 'info')
            return redirect(url_for('login', next=request.url)) # Assumes 'login' is your login route name
        if not user.is_admin(): # Assumes User model has is_admin method
            abort(403) # Forbidden
        return f(user, *args, **kwargs) # Pass user
    return decorated_function

def permission_required(permission):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user = get_current_user()
            if not user:
                flash('Please log in to access this page.', 'info')
                return redirect(url_for('login', next=request.url)) # Assumes 'login' is your login route name
            if not user.has_permission(permission): # Assumes User model has has_permission method
                abort(403) # Forbidden
            return f(user, *args, **kwargs) # Pass user
        return decorated_function
    return decorator

# Keep validate_user_access if it was defined in step 1, ensure it uses get_current_user
def validate_user_access(f):
    @wraps(f)
    def decorated_function(user_id, *args, **kwargs):
        requesting_user = get_current_user() # Renamed to avoid conflict with user_id param
        if not requesting_user:
            flash('Please log in to access this page.', 'info')
            return redirect(url_for('login', next=request.url)) # Assumes 'login' is your login route name

        if requesting_user.is_admin(): # Assumes User model has is_admin method
            return f(requesting_user, user_id, *args, **kwargs) # Pass requesting_user

        # Assumes User model has 'id' attribute
        if requesting_user.id != user_id:
            abort(403)

        return f(requesting_user, user_id, *args, **kwargs) # Pass requesting_user
    return decorated_function
