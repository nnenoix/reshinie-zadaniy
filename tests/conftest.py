import os
from datetime import date
from pathlib import Path

import pytest

from app.config import Settings
from app.db import open_database
from app.domain import Flight, Route

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
# Пусто — тесты пишут в новый файл SQLite. Адрес Postgres — те же тесты идут на Postgres:
# TEST_DATABASE_URL=postgresql://user:password@127.0.0.1:55432/db python -m pytest
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "").strip() or None
TABLES = "sessions, calculations, users, things"


@pytest.fixture
def database_target(tmp_path) -> tuple[str | None, Path]:
    """Куда пишут тесты: (адрес Postgres или None, путь к файлу SQLite). Postgres каждый раз чистый."""
    if TEST_DATABASE_URL:
        import psycopg
        with psycopg.connect(TEST_DATABASE_URL, autocommit=True) as connection:
            connection.execute(f"drop table if exists {TABLES} cascade")
    return TEST_DATABASE_URL, tmp_path / "app.db"


@pytest.fixture
def database(database_target):
    opened = open_database(*database_target)
    yield opened
    opened.close()

# Строка MOW-AER за 2026-06-01 из seasonal_forecast.csv.
SOCHI_BASE_DEMAND = {10: 656, 20: 694, 30: 723, 40: 742, 50: 775, 60: 802, 70: 835, 80: 863, 90: 923}


@pytest.fixture
def sochi() -> Route:
    return Route(
        code="MOW-AER",
        name="Москва — Сочи",
        origin="Москва",
        destination="Сочи",
        base_price=9000,
        price_sensitivity=0.141,
        price_min=5400,
        price_max=18000,
        cost_per_passenger=4200,
    )


@pytest.fixture
def sochi_june_1() -> Flight:
    return Flight(route_code="MOW-AER", date=date(2026, 6, 1), seats=900, base_demand=SOCHI_BASE_DEMAND,
                  file_price=9347)


@pytest.fixture
def real_routes_csv() -> Path:
    return DATA_DIR / "routes.csv"


@pytest.fixture
def real_forecast_csv() -> Path:
    return DATA_DIR / "seasonal_forecast.csv"


@pytest.fixture
def settings(tmp_path, database_target, real_routes_csv, real_forecast_csv) -> Settings:
    """Настройки для тестов API: своя база, файла ML-прогноза пока нет."""
    url, path = database_target
    return Settings(routes_csv=real_routes_csv, forecast_csv=real_forecast_csv,
                    ml_forecast_csv=tmp_path / "ml" / "my_forecast.csv", db_path=path, database_url=url)
