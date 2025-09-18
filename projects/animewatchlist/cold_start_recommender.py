import re
from collections import defaultdict
from anime_series_grouper import get_anime_details, normalize_title

def create_user_profile(user_watched_list):
    """
    Creates a user preference profile from their watched list.
    user_watched_list is a list of anime dicts from the db, including 'user_rating'
    and full anime details fetched from the API.
    """
    profile = {
        "loved_genres": defaultdict(int),
        "liked_genres": defaultdict(int),
        "disliked_genres": defaultdict(int),
        "favorite_studios": defaultdict(int),
        "loved_anime_titles": {}, # mal_id -> title
        "user_ratings": {} # mal_id -> rating
    }

    if not user_watched_list:
        print("create_user_profile: No watched list provided")
        return profile

    print(f"create_user_profile: Processing {len(user_watched_list)} anime")
    
    for anime in user_watched_list:
        if not anime:
            continue
            
        # Handle both 'id' and 'mal_id' keys
        mal_id = anime.get('mal_id') or anime.get('id')
        if not mal_id:
            print(f"Skipping anime with no mal_id: {anime.get('title', 'Unknown')}")
            continue

        rating = anime.get('user_rating')
        if rating is None:
            print(f"Skipping anime with no rating: {anime.get('title', 'Unknown')}")
            continue
            
        profile['user_ratings'][mal_id] = rating
        print(f"Processing {anime.get('title', 'Unknown')} (ID: {mal_id}, Rating: {rating})")

        # Handle genres - MAL API format vs stored format
        genres = []
        if anime.get('genres'):
            if isinstance(anime['genres'], str):
                # Stored format: "Action,Drama,Fantasy"
                genres = [g.strip() for g in anime['genres'].split(',') if g.strip()]
            elif isinstance(anime['genres'], list):
                # MAL API format: [{'name': 'Action'}, ...]
                genres = []
                for genre in anime['genres']:
                    if isinstance(genre, dict):
                        genres.append(genre.get('name', ''))
                    else:
                        genres.append(str(genre))

        # Handle studios
        studios = []
        if anime.get('studios'):
            if isinstance(anime['studios'], str):
                # Stored format: "Studio Name"
                studios = [anime['studios']] if anime['studios'] else []
            elif isinstance(anime['studios'], list):
                # MAL API format: [{'name': 'Studio Name'}, ...]
                for studio in anime['studios']:
                    if isinstance(studio, dict):
                        studios.append(studio.get('name', ''))
                    else:
                        studios.append(str(studio))
        elif anime.get('studio'):
            # Single studio stored format
            studios = [anime['studio']] if anime['studio'] else []

        print(f"  Genres: {genres}")
        print(f"  Studios: {studios}")

        if rating == 5:
            profile['loved_anime_titles'][mal_id] = anime.get('title', 'Unknown')
            for genre in genres:
                if genre:
                    profile['loved_genres'][genre] += 1
            for studio in studios:
                if studio:
                    profile['favorite_studios'][studio] += 2 # Higher weight for loved anime studios
        elif rating == 4:
            for genre in genres:
                if genre:
                    profile['liked_genres'][genre] += 1
            for studio in studios:
                if studio:
                    profile['favorite_studios'][studio] += 1
        elif rating is not None and rating <= 2:
            for genre in genres:
                if genre:
                    profile['disliked_genres'][genre] += 1

    print(f"Profile created:")
    print(f"  Loved genres: {dict(profile['loved_genres'])}")
    print(f"  Liked genres: {dict(profile['liked_genres'])}")
    print(f"  Favorite studios: {dict(profile['favorite_studios'])}")
    print(f"  Total ratings: {len(profile['user_ratings'])}")
    
    return profile

