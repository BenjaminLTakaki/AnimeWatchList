import pytest
from unittest.mock import patch, MagicMock
import spotify_client

class TestSpotifyClient:
    @patch('spotify_client.spotipy.Spotify')
    def test_initialize_spotify_success(self, mock_spotify):
        """Test successful Spotify initialization"""
        mock_instance = MagicMock()
        mock_spotify.return_value = mock_instance
        
        result = spotify_client.initialize_spotify()
        assert result is True
    
    def test_validate_spotify_url_valid(self):
        """Test valid Spotify URL validation"""
        valid_url = "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M"
        is_valid, message = spotify_client.validate_spotify_url(valid_url)
        assert is_valid is True
        assert "Valid Spotify URL" in message
    
    def test_validate_spotify_url_invalid(self):
        """Test invalid URL validation"""
        invalid_url = "https://youtube.com/watch?v=123"
        is_valid, message = spotify_client.validate_spotify_url(invalid_url)
        assert is_valid is False
        assert "Not a Spotify URL" in message