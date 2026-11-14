"""Число автотестов на витрине и слова, согласованные с ним.

Число живёт только здесь. Тест tests/test_pages.py сверяет его с pytest --collect-only:
после нового теста меняется одна строка, а «автотест», «автотеста», «автотестов» подбираются сами.
"""
TESTS_IN_SUITE = 547

TESTS = ("автотест", "автотеста", "автотестов")
CHECK = ("проверяет", "проверяют", "проверяют")


def plural(n: int, forms: tuple[str, str, str]) -> str:
    """plural(5, ("место", "места", "мест")) → «мест»: форма для 1, для 2–4 и для 5–20."""
    one, few, many = forms
    tens, units = n % 100, n % 10
    if 10 < tens < 20:
        return many
    if units == 1:
        return one
    if 2 <= units <= 4:
        return few
    return many


def count_phrases(n: int) -> dict[str, str]:
    """Подстановки в pages/landing.html: метка шаблона → текст."""
    count = f"<span data-tests>{n}</span>"
    word, verb = plural(n, TESTS), plural(n, CHECK)
    return {
        "<!-- tests-count -->": count,
        "<!-- tests-word -->": word,
        "<!-- tests-label -->": f"{word} {verb} сервис",
        "<!-- tests-sentence -->": f"Сервис {verb} {count} {word}.",
    }


def fill_tests(template: str, n: int = TESTS_IN_SUITE) -> str:
    for mark, text in count_phrases(n).items():
        template = template.replace(mark, text)
    return template
