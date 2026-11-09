"""Источники прогноза: файл организаторов и файл нашей ML-модели.

Файл ML-модели может появиться позже или поменяться, пока сервер работает:
каталог перечитывается, когда меняется время изменения файла.
"""
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from app.catalog import Catalog, CatalogError, load_flights, load_routes
from app.errors import InputError

ORGANIZERS = "organizers"
ML = "ml"
SOURCE_NAMES = {ORGANIZERS: "Прогноз организаторов", ML: "Наша ML-модель"}


@dataclass(frozen=True)
class SourceInfo:
    id: str
    name: str
    file: str
    available: bool
    detail: str


class ForecastSources:
    def __init__(self, routes_path: Path, paths: Mapping[str, Path]):
        self.routes_name = routes_path.name
        self.routes = load_routes(routes_path)
        self.paths = dict(paths)
        self._cache: dict[str, tuple[int, Catalog]] = {}
        self._lock = threading.Lock()

    def catalog(self, source_id: str) -> Catalog:
        if source_id not in self.paths:
            raise InputError(
                "source",
                f"Неизвестный источник прогноза «{source_id}». Можно: {', '.join(self.paths)}.",
            )
        path = self.paths[source_id]
        try:
            stamp = path.stat().st_mtime_ns
        except FileNotFoundError:
            raise InputError("source", f"{self.name(source_id)}: файла {path.name} пока нет.") from None
        with self._lock:
            cached = self._cache.get(source_id)
            if cached and cached[0] == stamp:
                return cached[1]
            try:
                catalog = load_flights(path, self.routes, self.routes_name)
            except CatalogError as error:
                raise InputError("source", f"{self.name(source_id)}: {error}") from None
            self._cache[source_id] = (stamp, catalog)
            return catalog

    def default_source(self) -> str:
        """Наша ML-модель, когда её файл есть и читается; иначе прогноз организаторов."""
        try:
            self.catalog(ML)
        except InputError:
            return ORGANIZERS
        return ML

    def describe(self) -> list[SourceInfo]:
        return [self._info(source_id) for source_id in self.paths]

    def name(self, source_id: str) -> str:
        return SOURCE_NAMES.get(source_id, source_id)

    def _info(self, source_id: str) -> SourceInfo:
        path = self.paths[source_id]
        try:
            catalog = self.catalog(source_id)
        except InputError as error:
            return SourceInfo(source_id, self.name(source_id), path.name, False, error.message)
        return SourceInfo(source_id, self.name(source_id), path.name, True, f"рейсов в файле: {len(catalog.flights)}")
