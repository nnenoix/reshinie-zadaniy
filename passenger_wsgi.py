"""Точка входа для виртуального хостинга с Passenger (например, TimeWeb).

Passenger запускает только WSGI-приложения, а FastAPI — ASGI.
Обёртка a2wsgi переводит одно в другое. Нужна строка a2wsgi из requirements-passenger.txt.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from a2wsgi import ASGIMiddleware  # noqa: E402

from app.main import create_app  # noqa: E402

application = ASGIMiddleware(create_app())
