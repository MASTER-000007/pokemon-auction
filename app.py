"""Pokémon Auction — application entry point (development server).

Same monkey-patching rule applies here as in wsgi.py: eventlet must patch
the standard library before Flask, SQLAlchemy or Werkzeug get imported.
"""
import eventlet
eventlet.monkey_patch()

import os                                      # noqa: E402

from app import create_app, socketio           # noqa: E402

app = create_app()

# Start the idle-room janitor once (guarded internally).
from app.game_engine import manager            # noqa: E402
manager.start_janitor()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_ENV", "development") != "production"
    print(f"\n  🎮  Pokémon Auction running on http://127.0.0.1:{port}\n")
    socketio.run(app, host="0.0.0.0", port=port, debug=debug,
                 allow_unsafe_werkzeug=True)
