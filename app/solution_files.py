"""Блок «Файлы решения» на витрине.

Адреса файлов задаются здесь (по умолчанию) или переменными окружения LINK_*,
вёрстку при этом трогать не нужно. Строка без адреса не кликается и говорит,
что файл лежит в папке сдачи.
"""
from dataclasses import dataclass
from html import escape
from typing import Mapping

GITHUB = "https://github.com/nnenoix/reshinie-zadaniy"
NO_LINK = "в папке сдачи"


@dataclass(frozen=True)
class SolutionFile:
    key: str
    name: str
    description: str
    tag: str
    env: str
    default_url: str | None = None


FILES = (
    SolutionFile("bia", "Титаренко_Егор_Константинович_БиА.pdf",
                 "Решение блока «Бизнес и аналитика», 5 схем", "PDF", "LINK_BIA_PDF"),
    SolutionFile("notebook", "Титаренко_Егор_Константинович_ml_demand_forecast.ipynb",
                 "Ноутбук ML-части: обучение, выбор модели, проверка на мае, бэктест", "IPYNB", "LINK_ML_NOTEBOOK"),
    SolutionFile("forecast", "Титаренко_Егор_Константинович_my_forecast.csv",
                 "Прогноз спроса и цен на июнь, его читает сервис", "CSV", "LINK_MY_FORECAST"),
    SolutionFile("code", "Код сервиса", "FastAPI, SQLite и Postgres, страница на JavaScript, тесты и README",
                 "GitHub", "LINK_CODE", GITHUB),
    SolutionFile("checks", "Титаренко_Егор_Константинович_Проверка.zip",
                 "proverka_bia.py и proverka_forecast.py с нужными файлами: "
                 "пересчёт чисел аналитики и проверка файла прогноза", "ZIP", "LINK_CHECK_SCRIPTS"),
    SolutionFile("video", "Видео", "До 3 минут", "Видео", "LINK_VIDEO"),
    SolutionFile("site", "Сайт", "Этот сервис", "Сайт", "LINK_SITE", "/"),
)


def safe_url(url: str) -> str | None:
    """Только адреса в интернете (http, https) и страницы этого сайта («/…»)."""
    url = url.strip()
    if url.startswith(("https://", "http://")) or (url.startswith("/") and not url.startswith("//")):
        return url
    return None


def file_links(env: Mapping[str, str]) -> dict[str, str]:
    links = {}
    for file in FILES:
        url = safe_url(env.get(file.env, "").strip() or file.default_url or "")
        if url:
            links[file.key] = url
    return links


def breakable(name: str) -> str:
    """Длинное имя файла переносится после «_», а не посреди слова: «Титаренко_<wbr>Егор_<wbr>…»."""
    return escape(name).replace("_", "_<wbr>")


def files_html(links: Mapping[str, str]) -> str:
    rows = []
    for file in FILES:
        cells = (f'<span class="file__name">{breakable(file.name)}</span>'
                 f'<span class="file__desc">{escape(file.description)}</span>'
                 f'<span class="tag">{escape(file.tag)}</span>')
        url = safe_url(links.get(file.key, ""))
        if url:
            new_tab = ' target="_blank" rel="noopener"' if url.startswith("http") else ""
            rows.append(f'<a class="file" href="{escape(url, quote=True)}"{new_tab}>{cells}'
                        '<span class="file__open">Открыть</span></a>')
        else:
            rows.append(f'<div class="file is-pending">{cells}<span class="file__open">{NO_LINK}</span></div>')
    return "\n    ".join(rows)
