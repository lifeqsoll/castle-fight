"""Проверка баланса v3: удар кликом, меч, лавка, бомба.

Сценарии (зеркальные пары: одинаковые фракция и бот у обеих сторон, стороны меняются):
  shop      — бот A пользуется лавкой (ремонт/зелья/бомба), бот B — нет;
  click100  — сторона A «кликает» с максимальной частотой и качает меч;
  click50   — то же, но с половинной частотой (реалистичный игрок);
  click100ns — клики на максимуме, но без меча.
Печатает винрейт стороны A и среднюю длину матча.

    python -m castlefight.tools.balance_v3 [normal|turbo] [n]
"""

from __future__ import annotations

import statistics as st
import sys
from multiprocessing import Pool

from castlefight.ai.bots import POOL
from castlefight.core.game import Game
from castlefight.data.balance import SLOTS, STRIKE_CD
from castlefight.data.factions import FACTION_NAMES

CL = list(FACTION_NAMES)


class ClickerGame(Game):
    """Матч, где сторона `clicker` ещё и бьёт кликом по ближайшему к своему замку врагу."""

    def __init__(self, *a, clicker: int = 0, rate: float = 1.0, sword: bool = True, **kw):
        super().__init__(*a, **kw)
        self.clicker = clicker
        self.period = STRIKE_CD / rate
        self.sword = sword
        self._next_click = 0.0

    def step(self) -> bool:
        w = self.world
        if w.winner is None:
            me = self.players[self.clicker]
            if self.sword and me.sword_cost() is not None:
                c = me.sword_cost()
                if len(me.buildings) >= SLOTS and me.gold >= c:  # меч — когда все места заняты
                    me.upgrade_sword()
            if w.t >= self._next_click:
                enemies = [u for u in w.enemy_units(self.clicker) if u.alive]
                if enemies:
                    tgt = min(enemies, key=lambda u: abs(u.x - me.castle.x))
                    if w.strike(self.clicker, tgt) is not None:
                        self._next_click = w.t + self.period
        return super().step()


def _job(args):
    scen, fac, bi, side, mode, seed = args
    bot = POOL[bi]
    kw = dict(mode=mode, seed=seed)
    if scen == "shop":
        shop = (True, False) if side == 0 else (False, True)
        g = Game(fac, fac, bot(), bot(), bot_shop=shop, **kw)
    else:
        rate = 0.5 if scen == "click50" else 1.0
        g = ClickerGame(fac, fac, bot(), bot(), clicker=side, rate=rate, sword=scen != "click100ns", **kw)
    r = g.run()
    p = g.players[side]
    return scen, fac, r["winner"] == side, r["t"], p.strike_dealt, p.sword, p.shop_spent


def run(n: int = 4, mode: str = "normal", procs: int = 8):
    scens = ["shop", "click50", "click100", "click100ns"]
    jobs = []
    s = 1000
    for scen in scens:
        for fac in CL:
            for bi in range(len(POOL)):
                for i in range(n):
                    s += 1
                    jobs.append((scen, fac, bi, i % 2, mode, s))
    with Pool(procs) as pool:
        res = pool.map(_job, jobs, chunksize=4)
    print(f"режим {mode}, матчей на сценарий: {len(jobs) // len(scens)}")
    for scen in scens:
        rows = [r for r in res if r[0] == scen]
        wr = 100 * sum(r[2] for r in rows) / len(rows)
        t = st.mean(r[3] for r in rows) / 60
        dealt = st.mean(r[4] for r in rows)
        sw = st.mean(r[5] for r in rows)
        spent = st.mean(r[6] for r in rows)
        per = {f: 100 * sum(r[2] for r in rows if r[1] == f) / max(1, sum(1 for r in rows if r[1] == f)) for f in CL}
        print(
            f"{scen:11s} винрейт A {wr:5.1f}%  матч {t:4.1f} мин  урон кликами {dealt:6.0f}  меч ур.{sw:.1f}  лавка {spent:4.0f} з  "
            + " ".join(f"{f[:4]}:{v:.0f}" for f, v in per.items())
        )
    return res


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "normal"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    run(n, mode)
