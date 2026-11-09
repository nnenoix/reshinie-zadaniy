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
    app = create_app(Settings(db_path=tmp_path_factory.mktemp("smoke") / "app.db"))
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
    assert page.inner_text("#chart-odds").startswith("С вероятностью 80% желающих от 782 до 1 039")
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
