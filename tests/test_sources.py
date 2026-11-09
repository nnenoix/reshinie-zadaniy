import os
import shutil
from datetime import date

import pytest

from app.errors import InputError
from app.sources import ML, ORGANIZERS, ForecastSources

HEADER = "route,date,seats," + ",".join(f"0.{q}_base_demand" for q in range(1, 10)) + "\n"


def one_flight_file(path, demand: int):
    path.write_text(HEADER + "MOW-AER,2026-06-01,900," + ",".join([str(demand)] * 9) + "\n", encoding="utf-8")


@pytest.fixture
def sources(tmp_path, real_routes_csv, real_forecast_csv):
    return ForecastSources(real_routes_csv, {ORGANIZERS: real_forecast_csv, ML: tmp_path / "my_forecast.csv"})


def source_error(sources, source_id) -> InputError:
    with pytest.raises(InputError) as caught:
        sources.catalog(source_id)
    return caught.value


def test_organizers_forecast_is_available(sources):
    assert len(sources.catalog(ORGANIZERS).flights) == 155


def test_missing_ml_file_is_reported_in_russian(sources):
    error = source_error(sources, ML)

    assert error.field == "source"
    assert error.message == "Наша ML-модель: файла my_forecast.csv пока нет."


def test_sources_list_shows_availability(sources):
    listed = {s.id: (s.name, s.available) for s in sources.describe()}

    assert listed == {ORGANIZERS: ("Прогноз организаторов", True), ML: ("Наша ML-модель", False)}


def test_ml_file_that_appears_later_is_picked_up(sources, tmp_path, real_forecast_csv):
    source_error(sources, ML)

    shutil.copy(real_forecast_csv, tmp_path / "my_forecast.csv")

    assert len(sources.catalog(ML).flights) == 155


def test_changed_ml_file_is_reloaded(sources, tmp_path):
    path = tmp_path / "my_forecast.csv"
    one_flight_file(path, 700)
    assert sources.catalog(ML).find_flight("MOW-AER", date(2026, 6, 1)).base_demand[50] == 700

    one_flight_file(path, 800)
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))

    assert sources.catalog(ML).find_flight("MOW-AER", date(2026, 6, 1)).base_demand[50] == 800


def test_broken_ml_file_is_reported_with_line(sources, tmp_path):
    (tmp_path / "my_forecast.csv").write_text(HEADER + "MOW-AER,2026-06-01,много" + ",1" * 9 + "\n", encoding="utf-8")

    error = source_error(sources, ML)

    assert error.field == "source"
    assert "my_forecast.csv, строка 2" in error.message


def test_ml_file_with_part_of_routes_limits_cities(sources, tmp_path):
    one_flight_file(tmp_path / "my_forecast.csv", 700)

    assert sources.catalog(ML).destinations("Москва") == ["Сочи"]


def test_unknown_source_is_rejected(sources):
    error = source_error(sources, "excel")

    assert error.field == "source"
    assert error.message == "Неизвестный источник прогноза «excel». Можно: organizers, ml."


def test_default_source_is_organizers_until_ml_file_appears(sources, tmp_path, real_forecast_csv):
    assert sources.default_source() == ORGANIZERS

    shutil.copy(real_forecast_csv, tmp_path / "my_forecast.csv")

    assert sources.default_source() == ML


def test_broken_ml_file_keeps_organizers_as_default(sources, tmp_path):
    (tmp_path / "my_forecast.csv").write_text("сломано", encoding="utf-8")

    assert sources.default_source() == ORGANIZERS
