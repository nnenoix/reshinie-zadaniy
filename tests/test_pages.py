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
from app.landing import count_phrases
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
    html = plain(page(client, "/"))

    assert "Цена из <span class=\"accent\">прогноза</span>, а не из правила" in html
    assert "Егор Титаренко · Центральный университет · направление «Технологии»" in html


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


@pytest.mark.parametrize("n, word", [(1, "автотест"), (21, "автотест"), (391, "автотест"), (392, "автотеста"),
                                     (394, "автотеста"), (395, "автотестов"), (400, "автотестов"),
                                     (411, "автотестов"), (412, "автотестов"), (514, "автотестов")])
def test_word_for_tests_agrees_with_their_number(n, word):
    assert count_phrases(n)["<!-- tests-word -->"] == word


@pytest.mark.parametrize("n, sentence", [
    (391, "Сервис проверяет <span data-tests>391</span> автотест."),
    (392, "Сервис проверяют <span data-tests>392</span> автотеста."),
    (395, "Сервис проверяют <span data-tests>395</span> автотестов."),
])
def test_tests_sentence_agrees_with_the_number(n, sentence):
    assert count_phrases(n)["<!-- tests-sentence -->"] == sentence


def test_landing_spells_the_number_of_tests_in_agreement(client):
    html = page(client, "/")
    n = int(re.search(r"<span data-tests>(\d+)</span>", html).group(1))
    phrases = count_phrases(n)

    assert f"<dt>{phrases['<!-- tests-label -->']}</dt><dd><span data-tests>{n}</span></dd>" in html
    assert f'<dt class="metric__label">{phrases["<!-- tests-word -->"]}</dt>' in html
    assert phrases["<!-- tests-sentence -->"] in html
    assert "<!-- tests" not in html


def plain(html: str) -> str:
    """Текст без типографских связок: неразрывный пробел — обычный, невидимая связка после тире убрана."""
    return html.replace("&nbsp;", " ").replace(" ", " ").replace("&#8288;", "").replace("⁠", "")


def test_best_price_on_landing_is_the_one_the_service_computes(client):
    html = page(client, "/")
    text = plain(html)

    assert "5&nbsp;605<span class=\"metric__unit\">₽</span>" in html
    assert "лучшая цена 12 июня по нашей модели" in text
    assert "По нашей модели лучшая цена 5 605 ₽: +3 217 ₽ ожидаемой прибыли за день к базовой цене 5 500 ₽." in text
    assert "5 610" not in text
    # 5 614 ₽ — только с пометкой, что это прогноз организаторов
    for found in re.finditer("5 614", text):
        assert "прогнозу организаторов" in text[max(0, found.start() - 60):found.start()]


def test_landing_texts_from_the_submission(client):
    html = plain(page(client, "/"))

    assert "По средней ошибке ансамбль точнее лишь на 1,8 %." in html
    assert "(WQL 0,068 против 0,076 у ансамбля), и не требует переобучения." in html
    assert "её не надо переобучать" not in html
    assert "пересчитал 302 числа аналитики" in html
    assert "Вход защищён от подбора пароля, формы — от подделки запросов." in html
    assert "Цену берём из прогноза. Правило «пятница — значит дороже» здесь не работает." in html
    # оборот «X, а не Y» — только в заголовке
    body = html.split('<h1 class="lp-title">', 1)[1].split("</h1>", 1)[1]
    assert ", а не " not in body


def test_landing_tells_the_june_12_story(client):
    html = page(client, "/")

    assert "Пятница, которая не стала пиком" in html
    assert "медиана 917 против 1 049" in plain(html)
    assert 'id="story-fridays"' in html


