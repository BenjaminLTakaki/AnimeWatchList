"""
AnimeWatchList - Flask Backend
MAL OAuth2 + Public API support
"""

import os
import secrets
import hashlib
import base64
import requests
import datetime
from flask import Flask, redirect, request, jsonify, session, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from functools import wraps

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))
CORS(app, supports_credentials=True, origins=["http://localhost:5173", os.environ.get("FRONTEND_URL", "")])

# ── Database ──────────────────────────────────────────────────────────────────
db_url = os.environ.get("DATABASE_URL", "sqlite:///animewatchlist.db")
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

# ── MAL Config ────────────────────────────────────────────────────────────────
MAL_CLIENT_ID     = os.environ.get("MAL_CLIENT_ID", "")
MAL_CLIENT_SECRET = os.environ.get("MAL_CLIENT_SECRET", "")
MAL_REDIRECT_URI  = os.environ.get("MAL_REDIRECT_URI", "http://localhost:5000/auth/mal/callback")
MAL_API_BASE      = "https://api.myanimelist.net/v2"
MAL_AUTH_BASE     = "https://myanimelist.net/v1/oauth2"

# ── Models ────────────────────────────────────────────────────────────────────
class User(db.Model):
    __tablename__ = "user"
    id             = db.Column(db.Integer, primary_key=True)
    username       = db.Column(db.String(64), unique=True, nullable=False)
    email          = db.Column(db.String(120), unique=True, nullable=True)
    password_hash  = db.Column(db.String(256), nullable=True)
    mal_user_id    = db.Column(db.Integer, unique=True, nullable=True)
    mal_username   = db.Column(db.String(64), nullable=True)
    mal_access_token   = db.Column(db.Text, nullable=True)
    mal_refresh_token  = db.Column(db.Text, nullable=True)
    mal_token_expires  = db.Column(db.DateTime, nullable=True)
    created_at     = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "mal_username": self.mal_username,
            "mal_linked": self.mal_access_token is not None,
            "created_at": self.created_at.isoformat(),
        }


class Anime(db.Model):
    __tablename__ = "anime"
    id          = db.Column(db.Integer, primary_key=True)
    mal_id      = db.Column(db.Integer, unique=True, nullable=False, index=True)
    title       = db.Column(db.String(512), nullable=False)
    title_en    = db.Column(db.String(512), nullable=True)
    image_url   = db.Column(db.String(512), nullable=True)
    episodes    = db.Column(db.Integer, nullable=True)
    score       = db.Column(db.Float, nullable=True)
    media_type  = db.Column(db.String(32), nullable=True)
    status      = db.Column(db.String(64), nullable=True)
    genres      = db.Column(db.Text, nullable=True)   # comma-separated
    studios     = db.Column(db.Text, nullable=True)
    synopsis    = db.Column(db.Text, nullable=True)
    year        = db.Column(db.Integer, nullable=True)
    season      = db.Column(db.String(16), nullable=True)
    popularity  = db.Column(db.Integer, nullable=True)
    rank        = db.Column(db.Integer, nullable=True)
    updated_at  = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    def to_dict(self):
        return {
            "mal_id":     self.mal_id,
            "title":      self.title,
            "title_en":   self.title_en,
            "image_url":  self.image_url,
            "episodes":   self.episodes,
            "score":      self.score,
            "media_type": self.media_type,
            "status":     self.status,
            "genres":     self.genres.split(",") if self.genres else [],
            "studios":    self.studios.split(",") if self.studios else [],
            "synopsis":   self.synopsis,
            "year":       self.year,
            "season":     self.season,
            "popularity": self.popularity,
            "rank":       self.rank,
        }


