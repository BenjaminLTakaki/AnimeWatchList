"""
AnimeWatchList — Flask app (Jinja2 templates, MAL API, MAL OAuth)
Drop this into projects/animewatchlist/ and register with wsgi.py.
"""
import os, secrets, hashlib, base64, datetime, requests
from flask import (Flask, render_template, redirect, request,
                   session, flash, url_for, Blueprint)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (LoginManager, UserMixin, login_user,
                         logout_user, login_required, current_user)
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

load_dotenv()

# ── App & blueprint ────────────────────────────────────────────────────────
bp = Blueprint(
    "animewatchlist", __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/animewatchlist/static",
)

db    = SQLAlchemy()
login = LoginManager()

MAL_CLIENT_ID     = os.environ.get("MAL_CLIENT_ID", "")
MAL_CLIENT_SECRET = os.environ.get("MAL_CLIENT_SECRET", "")
MAL_REDIRECT_URI  = os.environ.get("MAL_REDIRECT_URI", "http://localhost:5000/animewatchlist/auth/mal/callback")
MAL_API_BASE      = "https://api.myanimelist.net/v2"
MAL_AUTH_BASE     = "https://myanimelist.net/v1/oauth2"

ANIME_FIELDS = (
    "id,title,alternative_titles,main_picture,mean,rank,popularity,"
    "num_episodes,media_type,status,genres,studios,synopsis,start_season"
)


# ── Models ─────────────────────────────────────────────────────────────────
class User(UserMixin, db.Model):
    __tablename__ = "aw_user"
    id             = db.Column(db.Integer, primary_key=True)
    username       = db.Column(db.String(64), unique=True, nullable=False)
    email          = db.Column(db.String(120), unique=True, nullable=True)
    password_hash  = db.Column(db.String(256), nullable=True)
    mal_user_id    = db.Column(db.Integer, unique=True, nullable=True)
    mal_username   = db.Column(db.String(64), nullable=True)
    mal_access_token  = db.Column(db.Text, nullable=True)
    mal_refresh_token = db.Column(db.Text, nullable=True)
    mal_token_expires = db.Column(db.DateTime, nullable=True)
    created_at     = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    @property
    def mal_linked(self):
        return self.mal_access_token is not None

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)


class Anime(db.Model):
    __tablename__ = "aw_anime"
    id         = db.Column(db.Integer, primary_key=True)
    mal_id     = db.Column(db.Integer, unique=True, nullable=False, index=True)
    title      = db.Column(db.String(512), nullable=False)
    title_en   = db.Column(db.String(512), nullable=True)
    image_url  = db.Column(db.String(512), nullable=True)
    episodes   = db.Column(db.Integer, nullable=True)
    score      = db.Column(db.Float, nullable=True)
    media_type = db.Column(db.String(32), nullable=True)
    status     = db.Column(db.String(64), nullable=True)
    genres     = db.Column(db.Text, nullable=True)   # comma-separated
    studios    = db.Column(db.Text, nullable=True)
    synopsis   = db.Column(db.Text, nullable=True)
    year       = db.Column(db.Integer, nullable=True)
    season     = db.Column(db.String(16), nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

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
        }


class UserAnimeList(db.Model):
    __tablename__ = "aw_user_anime_list"
    id               = db.Column(db.Integer, primary_key=True)
    user_id          = db.Column(db.Integer, db.ForeignKey("aw_user.id"), nullable=False)
    anime_id         = db.Column(db.Integer, db.ForeignKey("aw_anime.id"), nullable=False)
    watch_status     = db.Column(db.String(32), default="plan_to_watch")
    user_rating      = db.Column(db.Integer, nullable=True)
    episodes_watched = db.Column(db.Integer, default=0)
    added_at         = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at       = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    anime = db.relationship("Anime", backref="user_entries")
    user  = db.relationship("User",  backref="anime_list")

    __table_args__ = (db.UniqueConstraint("user_id", "anime_id", name="aw_uq_user_anime"),)

    def to_dict(self):
        d = self.anime.to_dict()
        d.update({
            "watch_status":     self.watch_status,
            "user_rating":      self.user_rating,
            "episodes_watched": self.episodes_watched,
            "added_at":         self.added_at.isoformat() if self.added_at else None,
        })
        return d


# ── Helpers ────────────────────────────────────────────────────────────────
def _mal_pub():
    return {"X-MAL-CLIENT-ID": MAL_CLIENT_ID}


