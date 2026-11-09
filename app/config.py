"""Настройки из переменных окружения.

FORECAST_CSV     прогноз организаторов; по умолчанию data/seasonal_forecast.csv
ML_FORECAST_CSV  прогноз нашей ML-модели; по умолчанию data/my_forecast.csv
                 (если файла нет, работает только прогноз организаторов)
ROUTES_CSV       маршруты; по умолчанию data/routes.csv
DATABASE_URL     адрес Postgres (postgresql://…); если задан, база — Postgres, а не SQLite
DB_PATH          база SQLite (пользователи, сессии, история); по умолчанию var/app.db
COOKIE_SECURE    1 — cookie только по HTTPS (включить на хостинге)
SESSION_DAYS     сколько дней действует вход; по умолчанию 7
DEMO_LOGIN       демо-аккаунт для жюри; по умолчанию jury
DEMO_PASSWORD    пароль демо-аккаунта; не задан — демо-аккаунта нет (в репозитории пароля нет)
LOGIN_LIMIT      сколько неудачных входов подряд разрешено с одного адреса; по умолчанию 5
LOGIN_WINDOW_MINUTES  за какое окно они считаются; по умолчанию 5
ACCOUNT_LOGIN_LIMIT   сколько неудачных входов в один аккаунт с любых адресов; по умолчанию 10
ACCOUNT_LOGIN_WINDOW_MINUTES  за какое окно; по умолчанию 15
CLIENT_IP_HEADER заголовок с адресом клиента, который ставит прокси (на Render — cf-connecting-ip);
                 пусто — адрес соединения, X-Forwarded-For не читается
SIGNUP_LIMIT     сколько новых аккаунтов и гостей в час с одного адреса; по умолчанию 20

Относительные пути считаются от папки проекта.
"""
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

PROJECT_DIR = Path(__file__).resolve().parent.parent
DEMO_LOGIN = "jury"


@dataclass(frozen=True)
class Settings:
    routes_csv: Path = PROJECT_DIR / "data" / "routes.csv"
    forecast_csv: Path = PROJECT_DIR / "data" / "seasonal_forecast.csv"
    ml_forecast_csv: Path = PROJECT_DIR / "data" / "my_forecast.csv"
    db_path: Path = PROJECT_DIR / "var" / "app.db"
    database_url: str | None = None  # Postgres; без него — SQLite в db_path
    cookie_secure: bool = False
    session_days: int = 7
    demo_login: str = DEMO_LOGIN
    demo_password: str = ""  # пароль только из окружения: в репозитории его нет
    login_limit: int = 5
    login_window_minutes: int = 5
    account_login_limit: int = 10  # неудачных входов в один аккаунт с любых адресов
    account_login_window_minutes: int = 15
    client_ip_header: str | None = None
    signup_limit: int = 20  # новых аккаунтов (и гостей) с одного адреса в час

    @classmethod
    def from_env(cls) -> "Settings":
        return from_environment(os.environ)


def from_environment(env: Mapping[str, str]) -> Settings:
    defaults = Settings()

    def text(name: str, default: str = "") -> str:
        return env.get(name, default).strip()

    def number(name: str, default: int) -> int:
        return int(text(name) or default)

    def path(name: str, default: Path) -> Path:
        raw = text(name)
        if not raw:
            return default
        given = Path(raw)
        return given if given.is_absolute() else PROJECT_DIR / given

    return Settings(
        routes_csv=path("ROUTES_CSV", defaults.routes_csv),
        forecast_csv=path("FORECAST_CSV", defaults.forecast_csv),
        ml_forecast_csv=path("ML_FORECAST_CSV", defaults.ml_forecast_csv),
        db_path=path("DB_PATH", defaults.db_path),
        database_url=text("DATABASE_URL") or None,
        cookie_secure=text("COOKIE_SECURE").lower() in {"1", "true", "yes"},
        session_days=number("SESSION_DAYS", defaults.session_days),
        demo_login=text("DEMO_LOGIN", defaults.demo_login),
        demo_password=env.get("DEMO_PASSWORD", ""),
        login_limit=number("LOGIN_LIMIT", defaults.login_limit),
        login_window_minutes=number("LOGIN_WINDOW_MINUTES", defaults.login_window_minutes),
        account_login_limit=number("ACCOUNT_LOGIN_LIMIT", defaults.account_login_limit),
        account_login_window_minutes=number("ACCOUNT_LOGIN_WINDOW_MINUTES", defaults.account_login_window_minutes),
        client_ip_header=text("CLIENT_IP_HEADER").lower() or None,
        signup_limit=number("SIGNUP_LIMIT", defaults.signup_limit),
    )
