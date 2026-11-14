"""Лучшая цена при ничьей, пределы цены и даты, кэш страниц, схема /docs, ответ CSRF."""
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.catalog import load_catalog
from app.main import create_app
from app.pricing import best_price, expected

SOCHI = {"origin": "Москва", "destination": "Сочи", "date": "2026-06-09"}


@pytest.fixture
def raw_client(settings):
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def client(raw_client):
    raw_client.headers["X-CSRF-Token"] = raw_client.get("/api/csrf").json()["token"]
    return raw_client


@pytest.fixture
def guest(client):
    assert client.post("/api/guest").status_code == 201
    return client


# --- пункт 10: при равной прибыли — меньшая цена, на любой версии Python ---

def test_tie_on_moscow_sochi_june_9_takes_the_lower_price(real_routes_csv, real_forecast_csv):
    catalog = load_catalog(real_routes_csv, real_forecast_csv)
    route = catalog.routes["MOW-AER"]
    flight = catalog.find_flight("MOW-AER", date(2026, 6, 9))
    # 10 162 и 10 163 ₽ дают одну прибыль; разница только в шуме float
    assert expected(route, flight, 10162).profit == pytest.approx(expected(route, flight, 10163).profit, abs=1e-6)

    assert best_price(route, flight).price == 10162


def test_tie_is_settled_by_the_lower_price_even_if_float_noise_favours_the_higher(
        real_routes_csv, real_forecast_csv, monkeypatch):
    import app.pricing as pricing
    catalog = load_catalog(real_routes_csv, real_forecast_csv)
    route = catalog.routes["MOW-AER"]
    flight = catalog.find_flight("MOW-AER", date(2026, 6, 9))
    real = pricing.expected

    def noisy(route_, flight_, price):  # так считает sum() в Python 3.12: у 10 163 на несколько ulp больше
        result = real(route_, flight_, price)
        return result if price != 10163 else type(result)(result.sold, result.revenue, result.profit + 1e-8)

    monkeypatch.setattr(pricing, "expected", noisy)

    assert pricing.best_price(route, flight).price == 10162


# --- пункт 11: у цены есть верхний предел ---

def test_absurd_price_is_rejected_at_the_field(guest):
    response = guest.post("/api/forecast", json={**SOCHI, "price": 123456789012345, "save": True})

    assert response.status_code == 422
    assert response.json() == {"detail": "Цена не больше 1 000 000 ₽.", "field": "price"}
    assert guest.get("/api/history").json()["items"] == []


def test_price_of_one_million_is_still_accepted(guest):
    assert guest.post("/api/forecast", json={**SOCHI, "price": 1_000_000}).status_code == 200


# --- пункт 12: несуществующая дата ---

@pytest.mark.parametrize("day", ["2026-06-31", "2026-02-30"])
def test_impossible_date_says_there_is_no_such_date(guest, day):
    response = guest.post("/api/forecast", json={**SOCHI, "date": day, "price": 9000})

    assert response.json() == {"detail": "Такой даты нет.", "field": "date"}


# --- пункт 13: страница инструмента не берётся из кэша после выхода ---

def test_tool_page_is_never_stored(guest):
    assert guest.get("/app").headers["cache-control"] == "no-store"


# --- пункт 6: ответ CSRF говорит, что токена нет, — клиент может повторить запрос ---

def test_missing_csrf_token_has_a_code_for_the_retry(raw_client):
    response = raw_client.post("/api/guest")

    assert response.status_code == 403
    assert response.json()["code"] == "NO_TOKEN"
    assert raw_client.cookies.get("csrf_token")


def test_foreign_origin_has_its_own_code(client):
    response = client.post("/api/guest", headers={"Origin": "https://evil.example"})

    assert response.json()["code"] == "FOREIGN_ORIGIN"


# --- пункт 14: схема /docs ---

@pytest.fixture
def openapi(raw_client):
    return raw_client.get("/openapi.json").json()


def required_params(openapi, path):
    return {p["name"]: p.get("required", False) for p in openapi["paths"][path]["get"]["parameters"]}


def test_required_query_parameters_are_marked_in_docs(openapi):
    assert required_params(openapi, "/api/best-price") == {
        "origin": True, "destination": True, "date": True, "price": False, "source": False}
    assert required_params(openapi, "/api/calendar") == {
        "origin": True, "destination": True, "price": True, "source": False}
    assert required_params(openapi, "/api/compare") == {
        "origin": True, "destination": True, "date": True, "price": True}


def test_required_parameter_is_a_plain_string_in_docs(openapi):
    origin = next(p for p in openapi["paths"]["/api/compare"]["get"]["parameters"] if p["name"] == "origin")

    assert origin["schema"]["type"] == "string"
    assert not any(key.startswith("x-") for key in origin["schema"])


def test_missing_required_parameter_keeps_the_russian_message(guest):
    response = guest.get("/api/compare", params={"destination": "Сочи", "date": "2026-06-09", "price": 9000})

    assert response.json() == {"detail": "Укажите город отправления.", "field": "origin"}


def responses(openapi, path, method="get"):
    return set(openapi["paths"][path][method]["responses"])


def test_public_pages_list_no_auth_csrf_or_rate_errors(openapi):
    for path in ("/api/routes", "/api/story"):
        assert not responses(openapi, path) & {"401", "403", "429"}


def test_get_requests_list_no_csrf_or_rate_errors(openapi):
    for path in ("/api/best-price", "/api/calendar", "/api/compare", "/api/history", "/api/me"):
        assert not responses(openapi, path) & {"403", "429"}
        assert "401" in responses(openapi, path)


def test_login_lists_its_real_errors(openapi):
    assert {"401", "403", "422", "429"} <= responses(openapi, "/api/login", "post")


def test_save_flag_names_the_calculate_button(openapi):
    body = openapi["paths"]["/api/forecast"]["post"]["requestBody"]["content"]["application/json"]["schema"]
    description = body["properties"]["save"]["description"]

    assert "«Рассчитать»" in description
