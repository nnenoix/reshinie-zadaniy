"""Схемы запросов и ответов для документации /docs (описания по-русски).

Входные данные проверяются в app/queries.py и app/auth.py, чтобы ошибки были
по-русски и с именем поля; модели запросов здесь только описывают формат.
"""
from pydantic import BaseModel, Field

# --- запросы ---


class CredentialsIn(BaseModel):
    login: str = Field(description="Логин или email: 3–64 буквы, цифры, точка, дефис, подчёркивание, @ или +",
                       examples=["anna"])
    password: str = Field(description="Пароль: 8–128 символов", examples=["пароль-для-примера"])
    password2: str | None = Field(None, description="Повтор пароля при регистрации (необязательно). "
                                                    "Если передан и не совпадает — ошибка")


class ForecastIn(BaseModel):
    origin: str = Field(description="Город вылета", examples=["Москва"])
    destination: str = Field(description="Город прилёта", examples=["Санкт-Петербург"])
    date: str = Field(description="Дата вылета, ГГГГ-ММ-ДД", examples=["2026-06-12"])
    price: float | str = Field(description="Цена билета, ₽. Можно строкой: «9 500», «9500,5»", examples=[5500])
    source: str | None = Field(None, description="Источник прогноза: organizers или ml. По умолчанию — ml, "
                                                 "если файл нашей модели есть, иначе organizers")
    save: bool = Field(False, description="true — записать расчёт в историю (кнопка «Посчитать»); "
                                          "false — предпросмотр ползунка")


# --- ответы ---


class ErrorOut(BaseModel):
    detail: str = Field(description="Что не так, по-русски")
    field: str | None = Field(None, description="Поле формы, к которому относится ошибка")


class UserOut(BaseModel):
    login: str


class MeOut(BaseModel):
    login: str
    guest: bool = Field(description="Временный гостевой аккаунт: ему показывается ссылка на регистрацию")


class SessionOut(BaseModel):
    user: MeOut | None = Field(description="Кто вошёл; null — вход не выполнен")


class OddsOut(BaseModel):
    low: float = Field(description="Желают в сценарии 0.1: нижняя граница коридора 80 %")
    high: float = Field(description="Желают в сценарии 0.9: верхняя граница коридора 80 %")
    sold_out_scenarios: int = Field(description="Сколько сценариев из 9 упираются в места; вероятность ≈ × 10 %")


class CsrfOut(BaseModel):
    token: str = Field(description="Значение для заголовка X-CSRF-Token (то же, что в cookie csrf_token)")


class HealthOut(BaseModel):
    status: str = Field(description="ok — сервер работает")
    version: str
    database: str = Field(description="sqlite или postgres")
    sources: dict[str, bool] = Field(description="Какие источники прогноза доступны")


class SourceOut(BaseModel):
    id: str = Field(description="organizers или ml")
    name: str
    file: str = Field(description="Имя файла прогноза")
    available: bool
    detail: str = Field(description="Число рейсов в файле или причина, почему источник недоступен")


class SourcesOut(BaseModel):
    sources: list[SourceOut]


class DestinationOut(BaseModel):
    name: str
    route: str = Field(description="Код маршрута, например MOW-LED")
    base_price: float
    price_min: float = Field(description="Нижняя граница ползунка цены")
    price_max: float = Field(description="Верхняя граница ползунка цены")
    cost_per_passenger: float = Field(description="Себестоимость одного пассажира, ₽")
    first_date: str
    last_date: str


class OriginOut(BaseModel):
    name: str
    destinations: list[DestinationOut]


class RoutesOut(BaseModel):
    source: str = Field(description="Источник прогноза, по которому собран список")
    holidays: dict[str, str] = Field(description="Праздники: дата ГГГГ-ММ-ДД → название")
    origins: list[OriginOut]


class RouteOut(BaseModel):
    code: str
    name: str
    origin: str
    destination: str
    base_price: float
    price_sensitivity: float
    cost_per_passenger: float
    price_min: float
    price_max: float


class ScenarioOut(BaseModel):
    quantile: float = Field(description="Квантиль прогноза: 0.1 … 0.9")
    base_demand: float
    wanted: float = Field(description="Желают при введённой цене")
    sold: float = Field(description="Купят: min(seats, max(0, желают))")
    sold_out: bool = Field(description="Продажи упираются в число мест")


class ExpectedOut(BaseModel):
    sold: float = Field(description="Среднее «купят» по 9 сценариям")
    revenue: float = Field(description="Ожидаемая выручка, ₽")
    profit: float = Field(description="Ожидаемая прибыль, ₽: выручка минус себестоимость проданных мест")


