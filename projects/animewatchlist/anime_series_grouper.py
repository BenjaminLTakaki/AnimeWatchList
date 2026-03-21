import re
import requests
import time
import os
from collections import deque

# Official MyAnimeList API base URL
MAL_API_BASE = "https://api.myanimelist.net/v2"

def get_mal_headers():
    """Get authentication headers for MAL API requests."""
    client_id = os.environ.get('MAL_CLIENT_ID')
    if not client_id:
        raise ValueError("MAL_CLIENT_ID not found in environment variables")
    
    return {
        'X-MAL-CLIENT-ID': client_id,
        'Content-Type': 'application/json'
    }

def get_anime_details(mal_id):
    """
    Fetch detailed anime information from official MyAnimeList API.
    Returns a dictionary with anime details or None if failed.
    """
    try:
        # Ensure mal_id is valid
        if not mal_id or mal_id == 'None':
            print(f"Invalid mal_id provided: {mal_id}")
            return None
            
        # Convert to int to ensure it's valid
        try:
            mal_id = int(mal_id)
        except (ValueError, TypeError):
            print(f"Could not convert mal_id to int: {mal_id}")
            return None
        
        # MAL API endpoint for anime details with comprehensive fields
        fields = [
            'id', 'title', 'main_picture', 'alternative_titles',
            'start_date', 'end_date', 'synopsis', 'mean', 'rank', 'popularity',
            'num_list_users', 'num_scoring_users', 'nsfw', 'created_at', 'updated_at',
            'media_type', 'status', 'genres', 'num_episodes', 'start_season',
            'broadcast', 'source', 'average_episode_duration', 'rating',
            'pictures', 'background', 'related_anime', 'related_manga',
            'recommendations', 'studios', 'statistics'
        ]
        
        url = f"{MAL_API_BASE}/anime/{mal_id}"
        params = {'fields': ','.join(fields)}
        headers = get_mal_headers()
        
        print(f"Fetching anime {mal_id} from MAL API...")
        response = requests.get(url, params=params, headers=headers, timeout=10)
        
        # Handle rate limiting (MAL API uses different status codes)
        if response.status_code == 429:
            print(f"Rate limited while fetching {mal_id}, waiting 1 second...")
            time.sleep(1)
            response = requests.get(url, params=params, headers=headers, timeout=10)
        
        # Handle not found
        if response.status_code == 404:
            print(f"Anime {mal_id} not found on MAL")
            return None
            
        response.raise_for_status()
        data = response.json()
        
        if not data:
            print(f"Empty response for anime {mal_id}")
            return None
        
        # Debug: Print the raw data structure
        print(f"MAL API response for {mal_id}: {data.keys()}")
        
        # Ensure we have the required ID field
        anime_id = data.get('id')
        if not anime_id:
            print(f"No 'id' field in MAL response for {mal_id}: {data}")
            return None
        
        # Convert MAL API response to standardized format (similar to Jikan structure)
        result = {
            'mal_id': anime_id,  # Use the ID from the response
            'id': anime_id,      # Also include as 'id' for compatibility
            'title': data.get('title', 'Unknown Title'),
            'episodes': data.get('num_episodes'),
            'score': data.get('mean'),
            'images': {
                'jpg': {
                    'image_url': data.get('main_picture', {}).get('medium', ''),
                    'small_image_url': data.get('main_picture', {}).get('large', ''),
                    'large_image_url': data.get('main_picture', {}).get('large', '')
                }
            },
            'main_picture': {
                'medium': data.get('main_picture', {}).get('medium', '')
            },
            'url': f"https://myanimelist.net/anime/{anime_id}",
            'genres': data.get('genres', []),
            'studios': data.get('studios', []),
            'aired': {
                'from': data.get('start_date'),
                'to': data.get('end_date')
            },
            'type': data.get('media_type', ''),
            'status': data.get('status', ''),
            'synopsis': data.get('synopsis', ''),
            'year': data.get('start_season', {}).get('year') if data.get('start_season') else None,
            'season': data.get('start_season', {}).get('season') if data.get('start_season') else None,
            'source': data.get('source', ''),
            'duration': data.get('average_episode_duration'),
            'rating': data.get('rating', ''),
            'members': data.get('num_list_users', 0),
            'popularity': data.get('popularity', 0),
            'rank': data.get('rank', 0),
            'relations': data.get('related_anime', []),
            'alternative_titles': data.get('alternative_titles', {}),
            'background': data.get('background', ''),
            'broadcast': data.get('broadcast', {}),
            'pictures': data.get('pictures', []),
            'recommendations': data.get('recommendations', []),
            'statistics': data.get('statistics', {})
        }
        
        # Final validation
        if not result['mal_id']:
            print(f"ERROR: mal_id is still None after processing for {mal_id}")
            return None
            
        print(f"Successfully fetched anime: {result['title']} (ID: {result['mal_id']})")
        return result
        
    except requests.exceptions.RequestException as e:
        print(f"Network error fetching anime {mal_id}: {e}")
        return None
    except Exception as e:
        print(f"Error fetching anime details for ID {mal_id}: {e}")
        return None

