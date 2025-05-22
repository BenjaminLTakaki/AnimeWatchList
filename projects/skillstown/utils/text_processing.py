"""Text processing utilities for CV and content analysis."""
import re
import json
# Optional import for Google Generative AI
try:
    import google.generativeai as genai
except ImportError:
    genai = None

from config import Config

def analyze_cv(text):
    """
    Analyze CV using Gemini API or fallback to basic analysis.
    
    Args:
        text: CV text content
        
    Returns:
        dict: Structured analysis of the CV
    """
    if Config.GEMINI_API_KEY and genai:
        try:
            genai.configure(api_key=Config.GEMINI_API_KEY)
            return analyze_cv_with_gemini(text)
        except Exception as e:
            print(f"Gemini API error: {e}")
    
    return basic_cv_analysis(text)

def analyze_cv_with_gemini(text):
    """
    Use Gemini API for CV analysis.
    
    Args:
        text: CV text content
        
    Returns:
        dict: AI-generated structured analysis of the CV
    """
    if not genai:
        return basic_cv_analysis(text)
        
    model = genai.GenerativeModel('gemini-pro')
    
    prompt = f"""
    Analyze this CV and return JSON with:
    - technical_skills: [{{"skill": "name", "level": "beginner/intermediate/advanced/expert"}}]
    - soft_skills: [{{"skill": "name", "level": "level"}}]
    - domain_knowledge: [{{"area": "name", "level": "level"}}]
    - development_areas: ["area1", "area2", ...]
    - career_paths: ["path1", "path2", ...]
    
    CV Text: {text}
    """
    
    response = model.generate_content(prompt)
    result_text = response.text
    
    # Clean JSON response
    if "```json" in result_text:
        result_text = result_text.split("```json")[1].split("```")[0].strip()
    elif "```" in result_text:
        result_text = result_text.split("```")[1].split("```")[0].strip()
    
    return json.loads(result_text)

def basic_cv_analysis(text):
    """
    Fallback CV analysis without API.
    
    Args:
        text: CV text content
        
    Returns:
        dict: Basic structured analysis of the CV
    """
    text_lower = text.lower()
    
    # Define skill categories
    tech_skills = ["python", "java", "javascript", "html", "css", "sql", "excel", "machine learning"]
    soft_skills = ["communication", "leadership", "teamwork", "problem solving"]
    domains = ["finance", "marketing", "healthcare", "technology"]
    
    result = {
        "technical_skills": [],
        "soft_skills": [],
        "domain_knowledge": [],
        "development_areas": ["Data Analysis", "Project Management", "Cloud Computing"],
        "career_paths": ["Software Development", "Business Analysis", "IT Support"]
    }
    
    # Extract skills
    for skill in tech_skills:
        if re.search(rf'\b{re.escape(skill)}\b', text_lower):
            count = len(re.findall(rf'\b{re.escape(skill)}\b', text_lower))
            level = "advanced" if count > 6 else "intermediate" if count > 3 else "beginner"
            result["technical_skills"].append({"skill": skill, "level": level})
    
    for skill in soft_skills:
        if re.search(rf'\b{re.escape(skill)}\b', text_lower):
            result["soft_skills"].append({"skill": skill, "level": "intermediate"})
    
    for domain in domains:
        if re.search(rf'\b{re.escape(domain)}\b', text_lower):
            result["domain_knowledge"].append({"area": domain, "level": "intermediate"})
    
    return result
