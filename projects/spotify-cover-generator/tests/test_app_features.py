import pytest
import unittest.mock as mock
import os
import json
from pathlib import Path

# Assuming your Flask app instance is named 'app' in 'app.py'
# and can be imported. Adjust if necessary.
# For now, we might not be able to import app directly without issues in this environment.
# We will mock relevant parts of app or test utils directly.

# Mock BASE_DIR and other necessary config paths for tests
# This is crucial because utils.py and other modules might use them.
MOCK_BASE_DIR = Path(__file__).parent.parent # Simulates being in projects/spotify-cover-generator/
MOCK_LORA_DIR = MOCK_BASE_DIR / "loras"
MOCK_COVERS_DIR = MOCK_BASE_DIR / "generated_covers"

# It's often useful to have a dummy app for context if models need it
# from flask import Flask
# @pytest.fixture(scope="module")
# def test_app():
# app = Flask(__name__)
# app.config['TESTING'] = True
#     # Configure other necessary app settings if needed
#     # e.g., app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
# with app.app_context():
# yield app

# Placeholder for imports from the application, will be added as needed
from projects.spotify_cover_generator import spotify_client
# from spotify_cover_generator.app import User, db # If testing with real DB interactions (complex)

@mock.patch('projects.spotify_cover_generator.spotify_client.spotipy.Spotify')
class TestSpotifyClientUserSpecific:
    """Tests for user-specific Spotify client logic in spotify_client.py"""

    def test_get_user_specific_client_with_token(self, mock_spotify_constructor):
        """Test get_user_specific_client creates Spotipy instance with token."""
        dummy_token = "test_access_token"
        client = spotify_client.get_user_specific_client(dummy_token)

        mock_spotify_constructor.assert_called_once_with(auth=dummy_token)
        assert client == mock_spotify_constructor.return_value

    def test_get_user_specific_client_no_token(self, mock_spotify_constructor):
        """Test get_user_specific_client returns None if no token is provided."""
        client = spotify_client.get_user_specific_client(None)
        assert client is None
        mock_spotify_constructor.assert_not_called()

    def test_get_playlist_owner_id(self, mock_spotify_constructor):
        """Test get_playlist_owner_id calls sp_client.playlist()."""
        mock_sp_client = mock.MagicMock()
        mock_sp_client.playlist.return_value = {'owner': {'id': 'owner_test_id'}}
        playlist_id = "dummy_playlist_id"

        owner_id = spotify_client.get_playlist_owner_id(mock_sp_client, playlist_id)

        mock_sp_client.playlist.assert_called_once_with(playlist_id, fields="owner.id")
        assert owner_id == "owner_test_id"

    def test_get_playlist_owner_id_no_client(self, mock_spotify_constructor):
        """Test get_playlist_owner_id returns None if no client is provided."""
        owner_id = spotify_client.get_playlist_owner_id(None, "dummy_id")
        assert owner_id is None

    def test_update_playlist_details(self, mock_spotify_constructor):
        """Test update_playlist_details calls sp_client.playlist_change_details()."""
        mock_sp_client = mock.MagicMock()
        playlist_id = "dummy_playlist_id"
        new_name = "New Playlist Name"
        new_description = "New Description"

        result = spotify_client.update_playlist_details(mock_sp_client, playlist_id, name=new_name, description=new_description)

        mock_sp_client.playlist_change_details.assert_called_once_with(playlist_id, name=new_name, description=new_description)
        assert result is True

    def test_update_playlist_details_no_changes(self, mock_spotify_constructor):
        """Test update_playlist_details returns False if no name or description."""
        mock_sp_client = mock.MagicMock()
        result = spotify_client.update_playlist_details(mock_sp_client, "dummy_id", name=None, description=None)
        assert result is False
        mock_sp_client.playlist_change_details.assert_not_called()


    def test_update_playlist_details_no_client(self, mock_spotify_constructor):
        """Test update_playlist_details returns False if no client is provided."""
        result = spotify_client.update_playlist_details(None, "dummy_id", name="test")
        assert result is False

    @mock.patch('projects.spotify_cover_generator.spotify_client.base64')
    @mock.patch('builtins.open', new_callable=mock.mock_open, read_data=b'imagedata')
    def test_upload_custom_playlist_cover(self, mock_open_file, mock_base64, mock_spotify_constructor):
        """Test upload_custom_playlist_cover calls sp_client.playlist_upload_cover_image()."""
        mock_sp_client = mock.MagicMock()
        playlist_id = "dummy_playlist_id"
        image_path = "dummy/path/to/image.jpg"
        mock_base64.b64encode.return_value = b"encoded_image_data"

        result = spotify_client.upload_custom_playlist_cover(mock_sp_client, playlist_id, image_path)

        mock_open_file.assert_called_once_with(image_path, "rb")
        mock_base64.b64encode.assert_called_once_with(b"imagedata")
        mock_sp_client.playlist_upload_cover_image.assert_called_once_with(playlist_id, b"encoded_image_data")
        assert result is True

    def test_upload_custom_playlist_cover_file_not_found(self, mock_spotify_constructor):
        """Test upload_custom_playlist_cover returns False if file not found."""
        mock_sp_client = mock.MagicMock()
        with mock.patch('builtins.open', side_effect=FileNotFoundError):
            result = spotify_client.upload_custom_playlist_cover(mock_sp_client, "dummy_id", "bad/path.jpg")
            assert result is False
        mock_sp_client.playlist_upload_cover_image.assert_not_called()


    def test_upload_custom_playlist_cover_no_client(self, mock_spotify_constructor):
        """Test upload_custom_playlist_cover returns False if no client is provided."""
        result = spotify_client.upload_custom_playlist_cover(None, "dummy_id", "dummy/path.jpg")
        assert result is False


