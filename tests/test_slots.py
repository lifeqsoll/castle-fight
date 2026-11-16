"""Размещение зданий по ячейкам зоны застройки (без pygame)."""

import random

from castlefight.core.building import Building
from castlefight.core.game import Game
from castlefight.core.player import Player
from castlefight.data.balance import ECON, MAX_ULT, SLOTS
from castlefight.data.factions import FACTIONS


def _player(gold: float = 10_000) -> Player:
    p = Player(FACTIONS["Королевство"], 0, ECON["normal"])
    p.gold = gold
    return p


def test_buy_into_chosen_slot():
    p = _player()
    rng = random.Random(0)
    assert p.buy(0, rng, slot=7)
    assert p.building_at(7) is not None
    assert p.building_at(7).role.value == "melee"
    assert 7 not in p.free_slots()
    assert len(p.free_slots()) == SLOTS - 1


def test_cannot_buy_into_occupied_or_bad_slot():
    p = _player()
    rng = random.Random(0)
    assert p.buy(0, rng, slot=3)
    gold = p.gold
    assert not p.buy(1, rng, slot=3)  # занято
    assert not p.buy(1, rng, slot=SLOTS)  # вне зоны
    assert not p.buy(1, rng, slot=-1)
    assert p.gold == gold  # деньги не списаны


def test_buy_without_slot_takes_first_free():
    p = _player()
    rng = random.Random(0)
    p.buy(0, rng, slot=0)
    p.buy(0, rng, slot=1)
    assert p.buy(1, rng)
    assert p.buildings[-1].slot == 2


def test_twelve_slots_and_max_ult():
    p = _player()
    rng = random.Random(0)
    for i in range(MAX_ULT):
        assert p.buy(3, rng, slot=i)
    assert p.buy_block_reason(3) is not None
    assert not p.buy(3, rng, slot=5)
    for i in range(MAX_ULT, SLOTS):
        assert p.buy(0, rng, slot=i)
    assert p.free_slots() == []
    assert p.buy_block_reason(0) == "все 12 мест заняты"
    assert not p.buy(0, rng)


def test_gold_check_reason():
    p = _player(gold=10)
    assert p.buy_block_reason(0) == "не хватает золота"
    assert not p.buy(0, random.Random(0), slot=0)


def test_move_building_to_free_slot_is_free():
    p = _player()
    rng = random.Random(0)
    p.buy(0, rng, slot=2)
    p.buy(1, rng, slot=5)
    gold = p.gold
    assert p.move_building(2, 9)
    assert p.building_at(9).role.value == "melee"
    assert p.building_at(2) is None
    assert p.gold == gold
    assert not p.move_building(9, 5)  # занято
    assert not p.move_building(4, 6)  # пустая ячейка
    assert not p.move_building(9, SLOTS)


def test_legacy_append_gets_slot():
    p = _player()
    bt = p.faction.buildings[0]
    p.buildings.append(Building(bt, 1.0))
    p.buildings.append(Building(bt, 1.0))
    assert p.building_at(0) is not None and p.building_at(1) is not None
    assert len(p.free_slots()) == SLOTS - 2


def test_slot_does_not_change_simulation():
    """Без «Соседства» (одинаковые здания не рядом) ячейка — только визуал."""

    def run(slots):
        g = Game("Орда", "Лес", mode="turbo", seed=3)
        a, b = g.players
        a.gold = b.gold = 500
        for k, s in zip([0, 1, 0, 2], slots):
            a.buy(k, g.rng, slot=s)
            b.buy(k, g.rng)
        for _ in range(600):
            g.step()
        return round(g.world.t, 3), round(a.castle.hp, 3), round(b.castle.hp, 3), len(a.units), len(b.units)

    # мечники (k=0) не соседи ни в одной расстановке → матчи совпадают
    assert run([0, 1, 2, 3]) == run([11, 4, 7, 0])


def test_progress_between_zero_and_one():
    p = _player()
    rng = random.Random(0)
    p.buy(0, rng, slot=0)
    b = p.building_at(0)
    assert 0.0 <= b.progress <= 1.0
    for _ in range(100):
        u = b.tick(0.2, p, p.spawn_x(), rng)
        assert 0.0 <= b.progress <= 1.0
    assert b.spawned > 0
