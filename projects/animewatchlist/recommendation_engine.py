import time
import requests
from anime_series_grouper import get_anime_details, group_anime_series, create_series_mapping
from cold_start_recommender import generate_recommendations as generate_cold_start_recs

JIKAN_API_BASE = "https://api.jikan.moe/v4"

def fetch_candidate_anime(pages=3):
    """
    Fetches top anime from Jikan to serve as recommendation candidates.
    """
    candidates = []
    for page in range(1, pages + 1):
        print(f"Fetching page {page} of top anime for candidates...")
        try:
            url = f"{JIKAN_API_BASE}/top/anime"
            params = {"page": page, "limit": 25} # Increased limit slightly
            response = requests.get(url, params=params)

            if response.status_code == 429:
                print("Rate limited, waiting 2 seconds...")
                time.sleep(2)
                response = requests.get(url, params=params)

            response.raise_for_status()
            data = response.json().get("data", [])
            candidates.extend(data)
            # No sleep here, will sleep in the main loop if needed
        except requests.exceptions.RequestException as e:
            print(f"Error fetching candidate anime page {page}: {e}")
            break

    return candidates

def get_recommendations(user_watched_list, test_mode=False):
    """
    Orchestrates the entire recommendation process.
    - user_watched_list: A list of anime dicts from the db, MUST include 'user_rating'.
    - test_mode: If True, uses a smaller set of candidates to avoid long waits.
    """
    if not user_watched_list:
        print("User has no watched anime. Cannot generate personalized recommendations.")
        return []

    # 1. Get full details for the user's watched list
    print("Step 1: Fetching details for user's watched list...")
    user_watched_details = []
    for a in user_watched_list:
        if a.get('mal_id'):
            details = get_anime_details(a['mal_id'])
            if details:
                # Add user_rating to the detailed dict
                details['user_rating'] = a.get('user_rating')
                user_watched_details.append(details)
            time.sleep(0.5) # Politeness sleep

    # 2. Group watched anime into series to know what series user has seen
    print("Step 2: Grouping watched anime into series...")
    watched_series_groups = group_anime_series(user_watched_details)
    watched_series_mapping = create_series_mapping(watched_series_groups)
    watched_anime_ids = set(watched_series_mapping.keys())

    # 3. Fetch candidate anime
    pages_to_fetch = 1 if test_mode else 3
    print(f"Step 3: Fetching {pages_to_fetch} page(s) of candidate anime...")
    candidates = fetch_candidate_anime(pages=pages_to_fetch)

    # 4. Filter candidates
    print("Step 4: Filtering candidates...")
    filtered_candidates = [
        c for c in candidates
        if c['mal_id'] not in watched_anime_ids
    ]
    print(f"  - Started with {len(candidates)}, filtered down to {len(filtered_candidates)} candidates.")

    # 5. Generate initial recommendations using the cold start recommender
    print("Step 5: Generating initial recommendations with cold start model...")
    initial_recs = generate_cold_start_recs(user_watched_details, filtered_candidates)

    # 6. Post-process recommendations to group them by series
    print("Step 6: Post-processing recommendations to group by series...")
    if not initial_recs:
        print("No recommendations were generated.")
        return []

    rec_anime_list = [r['anime'] for r in initial_recs]
    rec_series_groups = group_anime_series(rec_anime_list)

    final_recommendations = []
    processed_series_roots = set()

    for group in rec_series_groups:
        if not group:
            continue

        group.sort(key=lambda a: (a.get('aired', {}).get('from') or '9999', a['mal_id']))
        root_anime = group[0]

        if root_anime['mal_id'] in processed_series_roots:
            continue

        original_rec = next((r for r in initial_recs if r['anime']['mal_id'] == root_anime['mal_id']), None)

        if original_rec:
            original_rec['series_info'] = {
                'total_seasons': len(group),
                'seasons': [{'title': s['title'], 'mal_id': s['mal_id']} for s in group]
            }
            final_recommendations.append(original_rec)
            processed_series_roots.add(root_anime['mal_id'])

    final_recommendations.sort(key=lambda x: x['score'], reverse=True)

    print(f"Generated {len(final_recommendations)} final series recommendations.")
    return final_recommendations


if __name__ == '__main__':
    mock_user_list_from_db = [
        {'mal_id': 16498, 'user_rating': 5}, # Attack on Titan
        {'mal_id': 11061, 'user_rating': 5}, # Hunter x Hunter
        {'mal_id': 205, 'user_rating': 4},   # Samurai Champloo
        {'mal_id': 2251, 'user_rating': 2}    # Baccano!
    ]

    print("--- Testing Recommendation Engine (in Test Mode) ---")
    recommendations = get_recommendations(mock_user_list_from_db, test_mode=True)

    print("\n--- FINAL RECOMMENDATIONS ---")
    for rec in recommendations[:5]: # Print top 5
        anime = rec['anime']
        series_info = rec['series_info']
        print(f"SERIES: {anime['title']} (Score: {rec['score']:.2f})")
        print(f"  -> Why: {rec['explanation']}")
        if series_info['total_seasons'] > 1:
            print(f"  -> This is a series with {series_info['total_seasons']} parts.")
        print("-" * 20)
