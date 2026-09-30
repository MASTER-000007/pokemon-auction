"""Authoritative, in-memory game runtime.

Everything that matters (coins, teams, auctions, timers, state machine) lives
here.  The database is written alongside so a game can be reconstructed after a
process restart.
"""
import json
import math
import random
import threading
import time
from datetime import datetime

from app import db, socketio
from app.auction import (minimum_next_bid, quick_bid_amounts, starting_bid_for,
                         validate_bid)
from app.battle import analyse_team, run_tournament
from app.models import (Auction, Battle, BattleResult, Bid, Game, Player,
                        PlayerPokemon, Pokemon, Room, RoomPlayer)
from app.utils import (generate_room_code, generate_session_token, sanitize_chat,
                       sanitize_name, clamp)
from config import Config

STATES = ("LOBBY", "AUCTION", "RESULT", "BATTLE", "FINISHED")


# ======================================================================
# Runtime objects
# ======================================================================
class PlayerState:
    __slots__ = ("rp_id", "player_id", "name", "coins", "is_host", "connected",
                 "team", "is_kicked", "sids", "last_bid_at", "last_chat_at",
                 "joined_at")

    def __init__(self, rp_id, player_id, name, coins, is_host=False,
                 connected=True, team=None, is_kicked=False):
        self.rp_id = rp_id
        self.player_id = player_id
        self.name = name
        self.coins = coins
        self.is_host = is_host
        self.connected = connected
        self.team = list(team or [])
        self.is_kicked = is_kicked
        self.sids = set()
        self.last_bid_at = 0.0
        self.last_chat_at = 0.0
        self.joined_at = time.time()

    def public(self, team_size, show_coins):
        return {
            "id": self.rp_id,
            "name": self.name,
            "coins": self.coins if show_coins else None,
            "team": self.team,
            "team_size": len(self.team),
            "team_max": team_size,
            "completed": len(self.team) >= team_size,
            "connected": self.connected,
            "is_host": self.is_host,
        }


class AuctionState:
    def __init__(self, auction_id, pokemon, starting_bid, duration, ends_at=None):
        self.auction_id = auction_id
        self.pokemon = pokemon
        self.starting_bid = int(starting_bid)
        self.current_bid = 0
        self.current_bidder = None
        self.duration = int(duration)
        self.ends_at = ends_at if ends_at is not None else time.time() + self.duration
        self.bids = []            # list of {name, amount, ts}
        self.resolved = False
        self.extensions = 0

    @property
    def remaining(self):
        return max(0.0, self.ends_at - time.time())


class RoomRuntime:
    def __init__(self, code, room_id, settings, host_rp_id=None, state="LOBBY"):
        self.code = code
        self.room_id = room_id
        self.settings = settings
        self.host_rp_id = host_rp_id
        self.state = state

        self.players = {}          # rp_id -> PlayerState
        self.lock = threading.RLock()
        self.auction = None
        self.used_pokemon = set()
        self.recent_pokemon = []
        self.chat = []
        self.game_id = None
        self.leaderboard = []
        self.battle_log = []
        self.consecutive_unsold = 0
        self.auction_index = 0
        self.created_at = time.time()
        self.last_activity = time.time()
        self.timer_running = False

    # ------------------------------------------------------------------
    def touch(self):
        self.last_activity = time.time()

    def player_by_player_id(self, player_id):
        for p in self.players.values():
            if p.player_id == player_id:
                return p
        return None

    def active_players(self):
        return [p for p in self.players.values() if not p.is_kicked]

    def connected_players(self):
        return [p for p in self.players.values() if p.connected and not p.is_kicked]

    def team_size(self):
        return int(self.settings.get("team_size", Config.TEAM_SIZE))

    # ------------------------------------------------------------------
    def lobby_payload(self):
        return {
            "room": {
                "code": self.code,
                "state": self.state,
                "settings": self.settings,
                "host": self.host_rp_id,
                "min_players": Config.MIN_PLAYERS,
                "max_players": self.settings["max_players"],
            },
            "players": [p.public(self.team_size(), True)
                        for p in sorted(self.players.values(), key=lambda x: x.joined_at)
                        if not p.is_kicked],
            "server_time": time.time(),
        }

    def snapshot(self, rp_id):
        you = self.players.get(rp_id)
        show = bool(self.settings.get("show_balances", True))

        players = []
        for p in sorted(self.players.values(), key=lambda x: x.joined_at):
            if p.is_kicked:
                continue
            players.append(p.public(self.team_size(), show or p.rp_id == rp_id))

        data = {
            "room": {
                "code": self.code,
                "state": self.state,
                "settings": self.settings,
                "host": self.host_rp_id,
                "team_size": self.team_size(),
                "min_players": Config.MIN_PLAYERS,
                "max_players": self.settings["max_players"],
            },
            "players": players,
            "you": None,
            "server_time": time.time(),
        }

        if you:
            data["you"] = {
                "id": you.rp_id,
                "name": you.name,
                "coins": you.coins,
                "team": you.team,
                "is_host": you.is_host,
                "team_size": len(you.team),
                "completed": len(you.team) >= self.team_size(),
            }

        if self.auction:
            a = self.auction
            bidder = self.players.get(a.current_bidder) if a.current_bidder else None
            data["auction"] = {
                "id": a.auction_id,
                "index": self.auction_index,
                "pokemon": a.pokemon,
                "starting_bid": a.starting_bid,
                "current_bid": a.current_bid,
                "current_bidder": a.current_bidder,
                "current_bidder_name": bidder.name if bidder else None,
                "remaining": a.remaining,
                "duration": a.duration,
                "resolved": a.resolved,
                "bid_history": a.bids[-12:],
                "quick_bids": quick_bid_amounts(
                    a.current_bid, a.starting_bid,
                    you.coins if you else 0,
                    self.settings["min_bid_increment"],
                ) if you else {},
                "min_increment": self.settings["min_bid_increment"],
                "anti_snipe": bool(self.settings.get("anti_snipe_enabled")),
                "anti_snipe_seconds": self.settings.get("anti_snipe_seconds", 5),
            }

        return data


