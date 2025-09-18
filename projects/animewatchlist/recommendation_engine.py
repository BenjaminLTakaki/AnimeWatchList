import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from anime_series_grouper import get_anime_details, get_top_anime, get_seasonal_anime, group_anime_series, create_series_mapping
from cold_start_recommender import generate_recommendations as generate_cold_start_recs

# MAL API configuration
MAL_API_BASE = "https://api.myanimelist.net/v2"
MAX_WORKERS = 2  # Reduced for MAL API rate limits
REQUEST_DELAY = 0.3  # Reduced delay for MAL API (less restrictive than Jikan)

def fetch_candidate_anime(pages=1, use_seasonal=False):  
    """
    Fetches anime from MAL API to serve as recommendation candidates.
    Optimized for production with proper rate limiting for MAL API.
    """
    candidates = []
    
    if use_seasonal:
        # Get current season anime
        import datetime
        current_year = datetime.datetime.now().year
        current_month = datetime.datetime.now().month
        
        # Determine current season
        if current_month in [12, 1, 2]:
            season = 'winter'
        elif current_month in [3, 4, 5]:
            season = 'spring'
        elif current_month in [6, 7, 8]:
            season = 'summer'
        else:
            season = 'fall'
        
        print(f"Fetching {current_year} {season} seasonal anime...")
        try:
            seasonal_data = get_seasonal_anime(current_year, season, limit=25 * pages)
            candidates.extend(seasonal_data)
        except Exception as e:
            print(f"Error fetching seasonal anime: {e}")
    
    # Get top anime from different categories
    ranking_types = ['all', 'airing', 'tv', 'movie', 'bypopularity']
    
    for i in range(pages):
        ranking_type = ranking_types[i % len(ranking_types)]
        print(f"Fetching page {i+1} of top {ranking_type} anime for candidates...")
        
        try:
            # Use MAL API to get top anime
            top_anime = get_top_anime(ranking_type, limit=25)
            candidates.extend(top_anime)

            # Rate limiting between requests
            if i < pages - 1:
                time.sleep(REQUEST_DELAY)

        except Exception as e:
            print(f"Error fetching candidate anime from {ranking_type}: {e}")
            break

    return candidates

def fetch_anime_details_batch(anime_ids, max_workers=MAX_WORKERS):
    """
    Fetch multiple anime details concurrently with rate limiting for MAL API.
    """
    results = {}

    def fetch_single(anime_id):
        try:
            time.sleep(REQUEST_DELAY)  # Rate limiting
            details = get_anime_details(anime_id)
            return anime_id, details
        except Exception as e:
            print(f"Error fetching details for {anime_id}: {e}")
            return anime_id, None

    # Use ThreadPoolExecutor for concurrent requests
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all requests
        future_to_id = {executor.submit(fetch_single, anime_id): anime_id for anime_id in anime_ids}

        # Process completed requests
        for future in as_completed(future_to_id):
            anime_id, details = future.result()
            if details:
                results[anime_id] = details

    return results

def get_user_genre_preferences(user_watched_list):
    """
    Extract user's genre preferences from their watched list.
    Helper function for better candidate filtering.
    """
    genre_scores = {}
    genre_counts = {}
    
    for anime in user_watched_list:
        rating = anime.get('user_rating')
        genres = anime.get('genres', [])
        
        if rating and genres:
            for genre in genres:
                genre_name = genre.get('name', '') if isinstance(genre, dict) else str(genre)
                if genre_name:
                    if genre_name not in genre_scores:
                        genre_scores[genre_name] = 0
                        genre_counts[genre_name] = 0
                    
                    genre_scores[genre_name] += rating
                    genre_counts[genre_name] += 1
    
    # Calculate average scores per genre
    genre_averages = {}
    for genre, total_score in genre_scores.items():
        count = genre_counts[genre]
        if count > 0:
            genre_averages[genre] = total_score / count
    
    # Return genres sorted by average rating
    return sorted(genre_averages.items(), key=lambda x: x[1], reverse=True)

