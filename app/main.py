"""HTTP-слой: страницы, API расчёта, вход, история, защита.

Запуск: uvicorn app.main:create_app --factory
"""
import logging
import math
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from time import perf_counter
from typing import Any, Callable

from fastapi import APIRouter, Body, Depends, FastAPI, Query, Request, Response, Security
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.security import APIKeyCookie, APIKeyHeader
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import schemas, views
from app.auth import AuthStore, LoginTaken, User, parse_credentials
from app.calendar import month_calendar
from app.catalog import CatalogError
from app.config import PROJECT_DIR, Settings
from app.errors import InputError
from app.history import HistoryEntry, HistoryStore, history_csv
from app.pricing import CURVE_STEP, advise, make_forecast, profit_curve
from app.queries import parse_flight_query, parse_forecast_query, parse_route_price_query, parse_source
from app.ratelimit import RateLimiter
from app.seatmap import seat_map
from app.story import STORY_DAY, STORY_ROUTE, friday_story
from app.security import (CSRF_COOKIE, CSRF_HEADER, client_address, csrf_problem, new_csrf_token,
                          security_headers)
from app.sources import ML, ORGANIZERS, ForecastSources

VERSION = "2.0"
STATIC_DIR = PROJECT_DIR / "static"
PAGES_DIR = PROJECT_DIR / "pages"
SESSION_COOKIE = "session"
log = logging.getLogger("aviaprognoz")

# Сообщения самого FastAPI/Starlette по-английски; здесь — их русские версии.
FRAMEWORK_ERRORS = {
    400: "Не удалось прочитать запрос: нужен JSON в кодировке UTF-8.",
    404: "Такого адреса нет.",
    405: "Этот адрес не принимает такой запрос.",
}
UNAUTHORIZED = "Войдите или зарегистрируйтесь, чтобы считать прогноз."

DESCRIPTION = """
Прогноз продаж авиабилетов по формуле кейса «Решись»:

    желают = 0.5_base_demand − price_sensitivity × (цена − base_price)
    купят  = min(seats, max(0, желают))

**Как пробовать здесь.** Расчёты доступны после входа. Войдите на главной странице
(кнопка «Войти как гость») — cookie сессии общая с этой страницей. Для POST-запросов нажмите
**Authorize** и вставьте в X-CSRF-Token значение из `GET /api/csrf`.

**Ошибки** приходят как `{"detail": "текст по-русски", "field": "имя поля или null"}`.
"""
TAGS = [
    {"name": "Прогноз", "description": "Расчёт продаж, лучшая цена, календарь, сравнение источников"},
    {"name": "Вход", "description": "Регистрация, вход, гость, выход"},
    {"name": "История", "description": "Сохранённые расчёты пользователя и выгрузка в CSV"},
    {"name": "Справочники", "description": "Маршруты и источники прогноза"},
    {"name": "Служебное", "description": "Проверка сервера и токен CSRF"},
]
ERRORS = {code: {"model": schemas.ErrorOut} for code in (401, 403, 422, 429)}

csrf_scheme = APIKeyHeader(name=CSRF_HEADER, auto_error=False,
                           description="Значение cookie csrf_token (его возвращает GET /api/csrf)")
session_scheme = APIKeyCookie(name=SESSION_COOKIE, auto_error=False,
                              description="Cookie сессии. Ставится при входе на главной странице")


class Unauthorized(Exception):
    pass


class TooManyAttempts(Exception):
    def __init__(self, message: str, wait_seconds: int):
        super().__init__(message)
        self.message = f"{message} Попробуйте через {math.ceil(wait_seconds / 60)} мин."
        self.wait_seconds = wait_seconds


