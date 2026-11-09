import math

import pytest

from app.seatmap import ICON_STEPS, MAX_ICONS, MAX_WAITING_ICONS, seat_map


def test_scale_steps_are_round_numbers():
    assert ICON_STEPS == (1, 2, 5, 10, 20, 50)
    assert MAX_ICONS == 150


@pytest.mark.parametrize("seats, per_icon, icons, last", [
    (1440, 10, 144, 10),
    (900, 10, 90, 10),
    (450, 5, 90, 5),
    (360, 5, 72, 5),
    (270, 2, 135, 2),
    (150, 1, 150, 1),
    (151, 2, 76, 1),
    (1, 1, 1, 1),
])
def test_one_icon_is_a_round_number_of_seats(seats, per_icon, icons, last):
    cabin = seat_map(seats=seats, wanted=0)

    assert cabin.seats_per_icon == per_icon
    assert cabin.icons_total == icons == math.ceil(seats / per_icon) <= MAX_ICONS
    assert cabin.last_icon_seats == last


def test_queue_at_the_door():
    cabin = seat_map(seats=900, wanted=916)

    assert (cabin.waiting_people, cabin.waiting_icons, cabin.waiting_capped) == (16, 2, False)


def test_no_queue_when_seats_are_enough():
    cabin = seat_map(seats=1440, wanted=917)

    assert (cabin.waiting_people, cabin.waiting_icons) == (0, 0)


def test_negative_demand_means_no_queue():
    assert seat_map(seats=1440, wanted=-50).waiting_people == 0


def test_long_queue_is_capped():
    cabin = seat_map(seats=270, wanted=2000)

    assert cabin.waiting_people == 1730
    assert cabin.waiting_icons == MAX_WAITING_ICONS == 35
    assert cabin.waiting_capped is True


@pytest.mark.parametrize("seats, beyond", [(1440, True), (900, True), (853, False), (450, False), (270, False)])
def test_flags_when_seats_exceed_the_largest_airliner(seats, beyond):
    # Самый вместительный пассажирский самолёт (A380) сертифицирован на 853 места.
    assert seat_map(seats=seats, wanted=0).more_than_one_aircraft is beyond
