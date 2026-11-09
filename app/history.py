"""История расчётов пользователя и её выгрузка в CSV."""
import csv
import io
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone

from app.db import Database, prepare

SCHEMA = """
create table if not exists calculations (
    id {id},
    user_id bigint not null,
    created_at bigint not null,
    source text not null,
    route_code text not null,
    origin text not null,
    destination text not null,
    flight_date text not null,
    price {real} not null,
    seats integer not null,
    wanted {real} not null,
    sold {real} not null
);
create index if not exists calculations_by_user on calculations (user_id, id);
"""
COLUMNS = "id, created_at, source, route_code, origin, destination, flight_date, price, seats, wanted, sold"
CSV_HEADER = ["Время расчёта (UTC)", "Источник", "Маршрут", "Откуда", "Куда", "Дата вылета",
              "Цена, ₽", "Мест", "Желают", "Купят", "Загрузка, %"]


@dataclass(frozen=True)
class HistoryEntry:
    created_at: datetime
    source: str
    route_code: str
    origin: str
    destination: str
    flight_date: date
    price: float
    seats: int
    wanted: float
    sold: float
    id: int | None = None

    @property
    def load(self) -> float:
        return self.sold / self.seats


class HistoryStore:
    def __init__(self, database: Database):
        self.database = database
        prepare(database, SCHEMA)

    def add(self, user_id: int, entry: HistoryEntry) -> HistoryEntry:
        with self.database.transaction() as db:
            (entry_id,) = db.one(
                "insert into calculations (user_id, created_at, source, route_code, origin, destination,"
                " flight_date, price, seats, wanted, sold) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) returning id",
                (user_id, int(entry.created_at.timestamp()), entry.source, entry.route_code, entry.origin,
                 entry.destination, entry.flight_date.isoformat(), entry.price, entry.seats, entry.wanted, entry.sold),
            )
        return replace(entry, id=entry_id)

    def latest(self, user_id: int, limit: int = 10) -> list[HistoryEntry]:
        return self._select(user_id, "limit ?", (limit,))

    def all(self, user_id: int) -> list[HistoryEntry]:
        return self._select(user_id, "", ())

    def _select(self, user_id: int, tail: str, args: tuple) -> list[HistoryEntry]:
        with self.database.transaction() as db:
            rows = db.all(
                f"select {COLUMNS} from calculations where user_id = ? order by id desc {tail}",
                (user_id, *args),
            )
        return [_entry(row) for row in rows]


def history_csv(entries: list[HistoryEntry]) -> str:
    """CSV для русского Excel: BOM, точка с запятой, десятичная запятая."""
    out = io.StringIO()
    out.write("﻿")
    writer = csv.writer(out, delimiter=";", lineterminator="\r\n")
    writer.writerow(CSV_HEADER)
    for e in entries:
        writer.writerow([
            e.created_at.strftime("%Y-%m-%d %H:%M"), e.source, e.route_code, e.origin, e.destination,
            e.flight_date.isoformat(), _number(e.price), e.seats, _number(e.wanted), _number(e.sold),
            _number(e.load * 100),
        ])
    return out.getvalue()


def _number(value: float) -> str:
    return f"{round(value, 2):g}".replace(".", ",")


def _entry(row: tuple) -> HistoryEntry:
    (id_, created_at, source, route_code, origin, destination, flight_date, price, seats, wanted, sold) = row
    return HistoryEntry(
        id=id_,
        created_at=datetime.fromtimestamp(created_at, tz=timezone.utc),
        source=source,
        route_code=route_code,
        origin=origin,
        destination=destination,
        flight_date=date.fromisoformat(flight_date),
        price=price,
        seats=seats,
        wanted=wanted,
        sold=sold,
    )
