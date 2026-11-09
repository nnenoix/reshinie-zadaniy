"""Масштаб схемы салона.

Схема рисует не больше 150 кресел. Одно кресло на схеме — круглое число мест
(1, 2, 5, 10, 20 или 50), чтобы подпись читалась сразу: «1 кресло = 10 мест».
Последнее кресло может вмещать меньше. Кресла закрашиваются по доле проданных
мест, поэтому неполное кресло видно как частично закрашенное.

В данных бывает до 1440 мест в день — больше, чем в самом вместительном самолёте
(A380, до 853 мест). Тогда это сумма по нескольким рейсам дня, и ответ помечает
это флагом more_than_one_aircraft.
"""
import math
from dataclasses import dataclass

ICON_STEPS = (1, 2, 5, 10, 20, 50)
MAX_ICONS = 150
MAX_WAITING_ICONS = 35  # 5 рядов по 7 фигурок у трапа
LARGEST_AIRCRAFT_SEATS = 853  # A380 в самой плотной компоновке


@dataclass(frozen=True)
class SeatMap:
    seats: int
    seats_per_icon: int
    icons_total: int
    last_icon_seats: int
    waiting_people: float  # желают − места, если желающих больше (медианный сценарий)
    waiting_icons: int
    waiting_capped: bool  # очередь у трапа длиннее, чем помещается на схеме
    more_than_one_aircraft: bool  # мест больше, чем в любом самолёте: это несколько рейсов


def icon_scale(seats: int) -> int:
    return next((n for n in ICON_STEPS if math.ceil(seats / n) <= MAX_ICONS), ICON_STEPS[-1])


def seat_map(seats: int, wanted: float) -> SeatMap:
    per_icon = icon_scale(seats)
    total = math.ceil(seats / per_icon)
    waiting = max(0.0, wanted - seats)
    needed = math.ceil(waiting / per_icon)
    return SeatMap(
        seats=seats,
        seats_per_icon=per_icon,
        icons_total=total,
        last_icon_seats=seats - (total - 1) * per_icon,
        waiting_people=waiting,
        waiting_icons=min(needed, MAX_WAITING_ICONS),
        waiting_capped=needed > MAX_WAITING_ICONS,
        more_than_one_aircraft=seats > LARGEST_AIRCRAFT_SEATS,
    )
