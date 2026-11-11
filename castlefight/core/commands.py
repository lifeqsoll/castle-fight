"""Команды игрока — одинаковые для локальной и сетевой игры (JSON-совместимые dict).

{"c": "buy", "i": 0..3, "s": slot}     — построить здание
{"c": "move", "a": src, "b": dst}      — переставить
{"c": "sell", "s": slot}               — продать
{"c": "upg"}                           — апгрейд армии
{"c": "shop", "item": "rage"|..., "x": позиция бомбы на линии или null}
{"c": "strike", "u": uid}              — удар героя по вражескому юниту
"""

from __future__ import annotations

from typing import Any

from castlefight.core import shop


def apply(game, side: int, cmd: dict) -> Any:
    """Применить команду стороны side. Возвращает результат (False/None — не вышло)."""
    p = game.players[side]
    w = game.world
    c = cmd.get("c")
    try:
        if c == "buy":
            return p.buy(int(cmd["i"]), game.rng, slot=int(cmd["s"]))
        if c == "move":
            return p.move_building(int(cmd["a"]), int(cmd["b"]))
        if c == "sell":
            return p.sell(int(cmd["s"]))
        if c == "upg":
            return p.try_upgrade()
        if c == "shop":
            x = cmd.get("x")
            return shop.buy(p, w, str(cmd["item"]), x=None if x is None else float(x))
        if c == "strike":
            u = w.unit_by_uid(1 - side, int(cmd["u"]))
            return None if u is None else w.strike(side, u)
    except (KeyError, ValueError, TypeError):
        return None
    return None
