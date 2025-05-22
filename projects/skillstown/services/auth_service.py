"""Authentication service for user management."""
from models import User, db
from flask_login import login_user, logout_user

class AuthService:
    """Service for authentication and user management."""
    
    @staticmethod
    def register_user(username, email, password):
        """
        Register a new user.
        
        Args:
            username: User's username
            email: User's email
            password: User's password
            
        Returns:
            tuple: (User object, error message or None)
        """
        # Check if user exists
        if User.query.filter_by(username=username).first():
            return None, "Username already taken"
            
        if User.query.filter_by(email=email).first():
            return None, "Email already registered"
            
        # Create user
        user = User(username=username, email=email)
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        return user, None
    
    @staticmethod
    def login_user(email, password, remember=False):
        """
        Log in a user.
        
        Args:
            email: User's email
            password: User's password
            remember: Remember login
            
        Returns:
            tuple: (Success flag, user object or None, error message or None)
        """
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            login_user(user, remember=remember)
            return True, user, None
            
        return False, None, "Invalid email or password"
    
    @staticmethod
    def logout():
        """Log out the current user."""
        logout_user()
        return True
