"""v3: удар кликом и меч, лавка (зелья, ремонт, бомба), продажа, «Соседство», «Казна»."""

import random

import pytest

from castlefight.ai.bots import POOL, best_bomb_x, bot_shop
from castlefight.core import shop
from castlefight.core.entity import Unit
from castlefight.core.game import Game
from castlefight.data.balance import (
    ADJ_SPAWN_MULT,
    ECON,
    INTEREST,
    SELL_REFUND,
    SHOP,
    STRIKE_CD,
    STRIKE_DMG,
    SWORD_COST,
)


def _game(mode="normal", seed=1):
    g = Game("Королевство", "Орда", mode=mode, seed=seed)
    return g, g.world, g.players[0], g.players[1]


def _spawn(player, k=0, x=None):
    bt = player.defs[k]
    u = Unit(bt.unit, player.side, player.spawn_x() if x is None else x)
    player.units.append(u)
    return u


# --- удар кликом и меч -------------------------------------------------------


def test_strike_damage_and_cooldown():
    g, w, a, b = _game()
    u = _spawn(b, 0)
    hp0 = u.hp
    dealt = w.strike(0, u)
    assert dealt == pytest.approx(STRIKE_DMG[0])
    assert u.hp == pytest.approx(hp0 - STRIKE_DMG[0])
    # сразу второй удар нельзя — кап частоты
    assert w.strike(0, u) is None
    for _ in range(int(STRIKE_CD / w.dt) + 1):
        w.tick()
    assert w.strike(0, u) is not None
    assert a.strikes == 2


def test_strike_only_enemies():
    g, w, a, b = _game()
    own = _spawn(a, 0)
    assert w.strike(0, own) is None
    assert own.hp == own.max_hp


def test_strike_kill_gives_bounty_and_kill():
    g, w, a, b = _game()
    u = _spawn(b, 0)
    u.hp = 1.0
    gold0 = a.gold
    w.strike(0, u)
    assert not u.alive
    w.tick()
    assert u not in b.units
    assert a.kills == 1
    assert a.gold >= gold0 + u.bounty


def test_sword_levels_cost_rise_and_cap():
    g, w, a, b = _game()
    assert list(SWORD_COST) == sorted(SWORD_COST)
    assert list(STRIKE_DMG) == sorted(STRIKE_DMG)
    a.gold = 10_000
    for lvl, cost in enumerate(SWORD_COST):
        assert a.strike_damage == STRIKE_DMG[lvl]
        g0 = a.gold
        assert shop.buy(a, w, "sword")
        assert a.gold == g0 - cost
    assert a.sword == len(STRIKE_DMG) - 1
    assert shop.block_reason(a, w, "sword") == "максимальный уровень"
    assert not shop.buy(a, w, "sword")


def test_sword_needs_gold():
    g, w, a, b = _game()
    a.gold = SWORD_COST[0] - 1
    assert shop.block_reason(a, w, "sword") == "не хватает золота"
    assert not shop.buy(a, w, "sword")
    assert a.sword == 0


# --- лавка ----------------------------------------------------------------------


def test_rage_potion_buffs_damage_then_expires():
    g, w, a, b = _game()
    u = _spawn(a, 0)
    base = u.dmg
    a.gold = 1000
    assert shop.buy(a, w, "rage")
    assert u.dmg == pytest.approx(base * SHOP["rage"]["mult"])
    # кулдаун
    assert shop.block_reason(a, w, "rage").startswith("перезарядка")
    while w.t < SHOP["rage"]["dur"] + 0.5:
        w.tick()
    assert not a.buff_active("rage", w.t)
    if u.alive:
        assert u.dmg == pytest.approx(base)


