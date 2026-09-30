"""HTTP routes — pages plus a small JSON API."""
import json

from flask import (Blueprint, abort, current_app, jsonify, redirect,
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
    except Exception:                              # pragma: no cover
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
        }
        # strip None so normalize_settings falls back to defaults
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
            battles.append({
                "name_a": b.name_a,
                "name_b": b.name_b,
                "wins_a": b.wins_a,
                "wins_b": b.wins_b,
                "draws": b.draws,
                "winner_id": b.winner_id,
                "hp_a_pct": b.hp_a_pct,
                "hp_b_pct": b.hp_b_pct,
                "tiebreak": b.tiebreak,
                "slots": [{
                    "slot": r.slot,
                    "name_a": r.name_a,
                    "name_b": r.name_b,
                    "pokemon_a_id": r.pokemon_a_id,
                    "pokemon_b_id": r.pokemon_b_id,
                    "winner": r.winner,
                    "turns": r.turns,
                    "hp_a_pct": r.hp_a_pct,
                    "hp_b_pct": r.hp_b_pct,
                    "log": r.log,
                } for r in b.results],
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