def search_anime(query, limit=10):
    """
    Search for anime using the official MAL API.
    Returns a list of anime matching the search query.
    """
    try:
        url = f"{MAL_API_BASE}/anime"
        params = {
            'q': query,
            'limit': limit,
            'fields': 'id,title,main_picture,mean,num_episodes,media_type,status,genres,start_date'
        }
        headers = get_mal_headers()
        
        response = requests.get(url, params=params, headers=headers, timeout=10)
        
        if response.status_code == 429:
            print(f"Rate limited while searching '{query}', waiting 1 second...")
            time.sleep(1)
            response = requests.get(url, params=params, headers=headers, timeout=10)
        
        response.raise_for_status()
        data = response.json()
        
        results = []
        for item in data.get('data', []):
            node = item.get('node', {})
            results.append({
                'mal_id': node.get('id'),
                'title': node.get('title'),
                'episodes': node.get('num_episodes'),
                'score': node.get('mean'),
                'main_picture': {
                    'medium': node.get('main_picture', {}).get('medium', '')
                },
                'type': node.get('media_type'),
                'status': node.get('status'),
                'genres': node.get('genres', []),
                'start_date': node.get('start_date')
            })
        
        return results
        
    except Exception as e:
        print(f"Error searching anime: {e}")
        return []

def get_seasonal_anime(year, season, limit=20):
    """
    Get seasonal anime using MAL API.
    Seasons: winter, spring, summer, fall
    """
    try:
        url = f"{MAL_API_BASE}/anime/season/{year}/{season}"
        params = {
            'limit': limit,
            'fields': 'id,title,main_picture,mean,num_episodes,media_type,status,genres,start_date,popularity,rank'
        }
        headers = get_mal_headers()
        
        response = requests.get(url, params=params, headers=headers, timeout=10)
        
        if response.status_code == 429:
            print(f"Rate limited while fetching {year} {season} anime, waiting 1 second...")
            time.sleep(1)
            response = requests.get(url, params=params, headers=headers, timeout=10)
        
        response.raise_for_status()
        data = response.json()
        
        results = []
        for item in data.get('data', []):
            node = item.get('node', {})
            results.append({
                'mal_id': node.get('id'),
                'title': node.get('title'),
                'episodes': node.get('num_episodes'),
                'score': node.get('mean'),
                'main_picture': {
                    'medium': node.get('main_picture', {}).get('medium', '')
                },
                'type': node.get('media_type'),
                'status': node.get('status'),
                'genres': node.get('genres', []),
                'popularity': node.get('popularity'),
                'rank': node.get('rank')
            })
        
        return results
        
    except Exception as e:
        print(f"Error fetching seasonal anime: {e}")
        return []

def get_top_anime(ranking_type='all', limit=20, offset=0):
    """
    Get top anime by ranking from MAL API.
    ranking_type: 'all', 'airing', 'upcoming', 'tv', 'ova', 'movie', 'special', 'bypopularity', 'favorite'
    """
    try:
        url = f"{MAL_API_BASE}/anime/ranking"
        params = {
            'ranking_type': ranking_type,
            'limit': limit,
            'offset': offset,
            'fields': 'id,title,main_picture,mean,num_episodes,media_type,status,genres,rank,popularity'
        }
        headers = get_mal_headers()
        
        response = requests.get(url, params=params, headers=headers, timeout=10)
        
        if response.status_code == 429:
            print(f"Rate limited while fetching top {ranking_type} anime, waiting 1 second...")
            time.sleep(1)
            response = requests.get(url, params=params, headers=headers, timeout=10)
        
        response.raise_for_status()
        data = response.json()
        
        results = []
        for item in data.get('data', []):
            node = item.get('node', {})
            results.append({
                'mal_id': node.get('id'),
                'title': node.get('title'),
                'episodes': node.get('num_episodes'),
                'score': node.get('mean'),
                'main_picture': {
                    'medium': node.get('main_picture', {}).get('medium', '')
                },
                'type': node.get('media_type'),
                'status': node.get('status'),
                'genres': node.get('genres', []),
                'rank': node.get('rank'),
                'popularity': node.get('popularity'),
                'ranking': item.get('ranking', {})
            })
        
        return results
        
    except Exception as e:
        print(f"Error fetching top anime: {e}")
        return []

def normalize_title(title):
    """Normalizes an anime title for similarity comparison."""
    if not title:
        return ""
    title = title.lower()
    title = re.sub(r'season\s*\d+', '', title, flags=re.IGNORECASE).strip()
    title = re.sub(r'\s+s\d+', '', title, flags=re.IGNORECASE).strip()
    title = re.sub(r'\d+(st|nd|rd|th)\s*season', '', title, flags=re.IGNORECASE).strip()
    title = re.sub(r'\(\d{4}\)', '', title).strip()
    title = re.sub(r'\b(tv)\b', '', title, flags=re.IGNORECASE).strip()
    title = re.sub(r'\b(the final season)\b', '', title, flags=re.IGNORECASE).strip()
    title = re.sub(r'\b(part\s*\d+)\b', '', title, flags=re.IGNORECASE).strip()
    title = re.sub(r'\s+ix\b', ' 9', title)
    title = re.sub(r'\s+iv\b', ' 4', title)
    title = re.sub(r'\s+v\b', ' 5', title)
    title = re.sub(r'\s+vi\b', ' 6', title)
    title = re.sub(r'\s+vii\b', ' 7', title)
    title = re.sub(r'\s+viii\b', ' 8', title)
    title = re.sub(r'\s+x\b', ' 10', title)
    title = re.sub(r'\s+i\b', ' 1', title)
    title = re.sub(r'\s+ii\b', ' 2', title)
    title = re.sub(r'\s+iii\b', ' 3', title)
    title = re.sub(r'[^\w\s]', '', title)
    title = re.sub(r'\s+', ' ', title).strip()
    return title

