"""Живые сущности на линии: Entity → Unit / Minion / Castle."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING, Optional

from castlefight.core.abilities import Ability, Siege, build_abilities
from castlefight.data.balance import CASTLE, damage_multiplier
from castlefight.data.enums import ArmorType, DamageType, Role
from castlefight.data.factions import UnitType

if TYPE_CHECKING:
    from castlefight.core.world import World


class Entity:
    """Базовая сущность с HP, бронёй и позицией на линии."""

    def __init__(self, side: int, x: float, hp: float, armor: ArmorType) -> None:
        self.side = side
        self.x = x
        self.hp = hp
        self.max_hp = hp
        self.armor = armor
        self.uid = 0  # номер в мире (выдаёт World.tick)
        self.taken_mult = 1.0  # множитель получаемого урона (зелье «Каменная кожа»)

    @property
    def alive(self) -> bool:
        return self.hp > 0

    def take_damage(
        self,
        raw: float,
        dtype: DamageType,
        *,
        siege: float = 1.0,
        rng: Optional[random.Random] = None,
    ) -> float:
        """Нанести raw-урон с множителем брони (и siege по замку). Вернуть фактический урон."""
        mult = damage_multiplier(dtype, self.armor)
        if self.armor == ArmorType.C:
            mult *= siege
        dealt = raw * mult * self.taken_mult
        if rng is not None:
            dealt *= rng.uniform(0.9, 1.1)
        self.hp -= dealt
        return dealt


class Unit(Entity):
    """Боевой юнит, созданный по UnitType."""

    def __init__(
        self,
        unit_type: UnitType,
        side: int,
        x: float,
        *,
        upgrade_mult: float = 1.0,
        owner: Optional[Unit] = None,
        abilities: Optional[list[Ability]] = None,
    ) -> None:
        hp = unit_type.hp * upgrade_mult
        super().__init__(side, x, hp, unit_type.armor)
        self.unit_type = unit_type
        self.upgrade_mult = upgrade_mult
        self.owner = owner
        self.abilities = abilities if abilities is not None else build_abilities(unit_type)
        self.cd = 0.0
        self.dir = 1 if side == 0 else -1
        self.summon_timer = float(unit_type.every or 0.0)
        self.nmin = 0
        self.made = 0
        self.raised = 0
        self.buff_dmg = 1.0  # множитель урона (зелье «Ярость»)

    @classmethod
    def from_type(
        cls,
        unit_type: UnitType,
        side: int,
        x: float,
        *,
        upgrade_mult: float = 1.0,
        owner: Optional[Unit] = None,
    ) -> Unit:
        if unit_type.role == Role.MINION:
            return Minion(unit_type, side, x, upgrade_mult=upgrade_mult, owner=owner)
        return cls(unit_type, side, x, upgrade_mult=upgrade_mult, owner=owner)

    @property
    def name(self) -> str:
        return self.unit_type.name

    @property
    def role(self) -> Role:
        return self.unit_type.role

    @property
    def dtype(self) -> DamageType:
        return self.unit_type.dtype

    @property
    def dmg(self) -> float:
        return self.unit_type.dmg * self.upgrade_mult * self.buff_dmg

    @property
    def attack_cd(self) -> float:
        return self.unit_type.cd

    @property
    def rng(self) -> float:
        return self.unit_type.rng

    @property
    def spd(self) -> float:
        return self.unit_type.spd

    @property
    def bounty(self) -> int:
        return self.unit_type.bounty

    @property
    def siege(self) -> float:
        for ability in self.abilities:
            if isinstance(ability, Siege):
                return ability.mult
        return 1.0

    def tick_abilities(self, world: World, dt: float) -> None:
        for ability in self.abilities:
            ability.on_tick(self, world, dt)

    def attack(self, target: Entity, world: World, rng: random.Random) -> float:
        """Ударить цель и вызвать on_attack / on_kill."""
        use_rng = None if isinstance(target, Castle) else rng
        dealt = target.take_damage(self.dmg, self.dtype, siege=self.siege, rng=use_rng)
        for ability in self.abilities:
            ability.on_attack(self, target, world, dealt)
        if not target.alive:
            for ability in self.abilities:
                ability.on_kill(self, target, world)
        return dealt


class Minion(Unit):
    """Миньон (призванный юнит)."""


class Castle(Entity):
    """Замок игрока: стреляет по ближайшему врагу в радиусе."""

    def __init__(self, side: int, x: float, hp: float) -> None:
        super().__init__(side, x, hp, ArmorType.C)
        self.cd = 0.0
        self.dmg = float(CASTLE["dmg"])
        self.attack_cd = float(CASTLE["cd"])
        self.rng = float(CASTLE["rng"])
        self.shots = int(CASTLE["shots"])

    def shoot(self, enemies: list[Unit], *, damage_mult: float = 1.0) -> int:
        """Выстрелить по ближайшим живым врагам в радиусе. Вернуть число попаданий."""
        if self.cd > 0:
            return 0
        hits = 0
        for enemy in enemies:
            if not enemy.alive:
                continue
            if abs(enemy.x - self.x) > self.rng:
                break
            enemy.take_damage(self.dmg * damage_mult, DamageType.CASTLE, rng=None)
            hits += 1
            if hits >= self.shots:
                break
        if hits:
            self.cd = self.attack_cd
        return hits
