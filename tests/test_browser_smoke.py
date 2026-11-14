"""Смоук-тесты страницы в настоящем браузере: Playwright и установленный Google Chrome.

Без пакета playwright или без Chrome тесты пропускаются, браузер не скачивается.
Талон снимает html2canvas с cdnjs: без интернета тест талона тоже пропускается.
Сервер поднимается в отдельном потоке на свободном порту, база — свой файл SQLite.
"""
import socket
import threading
import time

import pytest
import uvicorn

from app.config import Settings
from app.main import create_app

sync_api = pytest.importorskip("playwright.sync_api")


JURY_PASSWORD = "smoke-jury-pass"
BECOME_GUEST = "async () => { await (await import('/static/js/guest.js')).enterAsGuest(); }"


def become_guest(tab, base_url):
    """Свой гость у каждого теста: кнопки гостя на страницах нет, гостя создаёт API (как раньше кнопка)."""
    tab.goto(base_url + "/login")
    tab.evaluate(BECOME_GUEST)


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@pytest.fixture(scope="module")
def base_url(tmp_path_factory):
    port = free_port()
    # гостей здесь больше 20 за час: лимит регистраций с одного адреса проверяют другие тесты
    app = create_app(Settings(db_path=tmp_path_factory.mktemp("smoke") / "app.db", signup_limit=1000,
                              guest_limit=1000, guest_minute_limit=1000, demo_password=JURY_PASSWORD))
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 20
    while not server.started:
        if time.monotonic() > deadline:
            pytest.skip("сервер для смоук-тестов не запустился")
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=10)


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as playwright:
        try:
            chrome = playwright.chromium.launch(channel="chrome", headless=True)
        except Exception as problem:  # Chrome не установлен — тест не о нём
            pytest.skip(f"нет Google Chrome для Playwright: {problem}")
        yield chrome
        chrome.close()


def open_tool(browser, base_url, width=1440):
    """Новый гость в чистом браузере шириной width, расчёт 12 июня уже на экране."""
    context = browser.new_context(accept_downloads=True, viewport={"width": width, "height": 900})
    tab = context.new_page()
    become_guest(tab, base_url)
    tab.goto(base_url + "/app")
    wait_for_result(tab)
    return context, tab


@pytest.fixture
def page(browser, base_url):
    context, tab = open_tool(browser, base_url)
    yield tab
    context.close()


def wait_for_result(tab):
    tab.wait_for_function("() => !document.querySelector('[data-panel=\"ready\"]').hidden")


def test_story_calculation_shows_numbers_and_odds(page):
    assert page.inner_text("#result-route").startswith("Москва → Санкт-Петербург · 12.06.2026")
    assert page.inner_text('[data-out="seats"]') == "1 440"
    assert page.inner_text('[data-out="want"]') == "917"  # медиана нашей модели при 5 500 ₽
    assert page.inner_text("#chart-odds").startswith("С вероятностью 80 % желающих от 782 до 1 039")
    assert page.locator("#chart svg rect.ch-bar").count() == 9


def test_page_is_drawn_with_the_two_design_fonts(page):
    loaded = page.evaluate("""async () => {
        await document.fonts.ready;
        return [...document.fonts].filter((f) => f.status === 'loaded').map((f) => f.family.replace(/["']/g, ''));
    }""")
    if not loaded:
        pytest.skip("шрифты Google Fonts не загрузились: нет интернета")

    assert set(loaded) == {"Manrope", "Onest"}


def test_phone_header_of_a_guest_keeps_the_brand_on_one_line(browser, base_url):
    context = browser.new_context(viewport={"width": 375, "height": 812})
    tab = context.new_page()
    become_guest(tab, base_url)
    tab.goto(base_url + "/app")
    lines, overflow, fonts = tab.evaluate("""async () => {
        await document.fonts.ready;
        const text = document.createRange();
        text.selectNodeContents(document.querySelector('.brand'));
        return [text.getClientRects().length, document.documentElement.scrollWidth - innerWidth,
                document.fonts.check('800 16px Manrope')];
    }""")
    context.close()
    if not fonts:
        pytest.skip("Manrope не загрузился: нет интернета, ширина шапки другая")

    assert (lines, overflow) == (1, 0)  # «Решись Авиа» рядом с «Зарегистрироваться» и «Выйти»


def test_landing_chart_note_spells_the_source_as_it_is(browser, base_url):
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    tab = context.new_page()
    tab.goto(base_url + "/")
    tab.wait_for_function("() => document.querySelector('[data-story=\"chart-how\"]').textContent.includes('источник')")
    note = tab.inner_text('[data-story="chart-how"]')
    context.close()

    assert "источник: наша ML-модель." in note  # не «наша ml-модель»


def test_salon_scale_note_reads_as_one_paragraph(page):
    # «1 кресло = 10 мест, 1 человечек = 10 человек.» стояло узкой колонкой в четыре строки
    page.click('.tabs--main [data-tab="salon"]')
    lines = page.evaluate("""() => {
        const scale = document.createRange();
        scale.selectNodeContents(document.querySelector('#salon-how strong'));
        return scale.getClientRects().length;
    }""")

    assert lines == 1


@pytest.mark.parametrize("width", [1440, 375])
def test_ticket_stub_route_is_one_line_under_its_label(browser, base_url, width):
    context, tab = open_tool(browser, base_url, width)
    tab.click('.tabs--main [data-tab="ticket"]')
    lines, shift = tab.evaluate("""async () => {
        await document.fonts.ready;
        const route = document.querySelector('.stub__route'), label = document.querySelector('.stub__col .label');
        const text = document.createRange();
        text.selectNodeContents(route);
        return [text.getClientRects().length, route.getBoundingClientRect().left - label.getBoundingClientRect().left];
    }""")
    context.close()

    assert (lines, round(shift)) == (1, 0)  # «MOW → LED» без сдвига вправо и без переноса