def group_anime_series(anime_list):
    """
    Groups a list of anime into series using relations and title similarity.
    Now uses official MAL API for better relation data.
    """
    series_groups = []
    processed_ids = set()

    # Pre-fetch details for all anime in the list to normalize titles and get relations
    initial_anime_details = {}
    for anime_data in anime_list:
        mal_id = anime_data.get('id') or anime_data.get('mal_id')
        if mal_id and mal_id not in initial_anime_details:
            details = get_anime_details(mal_id)
            if details:
                initial_anime_details[mal_id] = details

    normalized_titles = {
        mal_id: normalize_title(details.get('title', ''))
        for mal_id, details in initial_anime_details.items()
    }

    for mal_id, details in initial_anime_details.items():
        if mal_id in processed_ids:
            continue

        current_series = {}
        queue = deque([mal_id])
        visited_in_group = {mal_id}

        while queue:
            current_id = queue.popleft()

            if current_id in processed_ids:
                continue

            current_details = get_anime_details(current_id)
            if not current_details:
                continue

            current_series[current_id] = current_details
            processed_ids.add(current_id)

            # Use MAL API relations to find related anime
            relations = current_details.get('relations', [])
            for relation in relations:
                related_id = relation.get('node', {}).get('id')
                if related_id and related_id not in visited_in_group:
                    # Check if it's a sequel, prequel, or related series
                    relation_type = relation.get('relation_type', '').lower()
                    if relation_type in ['sequel', 'prequel', 'side_story', 'parent_story', 'full_story']:
                        queue.append(related_id)
                        visited_in_group.add(related_id)

        # Group by title similarity (for anime in the initial list)
        base_title = normalized_titles.get(mal_id)
        if base_title:
            for other_id, other_title in normalized_titles.items():
                if other_id not in processed_ids and other_title == base_title:
                    if other_id not in visited_in_group:
                         queue.append(other_id)
                         visited_in_group.add(other_id)

        if current_series:
            series_groups.append(list(current_series.values()))

    return series_groups

def create_series_mapping(series_groups):
    """Creates a mapping from anime_id to a root series_id."""
    mapping = {}
    for group in series_groups:
        if not group:
            continue

        # Find the root of the series (oldest or lowest ID)
        # Using start date is more reliable if available
        def sort_key(anime):
            start_date = anime.get('aired', {}).get('from') or anime.get('start_date')
            return (start_date or '9999', anime['mal_id'])
        
        group.sort(key=sort_key)
        root_anime = group[0]
        series_id = root_anime['mal_id']

        for anime in group:
            mapping[anime['mal_id']] = series_id

    return mapping

if __name__ == '__main__':
    # Test the MAL API functions
    print("--- Testing MAL API Functions ---")
    
    # Test get_anime_details
    print("\n1. Testing get_anime_details:")
    anime = get_anime_details(16498)  # Attack on Titan
    if anime:
        print(f"   ✅ {anime['title']} - Episodes: {anime['episodes']}, Score: {anime['score']}")
    else:
        print("   ❌ Failed to fetch anime details")
    
    # Test search
    print("\n2. Testing search:")
    results = search_anime("attack on titan", limit=3)
    if results:
        for result in results[:3]:
            print(f"   ✅ {result['title']} (ID: {result['mal_id']})")
    else:
        print("   ❌ Search failed")
    
    # Test top anime
    print("\n3. Testing top anime:")
    top = get_top_anime('all', limit=3)
    if top:
        for anime in top[:3]:
            print(f"   ✅ #{anime.get('rank', '?')} - {anime['title']} (Score: {anime['score']})")
    else:
        print("   ❌ Failed to fetch top anime")
    
    # Test grouping with a sample list of anime
    sample_anime_list = [
        {'mal_id': 16498}, # Attack on Titan
        {'mal_id': 25777}, # Attack on Titan S2
        {'mal_id': 510},   # Code Geass R1
        {'mal_id': 2904},  # Code Geass R2
    ]

    print("\n4. Testing Series Grouping:")
    try:
        grouped_series = group_anime_series(sample_anime_list)
        print(f"   ✅ Found {len(grouped_series)} series groups:")
        for i, group in enumerate(grouped_series):
            print(f"     Group {i+1}:")
            for anime in group:
                print(f"       - {anime['title']} (ID: {anime['mal_id']})")
    except Exception as e:
        print(f"   ❌ Grouping failed: {e}")