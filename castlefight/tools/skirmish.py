"""Стычка без зданий: N юнитов A против N юнитов B на линии."""

from __future__ import annotations

import random
from typing import Optional

from castlefight.core.entity import Unit
from castlefight.data.balance import LANE
from castlefight.data.enums import Role
from castlefight.data.factions import FACTIONS, UnitType


def _front_sorted(units: list[Unit], side: int) -> list[Unit]:
    # сторона 0: фронт = больший x; сторона 1: фронт = меньший x
    return sorted(units, key=lambda u: -u.x if side == 0 else u.x)


class _SkirmishWorld:
    """Минимальный мир для attack()/сплеша без зданий."""

    def __init__(self, team_a: list[Unit], team_b: list[Unit]) -> None:
        self.team_a = team_a
        self.team_b = team_b
        self._pending: list[Unit] = []

    def units_of(self, side: int) -> list[Unit]:
        return self.team_a if side == 0 else self.team_b

    def enemy_units(self, side: int) -> list[Unit]:
        return self.team_b if side == 0 else self.team_a

    def queue_spawn(self, unit: Unit) -> None:
        self._pending.append(unit)


def _tick_side(
    units: list[Unit],
    enemies: list[Unit],
    enemy_front: list[Unit],
    dt: float,
    rng: random.Random,
    world: _SkirmishWorld,
) -> None:
    p = 0
    ne = len(enemy_front)
    for u in units:
        if not u.alive:
            continue
        while p < ne and not enemy_front[p].alive:
            p += 1
        tgt: Optional[Unit] = enemy_front[p] if p < ne else None

        if u.cd > 0:
            u.cd -= dt

        if tgt is not None and abs(tgt.x - u.x) <= u.rng:
            if u.cd <= 0:
                u.cd += u.attack_cd
                u.attack(tgt, world, rng)
        else:
            nx = u.x + u.dir * u.spd * dt
            if tgt is not None:
                gap = min(u.rng, 25) * 0.5
                if u.dir > 0:
                    nx = min(nx, tgt.x - gap)
                else:
                    nx = max(nx, tgt.x + gap)
            u.x = nx


def run_skirmish(
    *,
    n: int = 5,
    type_a: Optional[UnitType] = None,
    type_b: Optional[UnitType] = None,
    seed: int = 1,
    dt: float = 0.2,
    tmax: float = 600.0,
) -> dict:
    """Бой до смерти одной стороны. По умолчанию: 5 Мечников vs 5 Лучников."""
    if type_a is None:
        type_a = FACTIONS["Королевство"].building_by_role(Role.MELEE).unit
    if type_b is None:
        type_b = FACTIONS["Королевство"].building_by_role(Role.RANGED).unit

    rng = random.Random(seed)
    team_a = [Unit.from_type(type_a, 0, 30.0 + i * 5) for i in range(n)]
    team_b = [Unit.from_type(type_b, 1, LANE - 30.0 - i * 5) for i in range(n)]

    world = _SkirmishWorld(team_a, team_b)
    t = 0.0
    while t < tmax:
        world.team_a = team_a
        world.team_b = team_b
        front_a = _front_sorted(team_a, 0)
        front_b = _front_sorted(team_b, 1)
        _tick_side(team_a, team_b, front_b, dt, rng, world)
        _tick_side(team_b, team_a, front_a, dt, rng, world)
        team_a = [u for u in team_a if u.alive]
        team_b = [u for u in team_b if u.alive]
        t += dt
        if not team_a or not team_b:
            break

    alive_a, alive_b = len(team_a), len(team_b)
    if alive_a > alive_b:
        winner = 0
    elif alive_b > alive_a:
        winner = 1
    else:
        winner = None

    return {
        "t": t,
        "alive_a": alive_a,
        "alive_b": alive_b,
        "winner_side": winner,
        "name_a": type_a.name,
        "name_b": type_b.name,
        "hp_a": sum(u.hp for u in team_a),
        "hp_b": sum(u.hp for u in team_b),
    }


def main() -> None:
    result = run_skirmish(n=5, seed=1)
    print(
        f"{result['name_a']} x5 vs {result['name_b']} x5 | "
        f"t={result['t']:.1f}s | "
        f"живы A={result['alive_a']} (hp={result['hp_a']:.0f}) "
        f"B={result['alive_b']} (hp={result['hp_b']:.0f}) | "
        f"победитель сторона={result['winner_side']}"
    )


if __name__ == "__main__":
    main()
