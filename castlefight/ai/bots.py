"""Боты для headless-матчей."""

from __future__ import annotations

import random
from abc import ABC
from typing import Optional

from castlefight.core.player import Player
from castlefight.data.balance import SWORD_COST, MAX_ULT, MULT, SHOP, SLOTS, UPG_COST, UPG_MAX
from castlefight.data.enums import ArmorType


class Bot(ABC):
    """Базовый бот: план покупки и выбор роли 0..3."""

    name = "base"
    ult_after = 5
    weights = (0.4, 0.35, 0.25)

    def __init__(self, jitter: float = 0.15) -> None:
        self.jitter = jitter
        self.plan: Optional[int] = None
        self.done = False

    def want_ult(self, me: Player, counts: list[int], t: float) -> bool:
        return counts[3] < MAX_ULT and sum(counts[:3]) >= self.ult_after + 3 * counts[3]

    def pick(self, me: Player, en: Player, t: float, rng: random.Random) -> int:
        c = me.counts()
        tot = sum(c[:3]) + 1
        best = 0
        best_v = -1e9
        for k in range(3):
            v = self.weights[k] * tot - c[k] + rng.uniform(-self.jitter, self.jitter) * 2
            if v > best_v:
                best_v = v
                best = k
        return best

    def choose(self, me: Player, en: Player, t: float, rng: random.Random) -> Optional[int]:
        if len(me.buildings) >= SLOTS:
            return None
        c = me.counts()
        if self.plan is None:
            self.plan = 3 if self.want_ult(me, c, t) else self.pick(me, en, t, rng)
        k = self.plan
        if me.gold >= me.defs[k].cost:
            self.plan = None
            return k
        return None


class MixedBot(Bot):
    name = "mixed"


class RushBot(Bot):
    name = "rush"
    weights = (0.55, 0.35, 0.10)
    ult_after = 9


class GreedyBot(Bot):
    name = "greedy"
    ult_after = 2
    weights = (0.35, 0.35, 0.30)


class SwarmBot(Bot):
    name = "swarm"
    weights = (0.3, 0.25, 0.45)
    ult_after = 6


class CounterBot(Bot):
    name = "counter"

    def pick(self, me: Player, en: Player, t: float, rng: random.Random) -> int:
        mix = {a: 0.0 for a in (ArmorType.L, ArmorType.M, ArmorType.H, ArmorType.S, ArmorType.R)}
        for b in en.buildings:
            d = b.building_type.unit
            w = d.hp / b.building_type.spawn
            mix[d.armor] += w
            if d.minion is not None and d.every:
                m = d.minion
                mix[m.armor] += m.hp / d.every * 0.7
        tot = sum(mix.values()) or 1.0
        c = me.counts()
        n = sum(c[:3]) + 1
        best = 0
        best_v = -1e9
        for k in range(3):
            d = me.defs[k].unit
            if sum(mix.values()) > 0:
                eff = sum(mix[a] / tot * MULT[d.dtype][a] for a in mix)
            else:
                eff = 1.0
            if d.minion is not None:
                if sum(mix.values()) > 0:
                    meff = sum(mix[a] / tot * MULT[d.minion.dtype][a] for a in mix)
                else:
                    meff = 1.0
                eff = 0.5 * eff + 0.5 * meff
            share = c[k] / n
            v = eff - 1.2 * max(0.0, share - 0.5)
            if k == 0 and c[0] < max(1, n * 0.3):
                v += 0.4
            v += rng.uniform(-self.jitter, self.jitter)
            if v > best_v:
                best_v = v
                best = k
        return best


class MonoBot(Bot):
    def __init__(self, k: int, jitter: float = 0.0) -> None:
        super().__init__(jitter)
        self.k = k
        self.name = f"mono{k}"

    def want_ult(self, me: Player, counts: list[int], t: float) -> bool:
        return self.k == 3

    def pick(self, me: Player, en: Player, t: float, rng: random.Random) -> int:
        return self.k

    def choose(self, me: Player, en: Player, t: float, rng: random.Random) -> Optional[int]:
        if self.k == 3 and me.counts()[3] >= MAX_ULT:
            self.done = True
            return None
        return super().choose(me, en, t, rng)