class TestAppPlaylistUpdateRoutes:
    """Tests for playlist update Flask routes in app.py"""

    def test_example_placeholder(self):
        assert True

# Need to import app and User, db for mocking. This can be complex.
# For now, we'll assume app can be imported and configured for testing.
# If direct import of 'app' from 'projects.spotify_cover_generator.app' causes issues
# (e.g., due to extensions not being initialized or expecting a specific context),
# an app factory pattern (`create_app`) in app.py would be more robust for testing.

from projects.spotify_cover_generator.app import app as flask_app, db as flask_db, User

@pytest.fixture
def client():
    flask_app.config['TESTING'] = True
    flask_app.config['WTF_CSRF_ENABLED'] = False # Disable CSRF for easier testing of POST requests
    # Use a temporary, in-memory SQLite database for tests if models are involved
    # flask_app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    # flask_db.create_all() # If using in-memory DB

    with flask_app.test_client() as client:
        with flask_app.app_context(): # Ensure app context for db operations if any
            yield client
    # flask_db.drop_all() # Clean up if using in-memory DB


@pytest.fixture
def mock_user_obj():
    user = mock.MagicMock(spec=User)
    user.id = 1
    user.spotify_access_token = "fake_access_token"
    user.spotify_id = "user_spotify_id"
    user.refresh_spotify_token_if_needed = mock.MagicMock()
    return user