class BestOut(BaseModel):
    price: int = Field(description="Цена с наибольшей ожидаемой прибылью, целые рубли")
    expected: ExpectedOut
    gain: float | None = Field(description="Сколько ₽ ожидаемой прибыли даёт лучшая цена сверх введённой")
    price_difference: float | None = Field(description="Лучшая цена минус введённая, ₽")
    file_price: float | None = Field(description="0.5_price из файла прогноза (лучшая цена медианного сценария)")
    file_price_expected: ExpectedOut | None


class SeatMapOut(BaseModel):
    seats: int
    seats_per_icon: int = Field(description="Сколько мест означает одно кресло на схеме: 1, 2, 5, 10, 20 или 50")
    icons_total: int = Field(description="Кресел на схеме, не больше 150")
    last_icon_seats: int = Field(description="Сколько мест в последнем кресле (может быть меньше остальных)")
    waiting_people: float = Field(description="Желающих сверх мест — им не хватит билетов")
    waiting_icons: int
    waiting_capped: bool = Field(description="Очередь длиннее, чем помещается на схеме")
    max_waiting_icons: int = Field(description="Сколько фигурок помещается у трапа")
    more_than_one_aircraft: bool = Field(description="Мест больше, чем в любом самолёте (A380 — до 853): "
                                                     "это сумма по нескольким рейсам дня")


class ForecastOut(BaseModel):
    source: str
    route: RouteOut
    date: str
    weekday: str
    holiday: str | None
    price: float
    seats: int
    wanted: float = Field(description="желают = 0.5_base_demand − price_sensitivity × (цена − base_price)")
    sold: float = Field(description="купят = min(seats, max(0, желают))")
    sold_out: bool
    load: float = Field(description="Загрузка: купят / мест, от 0 до 1")
    expected: ExpectedOut = Field(description="Ожидаемые значения при введённой цене")
    best: BestOut
    seat_map: SeatMapOut
    scenarios: list[ScenarioOut]
    odds: OddsOut
    saved: bool = Field(description="Расчёт записан в историю")


class CurvePointOut(BaseModel):
    price: float
    profit: float
    revenue: float
    sold: float


class BestPriceOut(BaseModel):
    source: str
    route: RouteOut
    date: str
    price: float | None = Field(description="Введённая цена, если была передана")
    best: BestOut
    step: int = Field(description="Шаг кривой, ₽")
    curve: list[CurvePointOut] = Field(description="Ожидаемая прибыль и выручка от price_min до price_max")


class CalendarDayOut(BaseModel):
    date: str
    weekday: str
    is_friday: bool
    holiday: str | None
    seats: int
    wanted: float
    sold: float
    load: float
    sold_out: bool


class CalendarOut(BaseModel):
    source: str
    route: RouteOut
    price: float
    days: list[CalendarDayOut]


class CompareForecastOut(BaseModel):
    seats: int
    wanted: float
    sold: float
    sold_out: bool
    load: float
    best_price: int
    best_profit: float


class CompareSourceOut(BaseModel):
    source: str
    name: str
    available: bool
    detail: str
    forecast: CompareForecastOut | None


class CompareOut(BaseModel):
    date: str
    price: float
    sources: list[CompareSourceOut]


class HistoryItemOut(BaseModel):
    id: int
    created_at: str = Field(description="Время расчёта, UTC")
    source: str
    route_code: str
    origin: str
    destination: str
    date: str = Field(description="Дата вылета")
    price: float
    seats: int
    wanted: float
    sold: float
    load: float


class HistoryOut(BaseModel):
    items: list[HistoryItemOut]


class FridayOut(BaseModel):
    date: str
    median: float = Field(description="0.5_base_demand: спрос по базовой цене в медианном сценарии")
    is_story_day: bool


class StoryOut(BaseModel):
    source: str
    source_name: str
    route: RouteOut
    date: str
    weekday: str
    holiday: str | None
    seats: int
    median: float = Field(description="Медиана спроса в день истории (0.5_base_demand)")
    low: float = Field(description="Нижняя граница коридора: 0.1_base_demand")
    high: float = Field(description="Верхняя граница коридора: 0.9_base_demand")
    fridays: list[FridayOut] = Field(description="Все пятницы месяца, включая день истории")
    others_mean: float = Field(description="Средняя медиана других пятниц")
    drop: float = Field(description="На какую долю спрос дня истории ниже других пятниц, 0.13 = 13%")
    price: float = Field(description="Цена, для которой посчитаны сценарии (базовая цена маршрута)")
    scenarios: list[ScenarioOut]
    best: BestOut
