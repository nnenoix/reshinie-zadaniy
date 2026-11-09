from datetime import date

import pytest

from app.catalog import CatalogError, load_catalog

ROUTES_HEADER = "route,name,base_price,cost_per_passenger,price_sensitivity,price_min,price_max\n"
FORECAST_HEADER = "route,date,seats," + ",".join(
    f"0.{q}_base_demand,0.{q}_price,0.{q}_price_demand" for q in range(1, 10)
) + "\n"


def forecast_row(route: str, day: str, seats: int, demands: list[float]) -> str:
    cells = ",".join(f"{d},9000,{d}" for d in demands)
    return f"{route},{day},{seats},{cells}\n"


def write(tmp_path, name: str, text: str):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_real_files_load_all_routes_and_flights(real_routes_csv, real_forecast_csv):
    catalog = load_catalog(real_routes_csv, real_forecast_csv)

    assert len(catalog.routes) == 5
    assert len(catalog.flights) == 155
    assert catalog.origins() == ["Москва"]
    assert catalog.destinations("Москва") == [
        "Сочи", "Санкт-Петербург", "Калининград", "Новосибирск", "Минеральные Воды",
    ]


def test_finds_route_by_city_names(real_routes_csv, real_forecast_csv):
    catalog = load_catalog(real_routes_csv, real_forecast_csv)

    route = catalog.find_route("Москва", "Санкт-Петербург")

    assert route.code == "MOW-LED"
    assert route.base_price == 5500
    assert route.price_sensitivity == pytest.approx(0.294)


def test_finds_flight_by_route_and_date(real_routes_csv, real_forecast_csv):
    catalog = load_catalog(real_routes_csv, real_forecast_csv)

    flight = catalog.find_flight("MOW-AER", date(2026, 6, 1))

    assert flight.seats == 900
    assert flight.base_demand[10] == 656
    assert flight.base_demand[50] == 775
    assert flight.base_demand[90] == 923


def test_reports_date_range_of_a_route(real_routes_csv, real_forecast_csv):
    catalog = load_catalog(real_routes_csv, real_forecast_csv)

    assert catalog.date_range("MOW-OVB") == (date(2026, 6, 1), date(2026, 7, 1))


def test_unknown_route_and_date_are_none(real_routes_csv, real_forecast_csv):
    catalog = load_catalog(real_routes_csv, real_forecast_csv)

    assert catalog.find_route("Москва", "Париж") is None
    assert catalog.find_flight("MOW-AER", date(2026, 5, 31)) is None


def test_fractional_demand_from_ml_forecast_is_accepted(tmp_path):
    routes = write(tmp_path, "routes.csv", ROUTES_HEADER + "MOW-AER,Москва — Сочи,9000,4200,0.141,5400,18000\n")
    forecast = write(tmp_path, "my_forecast.csv", FORECAST_HEADER + forecast_row(
        "MOW-AER", "2026-06-01", 900, [600.5, 650, 700, 720, 774.25, 800, 830, 860, 920]))

    catalog = load_catalog(routes, forecast)

    assert catalog.find_flight("MOW-AER", date(2026, 6, 1)).base_demand[50] == 774.25


def test_missing_column_is_reported_by_name(tmp_path):
    routes = write(tmp_path, "routes.csv", ROUTES_HEADER + "MOW-AER,Москва — Сочи,9000,4200,0.141,5400,18000\n")
    forecast = write(tmp_path, "f.csv", "route,date,seats\nMOW-AER,2026-06-01,900\n")

    with pytest.raises(CatalogError, match="0.1_base_demand"):
        load_catalog(routes, forecast)


def test_forecast_for_unknown_route_is_an_error(tmp_path):
    routes = write(tmp_path, "routes.csv", ROUTES_HEADER + "MOW-AER,Москва — Сочи,9000,4200,0.141,5400,18000\n")
    forecast = write(tmp_path, "f.csv", FORECAST_HEADER + forecast_row("MOW-XXX", "2026-06-01", 100, [1] * 9))

    with pytest.raises(CatalogError, match="MOW-XXX"):
        load_catalog(routes, forecast)


def test_broken_number_is_reported_with_line(tmp_path):
    routes = write(tmp_path, "routes.csv", ROUTES_HEADER + "MOW-AER,Москва — Сочи,9000,4200,0.141,5400,18000\n")
    forecast = write(tmp_path, "f.csv", FORECAST_HEADER + forecast_row("MOW-AER", "2026-06-01", "много", [1] * 9))

    with pytest.raises(CatalogError, match="строка 2"):
        load_catalog(routes, forecast)


def test_missing_file_is_reported(tmp_path, real_routes_csv):
    with pytest.raises(CatalogError, match="нет_такого.csv"):
        load_catalog(real_routes_csv, tmp_path / "нет_такого.csv")


def test_route_has_cost_per_passenger(real_routes_csv, real_forecast_csv):
    catalog = load_catalog(real_routes_csv, real_forecast_csv)

    assert catalog.routes["MOW-LED"].cost_per_passenger == 2600


def test_flight_keeps_median_price_from_file(real_routes_csv, real_forecast_csv):
    catalog = load_catalog(real_routes_csv, real_forecast_csv)

    assert catalog.find_flight("MOW-AER", date(2026, 6, 1)).file_price == 9347


def test_file_price_is_optional(tmp_path):
    routes = write(tmp_path, "routes.csv", ROUTES_HEADER + "MOW-AER,Москва — Сочи,9000,4200,0.141,5400,18000\n")
    header = "route,date,seats," + ",".join(f"0.{q}_base_demand" for q in range(1, 10)) + "\n"
    forecast = write(tmp_path, "f.csv", header + "MOW-AER,2026-06-01,900," + ",".join(["700"] * 9) + "\n")

    flight = load_catalog(routes, forecast).find_flight("MOW-AER", date(2026, 6, 1))

    assert flight.file_price is None
    assert flight.base_demand[50] == 700


def test_flights_of_a_route_are_sorted_by_date(real_routes_csv, real_forecast_csv):
    catalog = load_catalog(real_routes_csv, real_forecast_csv)

    days = [f.date for f in catalog.flights_for("MOW-LED")]

    assert len(days) == 31
    assert days == sorted(days)
    assert days[0] == date(2026, 6, 1) and days[-1] == date(2026, 7, 1)
