#!/usr/bin/env python
"""Populate the local Pokémon cache from PokéAPI.

Usage:
    python init_pokemon.py                # uses POKEMON_LIMIT from .env
    python init_pokemon.py --limit 151    # only Gen 1
    python init_pokemon.py --force        # re-fetch everything
"""
import argparse
import sys

from app import create_app, db
from app.pokemon_api import populate_pokemon

app = create_app()


def main():
    parser = argparse.ArgumentParser(description="Populate the Pokémon cache.")
    parser.add_argument("--limit", type=int, default=None,
                        help="Highest national dex id to fetch (default: config).")
    parser.add_argument("--force", action="store_true",
                        help="Re-fetch Pokémon that are already cached.")
    args = parser.parse_args()

    with app.app_context():
        db.create_all()
        try:
            populate_pokemon(limit=args.limit, force=args.force)
        except KeyboardInterrupt:
            print("\nInterrupted — partial progress has been saved.")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())