LABEL_ON_CURVE = """() => {
    const svg = document.querySelector('#profit-chart svg');
    const mine = svg.querySelector('.pc-label--cur').getBBox(), best = svg.querySelector('.pc-label--best').getBBox();
    const points = svg.querySelector('.pc-line').getAttribute('points').trim().split(' ').map((p) => p.split(',').map(Number));
    const inside = ([x, y]) => x >= mine.x && x <= mine.x + mine.width && y >= mine.y && y <= mine.y + mine.height;
    const apart = mine.x + mine.width < best.x || best.x + best.width < mine.x ||
        mine.y + mine.height < best.y || best.y + best.height < mine.y;
    return { curve: points.filter(inside).length, best: !apart };
}"""


@pytest.mark.parametrize("price", ["5 500", "3 400", "9 500"])
def test_your_price_label_stays_off_the_profit_curve(page, price):
    if price != "5 500":
        page.fill("#price", price)
        page.click("#submit")
    page.wait_for_function("""(price) => {
        const label = document.querySelector('#profit-chart .pc-label--cur');
        return label && label.textContent.replace(/\\s/g, ' ').endsWith(price);
    }""", arg=price)

    assert page.evaluate(LABEL_ON_CURVE) == {"curve": 0, "best": False}


def test_negative_price_is_kept_and_explained(page):
    page.fill("#price", "−500")
    page.locator("#price").blur()

    assert page.input_value("#price") == "−500"
    page.click("#submit")
    page.wait_for_selector('[data-error-for="price"]:not([hidden])')
    assert page.inner_text('[data-error-for="price"]') == "Цена должна быть больше нуля."


def test_ticket_digits_are_drawn_the_way_html2canvas_draws_them(page):
    # html2canvas берёт места слов из вёрстки, а цифры рисует без font-variant-numeric:
    # с tabular-nums в PNG талона появлялись дыры внутри чисел — «1  440», «64  %».
    page.click('.tabs--main [data-tab="ticket"]')
    styled = page.evaluate("""() => [...document.querySelectorAll('#ticket *')]
        .map((e) => getComputedStyle(e).fontVariantNumeric).filter((v) => v !== 'normal')""")

    assert styled == []


def test_ticket_png_contains_the_barcode(page, tmp_path):
    page.click('.tabs--main [data-tab="ticket"]')
    if not page.evaluate("() => typeof window.html2canvas === 'function'"):
        pytest.skip("html2canvas не загрузился с cdnjs: нет интернета")

    with page.expect_download() as download:
        page.click("#dl-png")
    saved = tmp_path / download.value.suggested_filename
    download.value.save_as(saved)

    assert saved.name == "talon-RA-LED-120626-5500.png"
    assert saved.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    dark, total = page.evaluate("""async () => {
        const ticket = document.querySelector('#ticket'), bar = ticket.querySelector('.barcode');
        const canvas = await window.html2canvas(ticket, { scale: 1, logging: false });
        const t = ticket.getBoundingClientRect(), b = bar.getBoundingClientRect();
        const pixels = canvas.getContext('2d').getImageData(
            Math.round(b.left - t.left), Math.round(b.top - t.top), Math.round(b.width), Math.round(b.height)).data;
        let dark = 0;
        for (let i = 0; i < pixels.length; i += 4) if (pixels[i] < 80 && pixels[i + 3] > 200) dark++;
        return [dark, pixels.length / 4];
    }""")
    assert dark > total * 0.2  # полосы штрихкода есть на снимке талона


def test_story_button_leads_the_jury_through_the_prefilled_login(browser, base_url):
    # витрина → «Открыть расчёт 12 июня» → /login, где логин и пароль жюри уже введены → расчёт 12 июня
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    tab = context.new_page()
    errors = []
    tab.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
    tab.goto(base_url + "/")
    tab.click(".lp-cta a >> nth=0")
    tab.wait_for_url("**/login")
    filled = [tab.input_value("#jury-login"), tab.input_value("#jury-password") == JURY_PASSWORD,
              tab.is_visible("#jury-form"), tab.is_visible("#login-form")]
    tab.click("#jury-form button[type=submit]")
    tab.wait_for_url("**/app")
    wait_for_result(tab)
    shown = tab.inner_text("#result-route").replace("\xa0", " ")
    context.close()

    assert filled == ["jury", True, True, False]
    assert shown == "Москва → Санкт-Петербург · 12.06.2026 · 5 500 ₽"
    assert errors == []


def test_grey_register_line_opens_the_registration_form(browser, base_url):
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    tab = context.new_page()
    tab.goto(base_url + "/login")
    tab.click(".auth__switch--muted [data-tab=register]")
    shown = [tab.is_visible("#register-form"), tab.is_visible("#jury-form"), tab.is_visible(".auth__switch--muted")]
    context.close()

    assert shown == [True, False, False]


def test_guest_sees_the_story_flight_while_routes_are_still_loading(browser, base_url):
    # /app без параметров: пока сервер отвечает на /api/routes,
    # поля «Куда» и «Дата» уже заполнены, а вместо «Здесь появится прогноз» идёт расчёт.
    context = browser.new_context(viewport={"width": 1024, "height": 900})
    tab = context.new_page()
    become_guest(tab, base_url)
    held = []
    tab.route("**/api/routes*", lambda route: held.append(route))
    with tab.expect_request("**/api/routes*"):
        tab.goto(base_url + "/app", wait_until="commit")
    while_loading = tab.evaluate("""() => [document.querySelector('#destination').value, document.querySelector('#date').value,
        [...document.querySelectorAll('[data-panel]')].filter((p) => !p.hidden).map((p) => p.dataset.panel)]""")
    held[0].continue_()
    wait_for_result(tab)
    shown = [tab.url.removeprefix(base_url), tab.inner_text("#result-route"), tab.input_value("#source")]
    context.close()

    assert while_loading == ["Санкт-Петербург", "2026-06-12", ["loading"]]
    assert shown == ["/app", "Москва → Санкт-Петербург · 12.06.2026 · 5 500 ₽", "ml"]


