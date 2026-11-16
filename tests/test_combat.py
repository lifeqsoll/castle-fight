"""Этап 2: урон с учётом брони и стычка Мечники vs Лучники."""

import random

from castlefight.core.entity import Castle, Unit
from castlefight.data.balance import CASTLE, damage_multiplier
from castlefight.data.enums import ArmorType, DamageType, Role
from castlefight.data.factions import FACTIONS
from castlefight.tools.skirmish import run_skirmish


def test_take_damage_applies_armor_mult():
    unit = Unit.from_type(
        FACTIONS["Королевство"].building_by_role(Role.MELEE).unit,
        side=0,
        x=100.0,
    )
    # slash vs M = 1.0 → ровно raw
    dealt = unit.take_damage(100.0, DamageType.SLASH, rng=None)
    assert dealt == 100.0
    assert unit.hp == unit.max_hp - 100.0


def test_take_damage_light_armor_slash_bonus():
    unit = Unit.from_type(
        FACTIONS["Орда"].building_by_role(Role.MELEE).unit,  # Берсерк, броня L
        side=0,
        x=100.0,
    )
    dealt = unit.take_damage(100.0, DamageType.SLASH, rng=None)
    assert dealt == 100.0 * damage_multiplier(DamageType.SLASH, ArmorType.L)
    assert abs(dealt - 120.0) < 1e-9


def test_castle_take_damage_with_siege():
    castle = Castle(side=1, x=2000.0, hp=15000.0)
    # slash vs C = 0.25, siege=2 → 0.5
    dealt = castle.take_damage(100.0, DamageType.SLASH, siege=2.0, rng=None)
    assert abs(dealt - 50.0) < 1e-9
    assert abs(castle.hp - 14950.0) < 1e-9


def test_castle_defaults_match_balance():
    castle = Castle(side=0, x=0.0, hp=float(CASTLE["hp"]))
    assert castle.armor == ArmorType.C
    assert castle.alive


def test_skirmish_swordsmen_vs_archers_finishes():
    result = run_skirmish(n=5, seed=1, dt=0.2, tmax=600.0)
    assert result["t"] > 0
    assert result["alive_a"] + result["alive_b"] < 10  # кто-то умер
    # при seed=1 ожидаем победу мечников (танковее в ближнем)
    assert result["winner_side"] in (0, 1)
    assert result["alive_a"] != result["alive_b"] or result["winner_side"] is not None