def create_app(settings: Settings | None = None, now: Callable[[], datetime] | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    clock = now or (lambda: datetime.now(timezone.utc))
    _configure_logging()

    app = FastAPI(title="Прогноз продаж авиабилетов", description=DESCRIPTION, version=VERSION,
                  openapi_tags=TAGS, redoc_url=None)
    app.state.settings = settings
    app.state.clock = clock
    app.state.sources = ForecastSources(settings.routes_csv,
                                        {ORGANIZERS: settings.forecast_csv, ML: settings.ml_forecast_csv})
    _require_organizers_forecast(app.state.sources)
    app.state.auth = AuthStore(settings.db_path, session_ttl=timedelta(days=settings.session_days), now=clock)
    app.state.history = HistoryStore(settings.db_path)
    app.state.login_limiter = RateLimiter(settings.login_limit, timedelta(minutes=settings.login_window_minutes), clock)
    app.state.account_limiter = RateLimiter(settings.account_login_limit,
                                            timedelta(minutes=settings.account_login_window_minutes), clock)
    app.state.signup_limiter = RateLimiter(settings.signup_limit, timedelta(hours=1), clock)
    if settings.demo_login and settings.demo_password:
        app.state.auth.ensure_user(settings.demo_login, settings.demo_password)

    app.add_exception_handler(InputError, _input_error)
    app.add_exception_handler(RequestValidationError, _unreadable_request)
    app.add_exception_handler(Unauthorized, _unauthorized)
    app.add_exception_handler(TooManyAttempts, _too_many)
    app.add_exception_handler(StarletteHTTPException, _framework_error)
    app.add_exception_handler(Exception, _server_error)
    app.middleware("http")(_guard)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    app.include_router(router)
    return app


def _require_organizers_forecast(sources: ForecastSources) -> None:
    """Без прогноза организаторов сервер не запускается: в ошибке видно, какой файл не так."""
    try:
        sources.catalog(ORGANIZERS)
    except InputError as error:
        raise CatalogError(error.message) from None


def _configure_logging() -> None:
    if log.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    log.propagate = False


async def _guard(request: Request, call_next):
    """CSRF-проверка, заголовки безопасности и журнал запросов."""
    started = perf_counter()
    settings: Settings = request.app.state.settings
    cookie_token = request.cookies.get(CSRF_COOKIE)
    request.state.csrf_token = cookie_token or new_csrf_token()
    problem = csrf_problem(
        request.method, request.url.path, cookie_token, request.headers.get(CSRF_HEADER),
        request.headers.get("origin"), request.headers.get("host", ""),
    )
    if problem:
        log.warning("отклонён запрос %s %s: %s", request.method, request.url.path, problem)
        response = JSONResponse({"detail": problem, "field": None}, status_code=403)
    else:
        response = await call_next(request)
    if not cookie_token:
        response.set_cookie(CSRF_COOKIE, request.state.csrf_token, httponly=False, samesite="strict",
                            secure=settings.cookie_secure, path="/")
    for name, value in security_headers(request.url.path, settings.cookie_secure).items():
        response.headers[name] = value
    log.info("%s %s → %d за %.1f мс", request.method, request.url.path, response.status_code,
             (perf_counter() - started) * 1000)
    return response


# --- зависимости ---

def get_sources(request: Request) -> ForecastSources:
    return request.app.state.sources


def get_auth(request: Request) -> AuthStore:
    return request.app.state.auth


def get_history(request: Request) -> HistoryStore:
    return request.app.state.history


def current_user(request: Request, auth: AuthStore = Depends(get_auth),
                 _: str | None = Security(session_scheme)) -> User:
    user = auth.user_for_session(request.cookies.get(SESSION_COOKIE))
    if user is None:
        raise Unauthorized()
    return user


def client_ip(request: Request) -> str:
    peer = request.client.host if request.client else None
    return client_address(request.headers, peer, request.app.state.settings.client_ip_header)


def body_doc(model: type[BaseModel]) -> dict:
    """Схема тела запроса для /docs: сами данные проверяются вручную, чтобы ошибки были по-русски."""
    return {"requestBody": {"required": True, "content": {"application/json": {"schema": model.model_json_schema()}}}}


Q_ORIGIN = Query(None, description="Город вылета", examples=["Москва"])
Q_DESTINATION = Query(None, description="Город прилёта", examples=["Санкт-Петербург"])
Q_DATE = Query(None, description="Дата вылета, ГГГГ-ММ-ДД", examples=["2026-06-12"])
Q_SOURCE = Query(None, description="Источник прогноза: organizers или ml. По умолчанию — ml, если файл "
                                   "нашей модели есть, иначе organizers")

router = APIRouter()
csrf_protected = [Security(csrf_scheme)]


# --- страницы ---

def signed_in(request: Request) -> bool:
    return request.app.state.auth.user_for_session(request.cookies.get(SESSION_COOKIE)) is not None


@router.get("/", include_in_schema=False)
def landing_page() -> FileResponse:
    return FileResponse(PAGES_DIR / "landing.html")


@router.get("/login", include_in_schema=False, response_model=None)
def login_page(request: Request) -> Response:
    if signed_in(request):
        return RedirectResponse("/app", status_code=303)
    return FileResponse(PAGES_DIR / "login.html")


@router.get("/app", include_in_schema=False, response_model=None)
def tool_page(request: Request) -> Response:
    if not signed_in(request):
        return RedirectResponse("/login", status_code=303)
    return FileResponse(PAGES_DIR / "app.html")


# --- служебное ---


@router.get("/api/health", tags=["Служебное"], response_model=schemas.HealthOut, summary="Сервер работает?")
def health(sources: ForecastSources = Depends(get_sources)) -> dict:
    return {"status": "ok", "version": VERSION, "sources": {s.id: s.available for s in sources.describe()}}


@router.get("/api/csrf", tags=["Служебное"], response_model=schemas.CsrfOut, summary="Токен защиты от CSRF",
            description="Ставит cookie csrf_token и возвращает её значение. Его нужно передавать "
                        "в заголовке X-CSRF-Token во всех POST-запросах.")
def csrf(request: Request) -> dict:
    return {"token": request.state.csrf_token}


@router.get("/api/sources", tags=["Справочники"], response_model=schemas.SourcesOut,
            summary="Источники прогноза",
            description="Прогноз организаторов (seasonal_forecast.csv) и нашей ML-модели (my_forecast.csv). "
                        "Если файла ML-модели пока нет, источник помечен как недоступный.")
def sources_list(sources: ForecastSources = Depends(get_sources)) -> dict:
    return {"sources": [asdict(s) for s in sources.describe()]}


@router.get("/api/routes", tags=["Справочники"], response_model=schemas.RoutesOut, responses=ERRORS,
            summary="Города, направления, цены и даты для формы")
def routes(source: str | None = Q_SOURCE, sources: ForecastSources = Depends(get_sources)) -> dict:
    source_id = parse_source({"source": source}, sources.default_source())
    return views.routes_json(source_id, sources.catalog(source_id))


# --- вход ---

@router.post("/api/register", tags=["Вход"], status_code=201, response_model=schemas.UserOut,
             responses={409: {"model": schemas.ErrorOut}, **ERRORS}, dependencies=csrf_protected,
             openapi_extra=body_doc(schemas.CredentialsIn), summary="Регистрация",
             description="Создаёт аккаунт и сразу входит. С одного адреса — не больше 20 новых аккаунтов в час.")
def register(request: Request, response: Response, payload: Any = Body(None),
             auth: AuthStore = Depends(get_auth)) -> dict:
    _check_signup_limit(request)
    login, password = parse_credentials(payload)
    try:
        user = auth.register(login, password)
    except LoginTaken:
        return JSONResponse({"detail": f"Логин «{login}» уже занят.", "field": "login"}, status_code=409)
    request.app.state.signup_limiter.hit(client_ip(request))
    _start_session(request, response, user)
    return {"login": user.login}


@router.post("/api/login", tags=["Вход"], response_model=schemas.UserOut, responses=ERRORS,
             dependencies=csrf_protected, openapi_extra=body_doc(schemas.CredentialsIn), summary="Вход",
             description="После 5 неудачных попыток за 5 минут вход для этого логина с этого адреса "
                         "закрывается на 5 минут, после 10 неудачных попыток с любых адресов за 15 минут — "
                         "вход в этот аккаунт (ответ 429).")
def login(request: Request, response: Response, payload: Any = Body(None),
          auth: AuthStore = Depends(get_auth)) -> dict:
    data = payload if isinstance(payload, dict) else {}
    login_text = str(data.get("login") or "").strip()
    limiter: RateLimiter = request.app.state.login_limiter
    account_limiter: RateLimiter = request.app.state.account_limiter
    account = login_text.casefold()
    key = f"{client_ip(request)}|{account}"
    wait = limiter.retry_after(key)
    if wait:
        log.warning("вход закрыт на %d с: логин=%r, адрес=%s", wait, login_text, client_ip(request))
        raise TooManyAttempts("Слишком много неудачных попыток входа.", wait)
    wait = account_limiter.retry_after(account)
    if wait:
        log.warning("аккаунт закрыт на %d с: логин=%r, адрес=%s", wait, login_text, client_ip(request))
        raise TooManyAttempts("Слишком много неудачных попыток входа в этот аккаунт.", wait)
    user = auth.authenticate(login_text, str(data.get("password") or ""))
    if user is None:
        limiter.hit(key)
        account_limiter.hit(account)
        log.warning("неудачный вход: логин=%r, адрес=%s", login_text, client_ip(request))
        return JSONResponse({"detail": "Неверный логин или пароль.", "field": None}, status_code=401)
    limiter.reset(key)
    account_limiter.reset(account)
    _start_session(request, response, user)
    return {"login": user.login}


@router.post("/api/guest", tags=["Вход"], status_code=201, response_model=schemas.UserOut, responses=ERRORS,
             dependencies=csrf_protected, summary="Войти как гость",
             description="Создаёт временный аккаунт «гость-…» без пароля и входит в него. "
                         "У каждого гостя своя история.")
def guest(request: Request, response: Response, auth: AuthStore = Depends(get_auth)) -> dict:
    _check_signup_limit(request)
    user = auth.create_guest()
    request.app.state.signup_limiter.hit(client_ip(request))
    _start_session(request, response, user)
    return {"login": user.login}


@router.post("/api/logout", tags=["Вход"], status_code=204, dependencies=csrf_protected, summary="Выход")
def logout(request: Request, auth: AuthStore = Depends(get_auth)) -> Response:
    auth.close_session(request.cookies.get(SESSION_COOKIE))
    response = Response(status_code=204)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@router.get("/api/me", tags=["Вход"], response_model=schemas.UserOut, responses=ERRORS, summary="Кто вошёл")
def me(user: User = Depends(current_user)) -> dict:
    return {"login": user.login}


# --- прогноз ---

@router.post("/api/forecast", tags=["Прогноз"], response_model=schemas.ForecastOut, responses=ERRORS,
             dependencies=csrf_protected, openapi_extra=body_doc(schemas.ForecastIn),
             summary="Прогноз продаж рейса",
             description="Число мест и прогноз продаж: желают = 0.5_base_demand − price_sensitivity × "
                         "(цена − base_price), купят = min(seats, max(0, желают)). Плюс 9 сценариев для "
                         "графика, ожидаемая прибыль, лучшая цена и схема салона. "
                         "С save=true расчёт попадает в историю.")
def forecast(request: Request, payload: Any = Body(None), user: User = Depends(current_user),
             sources: ForecastSources = Depends(get_sources), history: HistoryStore = Depends(get_history)) -> dict:
    source = parse_source(payload, sources.default_source())
    query = parse_forecast_query(sources.catalog(source), payload)
    route, flight = query.route, query.flight
    result = make_forecast(route, flight, query.price)
    save = payload.get("save") is True
    if save:
        history.add(user.id, HistoryEntry(
            created_at=request.app.state.clock(), source=source, route_code=route.code, origin=route.origin,
            destination=route.destination, flight_date=flight.date, price=query.price, seats=result.seats,
            wanted=result.median.wanted, sold=result.median.sold,
        ))
    cabin = seat_map(result.seats, result.median.wanted)
    return views.forecast_json(source, route, flight, result, advise(route, flight, query.price), cabin, save)


@router.get("/api/best-price", tags=["Прогноз"], response_model=schemas.BestPriceOut, responses=ERRORS,
            summary="Лучшая цена и кривая прибыли",
            description="Ожидаемая прибыль = среднее по 9 сценариям от (цена − cost_per_passenger) × "
                        "min(seats, max(0, спрос сценария)). Кривая — от price_min до price_max с шагом 10 ₽; "
                        "лучшая цена найдена точно, в целых рублях. С price в ответе есть разница "
                        "с введённой ценой.")
def get_best_price(origin: str | None = Q_ORIGIN, destination: str | None = Q_DESTINATION,
                   date: str | None = Q_DATE,
                   price: str | None = Query(None, description="Введённая цена для сравнения, ₽"),
                   source: str | None = Q_SOURCE, user: User = Depends(current_user),
                   sources: ForecastSources = Depends(get_sources)) -> dict:
    data = {"origin": origin, "destination": destination, "date": date, "price": price, "source": source}
    source_id = parse_source(data, sources.default_source())
    query = parse_flight_query(sources.catalog(source_id), data)
    advice = advise(query.route, query.flight, query.price)
    curve = profit_curve(query.route, query.flight)
    return views.best_price_json(source_id, query.route, query.flight, advice, curve, CURVE_STEP)


@router.get("/api/calendar", tags=["Прогноз"], response_model=schemas.CalendarOut, responses=ERRORS,
            summary="Загрузка по дням месяца",
            description="Для выбранного маршрута и цены — прогноз на каждый день из файла прогноза: "
                        "загрузка, упор в места, пятницы и праздник 12 июня.")
def get_calendar(origin: str | None = Q_ORIGIN, destination: str | None = Q_DESTINATION,
                 price: str | None = Query(None, description="Цена билета, ₽", examples=[5500]),
                 source: str | None = Q_SOURCE, user: User = Depends(current_user),
                 sources: ForecastSources = Depends(get_sources)) -> dict:
    data = {"origin": origin, "destination": destination, "price": price, "source": source}
    source_id = parse_source(data, sources.default_source())
    catalog = sources.catalog(source_id)
    query = parse_route_price_query(catalog, data)
    days = month_calendar(query.route, catalog.flights_for(query.route.code), query.price)
    return views.calendar_json(source_id, query.route, query.price, days)


@router.get("/api/compare", tags=["Прогноз"], response_model=schemas.CompareOut, responses=ERRORS,
            summary="Сравнить прогноз организаторов и нашей ML-модели на одном рейсе")
def compare(origin: str | None = Q_ORIGIN, destination: str | None = Q_DESTINATION, date: str | None = Q_DATE,
            price: str | None = Query(None, description="Цена билета, ₽", examples=[5500]),
            user: User = Depends(current_user), sources: ForecastSources = Depends(get_sources)) -> dict:
    data = {"origin": origin, "destination": destination, "date": date, "price": price}
    checked = parse_forecast_query(sources.catalog(ORGANIZERS), data)
    rows = []
    for info in sources.describe():
        row = {"source": info.id, "name": info.name, "available": info.available, "detail": info.detail,
               "forecast": None}
        if info.available:
            try:
                query = parse_forecast_query(sources.catalog(info.id), data)
            except InputError as error:
                row.update(available=False, detail=error.message)
            else:
                result = make_forecast(query.route, query.flight, query.price)
                row["forecast"] = views.compare_forecast_json(result, advise(query.route, query.flight, None))
        rows.append(row)
    return {"date": checked.flight.date.isoformat(), "price": checked.price, "sources": rows}


@router.get("/api/story", tags=["Прогноз"], response_model=schemas.StoryOut, responses=ERRORS,
            summary="Сквозная история: пятница 12 июня на рейсе Москва → Санкт-Петербург",
            description="Публичный адрес для витрины. Медиана спроса 12 июня, коридор 10–90 %, все пятницы "
                        "июня и на сколько 12 июня ниже остальных; 9 сценариев и лучшая цена при базовой цене.")
def story(source: str | None = Q_SOURCE, sources: ForecastSources = Depends(get_sources)) -> dict:
    source_id = parse_source({"source": source}, sources.default_source())
    catalog = sources.catalog(source_id)
    route = catalog.routes[STORY_ROUTE]
    try:
        told = friday_story(route, catalog.flights_for(STORY_ROUTE), STORY_DAY)
    except ValueError as error:
        raise InputError("source", f"{sources.name(source_id)}: {error}") from None
    result = make_forecast(route, told.flight, route.base_price)
    advice = advise(route, told.flight, route.base_price)
    return views.story_json(source_id, sources.name(source_id), told, result, advice)


# --- история ---

@router.get("/api/history", tags=["История"], response_model=schemas.HistoryOut, responses=ERRORS,
            summary="Последние расчёты")
def history_latest(limit: int = Query(10, ge=1, le=50, description="Сколько расчётов вернуть, 1–50"),
                   user: User = Depends(current_user), history: HistoryStore = Depends(get_history)) -> dict:
    return {"items": [views.history_item_json(e) for e in history.latest(user.id, limit)]}


@router.get("/api/history.csv", tags=["История"], responses=ERRORS, summary="Вся история в CSV",
            description="CSV для Excel: кодировка UTF-8 с BOM, разделитель «;», десятичная запятая.",
            response_class=Response)
def history_export(user: User = Depends(current_user), history: HistoryStore = Depends(get_history)) -> Response:
    return Response(
        content=history_csv(history.all(user.id)).encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="aviaprognoz-history.csv"'},
    )


# --- сессии и ошибки ---

def _check_signup_limit(request: Request) -> None:
    wait = request.app.state.signup_limiter.retry_after(client_ip(request))
    if wait:
        raise TooManyAttempts("Слишком много новых аккаунтов с одного адреса.", wait)


def _start_session(request: Request, response: Response, user: User) -> None:
    settings: Settings = request.app.state.settings
    response.set_cookie(
        SESSION_COOKIE,
        request.app.state.auth.open_session(user),
        max_age=settings.session_days * 24 * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


async def _input_error(request: Request, error: InputError) -> JSONResponse:
    return JSONResponse({"detail": error.message, "field": error.field}, status_code=422)


async def _unreadable_request(request: Request, error: RequestValidationError) -> JSONResponse:
    problems = error.errors()
    if any(p.get("type") == "json_invalid" for p in problems) or not problems:
        return JSONResponse({"detail": "Не удалось прочитать запрос: нужен JSON-объект.", "field": None},
                            status_code=422)
    name = str(problems[0].get("loc", ["", ""])[-1])
    return JSONResponse({"detail": f"Неверное значение параметра «{name}».", "field": name}, status_code=422)


async def _unauthorized(request: Request, error: Unauthorized) -> JSONResponse:
    return JSONResponse({"detail": UNAUTHORIZED, "field": None}, status_code=401)


async def _too_many(request: Request, error: TooManyAttempts) -> JSONResponse:
    return JSONResponse({"detail": error.message, "field": None}, status_code=429,
                        headers={"Retry-After": str(error.wait_seconds)})


async def _framework_error(request: Request, error: StarletteHTTPException) -> JSONResponse:
    detail = FRAMEWORK_ERRORS.get(error.status_code, error.detail)
    return JSONResponse({"detail": detail, "field": None}, status_code=error.status_code,
                        headers=getattr(error, "headers", None))


async def _server_error(request: Request, error: Exception) -> JSONResponse:
    log.exception("ошибка при обработке %s %s", request.method, request.url.path)
    return JSONResponse({"detail": "Внутренняя ошибка сервера. Она записана в журнал.", "field": None},
                        status_code=500)
