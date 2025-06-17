import pytest
from unittest.mock import patch, MagicMock
from models import GenreAnalysis, PlaylistData, LoraModel

class TestGenreAnalysis:
    def test_from_genre_list_empty(self):
        """Test GenreAnalysis with empty genre list"""
        analysis = GenreAnalysis.from_genre_list([])
        assert analysis.top_genres == []
        assert analysis.mood == "balanced"
    
    def test_from_genre_list_basic(self):
        """Test GenreAnalysis with basic genre list"""
        genres = ["rock", "pop", "rock", "electronic"]
        analysis = GenreAnalysis.from_genre_list(genres)
        assert "rock" in analysis.top_genres
        assert len(analysis.all_genres) == 4
    
    def test_get_percentages(self):
        """Test percentage calculation"""
        genres = ["rock"] * 3 + ["pop"] * 2 + ["jazz"] * 1
        analysis = GenreAnalysis.from_genre_list(genres)
        percentages = analysis.get_percentages(max_genres=3)
        
        assert len(percentages) <= 3
        assert percentages[0]["name"] == "rock"
        assert percentages[0]["percentage"] == 50  # 3/6 = 50%

class TestPlaylistData:
    def test_to_dict(self):
        """Test PlaylistData serialization"""
        genre_analysis = GenreAnalysis(top_genres=["rock", "pop"])
        playlist = PlaylistData(
            item_name="Test Playlist",
            genre_analysis=genre_analysis,
            spotify_url="https://open.spotify.com/playlist/test"
        )
        
        data = playlist.to_dict()
        assert data["item_name"] == "Test Playlist"
        assert "rock" in data["genres"]
        assert data["spotify_url"] == "https://open.spotify.com/playlist/test"

class TestLoraModel:
    def test_is_local(self):
        """Test LoRA model local detection"""
        local_lora = LoraModel(name="test", source_type="local")
        link_lora = LoraModel(name="test", source_type="link")
        
        assert local_lora.is_local is True
        assert link_lora.is_local is False
    
    def test_to_dict(self):
        """Test LoRA model serialization"""
        lora = LoraModel(
            name="test_lora",
            source_type="local",
            path="/path/to/lora.safetensors",
            trigger_words=["style", "artistic"]
        )
        
        data = lora.to_dict()
        assert data["name"] == "test_lora"
        assert data["source_type"] == "local"
        assert "style" in data["trigger_words"]
