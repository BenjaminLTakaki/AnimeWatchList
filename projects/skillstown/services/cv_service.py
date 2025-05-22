"""CV analysis and recommendation services."""
import json
import os
from utils.text_processing import analyze_cv
from config import Config

class CVService:
    """Service for CV analysis and processing."""
    
    @staticmethod
    def analyze_cv_text(text):
        """
        Analyze CV text and extract skills data.
        
        Args:
            text: CV text content
            
        Returns:
            dict: Structured analysis of the CV
        """
        return analyze_cv(text)
    
    @staticmethod
    def recommend_courses(skills_data, catalog=None):
        """
        Generate course recommendations based on skills.
        
        Args:
            skills_data: Structured skills data
            catalog: Optional course catalog
            
        Returns:
            list: Recommended courses sorted by relevance
        """
        if not catalog:
            catalog = CVService.load_course_catalog()
        
        recommendations = []
        skill_weights = {
            "technical": [(s["skill"], 3) for s in skills_data.get("technical_skills", [])],
            "soft": [(s["skill"], 2) for s in skills_data.get("soft_skills", [])],
            "domain": [(s["area"], 2) for s in skills_data.get("domain_knowledge", [])],
            "development": [(area, 4) for area in skills_data.get("development_areas", [])]
        }
        
        # Flatten skills with weights
        all_skills = []
        for category_skills in skill_weights.values():
            all_skills.extend(category_skills)
        
        # Score courses
        for category in catalog.get("categories", []):
            for course in category.get("courses", []):
                score, matching_skills = CVService._calculate_course_score(
                    course['name'], 
                    course.get('description', ''), 
                    all_skills
                )
                
                if score > 0:
                    recommendations.append({
                        "category": category["name"],
                        "course": course["name"],
                        "description": course.get("description", ""),
                        "match_score": score,
                        "matching_skills": matching_skills
                    })
        
        return sorted(recommendations, key=lambda x: x["match_score"], reverse=True)[:15]
    
    @staticmethod
    def load_course_catalog():
        """
        Load the course catalog from the JSON file.
        
        Returns:
            dict: Course catalog data
        """
        try:
            with open(Config.COURSE_CATALOG_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            return {"categories": []}
    
    @staticmethod
    def _calculate_course_score(course_name, description, skills):
        """
        Calculate match score for a course.
        
        Args:
            course_name: Name of the course
            description: Course description
            skills: List of skills with weights
            
        Returns:
            tuple: (score, matching_skills)
        """
        score = 0
        matching_skills = set()
        
        for skill_name, weight in skills:
            skill_lower = skill_name.lower()
            
            if skill_lower in course_name.lower():
                score += 2 * weight
                matching_skills.add(skill_name)
            elif description and skill_lower in description.lower():
                score += weight
                matching_skills.add(skill_name)
        
        return score, list(matching_skills)
