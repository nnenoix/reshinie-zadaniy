"""Сквозная история: пятница 12 июня 2026 года на рейсе Москва → Санкт-Петербург.

Числа витрины (917 против 1 049, −13%, коридор 782–1 039) должны получаться из файла
прогноза нашей модели, а 5 614 ₽ и +3 812 ₽ — из прогноза организаторов.
"""
from datetime import date

import pytest

from app.catalog import load_catalog
from app.story import STORY_DAY, STORY_ROUTE, friday_story


@pytest.fixture
def ml_catalog(real_routes_csv):
    return load_catalog(real_routes_csv, real_routes_csv.parent / "my_forecast.csv")


@pytest.fixture
def organizers_catalog(real_routes_csv, real_forecast_csv):
    return load_catalog(real_routes_csv, real_forecast_csv)


def story(catalog):
    return friday_story(catalog.routes[STORY_ROUTE], catalog.flights_for(STORY_ROUTE), STORY_DAY)


def test_story_is_moscow_petersburg_on_russia_day():
    assert (STORY_ROUTE, STORY_DAY) == ("MOW-LED", date(2026, 6, 12))


def test_holiday_friday_is_13_percent_below_other_june_fridays(ml_catalog):
    told = story(ml_catalog)

    assert told.median == 917
    assert (told.low, told.high) == (782, 1039)
    assert [(f.date.day, f.median) for f in told.fridays] == [(5, 1010), (12, 917), (19, 1068), (26, 1070)]
    assert round(told.others_mean) == 1049
    assert round(told.drop * 100) == 13


def test_story_day_is_marked_among_fridays(ml_catalog):
    marked = [f.date for f in story(ml_catalog).fridays if f.is_story_day]

    assert marked == [STORY_DAY]


def test_organizers_forecast_gives_the_same_picture(organizers_catalog):
    told = story(organizers_catalog)

    assert told.drop > 0.1
    assert told.median < min(f.median for f in told.fridays if not f.is_story_day)


def test_story_needs_other_fridays(ml_catalog):
    june_12_only = [f for f in ml_catalog.flights_for(STORY_ROUTE) if f.date == STORY_DAY]

    with pytest.raises(ValueError):
        friday_story(ml_catalog.routes[STORY_ROUTE], june_12_only, STORY_DAY)