@mock.patch('projects.spotify_cover_generator.app.db', new_callable=mock.MagicMock) # Mock db.session.commit
@mock.patch('projects.spotify_cover_generator.app.spotify_client') # Mock the whole module
@mock.patch('projects.spotify_cover_generator.app.get_current_user')
class TestAppPlaylistUpdateRoutes:
    """Tests for playlist update Flask routes in app.py"""

    def test_update_playlist_title_success(self, mock_get_current_user, mock_spotify_client_module, mock_db_session, client, mock_user_obj):
        mock_get_current_user.return_value = mock_user_obj

        mock_sp_user_client = mock.MagicMock()
        mock_sp_user_client.me.return_value = {'id': 'user_spotify_id'}
        mock_spotify_client_module.get_user_specific_client.return_value = mock_sp_user_client
        mock_spotify_client_module.get_playlist_owner_id.return_value = 'user_spotify_id'
        mock_spotify_client_module.update_playlist_details.return_value = True

        response = client.post('/spotify/api/update_playlist_title',
                               json={'playlist_id': 'pl123', 'new_title': 'New Title'})

        data = json.loads(response.data)
        assert response.status_code == 200
        assert data['success'] is True
        mock_user_obj.refresh_spotify_token_if_needed.assert_called_once()
        mock_db_session.session.commit.assert_called_once() # from app.py's db.session.commit()
        mock_spotify_client_module.get_user_specific_client.assert_called_once_with("fake_access_token")
        mock_sp_user_client.me.assert_called_once()
        mock_spotify_client_module.get_playlist_owner_id.assert_called_once_with(mock_sp_user_client, 'pl123')
        mock_spotify_client_module.update_playlist_details.assert_called_once_with(mock_sp_user_client, 'pl123', name='New Title')

    def test_update_playlist_title_not_owner(self, mock_get_current_user, mock_spotify_client_module, mock_db_session, client, mock_user_obj):
        mock_get_current_user.return_value = mock_user_obj
        mock_sp_user_client = mock.MagicMock()
        mock_sp_user_client.me.return_value = {'id': 'user_spotify_id'}
        mock_spotify_client_module.get_user_specific_client.return_value = mock_sp_user_client
        mock_spotify_client_module.get_playlist_owner_id.return_value = 'another_user_id' # Different owner

        response = client.post('/spotify/api/update_playlist_title',
                               json={'playlist_id': 'pl123', 'new_title': 'New Title'})

        data = json.loads(response.data)
        assert response.status_code == 403
        assert data['success'] is False
        assert data['error'] == "You do not own this playlist"

    def test_update_playlist_title_missing_data(self, mock_get_current_user, mock_spotify_client_module, mock_db_session, client, mock_user_obj):
        mock_get_current_user.return_value = mock_user_obj
        response = client.post('/spotify/api/update_playlist_title', json={'playlist_id': 'pl123'})
        assert response.status_code == 400
        response = client.post('/spotify/api/update_playlist_title', json={'new_title': 'New Title'})
        assert response.status_code == 400

    def test_update_playlist_title_not_authenticated(self, mock_get_current_user, mock_spotify_client_module, mock_db_session, client):
        mock_get_current_user.return_value = None # Simulate no user logged in
        response = client.post('/spotify/api/update_playlist_title',
                               json={'playlist_id': 'pl123', 'new_title': 'New Title'})
        # Expecting @login_required to redirect to login, or return 401 if it's an API
        # The current @login_required flashes and redirects. For an API, 401 is better.
        # For now, we test the jsonify part for non-interactive cases from @login_required
        # However, our @login_required redirects. Let's assume it gives 401 for API for now
        # This test might need adjustment based on actual @login_required behavior for XHR.
        # Given it's an API, let's assume it should return 401 if not caught by redirect.
        # The current implementation returns HTML for redirect.
        # A better API @login_required would return JSON error.
        # For this test, we will assume the User object check `if not user ... return jsonify` is hit.
        # This means we'd have to bypass the @login_required or make it test-friendly.
        # Let's assume for now that if get_current_user is None, it proceeds and hits the user check in route.
        # Actually, the route explicitly checks: `if not user or not user.spotify_access_token:`
        # So, if mock_get_current_user.return_value = None, this check handles it.
        data = json.loads(response.data)
        assert response.status_code == 401 # or the status code from redirect
        assert data['success'] is False
        assert data['error'] == "User not authenticated or Spotify not connected"


    @mock.patch('projects.spotify_cover_generator.app.os.path.exists')
    @mock.patch('projects.spotify_cover_generator.app.os.path.abspath')
    def test_update_playlist_cover_success(self, mock_abspath, mock_exists, mock_get_current_user, mock_spotify_client_module, mock_db_session, client, mock_user_obj):
        mock_get_current_user.return_value = mock_user_obj
        mock_exists.return_value = True # Image file exists

        # Mock abspath to return predictable paths
        # Assuming COVERS_DIR will be obtained via config inside the route correctly
        # For this mock, let's make it simple.
        # In a real scenario, you'd mock config.COVERS_DIR
        with mock.patch('projects.spotify_cover_generator.app.COVERS_DIR', MOCK_COVERS_DIR):
             mock_abspath.side_effect = lambda x: MOCK_COVERS_DIR / x if not os.path.isabs(x) else x


        mock_sp_user_client = mock.MagicMock()
        mock_sp_user_client.me.return_value = {'id': 'user_spotify_id'}
        mock_spotify_client_module.get_user_specific_client.return_value = mock_sp_user_client
        mock_spotify_client_module.get_playlist_owner_id.return_value = 'user_spotify_id'
        mock_spotify_client_module.upload_custom_playlist_cover.return_value = True

        image_server_path = str(MOCK_COVERS_DIR / "test_image.png")

        response = client.post('/spotify/api/update_playlist_cover',
                               json={'playlist_id': 'pl123', 'image_path': image_server_path})

        data = json.loads(response.data)
        assert response.status_code == 200
        assert data['success'] is True
        mock_spotify_client_module.upload_custom_playlist_cover.assert_called_once_with(mock_sp_user_client, 'pl123', image_server_path)

    @mock.patch('projects.spotify_cover_generator.app.os.path.exists', return_value=False)
    def test_update_playlist_cover_image_not_found(self, mock_exists, mock_get_current_user, mock_spotify_client_module, mock_db_session, client, mock_user_obj):
        mock_get_current_user.return_value = mock_user_obj
        with mock.patch('projects.spotify_cover_generator.app.COVERS_DIR', MOCK_COVERS_DIR):
            image_server_path = str(MOCK_COVERS_DIR / "test_image.png")
            response = client.post('/spotify/api/update_playlist_cover',
                                   json={'playlist_id': 'pl123', 'image_path': image_server_path})
        data = json.loads(response.data)
        assert response.status_code == 404
        assert data['error'] == "Image file not found on server"

    def test_update_playlist_cover_invalid_path(self, mock_get_current_user, mock_spotify_client_module, mock_db_session, client, mock_user_obj):
        mock_get_current_user.return_value = mock_user_obj
        with mock.patch('projects.spotify_cover_generator.app.COVERS_DIR', MOCK_COVERS_DIR):
            # Path outside of COVERS_DIR
            image_server_path = str(MOCK_BASE_DIR / "outside_image.png")
            response = client.post('/spotify/api/update_playlist_cover',
                                   json={'playlist_id': 'pl123', 'image_path': image_server_path})
        data = json.loads(response.data)
        assert response.status_code == 400
        assert data['error'] == "Invalid image path"


