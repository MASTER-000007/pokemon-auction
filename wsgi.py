"""WSGI entry point for gunicorn: ``gunicorn wsgi:app``.

IMPORTANT: eventlet.monkey_patch() MUST be the very first thing this module
does — before any other import — or the standard library's threading,
socket, and time modules will be un-patchable, causing green-thread stalls.
"""
import eventlet
eventlet.monkey_patch()

from app import create_app, socketio          # noqa: E402
from app.game_engine import manager           # noqa: E402

app = create_app()
manager.start_janitor()
