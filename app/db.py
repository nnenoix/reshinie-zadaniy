"""Соединение с SQLite. Каждое действие открывает своё соединение,
поэтому хранилища можно вызывать из разных потоков сервера."""
import sqlite3
from contextlib import closing
from pathlib import Path


class Transaction:
    """Соединение, которое фиксирует изменения и закрывается при выходе из with."""

    def __init__(self, path: Path):
        self.connection = sqlite3.connect(path)
        self.connection.execute("pragma foreign_keys = on")

    def __enter__(self) -> sqlite3.Connection:
        return self.connection.__enter__()

    def __exit__(self, *exc) -> None:
        with closing(self.connection):
            self.connection.__exit__(*exc)


def prepare(path: Path, schema: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with Transaction(path) as db:
        db.executescript(schema)