TEXT_PERCENTS = r"""() => {
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    const bad = [];
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
        if (/\d[ \t]?%/.test(node.textContent)) bad.push(node.textContent.trim());
    }
    return bad;
}"""


def test_percents_written_by_scripts_keep_a_non_breaking_space(browser, base_url):
    # «−13 %», «64 %», «С вероятностью 80 %…» пишет JavaScript: везде «число&nbsp;%», как в вёрстке.
    context, tab = open_tool(browser, base_url)
    for name in ("salon", "calendar", "ticket"):
        tab.click(f'.tabs--main [data-tab="{name}"]')
    tab.wait_for_function("() => document.querySelector(\"#cal-min\").textContent !== \"\"")
    in_tool = tab.evaluate(TEXT_PERCENTS)
    tab.goto(base_url + "/")
    tab.wait_for_function("() => document.querySelector('[data-story=\"chart-how\"]').textContent.includes('источник')")
    on_landing = tab.evaluate(TEXT_PERCENTS)
    context.close()

    assert (in_tool, on_landing) == ([], [])


@pytest.mark.parametrize("sold_out, chance", [
    (0, "меньше 10 %"), (1, "от 10 до 20 %"), (3, "от 30 до 40 %"),
    (8, "от 80 до 90 %"), (9, "больше 90 %"),
])
def test_chance_to_run_out_of_seats_is_an_honest_range(page, sold_out, chance):
    # k сценариев из 9 упираются в места: места лежат между квантилями 0.(9−k) и 0.(10−k),
    # значит, вероятность упора — от k×10 до (k+1)×10 %, а не «≈ k×10 %».
    text = page.evaluate("""async (k) => {
        const { oddsText } = await import('/static/js/format.js');
        return oddsText({ low: 782, high: 1039, sold_out_scenarios: k });
    }""", sold_out)

    assert text == f"С вероятностью 80 % желающих от 782 до 1 039; в места упрёмся с вероятностью {chance}."


LINE_BREAKS = r"""(selector) => [...document.querySelectorAll(selector)].map((element) => {
    // символы, после которых строка переносится: у каждого символа своя верхняя граница
    const text = element.textContent, range = document.createRange(), node = element;
    const walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT);
    const chars = [];
    for (let t = walker.nextNode(); t; t = walker.nextNode()) {
        for (let i = 0; i < t.length; i++) {
            range.setStart(t, i); range.setEnd(t, i + 1);
            chars.push([t.data[i], range.getBoundingClientRect().top]);
        }
    }
    const breaks = [];
    for (let i = 1; i < chars.length; i++) if (chars[i][1] > chars[i - 1][1] + 2) breaks.push(chars[i - 1][0]);
    return [text, breaks];
})"""


def test_file_names_on_a_phone_break_only_after_an_underscore(browser, base_url):
    # «Титаренко_Егор_Ко / нстантинович_БиА. / pdf» рвало посреди слова.
    context = browser.new_context(viewport={"width": 375, "height": 812})
    tab = context.new_page()
    tab.goto(base_url + "/")
    names = tab.evaluate(LINE_BREAKS, "#files .file__name")
    context.close()

    wrapped = [(text, breaks) for text, breaks in names if breaks]
    assert wrapped, "на 375 px длинные имена должны переноситься"
    for text, breaks in wrapped:
        assert set(breaks) <= {"_", " "}, (text, breaks)


CROWDED_NUMBERS = """async (tab) => {
    // Крупные числа вкладки: число в одну строку (слова вроде «Пт · праздник» переносить можно),
    // целиком в своей ячейке и не налезает на соседей.
    await document.fonts.ready;
    const panel = document.querySelector(`[data-tabpanel="${tab}"]`);
    const groups = [
        ['.metrics', '.metric__value', '.metric'],
        ['.ticket__route', '.ticket__code', '.ticket__port'],
        ['.ticket__grid', 'dd', '.tf'],
        ['.stub__col', 'dd', '.tf, .stub__col'],
    ];
    const textBox = (element) => {
        const range = document.createRange();
        range.selectNodeContents(element);
        // строки считаем по тексту: у «100» и «%» разный кегль, но это одна строка
        const rects = [...range.getClientRects()].filter((r) => r.width > 0).sort((a, b) => a.top - b.top);
        let lines = 0, bottom = -Infinity;
        for (const r of rects) if (r.top >= bottom - 1) { lines++; bottom = r.bottom; } else bottom = Math.max(bottom, r.bottom);
        return [range.getBoundingClientRect(), lines];
    };
    const meet = (a, b) => a.left < b.right - .5 && b.left < a.right - .5 && a.top < b.bottom - .5 && b.top < a.bottom - .5;
    const problems = [];
    for (const [groupSel, valueSel, cellSel] of groups) {
        for (const group of panel.querySelectorAll(groupSel)) {
            const values = [...group.querySelectorAll(valueSel)].filter((v) => v.closest(groupSel) === group);
            const boxes = values.map((value) => {
                const [text, lines] = textBox(value), cell = value.closest(cellSel).getBoundingClientRect();
                const name = value.textContent.replace(/\\s/g, ' ');
                if (value.scrollWidth > value.clientWidth) problems.push(`${name}: шире своей ячейки`);
                if (lines > 1 && /\\d/.test(name)) problems.push(`${name}: перенос на ${lines} строки`);
                if (text.left < cell.left - .5 || text.right > cell.right + .5) problems.push(`${name}: вылезает из карточки`);
                return [name, text];
            });
            for (let i = 0; i < boxes.length; i++) for (let j = i + 1; j < boxes.length; j++) {
                if (meet(boxes[i][1], boxes[j][1])) problems.push(`${boxes[i][0]} налезает на ${boxes[j][0]}`);
            }
        }
    }
    for (const label of panel.querySelectorAll('.metric__label')) {
        const [, lines] = textBox(label);
        if (lines > 2) problems.push(`подпись «${label.textContent}» сжата в ${lines} строки`);
    }
    return problems;
}"""


