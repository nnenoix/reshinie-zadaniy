"""Гость регистрируется — его история расчётов переходит в новый аккаунт."""
import pytest
from fastapi.testclient import TestClient

from app.main import create_app

STORY = {"origin": "Москва", "destination": "Санкт-Петербург", "date": "2026-06-12"}
ANNA = {"login": "anna", "password": "password1"}


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as test_client:
        test_client.headers["X-CSRF-Token"] = test_client.get("/api/csrf").json()["token"]
        yield test_client


def save(client, price):
    assert client.post("/api/forecast", json={**STORY, "price": price, "save": True}).status_code == 200


def prices(client):
    return [item["price"] for item in client.get("/api/history").json()["items"]]


def test_guest_history_moves_to_the_new_account(client):
    client.post("/api/guest")
    save(client, 5500)
    save(client, 6000)

    response = client.post("/api/register", json=ANNA)

    assert response.status_code == 201
    assert client.get("/api/me").json() == {"login": "anna", "guest": False}
    assert prices(client) == [6000, 5500]


def test_guest_session_is_closed_after_registration(client):
    client.post("/api/guest")
    guest_cookie = client.cookies.get("session")

    client.post("/api/register", json=ANNA)
    client.cookies.clear()
    client.cookies.set("session", guest_cookie)

    assert client.get("/api/session").json() == {"user": None}


def test_moved_history_is_gone_from_the_guest(client):
    client.post("/api/guest")
    guest_login = client.get("/api/me").json()["login"]
    save(client, 5500)
    client.post("/api/register", json=ANNA)

    with client.app.state.database.transaction() as db:
        (guest_id,) = db.one("select id from users where login = ?", (guest_login,))

    assert client.app.state.history.all(guest_id) == []


def test_registered_user_creating_another_account_keeps_their_history(client):
    client.post("/api/register", json=ANNA)
    save(client, 5500)

    client.post("/api/register", json={"login": "boris", "password": "password1"})

    assert prices(client) == []
    client.post("/api/logout")
    client.post("/api/login", json=ANNA)
    assert prices(client) == [5500]


def test_failed_registration_keeps_the_guest_and_the_history(client):
    client.post("/api/register", json=ANNA)
    client.post("/api/logout")
    client.post("/api/guest")
    save(client, 5500)

    response = client.post("/api/register", json=ANNA)

    assert response.status_code == 409
    assert client.get("/api/me").json()["guest"] is True
    assert prices(client) == [5500]


def test_guest_can_open_the_login_page_to_register(client):
    client.post("/api/guest")

    response = client.get("/login", follow_redirects=False)

    assert response.status_code == 200


def test_registered_user_is_sent_from_login_to_the_tool(client):
    client.post("/api/register", json=ANNA)

    response = client.get("/login", follow_redirects=False)

    assert (response.status_code, response.headers["location"]) == (303, "/app")
