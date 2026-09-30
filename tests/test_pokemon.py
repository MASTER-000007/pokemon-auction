"""PokéAPI cache helpers, value formula, name normalisation."""
from app.models import Pokemon
from app.pokemon_api import compute_auction_value, fetch_pokemon
from app.utils import format_pokemon_name


def test_auction_value_scales_with_bst():
    low = compute_auction_value(300, False, False)
    mid = compute_auction_value(500, False, False)
    high = compute_auction_value(680, False, False)
    assert low < mid < high


def test_legendary_and_mythical_bonus():
    base = compute_auction_value(600, False, False)
    legend = compute_auction_value(600, True, False)
    myth = compute_auction_value(600, False, True)
    assert legend > base
    assert myth > legend


def test_auction_value_never_below_floor():
    assert compute_auction_value(1, False, False) >= 20


def test_auction_value_never_above_ceiling():
    assert compute_auction_value(10000, True, True) <= 400


def test_name_normalisation():
    assert format_pokemon_name("charizard") == "Charizard"
    assert format_pokemon_name("mr-mime") == "Mr. Mime"
    assert format_pokemon_name("nidoran-f") == "Nidoran♀"
    assert format_pokemon_name("ho-oh") == "Ho-Oh"


def test_seeded_pokemon_roundtrip(app, seeded_pokemon):
    poke = Pokemon.query.filter_by(name="Charizard").first()
    assert poke is not None
    data = poke.to_dict()
    assert data["types"] == ["fire", "flying"]
    assert data["bst"] == 78 + 84 + 78 + 109 + 85 + 100
    assert data["auction_value"] > 0


def test_fetch_pokemon_handles_bad_id():
    import requests

    class DummySession:
        def get(self, *a, **kw):
            raise requests.RequestException("boom")

    assert fetch_pokemon(1, DummySession(), "https://example.invalid") is None


def test_manager_pool_is_cached(app, seeded_pokemon):
    from app.game_engine import manager
    manager.invalidate_pool()
    first = manager._load_pool()
    second = manager._load_pool()
    assert first is second
    assert len(first) == len(seeded_pokemon)