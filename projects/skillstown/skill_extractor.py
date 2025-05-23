"""
Skill extraction module for the SkillsTown CV Analyzer application.
"""

import json
import logging
import spacy
from collections import Counter

logger = logging.getLogger(__name__)

class SkillExtractor:
    """
    A class to extract skills from text content based on a predefined skills list.
    Uses spaCy for advanced text processing.
    """
    
    def __init__(self, skills_path=None, default_skills=None, nlp_model="en_core_web_sm"):
        """
        Initialize the skill extractor.
        
        Args:
            skills_path (str): Path to the JSON file containing skills.
            default_skills (list): Default skills list to use if the file is not found.
            nlp_model (str): Name of the spaCy model to load.
        """
        self.skills = []
        self.nlp = None
        
        # Try to load spaCy model
        try:
            self.nlp = spacy.load(nlp_model)
            logger.info(f"Loaded spaCy model: {nlp_model}")
        except OSError as e:
            logger.warning(f"Failed to load spaCy model: {e}")
        
        # Load skills from file or use default
        if skills_path:
            try:
                with open(skills_path, 'r') as f:
                    self.skills = json.load(f).get('skills', [])
                logger.info(f"Loaded {len(self.skills)} skills from {skills_path}")
            except (FileNotFoundError, json.JSONDecodeError) as e:
                logger.warning(f"Error loading skills from {skills_path}: {e}")
                if default_skills:
                    self.skills = default_skills
                    logger.info(f"Using {len(self.skills)} default skills")
        elif default_skills:
            self.skills = default_skills
            logger.info(f"Using {len(self.skills)} default skills")
    
    def extract_skills(self, text, max_skills=20):
        """
        Extract skills from text content.
        
        Args:
            text (str): The text to extract skills from.
            max_skills (int): Maximum number of skills to return.
            
        Returns:
            list: A list of extracted skills, sorted by relevance.
        """
        if not text or not self.skills:
            return []
        
        text_lower = text.lower()
        
        skill_counter = Counter()
        for skill in self.skills:
            if skill in text_lower:
                skill_counter[skill] += 1
        
        if self.nlp:
            try:
                doc = self.nlp(text_lower)
                
                for chunk in doc.noun_chunks:
                    chunk_text = chunk.text.lower()
                    for skill in self.skills:
                        if skill in chunk_text:
                            skill_counter[skill] += 2
                
                for ent in doc.ents:
                    ent_text = ent.text.lower()
                    for skill in self.skills:
                        if skill in ent_text:
                            # Give higher weight to skills found in entities
                            skill_counter[skill] += 3
            except Exception as e:
                logger.error(f"Error in spaCy processing: {e}")
        
        # Return the most common skills
        return [skill for skill, _ in skill_counter.most_common(max_skills)]