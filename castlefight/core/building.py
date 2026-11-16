"""Здание на линии: таймер и спавн юнитов."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from castlefight.data.enums import Role
from castlefight.data.factions import BuildingType

if TYPE_CHECKING:
    from castlefight.core.entity import Unit
    from castlefight.core.player import Player


class Building:
    """Купленное здание со своим таймером спавна."""

    def __init__(self, building_type: BuildingType, timer: float, slot: int | None = None) -> None:
        self.building_type = building_type
        self.timer = timer
        self.period = timer  # длина текущего цикла (для полоски прогресса в UI)
        self.slot = slot  # ячейка в зоне застройки игрока (0..SLOTS-1)
        self.spawned = 0  # сколько юнитов уже выпустило здание
        self.spawn_mult = 1.0  # «Соседство»: <1, если рядом такое же здание

    @property
    def progress(self) -> float:
        """Доля готовности следующего юнита 0..1 (только для отображения)."""
        if self.period <= 0:
            return 1.0
        return max(0.0, min(1.0, 1.0 - self.timer / self.period))

    @property
    def role(self) -> Role:
        return self.building_type.role

    @property
    def cost(self) -> int:
        return self.building_type.cost

    def tick(self, dt: float, player: Player, spawn_x: float, rng: random.Random) -> Unit | None:
        """Уменьшить таймер; при готовности создать юнита и перезапустить таймер."""
        self.timer -= dt
        if self.timer > 0:
            return None
        bt = self.building_type
        step = bt.spawn * self.spawn_mult * rng.uniform(0.95, 1.05)
        self.timer += step
        self.period = step
        self.spawned += 1
        from castlefight.core.entity import Unit

        return Unit.from_type(
            bt.unit,
            player.side,
            spawn_x,
            upgrade_mult=player.upgrade_mult,
        )