@pytest.fixture(scope="module")
def full_flight(browser, base_url):
    """Самые широкие числа: 3 300 ₽ на 12 июня — желают 1 564, купят 1 440 из 1 440, загрузка 100 %."""
    context, tab = open_tool(browser, base_url)
    tab.goto(base_url + "/app?destination=Санкт-Петербург&date=2026-06-12&price=3300")
    wait_for_result(tab)
    assert tab.inner_text('[data-out="load"]') == "100"
    yield tab
    context.close()


@pytest.mark.parametrize("tab_name", ["calc", "salon", "ticket"])
@pytest.mark.parametrize("width", [375, 800, 900, 1024, 1100, 1280, 1440])
def test_big_numbers_fit_their_cards_at_every_width(full_flight, width, tab_name):
    # На 1024 «1 440» заходило на «917», «100 %» вылезало из карточки, подписи стояли столбиком.
    full_flight.set_viewport_size({"width": width, "height": 900})
    full_flight.click(f'.tabs--main [data-tab="{tab_name}"]')

    assert full_flight.evaluate(CROWDED_NUMBERS, tab_name) == []


COMPARE_FITS = """async () => {
    // Таблица «Два прогноза на этот рейс» целиком в карточке: без прокрутки, последний столбец виден.
    await document.fonts.ready;
    const box = document.querySelector('#compare-table'), card = box.closest('.card').getBoundingClientRect();
    const right = Math.min(box.getBoundingClientRect().right, card.right);
    const cut = [...box.querySelectorAll('tr > :last-child')].map((cell) => {
        const text = document.createRange();
        text.selectNodeContents(cell);
        return [cell.textContent.replace(/\\s/g, ' '), Math.round(text.getBoundingClientRect().right - right)];
    }).filter(([, over]) => over > 0);
    return { scroll: box.scrollWidth - box.clientWidth, cut };
}"""


@pytest.mark.parametrize("width", [360, 375, 800, 900, 1024, 1100, 1280, 1440])
def test_two_forecasts_table_fits_its_card(full_flight, width):
    # На 1024 px столбец «Лучшая цена, ₽» обрезало справа, его можно было только прокрутить.
    full_flight.set_viewport_size({"width": width, "height": 900})
    full_flight.click('.tabs--main [data-tab="calc"]')
    full_flight.wait_for_selector("#compare-table:not([hidden])")

    assert full_flight.evaluate(COMPARE_FITS) == {"scroll": 0, "cut": []}


def test_empty_history_on_a_phone_is_seen_whole(browser, base_url):
    context, tab = open_tool(browser, base_url, 375)
    cut = tab.evaluate("""() => {
        const cell = document.querySelector('.history__empty td'), box = cell.closest('.table-scroll');
        const text = document.createRange();
        text.selectNodeContents(cell);
        return [text.getBoundingClientRect().right - box.getBoundingClientRect().right, box.scrollWidth - box.clientWidth];
    }""")
    context.close()

    assert cut[0] <= 0 and cut[1] == 0  # текст не уходит за правый край и прокручивать нечего


# --- правки по проверке вёрстки и доступности ---

COLORS = r"""
    const canvas = document.createElement('canvas').getContext('2d', { willReadFrequently: true });
    const rgb = (css) => {
        canvas.clearRect(0, 0, 1, 1);
        canvas.fillStyle = '#000';
        canvas.fillStyle = css;
        canvas.fillRect(0, 0, 1, 1);
        return [...canvas.getImageData(0, 0, 1, 1).data].slice(0, 3);
    };
    const lum = (c) => {
        const [r, g, b] = c.map((v) => { v /= 255; return v <= .03928 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4; });
        return .2126 * r + .7152 * g + .0722 * b;
    };
    const ratio = (a, b) => { const [x, y] = [lum(rgb(a)), lum(rgb(b))].sort((p, q) => q - p); return (x + .05) / (y + .05); };
"""


def guest_tab(browser, base_url, width, height=900):
    """Гость на /app без ожидания расчёта: для страниц, где нужно поймать момент загрузки."""
    context = browser.new_context(viewport={"width": width, "height": height})
    tab = context.new_page()
    become_guest(tab, base_url)
    tab.goto(base_url + "/app")
    return context, tab


PLANE_IN_VIEW = """async () => {
    await document.fonts.ready;
    const box = document.querySelector('.plane-box'), b = box.getBoundingClientRect();
    const inner = b.left + box.clientLeft;
    const parts = ['.plane', '.plane__craft', '.plane__fin--a', '.plane__fin--b', '.plane__wing--a', '.plane__wing--b']
        .map((s) => [s, Math.round(document.querySelector(s).getBoundingClientRect().left - inner)]);
    return { cut: parts.filter(([, left]) => left < 0), scroll: box.scrollWidth - box.clientWidth };
}"""


