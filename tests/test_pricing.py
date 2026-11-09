"""Расчёт по формуле из условия:
желают = 0.5_base_demand − price_sensitivity × (цена − base_price)
купят  = min(seats, max(0, желают))
"""
import random
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from app.catalog import load_catalog
from app.domain import QUANTILES, Flight, Route
from app.pricing import CURVE_STEP, best_price, expected, make_forecast, profit_curve


def test_at_base_price_wanted_equals_median_base_demand(sochi, sochi_june_1):
    result = make_forecast(sochi, sochi_june_1, price=9000)

    assert result.seats == 900
    assert result.median.wanted == pytest.approx(775)
    assert result.median.sold == pytest.approx(775)
    assert result.median.sold_out is False


def test_higher_price_lowers_demand_by_sensitivity(sochi, sochi_june_1):
    result = make_forecast(sochi, sochi_june_1, price=10000)

    # 775 − 0.141 × 1000 = 634
    assert result.median.wanted == pytest.approx(634)
    assert result.median.sold == pytest.approx(634)


def test_sales_are_capped_by_seats(sochi, sochi_june_1):
    result = make_forecast(sochi, sochi_june_1, price=8000)

    # 775 + 0.141 × 1000 = 916 желающих, но мест 900
    assert result.median.wanted == pytest.approx(916)
    assert result.median.sold == 900
    assert result.median.sold_out is True


def test_sales_are_zero_when_demand_is_negative(sochi, sochi_june_1):
    result = make_forecast(sochi, sochi_june_1, price=20000)

    # 775 − 0.141 × 11000 = −776
    assert result.median.wanted == pytest.approx(-776)
    assert result.median.sold == 0
    assert result.median.sold_out is False


def test_demand_exactly_equal_to_seats_fills_the_plane(sochi, sochi_june_1):
    flight = replace(sochi_june_1, base_demand={**sochi_june_1.base_demand, 50: 900})

    result = make_forecast(sochi, flight, price=9000)

    assert result.median.sold == 900
    assert result.median.sold_out is True


def test_distribution_has_nine_scenarios_in_order(sochi, sochi_june_1):
    result = make_forecast(sochi, sochi_june_1, price=9500)

    assert [s.percent for s in result.scenarios] == list(QUANTILES)
    assert QUANTILES == (10, 20, 30, 40, 50, 60, 70, 80, 90)


def test_each_scenario_uses_its_own_base_demand(sochi, sochi_june_1):
    result = make_forecast(sochi, sochi_june_1, price=9500)

    for scenario in result.scenarios:
        expected = sochi_june_1.base_demand[scenario.percent] - 0.141 * 500
        assert scenario.base_demand == sochi_june_1.base_demand[scenario.percent]
        assert scenario.outcome.wanted == pytest.approx(expected)


@pytest.mark.parametrize("price", [1, 5400, 8000, 9000, 9500, 13000, 20000])
def test_median_scenario_matches_simple_forecast(sochi, sochi_june_1, price):
    result = make_forecast(sochi, sochi_june_1, price=price)

    median = next(s for s in result.scenarios if s.percent == 50)
    assert median.outcome == result.median


def test_low_price_fills_the_plane_only_in_upper_scenarios(sochi, sochi_june_1):
    result = make_forecast(sochi, sochi_june_1, price=8000)

    sold_out = {s.percent: s.outcome.sold_out for s in result.scenarios}
    # базовый спрос + 141: 40% → 883 (< 900), 50% → 916 (> 900)
    assert sold_out == {10: False, 20: False, 30: False, 40: False,
                        50: True, 60: True, 70: True, 80: True, 90: True}
    assert all(s.outcome.sold <= 900 for s in result.scenarios)


# --- ожидаемая прибыль и лучшая цена ---



def brute_force(route: Route, flight: Flight) -> tuple[int, float]:
    prices = range(int(route.price_min), int(route.price_max) + 1)
    best = max(prices, key=lambda p: expected(route, flight, p).profit)
    return best, expected(route, flight, best).profit


def test_expected_values_are_means_over_nine_scenarios(sochi, sochi_june_1):
    result = expected(sochi, sochi_june_1, price=8000)

    sold = [797, 835, 864, 883, 900, 900, 900, 900, 900]
    assert result.sold == pytest.approx(sum(sold) / 9)
    assert result.revenue == pytest.approx(8000 * sum(sold) / 9)
    assert result.profit == pytest.approx((8000 - 4200) * sum(sold) / 9)


def test_price_below_cost_means_loss(sochi, sochi_june_1):
    assert expected(sochi, sochi_june_1, price=4000).profit < 0


REAL_FLIGHTS = [(code, day) for code in ("MOW-AER", "MOW-LED", "MOW-KGD", "MOW-OVB", "MOW-MRV")
                for day in ("2026-06-01", "2026-06-12", "2026-06-27")]


@pytest.fixture(scope="module")
def real_catalog():
    data = Path(__file__).resolve().parent.parent / "data"
    return load_catalog(data / "routes.csv", data / "seasonal_forecast.csv")


@pytest.mark.parametrize("code, day", REAL_FLIGHTS)
def test_best_price_equals_brute_force_over_every_ruble(real_catalog, code, day):
    route = real_catalog.routes[code]
    flight = real_catalog.find_flight(code, date.fromisoformat(day))

    best = best_price(route, flight)

    expected_price, expected_profit = brute_force(route, flight)
    assert best.price == expected_price
    assert best.expected.profit == pytest.approx(expected_profit)


def random_flight(rng: random.Random) -> tuple[Route, Flight]:
    base_price = rng.randrange(3000, 9000)
    low = rng.randrange(1000, base_price)
    route = Route(code="X-Y", name="X — Y", origin="X", destination="Y", base_price=base_price,
                  price_sensitivity=rng.uniform(0.02, 0.5), price_min=low, price_max=low + rng.randrange(200, 2500),
                  cost_per_passenger=rng.uniform(0, low * 1.2))
    demand = sorted(rng.uniform(0, 1500) for _ in range(9))
    flight = Flight(route_code="X-Y", date=date(2026, 6, 1), seats=rng.randrange(50, 1500),
                    base_demand=dict(zip(QUANTILES, demand)))
    return route, flight


@pytest.mark.parametrize("seed", range(60))
def test_best_price_equals_brute_force_on_random_flights(seed):
    route, flight = random_flight(random.Random(seed))

    best = best_price(route, flight)

    expected_price, expected_profit = brute_force(route, flight)
    assert best.expected.profit == pytest.approx(expected_profit)
    assert best.price == expected_price


def test_best_price_is_whole_rubles_inside_route_range(real_catalog):
    for (code, _), flight in real_catalog.flights.items():
        route = real_catalog.routes[code]
        best = best_price(route, flight)
        assert isinstance(best.price, int)
        assert route.price_min <= best.price <= route.price_max


def test_curve_goes_from_min_to_max_price_with_10_rub_step(sochi, sochi_june_1):
    curve = profit_curve(sochi, sochi_june_1)

    prices = [point.price for point in curve]
    assert CURVE_STEP == 10
    assert prices[0] == 5400 and prices[-1] == 18000
    assert all(b - a == 10 for a, b in zip(prices, prices[1:]))
    assert curve[60].expected == expected(sochi, sochi_june_1, 6000)


def test_best_price_is_not_worse_than_any_curve_point(sochi, sochi_june_1):
    best = best_price(sochi, sochi_june_1)

    assert all(best.expected.profit >= point.expected.profit for point in profit_curve(sochi, sochi_june_1))
