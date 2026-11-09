"""Функции второй фазы через HTTP: лучшая цена, календарь, схема салона,
история, источники прогноза, гость, демо-аккаунт, документация."""
import shutil
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.catalog import load_catalog
from app.config import DEMO_LOGIN, DEMO_PASSWORD
from app.main import create_app
from app.pricing import best_price, expected, make_forecast

STORY = {"origin": "Москва", "destination": "Санкт-Петербург", "date": "2026-06-12"}
DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def with_csrf(client: TestClient) -> TestClient:
    client.headers["X-CSRF-Token"] = client.get("/api/csrf").json()["token"]
    return client


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as test_client:
        yield with_csrf(test_client)


@pytest.fixture
def guest(client):
    assert client.post("/api/guest").status_code == 201
    return client


@pytest.fixture
def catalog(real_routes_csv, real_forecast_csv):
    return load_catalog(real_routes_csv, real_forecast_csv)


def story_flight(catalog):
    return catalog.routes["MOW-LED"], catalog.find_flight("MOW-LED", date(2026, 6, 12))


# --- расчёт с новыми полями ---

def test_story_flight_is_friday_russia_day(guest, catalog):
    body = guest.post("/api/forecast", json={**STORY, "price": 5500}).json()

    route, flight = story_flight(catalog)
    single = make_forecast(route, flight, 5500)
    assert (body["weekday"], body["holiday"]) == ("пятница", "День России")
    assert body["wanted"] == round(single.median.wanted, 2)
    assert body["load"] == round(single.median.sold / 1440, 4)
    assert body["source"] == "organizers"


def test_forecast_compares_entered_price_with_best(guest, catalog):
    body = guest.post("/api/forecast", json={**STORY, "price": 5500}).json()

    route, flight = story_flight(catalog)
    best, at_price = best_price(route, flight), expected(route, flight, 5500)
    assert body["expected"]["profit"] == round(at_price.profit, 2)
    assert body["best"]["price"] == best.price
    assert body["best"]["expected"]["profit"] == round(best.expected.profit, 2)
    assert body["best"]["gain"] == round(best.expected.profit - at_price.profit, 2)
    assert body["best"]["price_difference"] == best.price - 5500
    assert body["best"]["file_price"] == flight.file_price


def test_forecast_has_seat_map_with_10_seats_per_icon_for_1440(guest):
    seat_map = guest.post("/api/forecast", json={**STORY, "price": 5500}).json()["seat_map"]

    assert (seat_map["seats"], seat_map["seats_per_icon"], seat_map["icons_total"]) == (1440, 10, 144)
    assert seat_map["more_than_one_aircraft"] is True


# --- лучшая цена ---

def test_best_price_endpoint_returns_curve_and_optimum(guest, catalog):
    body = guest.get("/api/best-price", params={**STORY, "price": 5500}).json()

    route, flight = story_flight(catalog)
    prices = [p["price"] for p in body["curve"]]
    assert body["step"] == 10
    assert prices[0] == 3300 and prices[-1] == 11000 and len(prices) == 771
    assert body["best"]["price"] == best_price(route, flight).price
    assert body["best"]["gain"] == round(best_price(route, flight).expected.profit - expected(route, flight, 5500).profit, 2)
    point = next(p for p in body["curve"] if p["price"] == 5500)
    assert point["profit"] == round(expected(route, flight, 5500).profit, 2)


def test_best_price_without_entered_price_has_no_gain(guest):
    body = guest.get("/api/best-price", params=STORY).json()

    assert body["price"] is None
    assert body["best"]["gain"] is None


def test_best_price_requires_login(client):
    assert client.get("/api/best-price", params=STORY).status_code == 401


# --- календарь ---

def test_calendar_matches_single_forecasts(guest):
    body = guest.get("/api/calendar", params={"origin": "Москва", "destination": "Санкт-Петербург", "price": 5500}).json()

    assert len(body["days"]) == 31
    for day in body["days"][:31:5] + [body["days"][11]]:
        single = guest.post("/api/forecast", json={**STORY, "date": day["date"], "price": 5500}).json()
        assert (day["sold"], day["wanted"], day["load"], day["sold_out"]) == \
               (single["sold"], single["wanted"], single["load"], single["sold_out"])
    june_12 = body["days"][11]
    assert (june_12["date"], june_12["is_friday"], june_12["holiday"]) == ("2026-06-12", True, "День России")


def test_calendar_checks_price(guest):
    response = guest.get("/api/calendar", params={"origin": "Москва", "destination": "Сочи", "price": "0"})

    assert response.status_code == 422
    assert response.json()["field"] == "price"


# --- история ---

def test_saved_forecasts_appear_in_history_newest_first(guest):
    guest.post("/api/forecast", json={**STORY, "price": 5500, "save": True})
    guest.post("/api/forecast", json={**STORY, "price": 6000})  # предпросмотр ползунка не сохраняется
    guest.post("/api/forecast", json={**STORY, "price": 6500, "save": True})

    items = guest.get("/api/history").json()["items"]

    assert [i["price"] for i in items] == [6500, 5500]
    assert items[0]["date"] == "2026-06-12" and items[0]["destination"] == "Санкт-Петербург"


def test_history_limit(guest):
    for price in range(5000, 5012):
        guest.post("/api/forecast", json={**STORY, "price": price, "save": True})

    assert len(guest.get("/api/history", params={"limit": 3}).json()["items"]) == 3
    assert len(guest.get("/api/history").json()["items"]) == 10


