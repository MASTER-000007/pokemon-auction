"""Central configuration for Pokémon Auction."""
import os

from dotenv import load_dotenv
from sqlalchemy.pool import NullPool

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, ".env"))


def _bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_db_url(url):
    """Render/Heroku hand out ``postgres://`` which SQLAlchemy 1.4+ rejects."""
    if not url:
        return "sqlite:///" + os.path.join(basedir, "pokemon_auction.db")
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


class Config:
    # ------------------------------------------------------------------
    # Flask / DB
    # ------------------------------------------------------------------
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
    SQLALCHEMY_DATABASE_URI = _normalize_db_url(os.environ.get("DATABASE_URL"))
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # NullPool avoids a known incompatibility between SQLAlchemy's QueuePool
    # and eventlet's monkey-patching.
    SQLALCHEMY_ENGINE_OPTIONS = {
        "poolclass": NullPool,
    }

    AUTO_CREATE_DB = _bool(os.environ.get("AUTO_CREATE_DB"), True)
    JSON_SORT_KEYS = False

    # ------------------------------------------------------------------
    # GAME CONFIGURATION  (single source of truth)
    # ------------------------------------------------------------------
    STARTING_COINS = _int(os.environ.get("STARTING_COINS"), 1000)
    TEAM_SIZE = _int(os.environ.get("TEAM_SIZE"), 4)
    MIN_PLAYERS = _int(os.environ.get("MIN_PLAYERS"), 2)
    MAX_PLAYERS = _int(os.environ.get("MAX_PLAYERS"), 8)
    AUCTION_DURATION = _int(os.environ.get("AUCTION_DURATION"), 20)
    MIN_BID_INCREMENT = _int(os.environ.get("MIN_BID_INCREMENT"), 10)
    ANTI_SNIPE_ENABLED = _bool(os.environ.get("ANTI_SNIPE_ENABLED"), True)
    ANTI_SNIPE_SECONDS = _int(os.environ.get("ANTI_SNIPE_SECONDS"), 5)
    ALLOW_DUPLICATES = _bool(os.environ.get("ALLOW_DUPLICATES"), False)
    ALLOW_LEGENDARIES = _bool(os.environ.get("ALLOW_LEGENDARIES"), True)
    ALLOW_MYTHICALS = _bool(os.environ.get("ALLOW_MYTHICALS"), True)
    SHOW_PLAYER_BALANCES = _bool(os.environ.get("SHOW_PLAYER_BALANCES"), True)

    # 0 = auto (active_players * team_size * 2). Any positive value caps the
    # auction phase to that many auctions per game, so the game never runs
    # forever even if some auctions go unsold.
    MAX_TOTAL_AUCTIONS = _int(os.environ.get("MAX_TOTAL_AUCTIONS"), 0)

    # ------------------------------------------------------------------
    # Auction value formula (configurable in ONE place)
    # ------------------------------------------------------------------
    VALUE_BST_FACTOR = 0.10
    VALUE_LEGENDARY_MULT = 1.25
    VALUE_MYTHICAL_MULT = 1.35
    VALUE_MIN_STARTING_BID = 20
    VALUE_ROUND_TO = 5
    VALUE_MAX_STARTING_BID = 400

    # ------------------------------------------------------------------
    # PokéAPI
    # ------------------------------------------------------------------
    POKEMON_API_BASE = "https://pokeapi.co/api/v2"
    POKEMON_LIMIT = _int(os.environ.get("POKEMON_LIMIT"), 1025)
    POKEMON_FETCH_WORKERS = _int(os.environ.get("POKEMON_FETCH_WORKERS"), 12)
    POKEMON_REQUEST_TIMEOUT = 20

    # ------------------------------------------------------------------
    # Limits / anti-abuse
    # ------------------------------------------------------------------
    MAX_BID_AMOUNT = 1_000_000
    BID_RATE_LIMIT_SECONDS = 0.30
    CHAT_RATE_LIMIT_SECONDS = 0.70
    CHAT_MAX_LENGTH = 240
    CHAT_HISTORY = 60
    ROOM_IDLE_TIMEOUT = 60 * 60 * 6
    HOST_TRANSFER_GRACE = 20
    MAX_CONSECUTIVE_UNSOLD = 3
    NAME_MAX_LENGTH = 16

    # ------------------------------------------------------------------
    # Battle simulator
    # ------------------------------------------------------------------
    BATTLE_LEVEL = 50
    BATTLE_MOVE_POWER = 80
    BATTLE_MAX_TURNS = 60
    STAB_MULTIPLIER = 1.5
