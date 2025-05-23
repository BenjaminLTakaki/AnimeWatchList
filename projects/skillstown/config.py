"""
Configuration settings for the SkillsTown CV Analyzer application.
"""

import os

DEBUG = True

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'.pdf', '.docx', '.txt'}

# Create upload directory if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Paths to data files
SKILLS_JSON_PATH = 'static/data/skills.json'
COURSE_CATALOG_PATH = 'static/data/course_catalog.json'

# Default skills list (if skills.json doesn't exist)
DEFAULT_SKILLS = [
    "python","java","javascript","html","css","sql","nosql","react","angular","node.js",
    "django","flask","php","ruby","c++","c#","swift","kotlin","machine learning","ai",
    "data analysis","data science","cloud computing","aws","azure","devops","docker",
    "kubernetes","git","blockchain","cybersecurity","project management","agile","scrum",
    "lean","six sigma","leadership","marketing","seo","content marketing","social media marketing",
    "digital marketing","sales","crm","accounting","financial analysis","budgeting","audit",
    "communication","public speaking","writing","editing","excel","word","powerpoint",
    "time management","problem solving","critical thinking"
]

# Maximum number of skills to extract
MAX_SKILLS = 20

# Maximum number of course recommendations
MAX_RECOMMENDATIONS = 10