def _mal_user(user):
    if user.mal_token_expires and datetime.datetime.utcnow() > user.mal_token_expires:
        _refresh(user)
    return {"Authorization": f"Bearer {user.mal_access_token}"}


def _refresh(user):
    r = requests.post(f"{MAL_AUTH_BASE}/token", data={
        "grant_type": "refresh_token", "refresh_token": user.mal_refresh_token,
        "client_id": MAL_CLIENT_ID, "client_secret": MAL_CLIENT_SECRET,
    })
    if r.ok:
        d = r.json()
        user.mal_access_token  = d["access_token"]
        user.mal_refresh_token = d.get("refresh_token", user.mal_refresh_token)
        user.mal_token_expires = datetime.datetime.utcnow() + datetime.timedelta(seconds=d["expires_in"])
        db.session.commit()


def _upsert(data):
    mid   = data.get("id") or data.get("mal_id")
    anime = Anime.query.filter_by(mal_id=mid).first()
    if not anime:
        anime = Anime(mal_id=mid)
        db.session.add(anime)
    alts = data.get("alternative_titles", {})
    anime.title      = data.get("title", "Unknown")
    anime.title_en   = alts.get("en") if isinstance(alts, dict) else None
    anime.image_url  = (data.get("main_picture") or {}).get("large") or (data.get("main_picture") or {}).get("medium")
    anime.episodes   = data.get("num_episodes") or data.get("episodes")
    anime.score      = data.get("mean") or data.get("score")
    anime.media_type = data.get("media_type")
    anime.status     = data.get("status")
    anime.synopsis   = data.get("synopsis")
    ss = data.get("start_season") or {}
    anime.year   = ss.get("year")
    anime.season = ss.get("season")
    anime.genres  = ",".join(g["name"] for g in data.get("genres",  []) if isinstance(g, dict))
    anime.studios = ",".join(s["name"] for s in data.get("studios", []) if isinstance(s, dict))
    anime.updated_at = datetime.datetime.utcnow()
    db.session.commit()
    return anime


def _get_url_for(endpoint, **kwargs):
    """Prefix-aware url_for that works under /animewatchlist."""
    return url_for(f"animewatchlist.{endpoint}", **kwargs)


STATUS_LABELS = {
    "completed":     "Completed",
    "watching":      "Watching",
    "plan_to_watch": "Plan to Watch",
    "dropped":       "Dropped",
}

TABS = [
    {"id": "all",          "label": "Top Rated"},
    {"id": "airing",       "label": "Airing"},
    {"id": "seasonal",     "label": "This Season"},
    {"id": "bypopularity", "label": "Popular"},
    {"id": "movie",        "label": "Films"},
]

LIST_TABS = [
    {"id": "",              "label": "All"},
    {"id": "watching",      "label": "Watching"},
    {"id": "completed",     "label": "Completed"},
    {"id": "plan_to_watch", "label": "Plan to Watch"},
    {"id": "dropped",       "label": "Dropped"},
]


# ── Routes ─────────────────────────────────────────────────────────────────

@bp.route("/")
def index():
    tab  = request.args.get("tab", "all")
    page = int(request.args.get("page", 1))
    limit, offset = 24, (page - 1) * 24
    try:
        if tab == "seasonal":
            url = f"{MAL_API_BASE}/anime/season/{datetime.datetime.now().year}/{_season()}"
            params = {"limit": limit, "fields": ANIME_FIELDS, "sort": "anime_score"}
        else:
            url = f"{MAL_API_BASE}/anime/ranking"
            params = {"ranking_type": tab, "limit": limit, "offset": offset, "fields": ANIME_FIELDS}
        resp = requests.get(url, headers=_mal_pub(), params=params, timeout=10)
        items = [_upsert(i["node"]).to_dict() for i in (resp.json().get("data", []) if resp.ok else [])]
    except Exception:
        items = []
    return render_template("index.html", anime_list=items, tabs=TABS, tab=tab,
                           page=page, active="discover", get_url_for=_get_url_for)


@bp.route("/search")
def search():
    q = request.args.get("q", "").strip()
    results = []
    if q:
        try:
            resp = requests.get(f"{MAL_API_BASE}/anime", headers=_mal_pub(),
                                params={"q": q, "limit": 40, "fields": ANIME_FIELDS}, timeout=10)
            if resp.ok:
                results = [_upsert(i["node"]).to_dict() for i in resp.json().get("data", [])]
        except Exception:
            pass
    return render_template("search.html", results=results, query=q,
                           active="search", get_url_for=_get_url_for)


