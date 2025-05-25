import requests
import json
import random
import re
from collections import defaultdict, Counter
from typing import List, Dict, Tuple
import numpy as np

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    from sklearn.cluster import KMeans
    SKLEARN_AVAILABLE = True
except ImportError:
    print("sklearn not available - falling back to basic algorithms")
    SKLEARN_AVAILABLE = False

try:
    import nltk
    from nltk.corpus import wordnet
    from nltk.tokenize import word_tokenize
    # Download required NLTK data
    try:
        nltk.data.find('tokenizers/punkt')
        nltk.data.find('corpora/wordnet')
    except LookupError:
        nltk.download('punkt', quiet=True)
        nltk.download('wordnet', quiet=True)
    NLTK_AVAILABLE = True
except ImportError:
    print("NLTK not available - falling back to basic word processing")
    NLTK_AVAILABLE = False

from config import GEMINI_API_KEY, GEMINI_API_URL

class MLEnhancedTitleGenerator:
    def __init__(self):
        # Comprehensive training dataset by genre
        self.album_corpus = {
            "rock": [
                "The Dark Side of the Moon", "Abbey Road", "Led Zeppelin IV", "Nevermind", 
                "The Wall", "Born to Run", "Rumours", "The Joshua Tree", "Blood Sugar Sex Magik",
                "Ten", "OK Computer", "The Bends", "In Utero", "Appetite for Destruction",
                "Back in Black", "Highway to Hell", "Master of Puppets", "Ride the Lightning",
                "The Number of the Beast", "Paranoid", "Black Sabbath", "Physical Graffiti"
            ],
            "electronic": [
                "Discovery", "Random Access Memories", "Since I Left You", "Cross", "Immunity",
                "Dive", "Flume", "Worlds", "Adventure", "Good Faith", "Clarity", "True",
                "Settle", "In Colour", "Woman Worldwide", "Alive 2007", "Human After All",
                "Selected Ambient Works", "Drukqs", "Come to Daddy", "Richard D James Album",
                "Mezzanine", "Blue Lines", "Protection", "Dummy", "Maxinquaye"
            ],
            "hip hop": [
                "Illmatic", "The Chronic", "Ready to Die", "All Eyez on Me", "The Blueprint",
                "Good Kid MAAD City", "To Pimp a Butterfly", "The College Dropout", 
                "My Beautiful Dark Twisted Fantasy", "The Low End Theory", "Midnight Marauders",
                "Enter the Wu-Tang", "Only Built 4 Cuban Linx", "Liquid Swords", "Supreme Clientele",
                "The Infamous", "Hell on Earth", "It Was Written", "Stillmatic", "The Black Album"
            ],
            "indie": [
                "In the Aeroplane Over the Sea", "Funeral", "The Lonesome Crowded West",
                "Crooked Rain Crooked Rain", "Doolittle", "Murmur", "Reckoning", "Document",
                "Illinois", "The Glow Pt 2", "Merriweather Post Pavilion", "Feels", "Strawberry Jam",
                "Is This It", "Room on Fire", "Angles", "The Strokes", "Bleed Like Me",
                "Version 2.0", "Garbage", "Beautiful Garbage", "Not Your Kind of People"
            ],
            "jazz": [
                "Kind of Blue", "A Love Supreme", "Bitches Brew", "Time Out", "Saxophone Colossus",
                "Blue Train", "Giant Steps", "Head Hunters", "The Black Saint and the Sinner Lady",
                "Mingus Ah Um", "The Shape of Jazz to Come", "Free Jazz", "Something Else",
                "Waltz for Debby", "Sunday at the Village Vanguard", "Empyrean Isles",
                "Maiden Voyage", "Speak No Evil", "Juju", "Search for the New Land"
            ],
            "pop": [
                "Thriller", "Purple Rain", "Like a Virgin", "True Blue", "Faith", "Listen Without Prejudice",
                "The Immaculate Collection", "Ray of Light", "Confessions on a Dance Floor",
                "21", "25", "19", "Back to Black", "Frank", "1989", "Red", "Folklore",
                "Reputation", "Lover", "Future Nostalgia", "Golden Hour", "When We All Fall Asleep"
            ]
        }
        
        # Semantic word categories
        self.semantic_categories = {
            "emotions": ["euphoria", "melancholy", "rage", "serenity", "anxiety", "bliss", "despair", "hope"],
            "colors": ["crimson", "azure", "golden", "silver", "obsidian", "pearl", "ruby", "emerald"],
            "textures": ["velvet", "silk", "steel", "glass", "concrete", "liquid", "smoke", "crystal"],
            "time": ["eternal", "fleeting", "ancient", "future", "momentary", "endless", "forgotten", "dawn"],
            "space": ["void", "cosmos", "horizon", "depth", "surface", "dimension", "realm", "plane"],
            "elements": ["fire", "water", "earth", "air", "lightning", "thunder", "wind", "storm"],
            "abstract": ["paradox", "synthesis", "metamorphosis", "equilibrium", "chaos", "harmony", "discord", "unity"]
        }
        
        # Initialize ML components
        self.tfidf_vectorizer = None
        self.genre_vectors = {}
        self.word_embeddings = {}
        self._initialize_ml_components()

    def _initialize_ml_components(self):
        """Initialize ML components for semantic analysis"""
        if SKLEARN_AVAILABLE:
            # Create TF-IDF vectors for each genre
            all_texts = []
            genre_labels = []
            
            for genre, albums in self.album_corpus.items():
                genre_text = " ".join(albums).lower()
                all_texts.append(genre_text)
                genre_labels.append(genre)
            
            # Fit TF-IDF vectorizer
            self.tfidf_vectorizer = TfidfVectorizer(
                max_features=1000,
                stop_words='english',
                ngram_range=(1, 2)
            )
            
            tfidf_matrix = self.tfidf_vectorizer.fit_transform(all_texts)
            
            # Store genre vectors
            for i, genre in enumerate(genre_labels):
                self.genre_vectors[genre] = tfidf_matrix[i].toarray().flatten()

    def get_synonyms_and_related(self, word: str, max_words: int = 5) -> List[str]:
        """Get synonyms and related words using WordNet"""
        if not NLTK_AVAILABLE:
            return []
        
        synonyms = set()
        try:
            for syn in wordnet.synsets(word):
                for lemma in syn.lemmas():
                    synonym = lemma.name().replace('_', ' ')
                    if synonym.lower() != word.lower() and len(synonym) > 2:
                        synonyms.add(synonym)
                
                # Get hypernyms (more general terms)
                for hypernym in syn.hypernyms():
                    for lemma in hypernym.lemmas():
                        hyper_word = lemma.name().replace('_', ' ')
                        if hyper_word.lower() != word.lower() and len(hyper_word) > 2:
                            synonyms.add(hyper_word)
            
            return list(synonyms)[:max_words]
        except Exception:
            return []

    def analyze_genre_semantics(self, genres: List[str]) -> Dict:
        """Analyze semantic content of genres using ML"""
        if not SKLEARN_AVAILABLE or not self.tfidf_vectorizer:
            return {"semantic_words": [], "genre_similarity": {}}
        
        # Find most similar genre from our corpus
        genre_similarities = {}
        
        for input_genre in genres:
            best_match = None
            best_score = 0
            
            for corpus_genre in self.genre_vectors.keys():
                if corpus_genre.lower() in input_genre.lower() or input_genre.lower() in corpus_genre.lower():
                    genre_similarities[input_genre] = corpus_genre
                    best_match = corpus_genre
                    break
            
            if not best_match:
                # Use cosine similarity if no direct match
                input_vector = self.tfidf_vectorizer.transform([input_genre.lower()]).toarray().flatten()
                
                for corpus_genre, genre_vector in self.genre_vectors.items():
                    similarity = cosine_similarity([input_vector], [genre_vector])[0][0]
                    if similarity > best_score:
                        best_score = similarity
                        best_match = corpus_genre
                
                if best_match:
                    genre_similarities[input_genre] = best_match
        
        # Extract semantic words from matched genres
        semantic_words = []
        for matched_genre in genre_similarities.values():
            if matched_genre in self.genre_vectors:
                # Get top TF-IDF features for this genre
                genre_vector = self.genre_vectors[matched_genre]
                feature_names = self.tfidf_vectorizer.get_feature_names_out()
                
                # Get top 10 features
                top_indices = np.argsort(genre_vector)[-10:]
                semantic_words.extend([feature_names[i] for i in top_indices if len(feature_names[i]) > 3])
        
        return {
            "semantic_words": list(set(semantic_words)),
            "genre_similarity": genre_similarities
        }

    def generate_semantic_variations(self, base_concepts: List[str]) -> List[str]:
        """Generate semantic variations using ML and linguistic analysis"""
        variations = []
        
        for concept in base_concepts:
            # Get synonyms using WordNet
            synonyms = self.get_synonyms_and_related(concept)
            variations.extend(synonyms)
            
            # Generate morphological variations
            variations.extend(self._generate_morphological_variants(concept))
            
            # Generate semantic combinations
            for category, words in self.semantic_categories.items():
                if len(variations) < 50:  # Limit to prevent explosion
                    # Create semantic combinations
                    combo = f"{random.choice(words)} {concept}"
                    variations.append(combo.title())
        
        return list(set(variations))

    def _generate_morphological_variants(self, word: str) -> List[str]:
        """Generate morphological variants of a word"""
        variants = []
        
        # Simple morphological rules
        if word.endswith('e'):
            variants.append(word + 'd')  # past tense
            variants.append(word[:-1] + 'ing')  # present participle
        elif word.endswith('y'):
            variants.append(word[:-1] + 'ies')  # plural
            variants.append(word[:-1] + 'ied')  # past tense
        else:
            variants.append(word + 's')    # plural
            variants.append(word + 'ed')   # past tense
            variants.append(word + 'ing')  # present participle
        
        # Add prefixes
        prefixes = ['un', 're', 'pre', 'anti', 'sub', 'super']
        for prefix in prefixes:
            variants.append(prefix + word)
        
        return [v for v in variants if len(v) > 2 and len(v) < 15]

    def cluster_concepts(self, concepts: List[str], n_clusters: int = 3) -> Dict[str, List[str]]:
        """Cluster concepts using K-means for diverse title generation"""
        if not SKLEARN_AVAILABLE or len(concepts) < n_clusters:
            return {"cluster_0": concepts}
        
        try:
            # Vectorize concepts
            vectorizer = TfidfVectorizer(max_features=100)
            concept_vectors = vectorizer.fit_transform(concepts)
            
            # Perform clustering
            kmeans = KMeans(n_clusters=min(n_clusters, len(concepts)), random_state=42, n_init=10)
            cluster_labels = kmeans.fit_predict(concept_vectors)
            
            # Group concepts by cluster
            clusters = defaultdict(list)
            for concept, label in zip(concepts, cluster_labels):
                clusters[f"cluster_{label}"].append(concept)
            
            return dict(clusters)
            
        except Exception as e:
            print(f"Clustering failed: {e}")
            return {"cluster_0": concepts}

    def generate_ml_enhanced_titles(self, playlist_data: Dict, mood: str = "", num_titles: int = 15) -> List[Tuple[str, float]]:
        """Generate titles using all ML techniques"""
        genres = playlist_data.get("genres", [])
        all_genres = playlist_data.get("all_genres", [])
        
        # Step 1: Semantic analysis
        semantic_analysis = self.analyze_genre_semantics(genres)
        semantic_words = semantic_analysis["semantic_words"]
        
        # Step 2: Generate base concepts
        base_concepts = []
        
        # Add mood-based concepts
        if mood:
            mood_concepts = mood.split()
            base_concepts.extend(mood_concepts)
        
        # Add genre-specific concepts
        base_concepts.extend(semantic_words[:10])
        
        # Add semantic category words
        for category in random.sample(list(self.semantic_categories.keys()), 3):
            base_concepts.extend(random.sample(self.semantic_categories[category], 2))
        
        # Step 3: Generate semantic variations
        expanded_concepts = self.generate_semantic_variations(base_concepts)
        all_concepts = base_concepts + expanded_concepts
        
        # Step 4: Cluster concepts for diversity
        concept_clusters = self.cluster_concepts(all_concepts)
        
        # Step 5: Generate titles from each cluster
        generated_titles = []
        
        for cluster_name, cluster_concepts in concept_clusters.items():
            # Pattern-based generation
            patterns = [
                "{concept}",
                "The {concept}",
                "{adj} {concept}",
                "{concept} {concept2}",
                "{concept} in {location}",
                "Before the {concept}",
                "After {concept}",
                "{concept} & {concept2}",
                "The Last {concept}",
                "{concept} Dreams"
            ]
            
            adjectives = ["Silent", "Hidden", "Electric", "Frozen", "Golden", "Broken", "Perfect"]
            locations = ["Void", "Space", "Time", "Mind", "Distance", "Shadows"]
            
            for pattern in patterns[:5]:  # Limit patterns per cluster
                try:
                    if len(cluster_concepts) >= 2:
                        title = pattern.format(
                            concept=random.choice(cluster_concepts).capitalize(),
                            concept2=random.choice(cluster_concepts).capitalize(),
                            adj=random.choice(adjectives),
                            location=random.choice(locations)
                        )
                        score = self._score_ml_title(title, genres, mood, semantic_words)
                        generated_titles.append((title, score))
                except (KeyError, IndexError):
                    continue
        
        # Step 6: Generate AI-assisted titles with semantic priming
        ai_titles = self._generate_semantically_primed_ai_titles(
            playlist_data, mood, semantic_words, num_titles=5
        )
        generated_titles.extend(ai_titles)
        
        # Step 7: Remove duplicates and sort by score
        unique_titles = {}
        for title, score in generated_titles:
            if title not in unique_titles or unique_titles[title] < score:
                unique_titles[title] = score
        
        sorted_titles = sorted(unique_titles.items(), key=lambda x: x[1], reverse=True)
        return sorted_titles[:num_titles]

    def _generate_semantically_primed_ai_titles(self, playlist_data: Dict, mood: str, 
                                              semantic_words: List[str], num_titles: int = 5) -> List[Tuple[str, float]]:
        """Generate AI titles with semantic priming"""
        genres = ", ".join(playlist_data.get("genres", ["music"]))
        semantic_context = ", ".join(semantic_words[:5]) if semantic_words else ""
        
        prompts = [
            # Semantic association prompt
            f"""Create an album title that associates with these concepts: {semantic_context}
            Genre: {genres}, Mood: {mood}
            Make it 2-3 words, abstract and evocative. Examples: "Velvet Thunder", "Crystal Maze", "Silent Frequency"
            Title only:""",
            
            # Contradiction prompt for creativity
            f"""Create an album title using contradictory or unexpected word combinations for {genres} music.
            Think: "Gentle Violence", "Bright Darkness", "Quiet Storm"
            Semantic context: {semantic_context}
            2-3 words only:""",
            
            # Synesthetic prompt
            f"""Create an album title mixing senses and abstract concepts for {genres} music.
            Examples: "Tasting Colors", "Hearing Textures", "Touching Sound"
            Context words: {semantic_context}
            Title only, 2-3 words:""",
            
            # Temporal/spatial prompt
            f"""Create an album title suggesting movement through time or space for {genres}.
            Examples: "Before Dawn", "After Silence", "Between Worlds"
            Use context: {semantic_context}
            Title only:""",
            
            # Emotional architecture prompt
            f"""Create an album title that treats emotions like physical structures for {genres}.
            Examples: "Building Sadness", "Demolishing Joy", "Architectural Hearts"
            Context: {semantic_context}
            Title only:"""
        ]
        
        ai_titles = []
        for prompt in prompts:
            for attempt in range(2):  # 2 attempts per prompt
                title = self._call_gemini_api(prompt)
                if title and title != "New Album":
                    score = self._score_ml_title(title, playlist_data.get("genres", []), mood, semantic_words)
                    ai_titles.append((title, score))
        
        return ai_titles

    def _score_ml_title(self, title: str, genres: List[str], mood: str, semantic_words: List[str]) -> float:
        """Advanced ML-based scoring"""
        score = 0.0
        title_lower = title.lower()
        title_words = title_lower.split()
        
        # Length scoring (prefer 2-3 words)
        if len(title_words) == 2:
            score += 3.0
        elif len(title_words) == 3:
            score += 2.5
        elif len(title_words) == 1:
            score += 1.0
        else:
            score -= 1.0
        
        # Semantic relevance using cosine similarity
        if SKLEARN_AVAILABLE and self.tfidf_vectorizer and semantic_words:
            try:
                title_vector = self.tfidf_vectorizer.transform([title_lower]).toarray().flatten()
                semantic_text = " ".join(semantic_words)
                semantic_vector = self.tfidf_vectorizer.transform([semantic_text]).toarray().flatten()
                
                similarity = cosine_similarity([title_vector], [semantic_vector])[0][0]
                score += similarity * 5.0
            except:
                pass
        
        # Novelty scoring (penalize common words)
        common_words = ["love", "heart", "soul", "dream", "night", "time", "life", "world"]
        novelty_penalty = sum(2.0 for word in title_words if word in common_words)
        score -= novelty_penalty
        
        # Phonetic appeal (alliteration bonus)
        if len(title_words) >= 2:
            first_letters = [word[0] for word in title_words if word]
            if len(set(first_letters)) < len(first_letters):  # Has repeated first letters
                score += 1.5
        
        # Mood alignment
        if mood:
            mood_words = mood.lower().split()
            mood_alignment = sum(1.0 for mood_word in mood_words 
                               for title_word in title_words 
                               if mood_word in title_word or title_word in mood_word)
            score += mood_alignment
        
        # Complexity bonus (avoid too simple titles)
        if any(len(word) >= 6 for word in title_words):
            score += 1.0
        
        return max(0.0, score)

    def _call_gemini_api(self, prompt: str) -> str:
        """Enhanced API call with error handling"""
        if not GEMINI_API_KEY:
            return "New Album"
        
        try:
            headers = {"Content-Type": "application/json"}
            data = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.95,  # High creativity
                    "maxOutputTokens": 25,
                    "topP": 0.9,
                    "topK": 40
                }
            }
            
            url = f"{GEMINI_API_URL}?key={GEMINI_API_KEY}"
            response = requests.post(url, headers=headers, json=data, timeout=30)
            
            if response.status_code == 200:
                response_json = response.json()
                if 'candidates' in response_json and len(response_json['candidates']) > 0:
                    text = response_json['candidates'][0]['content']['parts'][0]['text']
                    title = self._clean_title(text)
                    return title if title and len(title) >= 3 else "New Album"
            
            return "New Album"
        except Exception as e:
            print(f"Error calling Gemini API: {e}")
            return "New Album"

    def _clean_title(self, raw_title: str) -> str:
        """Clean and validate generated title"""
        if not raw_title:
            return ""
        
        # Remove quotes and extra whitespace
        title = raw_title.strip().replace('"', '').replace("'", "")
        
        # Remove common prefixes/suffixes from AI responses
        prefixes_to_remove = ["title:", "album title:", "album:", "suggested title:"]
        for prefix in prefixes_to_remove:
            if title.lower().startswith(prefix):
                title = title[len(prefix):].strip()
        
        # Capitalize properly
        title = ' '.join(word.capitalize() for word in title.split())
        
        # Validate length
        if len(title) > 60 or len(title) < 3:
            return ""
        
        # Check for reasonable word count
        word_count = len(title.split())
        if word_count > 6 or word_count < 1:
            return ""
        
        return title

    def generate_title(self, playlist_data: Dict, mood: str = "") -> str:
        """Main ML-enhanced title generation function"""
        try:
            # Generate multiple candidates using ML
            title_candidates = self.generate_ml_enhanced_titles(playlist_data, mood, num_titles=20)
            
            if title_candidates:
                best_title = title_candidates[0][0]
                print(f"🎵 Generated {len(title_candidates)} candidates, selected: '{best_title}' (score: {title_candidates[0][1]:.2f})")
                print(f"🔍 Top 5 candidates: {[f'{t} ({s:.1f})' for t, s in title_candidates[:5]]}")
                return best_title
            else:
                print("⚠️ ML generation failed, falling back to basic generation")
                return self._fallback_generation(playlist_data, mood)
                
        except Exception as e:
            print(f"❌ Error in ML title generation: {e}")
            return self._fallback_generation(playlist_data, mood)

    def _fallback_generation(self, playlist_data: Dict, mood: str = "") -> str:
        """Fallback to original prompting method"""
        # This is your original generate_title function as fallback
        genres = ", ".join(playlist_data.get("genres", ["music"]))
        mood_to_use = mood if mood else playlist_data.get("mood_descriptor", "")
        
        prompt = f"""Generate a unique, evocative, and original album title for a music album.

ALBUM INFORMATION:
- Genre(s): {genres}
- Mood/Atmosphere: {mood_to_use}

IMPORTANT INSTRUCTIONS:
1. Create a title that is TRULY UNIQUE and has never been used before
2. The title should be 2-4 words in length
3. Avoid generic words that are commonly used in album titles
4. The title should subtly reflect the musical genre(s) without being obvious
5. Do not use words from the genre names directly in the title

FORMAT:
Return ONLY the title without any quotation marks, explanation, or additional text.
"""
        
        return self._call_gemini_api(prompt)

# Updated main function
def generate_title(playlist_data, mood=""):
    """Enhanced title generation with ML and comprehensive fallbacks"""
    generator = MLEnhancedTitleGenerator()
    return generator.generate_title(playlist_data, mood)