@pytest.mark.parametrize("width", [360, 375, 768, 1024, 1100, 1280, 1440, 1920])
def test_whole_plane_is_seen_in_the_salon(full_flight, width):
    # На 1024–1440 самолёт обрезало слева (justify-content: center при overflow-x: auto): нос и кили не прокрутить.
    full_flight.set_viewport_size({"width": width, "height": 900})
    full_flight.click('.tabs--main [data-tab="salon"]')

    assert full_flight.evaluate(PLANE_IN_VIEW) == {"cut": [], "scroll": 0}


def test_read_only_origin_is_skipped_by_tab_and_fields_show_focus(page):
    page.focus("#source")
    page.keyboard.press("Tab")
    focused = page.evaluate("""() => {
        const style = getComputedStyle(document.activeElement);
        return [document.activeElement.id, style.outlineStyle, style.outlineWidth];
    }""")
    origin = page.evaluate("() => getComputedStyle(document.querySelector('#origin')).backgroundColor")

    assert focused == ["destination", "solid", "2px"]
    assert origin == "rgba(0, 0, 0, 0)"  # поле только для чтения без белой подложки, не как обычное


def test_borders_of_fields_and_outline_buttons_stand_out(page):
    ratios = page.evaluate("() => {" + COLORS + """
        const card = getComputedStyle(document.querySelector('.card')).backgroundColor;
        const edge = (s) => getComputedStyle(document.querySelector(s)).borderTopColor;
        return {
            field: ratio(edge('#price'), getComputedStyle(document.querySelector('#price')).backgroundColor),
            fieldOnCard: ratio(edge('#price'), card),
            ghost: ratio(edge('#logout'), getComputedStyle(document.body).backgroundColor),
            tabs: ratio(edge('.tabs--main'), getComputedStyle(document.body).backgroundColor),
            scenario: ratio(edge('.scen__btn:not(.is-median)'), card),
        };
    }""")

    assert {name: value >= 3 for name, value in ratios.items()} == dict.fromkeys(ratios, True), ratios


DELAY_SAVES = """(ms) => {
    const send = window.fetch;
    window.fetch = async (url, options = {}) => {
        if (String(url).includes('/api/forecast') && String(options.body || '').includes('"save":true')) {
            await new Promise((done) => setTimeout(done, ms));
        }
        return send(url, options);
    };
}"""


def test_calculate_dims_the_old_result_instead_of_collapsing_it(page):
    before = page.evaluate("() => document.querySelector('#result').getBoundingClientRect().height")
    page.evaluate(DELAY_SAVES, 1500)
    page.click("#submit")
    page.wait_for_timeout(300)
    during = page.evaluate("() => document.querySelector('#result').getBoundingClientRect().height")
    wait_for_result(page)

    assert during >= before * 0.9, (before, during)


def test_saved_calculation_reaches_history_when_the_slider_moves_right_after(page):
    # «Рассчитать» и сразу ползунок: запрос с записью отменялся, запись в базе была, а в таблице — нет.
    page.evaluate(DELAY_SAVES, 800)
    page.click("#submit")
    page.wait_for_timeout(100)
    page.evaluate("""() => {
        const range = document.querySelector('#price-range');
        range.value = 6000;
        range.dispatchEvent(new Event('input', { bubbles: true }));
    }""")

    page.wait_for_function("() => !document.querySelector('#history-body .history__empty')", timeout=6000)


@pytest.mark.parametrize("width", [1024, 1100])
def test_landing_hero_fits_between_tablet_and_desktop(browser, base_url, width):
    context = browser.new_context(viewport={"width": width, "height": 900})
    tab = context.new_page()
    tab.goto(base_url + "/")
    lines, tops = tab.evaluate("""async () => {
        await document.fonts.ready;
        const title = document.createRange();
        title.selectNodeContents(document.querySelector('.lp-title'));
        const rows = new Set([...title.getClientRects()].map((r) => Math.round(r.top)));
        const tops = [...document.querySelectorAll('.lp-hero .lp-cta__item')].map((i) => Math.round(i.getBoundingClientRect().top));
        return [rows.size, tops];
    }""")
    context.close()

    assert lines <= 3 and len(set(tops)) == 1, (lines, tops)  # кнопки в ряд, а не столбиком


def test_story_chart_card_is_as_tall_as_its_content(browser, base_url):
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    tab = context.new_page()
    tab.goto(base_url + "/")
    tab.wait_for_function("() => document.querySelector('#story-chart svg')")
    empty = tab.evaluate("""() => {
        const card = document.querySelector('.story .case__card');
        return card.getBoundingClientRect().bottom - card.lastElementChild.getBoundingClientRect().bottom;
    }""")
    context.close()

    assert empty <= 40  # только отступ карточки, без 270 px пустоты под графиком


@pytest.mark.parametrize("width", [360, 375])
def test_jury_login_button_is_on_the_first_phone_screen(browser, base_url, width):
    context = browser.new_context(viewport={"width": width, "height": 800})
    tab = context.new_page()
    tab.goto(base_url + "/login")
    form, button = tab.evaluate("""() => [document.querySelector('#jury-form').getBoundingClientRect().top,
        document.querySelector('#jury-form button[type=submit]').getBoundingClientRect().bottom]""")
    context.close()

    assert form < 250 and button <= 800, (form, button)


NUMBER_SPACES = r"""() => {
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    const bad = [];
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
        if (!node.parentElement.closest('[hidden]') && /\d \d| ₽/.test(node.textContent)) bad.push(node.textContent.trim());
    }
    return bad;
}"""


def test_numbers_and_rubles_on_the_landing_do_not_break(browser, base_url):
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    tab = context.new_page()
    tab.goto(base_url + "/")
    tab.wait_for_function("() => document.querySelector('[data-story=\"chart-how\"]').textContent.includes('источник')")
    bad = tab.evaluate(NUMBER_SPACES)
    context.close()

    assert bad == []