@bp.route("/list")
@login_required
def watchlist():
    status = request.args.get("status", "")
    q = UserAnimeList.query.filter_by(user_id=current_user.id)
    if status:
        q = q.filter_by(watch_status=status)
    entries = [e.to_dict() for e in q.order_by(UserAnimeList.updated_at.desc()).all()]
    return render_template("list.html", entries=entries, tabs=LIST_TABS,
                           status=status, status_labels=STATUS_LABELS,
                           active="list", get_url_for=_get_url_for)


@bp.route("/list/add", methods=["POST"])
@login_required
def add_to_list():
    mal_id   = request.form.get("mal_id")
    status   = request.form.get("watch_status", "plan_to_watch")
    rating   = request.form.get("user_rating") or None
    eps      = int(request.form.get("episodes_watched") or 0)
    if not mal_id:
        flash("Missing anime ID", "error")
        return redirect(request.referrer or _get_url_for("index"))

    anime = Anime.query.filter_by(mal_id=int(mal_id)).first()
    if not anime:
        try:
            resp = requests.get(f"{MAL_API_BASE}/anime/{mal_id}",
                                headers=_mal_pub(), params={"fields": ANIME_FIELDS}, timeout=10)
            anime = _upsert(resp.json()) if resp.ok else None
        except Exception:
            anime = None
    if not anime:
        flash("Could not find that anime", "error")
        return redirect(request.referrer or _get_url_for("index"))

    entry = UserAnimeList.query.filter_by(user_id=current_user.id, anime_id=anime.id).first()
    if not entry:
        entry = UserAnimeList(user_id=current_user.id, anime_id=anime.id)
        db.session.add(entry)
    entry.watch_status     = status
    entry.user_rating      = int(rating) if rating else None
    entry.episodes_watched = eps
    entry.updated_at       = datetime.datetime.utcnow()
    db.session.commit()
    flash(f"Added \"{anime.title_en or anime.title}\" to your list", "success")
    return redirect(request.referrer or _get_url_for("index"))


@bp.route("/list/update/<int:mal_id>", methods=["POST"])
@login_required
def update_entry(mal_id):
    anime = Anime.query.filter_by(mal_id=mal_id).first()
    if not anime:
        flash("Anime not found", "error")
        return redirect(_get_url_for("watchlist"))
    entry = UserAnimeList.query.filter_by(user_id=current_user.id, anime_id=anime.id).first()
    if not entry:
        flash("Not in your list", "error")
        return redirect(_get_url_for("watchlist"))
    entry.watch_status = request.form.get("watch_status", entry.watch_status)
    r = request.form.get("user_rating")
    entry.user_rating  = int(r) if r else None
    entry.updated_at   = datetime.datetime.utcnow()
    db.session.commit()
    flash("Updated", "success")
    return redirect(request.referrer or _get_url_for("watchlist"))


@bp.route("/list/remove/<int:mal_id>", methods=["POST"])
@login_required
def remove_entry(mal_id):
    anime = Anime.query.filter_by(mal_id=mal_id).first()
    if anime:
        entry = UserAnimeList.query.filter_by(user_id=current_user.id, anime_id=anime.id).first()
        if entry:
            db.session.delete(entry)
            db.session.commit()
            flash("Removed", "success")
    return redirect(request.referrer or _get_url_for("watchlist"))


@bp.route("/stats")
@login_required
def stats():
    entries = UserAnimeList.query.filter_by(user_id=current_user.id).all()
    completed   = [e for e in entries if e.watch_status == "completed"]
    watching    = [e for e in entries if e.watch_status == "watching"]
    ptw         = [e for e in entries if e.watch_status == "plan_to_watch"]
    dropped     = [e for e in entries if e.watch_status == "dropped"]
    rated       = [e for e in entries if e.user_rating]
    total_eps   = sum((e.anime.episodes or 0) for e in completed)
    mean_score  = round(sum(e.user_rating for e in rated) / len(rated), 1) if rated else 0

    genre_count = {}
    for e in entries:
        for g in (e.anime.genres or "").split(","):
            g = g.strip()
            if g: genre_count[g] = genre_count.get(g, 0) + 1
    top_genres = sorted(genre_count.items(), key=lambda x: x[1], reverse=True)[:10]
    top_rated  = sorted(rated, key=lambda e: e.user_rating, reverse=True)[:5]

    stats_data = {
        "total":          len(entries),
        "completed":      len(completed),
        "watching":       len(watching),
        "plan_to_watch":  len(ptw),
        "dropped":        len(dropped),
        "total_episodes": total_eps,
        "mean_score":     mean_score,
        "genres":         top_genres,
        "top_rated":      [e.to_dict() for e in top_rated],
    }
    return render_template("stats.html", stats=stats_data,
                           active="stats", get_url_for=_get_url_for)