class UserAnimeList(db.Model):
    __tablename__ = "user_anime_list"
    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    anime_id    = db.Column(db.Integer, db.ForeignKey("anime.id"), nullable=False)
    watch_status = db.Column(db.String(32), default="watching")  # watching/completed/dropped/plan_to_watch
    user_rating = db.Column(db.Integer, nullable=True)           # 1-10
    episodes_watched = db.Column(db.Integer, default=0)
    added_at    = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at  = db.Column(db.DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    anime = db.relationship("Anime", backref="user_entries")
    user  = db.relationship("User",  backref="anime_list")

    __table_args__ = (db.UniqueConstraint("user_id", "anime_id", name="uq_user_anime"),)

    def to_dict(self):
        return {
            **self.anime.to_dict(),
            "watch_status":      self.watch_status,
            "user_rating":       self.user_rating,
            "episodes_watched":  self.episodes_watched,
            "added_at":          self.added_at.isoformat(),
        }


with app.app_context():
    db.create_all()


# ── Helpers ───────────────────────────────────────────────────────────────────
def mal_headers_public():
    return {"X-MAL-CLIENT-ID": MAL_CLIENT_ID}


def mal_headers_user(user: User):
    """Return bearer headers; refresh token if expired."""
    if user.mal_token_expires and datetime.datetime.utcnow() > user.mal_token_expires:
        _refresh_mal_token(user)
    return {"Authorization": f"Bearer {user.mal_access_token}"}


def _refresh_mal_token(user: User):
    resp = requests.post(f"{MAL_AUTH_BASE}/token", data={
        "grant_type":    "refresh_token",
        "refresh_token": user.mal_refresh_token,
        "client_id":     MAL_CLIENT_ID,
        "client_secret": MAL_CLIENT_SECRET,
    })
    if resp.ok:
        data = resp.json()
        user.mal_access_token  = data["access_token"]
        user.mal_refresh_token = data.get("refresh_token", user.mal_refresh_token)
        user.mal_token_expires = datetime.datetime.utcnow() + datetime.timedelta(seconds=data["expires_in"])
        db.session.commit()


def _upsert_anime(data: dict) -> Anime:
    """Insert or update anime from MAL API response dict."""
    mal_id = data.get("id") or data.get("mal_id")
    anime  = Anime.query.filter_by(mal_id=mal_id).first()
    if not anime:
        anime = Anime(mal_id=mal_id)
        db.session.add(anime)

    alts = data.get("alternative_titles", {})
    anime.title      = data.get("title", "Unknown")
    anime.title_en   = alts.get("en") or data.get("title_en")
    anime.image_url  = (data.get("main_picture") or {}).get("large") or (data.get("main_picture") or {}).get("medium")
    anime.episodes   = data.get("num_episodes") or data.get("episodes")
    anime.score      = data.get("mean") or data.get("score")
    anime.media_type = data.get("media_type")
    anime.status     = data.get("status")
    anime.synopsis   = data.get("synopsis")
    anime.popularity = data.get("popularity")
    anime.rank       = data.get("rank")
    ss = data.get("start_season") or {}
    anime.year   = ss.get("year")
    anime.season = ss.get("season")
    anime.genres  = ",".join(g["name"] for g in data.get("genres",  []) if isinstance(g, dict))
    anime.studios = ",".join(s["name"] for s in data.get("studios", []) if isinstance(s, dict))
    anime.updated_at = datetime.datetime.utcnow()
    db.session.commit()
    return anime


def require_auth(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Unauthorized"}), 401
        user = User.query.get(user_id)
        if not user:
            return jsonify({"error": "Unauthorized"}), 401
        return f(user, *args, **kwargs)
    return wrapper


# ── Auth Routes ───────────────────────────────────────────────────────────────
@app.post("/auth/register")
def register():
    body = request.json or {}
    username = body.get("username", "").strip()
    email    = body.get("email", "").strip()
    password = body.get("password", "")
    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({"error": "Username taken"}), 409
    user = User(username=username, email=email or None)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    session["user_id"] = user.id
    return jsonify(user.to_dict()), 201


@app.post("/auth/login")
def login():
    body = request.json or {}
    username = body.get("username", "").strip()
    password = body.get("password", "")
    user = User.query.filter_by(username=username).first()
    if not user or not user.check_password(password):
        return jsonify({"error": "Invalid credentials"}), 401
    session["user_id"] = user.id
    return jsonify(user.to_dict())


@app.post("/auth/logout")
def logout():
    session.clear()
    return jsonify({"ok": True})


@app.get("/auth/me")
def me():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify(None)
    user = User.query.get(user_id)
    return jsonify(user.to_dict() if user else None)


# ── MAL OAuth ─────────────────────────────────────────────────────────────────
def _pkce_pair():
    verifier  = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    return verifier, challenge


@app.get("/auth/mal/authorize")
def mal_authorize():
    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(16)
    session["mal_pkce_verifier"] = verifier
    session["mal_state"]         = state
    params = (
        f"response_type=code"
        f"&client_id={MAL_CLIENT_ID}"
        f"&redirect_uri={MAL_REDIRECT_URI}"
        f"&state={state}"
        f"&code_challenge={challenge}"
        f"&code_challenge_method=plain"
    )
    return redirect(f"{MAL_AUTH_BASE}/authorize?{params}")


@app.get("/auth/mal/callback")
def mal_callback():
    code      = request.args.get("code")
    state     = request.args.get("state")
    if state != session.pop("mal_state", None):
        return jsonify({"error": "State mismatch"}), 400

    verifier = session.pop("mal_pkce_verifier", "")
    resp = requests.post(f"{MAL_AUTH_BASE}/token", data={
        "client_id":     MAL_CLIENT_ID,
        "client_secret": MAL_CLIENT_SECRET,
        "code":          code,
        "code_verifier": verifier,
        "grant_type":    "authorization_code",
        "redirect_uri":  MAL_REDIRECT_URI,
    })
    if not resp.ok:
        return jsonify({"error": "Token exchange failed", "detail": resp.text}), 400

    tokens = resp.json()
    access  = tokens["access_token"]
    refresh = tokens.get("refresh_token")
    expires = datetime.datetime.utcnow() + datetime.timedelta(seconds=tokens["expires_in"])

    # fetch MAL user info
    mal_user_resp = requests.get(f"{MAL_API_BASE}/users/@me", headers={"Authorization": f"Bearer {access}"})
    mal_info = mal_user_resp.json() if mal_user_resp.ok else {}
    mal_user_id  = mal_info.get("id")
    mal_username = mal_info.get("name")

    # link to existing session user or find by mal_id or create new user
    user_id = session.get("user_id")
    user = User.query.get(user_id) if user_id else None
    if not user:
        user = User.query.filter_by(mal_user_id=mal_user_id).first()
    if not user:
        user = User(username=mal_username or f"mal_{mal_user_id}", mal_user_id=mal_user_id)
        db.session.add(user)

    user.mal_user_id       = mal_user_id
    user.mal_username      = mal_username
    user.mal_access_token  = access
    user.mal_refresh_token = refresh
    user.mal_token_expires = expires
    db.session.commit()
    session["user_id"] = user.id

    frontend = os.environ.get("FRONTEND_URL", "http://localhost:5173")
    return redirect(f"{frontend}/profile?mal_linked=1")


@app.delete("/auth/mal/unlink")
@require_auth
def mal_unlink(user):
    user.mal_access_token  = None
    user.mal_refresh_token = None
    user.mal_token_expires = None
    user.mal_user_id       = None
    user.mal_username      = None
    db.session.commit()
    return jsonify(user.to_dict())


# ── MAL API Proxy ─────────────────────────────────────────────────────────────
ANIME_FIELDS = (
    "id,title,alternative_titles,main_picture,mean,rank,popularity,"
    "num_episodes,media_type,status,genres,studios,synopsis,start_season,"
    "broadcast,source,average_episode_duration,rating,pictures,background,"
    "related_anime,recommendations"
)


@app.get("/api/anime/<int:mal_id>")
def get_anime(mal_id):
    resp = requests.get(
        f"{MAL_API_BASE}/anime/{mal_id}",
        headers=mal_headers_public(),
        params={"fields": ANIME_FIELDS},
    )
    if not resp.ok:
        return jsonify({"error": "Not found"}), 404
    anime = _upsert_anime(resp.json())
    return jsonify(anime.to_dict())


@app.get("/api/anime/search")
def search_anime():
    q     = request.args.get("q", "")
    limit = min(int(request.args.get("limit", 20)), 100)
    if not q:
        return jsonify([])
    resp = requests.get(
        f"{MAL_API_BASE}/anime",
        headers=mal_headers_public(),
        params={"q": q, "limit": limit, "fields": ANIME_FIELDS},
    )
    if not resp.ok:
        return jsonify([])
    results = []
    for item in resp.json().get("data", []):
        anime = _upsert_anime(item["node"])
        results.append(anime.to_dict())
    return jsonify(results)


@app.get("/api/anime/ranking")
def get_ranking():
    ranking_type = request.args.get("ranking_type", "all")
    limit  = min(int(request.args.get("limit", 20)), 100)
    offset = int(request.args.get("offset", 0))
    resp = requests.get(
        f"{MAL_API_BASE}/anime/ranking",
        headers=mal_headers_public(),
        params={"ranking_type": ranking_type, "limit": limit, "offset": offset, "fields": ANIME_FIELDS},
    )
    if not resp.ok:
        return jsonify([])
    results = []
    for item in resp.json().get("data", []):
        anime = _upsert_anime(item["node"])
        results.append(anime.to_dict())
    return jsonify(results)


@app.get("/api/anime/seasonal")
def get_seasonal():
    year   = request.args.get("year",   datetime.datetime.now().year)
    season = request.args.get("season", _current_season())
    limit  = min(int(request.args.get("limit", 20)), 100)
    resp = requests.get(
        f"{MAL_API_BASE}/anime/season/{year}/{season}",
        headers=mal_headers_public(),
        params={"limit": limit, "fields": ANIME_FIELDS, "sort": "anime_score"},
    )
    if not resp.ok:
        return jsonify([])
    results = []
    for item in resp.json().get("data", []):
        anime = _upsert_anime(item["node"])
        results.append(anime.to_dict())
    return jsonify(results)


def _current_season():
    m = datetime.datetime.now().month
    if m in [12, 1, 2]:  return "winter"
    if m in [3, 4, 5]:   return "spring"
    if m in [6, 7, 8]:   return "summer"
    return "fall"


# ── User List Routes ──────────────────────────────────────────────────────────
@app.get("/api/list")
@require_auth
def get_list(user):
    status = request.args.get("status")
    query  = UserAnimeList.query.filter_by(user_id=user.id)
    if status:
        query = query.filter_by(watch_status=status)
    entries = query.order_by(UserAnimeList.updated_at.desc()).all()
    return jsonify([e.to_dict() for e in entries])


@app.post("/api/list")
@require_auth
def add_to_list(user):
    body     = request.json or {}
    mal_id   = body.get("mal_id")
    status   = body.get("watch_status", "plan_to_watch")
    rating   = body.get("user_rating")
    eps      = body.get("episodes_watched", 0)
    if not mal_id:
        return jsonify({"error": "mal_id required"}), 400

    # fetch from MAL if not in DB
    anime = Anime.query.filter_by(mal_id=mal_id).first()
    if not anime:
        resp = requests.get(
            f"{MAL_API_BASE}/anime/{mal_id}",
            headers=mal_headers_public(),
            params={"fields": ANIME_FIELDS},
        )
        if resp.ok:
            anime = _upsert_anime(resp.json())
        else:
            return jsonify({"error": "Anime not found on MAL"}), 404

    entry = UserAnimeList.query.filter_by(user_id=user.id, anime_id=anime.id).first()
    if not entry:
        entry = UserAnimeList(user_id=user.id, anime_id=anime.id)
        db.session.add(entry)

    entry.watch_status      = status
    entry.user_rating       = rating
    entry.episodes_watched  = eps
    entry.updated_at        = datetime.datetime.utcnow()
    db.session.commit()
    return jsonify(entry.to_dict()), 201


@app.patch("/api/list/<int:mal_id>")
@require_auth
def update_list_entry(user, mal_id):
    anime = Anime.query.filter_by(mal_id=mal_id).first()
    if not anime:
        return jsonify({"error": "Not found"}), 404
    entry = UserAnimeList.query.filter_by(user_id=user.id, anime_id=anime.id).first()
    if not entry:
        return jsonify({"error": "Not in list"}), 404

    body = request.json or {}
    if "watch_status"      in body: entry.watch_status      = body["watch_status"]
    if "user_rating"       in body: entry.user_rating       = body["user_rating"]
    if "episodes_watched"  in body: entry.episodes_watched  = body["episodes_watched"]
    entry.updated_at = datetime.datetime.utcnow()
    db.session.commit()
    return jsonify(entry.to_dict())


@app.delete("/api/list/<int:mal_id>")
@require_auth
def remove_from_list(user, mal_id):
    anime = Anime.query.filter_by(mal_id=mal_id).first()
    if not anime:
        return jsonify({"error": "Not found"}), 404
    entry = UserAnimeList.query.filter_by(user_id=user.id, anime_id=anime.id).first()
    if entry:
        db.session.delete(entry)
        db.session.commit()
    return jsonify({"ok": True})


# ── Stats Route ───────────────────────────────────────────────────────────────
@app.get("/api/stats")
@require_auth
def get_stats(user):
    entries = UserAnimeList.query.filter_by(user_id=user.id).all()
    if not entries:
        return jsonify({"total": 0, "completed": 0, "watching": 0, "plan_to_watch": 0,
                        "dropped": 0, "total_episodes": 0, "mean_score": 0,
                        "genres": {}, "top_rated": []})

    completed   = [e for e in entries if e.watch_status == "completed"]
    watching    = [e for e in entries if e.watch_status == "watching"]
    ptw         = [e for e in entries if e.watch_status == "plan_to_watch"]
    dropped     = [e for e in entries if e.watch_status == "dropped"]
    rated       = [e for e in entries if e.user_rating]
    total_eps   = sum((e.anime.episodes or 0) for e in completed)
    mean_score  = round(sum(e.user_rating for e in rated) / len(rated), 2) if rated else 0

    genre_count = {}
    for e in entries:
        for g in (e.anime.genres or "").split(","):
            g = g.strip()
            if g: genre_count[g] = genre_count.get(g, 0) + 1

    top_rated = sorted(rated, key=lambda e: e.user_rating, reverse=True)[:5]

    return jsonify({
        "total":          len(entries),
        "completed":      len(completed),
        "watching":       len(watching),
        "plan_to_watch":  len(ptw),
        "dropped":        len(dropped),
        "total_episodes": total_eps,
        "mean_score":     mean_score,
        "genres":         genre_count,
        "top_rated":      [e.to_dict() for e in top_rated],
    })


# ── MAL Sync Route ────────────────────────────────────────────────────────────
@app.post("/api/mal/sync")
@require_auth
def mal_sync(user):
    """Sync user's MAL list into local DB."""
    if not user.mal_access_token:
        return jsonify({"error": "MAL not linked"}), 400

    synced = 0
    offset = 0
    fields = "list_status,num_episodes,mean,genres,studios,main_picture,alternative_titles,start_season"

    while True:
        resp = requests.get(
            f"{MAL_API_BASE}/users/@me/animelist",
            headers=mal_headers_user(user),
            params={"fields": fields, "limit": 100, "offset": offset, "nsfw": True},
        )
        if not resp.ok:
            break
        data = resp.json()
        for item in data.get("data", []):
            node       = item["node"]
            ls         = item.get("list_status", {})
            anime      = _upsert_anime(node)
            entry      = UserAnimeList.query.filter_by(user_id=user.id, anime_id=anime.id).first()
            if not entry:
                entry  = UserAnimeList(user_id=user.id, anime_id=anime.id)
                db.session.add(entry)

            status_map = {"watching": "watching", "completed": "completed",
                          "on_hold": "watching", "dropped": "dropped",
                          "plan_to_watch": "plan_to_watch"}
            entry.watch_status     = status_map.get(ls.get("status", "plan_to_watch"), "plan_to_watch")
            entry.user_rating      = ls.get("score") or None
            entry.episodes_watched = ls.get("num_episodes_watched", 0)
            synced += 1

        if not data.get("paging", {}).get("next"):
            break
        offset += 100

    db.session.commit()
    return jsonify({"synced": synced})


# ── Recommendations Route ─────────────────────────────────────────────────────
@app.get("/api/recommendations")
@require_auth
def get_recommendations(user):
    completed = UserAnimeList.query.filter_by(
        user_id=user.id, watch_status="completed"
    ).order_by(UserAnimeList.user_rating.desc().nullslast()).limit(10).all()

    if not completed:
        # Fallback: top seasonal
        resp = requests.get(
            f"{MAL_API_BASE}/anime/ranking",
            headers=mal_headers_public(),
            params={"ranking_type": "all", "limit": 20, "fields": ANIME_FIELDS},
        )
        if resp.ok:
            results = [_upsert_anime(i["node"]).to_dict() for i in resp.json().get("data", [])]
            return jsonify(results)
        return jsonify([])

    # collect related anime from MAL for top 5 highest rated
    watched_ids = {e.anime.mal_id for e in UserAnimeList.query.filter_by(user_id=user.id).all()}
    recs = {}

    for entry in completed[:5]:
        resp = requests.get(
            f"{MAL_API_BASE}/anime/{entry.anime.mal_id}",
            headers=mal_headers_public(),
            params={"fields": "recommendations,related_anime"},
        )
        if not resp.ok:
            continue
        data = resp.json()
        for r in data.get("recommendations", [])[:5]:
            node = r.get("node", {})
            mid  = node.get("id")
            if mid and mid not in watched_ids:
                recs[mid] = node

    results = []
    for mid, node in list(recs.items())[:20]:
        full = requests.get(
            f"{MAL_API_BASE}/anime/{mid}",
            headers=mal_headers_public(),
            params={"fields": ANIME_FIELDS},
        )
        if full.ok:
            anime = _upsert_anime(full.json())
            results.append(anime.to_dict())

    return jsonify(results)


if __name__ == "__main__":
    app.run(debug=True, port=5000)

# ── Frontend SPA ──────────────────────────────────────────────────────────────
# Serves the bundled React app for all non-API/auth routes.
# Place animewatchlist.html in projects/animewatchlist/templates/
from flask import render_template as _render_template

@app.route("/ui")
@app.route("/ui/<path:frontend_path>")
def spa(frontend_path=None):
    return _render_template("animewatchlist.html")