CALENDAR_CONTRAST = "() => {" + COLORS + """
    return [...document.querySelectorAll('.cal__day[data-date]')].flatMap((day) => {
        const bg = getComputedStyle(day).backgroundColor;
        return [...day.querySelectorAll('.cal__date, .cal__load')]
            .map((text) => [day.dataset.date, Math.round(ratio(getComputedStyle(text).color, bg) * 100) / 100])
            .filter(([, value]) => value < 4.5);
    });
}"""


@pytest.mark.parametrize("price", ["3300", "5500", "8000"])
def test_calendar_day_numbers_are_readable_on_their_colour(browser, base_url, price):
    context, tab = guest_tab(browser, base_url, 1440)
    tab.goto(base_url + f"/app?destination=Санкт-Петербург&date=2026-06-12&price={price}&tab=calendar")
    tab.wait_for_function("() => document.querySelectorAll('.cal__day[data-date]').length > 20")
    low = tab.evaluate(CALENDAR_CONTRAST)
    context.close()

    assert low == []


def test_calendar_never_shades_a_day_where_neither_text_colour_reads(page):
    shades = page.evaluate("""async () => {
        const { shade } = await import('/static/js/calendar.js');
        return [...Array(101).keys()].map((load) => shade(load, { min: 0, max: 100 }));
    }""")

    assert [s for s in shades if 75 < s < 82] == []


def test_calendar_dates_on_a_phone_are_at_least_12px(browser, base_url):
    context, tab = open_tool(browser, base_url, 375)
    tab.click('.tabs--main [data-tab="calendar"]')
    tab.wait_for_selector(".cal__day[data-date]")
    size = tab.evaluate("() => parseFloat(getComputedStyle(document.querySelector('.cal__day[data-date] .cal__date')).fontSize)")
    context.close()

    assert size >= 12


TABS_WIRED = """(list) => {
    const tabs = [...document.querySelectorAll(list + ' [role="tab"]')];
    return tabs.map((tab) => {
        const panel = document.getElementById(tab.getAttribute('aria-controls'));
        return [tab.id !== '', panel && panel.getAttribute('role'), panel && panel.getAttribute('aria-labelledby') === tab.id,
                tab.tabIndex === (tab.getAttribute('aria-selected') === 'true' ? 0 : -1)];
    });
}"""

FOCUSED_TAB = """() => [document.activeElement.getAttribute('role'), document.activeElement.textContent.trim(),
    document.activeElement.getAttribute('aria-selected')]"""


def test_tool_tabs_follow_the_tabs_pattern(page):
    assert page.evaluate(TABS_WIRED, ".tabs--main") == [[True, "tabpanel", True, True]] * 4
    page.focus('.tabs--main [aria-selected="true"]')
    seen = []
    for key in ("ArrowRight", "End", "ArrowRight", "ArrowLeft", "Home"):
        page.keyboard.press(key)
        seen.append(page.evaluate(FOCUSED_TAB)[1])

    assert seen == ["Салон", "Талон", "Расчёт", "Талон", "Расчёт"]
    assert page.evaluate("() => document.querySelector('[data-tabpanel=\"salon\"]').hidden") is True
    assert page.evaluate("""() => [...document.querySelectorAll('[aria-live]')].map((e) => e.id)""") == ["note"]


def test_login_tabs_follow_the_tabs_pattern(browser, base_url):
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    tab = context.new_page()
    tab.goto(base_url + "/login")
    wired = tab.evaluate(TABS_WIRED, ".auth__card")
    tab.focus('.tabs [aria-selected="true"]')
    tab.keyboard.press("ArrowRight")
    after = [tab.evaluate(FOCUSED_TAB), tab.is_visible("#login-form")]
    context.close()

    assert wired == [[True, "tabpanel", True, True]] * 2
    assert after == [["tab", "Вход", "true"], True]


def test_phone_focus_order_matches_the_screen(browser, base_url):
    context, tab = open_tool(browser, base_url, 375)
    order = tab.evaluate("""() => {
        const result = document.querySelector('.main-col'), best = document.querySelector('#apply-best');
        return [Boolean(result.compareDocumentPosition(best) & Node.DOCUMENT_POSITION_FOLLOWING),
                best.getBoundingClientRect().top > result.getBoundingClientRect().bottom];
    }""")
    context.close()

    assert order == [True, True]  # «Поставить лучшую цену» и в порядке Tab, и на экране — после результата


def test_best_price_stays_under_the_form_on_a_desktop(page):
    form, best = page.evaluate("""() => [document.querySelector('#forecast-form').getBoundingClientRect().toJSON(),
        document.querySelector('#best').getBoundingClientRect().toJSON()]""")

    assert (best["left"], best["width"]) == (form["left"], form["width"])
    assert 0 < best["top"] - form["bottom"] <= 32


SMALL_TARGETS = """(selectors) => selectors.flatMap((s) => [...document.querySelectorAll(s)]
    .filter((e) => e.getClientRects().length)
    .map((e) => [s, Math.round(e.getBoundingClientRect().width), Math.round(e.getBoundingClientRect().height)])
    .filter(([, w, h]) => w < 44 || h < 44))"""


