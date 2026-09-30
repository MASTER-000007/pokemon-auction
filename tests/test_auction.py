"""Bidding rules, timers, anti-snipe, team limits."""
import time

from app.game_engine import manager


def _room_with_two_players(seeded_pokemon, settings=None):
    created, _ = manager.create_room("Ash", settings or {})
    joined, _ = manager.join_room(created["code"], "Misty")
    ok, error = manager.start_game(created["code"], created["room_player_id"])
    assert ok, error
    return created, joined


def test_bid_must_exceed_starting_bid(app, seeded_pokemon):
    created, joined = _room_with_two_players(seeded_pokemon)
    rt = manager.get_room(created["code"])
    starting = rt.auction.starting_bid

    ok, error, _ = manager.place_bid(created["code"], created["room_player_id"],
                                     starting - 1)
    assert not ok

    ok, error, payload = manager.place_bid(created["code"],
                                           created["room_player_id"], starting)
    assert ok, error
    assert payload["amount"] == starting


def test_bid_must_respect_increment(app, seeded_pokemon):
    created, joined = _room_with_two_players(seeded_pokemon)
    rt = manager.get_room(created["code"])
    starting = rt.auction.starting_bid

    manager.place_bid(created["code"], created["room_player_id"], starting)

    ok, error, _ = manager.place_bid(created["code"], joined["room_player_id"],
                                     starting + 1)
    assert not ok
    assert "at least" in error.lower()

    ok, error, _ = manager.place_bid(created["code"], joined["room_player_id"],
                                     starting + 10)
    assert ok, error


def test_cannot_bid_more_than_balance(app, seeded_pokemon):
    created, joined = _room_with_two_players(seeded_pokemon)
    ok, error, _ = manager.place_bid(created["code"], created["room_player_id"],
                                     10 ** 7)
    assert not ok
    assert "only have" in error.lower() or "maximum" in error.lower()


def test_cannot_bid_negative_or_fractional(app, seeded_pokemon):
    created, _ = _room_with_two_players(seeded_pokemon)
    for bad in (-5, 0, 12.5, "abc"):
        ok, error, _ = manager.place_bid(created["code"], created["room_player_id"], bad)
        assert not ok


def test_same_bidder_cannot_bid_twice_in_a_row(app, seeded_pokemon):
    created, _ = _room_with_two_players(seeded_pokemon)
    rt = manager.get_room(created["code"])
    starting = rt.auction.starting_bid

    ok, _, _ = manager.place_bid(created["code"], created["room_player_id"], starting)
    assert ok

    ok, error, _ = manager.place_bid(created["code"], created["room_player_id"],
                                     starting + 10)
    assert not ok
    assert "highest bid" in error.lower()


def test_anti_snipe_extends_timer(app, seeded_pokemon):
    created, joined = _room_with_two_players(seeded_pokemon)
    rt = manager.get_room(created["code"])
    starting = rt.auction.starting_bid

    rt.auction.ends_at = time.time() + 2      # inside the 5s window
    before = rt.auction.ends_at

    ok, error, _ = manager.place_bid(created["code"], created["room_player_id"], starting)
    assert ok, error
    assert rt.auction.ends_at > before
    assert rt.auction.extensions >= 1


def test_bid_after_timer_expires_is_rejected(app, seeded_pokemon):
    created, _ = _room_with_two_players(seeded_pokemon)
    rt = manager.get_room(created["code"])
    rt.auction.ends_at = time.time() - 1

    ok, error, _ = manager.place_bid(created["code"], created["room_player_id"],
                                     rt.auction.starting_bid)
    assert not ok
    assert "ended" in error.lower()


def test_bid_rejected_when_team_full(app, seeded_pokemon):
    created, _ = _room_with_two_players(seeded_pokemon, {"team_size": 1})
    rt = manager.get_room(created["code"])

    ok, error, _ = manager.place_bid(created["code"], created["room_player_id"],
                                     rt.auction.starting_bid)
    assert ok, error

    manager._resolve_auction(rt, rt.auction.auction_id)

    player = rt.players[created["room_player_id"]]
    assert len(player.team) == 1

    # Force a new auction for the other player
    manager._start_next_auction(rt)
    if rt.auction:
        ok, error, _ = manager.place_bid(created["code"],
                                         created["room_player_id"],
                                         rt.auction.starting_bid)
        assert not ok
        assert "team" in error.lower()


def test_duplicate_pokemon_not_reused(app, seeded_pokemon):
    created, joined = _room_with_two_players(seeded_pokemon)
    rt = manager.get_room(created["code"])

    seen = set()
    for _ in range(6):
        if not rt.auction:
            break
        seen.add(rt.auction.pokemon["id"])
        manager._resolve_auction(rt, rt.auction.auction_id)
        manager._start_next_auction(rt)

    assert len(seen) == len(set(seen))


def test_wallet_deducted_on_win(app, seeded_pokemon):
    created, _ = _room_with_two_players(seeded_pokemon)
    rt = manager.get_room(created["code"])
    starting = rt.auction.starting_bid

    manager.place_bid(created["code"], created["room_player_id"], starting)
    manager._resolve_auction(rt, rt.auction.auction_id)

    player = rt.players[created["room_player_id"]]
    assert player.coins == 1000 - starting
    assert len(player.team) == 1


def test_bid_rejected_outside_auction_state(app, seeded_pokemon):
    created, _ = manager.create_room("Ash")
    manager.join_room(created["code"], "Misty")
    ok, error, _ = manager.place_bid(created["code"], created["room_player_id"], 100)
    assert not ok