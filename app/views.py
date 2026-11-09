"""Перевод объектов предметной области в JSON-ответы. Округление — только здесь."""
from app.calendar import CalendarDay
from app.catalog import Catalog
from app.domain import HOLIDAYS, Flight, Route, weekday_name
from app.history import HistoryEntry
from app.pricing import Advice, Expected, Forecast, PricePoint
from app.seatmap import MAX_WAITING_ICONS, SeatMap
from app.story import FridayStory


def money(value: float) -> float:
    return round(value, 2) + 0.0  # + 0.0 убирает «-0.0»


def share(value: float) -> float:
    return round(value, 4) + 0.0


def route_json(route: Route) -> dict:
    return {
        "code": route.code, "name": route.name, "origin": route.origin, "destination": route.destination,
        "base_price": route.base_price, "price_sensitivity": route.price_sensitivity,
        "cost_per_passenger": route.cost_per_passenger, "price_min": route.price_min, "price_max": route.price_max,
    }


def routes_json(source: str, catalog: Catalog) -> dict:
    return {"source": source, "holidays": {day.isoformat(): name for day, name in HOLIDAYS.items()}, "origins": [
        {"name": origin, "destinations": [
            destination_json(catalog, catalog.find_route(origin, destination))
            for destination in catalog.destinations(origin)
        ]}
        for origin in catalog.origins()
    ]}


def destination_json(catalog: Catalog, route: Route) -> dict:
    first, last = catalog.date_range(route.code)
    return {
        "name": route.destination, "route": route.code, "base_price": route.base_price,
        "price_min": route.price_min, "price_max": route.price_max,
        "cost_per_passenger": route.cost_per_passenger,
        "first_date": first.isoformat(), "last_date": last.isoformat(),
    }


def expected_json(value: Expected | None) -> dict | None:
    if value is None:
        return None
    return {"sold": money(value.sold), "revenue": money(value.revenue), "profit": money(value.profit)}


def best_json(advice: Advice) -> dict:
    return {
        "price": advice.best.price,
        "expected": expected_json(advice.best.expected),
        "gain": None if advice.gain is None else money(advice.gain),
        "price_difference": None if advice.price is None else money(advice.best.price - advice.price),
        "file_price": advice.file_price,
        "file_price_expected": expected_json(advice.at_file_price),
    }


def seat_map_json(cabin: SeatMap) -> dict:
    return {
        "seats": cabin.seats, "seats_per_icon": cabin.seats_per_icon, "icons_total": cabin.icons_total,
        "last_icon_seats": cabin.last_icon_seats, "waiting_people": money(cabin.waiting_people),
        "waiting_icons": cabin.waiting_icons, "waiting_capped": cabin.waiting_capped,
        "max_waiting_icons": MAX_WAITING_ICONS, "more_than_one_aircraft": cabin.more_than_one_aircraft,
    }


def forecast_json(source: str, route: Route, flight: Flight, result: Forecast, advice: Advice,
                  cabin: SeatMap, saved: bool) -> dict:
    return {
        "source": source,
        "route": route_json(route),
        "date": flight.date.isoformat(),
        "weekday": weekday_name(flight.date),
        "holiday": HOLIDAYS.get(flight.date),
        "price": result.price,
        "seats": result.seats,
        "wanted": money(result.median.wanted),
        "sold": money(result.median.sold),
        "sold_out": result.median.sold_out,
        "load": share(result.median.sold / result.seats),
        "expected": expected_json(advice.at_price),
        "best": best_json(advice),
        "seat_map": seat_map_json(cabin),
        "scenarios": scenarios_json(result),
        "saved": saved,
    }


def scenarios_json(result: Forecast) -> list[dict]:
    return [
        {"quantile": s.percent / 100, "base_demand": s.base_demand, "wanted": money(s.outcome.wanted),
         "sold": money(s.outcome.sold), "sold_out": s.outcome.sold_out}
        for s in result.scenarios
    ]


def best_price_json(source: str, route: Route, flight: Flight, advice: Advice,
                    curve: list[PricePoint], step: int) -> dict:
    return {
        "source": source,
        "route": route_json(route),
        "date": flight.date.isoformat(),
        "price": advice.price,
        "best": best_json(advice),
        "step": step,
        "curve": [
            {"price": p.price, "profit": money(p.expected.profit), "revenue": money(p.expected.revenue),
             "sold": money(p.expected.sold)}
            for p in curve
        ],
    }


def calendar_json(source: str, route: Route, price: float, days: list[CalendarDay]) -> dict:
    return {
        "source": source,
        "route": route_json(route),
        "price": price,
        "days": [
            {"date": d.date.isoformat(), "weekday": d.weekday, "is_friday": d.is_friday, "holiday": d.holiday,
             "seats": d.seats, "wanted": money(d.wanted), "sold": money(d.sold), "load": share(d.load),
             "sold_out": d.sold_out}
            for d in days
        ],
    }


def compare_forecast_json(result: Forecast, advice: Advice) -> dict:
    return {
        "seats": result.seats, "wanted": money(result.median.wanted), "sold": money(result.median.sold),
        "sold_out": result.median.sold_out, "load": share(result.median.sold / result.seats),
        "best_price": advice.best.price, "best_profit": money(advice.best.expected.profit),
    }


def history_item_json(entry: HistoryEntry) -> dict:
    return {
        "id": entry.id, "created_at": entry.created_at.isoformat(timespec="seconds"), "source": entry.source,
        "route_code": entry.route_code, "origin": entry.origin, "destination": entry.destination,
        "date": entry.flight_date.isoformat(), "price": entry.price, "seats": entry.seats,
        "wanted": money(entry.wanted), "sold": money(entry.sold), "load": share(entry.load),
    }


def story_json(source: str, source_name: str, story: FridayStory, result: Forecast, advice: Advice) -> dict:
    return {
        "source": source, "source_name": source_name, "route": route_json(story.route),
        "date": story.flight.date.isoformat(), "weekday": weekday_name(story.flight.date),
        "holiday": HOLIDAYS.get(story.flight.date), "seats": story.flight.seats,
        "median": story.median, "low": story.low, "high": story.high,
        "fridays": [{"date": f.date.isoformat(), "median": f.median, "is_story_day": f.is_story_day}
                    for f in story.fridays],
        "others_mean": money(story.others_mean), "drop": share(story.drop),
        "price": result.price, "scenarios": scenarios_json(result), "best": best_json(advice),
    }