class RandomBot(Bot):
    name = "random"

    def pick(self, me: Player, en: Player, t: float, rng: random.Random) -> int:
        return rng.randrange(3)


POOL: list[type[Bot]] = [MixedBot, CounterBot, RushBot, GreedyBot, SwarmBot]


def best_bomb_x(enemy_units, radius: float) -> tuple[Optional[float], int]:
    """Точка, где бомба накроет больше всего врагов (перебор по позициям юнитов)."""
    alive = [u.x for u in enemy_units if u.alive]
    best_x, best_n = None, 0
    for x in alive:
        n = sum(1 for y in alive if abs(y - x) <= radius)
        if n > best_n:
            best_x, best_n = x, n
    return best_x, best_n


def bot_shop(me: Player, en: Player, world) -> None:
    """Простая и честная логика лавки для бота (без случайности).

    - ремонт замка, если HP < 45%;
    - бомба, когда у своего замка (на своей половине) скопилось >= 6 врагов в радиусе
      и золота хватает (бот копит золото, только когда все места заняты);
    - зелья «Ярость» / «Каменная кожа» — только из лишнего золота сверх запаса на апгрейд.
    Меч качает из лишнего золота (до 3 уровня) — он кликает как человек (BotClicker).
    """
    from castlefight.core import shop

    c = me.castle
    if c.hp < 0.45 * c.max_hp and shop.block_reason(me, world, "repair") is None:
        shop.buy(me, world, "repair")
    lane_mid = (me.castle.x + en.castle.x) / 2
    bx, n = best_bomb_x(en.units, SHOP["bomb"]["radius"] * 0.8)
    if bx is not None and n >= 6 and abs(bx - me.castle.x) <= abs(lane_mid - me.castle.x):
        if shop.block_reason(me, world, "bomb") is None:
            shop.buy(me, world, "bomb", x=bx)
            return
    if me.sword == 0 and me.gold >= SWORD_COST[0] + 100 and world.t > 60:
        shop.buy(me, world, "sword")  # первый меч — рано и дёшево: бот ведь кликает
        return
    if len(me.buildings) < SLOTS:
        return
    reserve = UPG_COST[me.lvl] if me.lvl < UPG_MAX else 0
    if me.gold - reserve < 60:
        return
    # меч героя: бот тоже кликает, качает меч из лишнего золота
    sc = me.sword_cost()
    if sc is not None and me.gold - reserve >= sc and me.sword < 3:
        shop.buy(me, world, "sword")
        return
    alive_me = sum(1 for u in me.units if u.alive)
    alive_en = sum(1 for u in en.units if u.alive)
    if alive_me >= 10 and shop.block_reason(me, world, "rage") is None:
        shop.buy(me, world, "rage")
    elif alive_en >= 10 and shop.block_reason(me, world, "stone") is None:
        shop.buy(me, world, "stone")


class BotClicker:
    """Бот кликает по вражеским юнитам как человек: ~1–1.5 клика/с со случайными паузами,
    по тем же правилам (перезарядка 0.4 с, урон по уровню меча). Свой генератор случайных
    чисел — не влияет на rng матча."""

    def __init__(self, side: int, seed: int) -> None:
        self.side = side
        self.rng = random.Random(seed * 7919 + side * 104729 + 1)
        self.next_t = 2.0 + self.rng.uniform(0, 2)

    def step(self, world) -> None:
        if world.t < self.next_t or world.winner is not None:
            return
        me = world.players[self.side]
        # «рука» отдыхает: иногда пауза 1–3 с
        if self.rng.random() < 0.06:
            self.next_t = world.t + self.rng.uniform(1.0, 3.0)
            return
        self.next_t = world.t + self.rng.uniform(0.55, 1.05)
        enemies = [u for u in world.players[1 - self.side].units if u.alive]
        if not enemies:
            return
        # чаще всего — самый опасный (ближе к своему замку), иногда промах по случайному
        enemies.sort(key=lambda u: abs(u.x - me.castle.x))
        tgt = enemies[0] if self.rng.random() < 0.75 else self.rng.choice(enemies[:5])
        world.strike(self.side, tgt)
