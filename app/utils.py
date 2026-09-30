"""Small shared helpers."""
import html
import re
import secrets
import time

ROOM_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # no I/O/0/1
_ROOM_PREFIX = "POKE"


def generate_room_code(length=4):
    """Cryptographically secure, human friendly room code -> ``POKE-7X92``."""
    body = "".join(secrets.choice(ROOM_CODE_ALPHABET) for _ in range(length))
    return f"{_ROOM_PREFIX}-{body}"


def generate_session_token():
    return secrets.token_urlsafe(32)


def now_ts():
    return time.time()


def clamp(value, low, high):
    return max(low, min(high, value))


_NAME_RE = re.compile(r"[^A-Za-z0-9 _.\-']")


def sanitize_name(raw, max_length=16):
    """Return a safe display name or ``''`` if invalid."""
    if raw is None:
        return ""
    name = str(raw).strip()
    name = _NAME_RE.sub("", name)
    name = re.sub(r"\s+", " ", name).strip()
    if not name:
        return ""
    return name[:max_length]


def sanitize_chat(raw, max_length=240):
    """Escape HTML and trim a chat message."""
    if raw is None:
        return ""
    text = str(raw)[: max_length * 2]
    text = text.replace("\x00", "")
    text = re.sub(r"[\r\n\t]+", " ", text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    if not text:
        return ""
    return html.escape(text[:max_length], quote=True)


def format_pokemon_name(slug):
    """``mr-mime`` -> ``Mr Mime``, with a few manual overrides."""
    overrides = {
        "nidoran-f": "Nidoran♀",
        "nidoran-m": "Nidoran♂",
        "mr-mime": "Mr. Mime",
        "mime-jr": "Mime Jr.",
        "mr-rime": "Mr. Rime",
        "type-null": "Type: Null",
        "jangmo-o": "Jangmo-o",
        "hakamo-o": "Hakamo-o",
        "kommo-o": "Kommo-o",
        "tapu-koko": "Tapu Koko",
        "tapu-lele": "Tapu Lele",
        "tapu-bulu": "Tapu Bulu",
        "tapu-fini": "Tapu Fini",
        "ho-oh": "Ho-Oh",
        "porygon-z": "Porygon-Z",
        "farfetchd": "Farfetch'd",
        "sirfetchd": "Sirfetch'd",
        "flabebe": "Flabébé",
    }
    if slug in overrides:
        return overrides[slug]
    return " ".join(part.capitalize() for part in slug.split("-"))