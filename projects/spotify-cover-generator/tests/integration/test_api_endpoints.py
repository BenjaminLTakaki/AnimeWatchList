import pytest
from app import app, db
from unittest.mock import patch

@pytest.fixture
def client():
    """Create test client"""
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    
    with app.test_client() as client:
        with app.app_context():
            db.create_all()
            yield client
            db.drop_all()

class TestAPIEndpoints:
    def test_health_endpoint(self, client):
        """Test health check endpoint"""
        response = client.get('/health')
        assert response.status_code in [200, 503]  # Healthy or degraded
        data = response.get_json()
        assert 'status' in data
        assert 'timestamp' in data
    
    def test_generate_get(self, client):
        """Test GET request to generate endpoint"""
        response = client.get('/generate')
        assert response.status_code == 200
        assert b'Spotify Music Cover Generator' in response.data
    
    @patch('generator.generate_cover')
    def test_generate_post_success(self, mock_generate, client):
        """Test successful cover generation"""
        mock_generate.return_value = {
            "title": "Test Album",
            "output_path": "/path/to/test.png",
            "item_name": "Test Playlist",
            "genres": ["rock", "pop"],
            "all_genres": ["rock", "pop", "indie"],
            "mood": "energetic",
            "image_data_base64": "base64data"
        }
        
        response = client.post('/generate', data={
            'playlist_url': 'https://open.spotify.com/playlist/test123',
            'mood': 'energetic'
        })
        
        assert response.status_code == 200
        assert b'Test Album' in response.data
    
    def test_generate_post_invalid_url(self, client):
        """Test generation with invalid URL"""
        response = client.post('/generate', data={
            'playlist_url': 'invalid_url',
            'mood': 'energetic'
        })
        
        assert response.status_code == 200
        assert b'error' in response.data.lower() or b'invalid' in response.data.lower()