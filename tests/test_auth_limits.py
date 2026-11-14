"""Лимиты входа и регистрации: гости, регистрации, подбор пароля, память и время ответа."""
import logging
import time
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import app.auth as auth_module
from app.auth import AuthStore, LoginTaken
from app.config import Settings, from_environment
from app.main import create_app

LOGIN = {"login": "anna", "password": "password1"}
WRONG = {**LOGIN, "password": "wrong-pass"}


class Clock:
    def __init__(self):
        self.now = datetime(2026, 6, 12, 9, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.now


@pytest.fixture
def clock():
    return Clock()


def make_client(settings, clock, **changes) -> TestClient:
    app = create_app(Settings(**{**settings.__dict__, **changes}), now=clock)
    client = TestClient(app)
    client.__enter__()
    client.headers["X-CSRF-Token"] = client.get("/api/csrf").json()["token"]
    return client


@pytest.fixture
def opened(settings, clock):
    clients = []

    def open_client(**changes) -> TestClient:
        clients.append(make_client(settings, clock, **changes))
        return clients[-1]

    yield open_client
    for client in clients:
        client.__exit__(None, None, None)


def new_guest(client):
    """Гость с чистого устройства: старая cookie сессии не передаётся."""
    client.cookies.delete("session")
    return client.post("/api/guest")


# --- пункт 1: гости и регистрации считаются отдельно ---

def test_default_limits_fit_a_jury_office_behind_one_address():
    defaults = from_environment({})

    assert (defaults.guest_limit, defaults.guest_minute_limit, defaults.signup_limit) == (300, 20, 30)


def test_limits_come_from_the_environment():
    env = from_environment({"GUEST_LIMIT": "50", "GUEST_MINUTE_LIMIT": "5", "SIGNUP_LIMIT": "7"})

    assert (env.guest_limit, env.guest_minute_limit, env.signup_limit) == (50, 5, 7)


def test_guests_have_their_own_hourly_limit(opened):
    client = opened(guest_limit=3, guest_minute_limit=100, signup_limit=100)

    codes = [new_guest(client).status_code for _ in range(4)]

    assert codes == [201, 201, 201, 429]
    assert new_guest(client).json()["detail"].startswith("Слишком много гостевых входов с одного адреса.")


def test_guests_are_limited_per_minute_too(opened, clock):
    client = opened(guest_limit=100, guest_minute_limit=2)

    codes = [new_guest(client).status_code for _ in range(3)]
    clock.now += timedelta(minutes=1, seconds=1)

    assert codes == [201, 201, 429]
    assert new_guest(client).status_code == 201


def test_used_up_guest_limit_does_not_block_registration(opened):
    client = opened(guest_limit=1, signup_limit=100)
    new_guest(client)
    assert new_guest(client).status_code == 429

    assert client.post("/api/register", json=LOGIN).status_code == 201


def test_registrations_have_their_own_limit(opened):
    client = opened(signup_limit=2, guest_limit=100)
    for login in ("anna", "boris"):
        client.post("/api/logout")
        assert client.post("/api/register", json={**LOGIN, "login": login}).status_code == 201
    client.post("/api/logout")

    response = client.post("/api/register", json={**LOGIN, "login": "vera"})

    assert response.status_code == 429
    assert response.json()["detail"].startswith("Слишком много регистраций с одного адреса.")
    assert new_guest(client).status_code == 201


def test_second_guest_click_returns_the_same_guest(opened):
    client = opened(guest_limit=1)
    first = client.post("/api/guest")

    second = client.post("/api/guest")

    assert (first.status_code, second.status_code) == (201, 200)
    assert second.json() == first.json()
    assert client.get("/api/me").json()["login"] == first.json()["login"]


def test_signed_in_user_asking_for_a_guest_gets_a_new_guest(opened):
    client = opened()
    client.post("/api/register", json=LOGIN)

    response = client.post("/api/guest")

    assert response.status_code == 201
    assert response.json()["login"].startswith("гость-")


# --- пункт 2: подбор пароля не закрывает аккаунт для владельца ---

def fail_from_many_addresses(client, times: int) -> list[int]:
    return [client.post("/api/login", json=WRONG, headers={"CF-Connecting-IP": f"203.0.113.{i}"}).status_code
            for i in range(times)]


def test_right_password_works_while_the_account_is_under_attack(opened):
    client = opened(client_ip_header="cf-connecting-ip", account_login_delay_seconds=0)
    client.post("/api/register", json=LOGIN)
    client.post("/api/logout")

    codes = fail_from_many_addresses(client, 12)
    response = client.post("/api/login", json=LOGIN, headers={"CF-Connecting-IP": "198.51.100.2"})

    assert codes == [401] * 12
    assert response.status_code == 200


def test_attempts_on_an_attacked_account_are_slowed_down(opened):
    client = opened(client_ip_header="cf-connecting-ip", account_login_limit=2, account_login_delay_seconds=0.4)
    client.post("/api/register", json=LOGIN)
    client.post("/api/logout")
    started = time.perf_counter()
    fail_from_many_addresses(client, 2)
    calm = time.perf_counter() - started

    started = time.perf_counter()
    response = client.post("/api/login", json=LOGIN, headers={"CF-Connecting-IP": "198.51.100.2"})
    slowed = time.perf_counter() - started

    assert calm < 0.4
    assert slowed >= 0.4
    assert response.status_code == 200


# --- пункт 4: длинные логины и тела не копятся в памяти ---

def test_too_long_login_is_rejected_before_the_limiter(opened):
    client = opened()

    response = client.post("/api/login", json={"login": "x" * 65, "password": "password1"})

    assert response.status_code == 422
    assert response.json()["field"] == "login"
    assert len(client.app.state.login_limiter) == 0
    assert len(client.app.state.account_limiter) == 0


def test_too_long_password_is_rejected_before_the_limiter(opened):
    client = opened()

    response = client.post("/api/login", json={"login": "anna", "password": "x" * 129})

    assert response.status_code == 422
    assert response.json()["field"] == "password"
    assert len(client.app.state.login_limiter) == 0


def test_rejected_login_is_not_written_to_the_log(opened):
    client = opened()
    records = []
    handler = logging.Handler()
    handler.emit = records.append
    logging.getLogger("aviaprognoz").addHandler(handler)
    try:
        client.post("/api/login", json={"login": "y" * 5000, "password": "password1"})
    finally:
        logging.getLogger("aviaprognoz").removeHandler(handler)

    assert all("y" * 65 not in record.getMessage() for record in records)


def test_huge_json_body_is_rejected(opened):
    client = opened()

    response = client.post("/api/login", content=b'{"login": "' + b"a" * 20_000 + b'"}',
                           headers={"Content-Type": "application/json"})

    assert response.status_code == 413
    assert response.json() == {"detail": "Запрос слишком большой: не больше 16 КБ.", "field": None}


def test_normal_body_still_passes_the_size_check(opened):
    client = opened()

    assert client.post("/api/register", json=LOGIN).status_code == 201


@pytest.fixture
def store(database, clock):
    return AuthStore(database, session_ttl=timedelta(days=7), now=clock)


def test_taken_login_is_found_before_hashing_the_password(store, monkeypatch):
    store.register("anna", "password1")

    def no_hashing(_password):
        raise AssertionError("scrypt для занятого логина не нужен")

    monkeypatch.setattr(auth_module, "hash_password", no_hashing)
    with pytest.raises(LoginTaken):
        store.register("ANNA", "password2")


def test_failed_registrations_count_toward_the_limit(opened):
    client = opened(signup_limit=2)
    client.post("/api/register", json=LOGIN)
    client.post("/api/logout")

    taken = client.post("/api/register", json=LOGIN)
    blocked = client.post("/api/register", json={**LOGIN, "login": "boris"})

    assert (taken.status_code, blocked.status_code) == (409, 429)


# --- пункт 5: время ответа не выдаёт, есть ли логин ---

def test_unknown_login_costs_one_scrypt_like_a_known_one(store, monkeypatch):
    store.register("anna", "password1")
    calls = []
    real = auth_module._scrypt
    monkeypatch.setattr(auth_module, "_scrypt", lambda password, salt: calls.append(1) or real(password, salt))

    store.authenticate("anna", "wrong-pass")
    known = len(calls)
    store.authenticate("nobody", "wrong-pass")

    assert known == 1
    assert len(calls) == 2


# --- пункт 15: DEMO_PASSWORD сменили в панели — пароль jury обновляется ---

def test_demo_password_change_rehashes_and_warns_without_the_password(store):
    store.ensure_user("jury", "old-password-1")
    records = []
    handler = logging.Handler()
    handler.emit = records.append
    logger = logging.getLogger("aviaprognoz.auth")
    logger.addHandler(handler)
    try:
        store.ensure_user("jury", "new-password-2")
    finally:
        logger.removeHandler(handler)

    assert store.authenticate("jury", "new-password-2").login == "jury"
    assert store.authenticate("jury", "old-password-1") is None
    assert [r.levelno for r in records] == [logging.WARNING]
    assert "jury" in records[0].getMessage()
    assert "new-password-2" not in records[0].getMessage()


def test_same_demo_password_changes_nothing_and_stays_quiet(store):
    store.ensure_user("jury", "demo-password-1")
    records = []
    handler = logging.Handler()
    handler.emit = records.append
    logger = logging.getLogger("aviaprognoz.auth")
    logger.addHandler(handler)
    try:
        store.ensure_user("jury", "demo-password-1")
    finally:
        logger.removeHandler(handler)

    assert records == []
    assert store.authenticate("jury", "demo-password-1").login == "jury"
