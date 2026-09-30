import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app, db as _db           # noqa: E402
from app.game_engine import manager             # noqa: E402
from app.pokemon_api import compute_auction_value  # noqa: E402


class TestConfig:
    TESTING = True
    SECRET_KEY = "test-secret"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    AUTO_CREATE_DB = False
    WTF_CSRF_ENABLED = False

    STARTING_COINS = 1000
    TEAM_SIZE = 4
    MIN_PLAYERS = 2
    MAX_PLAYERS = 8
    AUCTION_DURATION = 20
    MIN_BID_INCREMENT = 10
    ANTI_SNIPE_ENABLED = True
    ANTI_SNIPE_SECONDS = 5
    ALLOW_DUPLICATES = False
    ALLOW_LEGENDARIES = True
    ALLOW_MYTHICALS = True
    SHOW_PLAYER_BALANCES = True
    MAX_BID_AMOUNT = 1_000_000
    BID_RATE_LIMIT_SECONDS = 0.0
    CHAT_RATE_LIMIT_SECONDS = 0.0
    CHAT_MAX_LENGTH = 240
    CHAT_HISTORY = 60
    ROOM_IDLE_TIMEOUT = 3600
    HOST_TRANSFER_GRACE = 1
    MAX_CONSECUTIVE_UNSOLD = 3
    NAME_MAX_LENGTH = 16
    VALUE_BST_FACTOR = 0.10
    VALUE_LEGENDARY_MULT = 1.25
    VALUE_MYTHICAL_MULT = 1.35
    VALUE_MIN_STARTING_BID = 20
    VALUE_ROUND_TO = 5
    VALUE_MAX_STARTING_BID = 400
    BATTLE_LEVEL = 50
    BATTLE_MOVE_POWER = 80
    BATTLE_MAX_TURNS = 60
    STAB_MULTIPLIER = 1.5


@pytest.fixture()
def app():
    application = create_app(TestConfig)
    with application.app_context():
        _db.create_all()
        manager.rooms.clear()
        manager._pool = None
        yield application
        _db.session.remove()
        _db.drop_all()
        manager.rooms.clear()
        manager._pool = None


@pytest.fixture()
def client(app):
    return app.test_client()


def make_pokemon(dex_id, name, types, **stats):
    from app.models import Pokemon
    base = {"hp": 60, "attack": 60, "defense": 60,
            "sp_attack": 60, "sp_defense": 60, "speed": 60}
    base.update(stats)
    bst = sum(base.values())
    poke = Pokemon(
        id=dex_id, name=name, bst=bst,
        is_legendary=stats.pop("is_legendary", False),
        is_mythical=stats.pop("is_mythical", False),
        auction_value=compute_auction_value(bst, False, False),
        sprite_url="", artwork_url="",
    )
    poke.types = list(types)
    poke.abilities = ["Test Ability"]
    for key, value in base.items():
        setattr(poke, key, value)
    return poke


@pytest.fixture()
def seeded_pokemon(app):
    from app import db
    from app.models import Pokemon
    rows = [
        make_pokemon(1, "Bulbasaur", ["grass", "poison"], hp=45, attack=49, defense=49,
                     sp_attack=65, sp_defense=65, speed=45),
        make_pokemon(4, "Charmander", ["fire"], hp=39, attack=52, defense=43,
                     sp_attack=60, sp_defense=50, speed=65),
        make_pokemon(7, "Squirtle", ["water"], hp=44, attack=48, defense=65,
                     sp_attack=50, sp_defense=64, speed=43),
        make_pokemon(25, "Pikachu", ["electric"], hp=35, attack=55, defense=40,
                     sp_attack=50, sp_defense=50, speed=90),
        make_pokemon(94, "Gengar", ["ghost", "poison"], hp=60, attack=65, defense=60,
                     sp_attack=130, sp_defense=75, speed=110),
        make_pokemon(130, "Gyarados", ["water", "flying"], hp=95, attack=125, defense=79,
                     sp_attack=60, sp_defense=100, speed=81),
        make_pokemon(445, "Garchomp", ["dragon", "ground"], hp=108, attack=130,
                     defense=95, sp_attack=80, sp_defense=85, speed=102),
        make_pokemon(448, "Lucario", ["fighting", "steel"], hp=70, attack=110,
                     defense=70, sp_attack=115, sp_defense=70, speed=90),
        make_pokemon(149, "Dragonite", ["dragon", "flying"], hp=91, attack=134,
                     defense=95, sp_attack=100, sp_defense=100, speed=80),
        make_pokemon(150, "Mewtwo", ["psychic"], hp=106, attack=110, defense=90,
                     sp_attack=154, sp_defense=90, speed=130, is_legendary=True),
        make_pokemon(151, "Mew", ["psychic"], hp=100, attack=100, defense=100,
                     sp_attack=100, sp_defense=100, speed=100, is_mythical=True),
        make_pokemon(6, "Charizard", ["fire", "flying"], hp=78, attack=84, defense=78,
                     sp_attack=109, sp_defense=85, speed=100),
    ]
    for row in rows:
        db.session.add(row)
    db.session.commit()
    manager.invalidate_pool()
    return rows