def test_history_csv_download(guest):
    guest.post("/api/forecast", json={**STORY, "price": 5500, "save": True})

    response = guest.get("/api/history.csv")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    lines = response.content.decode("utf-8-sig").splitlines()
    assert lines[0].startswith("Время расчёта (UTC);Источник;Маршрут")
    assert ";MOW-LED;Москва;Санкт-Петербург;2026-06-12;5500;1440;" in lines[1]


def test_history_is_private(client):
    client.post("/api/guest")
    client.post("/api/forecast", json={**STORY, "price": 5500, "save": True})
    client.post("/api/logout")

    client.post("/api/guest")

    assert client.get("/api/history").json()["items"] == []


# --- источники прогноза ---

def test_sources_show_missing_ml_file(client):
    sources = {s["id"]: s for s in client.get("/api/sources").json()["sources"]}

    assert sources["organizers"]["available"] is True
    assert sources["ml"]["available"] is False
    assert sources["ml"]["detail"] == "Наша ML-модель: файла my_forecast.csv пока нет."


def test_forecast_from_missing_ml_source_is_explained(guest):
    response = guest.post("/api/forecast", json={**STORY, "price": 5500, "source": "ml"})

    assert response.status_code == 422
    assert response.json() == {"detail": "Наша ML-модель: файла my_forecast.csv пока нет.", "field": "source"}


def test_ml_source_works_once_file_appears(guest, settings, real_forecast_csv):
    settings.ml_forecast_csv.parent.mkdir(parents=True)
    shutil.copy(real_forecast_csv, settings.ml_forecast_csv)

    body = guest.post("/api/forecast", json={**STORY, "price": 5500, "source": "ml"}).json()

    assert body["source"] == "ml"
    assert body["seats"] == 1440


def test_compare_shows_both_sources(guest, settings, real_forecast_csv):
    params = {**STORY, "price": 5500}
    before = {s["source"]: s for s in guest.get("/api/compare", params=params).json()["sources"]}
    settings.ml_forecast_csv.parent.mkdir(parents=True)
    shutil.copy(real_forecast_csv, settings.ml_forecast_csv)
    after = {s["source"]: s for s in guest.get("/api/compare", params=params).json()["sources"]}

    assert before["organizers"]["available"] and not before["ml"]["available"]
    assert before["ml"]["forecast"] is None
    assert after["ml"]["forecast"]["sold"] == after["organizers"]["forecast"]["sold"]


def test_routes_for_source(client):
    assert client.get("/api/routes", params={"source": "ml"}).status_code == 422
    assert client.get("/api/routes", params={"source": "organizers"}).json()["source"] == "organizers"


# --- гость, демо-аккаунт, служебное ---

def test_guest_login_works_without_registration(client):
    response = client.post("/api/guest")

    assert response.status_code == 201
    assert response.json()["login"].startswith("гость-")
    assert client.post("/api/forecast", json={**STORY, "price": 5500}).status_code == 200


def test_demo_account_from_readme_logs_in(client):
    response = client.post("/api/login", json={"login": DEMO_LOGIN, "password": DEMO_PASSWORD})

    assert response.status_code == 200
    assert response.json() == {"login": DEMO_LOGIN}


def test_health(client):
    body = client.get("/api/health").json()

    assert body["status"] == "ok"
    assert body["sources"] == {"organizers": True, "ml": False}


def test_swagger_docs_are_in_russian(client):
    assert client.get("/docs").status_code == 200
    schema = client.get("/openapi.json").json()

    assert schema["info"]["title"] == "Прогноз продаж авиабилетов"
    forecast = schema["paths"]["/api/forecast"]["post"]
    assert forecast["summary"] == "Прогноз продаж рейса"
    assert "желают" in forecast["description"]
    assert "requestBody" in forecast


# --- источник по умолчанию и сквозная история ---

def put_ml_file(settings):
    settings.ml_forecast_csv.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(DATA_DIR / "my_forecast.csv", settings.ml_forecast_csv)


def test_forecast_uses_ml_by_default_once_its_file_exists(guest, settings):
    assert guest.post("/api/forecast", json={**STORY, "price": 5500}).json()["source"] == "organizers"

    put_ml_file(settings)

    assert guest.post("/api/forecast", json={**STORY, "price": 5500}).json()["source"] == "ml"
    assert guest.get("/api/routes").json()["source"] == "ml"
    assert guest.get("/api/calendar", params={**STORY, "price": 5500}).json()["source"] == "ml"


def test_routes_name_the_holidays(client):
    assert client.get("/api/routes").json()["holidays"] == {"2026-06-12": "День России"}


def test_story_is_public_and_matches_the_landing_text(client, settings):
    put_ml_file(settings)
    client.cookies.clear()

    response = client.get("/api/story")

    assert response.status_code == 200
    body = response.json()
    assert (body["source"], body["route"]["code"], body["date"]) == ("ml", "MOW-LED", "2026-06-12")
    assert (round(body["median"]), round(body["others_mean"]), round(body["drop"] * 100)) == (917, 1049, 13)
    assert (body["low"], body["high"]) == (782, 1039)
    assert [f["date"] for f in body["fridays"] if f["is_story_day"]] == ["2026-06-12"]
    assert len(body["scenarios"]) == 9
    assert body["price"] == 5500
    assert abs(body["best"]["price"] - 5610) <= 5  # «лучшая цена около 5 610 ₽»: по нашему прогнозу 5 605


def test_story_by_organizers_forecast_gives_5614(client):
    body = client.get("/api/story", params={"source": "organizers"}).json()

    assert body["best"]["price"] == 5614
    assert round(body["best"]["gain"]) == 3812
