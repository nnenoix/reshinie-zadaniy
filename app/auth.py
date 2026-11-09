"""Регистрация, вход и сессии.

Пароли хранятся как scrypt-хеш с солью. В браузер уходит случайный токен сессии
(в httpOnly-cookie), а в базе лежит только его SHA-256, поэтому утечка базы
не даёт войти ни по паролю, ни по сессии.
"""
import base64
import hashlib
import hmac
import re
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from app.db import Transaction, prepare
from app.errors import InputError

SCRYPT_N, SCRYPT_R, SCRYPT_P, SCRYPT_LEN = 2**14, 8, 1, 32
LOGIN_PATTERN = re.compile(r"[A-Za-zА-Яа-яЁё0-9_.@+\-]{3,64}")  # логин или email
PASSWORD_MIN, PASSWORD_MAX = 8, 128

SCHEMA = """
create table if not exists users (
    id integer primary key,
    login text not null,
    login_key text not null unique,
    password_hash text not null,
    created_at integer not null
);
create table if not exists sessions (
    token_hash text primary key,
    user_id integer not null references users(id) on delete cascade,
    expires_at integer not null
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


def parse_credentials(data: Any) -> tuple[str, str]:
    if not isinstance(data, dict):
        raise InputError(None, "Запрос должен быть JSON-объектом с полями login и password.")
    login = data.get("login")
    password = data.get("password")
    login = login.strip() if isinstance(login, str) else ""
    if not LOGIN_PATTERN.fullmatch(login):
        raise InputError(
            "login",
            "Логин или email: от 3 до 64 символов — буквы, цифры, точка, дефис, подчёркивание, @ или +.",
        )
    if not isinstance(password, str) or not PASSWORD_MIN <= len(password) <= PASSWORD_MAX:
        raise InputError("password", f"Пароль: от {PASSWORD_MIN} до {PASSWORD_MAX} символов.")
    if "password2" in data and data.get("password2") != password:
        raise InputError("password2", "Пароли не совпадают.")
    return login, password


class AuthStore:
    """Пользователи и сессии в SQLite. Каждое действие открывает своё соединение,
    поэтому хранилище можно вызывать из разных потоков сервера."""

    def __init__(
        self,
        db_path: Path,
        session_ttl: timedelta,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ):
        self.db_path = Path(db_path)
        self.session_ttl = session_ttl
        self.now = now
        prepare(self.db_path, SCHEMA)

    def register(self, login: str, password: str) -> User:
        try:
            with self._connect() as db:
                cursor = db.execute(
                    "insert into users (login, login_key, password_hash, created_at) values (?, ?, ?, ?)",
                    (login, login.casefold(), hash_password(password), self._timestamp()),
                )
        except sqlite3.IntegrityError:
            raise LoginTaken(login) from None
        return User(id=cursor.lastrowid, login=login)

    def create_guest(self) -> User:
        """Гостевой аккаунт для жюри: случайный логин и пароль, который никто не знает."""
        while True:
            try:
                return self.register(f"гость-{secrets.token_hex(3)}", secrets.token_urlsafe(32))
            except LoginTaken:
                continue

    def ensure_user(self, login: str, password: str) -> None:
        """Создаёт аккаунт, если его ещё нет (демо-вход). Повторный вызов ничего не меняет."""
        try:
            self.register(login, password)
        except LoginTaken:
            pass

    def authenticate(self, login: str, password: str) -> User | None:
        with self._connect() as db:
            row = db.execute(
                "select id, login, password_hash from users where login_key = ?",
                (login.casefold(),),
            ).fetchone()
        if row is None or not verify_password(password, row[2]):
            return None
        return User(id=row[0], login=row[1])

    def open_session(self, user: User) -> str:
        token = secrets.token_urlsafe(32)
        expires_at = self._timestamp(self.now() + self.session_ttl)
        with self._connect() as db:
            db.execute("delete from sessions where expires_at <= ?", (self._timestamp(),))
            db.execute(
                "insert into sessions (token_hash, user_id, expires_at) values (?, ?, ?)",
                (_token_hash(token), user.id, expires_at),
            )
        return token

    def user_for_session(self, token: str | None) -> User | None:
        if not token:
            return None
        with self._connect() as db:
            row = db.execute(
                "select users.id, users.login from sessions join users on users.id = sessions.user_id "
                "where sessions.token_hash = ? and sessions.expires_at > ?",
                (_token_hash(token), self._timestamp()),
            ).fetchone()
        return User(id=row[0], login=row[1]) if row else None

    def close_session(self, token: str | None) -> None:
        if not token:
            return
        with self._connect() as db:
            db.execute("delete from sessions where token_hash = ?", (_token_hash(token),))

    def _connect(self) -> Transaction:
        return Transaction(self.db_path)

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
