"""SQLAlchemy models — enough information to reconstruct any game state."""
import json
from datetime import datetime

from app import db


def _loads(raw, default):
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


class Player(db.Model):
    __tablename__ = "players"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(32), nullable=False)
    session_token = db.Column(db.String(80), unique=True, index=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    room_players = db.relationship("RoomPlayer", back_populates="player",
                                   cascade="all, delete-orphan")

    def to_dict(self):
        return {"id": self.id, "name": self.name}


class Room(db.Model):
    __tablename__ = "rooms"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(12), unique=True, index=True, nullable=False)
    state = db.Column(db.String(16), default="LOBBY", nullable=False)
    settings_json = db.Column(db.Text, default="{}", nullable=False)
    host_rp_id = db.Column(db.Integer, nullable=True)      # RoomPlayer.id
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow,
                           onupdate=datetime.utcnow, nullable=False)

    room_players = db.relationship("RoomPlayer", back_populates="room",
                                   cascade="all, delete-orphan",
                                   order_by="RoomPlayer.id")
    auctions = db.relationship("Auction", back_populates="room",
                               cascade="all, delete-orphan")
    games = db.relationship("Game", back_populates="room",
                            cascade="all, delete-orphan")

    @property
    def settings(self):
        return _loads(self.settings_json, {})

    @settings.setter
    def settings(self, value):
        self.settings_json = json.dumps(value)


class RoomPlayer(db.Model):
    __tablename__ = "room_players"

    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey("rooms.id"), nullable=False, index=True)
    player_id = db.Column(db.Integer, db.ForeignKey("players.id"), nullable=False, index=True)
    name = db.Column(db.String(32), nullable=False)
    coins = db.Column(db.Integer, default=0, nullable=False)
    is_host = db.Column(db.Boolean, default=False, nullable=False)
    is_connected = db.Column(db.Boolean, default=True, nullable=False)
    is_kicked = db.Column(db.Boolean, default=False, nullable=False)
    joined_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    room = db.relationship("Room", back_populates="room_players")
    player = db.relationship("Player", back_populates="room_players")
    pokemons = db.relationship("PlayerPokemon", back_populates="room_player",
                               cascade="all, delete-orphan", order_by="PlayerPokemon.id")

    __table_args__ = (db.UniqueConstraint("room_id", "player_id", name="uq_room_player"),)


class Pokemon(db.Model):
    __tablename__ = "pokemon"

    id = db.Column(db.Integer, primary_key=True)          # national dex id
    name = db.Column(db.String(64), nullable=False, index=True)
    types_json = db.Column(db.Text, default="[]", nullable=False)
    hp = db.Column(db.Integer, default=1, nullable=False)
    attack = db.Column(db.Integer, default=1, nullable=False)
    defense = db.Column(db.Integer, default=1, nullable=False)
    sp_attack = db.Column(db.Integer, default=1, nullable=False)
    sp_defense = db.Column(db.Integer, default=1, nullable=False)
    speed = db.Column(db.Integer, default=1, nullable=False)
    bst = db.Column(db.Integer, default=0, nullable=False, index=True)
    sprite_url = db.Column(db.String(255))
    artwork_url = db.Column(db.String(255))
    abilities_json = db.Column(db.Text, default="[]", nullable=False)
    generation = db.Column(db.String(32))
    is_legendary = db.Column(db.Boolean, default=False, nullable=False, index=True)
    is_mythical = db.Column(db.Boolean, default=False, nullable=False, index=True)
    auction_value = db.Column(db.Integer, default=20, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    @property
    def types(self):
        return _loads(self.types_json, [])

    @types.setter
    def types(self, value):
        self.types_json = json.dumps(value)

    @property
    def abilities(self):
        return _loads(self.abilities_json, [])

    @abilities.setter
    def abilities(self, value):
        self.abilities_json = json.dumps(value)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "types": self.types,
            "hp": self.hp,
            "attack": self.attack,
            "defense": self.defense,
            "sp_attack": self.sp_attack,
            "sp_defense": self.sp_defense,
            "speed": self.speed,
            "bst": self.bst,
            "sprite": self.sprite_url,
            "artwork": self.artwork_url or self.sprite_url,
            "abilities": self.abilities,
            "generation": self.generation,
            "is_legendary": self.is_legendary,
            "is_mythical": self.is_mythical,
            "auction_value": self.auction_value,
        }


class PlayerPokemon(db.Model):
    __tablename__ = "player_pokemon"

    id = db.Column(db.Integer, primary_key=True)
    room_player_id = db.Column(db.Integer, db.ForeignKey("room_players.id"),
                               nullable=False, index=True)
    pokemon_id = db.Column(db.Integer, db.ForeignKey("pokemon.id"),
                           nullable=False, index=True)
    price = db.Column(db.Integer, default=0, nullable=False)
    won_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    room_player = db.relationship("RoomPlayer", back_populates="pokemons")
    pokemon = db.relationship("Pokemon")


