from datetime import date

import pytest

from app.calendar import month_calendar
from app.catalog import load_catalog
from app.pricing import make_forecast


@pytest.fixture
def catalog(real_routes_csv, real_forecast_csv):
    return load_catalog(real_routes_csv, real_forecast_csv)


def test_calendar_day_equals_single_day_forecast(catalog):
    route = catalog.routes["MOW-LED"]

    days = month_calendar(route, catalog.flights_for("MOW-LED"), price=5500)

    assert len(days) == 31
    for day in days:
        single = make_forecast(route, catalog.find_flight("MOW-LED", day.date), 5500)
        assert day.seats == single.seats
        assert day.wanted == single.median.wanted
        assert day.sold == single.median.sold
        assert day.sold_out == single.median.sold_out
        assert day.load == pytest.approx(single.median.sold / single.seats)


def test_fridays_and_russia_day_are_marked(catalog):
    days = month_calendar(catalog.routes["MOW-LED"], catalog.flights_for("MOW-LED"), price=5500)

    assert [d.date.day for d in days if d.is_friday and d.date.month == 6] == [5, 12, 19, 26]
    assert {d.date: d.holiday for d in days if d.holiday} == {date(2026, 6, 12): "День России"}
    assert days[0].weekday == "понедельник"
    assert days[11].weekday == "пятница"


def test_cheap_tickets_hit_the_seat_limit_on_some_days(catalog):
    route = catalog.routes["MOW-AER"]

    days = month_calendar(route, catalog.flights_for("MOW-AER"), price=route.price_min)

    assert any(d.sold_out for d in days)
    assert all(d.load <= 1 for d in days)
    assert all(d.load == 1 for d in days if d.sold_out)
