"""Сквозная история кейса: пятница 12 июня 2026 года, День России.

Ждали пик спроса, как в пятницу из модели аналитики. Прогноз говорит другое:
на рейсе Москва → Санкт-Петербург медиана спроса ниже, чем в другие пятницы июня.
Здесь это считается из файла прогноза, чтобы витрина показывала настоящие числа.
"""
from dataclasses import dataclass
from datetime import date
from statistics import mean
from typing import Iterable

from app.domain import MEDIAN, Flight, Route, is_friday

STORY_ROUTE = "MOW-LED"
STORY_DAY = date(2026, 6, 12)
LOW, HIGH = 10, 90  # коридор прогноза: сценарии 0.1 и 0.9


@dataclass(frozen=True)
class FridayDemand:
    date: date
    median: float  # 0.5_base_demand: спрос по базовой цене в медианном сценарии
    is_story_day: bool


@dataclass(frozen=True)
class FridayStory:
    route: Route
    flight: Flight
    fridays: list[FridayDemand]  # все пятницы месяца по порядку, включая день истории

    @property
    def median(self) -> float:
        return self.flight.base_demand[MEDIAN]

    @property
    def low(self) -> float:
        return self.flight.base_demand[LOW]

    @property
    def high(self) -> float:
        return self.flight.base_demand[HIGH]

    @property
    def others_mean(self) -> float:
        return mean(f.median for f in self.fridays if not f.is_story_day)

    @property
    def drop(self) -> float:
        """На какую долю спрос дня истории ниже среднего по другим пятницам."""
        return 1 - self.median / self.others_mean


def friday_story(route: Route, flights: Iterable[Flight], day: date) -> FridayStory:
    same_month = [f for f in flights if (f.date.year, f.date.month) == (day.year, day.month)]
    story_flight = next((f for f in same_month if f.date == day), None)
    fridays = [FridayDemand(f.date, f.base_demand[MEDIAN], f.date == day)
               for f in sorted(same_month, key=lambda f: f.date) if is_friday(f.date)]
    if story_flight is None or len(fridays) < 2:
        raise ValueError(f"Для истории нужен рейс {route.code} на {day} и другие пятницы того же месяца.")
    return FridayStory(route=route, flight=story_flight, fridays=fridays)
