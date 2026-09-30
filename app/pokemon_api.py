"""PokéAPI integration + local caching layer.

The game NEVER talks to PokéAPI during gameplay — everything is served from the
local ``pokemon`` table.  ``populate_pokemon`` is the only place that performs
network requests.
"""
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from app.models import Pokemon
from app.utils import format_pokemon_name
from config import Config

STAT_KEYS = {
    "hp": "hp",
    "attack": "attack",
    "defense": "defense",
    "special-attack": "sp_attack",
    "special-defense": "sp_defense",
    "speed": "speed",
}


def compute_auction_value(bst, is_legendary, is_mythical):
    """Single configurable place for the starting-bid formula."""
    raw = bst * Config.VALUE_BST_FACTOR
    if is_mythical:
        raw *= Config.VALUE_MYTHICAL_MULT
    elif is_legendary:
        raw *= Config.VALUE_LEGENDARY_MULT

    step = max(1, Config.VALUE_ROUND_TO)
    rounded = int(round(raw / step) * step)
    return max(Config.VALUE_MIN_STARTING_BID, min(Config.VALUE_MAX_STARTING_BID, rounded))


def fetch_pokemon(dex_id, session, base_url):
    """Fetch one Pokémon + its species row.  Returns a dict or ``None``."""
    try:
        r = session.get(f"{base_url}/pokemon/{dex_id}", timeout=Config.POKEMON_REQUEST_TIMEOUT)
        if r.status_code != 200:
            return None
        data = r.json()

        try:
            sr = session.get(f"{base_url}/pokemon-species/{dex_id}",
                             timeout=Config.POKEMON_REQUEST_TIMEOUT)
            species = sr.json() if sr.status_code == 200 else {}
        except requests.RequestException:
            species = {}

        stats = {"hp": 1, "attack": 1, "defense": 1,
                 "sp_attack": 1, "sp_defense": 1, "speed": 1}
        for entry in data.get("stats", []):
            key = STAT_KEYS.get(entry["stat"]["name"])
            if key:
                stats[key] = int(entry["base_stat"])

        bst = sum(stats.values())

        types = [t["type"]["name"] for t in
                 sorted(data.get("types", []), key=lambda x: x["slot"])]
        abilities = [a["ability"]["name"].replace("-", " ").title()
                     for a in data.get("abilities", [])]

        sprites = data.get("sprites", {}) or {}
        other = sprites.get("other", {}) or {}
        artwork = (other.get("official-artwork", {}) or {}).get("front_default")
        sprite = sprites.get("front_default") or artwork

        is_legendary = bool(species.get("is_legendary"))
        is_mythical = bool(species.get("is_mythical"))
        generation = (species.get("generation", {}) or {}).get("name")

        return {
            "id": int(data["id"]),
            "name": format_pokemon_name(data["name"]),
            "types": types,
            "hp": stats["hp"],
            "attack": stats["attack"],
            "defense": stats["defense"],
            "sp_attack": stats["sp_attack"],
            "sp_defense": stats["sp_defense"],
            "speed": stats["speed"],
            "bst": bst,
            "sprite_url": sprite,
            "artwork_url": artwork or sprite,
            "abilities": abilities,
            "generation": generation,
            "is_legendary": is_legendary,
            "is_mythical": is_mythical,
            "auction_value": compute_auction_value(bst, is_legendary, is_mythical),
        }
    except (requests.RequestException, KeyError, ValueError, TypeError):
        return None


def populate_pokemon(limit=None, force=False, progress=True):
    """Populate the local Pokémon cache.  Safe to re-run (resumes where it left off)."""
    from app import db

    limit = limit or Config.POKEMON_LIMIT
    base_url = Config.POKEMON_API_BASE

    existing = {row[0] for row in db.session.query(Pokemon.id).all()}
    if force:
        existing = set()

    wanted = [i for i in range(1, limit + 1) if i not in existing]

    if not wanted:
        if progress:
            print(f"✔  Pokémon cache already complete ({len(existing)} entries).")
        return len(existing)

    if progress:
        print(f"→ Fetching {len(wanted)} Pokémon from PokéAPI "
              f"({len(existing)} already cached)…")

    session = requests.Session()
    session.headers.update({"User-Agent": "PokemonAuction/1.0 (educational project)"})

    added = 0
    failed = []
    started = time.time()

    with ThreadPoolExecutor(max_workers=Config.POKEMON_FETCH_WORKERS) as pool:
        futures = {pool.submit(fetch_pokemon, pid, session, base_url): pid
                   for pid in wanted}

        for done, future in enumerate(as_completed(futures), start=1):
            pid = futures[future]
            try:
                payload = future.result()
            except Exception:                     # pragma: no cover
                payload = None

            if not payload:
                failed.append(pid)
            else:
                if db.session.get(Pokemon, payload["id"]):
                    continue
                poke = Pokemon(
                    id=payload["id"],
                    name=payload["name"],
                    hp=payload["hp"],
                    attack=payload["attack"],
                    defense=payload["defense"],
                    sp_attack=payload["sp_attack"],
                    sp_defense=payload["sp_defense"],
                    speed=payload["speed"],
                    bst=payload["bst"],
                    sprite_url=payload["sprite_url"],
                    artwork_url=payload["artwork_url"],
                    generation=payload["generation"],
                    is_legendary=payload["is_legendary"],
                    is_mythical=payload["is_mythical"],
                    auction_value=payload["auction_value"],
                )
                poke.types = payload["types"]
                poke.abilities = payload["abilities"]
                db.session.add(poke)
                added += 1

            if progress and done % 25 == 0:
                db.session.commit()
                elapsed = time.time() - started
                rate = done / elapsed if elapsed else 0
                print(f"   … {done}/{len(wanted)} fetched "
                      f"({added} stored, {rate:.1f}/s)")

    db.session.commit()

    if progress:
        total = db.session.query(Pokemon).count()
        print(f"✔  Pokémon cache ready: {total} entries "
              f"({added} new, {len(failed)} failed).")
        if failed:
            print(f"   Failed ids: {failed[:20]}{' …' if len(failed) > 20 else ''}")

    return added


def ensure_pokemon_available():
    """Return True when the local cache has usable data."""
    from app import db
    try:
        return db.session.query(Pokemon.id).first() is not None
    except Exception:                             # pragma: no cover
        return False


if __name__ == "__main__":                        # pragma: no cover
    sys.exit(0)