def test_stone_potion_reduces_damage_taken():
    g, w, a, b = _game()
    u = _spawn(a, 0)
    a.gold = 1000
    shop.buy(a, w, "stone")
    hp0 = u.hp
    from castlefight.data.enums import DamageType

    dealt = u.take_damage(100.0, DamageType.CASTLE, rng=None)
    assert dealt == pytest.approx(100.0 * SHOP["stone"]["mult"])
    assert u.hp == pytest.approx(hp0 - dealt)


def test_repair_heals_capped_and_limited():
    g, w, a, b = _game()
    a.gold = 10_000
    assert shop.block_reason(a, w, "repair") == "замок цел"
    c = a.castle
    c.hp = c.max_hp * 0.5
    assert shop.buy(a, w, "repair")
    assert c.hp == pytest.approx(c.max_hp * (0.5 + SHOP["repair"]["frac"]))
    for i in range(SHOP["repair"]["uses"] - 1):
        a.cd_until["repair"] = 0
        assert shop.buy(a, w, "repair")
    a.cd_until["repair"] = 0
    assert shop.block_reason(a, w, "repair") == "ремонт закончился"
    c.hp = c.max_hp - 1
    a.repairs = 0
    shop.buy(a, w, "repair")
    assert c.hp == c.max_hp


def test_bomb_falls_after_delay_hits_only_enemies_in_radius():
    g, w, a, b = _game()
    x = 1000.0
    r = SHOP["bomb"]["radius"]
    near = _spawn(b, 0, x=x + r * 0.5)
    far = _spawn(b, 0, x=x + r * 1.5)
    friend = _spawn(a, 0, x=x)
    a.gold = 1000
    gold0 = a.gold
    assert shop.buy(a, w, "bomb", x=x)
    assert a.gold == gold0 - SHOP["bomb"]["cost"]
    assert len(w.bombs) == 1
    # бомбы отдельно от боя: тикаем только их
    w._tick_bombs(w.dt)
    assert near.hp == near.max_hp and len(w.bombs) == 1  # ещё падает
    t = w.dt
    while w.bombs:
        w._tick_bombs(w.dt)
        t += w.dt
    assert t == pytest.approx(SHOP["bomb"]["delay"], abs=w.dt)
    hit = [e for e in w.events if e[0] == "bomb"]
    assert hit and hit[0][1] == 0 and hit[0][3] == 1
    assert not near.alive  # 500 урона убивает мечника
    assert far.hp == far.max_hp
    assert friend.hp == friend.max_hp


def test_bomb_cooldown_and_needs_point():
    g, w, a, b = _game()
    a.gold = 10_000
    assert not shop.buy(a, w, "bomb")  # без точки
    assert not shop.buy(a, w, "bomb", x=-5)
    assert a.gold == 10_000
    assert shop.buy(a, w, "bomb", x=500)
    assert not shop.buy(a, w, "bomb", x=500)
    assert shop.cooldown_left(a, w, "bomb") == pytest.approx(SHOP["bomb"]["cd"])


def test_bomb_cost_vs_ult():
    ult = 140
    assert ult * 1.1 <= SHOP["bomb"]["cost"] <= ult * 1.3


def test_best_bomb_x():
    class U:
        def __init__(self, x):
            self.x, self.alive = x, True

    us = [U(100), U(150), U(180), U(900)]
    x, n = best_bomb_x(us, 100)
    assert n == 3 and x in (100, 150, 180)


# --- продажа ------------------------------------------------------------------


def test_sell_refund_and_free_slot():
    g, w, a, b = _game()
    a.gold = 200
    assert a.buy(3, g.rng, slot=5)  # ульт 140
    cost = a.building_at(5).cost
    gold0 = a.gold
    refund = a.sell(5)
    assert refund == int(cost * SELL_REFUND)
    assert 0.5 <= SELL_REFUND <= 0.6
    assert a.gold == gold0 + refund
    assert a.building_at(5) is None and a.is_slot_free(5)
    assert a.sell(5) == 0
    # ульт-лимит освобождается
    a.gold = 1000
    assert a.buy(3, g.rng, slot=5)


