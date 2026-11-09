"""Страницы: витрина (публичная), вход и инструмент после входа.

Вёрстка отделена от логики: в HTML нет инлайн-стилей и инлайн-скриптов,
а числа витрины совпадают с расчётом (их проверяет tests/test_story.py
и тест /api/story в test_api_features.py).
"""
import re

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


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


@pytest.mark.parametrize("number", ["705", "1 625", "4<small>", "+6,7", "83", "300+"])
def test_landing_shows_key_numbers(client, number):
    assert number in page(client, "/")


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


def test_solution_files_link_to_placeholders_or_https(client):
    files = re.findall(r'<a class="file" href="([^"]*)"', page(client, "/"))

    assert len(files) == 7
    assert all(href == "#" or href.startswith("https://") for href in files)
    assert "https://github.com/nnenoix/reshinie-zadaniy" in files


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