def test_touch_targets_on_a_phone_are_at_least_44px(browser, base_url):
    context, tab = open_tool(browser, base_url, 375)
    tab.click("#submit")
    tab.wait_for_selector("#history-body .link-btn")
    tab.click('.tabs--main [data-tab="salon"]')
    in_tool = tab.evaluate(SMALL_TARGETS, [".scen__btn", ".tabs--main .tabs__btn", ".topbar .btn", ".history .link-btn"])
    tab.goto(base_url + "/")
    on_landing = tab.evaluate(SMALL_TARGETS, [".topbar .btn"])
    context.close()
    context = browser.new_context(viewport={"width": 375, "height": 812})
    tab = context.new_page()
    tab.goto(base_url + "/login")
    on_login = tab.evaluate(SMALL_TARGETS, [".tabs__btn", ".field__toggle", ".link-btn"])
    context.close()

    assert (in_tool, on_landing, on_login) == ([], [], [])


CHART_LABELS = """() => {
    const svg = document.querySelector('#chart svg');
    const sizes = [...svg.querySelectorAll('.ch-tick, .ch-val, .ch-q, .ch-median-label')].map((t) => parseFloat(getComputedStyle(t).fontSize));
    const values = [...svg.querySelectorAll('.ch-val')].map((t) => t.getBBox());
    const touching = values.slice(1).filter((b, i) => {
        const a = values[i];
        return a.x + a.width + 2 > b.x && a.y < b.y + b.height && b.y < a.y + a.height;
    }).length;
    return { smallest: Math.min(...sizes), touching, quantiles: [...svg.querySelectorAll('.ch-q')].map((t) => t.textContent),
             axes: [...svg.querySelectorAll('.ch-axis')].map((t) => t.textContent) };
}"""


@pytest.mark.parametrize("width", [360, 375, 1440])
def test_demand_chart_labels_are_readable_and_named(browser, base_url, width):
    context, tab = open_tool(browser, base_url, width)
    labels = tab.evaluate(CHART_LABELS)
    legend = tab.inner_text("#best .legend")
    context.close()

    assert labels == {"smallest": 11, "touching": 0, "quantiles": [f"0,{i}" for i in range(1, 10)],
                      "axes": ["человек", "сценарий"]}
    assert "Лучшая цена" in legend  # пункт легенды у точки «Макс» на кривой прибыли


def test_seat_limit_has_one_colour_everywhere(full_flight):
    full_flight.set_viewport_size({"width": 1440, "height": 900})
    full_flight.click('.tabs--main [data-tab="salon"]')
    colours = full_flight.evaluate("""() => {
        const colour = (e, pseudo) => getComputedStyle(e, pseudo).color;
        const accent = getComputedStyle(document.querySelector('.accent')).color;
        return [accent, colour(document.querySelector('#note-tag')), colour(document.querySelector('#queue-title')),
                getComputedStyle(document.querySelector('.person'), '::before').backgroundColor];
    }""")

    assert len(set(colours)) == 1, colours


@pytest.mark.parametrize("width", [375, 1440])
def test_landing_numbers_card_lines_up_under_its_heading_without_a_double_rule(browser, base_url, width):
    # «Ключевые числа» — белая карточка вровень с заголовком; линия над первым кейсом одна и отстоит от карточки
    context = browser.new_context(viewport={"width": width, "height": 900})
    tab = context.new_page()
    tab.goto(base_url + "/")
    shift, gap = tab.evaluate("""() => {
        const card = document.querySelector('.lp-numbers').getBoundingClientRect();
        return [card.left - document.querySelector('#numbers .section-title').getBoundingClientRect().left,
                document.querySelector('#case .case').getBoundingClientRect().top - card.bottom];
    }""")
    context.close()

    assert round(shift) == 0 and gap >= 32, (shift, gap)


@pytest.mark.parametrize("width", [360, 375])
def test_phone_header_of_a_guest_fits_at_narrow_widths(browser, base_url, width):
    context, tab = guest_tab(browser, base_url, width, 800)
    lines, overflow = tab.evaluate("""async () => {
        await document.fonts.ready;
        const text = document.createRange();
        text.selectNodeContents(document.querySelector('.brand'));
        const rows = new Set([...text.getClientRects()].map((r) => Math.round(r.top)));
        return [rows.size, document.documentElement.scrollWidth - innerWidth];
    }""")
    context.close()

    assert (lines, overflow) == (1, 0)


def test_date_hint_names_the_available_range_with_a_dash(page):
    assert page.inner_text("#date-hint") == "Пт · День России · доступно 01.06–01.07.2026"


def test_missing_flight_moves_focus_to_the_date_without_a_useless_retry(page):
    page.fill("#date", "2026-07-15")
    page.dispatch_event("#date", "change")
    page.wait_for_selector('[data-panel="error"]:not([hidden])')
    state = page.evaluate("""() => [document.activeElement.id, document.querySelector('#retry').offsetParent === null,
        document.querySelector('#error-code').textContent]""")

    assert state == ["date", True, ""]


def test_price_out_of_the_new_route_range_is_kept_and_explained(page):
    page.fill("#price", "4000")
    page.locator("#price").blur()
    page.select_option("#destination", "Новосибирск")
    wait_for_result(page)

    assert page.input_value("#price") == "4 000"
    assert page.inner_text("#price-hint") == "Цена вне диапазона маршрута: 7 200–24 000 ₽"


@pytest.mark.parametrize("date", ["2026-08-15", "2026-02-30"])
def test_date_from_the_address_that_is_not_in_the_forecast_is_reported(browser, base_url, date):
    context, tab = guest_tab(browser, base_url, 1440)
    tab.goto(base_url + f"/app?date={date}")
    wait_for_result(tab)
    shown = [tab.input_value("#date"), tab.is_visible("#date-note"), tab.inner_text("#date-note")]
    context.close()

    assert shown[:2] == ["2026-06-01", True]
    assert date in shown[2] and "01.06.2026" in shown[2]


