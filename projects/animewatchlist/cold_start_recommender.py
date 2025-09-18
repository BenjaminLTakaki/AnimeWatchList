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
        return profile

    for anime in user_watched_list:
        if not anime or 'mal_id' not in anime:
            continue

        mal_id = anime['mal_id']
        rating = anime.get('user_rating')
        profile['user_ratings'][mal_id] = rating

        genres = [genre['name'] for genre in anime.get('genres', [])]
        studios = [studio['name'] for studio in anime.get('studios', [])]

        if rating == 5:
            profile['loved_anime_titles'][mal_id] = anime.get('title', 'Unknown')
            for genre in genres:
                profile['loved_genres'][genre] += 1
            for studio in studios:
                profile['favorite_studios'][studio] += 2 # Higher weight for loved anime studios
        elif rating == 4:
            for genre in genres:
                profile['liked_genres'][genre] += 1
            for studio in studios:
                profile['favorite_studios'][studio] += 1
        elif rating is not None and rating <= 2:
            for genre in genres:
                profile['disliked_genres'][genre] += 1

    return profile

def score_anime(anime_details, profile):
    """
    Scores a candidate anime based on the user's profile and provides an explanation.
    """
    score = 0.5  # Base score
    explanations = []

    if not anime_details:
        return 0, "Could not retrieve anime details."

    # Avoid recommending anime the user has already rated
    if anime_details['mal_id'] in profile['user_ratings']:
        return 0, "Already rated by the user."

    # --- Genre Scoring ---
    anime_genres = {genre['name'] for genre in anime_details.get('genres', [])}
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
    anime_studios = {studio['name'] for studio in anime_details.get('studios', [])}
    if anime_studios.intersection(profile['favorite_studios'].keys()):
        score += 0.1
        explanations.append("From a studio you seem to like.")

    # --- MAL Score Bonus ---
    mal_score = anime_details.get('score')
    if mal_score and mal_score > 8.0:
        score += 0.1
        explanations.append(f"It's highly rated on MAL ({mal_score}/10).")

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
    - candidates: List of simple anime dicts to be considered for recommendation.
    """
    print("Creating user profile...")
    profile = create_user_profile(user_watched_list)

    recommendations = []

    print(f"Scoring {len(candidates)} candidate anime...")
    for candidate in candidates:
        mal_id = candidate.get('mal_id') or candidate.get('id')
        if not mal_id:
            continue

        # Fetch full details for the candidate anime
        candidate_details = get_anime_details(mal_id)
        if not candidate_details:
            continue

        score, explanation = score_anime(candidate_details, profile)

        if score > 0.55: # Set a threshold to only show relevant recommendations
            recommendations.append({
                "anime": candidate_details,
                "score": score,
                "explanation": explanation
            })

    # Sort recommendations by score, descending
    recommendations.sort(key=lambda x: x['score'], reverse=True)

    return recommendations


if __name__ == '__main__':
    # This is a mock test since we can't access the DB from here.
    # In a real scenario, this data would come from get_user_anime_list and get_anime_details.
    mock_user_watched_list = [
        {
            'mal_id': 16498, 'title': 'Attack on Titan', 'user_rating': 5,
            'genres': [{'name': 'Action'}, {'name': 'Drama'}, {'name': 'Fantasy'}],
            'studios': [{'name': 'Wit Studio'}]
        },
        {
            'mal_id': 30276, 'title': 'One-Punch Man', 'user_rating': 4,
            'genres': [{'name': 'Action'}, {'name': 'Comedy'}, {'name': 'Sci-Fi'}],
            'studios': [{'name': 'Madhouse'}]
        },
        {
            'mal_id': 205, 'title': 'Samurai Champloo', 'user_rating': 5,
            'genres': [{'name': 'Action'}, {'name': 'Adventure'}, {'name': 'Comedy'}],
            'studios': [{'name': 'Manglobe'}]
        },
        {
            'mal_id': 11061, 'title': 'Hunter x Hunter (2011)', 'user_rating': 5,
            'genres': [{'name': 'Action'}, {'name': 'Adventure'}, {'name': 'Fantasy'}],
            'studios': [{'name': 'Madhouse'}]
        },
        {
            'mal_id': 2251, 'title': 'Baccano!', 'user_rating': 2,
            'genres': [{'name': 'Mystery'}, {'name': 'Supernatural'}],
            'studios': [{'name': 'Brain\'s Base'}]
        }
    ]

    # Candidates for recommendation
    mock_candidates = [
        {'mal_id': 25777}, # Attack on Titan S2 (should be high score)
        {'mal_id': 9253},  # Steins;Gate (High MAL score, different genre)
        {'mal_id': 1535},  # Death Note (High MAL score, some genre overlap)
        {'mal_id': 32281}, # KonoSuba (Comedy, might be lower score)
        {'mal_id': 5114},  # Fullmetal Alchemist: Brotherhood (Action/Adventure, high score)
        {'mal_id': 20},    # Naruto (Action/Adventure, long running)
    ]

    print("--- Testing Cold Start Recommender ---")
    recommendations = generate_recommendations(mock_user_watched_list, mock_candidates)

    print("\n--- Top Recommendations ---")
    for rec in recommendations:
        anime = rec['anime']
        print(f"Anime: {anime['title']} (Score: {rec['score']:.2f})")
        print(f"  -> Why: {rec['explanation']}")
        print(f"  -> MAL Score: {anime['score']}, Genres: {[g['name'] for g in anime['genres']]}")
        print("-" * 20)
