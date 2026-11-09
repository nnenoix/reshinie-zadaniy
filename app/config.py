"""Настройки из переменных окружения.

FORECAST_CSV     прогноз организаторов; по умолчанию data/seasonal_forecast.csv
ML_FORECAST_CSV  прогноз нашей ML-модели; по умолчанию data/my_forecast.csv
                 (если файла нет, работает только прогноз организаторов)
ROUTES_CSV       маршруты; по умолчанию data/routes.csv
DB_PATH          база SQLite (пользователи, сессии, история); по умолчанию var/app.db
COOKIE_SECURE    1 — cookie только по HTTPS (включить на хостинге)
SESSION_DAYS     сколько дней действует вход; по умолчанию 7
DEMO_LOGIN       демо-аккаунт для жюри; по умолчанию jury
DEMO_PASSWORD    пароль демо-аккаунта; пустая строка — демо-аккаунт не создаётся
LOGIN_LIMIT      сколько неудачных входов подряд разрешено; по умолчанию 5
LOGIN_WINDOW_MINUTES  за какое окно они считаются; по умолчанию 5
SIGNUP_LIMIT     сколько новых аккаунтов и гостей в час с одного адреса; по умолчанию 20

Относительные пути считаются от папки проекта.
"""
import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
DEMO_LOGIN = "jury"
DEMO_PASSWORD = "XePqLeeZozQu"  # сгенерирован случайно, записан в README


@dataclass(frozen=True)
class Settings:
    routes_csv: Path = PROJECT_DIR / "data" / "routes.csv"
    forecast_csv: Path = PROJECT_DIR / "data" / "seasonal_forecast.csv"
    ml_forecast_csv: Path = PROJECT_DIR / "data" / "my_forecast.csv"
    db_path: Path = PROJECT_DIR / "var" / "app.db"
    cookie_secure: bool = False
    session_days: int = 7
    demo_login: str = DEMO_LOGIN
    demo_password: str = DEMO_PASSWORD
    login_limit: int = 5
    login_window_minutes: int = 5
    signup_limit: int = 20  # новых аккаунтов (и гостей) с одного адреса в час

    @classmethod
    def from_env(cls) -> "Settings":
        defaults = cls()
        return cls(
            routes_csv=_path("ROUTES_CSV", defaults.routes_csv),
            forecast_csv=_path("FORECAST_CSV", defaults.forecast_csv),
            ml_forecast_csv=_path("ML_FORECAST_CSV", defaults.ml_forecast_csv),
            db_path=_path("DB_PATH", defaults.db_path),
            cookie_secure=os.environ.get("COOKIE_SECURE", "").strip().lower() in {"1", "true", "yes"},
            session_days=int(os.environ.get("SESSION_DAYS", defaults.session_days)),
            demo_login=os.environ.get("DEMO_LOGIN", defaults.demo_login).strip(),
            demo_password=os.environ.get("DEMO_PASSWORD", defaults.demo_password),
            login_limit=int(os.environ.get("LOGIN_LIMIT", defaults.login_limit)),
            login_window_minutes=int(os.environ.get("LOGIN_WINDOW_MINUTES", defaults.login_window_minutes)),
            signup_limit=int(os.environ.get("SIGNUP_LIMIT", defaults.signup_limit)),
        )


def _path(name: str, default: Path) -> Path:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_DIR / path
