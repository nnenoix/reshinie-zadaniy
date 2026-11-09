"""Проверка входных данных запроса на прогноз.

Всё, что приходит снаружи, проверяется здесь один раз. Дальше расчёт
получает уже найденные маршрут, рейс и положительную цену.
"""
import math
import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from app.catalog import Catalog
from app.domain import Flight, Route
from app.errors import InputError
from app.sources import ORGANIZERS

NOT_A_NUMBER = "Цена должна быть числом, например 9500."
BAD_DATE = "Дата должна быть в формате ГГГГ-ММ-ДД, например 2026-06-15."
ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


@dataclass(frozen=True)
class ForecastQuery:
    route: Route
    flight: Flight
    price: float


@dataclass(frozen=True)
class FlightQuery:
    route: Route
    flight: Flight
    price: float | None  # цена необязательна: с ней ответ сравнивает лучшую цену с введённой


@dataclass(frozen=True)
class RoutePriceQuery:
    route: Route
    price: float


def parse_source(data: Any, default: str = ORGANIZERS) -> str:
    raw = _as_dict(data).get("source")
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return default
    if not isinstance(raw, str):
        raise InputError("source", "Источник прогноза — это слово: organizers или ml.")
    return raw.strip()


def parse_forecast_query(catalog: Catalog, data: Any) -> ForecastQuery:
    data = _as_dict(data)
    route = _parse_route(catalog, data.get("origin"), data.get("destination"))
    flight = _parse_flight(catalog, route, data.get("date"))
    price = _parse_price(data.get("price"))
    return ForecastQuery(route=route, flight=flight, price=price)


def parse_flight_query(catalog: Catalog, data: Any) -> FlightQuery:
    data = _as_dict(data)
    route = _parse_route(catalog, data.get("origin"), data.get("destination"))
    flight = _parse_flight(catalog, route, data.get("date"))
    raw_price = data.get("price")
    price = None if raw_price is None or str(raw_price).strip() == "" else _parse_price(raw_price)
    return FlightQuery(route=route, flight=flight, price=price)


def parse_route_price_query(catalog: Catalog, data: Any) -> RoutePriceQuery:
    data = _as_dict(data)
    route = _parse_route(catalog, data.get("origin"), data.get("destination"))
    return RoutePriceQuery(route=route, price=_parse_price(data.get("price")))


def _as_dict(data: Any) -> dict:
    if not isinstance(data, dict):
        raise InputError(None, "Запрос должен быть JSON-объектом с полями origin, destination, date, price.")
    return data


def _parse_route(catalog: Catalog, raw_origin: Any, raw_destination: Any) -> Route:
    origin_text = _required_text(raw_origin, "origin", "Укажите город отправления.")
    destination_text = _required_text(raw_destination, "destination", "Укажите город назначения.")

    origin = _match_city(origin_text, catalog.origins())
    if origin is None:
        raise InputError(
            "origin",
            f"Из города «{origin_text}» рейсов нет. Есть рейсы из: {', '.join(catalog.origins())}.",
        )
    destinations = catalog.destinations(origin)
    destination = _match_city(destination_text, destinations)
    if destination is None:
        raise InputError(
            "destination",
            f"Рейсов {origin} — {destination_text} нет. "
            f"Из города {origin} можно улететь в: {', '.join(destinations)}.",
        )
    return catalog.find_route(origin, destination)


def _parse_flight(catalog: Catalog, route: Route, raw: Any) -> Flight:
    text = _required_text(raw, "date", "Укажите дату вылета.")
    if not ISO_DATE.fullmatch(text):
        raise InputError("date", BAD_DATE)
    try:
        day = date.fromisoformat(text)
    except ValueError:
        raise InputError("date", BAD_DATE) from None
    flight = catalog.find_flight(route.code, day)
    if flight is None:
        first, last = catalog.date_range(route.code)
        raise InputError(
            "date",
            f"На {day:%d.%m.%Y} прогноза нет. Можно выбрать дату с {first:%d.%m.%Y} по {last:%d.%m.%Y}.",
        )
    return flight


def _parse_price(raw: Any) -> float:
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        raise InputError("price", "Укажите цену билета.")
    if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
        raise InputError("price", NOT_A_NUMBER)
    if isinstance(raw, str):
        raw = raw.replace(" ", "").replace(" ", "").replace(",", ".")
    try:
        price = float(raw)
    except ValueError:
        raise InputError("price", NOT_A_NUMBER) from None
    if not math.isfinite(price):
        raise InputError("price", NOT_A_NUMBER)
    if price <= 0:
        raise InputError("price", "Цена должна быть больше нуля.")
    return price


def _required_text(raw: Any, field: str, empty_message: str) -> str:
    if raw is None:
        raise InputError(field, empty_message)
    text = str(raw).strip()
    if not text:
        raise InputError(field, empty_message)
    return text


def _match_city(text: str, cities: list[str]) -> str | None:
    wanted = text.casefold()
    return next((city for city in cities if city.casefold() == wanted), None)
