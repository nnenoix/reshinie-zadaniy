"""Календарь месяца: загрузка рейса по дням при одной цене (медианный сценарий)."""
from dataclasses import dataclass
from datetime import date
from typing import Iterable

from app.domain import HOLIDAYS, MEDIAN, Flight, Route, is_friday, weekday_name
from app.pricing import outcome


@dataclass(frozen=True)
class CalendarDay:
    date: date
    weekday: str
    is_friday: bool
    holiday: str | None
    seats: int
    wanted: float
    sold: float
    load: float  # купят / мест, от 0 до 1
    sold_out: bool


def month_calendar(route: Route, flights: Iterable[Flight], price: float) -> list[CalendarDay]:
    days = []
    for flight in flights:
        median = outcome(flight.base_demand[MEDIAN], flight.seats, route, price)
        days.append(CalendarDay(
            date=flight.date,
            weekday=weekday_name(flight.date),
            is_friday=is_friday(flight.date),
            holiday=HOLIDAYS.get(flight.date),
            seats=flight.seats,
            wanted=median.wanted,
            sold=median.sold,
            load=median.sold / flight.seats,
            sold_out=median.sold_out,
        ))
    return days
