"""Способности юнитов: композиция через on_tick / on_attack / on_kill."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from castlefight.data.enums import ArmorType
from castlefight.data.factions import NECRO_RAISE, UnitType

if TYPE_CHECKING:
    from castlefight.core.entity import Castle, Entity, Unit
    from castlefight.core.world import World


class Ability:
    """Базовый класс способности."""

    def on_tick(self, unit: Unit, world: World, dt: float) -> None:
        return None

    def on_attack(self, unit: Unit, target: Entity, world: World, dealt: float) -> None:
        return None

    def on_kill(self, unit: Unit, victim: Entity, world: World) -> None:
        return None


class Summon(Ability):
    """Периодический призыв миньонов."""

    def __init__(self, minion: UnitType, every: float, maxmin: int, total: int) -> None:
        self.minion = minion
        self.every = every
        self.maxmin = maxmin
        self.total = total

    def on_tick(self, unit: Unit, world: World, dt: float) -> None:
        unit.summon_timer -= dt
        if unit.summon_timer > 0:
            return
        unit.summon_timer += self.every
        if unit.nmin < self.maxmin and unit.made < self.total:
            from castlefight.core.entity import Unit as UnitCls

            unit.nmin += 1
            unit.made += 1
            world.queue_spawn(
                UnitCls.from_type(
                    self.minion,
                    unit.side,
                    unit.x,
                    upgrade_mult=unit.upgrade_mult,
                    owner=unit,
                )
            )


class AuraHeal(Ability):
    """Лечение союзников в радиусе 150."""

    def __init__(self, rate: float) -> None:
        self.rate = rate

    def on_tick(self, unit: Unit, world: World, dt: float) -> None:
        heal = self.rate * dt
        for ally in world.units_of(unit.side):
            if ally.alive and ally.hp < ally.max_hp and abs(ally.x - unit.x) <= 150:
                ally.hp = min(ally.max_hp, ally.hp + heal)


class Regen(Ability):
    """Самолечение."""

    def __init__(self, rate: float) -> None:
        self.rate = rate

    def on_tick(self, unit: Unit, world: World, dt: float) -> None:
        if unit.hp < unit.max_hp:
            unit.hp = min(unit.max_hp, unit.hp + self.rate * dt)


class Splash(Ability):
    """Урон по соседям цели в радиусе 50 (доля от dmg)."""

    def __init__(self, fraction: float) -> None:
        self.fraction = fraction

    def on_attack(self, unit: Unit, target: Entity, world: World, dealt: float) -> None:
        from castlefight.core.entity import Castle

        if isinstance(target, Castle):
            return
        raw = unit.dmg * self.fraction
        for other in world.enemy_units(unit.side):
            if other is target or not other.alive:
                continue
            if abs(other.x - target.x) <= 50:
                other.take_damage(raw, unit.dtype, rng=None)


class Cleave(Splash):
    """Клив — тот же сплеш по соседям."""


class RaiseDead(Ability):
    """Поднятие убитого врага как миньона (до 6 за жизнь)."""

    def on_kill(self, unit: Unit, victim: Entity, world: World) -> None:
        from castlefight.core.entity import Castle, Unit as UnitCls

        if isinstance(victim, Castle):
            return
        if unit.raised >= 6:
            return
        unit.raised += 1
        world.queue_spawn(
            UnitCls.from_type(
                NECRO_RAISE,
                unit.side,
                victim.x,
                upgrade_mult=unit.upgrade_mult,
            )
        )


class Siege(Ability):
    """Множитель урона по замку."""

    def __init__(self, mult: float) -> None:
        self.mult = mult


def build_abilities(unit_type: UnitType) -> list[Ability]:
    """Собрать список способностей по полям шаблона."""
    result: list[Ability] = []
    if unit_type.minion is not None:
        result.append(
            Summon(
                unit_type.minion,
                every=float(unit_type.every or 0),
                maxmin=int(unit_type.maxmin or 0),
                total=int(unit_type.total or 0),
            )
        )
    if unit_type.aura_heal is not None:
        result.append(AuraHeal(unit_type.aura_heal))
    if unit_type.regen is not None:
        result.append(Regen(unit_type.regen))
    if unit_type.splash is not None:
        result.append(Splash(unit_type.splash))
    if unit_type.cleave is not None:
        result.append(Cleave(unit_type.cleave))
    if unit_type.raise_dead:
        result.append(RaiseDead())
    if unit_type.siege is not None:
        result.append(Siege(unit_type.siege))
    return result
