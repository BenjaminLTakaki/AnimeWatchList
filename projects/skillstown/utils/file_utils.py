"""File utility functions for SkillsTown."""
import os
import PyPDF2
import docx

# File processing
ALLOWED_EXTENSIONS = {'pdf', 'docx', 'txt'}

def allowed_file(filename):
    """
    Check if a file has an allowed extension.
    
    Args:
        filename: The name of the file to check
        
    Returns:
        bool: True if the file has an allowed extension, False otherwise
    """
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_text(file_path):
    """
    Extract text from various file formats.
    
    Args:
        file_path: Path to the file
        
    Returns:
        str: Extracted text content
    """
    ext = file_path.rsplit('.', 1)[1].lower()
    
    extractors = {
        'pdf': extract_text_from_pdf,
        'docx': extract_text_from_docx,
        'txt': extract_text_from_txt
    }
    
    return extractors.get(ext, lambda x: "")(file_path)

def extract_text_from_pdf(file_path):
    """Extract text from PDF files."""
    with open(file_path, 'rb') as file:
        reader = PyPDF2.PdfReader(file)
        return " ".join(page.extract_text() for page in reader.pages)

def extract_text_from_docx(file_path):
    """Extract text from Word documents."""
    doc = docx.Document(file_path)
    return " ".join(paragraph.text for paragraph in doc.paragraphs)

def extract_text_from_txt(file_path):
    """Extract text from plain text files."""
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
        return file.read()