def filter_candidates_by_preferences(candidates, user_watched_list, max_candidates=25):
    """
    Filter and prioritize candidates based on user preferences.
    """
    if not user_watched_list:
        return candidates[:max_candidates]
    
    # Get user's watched anime IDs
    watched_ids = set()
    for anime in user_watched_list:
        watched_ids.add(anime.get('mal_id'))
    
    # Get user's genre preferences
    preferred_genres = get_user_genre_preferences(user_watched_list)
    preferred_genre_names = [genre[0] for genre in preferred_genres[:5]]  # Top 5 genres
    
    # Score and filter candidates
    scored_candidates = []
    
    for candidate in candidates:
        candidate_id = candidate.get('mal_id')
        
        # Skip if already watched
        if candidate_id in watched_ids:
            continue
        
        # Calculate preference score
        score = 0
        candidate_genres = candidate.get('genres', [])
        
        for genre in candidate_genres:
            genre_name = genre.get('name', '') if isinstance(genre, dict) else str(genre)
            if genre_name in preferred_genre_names:
                # Higher score for preferred genres
                preference_index = preferred_genre_names.index(genre_name)
                score += (5 - preference_index)  # 5 points for most preferred, 1 for least
        
        # Bonus for high MAL scores
        mal_score = candidate.get('score')
        if mal_score and mal_score > 7.5:
            score += 2
        elif mal_score and mal_score > 8.5:
            score += 3
        
        # Bonus for popularity (lower popularity number = more popular)
        popularity = candidate.get('popularity')
        if popularity and popularity <= 1000:
            score += 2
        elif popularity and popularity <= 100:
            score += 3
        
        scored_candidates.append((candidate, score))
    
    # Sort by score and return top candidates
    scored_candidates.sort(key=lambda x: x[1], reverse=True)
    return [candidate for candidate, score in scored_candidates[:max_candidates]]

def get_recommendations(user_watched_list, test_mode=True):
    """
    Optimized recommendation process using MAL API for production deployment.
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

        # 2. Fetch candidates - reduced for production, mix of seasonal and top anime
        pages_to_fetch = 1 if test_mode else 2
        print(f"Step 2: Fetching {pages_to_fetch} page(s) of candidate anime...")
        
        # Mix seasonal anime with top anime for variety
        candidates = []
        
        # Get some seasonal anime for freshness
        seasonal_candidates = fetch_candidate_anime(pages=1, use_seasonal=True)
        candidates.extend(seasonal_candidates)
        
        # Get top anime for quality
        top_candidates = fetch_candidate_anime(pages=pages_to_fetch, use_seasonal=False)
        candidates.extend(top_candidates)
        
        # Remove duplicates
        seen_ids = set()
        unique_candidates = []
        for candidate in candidates:
            candidate_id = candidate.get('mal_id')
            if candidate_id and candidate_id not in seen_ids:
                seen_ids.add(candidate_id)
                unique_candidates.append(candidate)
        
        candidates = unique_candidates

        # 3. Filter candidates based on user preferences
        print("Step 3: Filtering candidates based on preferences...")
        max_candidates = 15 if test_mode else 30
        filtered_candidates = filter_candidates_by_preferences(candidates, user_watched_list, max_candidates)
        print(f"  - Filtered to {len(filtered_candidates)} relevant candidates")

        # 4. Fetch details for a subset of user's loved/liked anime
        print("Step 4: Fetching details for key user anime...")
        key_user_anime_ids = []
        for anime in (loved_anime + liked_anime)[:8]:  # Reduced to 8 for performance
            if anime.get('mal_id'):
                key_user_anime_ids.append(anime['mal_id'])
        
        user_details_batch = fetch_anime_details_batch(key_user_anime_ids, max_workers=1)
        
        # Add ratings to detailed anime
        user_watched_details = []
        for anime_id, details in user_details_batch.items():
            if details:
                details['user_rating'] = user_ratings.get(anime_id)
                user_watched_details.append(details)

        # 5. Fetch details for top filtered candidates
        print("Step 5: Fetching candidate details...")
        candidate_ids = [c['mal_id'] for c in filtered_candidates]
        candidate_details_batch = fetch_anime_details_batch(candidate_ids, max_workers=MAX_WORKERS)

        # Convert to list format expected by cold start recommender
        detailed_candidates = []
        for candidate in filtered_candidates:
            if candidate['mal_id'] in candidate_details_batch:
                detailed_candidates.append(candidate_details_batch[candidate['mal_id']])

        # 6. Generate recommendations using cold start
        print("Step 6: Generating recommendations...")
        if not user_watched_details or not detailed_candidates:
            print("Insufficient data for recommendations")
            return []

        recommendations = generate_cold_start_recs(user_watched_details, detailed_candidates)

        # 7. Enhanced series grouping with MAL relation data
        print("Step 7: Processing final recommendations...")
        final_recommendations = []
        
        for rec in recommendations[:8]:  # Limit to top 8
            # Use MAL API relation data for better series info
            anime = rec['anime']
            relations = anime.get('relations', [])
            
            # Count related anime (sequels, prequels, etc.)
            related_count = len([r for r in relations if r.get('relation_type', '').lower() in 
                               ['sequel', 'prequel', 'side_story', 'parent_story']])
            
            rec['series_info'] = {
                'total_seasons': max(1, related_count + 1),
                'seasons': [{'title': anime['title'], 'mal_id': anime['mal_id']}],
                'has_relations': len(relations) > 0,
                'relation_types': [r.get('relation_type') for r in relations]
            }
            final_recommendations.append(rec)

        print(f"Generated {len(final_recommendations)} final recommendations")
        return final_recommendations

    except Exception as e:
        print(f"Error in recommendation generation: {e}")
        import traceback
        traceback.print_exc()
        return []