@bp.route("/recommendations")
@login_required
def recommendations():
    completed = (UserAnimeList.query
                 .filter_by(user_id=current_user.id, watch_status="completed")
                 .order_by(UserAnimeList.user_rating.desc().nullslast())
                 .limit(10).all())
    watched_ids = {e.anime.mal_id for e in UserAnimeList.query.filter_by(user_id=current_user.id).all()}
    recs = {}
    for entry in completed[:5]:
        try:
            r = requests.get(f"{MAL_API_BASE}/anime/{entry.anime.mal_id}",
                             headers=_mal_pub(), params={"fields": "recommendations"}, timeout=8)
            if r.ok:
                for rec in r.json().get("recommendations", [])[:5]:
                    node = rec.get("node", {})
                    mid  = node.get("id")
                    if mid and mid not in watched_ids:
                        recs[mid] = node
        except Exception:
            pass

    results = []
    for mid in list(recs.keys())[:20]:
        try:
            full = requests.get(f"{MAL_API_BASE}/anime/{mid}",
                                headers=_mal_pub(), params={"fields": ANIME_FIELDS}, timeout=8)
            if full.ok:
                results.append(_upsert(full.json()).to_dict())
        except Exception:
            pass

    if not results:
        # Fallback: top ranked
        try:
            r = requests.get(f"{MAL_API_BASE}/anime/ranking", headers=_mal_pub(),
                             params={"ranking_type": "all", "limit": 20, "fields": ANIME_FIELDS}, timeout=10)
            if r.ok:
                results = [_upsert(i["node"]).to_dict() for i in r.json().get("data", [])]
        except Exception:
            pass

    return render_template("recommendations.html", anime_list=results,
                           active="recs", get_url_for=_get_url_for)


@bp.route("/profile")
@login_required
def profile():
    return render_template("profile.html", active="profile", get_url_for=_get_url_for)


# ── Auth ───────────────────────────────────────────────────────────────────

