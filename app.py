"""Pokémon Auction — application entry point."""
import os

from app import create_app, socketio

app = create_app()

# Start the idle-room janitor once (guarded internally).
from app.game_engine import manager  # noqa: E402
manager.start_janitor()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_ENV", "development") != "production"
    print(f"\n  🎮  Pokémon Auction running on http://127.0.0.1:{port}\n")
    socketio.run(app, host="0.0.0.0", port=port, debug=debug,
                 allow_unsafe_werkzeug=True)