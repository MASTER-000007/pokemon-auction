"""HTTP routes — pages plus a small JSON API."""
import os
import threading
import time

from flask import (Blueprint, current_app, jsonify, redirect,
                   render_template, request, session, url_for)

from app import db
from app.battle import analyse_team
from app.game_engine import manager
from app.models import (Auction, Battle, BattleResult, Game, Player,
                        PlayerPokemon, Pokemon, Room, RoomPlayer)
from app.utils import sanitize_name
from config import Config

main_bp = Blueprint("main", __name__)


# ======================================================================
# Session helpers
# ======================================================================
def _current_rp(room_code):
    rp_id = session.get("room_player_id")
    if not rp_id or session.get("room_code") != room_code:
        return None
    rt = manager.get_room(room_code) or manager._load_room_from_db(room_code)
    if not rt:
        return None
    return rt.players.get(rp_id)


def _pokemon_count():
    try:
        return db.session.query(Pokemon.id).count()
    except Exception:
        return 0


# ======================================================================
# Pages
# ======================================================================
@main_bp.route("/")
def index():
    return render_template("index.html",
                           pokemon_count=_pokemon_count(),
                           config=Config)


@main_bp.route("/create", methods=["GET", "POST"])
def create():
    errors = []

    if request.method == "POST":
        name = sanitize_name(request.form.get("name"), Config.NAME_MAX_LENGTH)
        if not name:
            errors.append("Please enter a valid player name.")

        if _pokemon_count() == 0:
            errors.append("The Pokémon database is empty. "
                          "Run `python init_pokemon.py` and reload.")

        raw_settings = {
            "starting_coins": request.form.get("starting_coins"),
            "team_size": request.form.get("team_size"),
            "max_players": request.form.get("max_players"),
            "auction_duration": request.form.get("auction_duration"),
            "min_bid_increment": request.form.get("min_bid_increment"),
            "anti_snipe_enabled": request.form.get("anti_snipe_enabled") == "on",
            "anti_snipe_seconds": request.form.get("anti_snipe_seconds"),
            "allow_duplicates": request.form.get("allow_duplicates") == "on",
            "allow_legendaries": request.form.get("allow_legendaries") == "on",
            "allow_mythicals": request.form.get("allow_mythicals") == "on",
            "show_balances": request.form.get("show_balances") == "on",
            "max_total_auctions": request.form.get("max_total_auctions"),
        }
        raw_settings = {k: v for k, v in raw_settings.items() if v is not None}

        if not errors:
            result, error = manager.create_room(name, raw_settings)
            if error:
                errors.append(error)
            else:
                session.clear()
                session["room_code"] = result["code"]
                session["room_player_id"] = result["room_player_id"]
                session["player_id"] = result["player_id"]
                session.permanent = True
                return redirect(url_for("main.room", room_code=result["code"]))

    return render_template("create.html", errors=errors, config=Config,
                           pokemon_count=_pokemon_count())


@main_bp.route("/join", methods=["GET", "POST"])
def join():
    errors = []
    prefill = request.args.get("code", "").strip().upper()

    if request.method == "POST":
        code = (request.form.get("code") or "").strip().upper()
        name = sanitize_name(request.form.get("name"), Config.NAME_MAX_LENGTH)

        if not code:
            errors.append("Enter a room code.")
        if not name:
            errors.append("Enter a display name.")

        if not errors:
            existing_player_id = None
            if session.get("room_code") == code and session.get("player_id"):
                existing_player_id = session["player_id"]

            result, error = manager.join_room(code, name, existing_player_id)
            if error:
                errors.append(error)
            else:
                session.clear()
                session["room_code"] = result["code"]
                session["room_player_id"] = result["room_player_id"]
                session["player_id"] = result["player_id"]
                session.permanent = True
                return redirect(url_for("main.room", room_code=result["code"]))

    return render_template("join.html", errors=errors, prefill=prefill,
                           config=Config)


@main_bp.route("/room/<room_code>")
def room(room_code):
    room_code = room_code.upper()
    rt = manager.get_room(room_code) or manager._load_room_from_db(room_code)
    if not rt:
        return render_template("404.html",
                               message="That room does not exist or has closed."), 404

    rp_id = session.get("room_player_id")
    if not rp_id or session.get("room_code") != room_code:
        return redirect(url_for("main.join", code=room_code))
    if rp_id not in rt.players:
        session.pop("room_player_id", None)
        return redirect(url_for("main.join", code=room_code))

    if rt.state != "LOBBY":
        return redirect(url_for("main.game", room_code=room_code))

    return render_template("lobby.html", room_code=room_code,
                           rp_id=rp_id, config=Config)


