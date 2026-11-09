from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

LOGIN = {"login": "anna", "password": "password1"}
CSRF_ERROR = "Запрос отклонён: нет защитного токена. Обновите страницу и повторите."


class Clock:
    def __init__(self):
        self.now = datetime(2026, 6, 12, 9, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.now


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def raw_client(settings, clock):
    """Клиент без CSRF-заголовка."""
    with TestClient(create_app(settings, now=clock)) as client:
        yield client


@pytest.fixture
def client(raw_client):
    raw_client.headers["X-CSRF-Token"] = raw_client.get("/api/csrf").json()["token"]
    return raw_client


# --- CSRF ---

def test_post_without_csrf_token_is_rejected(raw_client):
    response = raw_client.post("/api/register", json=LOGIN)

    assert response.status_code == 403
    assert response.json() == {"detail": CSRF_ERROR, "field": None}


def test_post_with_wrong_csrf_token_is_rejected(raw_client):
    raw_client.get("/api/csrf")

    response = raw_client.post("/api/register", json=LOGIN, headers={"X-CSRF-Token": "wrong-token"})

    assert response.status_code == 403


def test_post_with_matching_token_passes(client):
    assert client.post("/api/register", json=LOGIN).status_code == 201


def test_get_requests_need_no_token(raw_client):
    assert raw_client.get("/api/routes").status_code == 200


def test_foreign_origin_is_rejected(client):
    response = client.post("/api/register", json=LOGIN, headers={"Origin": "https://evil.example"})

    assert response.status_code == 403
    assert response.json()["detail"] == "Запрос с чужого сайта отклонён."


def test_same_origin_is_accepted(client):
    response = client.post("/api/register", json=LOGIN, headers={"Origin": "http://testserver"})

    assert response.status_code == 201


def test_page_sets_csrf_cookie_readable_by_script(raw_client):
    response = raw_client.get("/")

    cookie = response.headers["set-cookie"].lower()
    assert "csrf_token=" in cookie and "samesite=strict" in cookie
    assert "httponly" not in cookie


# --- заголовки безопасности ---

def test_security_headers_on_page_and_api(raw_client):
    for path in ("/", "/api/routes"):
        headers = raw_client.get(path).headers
        csp = headers["content-security-policy"]
        assert "default-src 'self'" in csp and "frame-ancestors 'none'" in csp and "object-src 'none'" in csp
        assert headers["x-content-type-options"] == "nosniff"
        assert headers["x-frame-options"] == "DENY"
        assert headers["referrer-policy"] == "same-origin"
        assert "strict-transport-security" not in headers


def test_api_responses_are_not_cached(raw_client):
    assert raw_client.get("/api/routes").headers["cache-control"] == "no-store"


def test_docs_get_their_own_policy(raw_client):
    csp = raw_client.get("/docs").headers["content-security-policy"]

    assert "https://cdn.jsdelivr.net" in csp


def test_hsts_only_over_https(settings):
    secure = Settings(**{**settings.__dict__, "cookie_secure": True})
    with TestClient(create_app(secure), base_url="https://testserver") as client:
        assert client.get("/").headers["strict-transport-security"].startswith("max-age=")


# --- ограничение попыток входа ---

def register_and_logout(client):
    client.post("/api/register", json=LOGIN)
    client.post("/api/logout")


def test_sixth_attempt_after_five_wrong_passwords_is_blocked(client, clock):
    register_and_logout(client)
    for _ in range(5):
        assert client.post("/api/login", json={**LOGIN, "password": "wrong-pass"}).status_code == 401

    response = client.post("/api/login", json=LOGIN)

    assert response.status_code == 429
    assert response.json()["detail"] == "Слишком много неудачных попыток входа. Попробуйте через 5 мин."
    assert response.headers["retry-after"] == "300"


def test_login_works_again_after_the_window(client, clock):
    register_and_logout(client)
    for _ in range(5):
        client.post("/api/login", json={**LOGIN, "password": "wrong-pass"})

    clock.now += timedelta(minutes=5, seconds=1)

    assert client.post("/api/login", json=LOGIN).status_code == 200


def test_successful_login_resets_the_counter(client):
    register_and_logout(client)
    for _ in range(4):
        client.post("/api/login", json={**LOGIN, "password": "wrong-pass"})
    client.post("/api/login", json=LOGIN)
    client.post("/api/logout")

    for _ in range(4):
        client.post("/api/login", json={**LOGIN, "password": "wrong-pass"})

    assert client.post("/api/login", json=LOGIN).status_code == 200


def test_signups_from_one_address_are_limited(settings):
    limited = Settings(**{**settings.__dict__, "signup_limit": 2})
    with TestClient(create_app(limited)) as client:
        client.headers["X-CSRF-Token"] = client.get("/api/csrf").json()["token"]
        assert client.post("/api/guest").status_code == 201
        assert client.post("/api/register", json=LOGIN).status_code == 201

        response = client.post("/api/guest")

    assert response.status_code == 429
    assert response.json()["detail"].startswith("Слишком много новых аккаунтов с одного адреса.")
