"""Мир матча: тик, цели, бой, очистка, победа, sudden death."""

from __future__ import annotations

import random
from typing import Optional

from castlefight.core.economy import income_for_tick
from castlefight.core.entity import Unit
from castlefight.core.player import Player
from castlefight.data.balance import INTEREST, LANE, SD_MIN_MULT, SD_RATE, SHOP, STRIKE_CD
from castlefight.data.enums import DamageType, Role


class Bomb:
    """Падающая бомба игрока side в точке x линии."""

    def __init__(self, side: int, x: float, delay: float) -> None:
        self.side = side
        self.x = x
        self.t = delay
        self.delay = delay


class World:
    """Состояние линии и логика одного шага симуляции."""

    def __init__(
        self,
        players: tuple[Player, Player],
        econ: dict,
        rng: random.Random,
        *,
        dt: float = 0.2,
    ) -> None:
        self.players = players
        self.econ = econ
        self.rng = rng
        self.dt = dt
        self.t = 0.0
        self.winner: Optional[int] = None
        self.timeout = False
        self._pending: list[Unit] = []
        # v3
        self.bombs: list[Bomb] = []
        self.pending_events: list[tuple] = []  # события между тиками (покупки в лавке)
        self.events: list[tuple] = []  # события для UI: ("bomb", side, x, killed), ("interest", side, gold), ...
        self._interest_next = INTEREST["every"]
        self.next_uid = 1  # детерминированные номера юнитов (для сетевой игры и команд)

    def units_of(self, side: int) -> list[Unit]:
        return self.players[side].units

    def enemy_units(self, side: int) -> list[Unit]:
        return self.players[1 - side].units

    def queue_spawn(self, unit: Unit) -> None:
        self._pending.append(unit)

    def front_sorted(self, side: int) -> list[Unit]:
        units = self.players[side].units
        if side == 0:
            return sorted(units, key=lambda u: -u.x)
        return sorted(units, key=lambda u: u.x)

    def sudden_death_mult(self) -> float:
        sd_sec = self.econ["sd"] * 60
        return max(SD_MIN_MULT, 1.0 - SD_RATE * max(0.0, (self.t - sd_sec) / 60.0))

    def tick(self, dt: Optional[float] = None) -> None:
        """Один шаг симуляции."""
        if self.winner is not None:
            return
        dt = self.dt if dt is None else dt
        self._pending = []
        self.events = self.pending_events
        self.pending_events = []
        for p in self.players:
            p._sync_slots()

        # экономика
        gain = income_for_tick(self.t, self.econ, dt)
        for p in self.players:
            p.gold += gain
        if self.t + dt >= self._interest_next:
            self._interest_next += INTEREST["every"]
            for p in self.players:
                bonus = min(INTEREST["cap"], p.gold * INTEREST["rate"])
                if bonus >= 1.0:
                    bonus = float(int(bonus))
                    p.gold += bonus
                    self.events.append(("interest", p.side, bonus))

        # бомбы
        if self.bombs:
            self._tick_bombs(dt)

        # спавн из зданий
        for p in self.players:
            spawn_x = p.spawn_x()
            for b in p.buildings:
                unit = b.tick(dt, p, spawn_x, self.rng)
                if unit is not None:
                    p.units.append(unit)
                    if unit.role == Role.ULT:
                        p.ultspawned += 1
                        if p.first_ult is None:
                            p.first_ult = self.t

        self.apply_buffs()
        fronts = [self.front_sorted(0), self.front_sorted(1)]
        sdm = self.sudden_death_mult()

        for i, p in enumerate(self.players):
            enemy = self.players[1 - i]
            ef = fronts[1 - i]
            ecx = enemy.castle.x
            ptr = 0
            ne = len(ef)

            for u in p.units:
                if not u.alive:
                    continue
                u.tick_abilities(self, dt)

                while ptr < ne and not ef[ptr].alive:
                    ptr += 1
                tgt = ef[ptr] if ptr < ne else None

                if u.cd > 0:
                    u.cd -= dt

                if tgt is not None and abs(tgt.x - u.x) <= u.rng:
                    if u.cd <= 0:
                        u.cd += u.attack_cd
                        u.attack(tgt, self, self.rng)
                elif abs(ecx - u.x) <= u.rng + 20:
                    if u.cd <= 0:
                        u.cd += u.attack_cd
                        u.attack(enemy.castle, self, self.rng)
                else:
                    nx = u.x + u.dir * u.spd * dt
                    if tgt is not None:
                        gap = min(u.rng, 25) * 0.5
                        if u.dir > 0:
                            nx = min(nx, tgt.x - gap)
                        else:
                            nx = max(nx, tgt.x + gap)
                    u.x = nx

            # выстрел замка (указатель ptr — как в прототипе, после обхода юнитов)
            p.castle.cd = max(0.0, p.castle.cd - dt)
            if p.castle.cd <= 0:
                while ptr < ne and not ef[ptr].alive:
                    ptr += 1
                p.castle.shoot(ef[ptr:], damage_mult=sdm)

        # очистка и награды
        for i, p in enumerate(self.players):
            enemy = self.players[1 - i]
            alive: list[Unit] = []
            for u in p.units:
                if u.alive:
                    alive.append(u)
                else:
                    enemy.gold += u.bounty
                    enemy.earned += u.bounty
                    enemy.kills += 1
                    if u.owner is not None:
                        u.owner.nmin -= 1
            spawned = [u for u in self._pending if u.side == i]
            p.units = alive + spawned

        for p in self.players:
            for u in p.units:
                if getattr(u, "uid", 0) == 0:
                    u.uid = self.next_uid
                    self.next_uid += 1
        self.t += dt
        self._check_winner()

    def unit_by_uid(self, side: int, uid: int):
        for u in self.players[side].units:
            if getattr(u, "uid", 0) == uid:
                return u
        return None

    # --- v3: баффы, бомбы, удар игрока ---------------------------------------

    def apply_buffs(self) -> None:
        """Раздать юнитам множители зелий своего игрока."""
        for p in self.players:
            dm = p.dmg_mult(self.t)
            tm = p.taken_mult(self.t)
            for u in p.units:
                u.buff_dmg = dm
                u.taken_mult = tm

    def drop_bomb(self, side: int, x: float) -> Bomb:
        b = Bomb(side, max(0.0, min(float(LANE), x)), SHOP["bomb"]["delay"])
        self.bombs.append(b)
        return b

    def _tick_bombs(self, dt: float) -> None:
        spec = SHOP["bomb"]
        left: list[Bomb] = []
        for b in self.bombs:
            b.t -= dt
            if b.t > 1e-9:
                left.append(b)
                continue
            killed = 0
            for u in self.enemy_units(b.side):
                if u.alive and abs(u.x - b.x) <= spec["radius"]:
                    u.take_damage(spec["dmg"], DamageType.CASTLE, rng=None)
                    if not u.alive:
                        killed += 1
            self.events.append(("bomb", b.side, b.x, killed))
        self.bombs = left

    def strike(self, side: int, target: Unit) -> Optional[float]:
        """Удар игрока side кликом по вражескому юниту. None — нельзя (перезарядка/не враг)."""
        if self.winner is not None:
            return None
        p = self.players[side]
        if not p.strike_ready(self.t):
            return None
        if not target.alive or target.side == side or target not in self.players[1 - side].units:
            return None
        dealt = target.take_damage(p.strike_damage, DamageType.CASTLE, rng=None)
        p.next_strike_t = self.t + STRIKE_CD
        p.strikes += 1
        p.strike_dealt += dealt
        self.pending_events.append(("strike", side, target.x, dealt))
        return dealt

    def _check_winner(self) -> None:
        a, b = self.players
        if a.castle.hp <= 0 and b.castle.hp <= 0:
            self.winner = self.rng.randint(0, 1)
        elif b.castle.hp <= 0:
            self.winner = 0
        elif a.castle.hp <= 0:
            self.winner = 1

    def finish_by_timeout(self) -> None:
        """Назначить победителя по HP замков при истечении времени."""
        a, b = self.players
        self.timeout = a.castle.hp > 0 and b.castle.hp > 0
        if a.castle.hp <= 0 and b.castle.hp <= 0:
            self.winner = self.rng.randint(0, 1)
        elif b.castle.hp <= 0:
            self.winner = 0
        elif a.castle.hp <= 0:
            self.winner = 1
        else:
            self.winner = 0 if a.castle.hp > b.castle.hp else 1