@main_bp.route("/room/<room_code>/game")
def game(room_code):
    room_code = room_code.upper()
    rt = manager.get_room(room_code) or manager._load_room_from_db(room_code)
    if not rt:
        return render_template("404.html",
                               message="That room does not exist or has closed."), 404

    rp_id = session.get("room_player_id")
    if not rp_id or session.get("room_code") != room_code or rp_id not in rt.players:
        return redirect(url_for("main.join", code=room_code))

    if rt.state == "LOBBY":
        return redirect(url_for("main.room", room_code=room_code))
    if rt.state == "FINISHED":
        return redirect(url_for("main.results", room_code=room_code))

    return render_template("auction.html", room_code=room_code,
                           rp_id=rp_id, config=Config)


@main_bp.route("/room/<room_code>/results")
def results(room_code):
    room_code = room_code.upper()
    room = Room.query.filter_by(code=room_code).first()
    if not room:
        return render_template("404.html", message="Room not found."), 404

    game = (Game.query.filter_by(room_id=room.id)
            .order_by(Game.id.desc()).first())

    battles = []
    leaderboard = []
    teams = []

    if game:
        leaderboard = game.leaderboard
        for b in game.battles:
            details = b.details or {}
            battles.append({
                "player_a_id": b.player_a_id,
                "player_b_id": b.player_b_id,
                "name_a": b.name_a,
                "name_b": b.name_b,
                "wins_a": b.wins_a,
                "wins_b": b.wins_b,
                "draws": b.draws,
                "winner_id": b.winner_id,
                "hp_a_pct": b.hp_a_pct,
                "hp_b_pct": b.hp_b_pct,
                "tiebreak": b.tiebreak,
                "score_a": details.get("score_a", 0),
                "score_b": details.get("score_b", 0),
                "stats_a": details.get("stats_a", {}),
                "stats_b": details.get("stats_b", {}),
                "power_a": details.get("power_a", {}),
                "power_b": details.get("power_b", {}),
                "per_stat": details.get("per_stat", []),
            })

    for rp in room.room_players:
        if rp.is_kicked:
            continue
        team = [pp.pokemon.to_dict() for pp in rp.pokemons if pp.pokemon]
        teams.append({
            "id": rp.id,
            "name": rp.name,
            "team": team,
            "analysis": analyse_team(team),
        })

    return render_template("results.html", room_code=room_code,
                           leaderboard=leaderboard, battles=battles,
                           teams=teams, has_game=bool(game), config=Config)


@main_bp.route("/room/<room_code>/leaderboard")
def leaderboard(room_code):
    room_code = room_code.upper()
    room = Room.query.filter_by(code=room_code).first()
    if not room:
        return render_template("404.html", message="Room not found."), 404

    game = (Game.query.filter_by(room_id=room.id)
            .order_by(Game.id.desc()).first())
    rows = game.leaderboard if game else []
    return render_template("leaderboard.html", room_code=room_code,
                           leaderboard=rows, has_game=bool(game), config=Config)


# ======================================================================
# HTTP fallbacks / JSON API
# ======================================================================
@main_bp.route("/room/<room_code>/start", methods=["POST"])
def start_room(room_code):
    room_code = room_code.upper()
    rp_id = session.get("room_player_id")
    if not rp_id or session.get("room_code") != room_code:
        return jsonify({"ok": False, "error": "Not in this room."}), 403
    ok, error = manager.start_game(room_code, rp_id)
    if not ok:
        return jsonify({"ok": False, "error": error}), 400
    return jsonify({"ok": True})


@main_bp.route("/leave", methods=["POST"])
def leave():
    session.pop("room_player_id", None)
    session.pop("room_code", None)
    return jsonify({"ok": True})


@main_bp.route("/api/room/<room_code>")
def api_room(room_code):
    room_code = room_code.upper()
    rp_id = session.get("room_player_id")
    snapshot = manager.room_full_snapshot(room_code, rp_id)
    if not snapshot:
        return jsonify({"ok": False, "error": "Room not found."}), 404
    snapshot["ok"] = True
    return jsonify(snapshot)


@main_bp.route("/api/room/<room_code>/pool")
def api_room_pool(room_code):
    room_code = room_code.upper()
    rt = manager.get_room(room_code) or manager._load_room_from_db(room_code)
    if not rt:
        return jsonify({"ok": False, "error": "Room not found."}), 404
    return jsonify({
        "ok": True,
        "used": sorted(rt.used_pokemon),
        "index": rt.auction_index,
    })


