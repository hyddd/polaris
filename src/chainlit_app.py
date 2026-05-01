"""Chainlit entry point — imports web channel module for @cl decorator registration.

Run: source venv/bin/activate && chainlit run src/chainlit_app.py
"""

from src.channels.web import *  # noqa: F401, F403 — Chainlit decorator registration
