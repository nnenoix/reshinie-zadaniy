"""Предметная область.

Словарь:
- маршрут (Route) — пара городов с базовой ценой, себестоимостью пассажира
  и чувствительностью спроса к цене;
- рейс (Flight) — маршрут в конкретную дату: число мест и прогноз спроса;
- сценарий — один из 9 квантилей прогноза (10%, 20%, …, 90%);
- базовый спрос (base_demand) — сколько человек захотят лететь по базовой цене;
- «желают» (wanted) — спрос при введённой цене, может быть отрицательным;
- «купят» (sold) — желающие, ограниченные нулём снизу и числом мест сверху;
- загрузка — купят / мест;
- ожидаемая прибыль — среднее по 9 сценариям от (цена − себестоимость) × купят;
- цена из файла (file_price) — 0.5_price из файла прогноза: лучшая цена медианного сценария.
"""
from dataclasses import dataclass
from datetime import date
from typing import Mapping

# Сценарии храним в процентах, чтобы не сравнивать дробные 0.1, 0.2, …
QUANTILES: tuple[int, ...] = (10, 20, 30, 40, 50, 60, 70, 80, 90)
MEDIAN = 50

HOLIDAYS: Mapping[date, str] = {date(2026, 6, 12): "День России"}
WEEKDAYS = ("понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье")
FRIDAY = 4


@dataclass(frozen=True)
class Route:
    code: str
    name: str
    origin: str
    destination: str
    base_price: float
    price_sensitivity: float
    price_min: float
    price_max: float
    cost_per_passenger: float


@dataclass(frozen=True)
class Flight:
    route_code: str
    date: date
    seats: int
    base_demand: Mapping[int, float]  # процент сценария → базовый спрос
    file_price: float | None = None  # 0.5_price из файла прогноза, если колонка есть


def weekday_name(day: date) -> str:
    return WEEKDAYS[day.weekday()]


def is_friday(day: date) -> bool:
    return day.weekday() == FRIDAY
