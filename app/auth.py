"""Регистрация, вход и сессии (SQLite или Postgres, см. app/db.py).

Пароли хранятся как scrypt-хеш с солью. В браузер уходит случайный токен сессии
(в httpOnly-cookie), а в базе лежит только его SHA-256, поэтому утечка базы
не даёт войти ни по паролю, ни по сессии.

Параметры scrypt (N=2^14, r=8, p=1) — сознательный выбор: каждая проверка берёт 16 МБ памяти,
а у бесплатного сервиса Render всего 512 МБ, так что N=2^15 и выше при нескольких входах
сразу рискуют уронить процесс. Проверка занимает около 50 мс.
"""
import base64
import functools
import hashlib
import hmac
import logging
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from app.db import Database, Duplicate, prepare
from app.errors import InputError

SCRYPT_N, SCRYPT_R, SCRYPT_P, SCRYPT_LEN = 2**14, 8, 1, 32
LOGIN_MIN, LOGIN_MAX = 3, 64
LOGIN_PATTERN = re.compile(rf"[A-Za-zА-Яа-яЁё0-9_.@+\-]{{{LOGIN_MIN},{LOGIN_MAX}}}")  # логин или email
PASSWORD_MIN, PASSWORD_MAX = 8, 128
GUEST_PREFIX = "гость-"
GUEST_HASH = "guest"  # не scrypt: под гостем по паролю не войти, и создание гостя не тратит scrypt
log = logging.getLogger("aviaprognoz.auth")

SCHEMA = """
create table if not exists users (
    id {id},
    login text not null,
    login_key text not null unique,
    password_hash text not null,
    created_at bigint not null
);
create table if not exists sessions (
    token_hash text primary key,
    user_id bigint not null references users(id) on delete cascade,
    expires_at bigint not null
);
"""


class LoginTaken(Exception):
    pass


@dataclass(frozen=True)
class User:
    id: int
    login: str


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = _scrypt(password, salt)
    return "$".join(["scrypt", _b64(salt), _b64(digest)])


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        return hmac.compare_digest(_scrypt(password, _unb64(salt)), _unb64(digest))
    except ValueError:
        return False


@functools.cache
def _dummy_hash() -> str:
    """Хеш, с которым сверяется пароль несуществующего логина: ответ идёт столько же, сколько с настоящим.
    Случайные соль и результат: ни один пароль к нему не подходит."""
    return "$".join(["scrypt", _b64(secrets.token_bytes(16)), _b64(secrets.token_bytes(SCRYPT_LEN))])


def is_guest(login: str) -> bool:
    return login.casefold().startswith(GUEST_PREFIX)


def parse_credentials(data: Any) -> tuple[str, str]:
    if not isinstance(data, dict):
        raise InputError(None, "Запрос должен быть JSON-объектом с полями login и password.")
    login = data.get("login")
    password = data.get("password")
    login = login.strip() if isinstance(login, str) else ""
    if not LOGIN_PATTERN.fullmatch(login):
        raise InputError(
            "login",
            f"Логин или email: от {LOGIN_MIN} до {LOGIN_MAX} символов — русские и латинские буквы, цифры, "
            "точка, дефис, подчёркивание, @ или +.",
        )
    if is_guest(login):
        raise InputError("login", f"Логины «{GUEST_PREFIX}…» заняты под гостевой вход.")
    if not isinstance(password, str) or not PASSWORD_MIN <= len(password) <= PASSWORD_MAX:
        raise InputError("password", f"Пароль: от {PASSWORD_MIN} до {PASSWORD_MAX} символов.")
    if "password2" in data and data.get("password2") != password:
        raise InputError("password2", "Пароли не совпадают.")
    return login, password


def parse_login_attempt(data: Any) -> tuple[str, str]:
    """Логин и пароль для входа. Слишком длинные отклоняются сразу: такой логин не может
    существовать, и его незачем держать в лимитере и писать в журнал."""
    data = data if isinstance(data, dict) else {}
    login = str(data.get("login") or "").strip()
    password = str(data.get("password") or "")
    if len(login) > LOGIN_MAX:
        raise InputError("login", f"Логин или email — не длиннее {LOGIN_MAX} символов.")
    if len(password) > PASSWORD_MAX:
        raise InputError("password", f"Пароль — не длиннее {PASSWORD_MAX} символов.")
    return login, password