class TestLoraUtils:
    """Tests for LoRA loading utilities in utils.py"""

    def test_example_placeholder(self):
        assert True

from projects.spotify_cover_generator import utils
from projects.spotify_cover_generator.models import LoraModel
# Assuming LoraModelDB is part of app.py for now, for mocking its query.all()
# If LoraModelDB moves to models.py, this import might change.
# from projects.spotify_cover_generator.app import LoraModelDB

# Mock the LORA_DIR used in utils.py
@mock.patch('projects.spotify_cover_generator.utils.LORA_DIR', MOCK_LORA_DIR)
class TestLoraUtils:
    """Tests for LoRA loading utilities in utils.py"""

    @mock.patch('projects.spotify_cover_generator.utils.Path.exists')
    @mock.patch('builtins.open', new_callable=mock.mock_open)
    @mock.patch('projects.spotify_cover_generator.utils.json.load')
    @mock.patch('projects.spotify_cover_generator.utils.LORA_DIR.glob')
    @mock.patch('projects.spotify_cover_generator.utils.os.path.exists')
    @mock.patch('projects.spotify_cover_generator.utils.app') # Mocking 'app' for app_context
    def test_get_available_loras_config_only(self, mock_app_for_context, mock_os_path_exists, mock_glob, mock_json_load, mock_open, mock_path_exists):
        mock_path_exists.return_value = True # lora_config.json exists
        mock_json_load.return_value = {
            "loras": [
                {"name": "ConfigLoRA1", "source_type": "link", "url": "http://example.com/lora1", "trigger_words": ["cfg1"], "strength": 0.8}
            ]
        }
        mock_glob.return_value = [] # No filesystem LoRAs

        # Mock DB query
        with mock.patch('projects.spotify_cover_generator.utils.LoraModelDB.query') as mock_query:
            mock_query.all.return_value = [] # No DB LoRAs

            loras = utils.get_available_loras()

        assert len(loras) == 1
        assert loras[0].name == "ConfigLoRA1"
        assert loras[0].source_type == "link"
        assert loras[0].url == "http://example.com/lora1"
        assert loras[0].trigger_words == ["cfg1"]
        assert loras[0].strength == 0.8

    @mock.patch('projects.spotify_cover_generator.utils.Path.exists') # For lora_config.json
    @mock.patch('projects.spotify_cover_generator.utils.LORA_DIR.glob')
    @mock.patch('projects.spotify_cover_generator.utils.os.path.exists') # For local files from DB check
    @mock.patch('projects.spotify_cover_generator.utils.app')
    def test_get_available_loras_filesystem_only(self, mock_app_for_context, mock_os_path_exists_db, mock_glob, mock_config_exists):
        mock_config_exists.return_value = False # No lora_config.json

        mock_lora_file1_path = mock.MagicMock(spec=Path)
        mock_lora_file1_path.stem = "FileSystemLoRA1"
        mock_lora_file1_path.__str__ = mock.MagicMock(return_value=str(MOCK_LORA_DIR / "FileSystemLoRA1.safetensors"))
        mock_glob.return_value = [mock_lora_file1_path] # One filesystem LoRA

        # Mock DB query
        with mock.patch('projects.spotify_cover_generator.utils.LoraModelDB.query') as mock_query:
            mock_query.all.return_value = []

            loras = utils.get_available_loras()

        assert len(loras) == 1
        assert loras[0].name == "FileSystemLoRA1"
        assert loras[0].source_type == "local"
        assert loras[0].path == str(MOCK_LORA_DIR / "FileSystemLoRA1.safetensors")

    @mock.patch('projects.spotify_cover_generator.utils.Path.exists') # For lora_config.json
    @mock.patch('projects.spotify_cover_generator.utils.LORA_DIR.glob')
    @mock.patch('projects.spotify_cover_generator.utils.os.path.exists')
    @mock.patch('projects.spotify_cover_generator.utils.app')
    def test_get_available_loras_db_only(self, mock_app_for_context, mock_os_path_exists, mock_glob, mock_config_exists):
        mock_config_exists.return_value = False # No lora_config.json
        mock_glob.return_value = [] # No filesystem LoRAs

        mock_db_lora1 = mock.MagicMock()
        mock_db_lora1.name = "DbLoRA1"
        mock_db_lora1.source_type = "local"
        mock_db_lora1.path = str(MOCK_LORA_DIR / "DbLoRA1.safetensors")

        mock_os_path_exists.return_value = True # DB LoRA file exists

        with mock.patch('projects.spotify_cover_generator.utils.LoraModelDB.query') as mock_query:
            mock_query.all.return_value = [mock_db_lora1]
            loras = utils.get_available_loras()

        assert len(loras) == 1
        assert loras[0].name == "DbLoRA1"
        assert loras[0].source_type == "local"
        assert loras[0].path == str(MOCK_LORA_DIR / "DbLoRA1.safetensors")

    @mock.patch('projects.spotify_cover_generator.utils.Path.exists') # config path exists
    @mock.patch('builtins.open', new_callable=mock.mock_open)
    @mock.patch('projects.spotify_cover_generator.utils.json.load')
    @mock.patch('projects.spotify_cover_generator.utils.LORA_DIR.glob')
    @mock.patch('projects.spotify_cover_generator.utils.os.path.exists') # for DB file checks
    @mock.patch('projects.spotify_cover_generator.utils.app')
    def test_get_available_loras_precedence(self, mock_app_for_context, mock_os_path_exists_db, mock_glob, mock_json_load, mock_open, mock_config_path_exists):
        # Config LoRA (should take precedence)
        mock_config_path_exists.return_value = True
        mock_json_load.return_value = {
            "loras": [
                {"name": "SharedLoRA", "source_type": "link", "url": "http://config.com/shared", "strength": 0.9}
            ]
        }

        # Filesystem LoRA (same name as config, different type - config should still win due to earlier loading)
        # Actually, current logic: if name matches, config wins. If config is link and FS is local, path from FS might be added if types match.
        # Let's test with distinct names first for clarity of loading, then override.
        mock_fs_lora_path = mock.MagicMock(spec=Path); mock_fs_lora_path.stem = "FileSystemUnique"; mock_fs_lora_path.__str__ = mock.MagicMock(return_value=str(MOCK_LORA_DIR / "FileSystemUnique.safetensors"))
        mock_glob.return_value = [mock_fs_lora_path]

        # DB LoRA (local, file exists, unique name)
        mock_db_lora_local = mock.MagicMock(); mock_db_lora_local.name = "DBLocalUnique"; mock_db_lora_local.source_type = "local"; mock_db_lora_local.path = str(MOCK_LORA_DIR / "DBLocalUnique.safetensors")
        # DB LoRA (link type, unique name)
        mock_db_lora_link = mock.MagicMock(); mock_db_lora_link.name = "DBLinkUnique"; mock_db_lora_link.source_type = "link"; mock_db_lora_link.path = "" # path is empty for link from DB

        mock_os_path_exists_db.return_value = True # Assume local DB LoRA files exist

        with mock.patch('projects.spotify_cover_generator.utils.LoraModelDB.query') as mock_query:
            mock_query.all.return_value = [mock_db_lora_local, mock_db_lora_link]
            loras = utils.get_available_loras()

        assert len(loras) == 4
        lora_names = [l.name for l in loras]
        assert "SharedLoRA" in lora_names
        assert "FileSystemUnique" in lora_names
        assert "DBLocalUnique" in lora_names
        assert "DBLinkUnique" in lora_names

        shared_lora = next(l for l in loras if l.name == "SharedLoRA")
        assert shared_lora.source_type == "link"
        assert shared_lora.strength == 0.9 # From config

    @mock.patch('projects.spotify_cover_generator.utils.Path.exists') # config path exists
    @mock.patch('projects.spotify_cover_generator.utils.LORA_DIR.glob')
    @mock.patch('projects.spotify_cover_generator.utils.os.path.exists') # for DB file checks
    @mock.patch('projects.spotify_cover_generator.utils.app')
    def test_get_available_loras_db_local_file_missing(self, mock_app_for_context, mock_os_path_exists_db, mock_glob, mock_config_path_exists):
        mock_config_path_exists.return_value = False # No config
        mock_glob.return_value = [] # No filesystem

        mock_db_lora_missing = mock.MagicMock()
        mock_db_lora_missing.name = "DBLocalMissing"
        mock_db_lora_missing.source_type = "local"
        mock_db_lora_missing.path = str(MOCK_LORA_DIR / "DBLocalMissing.safetensors")

        mock_os_path_exists_db.return_value = False # File for this DB entry does NOT exist

        with mock.patch('projects.spotify_cover_generator.utils.LoraModelDB.query') as mock_query:
            mock_query.all.return_value = [mock_db_lora_missing]
            loras = utils.get_available_loras()

        assert len(loras) == 0 # Should not be loaded

# More specific test classes or functions will be added below.
