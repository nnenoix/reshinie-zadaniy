"""Защита cookie-сессий от CSRF и заголовки безопасности.

CSRF: браузер получает cookie csrf_token (её может прочитать скрипт страницы, SameSite=Strict).
Каждый POST к /api/ должен прислать то же значение в заголовке X-CSRF-Token. Чужой сайт
не может ни прочитать cookie, ни поставить свой заголовок без CORS, которого здесь нет.
Дополнительно запросы с заголовком Origin другого сайта отклоняются.

Адрес клиента для лимитов берётся из TCP-соединения. X-Forwarded-For по умолчанию
не читается: его может прислать сам клиент, и прокси Render его не очищает, а только
дописывает. За прокси адрес берётся из заголовка, который ставит сам прокси
(на Render — CF-Connecting-IP от Cloudflare); имя заголовка задаёт CLIENT_IP_HEADER.
"""
import hmac
import ipaddress
import secrets
from typing import Mapping
from urllib.parse import urlsplit

CSRF_COOKIE = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
DOCS_PATHS = ("/docs", "/openapi.json")

NO_TOKEN = "Запрос отклонён: нет защитного токена. Обновите страницу и повторите."
FOREIGN_ORIGIN = "Запрос с чужого сайта отклонён."

# html2canvas 1.4.1 (картинка талона) вставляет один постоянный <style>, который прячет
# исходные ::before/::after на время снимка. Разрешён ровно он — по хешу, без 'unsafe-inline'.
HTML2CANVAS_STYLE = "'sha256-UP0QZg7irvSMvOBz9mH2PIIE28+57UiavRfeVea0l3g='"

PAGE_CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self' https://cdnjs.cloudflare.com",
    f"style-src 'self' https://fonts.googleapis.com {HTML2CANVAS_STYLE}",
    "font-src 'self' https://fonts.gstatic.com",
    "img-src 'self' data: blob:",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
])
# Swagger UI грузится с cdn.jsdelivr.net и запускается встроенным скриптом.
DOCS_CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",
    "img-src 'self' data: https://fastapi.tiangolo.com",
    "connect-src 'self'",
    "object-src 'none'",
    "frame-ancestors 'none'",
])


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def csrf_problem(method: str, path: str, cookie_token: str | None, header_token: str | None,
                 origin: str | None, own_host: str) -> str | None:
    """Почему запрос нужно отклонить, или None, если всё в порядке.

    Origin сверяется по адресу сайта без схемы: за HTTPS-прокси сервер видит http,
    а браузер присылает https.
    """
    if method not in UNSAFE_METHODS or not path.startswith("/api/"):
        return None
    if origin is not None and urlsplit(origin).netloc.lower() != own_host.lower():
        return FOREIGN_ORIGIN
    if not cookie_token or not header_token or not hmac.compare_digest(cookie_token, header_token):
        return NO_TOKEN
    return None


def security_headers(path: str, https: bool) -> dict[str, str]:
    headers = {
        "Content-Security-Policy": DOCS_CSP if path.startswith(DOCS_PATHS) else PAGE_CSP,
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "same-origin",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
        "Cross-Origin-Opener-Policy": "same-origin",
    }
    if path.startswith("/api/"):
        headers["Cache-Control"] = "no-store"
    elif path.startswith("/static/"):
        headers["Cache-Control"] = "no-cache"  # браузер сверяет ETag: после деплоя модули не смешиваются
    if https:
        headers["Strict-Transport-Security"] = "max-age=31536000"
    return headers


def client_address(headers: Mapping[str, str], peer: str | None, trusted_header: str | None) -> str:
    """Адрес клиента для лимитов.

    trusted_header — заголовок, который ставит свой прокси (например, cf-connecting-ip).
    Если в нём список, берётся последний адрес: его дописал ближайший прокси.
    Пустой или испорченный заголовок не учитывается.
    """
    if trusted_header:
        candidate = headers.get(trusted_header.lower(), "").split(",")[-1].strip()
        try:
            return str(ipaddress.ip_address(candidate))
        except ValueError:
            pass
    return peer or "unknown"
