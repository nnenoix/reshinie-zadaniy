"""Загрузка маршрутов (routes.csv) и прогноза спроса (seasonal_forecast.csv или my_forecast.csv).

Файлы проверяются при загрузке. Если файл испорчен, ошибка называет файл,
строку и колонку.
"""
import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable, Iterator, Mapping, TypeVar

from app.domain import MEDIAN, QUANTILES, Flight, Route

T = TypeVar("T")

ROUTE_COLUMNS = ("route", "name", "base_price", "cost_per_passenger", "price_sensitivity", "price_min", "price_max")
DEMAND_COLUMNS = {percent: f"{percent / 100:.1f}_base_demand" for percent in QUANTILES}
FORECAST_COLUMNS = ("route", "date", "seats", *DEMAND_COLUMNS.values())
FILE_PRICE_COLUMN = f"{MEDIAN / 100:.1f}_price"  # необязательная колонка
CITY_SEPARATOR = " — "


class CatalogError(Exception):
    pass


@dataclass(frozen=True)
class Catalog:
    routes: Mapping[str, Route]
    flights: Mapping[tuple[str, date], Flight]

    def origins(self) -> list[str]:
        return list(dict.fromkeys(r.origin for r in self.routes.values()))

    def destinations(self, origin: str) -> list[str]:
        return [r.destination for r in self.routes.values() if r.origin == origin]

    def find_route(self, origin: str, destination: str) -> Route | None:
        return next(
            (r for r in self.routes.values() if r.origin == origin and r.destination == destination),
            None,
        )

    def find_flight(self, route_code: str, day: date) -> Flight | None:
        return self.flights.get((route_code, day))

    def flights_for(self, route_code: str) -> list[Flight]:
        return sorted((f for (code, _), f in self.flights.items() if code == route_code), key=lambda f: f.date)

    def date_range(self, route_code: str) -> tuple[date, date]:
        days = [day for code, day in self.flights if code == route_code]
        return min(days), max(days)


def load_catalog(routes_path: Path, forecast_path: Path) -> Catalog:
    return load_flights(forecast_path, load_routes(routes_path), routes_path.name)


def load_routes(path: Path) -> dict[str, Route]:
    return {route.code: route for route in _read(path, ROUTE_COLUMNS, _parse_route)}


def load_flights(forecast_path: Path, routes: Mapping[str, Route], routes_name: str = "routes.csv") -> Catalog:
    flights = {}
    for flight in _read(forecast_path, FORECAST_COLUMNS, _parse_flight):
        if flight.route_code not in routes:
            raise CatalogError(f"{forecast_path.name}: маршрута {flight.route_code} нет в {routes_name}")
        flights[(flight.route_code, flight.date)] = flight
    if not flights:
        raise CatalogError(f"{forecast_path.name}: в файле нет ни одного рейса")
    used = {code for code, _ in flights}
    return Catalog(routes={code: r for code, r in routes.items() if code in used}, flights=flights)


def _read(path: Path, columns: tuple[str, ...], parse: Callable[[dict], T]) -> Iterator[T]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            missing = [c for c in columns if c not in (reader.fieldnames or [])]
            if missing:
                raise CatalogError(f"{path.name}: нет колонок {', '.join(missing)}")
            for row in reader:
                try:
                    yield parse(row)
                except (ValueError, TypeError) as error:
                    raise CatalogError(f"{path.name}, строка {reader.line_num}: {error}") from error
    except FileNotFoundError as error:
        raise CatalogError(f"Файл не найден: {path}") from error


def _parse_route(row: dict) -> Route:
    origin, separator, destination = row["name"].partition(CITY_SEPARATOR)
    if not separator:
        raise ValueError(f"в названии «{row['name']}» нет разделителя «{CITY_SEPARATOR.strip()}»")
    return Route(
        code=row["route"].strip(),
        name=row["name"].strip(),
        origin=origin.strip(),
        destination=destination.strip(),
        base_price=float(row["base_price"]),
        price_sensitivity=float(row["price_sensitivity"]),
        price_min=float(row["price_min"]),
        price_max=float(row["price_max"]),
        cost_per_passenger=float(row["cost_per_passenger"]),
    )


def _parse_flight(row: dict) -> Flight:
    file_price = (row.get(FILE_PRICE_COLUMN) or "").strip()
    return Flight(
        route_code=row["route"].strip(),
        date=date.fromisoformat(row["date"].strip()),
        seats=int(float(row["seats"])),
        base_demand={percent: float(row[column]) for percent, column in DEMAND_COLUMNS.items()},
        file_price=float(file_price) if file_price else None,
    )
