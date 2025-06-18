import pytest
from flask import url_for, session

def test_profile_access_unauthenticated(client, app):
    """Test accessing /profile without being logged in."""
    # Need app_context for url_for to work if SERVER_NAME is not set or app not running
    with app.app_context():
        profile_url = url_for('auth.profile')
        # Assuming login route is 'auth.login' based on blueprint structure
        login_url = url_for('auth.login', _external=False) # Use _external=False for path only

    response = client.get(profile_url)
    assert response.status_code == 302 # Should redirect
    # The redirect location check needs to be careful about scheme and host
    # For instance, response.headers['Location'] might be 'http://localhost/login?next=%2Fprofile'
    # url_for('auth.login', next=profile_url, _external=False) should generate the expected path part
    with app.app_context(): # url_for needs context
        expected_redirect_path = url_for('auth.login', next=profile_url, _external=False)

    # Normalize paths for comparison if needed, or check for path components
    # response.headers['Location'] will be a full URL if SERVER_NAME is set.
    # A simpler check might be for the presence of login_url path and next parameter.
    assert login_url in response.headers['Location']
    assert profile_url in response.headers['Location']


def test_login_and_profile_access(client, app, create_test_user, new_user_data, db):
    """Test logging in and then accessing /profile."""
    test_user = create_test_user # User is created and in db

    with app.app_context():
        login_url = url_for('auth.login')
        profile_url = url_for('auth.profile')

    # Simulate login
    response = client.post(login_url, data={
        'username': new_user_data['username'],
        'password': new_user_data['password']
    }, follow_redirects=True)

    assert response.status_code == 200

    with client.session_transaction() as sess:
        assert 'user_id' in sess
        assert sess['user_id'] == test_user.id

    response = client.get(profile_url)
    assert response.status_code == 200
    assert b"User Profile" in response.data
    assert bytes(test_user.username, 'utf-8') in response.data

def test_admin_route_unauthorized_access(client, app, create_test_user, new_user_data, db):
    """Test a non-admin user trying to access the dummy admin route."""
    test_user = create_test_user
    with app.app_context():
        login_url = url_for('auth.login')
        # Assuming the dummy admin route is '/admin-only-test' within the 'auth' blueprint
        admin_test_url = url_for('auth.admin_only_page')

    client.post(login_url, data={
        'username': new_user_data['username'],
        'password': new_user_data['password']
    })

    response = client.get(admin_test_url)
    assert response.status_code == 403 # Expecting Forbidden due to @admin_required

def test_admin_route_authorized_access(client, app, create_admin_user, db):
    """Test an admin user accessing the dummy admin route."""
    admin_user = create_admin_user

    with app.app_context():
        login_url = url_for('auth.login')
        admin_test_url = url_for('auth.admin_only_page')

    client.post(login_url, data={
        'username': admin_user.username,
        'password': 'adminpassword'
    }, follow_redirects=True)

    response = client.get(admin_test_url)
    assert response.status_code == 200
    assert b"Admin Page Content" in response.data