def test_landing_says_things_plainly(client):
    # правки витрины 14.11.2026: без жаргона, с единицами, без выдачи догадки за факт
    html = page(client, "/")
    text = plain(html)

    assert "Модель одного дня работы самолёта, прогноз спроса на июнь 2026 года и сервис, который на лету считает продажи и лучшую цену." in text
    assert "если вместо Сочи дважды летать в Москву" in text
    assert "не лететь в Сочи" not in text
    assert "Вероятно, праздничная пятница не деловой день: в прошлом году 12 июня спрос на этом рейсе тоже упал, 598 против 822–878 в будни до и после." in text
    assert "+3 812 ₽ ожидаемой прибыли за день" in text
    assert "столько приносит одно лишнее кресло П→М в пиковую пятницу" in text
    assert "если бы в мае 2026 цены ставили по прогнозу" in text
    assert "дней мая, когда реальный спрос попал в коридор прогноза (ожидалось 80 %)" in text
    assert "с 42,3 до 40,9 пассажира в день на маршрут" in text
    assert re.findall(r'<dd class="lp-num__group">([^<]*)</dd>', html) == [
        "Аналитика", "Аналитика", "Аналитика", "Прогноз", "Прогноз", "Сервис"]
    assert '<a href="#case">Решение</a>' in html
    for gone in ("бэктесте", "теневая цена кресла в", "живьём", "ошибка 42,31 → 40,88", "Рейс дня", "CSRF"):
        assert gone not in text, gone


def test_landing_buttons_lead_into_the_tool(client):
    html = page(client, "/")

    assert re.search(r'<button[^>]*data-guest', html)
    assert 'href="/app?destination=' in html
    assert 'href="/login"' in html


def test_story_steps_are_numbered_plainly(client):
    steps = re.findall(r'<span class="steps-list__n">([^<]*)</span>', page(client, "/"))

    assert steps == ["1", "2", "3", "4", "5"]


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
            assert "href" not in attrs and "в&nbsp;папке сдачи" in body and "Открыть" not in body


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


def test_tool_opens_on_the_story_flight_before_its_script_runs(guest):
    # На медленном сервере гость секунды смотрел на пустые «Куда» и «Дата» и «Здесь появится прогноз»,
    # пока скрипт грузил маршруты. Страница сразу приходит с рейсом истории и «Сервер считает…».
    story = guest.get("/api/story").json()
    html = page(guest, "/app")

    destination = re.search(r'<select[^>]*id="destination"[^>]*>(.*?)</select>', html, re.S).group(1)
    assert destination.strip() == f'<option selected>{story["route"]["destination"]}</option>'
    assert re.search(r'<input[^>]*id="date"[^>]*>', html).group(0).count(f'value="{story["date"]}"') == 1
    assert re.search(r'data-panel="empty"[^>]*>', html).group(0).endswith(" hidden>")
    assert "hidden" not in re.search(r'data-panel="loading"[^>]*>', html).group(0)


def test_login_page_sends_signed_in_user_to_the_tool(client):
    assert client.post("/api/register", json={"login": "anna", "password": "password1"}).status_code == 201
    response = client.get("/login")

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


DESIGN_FONTS = ("https://fonts.googleapis.com/css2?family=Manrope:wght@700;800"
                "&amp;family=Onest:wght@400;500;600&amp;display=swap")
STYLE = PROJECT / "static" / "style.css"


@pytest.mark.parametrize("path", ["/", "/login", "/app"])
def test_pages_load_design_fonts_allowed_by_csp(client, path):
    # вариант 2 «Привычный сервис»: Manrope — заголовки, числа и кнопки, Onest — текст
    response = open_page(client, path)
    policy = response.headers["content-security-policy"]

    assert re.findall(r'href="(https://fonts\.googleapis\.com/css2[^"]*)"', response.text) == [DESIGN_FONTS]
    assert "style-src 'self' https://fonts.googleapis.com" in policy
    assert "font-src 'self' https://fonts.gstatic.com" in policy


def test_style_uses_only_the_two_design_fonts():
    css = STYLE.read_text(encoding="utf-8")

    assert "JetBrains Mono" not in css and "Golos Text" not in css and "Unbounded" not in css
    assert set(re.findall(r"'([A-Za-z][^']*)'", css)) == {"Manrope", "Onest"}


@pytest.mark.parametrize("path", ["/", "/login", "/app"])
def test_pages_do_not_mention_unbounded(client, path):
    assert "Unbounded" not in open_page(client, path).text


# --- подписи без тегов в квадратных скобках ---

