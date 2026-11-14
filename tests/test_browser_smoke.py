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


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@pytest.fixture(scope="module")
def base_url(tmp_path_factory):
    port = free_port()
    # гостей здесь больше 20 за час: лимит регистраций с одного адреса проверяют другие тесты
    app = create_app(Settings(db_path=tmp_path_factory.mktemp("smoke") / "app.db", signup_limit=1000))
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
    tab.goto(base_url + "/login")
    tab.click("[data-guest]")
    tab.wait_for_url("**/app")
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


def test_page_is_drawn_with_the_three_design_fonts(page):
    loaded = page.evaluate("""async () => {
        await document.fonts.ready;
        return [...document.fonts].filter((f) => f.status === 'loaded').map((f) => f.family.replace(/["']/g, ''));
    }""")
    if not loaded:
        pytest.skip("шрифты Google Fonts не загрузились: нет интернета")

    assert set(loaded) == {"Unbounded", "Manrope", "Onest"}


def test_phone_header_of_a_guest_keeps_the_brand_on_one_line(browser, base_url):
    context = browser.new_context(viewport={"width": 375, "height": 812})
    tab = context.new_page()
    tab.goto(base_url + "/login")
    tab.click("[data-guest]")
    tab.wait_for_url("**/app")
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


def test_opening_the_story_without_login_leaves_no_errors_in_the_console(browser, base_url):
    # Раньше кнопка спрашивала GET /api/me, и в консоли гостя краснело «401 (Unauthorized)».
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    tab = context.new_page()
    errors = []
    tab.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
    tab.goto(base_url + "/")
    tab.click(".lp-cta [data-open-story]")
    tab.wait_for_url("**/app**")
    wait_for_result(tab)
    context.close()

    assert errors == []


@pytest.mark.parametrize("start", ["/", "/login"])
def test_guest_sees_the_story_flight_while_routes_are_still_loading(browser, base_url, start):
    # «Войти как гость» открывает /app без параметров. Пока сервер отвечает на /api/routes,
    # поля «Куда» и «Дата» уже заполнены, а вместо «Здесь появится прогноз» идёт расчёт.
    context = browser.new_context(viewport={"width": 1024, "height": 900})
    tab = context.new_page()
    held = []
    tab.route("**/api/routes*", lambda route: held.append(route))
    tab.goto(base_url + start)
    with tab.expect_request("**/api/routes*"):
        tab.click("[data-guest] >> nth=0")
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
                if (lines > 1 && /\d/.test(name)) problems.push(`${name}: перенос на ${lines} строки`);
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
