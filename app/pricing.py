"""Расчёт спроса и продаж по формуле из условия кейса.

желают = base_demand − price_sensitivity × (цена − base_price)
купят  = min(seats, max(0, желают))

Для простого прогноза base_demand берётся из медианы (50%),
для графика — из каждого из 9 сценариев.
"""
import math
from dataclasses import dataclass

from app.domain import MEDIAN, QUANTILES, Flight, Route


@dataclass(frozen=True)
class Outcome:
    wanted: float
    sold: float
    sold_out: bool  # продажи упёрлись в число мест


@dataclass(frozen=True)
class Scenario:
    percent: int
    base_demand: float
    outcome: Outcome


@dataclass(frozen=True)
class Forecast:
    seats: int
    price: float
    median: Outcome
    scenarios: tuple[Scenario, ...]


def wanted(base_demand: float, route: Route, price: float) -> float:
    return base_demand - route.price_sensitivity * (price - route.base_price)


def outcome(base_demand: float, seats: int, route: Route, price: float) -> Outcome:
    demand = wanted(base_demand, route, price)
    return Outcome(
        wanted=demand,
        sold=min(seats, max(0, demand)),
        sold_out=demand >= seats,
    )


def make_forecast(route: Route, flight: Flight, price: float) -> Forecast:
    scenarios = tuple(
        Scenario(
            percent=percent,
            base_demand=flight.base_demand[percent],
            outcome=outcome(flight.base_demand[percent], flight.seats, route, price),
        )
        for percent in QUANTILES
    )
    median = next(s.outcome for s in scenarios if s.percent == MEDIAN)
    return Forecast(seats=flight.seats, price=price, median=median, scenarios=scenarios)


# --- Ожидаемая прибыль и лучшая цена ---
#
# Ожидаемая прибыль при цене p — среднее по 9 сценариям от (p − себестоимость) × купят_q(p).
# В каждом сценарии «купят» по цене — ломаная: все места, потом прямая, потом ноль.
# Поэтому прибыль между точками излома — парабола или прямая, и её максимум в целых
# рублях лежит в точке излома, в вершине параболы или рядом с ними. Перебор этих
# точек даёт точный ответ; тесты сверяют его с перебором каждого рубля.

CURVE_STEP = 10  # шаг кривой прибыли, ₽
PROFIT_TIE = 1e-6  # ₽: прибыли ближе этого считаются равными


@dataclass(frozen=True)
class Expected:
    sold: float  # среднее «купят» по сценариям
    revenue: float
    profit: float


@dataclass(frozen=True)
class PricePoint:
    price: float
    expected: Expected


@dataclass(frozen=True)
class BestPrice:
    price: int
    expected: Expected


def expected(route: Route, flight: Flight, price: float) -> Expected:
    sold = [outcome(flight.base_demand[q], flight.seats, route, price).sold for q in QUANTILES]
    mean = sum(sold) / len(sold)
    return Expected(sold=mean, revenue=price * mean, profit=(price - route.cost_per_passenger) * mean)


def profit_curve(route: Route, flight: Flight, step: int = CURVE_STEP) -> list[PricePoint]:
    low, high = _whole_price_range(route)
    prices = list(range(low, high + 1, step))
    if prices[-1] != high:
        prices.append(high)
    return [PricePoint(price=p, expected=expected(route, flight, p)) for p in prices]


def best_price(route: Route, flight: Flight) -> BestPrice:
    low, high = _whole_price_range(route)
    edges = sorted({low, high, *(p for p in _kinks(route, flight) if low < p < high)})
    candidates = set(edges)
    for left, right in zip(edges, edges[1:]):
        top = _vertex(route, flight, (left + right) / 2)
        if top is not None and left < top < right:
            candidates.add(top)
    prices = {min(high, max(low, rounded)) for c in candidates for rounded in (math.floor(c), math.ceil(c))}
    profits = {p: expected(route, flight, p).profit for p in prices}
    top = max(profits.values())
    # Ничья — меньшая цена. Разница меньше PROFIT_TIE — это шум float: sum() в Python 3.12
    # складывает точнее, чем в 3.11, и без допуска версии выбирали бы разные цены.
    price = min(p for p, profit in profits.items() if profit >= top - PROFIT_TIE)
    return BestPrice(price=price, expected=expected(route, flight, price))


def _whole_price_range(route: Route) -> tuple[int, int]:
    return math.ceil(route.price_min), math.floor(route.price_max)


def _kinks(route: Route, flight: Flight) -> list[float]:
    """Цены, где в каком-то сценарии спрос становится равен числу мест или нулю."""
    s = route.price_sensitivity
    if s <= 0:
        return []
    kinks = []
    for q in QUANTILES:
        base = flight.base_demand[q]
        kinks.append(route.base_price + (base - flight.seats) / s)
        kinks.append(route.base_price + base / s)
    return kinks


def _vertex(route: Route, flight: Flight, inside: float) -> float | None:
    """Вершина параболы прибыли на участке, содержащем цену inside, или None, если участок прямой.

    На участке прибыль ∝ (p − c) × (K − n·s·p), где n — сценарии на прямом участке спроса,
    K — сумма мест полных сценариев и (base + s × base_price) прямых.
    """
    s, c = route.price_sensitivity, route.cost_per_passenger
    k, n = 0.0, 0
    for q in QUANTILES:
        demand = wanted(flight.base_demand[q], route, inside)
        if demand >= flight.seats:
            k += flight.seats
        elif demand > 0:
            k += flight.base_demand[q] + s * route.base_price
            n += 1
    if n == 0 or s <= 0:
        return None
    return (k + n * s * c) / (2 * n * s)


@dataclass(frozen=True)
class Advice:
    """Лучшая цена рядом с введённой и с ценой из файла прогноза."""
    best: BestPrice
    price: float | None
    at_price: Expected | None
    file_price: float | None
    at_file_price: Expected | None

    @property
    def gain(self) -> float | None:
        """На сколько рублей ожидаемая прибыль при лучшей цене больше, чем при введённой."""
        return None if self.at_price is None else self.best.expected.profit - self.at_price.profit


def advise(route: Route, flight: Flight, price: float | None) -> Advice:
    return Advice(
        best=best_price(route, flight),
        price=price,
        at_price=None if price is None else expected(route, flight, price),
        file_price=flight.file_price,
        at_file_price=None if flight.file_price is None else expected(route, flight, flight.file_price),
    )
