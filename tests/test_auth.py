from datetime import datetime, timedelta, timezone

import pytest

from app.auth import AuthStore, LoginTaken, hash_password, parse_credentials, verify_password
from app.db import open_database
from app.errors import InputError


def test_password_hash_is_not_the_password_and_verifies():
    stored = hash_password("секрет-123")

    assert "секрет-123" not in stored
    assert stored.startswith("scrypt$")
    assert verify_password("секрет-123", stored) is True
    assert verify_password("секрет-124", stored) is False


def test_same_password_gets_different_hashes():
    assert hash_password("password1") != hash_password("password1")


@pytest.mark.parametrize("stored", ["", "plain", "scrypt$1$2", "scrypt$x$y$z$!!$!!"])
def test_broken_stored_hash_never_verifies(stored):
    assert verify_password("password1", stored) is False


class Clock:
    def __init__(self):
        self.now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.now


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def store(database, clock):
    return AuthStore(database, session_ttl=timedelta(days=7), now=clock)


def test_registered_user_can_log_in(store):
    created = store.register("anna", "password1")

    assert store.authenticate("anna", "password1") == created
    assert store.authenticate("anna", "wrong-pass") is None
    assert store.authenticate("boris", "password1") is None


def test_login_is_unique_regardless_of_case(store):
    store.register("Anna", "password1")

    with pytest.raises(LoginTaken):
        store.register("anna", "password2")
    assert store.authenticate("ANNA", "password1").login == "Anna"


def test_password_is_stored_hashed(store, database):
    store.register("anna", "password1")

    with database.transaction() as db:
        (stored,) = db.one("select password_hash from users")
    assert "password1" not in stored
    assert verify_password("password1", stored)


def test_session_token_identifies_user_until_logout(store):
    user = store.register("anna", "password1")
    token = store.open_session(user)

    assert store.user_for_session(token) == user
    store.close_session(token)
    assert store.user_for_session(token) is None


def test_session_expires(store, clock):
    token = store.open_session(store.register("anna", "password1"))

    clock.now += timedelta(days=7, seconds=1)

    assert store.user_for_session(token) is None


def test_unknown_or_empty_token_has_no_user(store):
    assert store.user_for_session("no-such-token") is None
    assert store.user_for_session(None) is None


def test_reopening_the_database_keeps_users(store, database, database_target, clock):
    store.register("anna", "password1")
    database.close()

    reopened = open_database(*database_target)
    try:
        again = AuthStore(reopened, session_ttl=timedelta(days=7), now=clock)
        assert again.authenticate("anna", "password1") is not None
    finally:
        reopened.close()


def test_valid_credentials_are_parsed():
    assert parse_credentials({"login": " anna_1 ", "password": "password1"}) == ("anna_1", "password1")


@pytest.mark.parametrize("login", ["", "ab", "a" * 65, "anna smith", "anna!", "<b>", None])
def test_bad_login_is_rejected(login):
    with pytest.raises(InputError) as caught:
        parse_credentials({"login": login, "password": "password1"})

    assert caught.value.field == "login"


@pytest.mark.parametrize("password", ["", "short", None, 12345678, "x" * 129])
def test_bad_password_is_rejected(password):
    with pytest.raises(InputError) as caught:
        parse_credentials({"login": "anna", "password": password})

    assert caught.value.field == "password"


def test_cyrillic_login_is_allowed():
    assert parse_credentials({"login": "Анна-К", "password": "password1"})[0] == "Анна-К"


def test_guest_accounts_are_unique_and_have_no_usable_password(store):
    first, second = store.create_guest(), store.create_guest()

    assert first.login.startswith("гость-") and second.login.startswith("гость-")
    assert first.login != second.login
    assert store.authenticate(first.login, "") is None


def test_demo_account_is_created_once(store):
    store.ensure_user("jury", "demo-password-1")
    store.ensure_user("jury", "demo-password-1")

    assert store.authenticate("jury", "demo-password-1").login == "jury"


@pytest.mark.parametrize("login", ["manager@reshis.aero", "anna+test@mail.ru", "a" * 64])
def test_email_can_be_a_login(login):
    assert parse_credentials({"login": login, "password": "password1"})[0] == login


def test_repeated_password_must_match():
    with pytest.raises(InputError) as caught:
        parse_credentials({"login": "anna", "password": "password1", "password2": "password2"})

    assert (caught.value.field, caught.value.message) == ("password2", "Пароли не совпадают.")


def test_repeated_password_is_optional_for_api_clients():
    assert parse_credentials({"login": "anna", "password": "password1", "password2": "password1"}) == ("anna", "password1")