class AuthStore:
    """Пользователи и сессии. Каждое действие — своя транзакция,
    поэтому хранилище можно вызывать из разных потоков сервера."""

    def __init__(
        self,
        database: Database,
        session_ttl: timedelta,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ):
        self.database = database
        self.session_ttl = session_ttl
        self.now = now
        prepare(database, SCHEMA)

    def register(self, login: str, password: str) -> User:
        """Занятость логина проверяется до scrypt: занятый логин не тратит процессор сервера."""
        if self._stored_hash(login) is not None:
            raise LoginTaken(login)
        return self._insert(login, hash_password(password))

    def create_guest(self) -> User:
        """Гостевой аккаунт для жюри: случайный логин, войти по паролю нельзя."""
        while True:
            try:
                return self._insert(f"{GUEST_PREFIX}{secrets.token_hex(3)}", GUEST_HASH)
            except LoginTaken:
                continue

    def ensure_user(self, login: str, password: str) -> None:
        """Демо-аккаунт: создаёт его или, если пароль в окружении сменили, обновляет хеш."""
        stored = self._stored_hash(login)
        if stored is None:
            self.register(login, password)
        elif not verify_password(password, stored):
            with self.database.transaction() as db:
                db.execute("update users set password_hash = ? where login_key = ?",
                           (hash_password(password), login.casefold()))
            log.warning("пароль аккаунта %r не совпадал с DEMO_PASSWORD и заменён на него", login)

    def authenticate(self, login: str, password: str) -> User | None:
        with self.database.transaction() as db:
            row = db.one("select id, login, password_hash from users where login_key = ?", (login.casefold(),))
        if row is None or row[2] == GUEST_HASH:
            verify_password(password, _dummy_hash())  # столько же времени, сколько у настоящего логина
            return None
        if not verify_password(password, row[2]):
            return None
        return User(id=row[0], login=row[1])

    def _stored_hash(self, login: str) -> str | None:
        with self.database.transaction() as db:
            row = db.one("select password_hash from users where login_key = ?", (login.casefold(),))
        return row[0] if row else None

    def _insert(self, login: str, password_hash: str) -> User:
        try:
            with self.database.transaction() as db:
                (user_id,) = db.one(
                    "insert into users (login, login_key, password_hash, created_at) values (?, ?, ?, ?) "
                    "returning id",
                    (login, login.casefold(), password_hash, self._timestamp()),
                )
        except Duplicate:  # логин заняли между проверкой и записью
            raise LoginTaken(login) from None
        return User(id=user_id, login=login)

    def open_session(self, user: User) -> str:
        token = secrets.token_urlsafe(32)
        expires_at = self._timestamp(self.now() + self.session_ttl)
        with self.database.transaction() as db:
            db.execute("delete from sessions where expires_at <= ?", (self._timestamp(),))
            db.execute(
                "insert into sessions (token_hash, user_id, expires_at) values (?, ?, ?)",
                (_token_hash(token), user.id, expires_at),
            )
        return token

    def user_for_session(self, token: str | None) -> User | None:
        if not token:
            return None
        with self.database.transaction() as db:
            row = db.one(
                "select users.id, users.login from sessions join users on users.id = sessions.user_id "
                "where sessions.token_hash = ? and sessions.expires_at > ?",
                (_token_hash(token), self._timestamp()),
            )
        return User(id=row[0], login=row[1]) if row else None

    def close_session(self, token: str | None) -> None:
        if not token:
            return
        with self.database.transaction() as db:
            db.execute("delete from sessions where token_hash = ?", (_token_hash(token),))

    def _timestamp(self, moment: datetime | None = None) -> int:
        return int((moment or self.now()).timestamp())


def _scrypt(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=SCRYPT_LEN
    )


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"), validate=True)
