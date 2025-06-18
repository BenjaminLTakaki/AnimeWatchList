import matplotlib.pyplot as plt
import matplotlib
import io
import base64
from collections import Counter
matplotlib.use('Agg')  # Use non-interactive backend

def generate_genre_chart(genres):
    """Generate a bar chart visualization of genres"""
    if not genres:
        return None
    
    # Count genre frequencies if it's a list
    if isinstance(genres, list):
        # Count genres by frequency using Counter
        genre_counter = Counter(genres)
        genres_sorted = genre_counter.most_common(8)  # Get top 8 genres
        labels = [genre for genre, _ in genres_sorted]
        values = [count for _, count in genres_sorted]
    else:
        return None
    
    # Create bar chart with improved styling
    fig = plt.figure(figsize=(12, 8), dpi=100)
    ax = fig.add_subplot(111)
    
    # Plot bars with Spotify green color gradient
    bars = ax.bar(
        labels, values, 
        color=['#1DB954', '#1ED760', '#24E066', '#30D67B', '#3DCF8B', '#4AC89D', '#57C0AD', '#63B9BE'][:len(labels)],
        width=0.6, edgecolor='#444444'
    )
    
    # Add count labels on top of bars
    for bar in bars:
        height = bar.get_height()
        ax.text(
            bar.get_x() + bar.get_width()/2., height + 0.05,
            f'{int(height)}', ha='center', va='bottom', 
            color='white', fontsize=12, fontweight='bold',
            bbox=dict(boxstyle="round,pad=0.3", facecolor='#333', alpha=0.7)
        )
    
    # Set labels and title with improved font
    ax.set_xlabel('Genres', fontsize=14, fontweight='bold', color='white', labelpad=10)
    ax.set_ylabel('Frequency', fontsize=14, fontweight='bold', color='white', labelpad=10)
    ax.set_title('Genre Analysis', fontsize=18, fontweight='bold', color='#1DB954', pad=20)
    
    # Configure chart aesthetics
    ax.set_facecolor('#2a2a2a')
    fig.patch.set_facecolor('#1e1e1e')
    
    # Style the axis and ticks
    ax.tick_params(axis='x', colors='white', labelsize=12, rotation=45)
    plt.setp(ax.get_xticklabels(), ha="right")  # Set horizontal alignment separately
    
    ax.tick_params(axis='y', colors='white', labelsize=12)
    
    # Add subtle grid lines
    ax.grid(axis='y', color='#444444', alpha=0.3, linestyle='--')
    
    # Adjust layout for better fit with rotated labels
    plt.tight_layout()
    
    # Save to base64 for embedding in HTML
    buffer = io.BytesIO()
    plt.savefig(buffer, format='png', transparent=True, dpi=100)
    buffer.seek(0)
    image_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
    plt.close(fig)  # Close figure to free memory
    
    return f"data:image/png;base64,{image_base64}"