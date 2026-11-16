"""Матч бот vs бот в консоли."""

from __future__ import annotations

import argparse

from castlefight.ai.bots import CounterBot, GreedyBot, MixedBot, RushBot, SwarmBot
from castlefight.core.game import Game
from castlefight.data.factions import FACTION_NAMES

BOTS = {
    "mixed": MixedBot,
    "counter": CounterBot,
    "rush": RushBot,
    "greedy": GreedyBot,
    "swarm": SwarmBot,
}


def main() -> None:
    p = argparse.ArgumentParser(description="Castle Fight headless")
    p.add_argument("faction_a", choices=FACTION_NAMES)
    p.add_argument("faction_b", choices=FACTION_NAMES)
    p.add_argument("--bot-a", default="mixed", choices=BOTS)
    p.add_argument("--bot-b", default="counter", choices=BOTS)
    p.add_argument("--mode", default="normal", choices=("normal", "turbo"))
    p.add_argument("--seed", type=int, default=1)
    args = p.parse_args()

    def on_minute(world):
        a, b = world.players
        print(
            f"t={world.t/60:5.1f}m  "
            f"HP {a.castle.hp:7.0f}/{b.castle.hp:7.0f}  "
            f"gold {a.gold:5.0f}/{b.gold:5.0f}  "
            f"units {len(a.units):2d}/{len(b.units):2d}  "
            f"blds {a.counts()}/{b.counts()}"
        )

    game = Game(
        args.faction_a,
        args.faction_b,
        BOTS[args.bot_a](),
        BOTS[args.bot_b](),
        mode=args.mode,
        seed=args.seed,
        on_minute=on_minute,
    )
    result = game.run()
    print(
        f"winner={result['winner']} t={result['t']/60:.1f}m "
        f"timeout={result['timeout']} chp={result['chp'][0]:.0f}/{result['chp'][1]:.0f}"
    )


if __name__ == "__main__":
    main()
