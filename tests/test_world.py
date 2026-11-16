"""Этап 3–4: World / Player / Economy с фиксированными зданиями."""

import random

from castlefight.core.building import Building
from castlefight.core.game import Game
from castlefight.core.player import Player
from castlefight.core.world import World
from castlefight.data.balance import ECON
from castlefight.data.enums import Role
from castlefight.data.factions import FACTIONS


def _preset_player(faction_name: str, side: int, roles: list[Role], mode: str = "normal") -> Player:
    econ = ECON[mode]
    player = Player(FACTIONS[faction_name], side, econ)
    rng = random.Random(0)
    for role in roles:
        bt = player.faction.building_by_role(role)
        timer = bt.spawn * 0.5 * rng.uniform(0.8, 1.2)
        player.buildings.append(Building(bt, timer))
        player.gold = max(0.0, player.gold - bt.cost)
    return player


def test_world_match_finishes_with_preset_buildings():
    a = _preset_player(
        "Королевство",
        0,
        [Role.MELEE, Role.MELEE, Role.RANGED, Role.SUMMON],
    )
    b = _preset_player(
        "Орда",
        1,
        [Role.MELEE, Role.RANGED, Role.RANGED, Role.SUMMON],
    )
    world = World((a, b), ECON["normal"], random.Random(42))
    while world.winner is None and world.t < 45 * 60:
        world.tick()
    if world.winner is None:
        world.finish_by_timeout()
    assert world.winner in (0, 1)
    assert world.t > 60


def test_player_buy_limits():
    p = Player(FACTIONS["Кузня"], 0, ECON["normal"])
    rng = random.Random(1)
    assert p.buy(0, rng)  # melee
    assert p.ult_count() == 0
    # не хватает на ult сразу после старта с 60 золота и покупки за 50
    p.gold = 200
    assert p.buy(3, rng)
    assert p.ult_count() == 1
    p.gold = 200
    assert p.buy(3, rng)
    assert p.ult_count() == 2
    p.gold = 500
    assert not p.buy(3, rng)  # MAX_ULT


def test_headless_bots_short_match():
    game = Game("Лес", "Аркана", mode="turbo", seed=7)
    from castlefight.ai.bots import MixedBot, RushBot

    game.bot_a = MixedBot()
    game.bot_b = RushBot()
    result = game.run()
    assert result["winner"] in (0, 1)
    assert result["t"] > 30
