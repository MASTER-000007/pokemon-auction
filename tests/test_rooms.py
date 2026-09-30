"""Room creation, joining, host transfer, locking."""
from app.game_engine import manager


def test_create_room_returns_unique_code(app):
    r1, err1 = manager.create_room("Ash")
    r2, err2 = manager.create_room("Misty")
    assert err1 is None and err2 is None
    assert r1["code"] != r2["code"]
    assert r1["code"].startswith("POKE-")


def test_create_room_rejects_blank_name(app):
    result, error = manager.create_room("   ")
    assert result is None
    assert error


def test_join_room_success(app):
    created, _ = manager.create_room("Ash")
    joined, error = manager.join_room(created["code"], "Brock")
    assert error is None
    assert joined["room_player_id"] != created["room_player_id"]


def test_join_invalid_code(app):
    result, error = manager.join_room("POKE-ZZZZ", "Brock")
    assert result is None
    assert "does not exist" in error


def test_join_full_room(app):
    created, _ = manager.create_room("Ash", {"max_players": 2})
    manager.join_room(created["code"], "Misty")
    result, error = manager.join_room(created["code"], "Brock")
    assert result is None
    assert "full" in error.lower()


def test_cannot_join_after_start(app, seeded_pokemon):
    created, _ = manager.create_room("Ash")
    manager.join_room(created["code"], "Misty")
    ok, error = manager.start_game(created["code"], created["room_player_id"])
    assert ok, error
    result, error = manager.join_room(created["code"], "Late")
    assert result is None
    assert "already started" in error.lower()


def test_duplicate_name_rejected(app):
    created, _ = manager.create_room("Ash")
    result, error = manager.join_room(created["code"], "Ash")
    assert result is None
    assert "taken" in error.lower()


def test_host_transfer_on_disconnect(app):
    created, _ = manager.create_room("Ash")
    joined, _ = manager.join_room(created["code"], "Misty")

    rt = manager.get_room(created["code"])
    host_rp = created["room_player_id"]

    # Simulate the host losing every socket.
    rt.players[host_rp].sids.add("sid-host")
    manager.detach_socket(created["code"], "sid-host")
    manager.maybe_transfer_host(created["code"])

    assert rt.host_rp_id == joined["room_player_id"]
    assert rt.players[joined["room_player_id"]].is_host


def test_kick_player(app):
    created, _ = manager.create_room("Ash")
    joined, _ = manager.join_room(created["code"], "Misty")

    ok, error = manager.kick_player(created["code"], created["room_player_id"],
                                    joined["room_player_id"])
    assert ok, error
    rt = manager.get_room(created["code"])
    assert joined["room_player_id"] not in rt.players


def test_non_host_cannot_kick(app):
    created, _ = manager.create_room("Ash")
    joined, _ = manager.join_room(created["code"], "Misty")
    ok, error = manager.kick_player(created["code"], joined["room_player_id"],
                                    created["room_player_id"])
    assert not ok


def test_settings_normalised(app):
    created, _ = manager.create_room("Ash", {"max_players": 99, "team_size": 42})
    rt = manager.get_room(created["code"])
    assert rt.settings["max_players"] == 8
    assert rt.settings["team_size"] == 6