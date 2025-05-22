import os
import json
import re
import PyPDF2
import docx
import google.generativeai as genai
from config import GEMINI_API_KEY, COURSE_CATALOG_PATH

# File processing
ALLOWED_EXTENSIONS = {'pdf', 'docx', 'txt'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_text(file_path):
    """Extract text from various file formats"""
    ext = file_path.rsplit('.', 1)[1].lower()
    
    extractors = {
        'pdf': extract_text_from_pdf,
        'docx': extract_text_from_docx,
        'txt': extract_text_from_txt
    }
    
    return extractors.get(ext, lambda x: "")(file_path)

def extract_text_from_pdf(file_path):
    with open(file_path, 'rb') as file:
        reader = PyPDF2.PdfReader(file)
        return " ".join(page.extract_text() for page in reader.pages)

def extract_text_from_docx(file_path):
    doc = docx.Document(file_path)
    return " ".join(paragraph.text for paragraph in doc.paragraphs)

def extract_text_from_txt(file_path):
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
        return file.read()

# Course catalog management
def load_course_catalog():
    try:
        with open(COURSE_CATALOG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {"categories": []}

def search_courses(query, catalog=None):
    """Search courses with relevance scoring"""
    if not catalog:
        catalog = load_course_catalog()
    
    query = query.lower().strip()
    results = []
    
    for category in catalog.get("categories", []):
        for course in category.get("courses", []):
            score = calculate_relevance_score(query, course['name'], course.get('description', ''))
            
            if score > 0:
                results.append({
                    "category": category["name"],
                    "course": course["name"],
                    "description": course.get("description", ""),
                    "relevance_score": score
                })
    
    return sorted(results, key=lambda x: x["relevance_score"], reverse=True)

def calculate_relevance_score(query, title, description):
    """Calculate relevance score for search results"""
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

# CV Analysis
def analyze_cv(text):
    """Analyze CV using Gemini API or fallback"""
    if GEMINI_API_KEY:
        try:
            return analyze_cv_with_gemini(text)
        except Exception as e:
            print(f"Gemini API error: {e}")
    
    return basic_cv_analysis(text)

def analyze_cv_with_gemini(text):
    """Use Gemini API for CV analysis"""
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
    """Fallback CV analysis without API"""
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

def recommend_courses(skills_data, catalog=None):
    """Generate course recommendations based on skills"""
    if not catalog:
        catalog = load_course_catalog()
    
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
            score, matching_skills = calculate_course_score(
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

def calculate_course_score(course_name, description, skills):
    """Calculate match score for a course"""
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