@bp.route("/auth/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(_get_url_for("index"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email    = request.form.get("email", "").strip() or None
        password = request.form.get("password", "")
        if not username or not password:
            flash("Username and password required", "error")
        elif User.query.filter_by(username=username).first():
            flash("Username already taken", "error")
        else:
            u = User(username=username, email=email)
            u.set_password(password)
            db.session.add(u)
            db.session.commit()
            login_user(u)
            flash("Account created", "success")
            return redirect(_get_url_for("index"))
    return render_template("register.html", active=None, get_url_for=_get_url_for)


@bp.route("/auth/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(_get_url_for("index"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        u = User.query.filter_by(username=username).first()
        if u and u.check_password(password):
            login_user(u)
            return redirect(_get_url_for("index"))
        flash("Invalid credentials", "error")
    return render_template("login.html", active=None, get_url_for=_get_url_for)


@bp.route("/auth/logout")
@login_required
def logout():
    logout_user()
    return redirect(_get_url_for("index"))


# ── MAL OAuth ──────────────────────────────────────────────────────────────

def _pkce():
    v = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    c = base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).rstrip(b"=").decode()
    return v, c


@bp.route("/auth/mal/authorize")
def mal_authorize():
    v, c = _pkce()
    state = secrets.token_urlsafe(16)
    session["mal_verifier"] = v
    session["mal_state"]    = state
    params = (f"response_type=code&client_id={MAL_CLIENT_ID}"
              f"&redirect_uri={MAL_REDIRECT_URI}&state={state}"
              f"&code_challenge={c}&code_challenge_method=plain")
    return redirect(f"{MAL_AUTH_BASE}/authorize?{params}")


@bp.route("/auth/mal/callback")
def mal_callback():
    code  = request.args.get("code")
    state = request.args.get("state")
    if state != session.pop("mal_state", None):
        flash("OAuth state mismatch", "error")
        return redirect(_get_url_for("login"))

    verifier = session.pop("mal_verifier", "")
    resp = requests.post(f"{MAL_AUTH_BASE}/token", data={
        "client_id": MAL_CLIENT_ID, "client_secret": MAL_CLIENT_SECRET,
        "code": code, "code_verifier": verifier,
        "grant_type": "authorization_code", "redirect_uri": MAL_REDIRECT_URI,
    })
    if not resp.ok:
        flash("MAL token exchange failed", "error")
        return redirect(_get_url_for("login"))

    tokens = resp.json()
    access  = tokens["access_token"]
    refresh = tokens.get("refresh_token")
    expires = datetime.datetime.utcnow() + datetime.timedelta(seconds=tokens["expires_in"])

    mal_info = requests.get(f"{MAL_API_BASE}/users/@me",
                            headers={"Authorization": f"Bearer {access}"}).json()
    mal_uid  = mal_info.get("id")
    mal_name = mal_info.get("name")

    u = User.query.get(current_user.id) if current_user.is_authenticated else None
    if not u:
        u = User.query.filter_by(mal_user_id=mal_uid).first()
    if not u:
        u = User(username=mal_name or f"mal_{mal_uid}", mal_user_id=mal_uid)
        db.session.add(u)

    u.mal_user_id       = mal_uid
    u.mal_username      = mal_name
    u.mal_access_token  = access
    u.mal_refresh_token = refresh
    u.mal_token_expires = expires
    db.session.commit()
    login_user(u)
    flash(f"Connected as {mal_name}", "success")
    return redirect(_get_url_for("profile"))


@bp.route("/auth/mal/unlink", methods=["POST"])
@login_required
def mal_unlink():
    current_user.mal_access_token  = None
    current_user.mal_refresh_token = None
    current_user.mal_token_expires = None
    current_user.mal_user_id       = None
    current_user.mal_username      = None
    db.session.commit()
    flash("MAL unlinked", "success")
    return redirect(_get_url_for("profile"))


@bp.route("/auth/mal/sync", methods=["POST"])
@login_required
def mal_sync():
    if not current_user.mal_linked:
        flash("MAL not linked", "error")
        return redirect(_get_url_for("profile"))
    synced, offset = 0, 0
    fields = "list_status,num_episodes,mean,genres,studios,main_picture,alternative_titles,start_season"
    while True:
        r = requests.get(f"{MAL_API_BASE}/users/@me/animelist",
                         headers=_mal_user(current_user),
                         params={"fields": fields, "limit": 100, "offset": offset, "nsfw": True},
                         timeout=15)
        if not r.ok:
            break
        data = r.json()
        for item in data.get("data", []):
            node = item["node"]
            ls   = item.get("list_status", {})
            anime = _upsert(node)
            entry = UserAnimeList.query.filter_by(user_id=current_user.id, anime_id=anime.id).first()
            if not entry:
                entry = UserAnimeList(user_id=current_user.id, anime_id=anime.id)
                db.session.add(entry)
            sm = {"watching":"watching","completed":"completed",
                  "on_hold":"watching","dropped":"dropped","plan_to_watch":"plan_to_watch"}
            entry.watch_status     = sm.get(ls.get("status", "plan_to_watch"), "plan_to_watch")
            entry.user_rating      = ls.get("score") or None
            entry.episodes_watched = ls.get("num_episodes_watched", 0)
            synced += 1
        if not data.get("paging", {}).get("next"):
            break
        offset += 100
    db.session.commit()
    flash(f"Synced {synced} titles from MAL", "success")
    return redirect(_get_url_for("profile"))


# ── Factory ────────────────────────────────────────────────────────────────

def create_app(app):
    """Register blueprint + init db on an existing Flask app."""
    db.init_app(app)
    login.init_app(app)
    login.login_view = "animewatchlist.login"

    @login.user_loader
    def load_user(uid):
        return User.query.get(int(uid))

    app.register_blueprint(bp, url_prefix="/animewatchlist")

    with app.app_context():
        db.create_all()

    return app


def _season():
    m = datetime.datetime.now().month
    if m in [12, 1, 2]:  return "winter"
    if m in [3, 4, 5]:   return "spring"
    if m in [6, 7, 8]:   return "summer"
    return "fall"
