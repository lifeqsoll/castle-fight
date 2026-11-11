"""Шаблоны юнитов, зданий и фракций."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from castlefight.data.balance import kill_bounty
from castlefight.data.enums import ArmorType, DamageType, Role


@dataclass(frozen=True)
class UnitType:
    """Шаблон юнита (или миньона): статы боя и опциональные способности."""

    name: str
    role: Role
    dtype: DamageType
    armor: ArmorType
    hp: float
    dmg: float
    cd: float  # перезарядка атаки, сек
    rng: float  # дальность атаки
    spd: float  # скорость движения
    bounty: int = 0  # награда за убийство (у миньонов 0)

    # --- способности (пустые = нет способности) ---
    minion: Optional[UnitType] = None  # кого призывает summon
    every: Optional[float] = None  # интервал призыва, сек
    maxmin: Optional[int] = None  # максимум живых миньонов
    total: Optional[int] = None  # всего призывов за жизнь
    aura_heal: Optional[float] = None  # лечение союзников в радиусе 150
    regen: Optional[float] = None  # самолечение в секунду
    cleave: Optional[float] = None  # доля урона по соседям (клив)
    splash: Optional[float] = None  # доля урона по соседям (сплеш)
    raise_dead: bool = False  # поднимать убитых врагов
    siege: Optional[float] = None  # множитель урона по замку


@dataclass(frozen=True)
class BuildingType:
    """Шаблон здания: что спавнит, сколько стоит, как часто."""

    unit: UnitType
    cost: int
    spawn: float  # интервал спавна, сек

    @property
    def name(self) -> str:
        return self.unit.name

    @property
    def role(self) -> Role:
        return self.unit.role


@dataclass(frozen=True)
class Faction:
    """Фракция: имя и ровно 4 здания (melee, ranged, summon, ult)."""

    name: str
    buildings: tuple[BuildingType, BuildingType, BuildingType, BuildingType]

    def building_by_role(self, role: Role) -> BuildingType:
        """Найти здание фракции по роли."""
        for b in self.buildings:
            if b.role == role:
                return b
        raise KeyError(f"У фракции {self.name!r} нет здания роли {role}")


def _unit(
    name: str,
    role: Role,
    dtype: DamageType,
    armor: ArmorType,
    hp: float,
    dmg: float,
    cd: float,
    rng: float,
    spd: float,
    *,
    bounty: int = 0,
    **abilities,
) -> UnitType:
    """Создать UnitType с опциональными полями способностей."""
    return UnitType(
        name=name,
        role=role,
        dtype=dtype,
        armor=armor,
        hp=hp,
        dmg=dmg,
        cd=cd,
        rng=rng,
        spd=spd,
        bounty=bounty,
        **abilities,
    )


def _minion(
    name: str,
    dtype: DamageType,
    armor: ArmorType,
    hp: float,
    dmg: float,
    cd: float,
    rng: float,
    spd: float,
    bounty: int = 0,
    **abilities,
) -> UnitType:
    """Создать шаблон миньона (роль MINION, обычно bounty=0)."""
    return _unit(
        name,
        Role.MINION,
        dtype,
        armor,
        hp,
        dmg,
        cd,
        rng,
        spd,
        bounty=bounty,
        **abilities,
    )


def _building(
    name: str,
    role: Role,
    dtype: DamageType,
    armor: ArmorType,
    hp: float,
    dmg: float,
    cd: float,
    rng: float,
    spd: float,
    cost: int,
    spawn: float,
    **abilities,
) -> BuildingType:
    """Создать здание: UnitType с bounty от cost + BuildingType(cost, spawn)."""
    unit = _unit(
        name,
        role,
        dtype,
        armor,
        hp,
        dmg,
        cd,
        rng,
        spd,
        bounty=kill_bounty(cost),
        **abilities,
    )
    return BuildingType(unit=unit, cost=cost, spawn=spawn)


NECRO_RAISE = _minion("Поднятый", DamageType.SLASH, ArmorType.S, 60, 10, 1.0, 25, 70)

FACTIONS: dict[str, Faction] = {
    "Королевство": Faction(
        "Королевство",
        (
            _building("Мечник", Role.MELEE, DamageType.SLASH, ArmorType.M, 275, 27, 1.0, 25, 70, 40, 8),
            _building("Лучник", Role.RANGED, DamageType.PIERCE, ArmorType.L, 130, 19, 1.1, 180, 65, 40, 8),
            _building(
                "Капеллан",
                Role.SUMMON,
                DamageType.SLASH,
                ArmorType.L,
                225,
                15,
                1.0,
                25,
                60,
                65,
                12,
                minion=_minion("Оруженосец", DamageType.SLASH, ArmorType.S, 80, 12, 1.0, 25, 70),
                every=6,
                maxmin=3,
                total=5,
            ),
            _building(
                "Паладин",
                Role.ULT,
                DamageType.SLASH,
                ArmorType.M,
                695,
                48,
                1.1,
                30,
                55,
                140,
                28,
                aura_heal=6,
            ),
        ),
    ),
    "Орда": Faction(
        "Орда",
        (
            _building("Берсерк", Role.MELEE, DamageType.SLASH, ArmorType.L, 245, 40, 0.9, 25, 85, 40, 8),
            _building("Метатель", Role.RANGED, DamageType.PIERCE, ArmorType.L, 165, 25, 1.25, 150, 70, 35, 8),
            _building(
                "Вожак",
                Role.SUMMON,
                DamageType.SLASH,
                ArmorType.L,
                195,
                14,
                1.0,
                25,
                70,
                65,
                12,
                minion=_minion("Варвар", DamageType.SLASH, ArmorType.S, 80, 13, 1.0, 25, 80),
                every=5.5,
                maxmin=3,
                total=5,
            ),
            _building(
                "Вождь",
                Role.ULT,
                DamageType.SLASH,
                ArmorType.M,
                995,
                86,
                1.2,
                30,
                60,
                140,
                28,
                cleave=0.5,
            ),
        ),
    ),
    "Лес": Faction(
        "Лес",
        (
            _building("Следопыт", Role.MELEE, DamageType.SLASH, ArmorType.L, 245, 28, 1.0, 25, 75, 35, 8),
            _building("Егерь", Role.RANGED, DamageType.PIERCE, ArmorType.L, 70, 16, 1.0, 200, 65, 45, 8),
            _building(
                "Друид",
                Role.SUMMON,
                DamageType.SLASH,
                ArmorType.L,
                205,
                12,
                1.0,
                25,
                65,
                65,
                12,
                minion=_minion("Волк", DamageType.SLASH, ArmorType.S, 70, 14, 0.8, 25, 95),
                every=6,
                maxmin=3,
                total=5,
            ),
            _building(
                "Древень",
                Role.ULT,
                DamageType.SLASH,
                ArmorType.H,
                1140,
                56,
                1.4,
                30,
                40,
                140,
                30,
                regen=12,
            ),
        ),
    ),
    "Некрополь": Faction(
        "Некрополь",
        (
            _building("Скелет", Role.MELEE, DamageType.SLASH, ArmorType.S, 200, 30, 1.0, 25, 70, 25, 6),
            _building(
                "Проклятый лучник",
                Role.RANGED,
                DamageType.PIERCE,
                ArmorType.L,
                125,
                22,
                1.1,
                170,
                65,
                35,
                8,
            ),
            _building(
                "Некромант",
                Role.SUMMON,
                DamageType.MAGIC,
                ArmorType.L,
                105,
                6,
                1.2,
                120,
                60,
                65,
                12,
                minion=_minion("Скелетик", DamageType.SLASH, ArmorType.S, 30, 5, 1.0, 25, 75),
                every=3.5,
                maxmin=3,
                total=6,
            ),
            _building(
                "Рыцарь смерти",
                Role.ULT,
                DamageType.MAGIC,
                ArmorType.M,
                590,
                44,
                1.1,
                30,
                60,
                140,
                28,
                raise_dead=True,
            ),
        ),
    ),
    "Аркана": Faction(
        "Аркана",
        (
            _building("Голем", Role.MELEE, DamageType.SLASH, ArmorType.R, 310, 13, 1.25, 25, 50, 45, 9),
            _building(
                "Маг",
                Role.RANGED,
                DamageType.MAGIC,
                ArmorType.L,
                50,
                14,
                1.15,
                210,
                60,
                50,
                8,
                splash=0.1,
            ),
            _building(
                "Элементалист",
                Role.SUMMON,
                DamageType.MAGIC,
                ArmorType.L,
                80,
                5,
                1.2,
                140,
                60,
                65,
                12,
                minion=_minion("Элементаль", DamageType.MAGIC, ArmorType.S, 45, 6, 1.0, 25, 70),
                every=7,
                maxmin=3,
                total=4,
            ),
            _building(
                "Архимаг",
                Role.ULT,
                DamageType.MAGIC,
                ArmorType.L,
                190,
                36,
                1.3,
                230,
                50,
                140,
                30,
                splash=0.5,
            ),
        ),
    ),
    "Кузня": Faction(
        "Кузня",
        (
            _building("Страж", Role.MELEE, DamageType.PIERCE, ArmorType.H, 375, 19, 1.25, 25, 45, 50, 9),
            _building(
                "Пушка",
                Role.RANGED,
                DamageType.MAGIC,
                ArmorType.M,
                90,
                18,
                1.8,
                200,
                45,
                55,
                10,
                splash=0.3,
            ),
            _building(
                "Инженер",
                Role.SUMMON,
                DamageType.PIERCE,
                ArmorType.M,
                115,
                6,
                1.2,
                120,
                50,
                65,
                12,
                minion=_minion("Дрон", DamageType.SLASH, ArmorType.M, 60, 7, 1.0, 25, 60),
                every=7,
                maxmin=3,
                total=4,
            ),
            _building(
                "Титан",
                Role.ULT,
                DamageType.SLASH,
                ArmorType.H,
                1345,
                69,
                1.5,
                30,
                35,
                150,
                34,
                siege=2.0,
            ),
        ),
    ),
}

FACTION_NAMES: tuple[str, ...] = tuple(FACTIONS.keys())


def all_buildings() -> list[BuildingType]:
    """Все 24 здания всех фракций."""
    result: list[BuildingType] = []
    for faction in FACTIONS.values():
        result.extend(faction.buildings)
    return result