def test_unknown_source_in_the_address_falls_back_to_the_default(browser, base_url):
    context, tab = guest_tab(browser, base_url, 1440)
    tab.goto(base_url + "/app?source=xyz")
    wait_for_result(tab)
    form = tab.evaluate("""() => [document.querySelector('#destination').options.length > 1,
        document.querySelector('#price').value !== '', Number(document.querySelector('#price-range').max) > 1]""")
    context.close()

    assert form == [True, True, True]


def test_back_to_a_cached_tool_after_logout_leaves_no_errors(browser, base_url):
    context, tab = open_tool(browser, base_url)
    cached = tab.request.get(base_url + "/app").text()
    errors = []
    tab.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
    tab.click("#logout")
    tab.wait_for_url("**/login**")
    tab.route("**/app", lambda route: route.fulfill(status=200, content_type="text/html", body=cached))
    tab.goto(base_url + "/app")
    tab.wait_for_url("**/login**")
    context.close()

    assert errors == []


def test_register_link_keeps_the_guest_signed_in(browser, base_url):
    # История гостя переносится при регистрации на сервере, поэтому ссылка не выходит из гостя.
    context, tab = open_tool(browser, base_url)
    tab.click("#register-link")
    tab.wait_for_load_state()
    session = tab.request.get(base_url + "/api/session").json()
    context.close()

    assert session["user"] is not None and session["user"]["guest"] is True


# --- вариант 2 «Привычный сервис»: без украшений варианта 1 ---

ARROWS_IN_CONTROLS = """() => [...document.querySelectorAll('button, .btn, .link-btn, .file__open')]
    .map((control) => control.textContent).filter((text) => text.includes('→'))"""


def test_buttons_written_by_scripts_carry_no_arrow(page):
    # «5 605 ₽ →» в «Поставить лучшую цену» и «Повторить →» в истории пишет app.js
    page.click("#submit")
    page.wait_for_function("() => document.querySelector('#history-body .link-btn')")

    assert page.evaluate(ARROWS_IN_CONTROLS) == []


LABEL_FRAMES = """() => {
    const probe = (cls) => { const el = document.createElement('span'); el.className = cls; document.body.append(el); return el; };
    const tags = [...document.querySelectorAll('.tag, .chip'), probe('cal__cap')];
    const how = document.querySelector('.how');
    return [tags.length, tags.filter((el) => getComputedStyle(el).borderTopStyle !== 'none').map((el) => el.className),
            getComputedStyle(how, '::before').content];
}"""


def test_labels_are_plain_text_without_frames_or_arrows(browser, base_url):
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    tab = context.new_page()
    tab.goto(base_url + "/")
    count, framed, before = tab.evaluate(LABEL_FRAMES)
    context.close()

    assert count > 5 and framed == [] and before == "none"


# --- вариант 2 «Привычный сервис»: светло-серый фон, белые карточки, тёмные заголовки ---

SURFACES = """() => {
    const style = (s) => getComputedStyle(document.querySelector(s));
    const card = style('.card'), numbers = style('.lp-numbers');
    return {
        page: style('body').backgroundColor, topbar: style('.topbar').backgroundColor,
        card: [card.backgroundColor, card.borderTopLeftRadius, card.boxShadow !== 'none'],
        numbers: [numbers.backgroundColor, numbers.borderTopLeftRadius],
        headings: [...document.querySelectorAll('.section-title, .card-title')].map((h) => getComputedStyle(h).color),
        ink: style('.lp-title').color,
    };
}"""


def test_landing_has_grey_page_white_cards_and_dark_headings(browser, base_url):
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    tab = context.new_page()
    tab.goto(base_url + "/")
    found = tab.evaluate(SURFACES)
    context.close()

    white = "rgb(255, 255, 255)"
    assert found["page"] == "rgb(245, 246, 248)"  # --bg #F5F6F8
    assert (found["topbar"], found["card"], found["numbers"]) == (white, [white, "12px", True], [white, "12px"])
    assert len(found["headings"]) >= 6 and set(found["headings"]) == {found["ink"]}


# Висячие однобуквенные предлоги и союзы и тире, оторванное от числа: «в / другие пятницы», «— / 5 605 ₽».
LOOSE_WORDS = r"""() => {
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    const bad = [];
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
        if (node.parentElement.closest('[hidden]')) continue;
        const text = node.textContent;
        if (/(^|[^А-Яа-яЁё])[вксуоиаВКСУОИА] |— \d/.test(text)) bad.push(text.trim());
    }
    return bad;
}"""


def test_texts_written_by_the_landing_script_keep_short_words_together(browser, base_url):
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    tab = context.new_page()
    tab.goto(base_url + "/")
    tab.wait_for_function("() => document.querySelector('[data-story=\"chart-how\"]').textContent.includes('источник')")
    bad = tab.evaluate(LOOSE_WORDS)
    context.close()

    assert bad == []


def test_landing_header_stays_on_screen_and_does_not_cover_sections(browser, base_url):
    # шапка витрины не уезжает при прокрутке, а раздел по ссылке меню не прячется под неё
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    tab = context.new_page()
    tab.goto(base_url + "/")
    tab.evaluate("document.documentElement.style.scrollBehavior = 'auto'")
    tab.mouse.wheel(0, 2500)
    tab.wait_for_timeout(200)
    header_top = tab.evaluate("document.querySelector('.topbar').getBoundingClientRect().top")
    tab.click(".lp-nav a[href='#files']")
    tab.wait_for_timeout(300)
    header_bottom, title_top = tab.evaluate("""() => [document.querySelector('.topbar').getBoundingClientRect().bottom,
        document.querySelector('#files .section-title').getBoundingClientRect().top]""")
    context.close()

    assert header_top == 0
    assert title_top >= header_bottom, (title_top, header_bottom)
