"""Игровой цикл: режим, игроки, боты, события."""

from __future__ import annotations

import random
from typing import Any, Callable, Optional

from castlefight.ai.bots import Bot, BotClicker, bot_shop
from castlefight.core.player import Player
from castlefight.core.world import World
from castlefight.data.balance import ECON, SLOTS, UPG_MAX
from castlefight.data.factions import FACTIONS, Faction


class Game:
    """Матч двух игроков с фиксированным шагом dt."""

    def __init__(
        self,
        faction_a: str | Faction,
        faction_b: str | Faction,
        bot_a: Optional[Bot] = None,
        bot_b: Optional[Bot] = None,
        *,
        mode: str = "normal",
        seed: int = 0,
        dt: float = 0.2,
        tmax: float = 45 * 60,
        on_minute: Optional[Callable[[World], None]] = None,
        bot_shop: bool | tuple[bool, bool] = True,
        bot_click: bool | tuple[bool, bool] = True,
    ) -> None:
        if mode not in ECON:
            raise ValueError(f"Неизвестный режим: {mode}")
        self.mode = mode
        self.econ = ECON[mode]
        self.dt = dt
        self.tmax = tmax
        self.rng = random.Random(seed)
        self.bot_a = bot_a
        self.bot_b = bot_b
        self.on_minute = on_minute
        self.use_bot_shop = bot_shop if isinstance(bot_shop, tuple) else (bot_shop, bot_shop)
        bc = bot_click if isinstance(bot_click, tuple) else (bot_click, bot_click)
        self.clickers = [BotClicker(i, seed) if bc[i] else None for i in range(2)]

        fa = FACTIONS[faction_a] if isinstance(faction_a, str) else faction_a
        fb = FACTIONS[faction_b] if isinstance(faction_b, str) else faction_b
        self.players = (
            Player(fa, 0, self.econ),
            Player(fb, 1, self.econ),
        )
        self.world = World(self.players, self.econ, self.rng, dt=dt)
        for p in self.players:
            p._world_ref = self.world  # для MLBot
        self._decide_at = 0.0
        self._last_minute = -1

    def _bot_step(self) -> None:
        bots = (self.bot_a, self.bot_b)
        for i, bot in enumerate(bots):
            if bot is None:
                continue
            me = self.players[i]
            en = self.players[1 - i]
            # апгрейд, если слоты полны или бот «done»
            if self.use_bot_shop[i]:
                bot_shop(me, en, self.world)
            if (len(me.buildings) >= SLOTS or getattr(bot, "done", False)) and me.lvl < UPG_MAX:
                me.try_upgrade()
                continue
            for _ in range(3):
                k = bot.choose(me, en, self.world.t, self.rng)
                if k is None:
                    break
                if not me.buy(k, self.rng, slot=me.best_slot(k)):
                    break

    def step(self) -> bool:
        """Один тик. Вернуть True, если матч ещё идёт."""
        w = self.world
        if w.winner is not None:
            return False
        if w.t >= self._decide_at:
            self._decide_at += 1.0
            self._bot_step()
        for i, bot in enumerate((self.bot_a, self.bot_b)):
            if bot is not None and self.clickers[i] is not None:
                self.clickers[i].step(w)
        w.tick()
        minute = int(w.t // 60)
        if self.on_minute and minute != self._last_minute and minute > 0:
            self._last_minute = minute
            self.on_minute(w)
        if w.winner is not None:
            return False
        if w.t >= self.tmax:
            w.finish_by_timeout()
            return False
        return True

    def run(self) -> dict[str, Any]:
        """Прогнать матч до конца и вернуть результат."""
        while self.step():
            pass
        a, b = self.players
        w = self.world
        return {
            "winner": w.winner,
            "t": w.t,
            "timeout": w.timeout,
            "chp": (a.castle.hp, b.castle.hp),
            "fu": (a.first_ult, b.first_ult),
            "earned": (a.earned, b.earned),
            "lvl": (a.lvl, b.lvl),
            "blds": (a.counts(), b.counts()),
        }


def simulate(
    cls_a: str,
    cls_b: str,
    bot_a: Bot,
    bot_b: Bot,
    *,
    mode: str = "normal",
    seed: int = 0,
    dt: float = 0.2,
    tmax: float = 45 * 60,
) -> dict[str, Any]:
    """API как у balance_sim.sim.simulate."""
    return Game(cls_a, cls_b, bot_a, bot_b, mode=mode, seed=seed, dt=dt, tmax=tmax).run()
