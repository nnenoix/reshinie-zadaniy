"""Страницы: витрина (публичная), вход и инструмент после входа.

Вёрстка отделена от логики: в HTML нет инлайн-стилей и инлайн-скриптов,
а числа витрины совпадают с расчётом (их проверяет tests/test_story.py
и тест /api/story в test_api_features.py).
"""
import re
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.solution_files import FILES

PROJECT = Path(__file__).resolve().parent.parent


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings), follow_redirects=False) as test_client:
        test_client.headers["X-CSRF-Token"] = test_client.get("/api/csrf").json()["token"]
        yield test_client


@pytest.fixture
def guest(client):
    assert client.post("/api/guest").status_code == 201
    return client


def page(client, path) -> str:
    response = client.get(path)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    return response.text


def test_landing_is_public(client):
    html = page(client, "/")

    assert "Цена из <span class=\"accent\">прогноза</span>, а не из правила" in html
    assert "[ ТУРНИР «РЕШИСЬ» / ТЕХНОЛОГИИ ]" in html


@pytest.mark.parametrize("number", ["705<small>", "1&nbsp;625<small>", "4<small>", "+6,7<small>", "83<small>"])
def test_landing_shows_key_numbers(client, number):
    assert number in page(client, "/")


def test_big_numbers_do_not_break_inside(client):
    # «1 625» не должно переноситься на «1» и «625»: внутри чисел только неразрывный пробел.
    numbers = re.findall(r'<dd class="metric__value[^"]*">([^<]*)<|<dd>([^<]*)<', page(client, "/"))
    for value in ("".join(pair) for pair in numbers):
        assert " " not in value, value


def full_suite_size() -> int:
    """Сколько тестов во всём наборе: столько и должно быть написано на витрине."""
    out = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"],
                         cwd=PROJECT, capture_output=True, text=True, encoding="utf-8", check=True).stdout
    return int(re.search(r"(\d+) tests? collected", out).group(1))


def test_landing_names_the_actual_number_of_tests(client):
    shown = re.findall(r"<span data-tests>(\d+)</span>", page(client, "/"))

    assert len(shown) == 3 and len(set(shown)) == 1
    assert int(shown[0]) == full_suite_size()


def test_best_price_on_landing_is_the_one_the_service_computes(client):
    html = page(client, "/")

    assert "5&nbsp;605<span class=\"metric__unit\">₽</span>" in html
    assert "лучшая цена 12 июня по нашей модели" in html
    assert "По нашей модели лучшая цена 5 605 ₽: +3 217 ₽ ожидаемой прибыли к базовой цене 5 500 ₽." in html
    assert "5 610" not in html
    # 5 614 ₽ — только с пометкой, что это прогноз организаторов
    for found in re.finditer("5 614", html):
        assert "прогнозу организаторов" in html[max(0, found.start() - 60):found.start()]


def test_landing_texts_from_the_submission(client):
    html = page(client, "/")

    assert "уступают лучшей не больше чем на 2%" in html
    assert "Защита: лимит попыток входа, CSRF-токен, CSP." in html
    assert "Цену берём из прогноза. Правило «пятница — значит дороже» здесь не работает." in html
    # оборот «X, а не Y» — только в заголовке
    body = html.split('<h1 class="lp-title">', 1)[1].split("</h1>", 1)[1]
    assert ", а не " not in body


def test_landing_tells_the_june_12_story(client):
    html = page(client, "/")

    assert "Пятница, которая не стала пиком" in html
    assert "медиана 917 против 1 049" in html
    assert 'id="story-fridays"' in html


def test_landing_buttons_lead_into_the_tool(client):
    html = page(client, "/")

    assert re.search(r'<button[^>]*data-guest', html)
    assert 'href="/app?destination=' in html
    assert 'href="/login"' in html


def test_no_link_on_the_landing_leads_nowhere(client):
    assert 'href="#"' not in page(client, "/")


def solution_rows(html):
    block = html.split('<div class="card files">', 1)[1].split("</section>", 1)[0]
    return re.findall(r'<(a|div) class="file[^"]*"([^>]*)>(.*?)</\1>', block)


def test_files_without_a_link_say_where_they_are(client):
    rows = solution_rows(page(client, "/"))

    assert len(rows) == 7
    links = {re.search(r'file__name">([^<]*)', body).group(1): re.search(r'href="([^"]*)"', attrs)
             for tag, attrs, body in rows}
    assert links["Код сервиса"].group(1) == "https://github.com/nnenoix/reshinie-zadaniy"
    assert links["Сайт"].group(1) == "/"
    for tag, attrs, body in rows:
        if tag == "div":
            assert "href" not in attrs and "в папке сдачи" in body and "Открыть" not in body


def test_file_links_come_from_settings_without_touching_the_markup(settings):
    links = {**settings.file_links, "bia": "https://disk.yandex.ru/d/abc", "video": "javascript:alert(1)"}
    with TestClient(create_app(Settings(**{**settings.__dict__, "file_links": links}))) as client:
        rows = solution_rows(page(client, "/"))

    bia = next(r for r in rows if "БиА.pdf" in r[2])
    video = next(r for r in rows if "Видео" in r[2])
    assert bia[0] == "a" and 'href="https://disk.yandex.ru/d/abc"' in bia[1]
    assert video[0] == "div"  # небезопасная ссылка не попадает на страницу


def test_every_solution_file_has_its_own_environment_variable():
    names = [f.env for f in FILES]

    assert len(FILES) == 7 and len(set(names)) == 7
    assert all(name.startswith("LINK_") for name in names)


def test_tools_line_names_claude_code_and_claude_design(client):
    html = page(client, "/")

    assert "Claude Code на модели Claude Opus 5.5" in html
    assert "Claude Design" in html


def test_login_page_has_login_register_and_guest(client):
    html = page(client, "/login")

    assert 'data-form="login"' in html and 'data-form="register"' in html
    assert 'name="password2"' in html
    assert "data-guest" in html


def test_tool_needs_a_session(client):
    response = client.get("/app")

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_tool_opens_after_guest_login(guest):
    html = page(guest, "/app")

    for tab in ("calc", "salon", "calendar", "ticket"):
        assert f'data-tab="{tab}"' in html


def test_login_page_sends_signed_in_user_to_the_tool(guest):
    response = guest.get("/login")

    assert response.status_code == 303
    assert response.headers["location"] == "/app"


def open_page(client, path):
    """/app открывается после входа, /login — до входа."""
    if path == "/app":
        client.post("/api/guest")
    response = client.get(path)
    assert response.status_code == 200
    return response


@pytest.mark.parametrize("path", ["/", "/login", "/app"])
def test_pages_keep_markup_apart_from_logic(client, path):
    html = open_page(client, path).text

    assert " style=" not in html
    assert not re.search(r"<style", html)
    assert not re.search(r"<script(?![^>]*\bsrc=)", html)
    assert not re.search(r"\son[a-z]+=", html)
    assert "demo=" not in html


@pytest.mark.parametrize("path", ["/", "/login", "/app"])
def test_pages_load_design_fonts_allowed_by_csp(client, path):
    response = open_page(client, path)
    policy = response.headers["content-security-policy"]

    assert "fonts.googleapis.com/css2?family=Unbounded" in response.text
    assert "style-src 'self' https://fonts.googleapis.com" in policy
    assert "font-src 'self' https://fonts.gstatic.com" in policy


def test_old_static_page_is_gone(client):
    assert client.get("/static/index.html").status_code == 404