# ======================================================================
# Manager
# ======================================================================
class GameManager:
    def __init__(self):
        self.rooms = {}
        self.lock = threading.RLock()
        self.app = None
        self._pool = None
        self._janitor_started = False

    def init_app(self, app):
        self.app = app

    # ------------------------------------------------------------------
    # Room helpers
    # ------------------------------------------------------------------
    def get_room(self, code):
        if not code:
            return None
        return self.rooms.get(str(code).upper())

    def _load_pool(self):
        """Cache the full Pokémon table as dicts (loaded once per process)."""
        if self._pool is None:
            with self.app.app_context():
                rows = Pokemon.query.all()
                self._pool = [p.to_dict() for p in rows]
        return self._pool

    def invalidate_pool(self):
        self._pool = None

    # ------------------------------------------------------------------
    def normalize_settings(self, raw):
        raw = raw or {}
        max_players = clamp(int(raw.get("max_players", Config.MAX_PLAYERS)),
                            Config.MIN_PLAYERS, 8)
        team_size = clamp(int(raw.get("team_size", Config.TEAM_SIZE)), 1, 6)

        return {
            "starting_coins": clamp(int(raw.get("starting_coins", Config.STARTING_COINS)),
                                    100, 100000),
            "team_size": team_size,
            "max_players": max_players,
            "auction_duration": clamp(int(raw.get("auction_duration", Config.AUCTION_DURATION)),
                                      5, 180),
            "min_bid_increment": clamp(int(raw.get("min_bid_increment",
                                                   Config.MIN_BID_INCREMENT)), 1, 1000),
            "anti_snipe_enabled": bool(raw.get("anti_snipe_enabled",
                                               Config.ANTI_SNIPE_ENABLED)),
            "anti_snipe_seconds": clamp(int(raw.get("anti_snipe_seconds",
                                                    Config.ANTI_SNIPE_SECONDS)), 1, 30),
            "allow_duplicates": bool(raw.get("allow_duplicates", Config.ALLOW_DUPLICATES)),
            "allow_legendaries": bool(raw.get("allow_legendaries", Config.ALLOW_LEGENDARIES)),
            "allow_mythicals": bool(raw.get("allow_mythicals", Config.ALLOW_MYTHICALS)),
            "show_balances": bool(raw.get("show_balances", Config.SHOW_PLAYER_BALANCES)),
        }

    # ------------------------------------------------------------------
    # Create / join
    # ------------------------------------------------------------------
    def create_room(self, host_name, raw_settings=None):
        name = sanitize_name(host_name, Config.NAME_MAX_LENGTH)
        if not name:
            return None, "Please enter a valid name (letters and numbers)."

        settings = self.normalize_settings(raw_settings)

        with self.app.app_context():
            # unique code
            for _ in range(40):
                code = generate_room_code()
                if not Room.query.filter_by(code=code).first():
                    break
            else:                                  # pragma: no cover
                return None, "Could not allocate a room code. Try again."

            player = Player(name=name, session_token=generate_session_token())
            db.session.add(player)
            db.session.flush()

            room = Room(code=code, state="LOBBY", is_active=True)
            room.settings = settings
            db.session.add(room)
            db.session.flush()

            rp = RoomPlayer(room_id=room.id, player_id=player.id, name=name,
                            coins=settings["starting_coins"], is_host=True,
                            is_connected=True)
            db.session.add(rp)
            db.session.flush()

            room.host_rp_id = rp.id
            db.session.commit()

            rt = RoomRuntime(code, room.id, settings, host_rp_id=rp.id, state="LOBBY")
            rt.players[rp.id] = PlayerState(rp.id, player.id, name,
                                            settings["starting_coins"], is_host=True)

            with self.lock:
                self.rooms[code] = rt

            return {
                "code": code,
                "room_player_id": rp.id,
                "player_id": player.id,
                "session_token": player.session_token,
                "name": name,
            }, None

    # ------------------------------------------------------------------
    def join_room(self, code, name, existing_player_id=None):
        code = str(code or "").strip().upper()
        name = sanitize_name(name, Config.NAME_MAX_LENGTH)
        if not name:
            return None, "Please enter a valid name."

        rt = self.get_room(code)
        if rt is None:
            rt = self._load_room_from_db(code)
            if rt:
                with self.lock:
                    self.rooms[code] = rt

        if rt is None:
            return None, "That room does not exist."

        with rt.lock:
            if rt.state != "LOBBY":
                return None, "This game has already started."

            if existing_player_id:
                existing = rt.player_by_player_id(existing_player_id)
                if existing and not existing.is_kicked:
                    return {"code": code, "room_player_id": existing.rp_id,
                            "player_id": existing.player_id,
                            "name": existing.name, "rejoined": True}, None

            if len(rt.players) >= rt.settings["max_players"]:
                return None, "This room is full."

            if any(p.name.lower() == name.lower() for p in rt.players.values()
                   if not p.is_kicked):
                return None, "That name is already taken in this room."

            with self.app.app_context():
                player = Player(name=name, session_token=generate_session_token())
                db.session.add(player)
                db.session.flush()

                rp = RoomPlayer(room_id=rt.room_id, player_id=player.id, name=name,
                                coins=rt.settings["starting_coins"],
                                is_host=False, is_connected=True)
                db.session.add(rp)
                db.session.commit()

                rt.players[rp.id] = PlayerState(rp.id, player.id, name,
                                                rt.settings["starting_coins"])
                rt.touch()

                return {"code": code, "room_player_id": rp.id,
                        "player_id": player.id, "session_token": player.session_token,
                        "name": name}, None

    # ------------------------------------------------------------------
    def _load_room_from_db(self, code):
        """Rebuild runtime state after a process restart / cache eviction."""
        try:
            with self.app.app_context():
                room = Room.query.filter_by(code=code, is_active=True).first()
                if not room:
                    return None

                settings = self.normalize_settings(room.settings)
                rt = RoomRuntime(room.code, room.id, settings,
                                 host_rp_id=room.host_rp_id, state=room.state)

                for rp in room.room_players:
                    if rp.is_kicked:
                        continue
                    team = [pp.pokemon.to_dict() for pp in rp.pokemons if pp.pokemon]
                    ps = PlayerState(rp.id, rp.player_id, rp.name, rp.coins,
                                     is_host=(rp.id == room.host_rp_id),
                                     connected=False, team=team)
                    rt.players[rp.id] = ps

                rows = Auction.query.filter_by(room_id=room.id).all()
                rt.used_pokemon = {r.pokemon_id for r in rows}
                rt.auction_index = len(rows)

                if room.state in ("AUCTION", "RESULT"):
                    active = (Auction.query
                              .filter_by(room_id=room.id, status="active")
                              .order_by(Auction.id.desc()).first())
                    if active:
                        pk = db.session.get(Pokemon, active.pokemon_id)
                        if pk:
                            a = AuctionState(active.id, pk.to_dict(),
                                             active.starting_bid,
                                             settings["auction_duration"],
                                             ends_at=active.ends_at or
                                             (time.time() + settings["auction_duration"]))
                            a.current_bid = active.current_bid or 0
                            a.current_bidder = active.current_bidder_id
                            rt.auction = a

                game = (Game.query.filter_by(room_id=room.id)
                        .order_by(Game.id.desc()).first())
                if game:
                    rt.game_id = game.id
                    rt.leaderboard = game.leaderboard

                return rt
        except Exception as exc:                   # pragma: no cover
            if self.app:
                self.app.logger.warning("Could not restore room %s: %s", code, exc)
            return None

    # ------------------------------------------------------------------
    # Connecting / disconnecting
    # ------------------------------------------------------------------
    def attach_socket(self, code, rp_id, sid):
        rt = self.get_room(code)
        if not rt:
            return None
        with rt.lock:
            p = rt.players.get(rp_id)
            if not p or p.is_kicked:
                return None
            was_offline = not p.connected
            p.sids.add(sid)
            p.connected = True
            rt.touch()
            self._persist_connection(rt, rp_id, True)
        if was_offline:
            self.broadcast(rt, "player_joined",
                           {"player": p.public(rt.team_size(), True),
                            "reconnected": True})
        return p

    def detach_socket(self, code, sid):
        rt = self.get_room(code)
        if not rt:
            return None
        with rt.lock:
            for p in rt.players.values():
                if sid in p.sids:
                    p.sids.discard(sid)
                    if not p.sids:
                        p.connected = False
                        self._persist_connection(rt, p.rp_id, False)
                        self.broadcast(rt, "player_left",
                                       {"id": p.rp_id, "name": p.name})
                        self._schedule_host_check(rt)
                    return p
        return None

    def _persist_connection(self, rt, rp_id, connected):
        try:
            with self.app.app_context():
                rp = db.session.get(RoomPlayer, rp_id)
                if rp:
                    rp.is_connected = connected
                    db.session.commit()
        except Exception:                          # pragma: no cover
            pass

    def _schedule_host_check(self, rt):
        def worker():
            time.sleep(Config.HOST_TRANSFER_GRACE)
            self.maybe_transfer_host(rt.code)

        socketio.start_background_task(worker)

    def maybe_transfer_host(self, code):
        rt = self.get_room(code)
        if not rt or rt.state == "FINISHED":
            return
        with rt.lock:
            host = rt.players.get(rt.host_rp_id)
            if host and host.connected and not host.is_kicked:
                return
            candidates = sorted(rt.connected_players(), key=lambda p: p.joined_at)
            if not candidates:
                return
            new_host = candidates[0]
            if host:
                host.is_host = False
            new_host.is_host = True
            rt.host_rp_id = new_host.rp_id
            self._persist_host(rt)

        self.broadcast(rt, "host_changed",
                       {"host": new_host.rp_id, "name": new_host.name})

    def _persist_host(self, rt):
        try:
            with self.app.app_context():
                room = db.session.get(Room, rt.room_id)
                if room:
                    room.host_rp_id = rt.host_rp_id
                for rp in RoomPlayer.query.filter_by(room_id=rt.room_id).all():
                    rp.is_host = (rp.id == rt.host_rp_id)
                db.session.commit()
        except Exception:                          # pragma: no cover
            db.session.rollback()

    # ------------------------------------------------------------------
    # Broadcasting
    # ------------------------------------------------------------------
    def broadcast(self, rt, event, payload):
        """Broadcast a *room-agnostic* event to every client in the room."""
        try:
            socketio.emit(event, payload, to=rt.code)
        except Exception:                          # pragma: no cover
            pass

    def broadcast_snapshot(self, rt):
        """Send each connected player their OWN personalised snapshot.

        Critical: `state_sync` carries per-player data (`you`), so it must be
        delivered with `to=sid` (a socket's private room) — never with
        `to=rt.code`, or the last player's snapshot overwrites everyone else's.
        """
        for rp_id, p in list(rt.players.items()):
            if p.sids:
                self.emit_snapshot(rt, rp_id)

    def emit_snapshot(self, rt, rp_id):
        p = rt.players.get(rp_id)
        if not p or not p.sids:
            return
        data = rt.snapshot(rp_id)
        for sid in list(p.sids):
            try:
                socketio.emit("state_sync", data, to=sid)
            except Exception:                      # pragma: no cover
                pass

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------
    def update_settings(self, code, rp_id, raw_settings):
        rt = self.get_room(code)
        if not rt:
            return False, "Room not found."
        with rt.lock:
            p = rt.players.get(rp_id)
            if not p or not p.is_host:
                return False, "Only the host can change settings."
            if rt.state != "LOBBY":
                return False, "Settings are locked once the game starts."
            rt.settings = self.normalize_settings({**rt.settings, **(raw_settings or {})})
            settings = rt.settings
            self._persist_settings(rt)
        self.broadcast_snapshot(rt)
        self.broadcast(rt, "settings_updated", {"settings": settings})
        return True, None

    def _persist_settings(self, rt):
        try:
            with self.app.app_context():
                room = db.session.get(Room, rt.room_id)
                if room:
                    room.settings = rt.settings
                    db.session.commit()
        except Exception:                          # pragma: no cover
            db.session.rollback()

    # ------------------------------------------------------------------
    # Kick / end
    # ------------------------------------------------------------------
    def kick_player(self, code, host_rp_id, target_rp_id):
        rt = self.get_room(code)
        if not rt:
            return False, "Room not found."
        with rt.lock:
            host = rt.players.get(host_rp_id)
            if not host or not host.is_host:
                return False, "Only the host can kick players."
            if target_rp_id == host_rp_id:
                return False, "You cannot kick yourself."
            target = rt.players.get(target_rp_id)
            if not target:
                return False, "Player not found."
            target.is_kicked = True
            rt.players.pop(target_rp_id, None)
        self._persist_kick(target_rp_id)
        self.broadcast(rt, "player_kicked", {"id": target_rp_id, "name": target.name})
        self.broadcast(rt, "player_left", {"id": target_rp_id, "name": target.name})
        self.broadcast_snapshot(rt)
        return True, None

    def _persist_kick(self, rp_id):
        try:
            with self.app.app_context():
                rp = db.session.get(RoomPlayer, rp_id)
                if rp:
                    rp.is_kicked = True
                    rp.is_connected = False
                    db.session.commit()
        except Exception:                          # pragma: no cover
            db.session.rollback()

    def end_room(self, code, rp_id):
        rt = self.get_room(code)
        if not rt:
            return False, "Room not found."
        with rt.lock:
            p = rt.players.get(rp_id)
            if not p or not p.is_host:
                return False, "Only the host can close the room."
            rt.state = "FINISHED"
        self.broadcast(rt, "room_closed", {"reason": "Host ended the room."})
        self._persist_room_state(rt)
        with self.lock:
            self.rooms.pop(code, None)
        return True, None

    def _persist_room_state(self, rt):
        try:
            with self.app.app_context():
                room = db.session.get(Room, rt.room_id)
                if room:
                    room.state = rt.state
                    if rt.state == "FINISHED":
                        room.is_active = False
                    db.session.commit()
        except Exception:                          # pragma: no cover
            db.session.rollback()

    # ------------------------------------------------------------------
    # Chat
    # ------------------------------------------------------------------
    def add_chat(self, code, rp_id, text):
        rt = self.get_room(code)
        if not rt:
            return False, "Room not found."
        with rt.lock:
            p = rt.players.get(rp_id)
            if not p or p.is_kicked:
                return False, "You are not in this room."
            now = time.time()
            if now - p.last_chat_at < Config.CHAT_RATE_LIMIT_SECONDS:
                return False, "Slow down a little."
            clean = sanitize_chat(text, Config.CHAT_MAX_LENGTH)
            if not clean:
                return False, "Empty message."
            p.last_chat_at = now
            message = {
                "name": p.name,
                "id": p.rp_id,
                "text": clean,
                "ts": now,
                "system": False,
            }
            rt.chat.append(message)
            rt.chat = rt.chat[-Config.CHAT_HISTORY:]
        self.broadcast(rt, "chat_message", message)
        return True, None

    def system_chat(self, rt, text):
        message = {"name": "System", "id": 0, "text": text,
                   "ts": time.time(), "system": True}
        with rt.lock:
            rt.chat.append(message)
            rt.chat = rt.chat[-Config.CHAT_HISTORY:]
        self.broadcast(rt, "chat_message", message)

    # ------------------------------------------------------------------
    # Game start
    # ------------------------------------------------------------------
    def start_game(self, code, rp_id):
        rt = self.get_room(code)
        if not rt:
            return False, "Room not found."
        with rt.lock:
            p = rt.players.get(rp_id)
            if not p or not p.is_host:
                return False, "Only the host can start the game."
            if rt.state != "LOBBY":
                return False, "The game has already started."
            active = rt.active_players()
            if len(active) < Config.MIN_PLAYERS:
                return False, f"Need at least {Config.MIN_PLAYERS} players."

            pool = self._load_pool()
            if not pool:
                return False, ("Pokémon database is empty. Run "
                               "`python init_pokemon.py` first.")

            rt.state = "AUCTION"
            rt.auction_index = 0
            rt.consecutive_unsold = 0
            for player in active:
                player.team = []
                player.coins = rt.settings["starting_coins"]

        with self.app.app_context():
            game = Game(room_id=rt.room_id, state="AUCTION")
            db.session.add(game)
            db.session.commit()
            rt.game_id = game.id
            self._reset_players_in_db(rt)

        self._persist_room_state(rt)
        self.broadcast(rt, "game_started", {"state": "AUCTION"})
        self.broadcast_snapshot(rt)
        self.system_chat(rt, "The auction has begun! Good luck.")

        socketio.start_background_task(self._start_next_auction, rt, 2.0)
        return True, None

    def _reset_players_in_db(self, rt):
        try:
            for rp in RoomPlayer.query.filter_by(room_id=rt.room_id).all():
                rp.coins = rt.settings["starting_coins"]
                PlayerPokemon.query.filter_by(room_player_id=rp.id).delete()
            db.session.commit()
        except Exception:                          # pragma: no cover
            db.session.rollback()

    # ------------------------------------------------------------------
    # Auction loop
    # ------------------------------------------------------------------
    def _pick_pokemon(self, rt, max_coins=None):
        """Pick a random eligible Pokémon.

        When ``max_coins`` is provided, only Pokémon whose starting bid is
        affordable by at least one incomplete-team player are considered.
        Returns ``None`` when nothing can be auctioned.
        """
        pool = self._load_pool()
        if not pool:
            return None

        allow_dup = rt.settings.get("allow_duplicates", False)
        allow_leg = rt.settings.get("allow_legendaries", True)
        allow_myth = rt.settings.get("allow_mythicals", True)

        def _eligible(poke):
            if poke.get("is_legendary") and not allow_leg:
                return False
            if poke.get("is_mythical") and not allow_myth:
                return False
            if not allow_dup and poke["id"] in rt.used_pokemon:
                return False
            return True

        # Pass 1 — not recently seen
        candidates = [p for p in pool
                      if _eligible(p) and p["id"] not in rt.recent_pokemon]

        # Pass 2 — if duplicates are allowed, relax the "recent" filter
        if not candidates and allow_dup:
            candidates = [p for p in pool if _eligible(p)]

        if not candidates:
            return None

        # Filter by affordability when asked
        if max_coins is not None:
            affordable = [p for p in candidates
                          if starting_bid_for(p) <= max_coins]
            if not affordable:
                return None
            candidates = affordable

        return random.choice(candidates)

    def _start_next_auction(self, rt, delay=0.0):
        if delay:
            time.sleep(delay)

        with rt.lock:
            if rt.state != "AUCTION":
                return

            active = rt.active_players()
            if not active:
                return

            team_size = rt.team_size()
            incomplete = [p for p in active if len(p.team) < team_size]

            # Case 1 — everyone is full or the unsold limit has tripped.
            if not incomplete or rt.consecutive_unsold >= Config.MAX_CONSECUTIVE_UNSOLD:
                self._finish_auction_phase(rt)
                return

            # Case 2 — nobody who still needs a Pokémon can afford anything.
            max_coins = max(p.coins for p in incomplete)
            pokemon = self._pick_pokemon(rt, max_coins=max_coins)

            if not pokemon:
                if max_coins < Config.VALUE_MIN_STARTING_BID:
                    self.system_chat(
                        rt,
                        "No player can afford the minimum bid — ending the auction.",
                    )
                else:
                    self.system_chat(
                        rt,
                        "No more Pokémon can be auctioned — ending the auction.",
                    )
                self._finish_auction_phase(rt)
                return

            rt.used_pokemon.add(pokemon["id"])
            rt.recent_pokemon.append(pokemon["id"])
            rt.recent_pokemon = rt.recent_pokemon[-12:]
            rt.auction_index += 1

            starting = starting_bid_for(pokemon)
            auction_state = AuctionState(0, pokemon, starting,
                                         rt.settings["auction_duration"])

        # ---- persist ------------------------------------------------
        try:
            with self.app.app_context():
                row = Auction(
                    room_id=rt.room_id,
                    game_id=rt.game_id,
                    index=rt.auction_index,
                    pokemon_id=pokemon["id"],
                    starting_bid=starting,
                    current_bid=0,
                    status="active",
                    ends_at=auction_state.ends_at,
                )
                db.session.add(row)
                db.session.commit()
                auction_state.auction_id = row.id
        except Exception:                          # pragma: no cover
            db.session.rollback()

        with rt.lock:
            rt.auction = auction_state
            rt.consecutive_unsold = 0

        self.broadcast(rt, "auction_started", {
            "auction": {
                "id": auction_state.auction_id,
                "index": rt.auction_index,
                "pokemon": pokemon,
                "starting_bid": starting,
                "current_bid": 0,
                "current_bidder": None,
                "current_bidder_name": None,
                "duration": auction_state.duration,
                "remaining": auction_state.duration,
                "min_increment": rt.settings["min_bid_increment"],
                "anti_snipe": bool(rt.settings.get("anti_snipe_enabled")),
                "anti_snipe_seconds": rt.settings.get("anti_snipe_seconds", 5),
            }
        })
        self.broadcast_snapshot(rt)
        self._start_auction_timer(rt, auction_state.auction_id)

    def _start_auction_timer(self, rt, auction_id):
        def loop():
            last_broadcast = None
            while True:
                time.sleep(0.5)
                with rt.lock:
                    a = rt.auction
                    if not a or a.auction_id != auction_id or a.resolved:
                        return
                    if rt.state != "AUCTION":
                        return
                    remaining = a.remaining

                if remaining <= 0:
                    self._resolve_auction(rt, auction_id)
                    return

                seconds = int(math.ceil(remaining))
                if seconds != last_broadcast:
                    last_broadcast = seconds
                    self.broadcast(rt, "auction_tick",
                                   {"id": auction_id, "remaining": seconds})

        socketio.start_background_task(loop)

    # ------------------------------------------------------------------
    # Bidding
    # ------------------------------------------------------------------
    def place_bid(self, code, rp_id, amount):
        rt = self.get_room(code)
        if not rt:
            return False, "Room not found.", None

        with rt.lock:
            if rt.state != "AUCTION":
                return False, "The auction is not active.", None

            auction = rt.auction
            if not auction or auction.resolved:
                return False, "There is no active auction.", None

            player = rt.players.get(rp_id)
            if not player or player.is_kicked:
                return False, "You are not in this room.", None

            if len(player.team) >= rt.team_size():
                return False, "Your team is already complete.", None

            if time.time() >= auction.ends_at:
                return False, "The auction has already ended.", None

            now = time.time()
            if now - player.last_bid_at < Config.BID_RATE_LIMIT_SECONDS:
                return False, "You are bidding too quickly.", None

            if auction.current_bidder == rp_id:
                return False, "You already hold the highest bid.", None

            ok, error, value = validate_bid(
                amount, player.coins, auction.current_bid,
                auction.starting_bid, rt.settings["min_bid_increment"],
            )
            if not ok:
                return False, error, None

            # ---- anti-snipe -----------------------------------------
            extended = False
            remaining = auction.ends_at - now
            anti_snipe = rt.settings.get("anti_snipe_enabled", True)
            anti_seconds = rt.settings.get("anti_snipe_seconds", 5)
            if anti_snipe and remaining <= anti_seconds:
                auction.ends_at = now + anti_seconds
                auction.extensions += 1
                extended = True

            auction.current_bid = value
            auction.current_bidder = rp_id
            auction.bids.append({
                "name": player.name,
                "id": rp_id,
                "amount": value,
                "ts": now,
            })
            auction.bids = auction.bids[-40:]
            player.last_bid_at = now
            rt.touch()

            auction_id = auction.auction_id
            ends_at = auction.ends_at
            quick = quick_bid_amounts(value, auction.starting_bid, player.coins,
                                      rt.settings["min_bid_increment"])

        # ---- persist the bid -----------------------------------------
        try:
            with self.app.app_context():
                row = db.session.get(Auction, auction_id)
                if row:
                    row.current_bid = value
                    row.current_bidder_id = rp_id
                    row.ends_at = ends_at
                    db.session.add(Bid(auction_id=auction_id,
                                       room_player_id=rp_id, amount=value))
                    db.session.commit()
        except Exception:                          # pragma: no cover
            db.session.rollback()

        self.broadcast(rt, "bid_placed", {
            "id": auction_id,
            "bidder": rp_id,
            "bidder_name": player.name,
            "amount": value,
            "current_bid": value,
            "current_bidder": rp_id,
            "remaining": max(0.0, ends_at - time.time()),
            "min_increment": rt.settings["min_bid_increment"],
        })

        if extended:
            self.broadcast(rt, "auction_extended", {
                "id": auction_id,
                "remaining": anti_seconds,
                "reason": "Anti-snipe protection",
            })

        return True, None, {
            "amount": value,
            "coins": player.coins,
            "quick_bids": quick,
        }

    # ------------------------------------------------------------------
    # Resolve
    # ------------------------------------------------------------------
    def _resolve_auction(self, rt, auction_id):
        with rt.lock:
            auction = rt.auction
            if not auction or auction.auction_id != auction_id or auction.resolved:
                return
            auction.resolved = True

            winner = rt.players.get(auction.current_bidder) if auction.current_bidder else None
            price = auction.current_bid

            if (winner is None or price <= 0 or winner.coins < price
                    or len(winner.team) >= rt.team_size()):
                winner, price = None, 0
                rt.consecutive_unsold += 1
            else:
                winner.coins -= price
                winner.team.append(auction.pokemon)
                rt.consecutive_unsold = 0

            pokemon = auction.pokemon

        # ---- persist result -----------------------------------------
        try:
            with self.app.app_context():
                row = db.session.get(Auction, auction_id)
                if row:
                    row.current_bid = price
                    row.final_price = price
                    row.winner_id = winner.rp_id if winner else None
                    row.status = "sold" if winner else "unsold"
                    row.ended_at = datetime.utcnow()
                    if winner:
                        rp = db.session.get(RoomPlayer, winner.rp_id)
                        if rp:
                            rp.coins = winner.coins
                        db.session.add(PlayerPokemon(
                            room_player_id=winner.rp_id,
                            pokemon_id=pokemon["id"],
                            price=price,
                        ))
                    db.session.commit()
        except Exception:                          # pragma: no cover
            db.session.rollback()

        self.broadcast(rt, "auction_ended", {
            "id": auction_id,
            "pokemon": pokemon,
            "winner": winner.rp_id if winner else None,
            "winner_name": winner.name if winner else None,
            "price": price,
            "sold": winner is not None,
            "state": "RESULT",
        })

        if winner:
            self.broadcast(rt, "pokemon_won", {
                "player": winner.rp_id,
                "player_name": winner.name,
                "pokemon": pokemon,
                "price": price,
                "coins": winner.coins,
                "team_size": len(winner.team),
            })
            self.system_chat(rt, f"{winner.name} won {pokemon['name']} for {price} coins!")
        else:
            self.system_chat(rt, f"No bids for {pokemon['name']} — moving on.")

        self.broadcast(rt, "player_team_updated", {})
        self.broadcast_snapshot(rt)

        with rt.lock:
            rt.state = "RESULT" if rt.state == "AUCTION" else rt.state
        self._persist_room_state(rt)

        socketio.start_background_task(self._resume_after_result, rt)

    def _resume_after_result(self, rt):
        time.sleep(3.5)
        with rt.lock:
            if rt.state != "RESULT":
                return
            active = rt.active_players()
            team_size = rt.team_size()
            complete = all(len(p.team) >= team_size for p in active)
            stuck = rt.consecutive_unsold >= Config.MAX_CONSECUTIVE_UNSOLD

            if complete or stuck or not active:
                self._finish_auction_phase(rt)
                return

            rt.state = "AUCTION"

        self._persist_room_state(rt)
        self.broadcast(rt, "state_changed", {"state": "AUCTION"})
        self._start_next_auction(rt, 0.5)

    # ------------------------------------------------------------------
    # Auction phase finished -> battles
    # ------------------------------------------------------------------
    def _finish_auction_phase(self, rt):
        with rt.lock:
            if rt.state in ("BATTLE", "FINISHED"):
                return
            rt.state = "BATTLE"
            rt.auction = None

        self._persist_room_state(rt)
        self.broadcast(rt, "auction_complete", {"state": "BATTLE"})
        self.system_chat(rt, "Auction complete — running team battles…")
        self.broadcast_snapshot(rt)

        socketio.start_background_task(self._run_battles, rt)

    def _run_battles(self, rt):
        time.sleep(2.0)

        with rt.lock:
            participants = []
            for p in sorted(rt.active_players(), key=lambda x: x.joined_at):
                if p.team:
                    participants.append({"id": p.rp_id, "name": p.name,
                                         "team": p.team})

        if len(participants) < 2:
            with rt.lock:
                rt.leaderboard = [
                    {"rank": 1, "id": p["id"], "name": p["name"], "points": 0,
                     "team": p["team"], "matchup_wins": 0, "matchup_losses": 0,
                     "matchup_draws": 0, "hp_left": 0, "synergy": 0, "bst": 0,
                     "battles_won": 0, "battles_lost": 0}
                    for p in participants
                ]
                rt.state = "FINISHED"
            self._persist_final(rt, [])
            self.broadcast(rt, "game_finished", {"leaderboard": rt.leaderboard})
            return

        leaderboard, battles = run_tournament(participants)

        with rt.lock:
            rt.leaderboard = [
                {k: v for k, v in row.items() if k != "team"} | {"team": row["team"]}
                for row in leaderboard
            ]
            rt.state = "FINISHED"

        self._persist_battles(rt, battles, leaderboard)
        self._persist_final(rt, leaderboard)

        self.broadcast(rt, "game_finished", {
            "leaderboard": rt.leaderboard,
            "battle_count": len(battles),
        })
        self.broadcast_snapshot(rt)

    def _persist_battles(self, rt, battles, leaderboard):
        try:
            with self.app.app_context():
                game = db.session.get(Game, rt.game_id) if rt.game_id else None
                if not game:
                    return
                game.state = "FINISHED"
                game.finished_at = datetime.utcnow()

                for battle in battles:
                    res = battle["result"]
                    row = Battle(
                        game_id=game.id,
                        player_a_id=battle["player_a"],
                        player_b_id=battle["player_b"],
                        name_a=battle["name_a"],
                        name_b=battle["name_b"],
                        wins_a=res["wins_a"],
                        wins_b=res["wins_b"],
                        draws=res["draws"],
                        winner_id=battle["winner_id"],
                        hp_a_pct=res["hp_a_pct"],
                        hp_b_pct=res["hp_b_pct"],
                        tiebreak=res["tiebreak"],
                    )
                    row.details = {
                        "synergy_a": res["synergy_a"],
                        "synergy_b": res["synergy_b"],
                        "name_a": res["name_a"],
                        "name_b": res["name_b"],
                    }
                    db.session.add(row)
                    db.session.flush()

                    for slot in res["slots"]:
                        br = BattleResult(
                            battle_id=row.id,
                            slot=slot["slot"],
                            pokemon_a_id=slot["a"]["id"],
                            pokemon_b_id=slot["b"]["id"],
                            name_a=slot["a"]["name"],
                            name_b=slot["b"]["name"],
                            winner=slot["winner"],
                            turns=slot["turns"],
                            hp_a_pct=slot["a"]["hp_pct"],
                            hp_b_pct=slot["b"]["hp_pct"],
                        )
                        br.log = slot["log"]
                        db.session.add(br)

                db.session.commit()
        except Exception as exc:                   # pragma: no cover
            db.session.rollback()
            if self.app:
                self.app.logger.warning("Could not persist battles: %s", exc)

    def _persist_final(self, rt, leaderboard):
        try:
            with self.app.app_context():
                game = db.session.get(Game, rt.game_id) if rt.game_id else None
                if game:
                    game.state = "FINISHED"
                    game.finished_at = game.finished_at or datetime.utcnow()
                    game.leaderboard = [
                        {k: v for k, v in row.items() if k != "team"}
                        for row in (leaderboard or rt.leaderboard)
                    ]
                room = db.session.get(Room, rt.room_id)
                if room:
                    room.state = "FINISHED"
                    room.is_active = False
                db.session.commit()
        except Exception:                          # pragma: no cover
            db.session.rollback()

    # ------------------------------------------------------------------
    # Read helpers for HTTP routes
    # ------------------------------------------------------------------
    def room_public_state(self, code):
        rt = self.get_room(code)
        if rt:
            with rt.lock:
                return rt.lobby_payload()
        return None

    def room_full_snapshot(self, code, rp_id):
        rt = self.get_room(code) or self._load_room_from_db(code)
        if not rt:
            return None
        with rt.lock:
            return rt.snapshot(rp_id)

    # ------------------------------------------------------------------
    # Janitor
    # ------------------------------------------------------------------
    def start_janitor(self):
        if self._janitor_started or not self.app:
            return
        self._janitor_started = True

        def loop():
            while True:
                time.sleep(300)
                now = time.time()
                with self.lock:
                    stale = [code for code, rt in self.rooms.items()
                             if now - rt.last_activity > Config.ROOM_IDLE_TIMEOUT]
                    for code in stale:
                        self.rooms.pop(code, None)

        socketio.start_background_task(loop)


manager = GameManager()