@pytest.mark.parametrize("path", ["/", "/login", "/app"])
def test_pages_have_no_bracket_labels(client, path):
    html = open_page(client, path).text

    assert "[ " not in html and " ]" not in html
    assert '<a class="brand" href="/">Решись Авиа</a>' in html


def test_scripts_write_no_bracket_labels():
    scripts = {path.name: path.read_text(encoding="utf-8") for path in (PROJECT / "static" / "js").glob("*.js")}

    assert scripts
    assert [name for name, source in scripts.items() if "[ " in source or " ]" in source] == []


# --- подписи обычным регистром, без моноширинного капса с разрядкой ---

CAPS_WORD = re.compile(r"\b[А-ЯЁ]{3,}\b")  # «УПОР», «ПЯТНИЦА»; сокращения вроде «РФ» короче


@pytest.mark.parametrize("path", ["/", "/login", "/app"])
def test_pages_write_no_words_in_caps(client, path):
    text = re.sub(r"<[^>]*>", " ", open_page(client, path).text)

    assert CAPS_WORD.findall(text) == []


def test_scripts_write_no_words_in_caps():
    for script in (PROJECT / "static" / "js").glob("*.js"):
        source = script.read_text(encoding="utf-8")
        assert CAPS_WORD.findall(source) == [], script.name
        assert "toUpperCase" not in source, script.name


def test_style_has_no_caps_and_no_wide_letter_spacing():
    css = STYLE.read_text(encoding="utf-8")

    assert "text-transform" not in css
    assert all(value.startswith("-") for value in re.findall(r"letter-spacing:\s*([^;}\s]+)", css))


def test_old_static_page_is_gone(client):
    assert client.get("/static/index.html").status_code == 404


# --- инструмент /app: правки по ревью ---

def test_ticket_barcode_is_solid_bars_that_html2canvas_can_draw(client):
    html = open_page(client, "/app").text
    bars = re.search(r'<span class="barcode"[^>]*>(.*?)</span>', html).group(1)

    assert bars.count('<i class="b') >= 20
    css = (PROJECT / "static" / "style.css").read_text(encoding="utf-8")
    rules = [line for line in css.splitlines() if line.startswith(".barcode")]
    assert rules and not any("gradient" in line for line in rules)


def test_tool_tabs_are_named_without_numbers(client):
    html = open_page(client, "/app").text
    tabs = html.split('<div class="tabs tabs--main"', 1)[1].split("</div>", 1)[0]

    assert re.findall(r'data-tab="[a-z]+"[^>]*>([^<]*)</button>', tabs) == ["Расчёт", "Салон", "Календарь", "Талон"]


def test_seats_are_the_seats_of_all_flights_of_the_day(client):
    html = open_page(client, "/app").text

    assert "Мест на рейсах дня" in html and "Мест в самолёте" not in html


def test_probability_lines_have_their_places(client):
    html = open_page(client, "/app").text

    assert 'id="chart-odds"' in html and 'id="salon-odds"' in html


def test_guest_gets_a_link_to_register(client):
    html = open_page(client, "/app").text

    assert re.search(r'<a [^>]*href="/login#register"[^>]*id="register-link"', html)


# Проценты по правилам русской типографики: «13 %» с неразрывным пробелом, чтобы «%» не уезжал
# на другую строку. Крупные числа с отдельным «%» (83<small>%</small>) отбиты отступом в CSS.
PERCENT_WITHOUT_NBSP = re.compile(r"\d[ \t]?%")


@pytest.mark.parametrize("path", ["/", "/login", "/app"])
def test_percent_sign_is_set_off_by_a_non_breaking_space(client, path):
    html = open_page(client, path).text.replace("&nbsp;", " ")
    text = re.sub(r"<[^>]*>", "\n", html)  # без тегов: в адресах ссылок «%D0» — не проценты

    assert PERCENT_WITHOUT_NBSP.findall(text) == []


def test_june_12_is_compared_with_the_other_fridays_of_june(client):
    # 12 июня сравнивается со всеми остальными пятницами июня (5, 19, 26), а не с «соседними».
    html = page(client, "/")

    assert "спрос на 13 % ниже других пятниц июня: медиана 917 против 1 049" in plain(html)
    assert "12 июня бледнее других пятниц июня" in plain(html)
    assert "соседн" not in html


