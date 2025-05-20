import requests
import json
from config import GEMINI_API_KEY, GEMINI_API_URL

def generate_title(playlist_data, mood=""):
    """Generate album title using Gemini API"""
    if not GEMINI_API_KEY:
        print("ERROR: Missing Gemini API key. Please set GEMINI_API_KEY in your .env file.")
        return "New Album"
    
    genres = ", ".join(playlist_data.get("genres", ["music"]))
    mood_to_use = mood if mood else playlist_data.get("mood_descriptor", "")
    
    style_elements = playlist_data.get("style_elements", [])
    style_text = ", ".join(style_elements) if style_elements else ""
    
    # Completely redesigned prompt to generate more diverse and unique titles
    prompt = f"""Generate a unique, evocative, and original album title for a music album.

ALBUM INFORMATION:
- Genre(s): {genres}
- Mood/Atmosphere: {mood_to_use}
- Visual style: {style_text}

IMPORTANT INSTRUCTIONS:
1. Create a title that is TRULY UNIQUE and has never been used before
2. The title should be 2-5 words in length
3. Avoid generic words that are commonly used in album titles within these genres
4. Do not use overly poetic, clichéd, or stereotypical terms
5. The title should subtly reflect the musical genre(s) without being obvious
6. Do not use words from the genre names directly in the title
7. The title should have depth, intrigue, and be memorable
8. Aim for something that sounds modern and fresh, not dated
9. Avoid ALL common title patterns found in the given music genres

DIVERSITY REQUIREMENTS:
- If the genre is electronic, avoid words like: "pulse", "digital", "electric", "neon", "wave", "cyber"
- If the genre is hip-hop/rap, avoid words like: "street", "flow", "beat", "rhyme", "hustle"
- If the genre is rock, avoid words like: "stone", "edge", "wild", "rebel", "fury"
- If the genre is indie, avoid words like: "whisper", "echo", "dream", "wonder"
- If the genre is pop, avoid words like: "star", "shine", "glow", "bright", "love"

FORMAT:
Return ONLY the title without any quotation marks, explanation, or additional text.
"""

    try:
        # Prepare the request to Gemini API
        headers = {
            "Content-Type": "application/json",
        }
        
        data = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": prompt
                        }
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 1.0,  # Increased temperature for more randomness
                "maxOutputTokens": 20,
                "topP": 0.9,  # Adjusted for more diversity
                "topK": 40   # Added to increase diversity
            }
        }
        
        # Add API key to URL
        url = f"{GEMINI_API_URL}?key={GEMINI_API_KEY}"
        
        # Make the request
        response = requests.post(url, headers=headers, json=data)
        
        if response.status_code == 200:
            response_json = response.json()
            # Extract the title from the response
            if 'candidates' in response_json and len(response_json['candidates']) > 0:
                text = response_json['candidates'][0]['content']['parts'][0]['text']
                # Clean up the title
                title = text.strip().replace('"', '').replace("'", "")
                return title[:50] if title and len(title) >= 3 else "New Album"
        
        print(f"Error generating title: {response.text}")
        return "New Album"
        
    except Exception as e:
        print(f"Error generating title: {e}")
        return "New Album"