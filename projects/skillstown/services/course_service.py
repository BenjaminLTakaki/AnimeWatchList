"""Course management and recommendation services."""
import json
from models import UserCourse, db

class CourseService:
    """Service for course management and recommendations."""
    
    @staticmethod
    def search_courses(query, catalog=None):
        """
        Search courses with relevance scoring.
        
        Args:
            query: Search query string
            catalog: Optional course catalog
            
        Returns:
            list: Courses sorted by relevance
        """
        from services.cv_service import CVService
        
        if not catalog:
            catalog = CVService.load_course_catalog()
        
        query = query.lower().strip()
        results = []
        
        for category in catalog.get("categories", []):
            for course in category.get("courses", []):
                score = CourseService._calculate_relevance_score(query, course['name'], course.get('description', ''))
                
                if score > 0:
                    results.append({
                        "category": category["name"],
                        "course": course["name"],
                        "description": course.get("description", ""),
                        "relevance_score": score
                    })
        
        return sorted(results, key=lambda x: x["relevance_score"], reverse=True)
    
    @staticmethod
    def _calculate_relevance_score(query, title, description):
        """
        Calculate relevance score for search results.
        
        Args:
            query: Search query string
            title: Course title
            description: Course description
            
        Returns:
            int: Relevance score
        """
        title_lower = title.lower()
        desc_lower = description.lower()
        
        # Exact match
        if query == title_lower:
            return 100
        
        # Partial matches
        score = 0
        if query in title_lower:
            score += 75
        elif all(word in title_lower for word in query.split()):
            score += 50
        
        if query in desc_lower:
            score += 25
        elif all(word in desc_lower for word in query.split()):
            score += 15
        
        return score
    
    @staticmethod
    def enroll_user_in_course(user, category, course_name):
        """
        Enroll a user in a course.
        
        Args:
            user: User object
            category: Course category
            course_name: Course name
            
        Returns:
            UserCourse: Created enrollment or None if already enrolled
        """
        # Check if already enrolled
        existing = UserCourse.query.filter_by(
            user_id=user.id, 
            course_name=course_name
        ).first()
        
        if existing:
            return None
            
        # Create enrollment
        enrollment = UserCourse(
            user_id=user.id,
            category=category,
            course_name=course_name,
            status='enrolled'
        )
        
        db.session.add(enrollment)
        db.session.commit()
        return enrollment
    
    @staticmethod
    def get_user_courses(user, status=None):
        """
        Get courses for a user.
        
        Args:
            user: User object
            status: Optional course status filter
            
        Returns:
            list: User's enrolled courses
        """
        query = UserCourse.query.filter_by(user_id=user.id)
        
        if status:
            query = query.filter_by(status=status)
            
        return query.all()
    
    @staticmethod
    def update_course_status(course_id, status, user_id=None):
        """
        Update course status.
        
        Args:
            course_id: UserCourse ID
            status: New status
            user_id: Optional user ID for security check
            
        Returns:
            bool: Success status
        """
        course = UserCourse.query.get(course_id)
        
        if not course or (user_id and course.user_id != user_id):
            return False
            
        course.status = status
        db.session.commit()
        return True
