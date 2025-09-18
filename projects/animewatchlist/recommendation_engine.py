import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from .mal_api_client import get_top_anime, get_anime_details
from anime_series_grouper import group_anime_series, create_series_mapping
from cold_start_recommender import generate_recommendations as generate_cold_start_recs

MAX_WORKERS = 10  # Increased workers due to caching and higher API limits
REQUEST_DELAY = 0  # No longer needed with MAL API and caching

def fetch_candidate_anime(pages=1):
    """
    Fetches top anime from MAL API to serve as recommendation candidates.
    """
    print(f"Fetching {pages} page(s) of top anime from MAL API...")
    candidates = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_page = {executor.submit(get_top_anime, page): page for page in range(1, pages + 1)}
        for future in as_completed(future_to_page):
            page = future_to_page[future]
            try:
                data = future.result()
                if data:
                    candidates.extend(data)
                print(f"Successfully fetched page {page} of top anime.")
            except Exception as exc:
                print(f"Page {page} generated an exception: {exc}")
    return candidates

def fetch_anime_details_batch(anime_ids, max_workers=MAX_WORKERS):
    """
    Fetch multiple anime details concurrently using the new MAL client.
    The client handles caching, so we can increase concurrency.
    """
    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_id = {executor.submit(get_anime_details, anime_id): anime_id for anime_id in anime_ids}
        for future in as_completed(future_to_id):
            anime_id = future_to_id[future]
            try:
                details = future.result()
                if details:
                    results[anime_id] = details
            except Exception as e:
                print(f"Error fetching details for anime ID {anime_id}: {e}")
    return results

def get_recommendations(user_watched_list, test_mode=True):
    """
    Optimized recommendation process for production deployment.
    - user_watched_list: A list of anime dicts from the db, MUST include 'user_rating'.
    - test_mode: If True, uses minimal candidates to prevent timeouts.
    """
    if not user_watched_list:
        print("User has no watched anime. Cannot generate personalized recommendations.")
        return []

    try:
        # 1. Get basic user preferences without fetching all details
        print("Step 1: Analyzing user preferences...")
        user_ratings = {a.get('mal_id'): a.get('user_rating') for a in user_watched_list if a.get('mal_id')}
        loved_anime = [a for a in user_watched_list if a.get('user_rating') == 5]
        liked_anime = [a for a in user_watched_list if a.get('user_rating') == 4]
        
        print(f"  - Found {len(loved_anime)} loved anime, {len(liked_anime)} liked anime")

        # 2. Fetch candidates - reduced for production
        pages_to_fetch = 1 if test_mode else 2
        print(f"Step 2: Fetching {pages_to_fetch} page(s) of candidate anime...")
        candidates = fetch_candidate_anime(pages=pages_to_fetch)

        # 3. Filter candidates to remove already watched
        watched_ids = set(user_ratings.keys())
        filtered_candidates = [c for c in candidates if c['mal_id'] not in watched_ids]
        print(f"  - Started with {len(candidates)}, filtered to {len(filtered_candidates)} candidates")

        # 4. Limit candidates for production to prevent timeout
        max_candidates = 15 if test_mode else 25
        if len(filtered_candidates) > max_candidates:
            filtered_candidates = filtered_candidates[:max_candidates]
            print(f"  - Limited to {max_candidates} candidates for performance")

        # 5. Fetch details for a subset of user's loved/liked anime
        print("Step 3: Fetching details for key user anime...")
        key_user_anime_ids = []
        for anime in (loved_anime + liked_anime)[:10]:  # Limit to top 10
            if anime.get('mal_id'):
                key_user_anime_ids.append(anime['mal_id'])
        
        user_details_batch = fetch_anime_details_batch(key_user_anime_ids, max_workers=2)
        
        # Add ratings to detailed anime
        user_watched_details = []
        for anime_id, details in user_details_batch.items():
            if details:
                details['user_rating'] = user_ratings.get(anime_id)
                user_watched_details.append(details)

        # 6. Fetch details for candidates
        print("Step 4: Fetching candidate details...")
        candidate_ids = [c['mal_id'] for c in filtered_candidates]
        candidate_details_batch = fetch_anime_details_batch(candidate_ids, max_workers=MAX_WORKERS)

        # Convert to list format expected by cold start recommender
        detailed_candidates = []
        for candidate in filtered_candidates:
            if candidate['mal_id'] in candidate_details_batch:
                detailed_candidates.append(candidate_details_batch[candidate['mal_id']])

        # 7. Generate recommendations using cold start
        print("Step 5: Generating recommendations...")
        if not user_watched_details or not detailed_candidates:
            print("Insufficient data for recommendations")
            return []

        recommendations = generate_cold_start_recs(user_watched_details, detailed_candidates)

        # 8. Basic series grouping (simplified for production)
        print("Step 6: Processing final recommendations...")
        final_recommendations = []
        
        for rec in recommendations[:10]:  # Limit to top 10
            # Add basic series info without complex grouping
            anime = rec['anime']
            rec['series_info'] = {
                'total_seasons': 1,  # Simplified - assume single season
                'seasons': [{'title': anime['title'], 'mal_id': anime['mal_id']}]
            }
            final_recommendations.append(rec)

        print(f"Generated {len(final_recommendations)} final recommendations")
        return final_recommendations[:8]  # Return top 8 recommendations

    except Exception as e:
        print(f"Error in recommendation generation: {e}")
        import traceback
        traceback.print_exc()
        return []