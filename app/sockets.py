"""Socket.IO event handlers — thin wrappers around the authoritative manager."""
from flask import request, session
from flask_socketio import emit, join_room, leave_room

from app import socketio
from app.game_engine import manager


def _ctx():
    """Return ``(room_code, rp_id)`` from the Flask session."""
    return session.get("room_code"), session.get("room_player_id")


# ======================================================================
# Connection lifecycle
# ======================================================================
@socketio.on("connect")
def handle_connect():
    code, rp_id = _ctx()
    if not code or not rp_id:
        emit("sync_error", {"error": "No active session."})
        return

    rt = manager.get_room(code) or manager._load_room_from_db(code)
    if not rt or rp_id not in rt.players:
        emit("sync_error", {"error": "Room not found."})
        return

    join_room(code)
    manager.attach_socket(code, rp_id, request.sid)
    emit("state_sync", rt.snapshot(rp_id))


@socketio.on("disconnect")
def handle_disconnect():
    code, _rp_id = _ctx()
    if not code:
        return
    manager.detach_socket(code, request.sid)


# ======================================================================
# Explicit (re)join — used by clients after a page navigation
# ======================================================================
@socketio.on("join_room")
def handle_join_room(data):
    data = data or {}
    code = (data.get("room_code") or session.get("room_code") or "").upper()
    rp_id = session.get("room_player_id")

    if not code or not rp_id or session.get("room_code") != code:
        emit("error_message", {"error": "Invalid session."})
        return

    rt = manager.get_room(code) or manager._load_room_from_db(code)
    if not rt or rp_id not in rt.players:
        emit("error_message", {"error": "Room not found."})
        return

    join_room(code)
    manager.attach_socket(code, rp_id, request.sid)
    emit("state_sync", rt.snapshot(rp_id))


@socketio.on("request_state")
def handle_request_state():
    code, rp_id = _ctx()
    if not code or not rp_id:
        return
    rt = manager.get_room(code)
    if rt and rp_id in rt.players:
        emit("state_sync", rt.snapshot(rp_id))


# ======================================================================
# Game actions
# ======================================================================
@socketio.on("place_bid")
def handle_place_bid(data):
    code, rp_id = _ctx()
    if not code or not rp_id:
        emit("error_message", {"error": "Invalid session."})
        return

    data = data or {}
    ok, error, payload = manager.place_bid(code, rp_id, data.get("amount"))
    if not ok:
        emit("bid_rejected", {"error": error})
        return

    emit("bid_accepted", payload)


@socketio.on("chat_message")
def handle_chat(data):
    code, rp_id = _ctx()
    if not code or not rp_id:
        return
    data = data or {}
    ok, error = manager.add_chat(code, rp_id, data.get("text"))
    if not ok:
        emit("error_message", {"error": error})


@socketio.on("start_game")
def handle_start_game():
    code, rp_id = _ctx()
    if not code or not rp_id:
        return
    ok, error = manager.start_game(code, rp_id)
    if not ok:
        emit("error_message", {"error": error})


@socketio.on("update_settings")
def handle_update_settings(data):
    code, rp_id = _ctx()
    if not code or not rp_id:
        return
    ok, error = manager.update_settings(code, rp_id, (data or {}).get("settings"))
    if not ok:
        emit("error_message", {"error": error})


@socketio.on("kick_player")
def handle_kick(data):
    code, rp_id = _ctx()
    if not code or not rp_id:
        return
    target = (data or {}).get("player_id")
    ok, error = manager.kick_player(code, rp_id, target)
    if not ok:
        emit("error_message", {"error": error})


@socketio.on("end_room")
def handle_end_room():
    code, rp_id = _ctx()
    if not code or not rp_id:
        return
    manager.end_room(code, rp_id)


@socketio.on("leave_room")
def handle_leave():
    code, _rp_id = _ctx()
    if code:
        leave_room(code)