"""Тесты этапа 1: загрузка данных и таблица урона."""

from castlefight.data.balance import CASTLE, ECON, MULT, damage_multiplier, kill_bounty
from castlefight.data.enums import ArmorType, DamageType, Role
from castlefight.data.factions import FACTIONS, NECRO_RAISE, all_buildings


def test_six_factions_twenty_four_buildings():
    """Ровно 6 фракций и 24 здания."""
    assert len(FACTIONS) == 6
    buildings = all_buildings()
    assert len(buildings) == 24


def test_each_faction_has_four_roles():
    """У каждой фракции здания melee/ranged/summon/ult."""
    needed = {Role.MELEE, Role.RANGED, Role.SUMMON, Role.ULT}
    for name, faction in FACTIONS.items():
        roles = {b.role for b in faction.buildings}
        assert roles == needed, f"{name}: {roles}"


def test_damage_table_complete():
    """Таблица MULT покрывает все типы урона и все виды брони."""
    armors = set(ArmorType)
    dtypes = set(DamageType)
    assert set(MULT.keys()) == dtypes
    for dtype, row in MULT.items():
        assert set(row.keys()) == armors, f"дыры в строке {dtype}"
        for mult in row.values():
            assert isinstance(mult, float) and mult > 0


def test_damage_multiplier_known_values():
    """Проверка нескольких известных множителей из прототипа."""
    assert damage_multiplier(DamageType.SLASH, ArmorType.L) == 1.2
    assert damage_multiplier(DamageType.PIERCE, ArmorType.H) == 0.8
    assert damage_multiplier(DamageType.MAGIC, ArmorType.C) == 0.25
    assert damage_multiplier(DamageType.CASTLE, ArmorType.S) == 1.0


def test_kill_bounty_matches_prototype():
    """Обычные ≈1, дорогие ult ≈3."""
    assert kill_bounty(40) == 1
    assert kill_bounty(140) == 3
    assert kill_bounty(150) == 3


def test_sample_unit_numbers():
    """Точечная проверка чисел: Мечник и Титан как в classes.py."""
    kingdom = FACTIONS["Королевство"]
    swordsman = kingdom.building_by_role(Role.MELEE)
    assert swordsman.cost == 40
    assert swordsman.spawn == 8
    assert swordsman.unit.hp == 275
    assert swordsman.unit.dmg == 27
    assert swordsman.unit.bounty == 1

    forge = FACTIONS["Кузня"]
    titan = forge.building_by_role(Role.ULT)
    assert titan.cost == 150
    assert titan.unit.siege == 2.0
    assert titan.unit.hp == 1345


def test_summon_has_minion_template():
    """Summon-здания хранят шаблон миньона отдельно от BuildingType."""
    chaplain = FACTIONS["Королевство"].building_by_role(Role.SUMMON)
    assert chaplain.unit.minion is not None
    assert chaplain.unit.minion.role == Role.MINION
    assert chaplain.unit.minion.name == "Оруженосец"
    assert chaplain.unit.every == 6
    assert chaplain.unit.maxmin == 3
    assert chaplain.unit.total == 5


def test_necro_raise_and_econ_castle():
    """NECRO_RAISE и режимы экономики на месте."""
    assert NECRO_RAISE.name == "Поднятый"
    assert NECRO_RAISE.bounty == 0
    assert ECON["normal"]["castle_hp"] == 15000
    assert ECON["turbo"]["castle_hp"] == 6000
    assert CASTLE["dmg"] == 200
