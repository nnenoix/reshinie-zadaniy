"""Страница /login: вкладка «Вход для жюри» с уже введёнными логином и паролем демо-аккаунта.

Пароль берётся из настройки DEMO_PASSWORD при запуске и в репозиторий не попадает.
Пароля нет (свой компьютер) — нет и вкладки жюри: страница открывается на обычном «Вход».
"""
import re
from html import escape

JURY_BLOCK = re.compile(r"<!-- jury:start -->.*?<!-- jury:end -->\s*", re.S)


def render_login(template: str, demo_login: str, demo_password: str) -> str:
    if demo_login and demo_password:
        html = template.replace("{{demo_login}}", escape(demo_login, quote=True))
        html = html.replace("{{demo_password}}", escape(demo_password, quote=True))
        return html.replace("<!-- jury:start -->", "").replace("<!-- jury:end -->", "")
    html = JURY_BLOCK.sub("", template)
    html = html.replace('aria-selected="false" data-tab="login"', 'aria-selected="true" data-tab="login"')
    return html.replace('data-form="login" action="/api/login" method="post" novalidate hidden>',
                        'data-form="login" action="/api/login" method="post" novalidate>')