class Game(db.Model):
    __tablename__ = "games"

    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey("rooms.id"), nullable=False, index=True)
    state = db.Column(db.String(16), default="AUCTION", nullable=False)
    leaderboard_json = db.Column(db.Text, default="[]", nullable=False)
    started_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    finished_at = db.Column(db.DateTime)

    room = db.relationship("Room", back_populates="games")
    battles = db.relationship("Battle", back_populates="game",
                              cascade="all, delete-orphan", order_by="Battle.id")

    @property
    def leaderboard(self):
        return _loads(self.leaderboard_json, [])

    @leaderboard.setter
    def leaderboard(self, value):
        self.leaderboard_json = json.dumps(value)


class Auction(db.Model):
    __tablename__ = "auctions"

    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey("rooms.id"), nullable=False, index=True)
    game_id = db.Column(db.Integer, db.ForeignKey("games.id"), nullable=True, index=True)
    index = db.Column(db.Integer, default=0, nullable=False)
    pokemon_id = db.Column(db.Integer, db.ForeignKey("pokemon.id"), nullable=False)
    starting_bid = db.Column(db.Integer, default=0, nullable=False)
    current_bid = db.Column(db.Integer, default=0, nullable=False)
    current_bidder_id = db.Column(db.Integer, db.ForeignKey("room_players.id"), nullable=True)
    winner_id = db.Column(db.Integer, db.ForeignKey("room_players.id"), nullable=True)
    final_price = db.Column(db.Integer, default=0, nullable=False)
    status = db.Column(db.String(16), default="active", nullable=False, index=True)
    started_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    ends_at = db.Column(db.Float, default=0.0, nullable=False)
    ended_at = db.Column(db.DateTime)

    room = db.relationship("Room", back_populates="auctions")
    pokemon = db.relationship("Pokemon")
    bids = db.relationship("Bid", back_populates="auction",
                           cascade="all, delete-orphan", order_by="Bid.id")


class Bid(db.Model):
    __tablename__ = "bids"

    id = db.Column(db.Integer, primary_key=True)
    auction_id = db.Column(db.Integer, db.ForeignKey("auctions.id"),
                           nullable=False, index=True)
    room_player_id = db.Column(db.Integer, db.ForeignKey("room_players.id"),
                               nullable=False, index=True)
    amount = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    auction = db.relationship("Auction", back_populates="bids")
    room_player = db.relationship("RoomPlayer")


class Battle(db.Model):
    __tablename__ = "battles"

    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey("games.id"), nullable=False, index=True)
    player_a_id = db.Column(db.Integer, db.ForeignKey("room_players.id"), nullable=False)
    player_b_id = db.Column(db.Integer, db.ForeignKey("room_players.id"), nullable=False)
    name_a = db.Column(db.String(32), nullable=False)
    name_b = db.Column(db.String(32), nullable=False)
    wins_a = db.Column(db.Integer, default=0, nullable=False)
    wins_b = db.Column(db.Integer, default=0, nullable=False)
    draws = db.Column(db.Integer, default=0, nullable=False)
    winner_id = db.Column(db.Integer, nullable=True)
    hp_a_pct = db.Column(db.Float, default=0.0, nullable=False)
    hp_b_pct = db.Column(db.Float, default=0.0, nullable=False)
    tiebreak = db.Column(db.String(64))
    details_json = db.Column(db.Text, default="{}", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    game = db.relationship("Game", back_populates="battles")
    results = db.relationship("BattleResult", back_populates="battle",
                              cascade="all, delete-orphan", order_by="BattleResult.id")

    @property
    def details(self):
        return _loads(self.details_json, {})

    @details.setter
    def details(self, value):
        self.details_json = json.dumps(value)


class BattleResult(db.Model):
    __tablename__ = "battle_results"

    id = db.Column(db.Integer, primary_key=True)
    battle_id = db.Column(db.Integer, db.ForeignKey("battles.id"),
                          nullable=False, index=True)
    slot = db.Column(db.Integer, default=0, nullable=False)
    pokemon_a_id = db.Column(db.Integer, nullable=True)
    pokemon_b_id = db.Column(db.Integer, nullable=True)
    name_a = db.Column(db.String(64))
    name_b = db.Column(db.String(64))
    winner = db.Column(db.String(8))            # 'a' | 'b' | 'draw'
    turns = db.Column(db.Integer, default=0)
    hp_a_pct = db.Column(db.Float, default=0.0)
    hp_b_pct = db.Column(db.Float, default=0.0)
    log_json = db.Column(db.Text, default="[]", nullable=False)

    battle = db.relationship("Battle", back_populates="results")

    @property
    def log(self):
        return _loads(self.log_json, [])

    @log.setter
    def log(self, value):
        self.log_json = json.dumps(value)