# --- «Соседство» -----------------------------------------------------------------


def test_adjacency_speeds_up_same_neighbors():
    g, w, a, b = _game()
    a.gold = 1000
    a.buy(0, g.rng, slot=0)
    a.buy(0, g.rng, slot=1)  # сосед по ряду
    a.buy(1, g.rng, slot=6)  # под мечниками, другой тип
    a.buy(0, g.rng, slot=9)  # одиночка
    assert a.building_at(0).spawn_mult == ADJ_SPAWN_MULT
    assert a.building_at(1).spawn_mult == ADJ_SPAWN_MULT
    assert a.building_at(6).spawn_mult == 1.0
    assert a.building_at(9).spawn_mult == 1.0
    assert a.neighbors(5) == [4, 11]  # край ряда не переносится
    a.sell(1)
    assert a.building_at(0).spawn_mult == 1.0
    assert a.move_building(9, 1)  # подвинули одиночку к первому
    assert a.building_at(0).spawn_mult == ADJ_SPAWN_MULT


def test_best_slot_prefers_same_neighbors():
    g, w, a, b = _game()
    a.gold = 1000
    a.buy(1, g.rng, slot=8)
    assert a.best_slot(1) in a.neighbors(8)
    assert a.best_slot(0) == 0


def test_adjacent_building_spawns_faster():
    g, w, a, b = _game()
    a.gold = 1000
    a.buy(0, g.rng, slot=0)
    a.buy(0, g.rng, slot=1)
    a.buy(0, g.rng, slot=9)
    rng = random.Random(0)
    fast = a.building_at(0)
    slow = a.building_at(9)
    fast.timer = slow.timer = 0.0
    for _ in range(int(600 / 0.2)):
        fast.tick(0.2, a, 0.0, rng)
        slow.tick(0.2, a, 0.0, rng)
    assert fast.spawned > slow.spawned


# --- «Казна» и экономика ------------------------------------------------------------


def test_interest_every_period_capped():
    g, w, a, b = _game()
    a.gold = 1000.0
    b.gold = 50.0
    ev = []
    while w.t < INTEREST["every"] + 2 * w.dt:
        w.tick()
        ev += [e for e in w.events if e[0] == "interest"]
    assert len(ev) == 2  # по разу на игрока
    assert any(e[1] == 0 and e[2] == INTEREST["cap"] for e in ev)
    assert all(e[2] <= INTEREST["cap"] for e in ev)


def test_normal_mode_faster_start():
    assert ECON["normal"]["start"] >= 90
    assert ECON["normal"]["base"] >= 20


# --- бот и детерминизм ------------------------------------------------------------


def test_bot_shop_repairs_low_castle():
    g, w, a, b = _game()
    a.castle.hp = a.castle.max_hp * 0.3
    a.gold = 500
    bot_shop(a, b, w)
    assert a.repairs == 1


def test_bot_bombs_big_crowd_near_own_castle():
    g, w, a, b = _game()
    for i in range(8):
        _spawn(b, 0, x=a.castle.x + 200 + i * 5)
    a.gold = 500
    bot_shop(a, b, w)
    assert len(w.bombs) == 1 and abs(w.bombs[0].x - (a.castle.x + 217)) < 100


def test_bot_does_not_bomb_far_crowd():
    g, w, a, b = _game()
    for i in range(8):
        _spawn(b, 0, x=b.castle.x - 100 - i * 5)
    a.gold = 500
    bot_shop(a, b, w)
    assert w.bombs == []


def test_full_match_with_shop_is_deterministic():
    def run():
        return Game("Некрополь", "Аркана", POOL[0](), POOL[1](), mode="turbo", seed=7).run()

    r1, r2 = run(), run()
    assert r1["winner"] == r2["winner"] and r1["t"] == r2["t"] and r1["chp"] == r2["chp"]
    assert r1["winner"] in (0, 1)
