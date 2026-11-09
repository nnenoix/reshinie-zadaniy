import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

UNAUTHORIZED = "Войдите или зарегистрируйтесь, чтобы считать прогноз."


def with_csrf(client: TestClient) -> TestClient:
    client.headers["X-CSRF-Token"] = client.get("/api/csrf").json()["token"]
    return client


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as test_client:
        yield with_csrf(test_client)


@pytest.fixture
def logged_in(client):
    assert client.post("/api/register", json={"login": "anna", "password": "password1"}).status_code == 201
    return client


def forecast(client, **changes):
    body = {"origin": "Москва", "destination": "Сочи", "date": "2026-06-01", "price": 9000, **changes}
    return client.post("/api/forecast", json=body)


def test_main_page_is_served(client):
    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_routes_list_cities_dates_and_prices(client):
    response = client.get("/api/routes")

    assert response.status_code == 200
    (moscow,) = response.json()["origins"]
    assert moscow["name"] == "Москва"
    sochi = next(d for d in moscow["destinations"] if d["name"] == "Сочи")
    assert sochi == {
        "name": "Сочи", "route": "MOW-AER", "base_price": 9000, "price_min": 5400, "price_max": 18000,
        "cost_per_passenger": 4200, "first_date": "2026-06-01", "last_date": "2026-07-01",
    }


def test_forecast_requires_login(client):
    response = forecast(client)

    assert response.status_code == 401
    assert response.json()["detail"] == UNAUTHORIZED


def test_register_logs_in_with_http_only_cookie(client):
    response = client.post("/api/register", json={"login": "anna", "password": "password1"})

    assert response.status_code == 201
    assert response.json() == {"login": "anna"}
    cookie = response.headers["set-cookie"].lower()
    assert "session=" in cookie and "httponly" in cookie and "samesite=lax" in cookie
    assert "secure" not in cookie
    assert client.get("/api/me").json() == {"login": "anna"}


def test_secure_cookie_can_be_switched_on(settings):
    settings = Settings(**{**settings.__dict__, "cookie_secure": True})
    with TestClient(create_app(settings), base_url="https://testserver") as client:
        response = with_csrf(client).post("/api/register", json={"login": "anna", "password": "password1"})

    assert "secure" in response.headers["set-cookie"].lower()


def test_me_without_session_is_unauthorized(client):
    assert client.get("/api/me").status_code == 401


def test_taken_login_is_rejected(logged_in):
    response = logged_in.post("/api/register", json={"login": "ANNA", "password": "password2"})

    assert response.status_code == 409
    assert response.json() == {"detail": "Логин «ANNA» уже занят.", "field": "login"}


def test_short_password_is_rejected_in_russian(client):
    response = client.post("/api/register", json={"login": "anna", "password": "123"})

    assert response.status_code == 422
    assert response.json() == {"detail": "Пароль: от 8 до 128 символов.", "field": "password"}


def test_login_with_wrong_password_fails(logged_in):
    logged_in.post("/api/logout")

    response = logged_in.post("/api/login", json={"login": "anna", "password": "wrong-pass"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Неверный логин или пароль."
    assert forecast(logged_in).status_code == 401


def test_login_then_forecast(logged_in):
    logged_in.post("/api/logout")
    assert logged_in.post("/api/login", json={"login": "anna", "password": "password1"}).status_code == 200

    response = forecast(logged_in)

    assert response.status_code == 200
    body = response.json()
    assert body["route"] == {
        "code": "MOW-AER", "name": "Москва — Сочи", "origin": "Москва", "destination": "Сочи",
        "base_price": 9000, "price_sensitivity": 0.141, "cost_per_passenger": 4200,
        "price_min": 5400, "price_max": 18000,
    }
    assert body["date"] == "2026-06-01"
    assert (body["price"], body["seats"], body["wanted"], body["sold"], body["sold_out"]) == (9000, 900, 775, 775, False)


def test_forecast_returns_nine_scenarios_with_median_equal_to_wanted(logged_in):
    body = forecast(logged_in, price=10000).json()

    scenarios = body["scenarios"]
    assert [s["quantile"] for s in scenarios] == [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
    median = scenarios[4]
    assert median["wanted"] == body["wanted"] == 634
    assert median["sold"] == body["sold"]
    assert scenarios[0] == {"quantile": 0.1, "base_demand": 656, "wanted": 515, "sold": 515, "sold_out": False}


def test_forecast_capped_by_seats(logged_in):
    body = forecast(logged_in, price=8000).json()

    assert (body["wanted"], body["sold"], body["sold_out"]) == (916, 900, True)
    assert [s["sold_out"] for s in body["scenarios"]] == [False] * 4 + [True] * 5


def test_forecast_with_zero_sales(logged_in):
    body = forecast(logged_in, price=20000).json()

    assert (body["wanted"], body["sold"]) == (-776, 0)
    assert all(s["sold"] == 0 for s in body["scenarios"])


def test_fractional_values_are_rounded_to_cents(logged_in):
    body = forecast(logged_in, destination="Новосибирск", price=12345).json()

    # Новосибирск 2026-06-01: медиана 0.5_base_demand, чувствительность 0.0312
    assert body["wanted"] == round(body["scenarios"][4]["base_demand"] - 0.0312 * 345, 2)


@pytest.mark.parametrize("changes, field, message", [
    ({"price": "abc"}, "price", "Цена должна быть числом, например 9500."),
    ({"price": 0}, "price", "Цена должна быть больше нуля."),
    ({"price": -10}, "price", "Цена должна быть больше нуля."),
    ({"date": "2026-08-01"}, "date", "На 01.08.2026 прогноза нет. Можно выбрать дату с 01.06.2026 по 01.07.2026."),
    ({"destination": "Париж"}, "destination", None),
])
def test_bad_input_gets_russian_error_with_field(logged_in, changes, field, message):
    response = forecast(logged_in, **changes)

    assert response.status_code == 422
    assert response.json()["field"] == field
    if message:
        assert response.json()["detail"] == message


def test_broken_json_gets_russian_error(logged_in):
    response = logged_in.post("/api/forecast", content=b"{not json", headers={"content-type": "application/json"})

    assert response.status_code == 422
    assert response.json() == {"detail": "Не удалось прочитать запрос: нужен JSON-объект.", "field": None}


def test_body_not_in_utf8_gets_russian_error(logged_in):
    body = '{"origin": "Москва", "destination": "Сочи", "date": "2026-06-01", "price": 9000}'.encode("cp1251")

    response = logged_in.post("/api/forecast", content=body, headers={"content-type": "application/json"})

    assert response.status_code == 400
    assert response.json() == {"detail": "Не удалось прочитать запрос: нужен JSON в кодировке UTF-8.", "field": None}


def test_unknown_api_path_gets_russian_error(client):
    response = client.get("/api/nothing-here")

    assert response.status_code == 404
    assert response.json()["detail"] == "Такого адреса нет."


def test_wrong_method_gets_russian_error(client):
    response = client.get("/api/forecast")

    assert response.status_code == 405
    assert response.json()["detail"] == "Этот адрес не принимает такой запрос."


def test_logout_ends_session(logged_in):
    assert logged_in.post("/api/logout").status_code == 204

    assert forecast(logged_in).status_code == 401
    assert logged_in.get("/api/me").status_code == 401
