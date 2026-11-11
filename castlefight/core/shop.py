"""Лавка: зелья, ремонт замка, бомба, меч героя. Без pygame — только правила."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from castlefight.data.balance import LANE, SHOP

if TYPE_CHECKING:
    from castlefight.core.player import Player
    from castlefight.core.world import World

ITEMS = ("rage", "stone", "repair", "bomb", "sword")


def cost(player: "Player", item: str) -> Optional[int]:
    if item == "sword":
        return player.sword_cost()
    return SHOP[item]["cost"]


def cooldown_left(player: "Player", world: "World", item: str) -> float:
    return max(0.0, player.cd_until.get(item, 0.0) - world.t)


def block_reason(player: "Player", world: "World", item: str) -> Optional[str]:
    """Почему нельзя купить предмет сейчас (None — можно)."""
    if item not in ITEMS:
        return "нет такого предмета"
    if world.winner is not None:
        return "матч окончен"
    c = cost(player, item)
    if c is None:
        return "максимальный уровень"
    if item == "repair":
        if player.repairs >= SHOP["repair"]["uses"]:
            return "ремонт закончился"
        if player.castle.hp >= player.castle.max_hp:
            return "замок цел"
    if cooldown_left(player, world, item) > 0:
        return f"перезарядка {cooldown_left(player, world, item):.0f} с"
    if player.gold < c:
        return "не хватает золота"
    return None


def buy(player: "Player", world: "World", item: str, x: Optional[float] = None) -> bool:
    """Купить и сразу применить предмет. Для бомбы нужна точка x на линии."""
    if block_reason(player, world, item) is not None:
        return False
    if item == "bomb":
        if x is None or not (0.0 <= x <= LANE):
            return False
    c = cost(player, item)
    assert c is not None
    player.gold -= c
    if item == "sword":
        player.gold += c  # upgrade_sword сам спишет
        return player.upgrade_sword()
    player.shop_spent += c
    spec = SHOP[item]
    player.cd_until[item] = world.t + spec["cd"]
    if item in ("rage", "stone"):
        player.buff_until[item] = world.t + spec["dur"]
        world.apply_buffs()
    elif item == "repair":
        castle = player.castle
        castle.hp = min(castle.max_hp, castle.hp + castle.max_hp * spec["frac"])
        player.repairs += 1
    elif item == "bomb":
        world.drop_bomb(player.side, float(x))
    world.pending_events.append(("shop", player.side, item))
    return True
