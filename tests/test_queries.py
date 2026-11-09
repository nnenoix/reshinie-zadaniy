from datetime import date

import pytest

from app.catalog import load_catalog
from app.errors import InputError
from app.queries import parse_flight_query, parse_forecast_query, parse_route_price_query, parse_source


@pytest.fixture
def catalog(real_routes_csv, real_forecast_csv):
    return load_catalog(real_routes_csv, real_forecast_csv)


def payload(**changes):
    return {"origin": "Москва", "destination": "Сочи", "date": "2026-06-01", "price": 9000, **changes}


def error_for(catalog, data) -> InputError:
    with pytest.raises(InputError) as caught:
        parse_forecast_query(catalog, data)
    return caught.value


def test_valid_query_finds_route_flight_and_price(catalog):
    query = parse_forecast_query(catalog, payload())

    assert query.route.code == "MOW-AER"
    assert query.flight.date == date(2026, 6, 1)
    assert query.price == 9000


@pytest.mark.parametrize("raw, expected", [("9000", 9000), (" 9 500,5 ", 9500.5), (7999.99, 7999.99)])
def test_price_may_come_as_number_or_text(catalog, raw, expected):
    assert parse_forecast_query(catalog, payload(price=raw)).price == expected


def test_city_names_ignore_case_and_spaces(catalog):
    query = parse_forecast_query(catalog, payload(origin=" москва ", destination="САНКТ-ПЕТЕРБУРГ"))

    assert query.route.code == "MOW-LED"


@pytest.mark.parametrize("raw", ["abc", "12abc", True, [], {}, "nan", "inf", float("inf")])
def test_price_that_is_not_a_number_is_rejected(catalog, raw):
    error = error_for(catalog, payload(price=raw))

    assert error.field == "price"
    assert error.message == "Цена должна быть числом, например 9500."


@pytest.mark.parametrize("raw", [0, -1, "-500", "0"])
def test_price_must_be_positive(catalog, raw):
    error = error_for(catalog, payload(price=raw))

    assert error.field == "price"
    assert error.message == "Цена должна быть больше нуля."


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_empty_price_asks_to_fill_it(catalog, raw):
    error = error_for(catalog, payload(price=raw))

    assert (error.field, error.message) == ("price", "Укажите цену билета.")


def test_missing_price_asks_to_fill_it(catalog):
    data = payload()
    del data["price"]

    assert error_for(catalog, data).message == "Укажите цену билета."


def test_unknown_origin_lists_available_cities(catalog):
    error = error_for(catalog, payload(origin="Казань"))

    assert error.field == "origin"
    assert error.message == "Из города «Казань» рейсов нет. Есть рейсы из: Москва."


def test_unknown_destination_lists_available_cities(catalog):
    error = error_for(catalog, payload(destination="Париж"))

    assert error.field == "destination"
    assert error.message.startswith("Рейсов Москва — Париж нет. Из города Москва можно улететь в: Сочи,")


@pytest.mark.parametrize("field", ["origin", "destination", "date"])
def test_empty_fields_ask_to_fill_them(catalog, field):
    error = error_for(catalog, payload(**{field: ""}))

    assert error.field == field
    assert error.message.startswith("Укажите ")


@pytest.mark.parametrize("raw", ["01.06.2026", "2026-02-30", "завтра", 20260601])
def test_bad_date_format_is_rejected(catalog, raw):
    error = error_for(catalog, payload(date=raw))

    assert error.field == "date"
    assert error.message == "Дата должна быть в формате ГГГГ-ММ-ДД, например 2026-06-15."


def test_date_without_forecast_shows_available_range(catalog):
    error = error_for(catalog, payload(date="2026-05-31"))

    assert error.field == "date"
    assert error.message == "На 31.05.2026 прогноза нет. Можно выбрать дату с 01.06.2026 по 01.07.2026."


def test_request_body_must_be_an_object(catalog):
    error = error_for(catalog, ["Москва", "Сочи"])

    assert error.field is None
    assert "JSON" in error.message


def test_flight_query_needs_no_price(catalog):
    query = parse_flight_query(catalog, {"origin": "Москва", "destination": "Санкт-Петербург", "date": "2026-06-12"})

    assert (query.route.code, query.flight.date, query.price) == ("MOW-LED", date(2026, 6, 12), None)


def test_flight_query_checks_price_when_given(catalog):
    data = {"origin": "Москва", "destination": "Сочи", "date": "2026-06-12", "price": "abc"}

    assert error_for_flight(catalog, data).field == "price"
    assert parse_flight_query(catalog, {**data, "price": "6000"}).price == 6000


def error_for_flight(catalog, data) -> InputError:
    with pytest.raises(InputError) as caught:
        parse_flight_query(catalog, data)
    return caught.value


def test_route_price_query_needs_no_date(catalog):
    query = parse_route_price_query(catalog, {"origin": "Москва", "destination": "Сочи", "price": "8000"})

    assert (query.route.code, query.price) == ("MOW-AER", 8000)


def test_source_defaults_to_organizers():
    assert parse_source({}) == "organizers"
    assert parse_source({"source": " ml "}) == "ml"


def test_source_default_can_be_given():
    assert parse_source({}, default="ml") == "ml"
    assert parse_source({"source": ""}, default="ml") == "ml"
    assert parse_source({"source": "organizers"}, default="ml") == "organizers"


def test_source_must_be_text():
    with pytest.raises(InputError) as caught:
        parse_source({"source": 5})

    assert caught.value.field == "source"