def score_anime(anime_details, profile):
    """
    Scores a candidate anime based on the user's profile and provides an explanation.
    """
    score = 0.5  # Base score
    explanations = []

    if not anime_details:
        return 0, "Could not retrieve anime details."

    # Handle both 'id' and 'mal_id' keys
    mal_id = anime_details.get('mal_id') or anime_details.get('id')
    if not mal_id:
        return 0, "No valid mal_id found."

    # Avoid recommending anime the user has already rated
    if mal_id in profile['user_ratings']:
        return 0, "Already rated by the user."

    # --- Genre Scoring ---
    anime_genres = set()
    if anime_details.get('genres'):
        if isinstance(anime_details['genres'], list):
            for genre in anime_details['genres']:
                if isinstance(genre, dict):
                    anime_genres.add(genre.get('name', ''))
                else:
                    anime_genres.add(str(genre))
        elif isinstance(anime_details['genres'], str):
            anime_genres = set(g.strip() for g in anime_details['genres'].split(',') if g.strip())

    loved_matches = anime_genres.intersection(profile['loved_genres'].keys())
    liked_matches = anime_genres.intersection(profile['liked_genres'].keys())
    disliked_matches = anime_genres.intersection(profile['disliked_genres'].keys())

    if loved_matches:
        score += 0.3
        explanations.append(f"It's in genres you love, like {next(iter(loved_matches))}.")
    elif liked_matches: # Use elif to not over-reward
        score += 0.15
        explanations.append(f"Matches liked genres, such as {next(iter(liked_matches))}.")

    if disliked_matches:
        score -= 0.4 # Stronger penalty for disliked genres
        explanations.append(f"May not be for you, as it's in the {next(iter(disliked_matches))} genre.")

    # --- Studio Scoring ---
    anime_studios = set()
    if anime_details.get('studios'):
        if isinstance(anime_details['studios'], list):
            for studio in anime_details['studios']:
                if isinstance(studio, dict):
                    anime_studios.add(studio.get('name', ''))
                else:
                    anime_studios.add(str(studio))
        elif isinstance(anime_details['studios'], str):
            anime_studios.add(anime_details['studios'])
    elif anime_details.get('studio'):
        anime_studios.add(anime_details['studio'])

    if anime_studios.intersection(profile['favorite_studios'].keys()):
        score += 0.1
        explanations.append("From a studio you seem to like.")

    # --- MAL Score Bonus ---
    mal_score = anime_details.get('score') or anime_details.get('mean')
    if mal_score:
        try:
            mal_score = float(mal_score)
            if mal_score > 8.0:
                score += 0.1
                explanations.append(f"It's highly rated on MAL ({mal_score}/10).")
        except (ValueError, TypeError):
            pass

    # --- Similarity to Loved Anime ---
    normalized_candidate_title = normalize_title(anime_details.get('title', ''))
    for loved_id, loved_title in profile['loved_anime_titles'].items():
        if normalize_title(loved_title) == normalized_candidate_title:
            # This is likely a different season of a show they love
            score += 0.5 # Big bonus
            explanations.append(f"It's in the same series as '{loved_title}', which you loved.")
            break # Stop after finding one match

    # Final explanation
    if not explanations:
        final_explanation = "This might be something new for you to explore."
    else:
        final_explanation = " ".join(explanations)

    return max(0, min(1, score)), final_explanation # Clamp score between 0 and 1

def generate_recommendations(user_watched_list, candidates):
    """
    Generates a scored and sorted list of recommendations.
    - user_watched_list: List of detailed anime dicts the user has watched and rated.
    - candidates: List of anime dicts to be considered for recommendation.
    """
    print(f"generate_recommendations called with {len(user_watched_list)} watched, {len(candidates)} candidates")
    
    if not user_watched_list:
        print("No user watched list provided")
        return []
    
    if not candidates:
        print("No candidates provided")
        return []
    
    print("Creating user profile...")
    profile = create_user_profile(user_watched_list)
    
    # Check if profile has meaningful data
    total_profile_data = (len(profile['loved_genres']) + len(profile['liked_genres']) + 
                         len(profile['user_ratings']))
    if total_profile_data == 0:
        print("Profile has no meaningful data")
        return []

    recommendations = []

    print(f"Scoring {len(candidates)} candidate anime...")
    for candidate in candidates:
        # Handle both direct anime details and simple candidate format
        if isinstance(candidate, dict):
            if candidate.get('genres') or candidate.get('studios'):
                # This is already detailed anime data
                candidate_details = candidate
            else:
                # This is simple candidate data, need to fetch details
                mal_id = candidate.get('mal_id') or candidate.get('id')
                if not mal_id:
                    continue
                candidate_details = get_anime_details(mal_id)
        else:
            continue
            
        if not candidate_details:
            continue

        score, explanation = score_anime(candidate_details, profile)

        if score > 0.55: # Set a threshold to only show relevant recommendations
            recommendations.append({
                "anime": candidate_details,
                "score": score,
                "explanation": explanation
            })

    print(f"Found {len(recommendations)} recommendations above threshold")

    # Sort recommendations by score, descending
    recommendations.sort(key=lambda x: x['score'], reverse=True)

    return recommendations


if __name__ == '__main__':
    print("Cold start recommender test - would need actual data to run")