@main_bp.route("/api/pokemon/<int:pokemon_id>")
def api_pokemon(pokemon_id):
    poke = db.session.get(Pokemon, pokemon_id)
    if not poke:
        return jsonify({"ok": False, "error": "Pokémon not found."}), 404
    return jsonify({"ok": True, "pokemon": poke.to_dict()})


@main_bp.route("/api/pokemon")
def api_pokemon_search():
    query = (request.args.get("q") or "").strip()
    if not query:
        return jsonify({"ok": True, "results": []})
    rows = (Pokemon.query
            .filter(Pokemon.name.ilike(f"%{query}%"))
            .order_by(Pokemon.id)
            .limit(25).all())
    return jsonify({"ok": True,
                    "results": [{"id": p.id, "name": p.name,
                                 "sprite": p.sprite_url,
                                 "types": p.types, "bst": p.bst} for p in rows]})


@main_bp.route("/api/player/<int:player_id>")
def api_player(player_id):
    player = db.session.get(Player, player_id)
    if not player:
        return jsonify({"ok": False, "error": "Player not found."}), 404
    return jsonify({"ok": True, "player": player.to_dict()})


@main_bp.route("/api/stats")
def api_stats():
    return jsonify({
        "ok": True,
        "pokemon_cached": _pokemon_count(),
        "active_rooms": len(manager.rooms),
    })


# ======================================================================
# Admin: background Pokémon cache population
# ======================================================================
_INIT_STATE = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "limit": 0,
    "initial_count": 0,
    "last_error": None,
    "thread": None,
}


def _run_init_in_thread(app, limit):
    with app.app_context():
        try:
            from app.pokemon_api import populate_pokemon
            populate_pokemon(limit=limit, progress=True)
        except Exception as exc:
            _INIT_STATE["last_error"] = str(exc)
        finally:
            _INIT_STATE["finished_at"] = time.time()
            _INIT_STATE["running"] = False


@main_bp.route("/admin/init-pokemon")
def admin_init_pokemon():
    expected = os.environ.get("INIT_SECRET")
    provided = request.args.get("secret", "")

    if not expected:
        return jsonify({"ok": False,
                        "error": "INIT_SECRET is not set on the server."}), 403
    if provided != expected:
        return jsonify({"ok": False, "error": "Forbidden."}), 403

    if _INIT_STATE["running"]:
        return jsonify({
            "ok": True,
            "message": "A fetch is already running. Check /admin/init-pokemon/status.",
            "status_url": "/admin/init-pokemon/status?secret=" + provided,
        })

    try:
        limit = int(request.args.get("limit", os.environ.get("POKEMON_LIMIT", 1025)))
    except ValueError:
        return jsonify({"ok": False, "error": "limit must be an integer."}), 400

    db.create_all()
    initial = _pokemon_count()

    _INIT_STATE.update({
        "running": True,
        "started_at": time.time(),
        "finished_at": None,
        "limit": limit,
        "initial_count": initial,
        "last_error": None,
    })

    app = current_app._get_current_object()
    t = threading.Thread(target=_run_init_in_thread, args=(app, limit), daemon=True)
    _INIT_STATE["thread"] = t
    t.start()

    return jsonify({
        "ok": True,
        "message": (
            f"Fetch started in the background for up to {limit} Pokémon. "
            f"{initial} already cached. Poll the status URL below."
        ),
        "initial_count": initial,
        "limit": limit,
        "status_url": "/admin/init-pokemon/status?secret=" + provided,
    })


@main_bp.route("/admin/init-pokemon/status")
def admin_init_pokemon_status():
    expected = os.environ.get("INIT_SECRET")
    provided = request.args.get("secret", "")

    if not expected or provided != expected:
        return jsonify({"ok": False, "error": "Forbidden."}), 403

    current = _pokemon_count()
    elapsed = None
    if _INIT_STATE["started_at"]:
        end = _INIT_STATE["finished_at"] or time.time()
        elapsed = round(end - _INIT_STATE["started_at"], 1)

    return jsonify({
        "ok": True,
        "running": _INIT_STATE["running"],
        "target_limit": _INIT_STATE["limit"],
        "initial_count": _INIT_STATE["initial_count"],
        "current_count": current,
        "elapsed_seconds": elapsed,
        "last_error": _INIT_STATE["last_error"],
        "percent_complete": (
            round(100.0 * current / _INIT_STATE["limit"], 1)
            if _INIT_STATE["limit"] else 0
        ),
    })
