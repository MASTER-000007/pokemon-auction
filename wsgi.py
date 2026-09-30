"""WSGI entry point for gunicorn / uWSGI: ``gunicorn wsgi:app``."""
from app import create_app, socketio
from app.game_engine import manager

app = create_app()
manager.start_janitor()