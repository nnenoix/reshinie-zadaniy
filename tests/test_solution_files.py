"""Ссылки «Файлы решения» на витрине: одно место для адресов, без правки вёрстки."""
import pytest

from app.config import from_environment
from app.solution_files import FILES, breakable, file_links, files_html, safe_url

GITHUB = "https://github.com/nnenoix/reshinie-zadaniy"


def test_by_default_only_code_and_site_have_links():
    assert file_links({}) == {"code": GITHUB, "site": "/"}


def test_links_are_set_by_environment_variables():
    env = {"LINK_BIA_PDF": " https://disk.yandex.ru/d/bia ", "LINK_VIDEO": "https://disk.yandex.ru/i/video"}

    links = file_links(env)

    assert links["bia"] == "https://disk.yandex.ru/d/bia"
    assert links["video"] == "https://disk.yandex.ru/i/video"
    assert links["code"] == GITHUB


def test_empty_variable_keeps_the_default():
    assert file_links({"LINK_CODE": "  "})["code"] == GITHUB


def test_settings_carry_the_links():
    assert from_environment({"LINK_MY_FORECAST": "https://disk.yandex.ru/d/csv"}).file_links["forecast"] == \
        "https://disk.yandex.ru/d/csv"


@pytest.mark.parametrize("url, safe", [
    ("https://disk.yandex.ru/d/x", True), ("http://example.org/a?b=1", True), ("/", True), ("/docs", True),
    ("#", False), ("", False), ("javascript:alert(1)", False), ("//evil.example/x", False),
    ("data:text/html,hi", False), ("ftp://x", False),
])
def test_only_web_and_site_links_are_allowed(url, safe):
    assert (safe_url(url) is not None) is safe


def test_row_without_a_link_is_not_clickable():
    html = files_html(file_links({}))

    assert html.count('<div class="file is-pending">') == 5
    assert html.count("в&nbsp;папке сдачи") == 5
    assert 'href="#"' not in html


def test_external_link_opens_in_a_new_tab_and_text_is_escaped():
    html = files_html({"code": GITHUB + '?a=1&b="2"'})

    assert f'href="{GITHUB}?a=1&amp;b=&quot;2&quot;" target="_blank" rel="noopener"' in html
    assert '<span class="file__open">Открыть</span>' in html and "→" not in html


def test_check_scripts_come_as_one_archive():
    checks = next(f for f in FILES if f.key == "checks")

    assert (checks.name, checks.tag, checks.env) == \
        ("Титаренко_Егор_Константинович_Проверка.zip", "ZIP", "LINK_CHECK_SCRIPTS")
    assert checks.description == ("proverka_bia.py и proverka_forecast.py с нужными файлами: "
                                  "пересчёт чисел аналитики и проверка файла прогноза")


def test_files_keep_their_order_without_numbers():
    html = files_html({})

    names = [html.index(breakable(f.name)) for f in FILES]
    assert names == sorted(names) and 'class="file__n"' not in html
