from datetime import date, datetime, timedelta, timezone

import pytest

from app.history import HistoryEntry, HistoryStore, history_csv

START = datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc)


def entry(minutes: int = 0, **changes) -> HistoryEntry:
    fields = dict(
        created_at=START + timedelta(minutes=minutes), source="organizers", route_code="MOW-LED",
        origin="Москва", destination="Санкт-Петербург", flight_date=date(2026, 6, 12),
        price=5500.0, seats=1440, wanted=1069.0, sold=1069.0,
    )
    return HistoryEntry(**{**fields, **changes})


@pytest.fixture
def store(tmp_path):
    return HistoryStore(tmp_path / "app.db")


def test_latest_entries_are_newest_first_and_limited(store):
    for minute in range(12):
        store.add(user_id=1, entry=entry(minute, price=5000.0 + minute))

    latest = store.latest(user_id=1, limit=10)

    assert [e.price for e in latest] == [5011.0 - i for i in range(10)]
    assert all(e.id is not None for e in latest)


def test_users_see_only_their_own_history(store):
    store.add(user_id=1, entry=entry(price=5000.0))
    store.add(user_id=2, entry=entry(price=7000.0))

    assert [e.price for e in store.latest(user_id=1)] == [5000.0]
    assert [e.price for e in store.latest(user_id=2)] == [7000.0]


def test_entry_round_trips_through_the_database(store, tmp_path):
    saved = store.add(user_id=1, entry=entry())

    (loaded,) = HistoryStore(tmp_path / "app.db").latest(user_id=1)

    assert loaded == saved


def test_csv_opens_in_russian_excel(store):
    store.add(user_id=1, entry=entry(price=5500.5, wanted=1068.85, sold=1068.85))

    text = history_csv(store.all(user_id=1))

    lines = text.splitlines()
    assert text.startswith("﻿")
    assert lines[0] == "﻿Время расчёта (UTC);Источник;Маршрут;Откуда;Куда;Дата вылета;Цена, ₽;Мест;Желают;Купят;Загрузка, %"
    assert lines[1] == "2026-06-01 09:00;organizers;MOW-LED;Москва;Санкт-Петербург;2026-06-12;5500,5;1440;1068,85;1068,85;74,23"


def test_csv_of_empty_history_has_only_header(store):
    assert len(history_csv(store.all(user_id=1)).splitlines()) == 1
