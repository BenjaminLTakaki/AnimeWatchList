import requests
import time
import re
from collections import deque

# Jikan API base URL
JIKAN_API_BASE = "https://api.jikan.moe/v4"

# In-memory cache to store API responses
RELATIONS_CACHE = {}
ANIME_DETAILS_CACHE = {}

def get_anime_details(mal_id):
    """Fetches full anime details from the Jikan API with caching."""
    if mal_id in ANIME_DETAILS_CACHE:
        return ANIME_DETAILS_CACHE[mal_id]

    print(f"Fetching details for {mal_id} from API.")
    try:
        url = f"{JIKAN_API_BASE}/anime/{mal_id}"
        response = requests.get(url)
        if response.status_code == 429:
            time.sleep(2)
            response = requests.get(url)
        response.raise_for_status()
        data = response.json().get("data")
        ANIME_DETAILS_CACHE[mal_id] = data
        return data
    except requests.exceptions.RequestException as e:
        print(f"Error fetching anime details for ID {mal_id}: {e}")
        return None

def get_anime_relations(mal_id):
    """Fetches anime relations from the Jikan API with caching."""
    if mal_id in RELATIONS_CACHE:
        return RELATIONS_CACHE[mal_id]

    print(f"Fetching relations for {mal_id} from API.")
    try:
        url = f"{JIKAN_API_BASE}/anime/{mal_id}/relations"
        response = requests.get(url)
        if response.status_code == 429:
            time.sleep(2)
            response = requests.get(url)
        response.raise_for_status()
        data = response.json().get("data", [])
        RELATIONS_CACHE[mal_id] = data
        return data
    except requests.exceptions.RequestException as e:
        print(f"Error fetching anime relations for ID {mal_id}: {e}")
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
    """
    series_groups = []
    processed_ids = set()

    # Pre-fetch details for all anime in the list to normalize titles
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

            # 1. Group by official relations
            relations = get_anime_relations(current_id)
            for relation_group in relations:
                # We only care about sequels, prequels, and main stories
                if relation_group['relation'] in ['Sequel', 'Prequel', 'Parent story', 'Main story']:
                    for entry in relation_group['entry']:
                        if entry['type'] == 'anime' and entry['mal_id'] not in visited_in_group:
                            queue.append(entry['mal_id'])
                            visited_in_group.add(entry['mal_id'])

        # 2. Group by title similarity (for anime in the initial list)
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
        # Using aired date is more reliable if available
        group.sort(key=lambda a: (a.get('aired', {}).get('from') or '9999', a['mal_id']))
        root_anime = group[0]
        series_id = root_anime['mal_id']

        for anime in group:
            mapping[anime['mal_id']] = series_id

    return mapping

if __name__ == '__main__':
    # Test grouping with a sample list of anime
    # Attack on Titan S1, S2, and a movie
    sample_anime_list = [
        {'mal_id': 16498}, # Attack on Titan
        {'mal_id': 25777}, # Attack on Titan S2
        {'mal_id': 23775}, # Movie
        {'mal_id': 510},   # Code Geass R1
        {'mal_id': 2904},  # Code Geass R2
        {'mal_id': 34599}  # A silent voice (unrelated)
    ]

    print("--- Testing Series Grouping ---")
    grouped_series = group_anime_series(sample_anime_list)

    print(f"\nFound {len(grouped_series)} series groups:")
    for i, group in enumerate(grouped_series):
        print(f"  Group {i+1}:")
        for anime in group:
            print(f"    - {anime['title']} (ID: {anime['mal_id']})")

    print("\n--- Testing Series Mapping ---")
    series_map = create_series_mapping(grouped_series)
    print("Anime ID -> Series ID Mapping:")
    for anime_id, series_id in sorted(series_map.items()):
        print(f"  {anime_id} -> {series_id}")
