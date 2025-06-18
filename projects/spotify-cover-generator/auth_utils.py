# projects/spotify-cover-generator/auth_utils.py
import datetime
from flask import session, request
# The following imports assume User and LoginSession will be moved here or app context is handled.
# For now, this will cause an issue if User and LoginSession are not accessible.
# This highlights that User and LoginSession models might also need to be in a models.py
# and imported here, or passed around.
# User and LoginSession models are now in models.py
from .models import User, LoginSession

# SAFER APPROACH: Define get_current_user to accept db and models as arguments,
# or ensure User and LoginSession are moved to a central models.py that auth_utils.py can import from.
# Current approach with direct import from .models is now standard.

# Let's proceed with the assumption that User and LoginSession are defined in app.py
# and we will try to make this work. The alternative is a larger refactor of models.py first.

def get_current_user():
    # Method 1: Check user_id in session
    if 'user_id' in session:
        try:
            # This assumes User.query is available.
            # User model is imported from .models at the top of the file.
            # from .app import User # No longer needed to re-import
            user = User.query.get(session['user_id'])
            if user:
                return user
        except Exception as e:
            print(f"Error fetching user by ID: {e}")
            session.pop('user_id', None)

    # Method 2: Check session token
    session_token = request.cookies.get('session_token')
    if session_token:
        try:
            # This assumes LoginSession.query is available.
            # LoginSession model is imported from .models at the top of the file.
            # from .app import LoginSession # No longer needed to re-import
            login_session = LoginSession.query.filter_by(
                session_token=session_token,
                is_active=True
            ).first()

            if login_session and login_session.expires_at > datetime.datetime.utcnow():
                user = login_session.user
                if user:
                    session['user_id'] = user.id # Ensure user_id is set in session
                    return user
        except Exception as e:
            print(f"Error fetching user by cookie: {e}")

    return None
