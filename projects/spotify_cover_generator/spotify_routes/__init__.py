from flask import Blueprint
bp = Blueprint('spotify_routes', __name__, template_folder='../templates')
from spotify_routes import routes
