from flask import Flask, render_template, request, redirect, url_for, flash
import os
from werkzeug.utils import secure_filename
import PyPDF2
import docx
import spacy
import re
from collections import Counter
import json

# Load spaCy model for NLP
try:
    nlp = spacy.load("en_core_web_sm")
except:
    spacy.cli.download("en_core_web_sm")
    nlp = spacy.load("en_core_web_sm")

# Check if running in the portfolio environment
is_production = os.environ.get('RENDER', False)
app = Flask(
    __name__,
    static_url_path='/static' if not is_production else '/skillstown/static',
    template_folder='templates'
)
app.secret_key = "supersecretkey"

# Configure upload folder
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf', 'docx', 'txt'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Ensure upload folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Define helper function for URL generation
def get_url_for(*args, **kwargs):
    url = url_for(*args, **kwargs)
    if is_production and not url.startswith('/skillstown'):
        url = f"/skillstown{url}"
    return url

# Add context processor to inject variables into all templates
@app.context_processor
def inject_template_vars():
    return {
        'get_url_for': get_url_for
    }

# Load course catalog from JSON file
def load_course_catalog():
    try:
        with open('projects/skillstown/static/data/course_catalog.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        # If the file doesn't exist, return an empty catalog
        return {"categories": []}

# Helper function to check allowed file extension
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Extract text from PDF files
def extract_text_from_pdf(file_path):
    text = ""
    with open(file_path, 'rb') as file:
        reader = PyPDF2.PdfReader(file)
        for page_num in range(len(reader.pages)):
            page = reader.pages[page_num]
            text += page.extract_text()
    return text

# Extract text from DOCX files
def extract_text_from_docx(file_path):
    doc = docx.Document(file_path)
    return " ".join([paragraph.text for paragraph in doc.paragraphs])

# Extract text from TXT files
def extract_text_from_txt(file_path):
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
        return file.read()

# Extract skills from text using NLP
def extract_skills(text):
    # Preprocess text
    text = text.lower()
    
    skill_keywords = [
        # IT & Programming
        "python", "java", "javascript", "html", "css", "sql", "nosql", "react", "angular", 
        "node.js", "django", "flask", "php", "ruby", "c++", "c#", "swift", "kotlin",
        "machine learning", "ai", "artificial intelligence", "data analysis", "data science",
        "cloud computing", "aws", "azure", "google cloud", "devops", "docker", "kubernetes",
        "git", "blockchain", "cybersecurity", "network security",
        
        # Business & Management
        "project management", "agile", "scrum", "lean", "six sigma", "leadership", 
        "strategic planning", "business analysis", "marketing", "seo", "content marketing",
        "social media marketing", "email marketing", "digital marketing", "sales", 
        "customer relationship management", "crm", "negotiation", "business development",
        
        # Finance
        "accounting", "financial analysis", "budgeting", "forecasting", "investment",
        "risk management", "taxation", "audit", "financial planning", "banking",
        
        # HR & Communication
        "human resources", "recruitment", "talent acquisition", "employee relations",
        "compensation", "benefits", "workforce planning", "performance management",
        "communication", "public speaking", "presentation", "writing", "editing",
        "content creation", "team building", "coaching", "mentoring",
        
        # Languages
        "english", "dutch", "german", "french", "spanish", "italian", "portuguese",
        "russian", "chinese", "japanese", "arabic",
        
        # Office Skills
        "microsoft office", "excel", "word", "powerpoint", "outlook", "google workspace",
        "data entry", "typing", "documentation", "research",
        
        # Personal Development
        "time management", "stress management", "problem solving", "critical thinking",
        "creativity", "decision making", "adaptability", "flexibility", "emotional intelligence",
        "mindfulness", "work ethic", "attention to detail"
    ]
    
    doc = nlp(text)
    
    # Extract potential skills based on parts of speech (nouns, proper nouns)
    potential_skills = []
    for token in doc:
        if token.pos_ in ["NOUN", "PROPN"]:
            potential_skills.append(token.text.lower())
    
    # Extract noun phrases as potential complex skills
    for chunk in doc.noun_chunks:
        potential_skills.append(chunk.text.lower())
    
    # Match potential skills against skill keywords
    matched_skills = []
    for skill in skill_keywords:
        if skill in text:
            matched_skills.append(skill)
    
    # Count skill occurrences to find most relevant skills
    skill_counter = Counter(matched_skills)
    top_skills = [skill for skill, count in skill_counter.most_common(20)]
    
    return top_skills

# Recommend courses based on extracted skills
def recommend_courses(skills, course_catalog):
    recommendations = []
    seen_courses = set() 
    
    # Convert skills to lowercase for matching
    skills = [skill.lower() for skill in skills]
    
    # For each category and course in the catalog
    for category in course_catalog["categories"]:
        category_name = category["name"]
        category_courses = category["courses"]
        
        for course in category_courses:
            course_name = course["name"]
            course_description = course.get("description", "")
            course_key = f"{category_name}:{course_name}"  # Create a unique key for the course
            
            # Skip if we've already added this course
            if course_key in seen_courses:
                continue
            
            # Check if any skill matches the course name or description
            match_score = 0
            matching_skills = []
            
            for skill in skills:
                # Check for skill in course name (stronger match)
                if skill in course_name.lower():
                    match_score += 2
                    matching_skills.append(skill)
                # Check for skill in course description
                elif course_description and skill in course_description.lower():
                    match_score += 1
                    matching_skills.append(skill)
            
            # If we have a match, add to recommendations
            if match_score > 0 and matching_skills:
                recommendations.append({
                    "category": category_name,
                    "course": course_name,
                    "description": course_description,
                    "match_score": match_score,
                    "matching_skills": list(set(matching_skills))  # Remove duplicates
                })
                seen_courses.add(course_key)
    
    # Sort recommendations by match score (highest first)
    recommendations.sort(key=lambda x: x["match_score"], reverse=True)
    
    # Limit to top 10 recommendations
    return recommendations[:10]

@app.route('/')
def index():
    # Modified to handle portfolio integration
    template_path = 'index.html'
    return render_template(template_path)

@app.route('/upload', methods=['POST'])
def upload_file():
    # Check if a file was submitted
    if 'file' not in request.files:
        flash('No file part')
        return redirect(request.url)
    
    file = request.files['file']
    
    # Check if user submitted an empty form
    if file.filename == '':
        flash('No selected file')
        return redirect(request.url)
    
    # Check if the file has an allowed extension
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        
        # Extract text based on file type
        text = ""
        file_ext = filename.rsplit('.', 1)[1].lower()
        
        try:
            if file_ext == 'pdf':
                text = extract_text_from_pdf(file_path)
            elif file_ext == 'docx':
                text = extract_text_from_docx(file_path)
            elif file_ext == 'txt':
                text = extract_text_from_txt(file_path)
                
            # Extract skills from the text
            skills = extract_skills(text)
            
            # Load course catalog
            course_catalog = load_course_catalog()
            
            # Recommend courses based on extracted skills
            recommendations = recommend_courses(skills, course_catalog)
            
            return render_template('results.html', 
                                  skills=skills, 
                                  recommendations=recommendations,
                                  filename=filename)
        
        except Exception as e:
            flash(f'Error processing file: {str(e)}')
            return redirect(request.url)
    else:
        flash('File type not allowed. Please upload a PDF, DOCX, or TXT file.')
        return redirect(request.url)

@app.route('/about')
def about():
    return render_template('about.html')

if __name__ == '__main__':
    app.run(debug=True)