# --- правки по проверке вёрстки ---

@pytest.mark.parametrize("path", ["/", "/login", "/app"])
def test_pages_declare_a_light_colour_scheme(client, path):
    assert '<meta name="color-scheme" content="light">' in open_page(client, path).text


def visible_text(html: str) -> str:
    body = html.split("<body", 1)[1]
    return re.sub(r"<[^>]*>", "", body).replace("&nbsp;", " ")


# Висячие однобуквенные предлоги и союзы: «попал в / коридор», «кресла в / пиковую».
HANGING = re.compile(r"(?<![А-Яа-яЁё])[вксуоиаВКСУОИА] ")


def test_landing_keeps_numbers_rubles_and_short_words_together(client):
    # вся витрина, вместе с «Файлами решения» из app/solution_files.py
    text = visible_text(page(client, "/"))

    assert re.findall(r"\d \d|.. ₽|\d сценари|День России", text) == []
    assert HANGING.findall(text) == []
    assert "10–90" not in text  # после тире строка не рвётся: «10–⁠90»


def test_quantiles_on_the_landing_are_written_with_a_comma(client):
    text = visible_text(page(client, "/"))

    assert "0.1" not in text and "0.9" not in text
    assert "0,1" in text


def test_form_note_names_every_action_that_writes_history(client):
    note = re.search(r'<p class="form-note">([^<]*)</p>', open_page(client, "/app").text).group(1)

    for action in ("«Рассчитать»", "календар", "«Поставить лучшую цену»", "«Повторить»"):
        assert action in note, action


def test_read_only_origin_is_out_of_the_tab_order(client):
    origin = re.search(r'<input[^>]*id="origin"[^>]*>', open_page(client, "/app").text).group(0)

    assert 'tabindex="-1"' in origin and "readonly" in origin


# --- вариант 2 «Привычный сервис»: без украшений варианта 1 ---

BUTTONS = re.compile(r'<(button|a)\b[^>]*class="[^"]*\b(btn|link-btn|file)\b[^"]*"[^>]*>(.*?)</\1>', re.S)


@pytest.mark.parametrize("path", ["/", "/login", "/app"])
def test_buttons_and_links_carry_no_arrow(client, path):
    # «→» в маршрутах («MOW → LED», «Москва → Санкт-Петербург») — смысл, в кнопках — украшение
    html = open_page(client, path).text
    found = [inner for _, _, inner in BUTTONS.findall(html) if "→" in inner]

    assert found == []


@pytest.mark.parametrize("path", ["/", "/login", "/app"])
def test_unordered_lists_carry_no_numbers(client, path):
    html = open_page(client, path).text

    for number in ("feat__n", "file__n", "facts__n", "steps__n"):
        assert f'class="{number}"' not in html, number


def test_story_steps_keep_their_numbers(client):
    # сквозная история 12 июня — последовательность, её шаги 1–5 остаются
    assert re.findall(r'<span class="steps-list__n">(\d)</span>', page(client, "/")) == list("12345")


@pytest.mark.parametrize("path", ["/", "/login", "/app"])
def test_no_overline_above_a_heading(client, path):
    # над h1/h2 нет мелкой серой подписи: «Турнир «Решись» · Технологии», «Аналитика», «Внутренний инструмент»
    html = open_page(client, path).text

    assert re.findall(r'<p class="label">[^<]*</p>\s*<h[12]\b', html) == []


@pytest.mark.parametrize("path, headings", [
    ("/", ["12 июня ·", "Ключевые числа", "Пиковая пятница · П→М", "Как проверено", "Файлы решения", "Инструменты"]),
    ("/app", ["Параметры рейса", "Лучшая цена", "История расчётов"]),
])
def test_section_and_card_captions_are_headings(client, path, headings):
    # подписи разделов без заголовка рядом и подписи карточек стали заголовками, как в макете
    html = open_page(client, path).text
    found = [re.sub(r"<[^>]*>", "", text) for text in
             re.findall(r'<h[23] class="(?:section|card)-title"[^>]*>(.*?)</h[23]>', html)]

    for heading in headings:
        assert any(text.startswith(heading) for text in found), (heading, found)
