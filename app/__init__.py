"""Application factory for Pokémon Auction."""
import os

from flask import Flask, jsonify, render_template, request
from flask_socketio import SocketIO
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.pool import NullPool

from config import Config

db = SQLAlchemy()
socketio = SocketIO(
    async_mode="eventlet",
    cors_allowed_origins="*",
    ping_timeout=30,
    ping_interval=15,
    max_http_buffer_size=1_000_000,
)


def create_app(config_class=Config):
    base = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    app = Flask(
        __name__,
        template_folder=os.path.join(base, "templates"),
        static_folder=os.path.join(base, "static"),
    )
    app.config.from_object(config_class)

    # ------------------------------------------------------------------
    # Engine options
    # NullPool is mandatory under eventlet (see config.py for the reason).
    # For SQLite we also need check_same_thread=False.
    # ------------------------------------------------------------------
    opts = dict(app.config.get("SQLALCHEMY_ENGINE_OPTIONS", {}))
    opts.setdefault("poolclass", NullPool)

    if str(app.config["SQLALCHEMY_DATABASE_URI"]).startswith("sqlite"):
        opts["connect_args"] = {"check_same_thread": False}

    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = opts

    db.init_app(app)
    socketio.init_app(
        app,
        async_mode="eventlet",
        manage_session=True,
        cors_allowed_origins="*",
        logger=False,
        engineio_logger=False,
    )

    # ---- models must be imported before create_all -------------------
    from app import models  # noqa: F401

    # ---- blueprints ---------------------------------------------------
    from app.routes import main_bp
    app.register_blueprint(main_bp)

    # ---- socket handlers (import registers the decorators) ------------
    from app import sockets  # noqa: F401

    # ---- game manager --------------------------------------------------
    from app.game_engine import manager
    manager.init_app(app)

    # ---- error handlers -------------------------------------------------
    @app.errorhandler(404)
    def not_found(_e):
        if request.path.startswith("/api/"):
            return jsonify({"ok": False, "error": "Not found"}), 404
        return render_template("404.html"), 404

    @app.errorhandler(500)
    def server_error(_e):
        db.session.rollback()
        if request.path.startswith("/api/"):
            return jsonify({"ok": False, "error": "Internal server error"}), 500
        return render_template("500.html"), 500

    # ---- CLI ------------------------------------------------------------
    @app.cli.command("init-db")
    def init_db_command():
        """Create all database tables."""
        db.create_all()
        print("✔  Database tables created.")

    @app.cli.command("init-pokemon")
    def init_pokemon_command():
        """Populate the local Pokémon cache from PokéAPI."""
        from app.pokemon_api import populate_pokemon
        db.create_all()
        populate_pokemon(limit=app.config["POKEMON_LIMIT"])

    @app.cli.command("reset-db")
    def reset_db_command():
        """Drop and recreate all tables (DESTRUCTIVE)."""
        db.drop_all()
        db.create_all()
        print("✔  Database reset.")

    if app.config.get("AUTO_CREATE_DB"):
        with app.app_context():
            try:
                db.create_all()
            except Exception as exc:          # pragma: no cover
                app.logger.warning("Could not auto-create tables: %s", exc)

    return app
