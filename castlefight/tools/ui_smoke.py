"""Скриптовый прогон UI без окна: меню → фракция → расстановка мышью → бой → итоги.

Запуск: python -m castlefight.tools.ui_smoke [папка_для_скриншотов] [фракция 0..5] [--native]
Работает и на сервере без дисплея (SDL_VIDEODRIVER=dummy ставится сам).
По умолчанию «окно» эмулируется в формате ARGB с прозрачной альфой — так ведёт себя
окно на многих Linux (Arch, pygame-ce), где раньше были чёрные фоны у спрайтов.
--native — рисовать прямо в окно dummy-драйвера.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

from castlefight.data.enums import Role  # noqa: E402
from castlefight.ui.layout import slot_rect  # noqa: E402
from castlefight.ui.main import App  # noqa: E402
from castlefight.ui.scenes import MatchScene, SetupScene  # noqa: E402
from castlefight.ui.theme import HEIGHT, ROLE_ORDER, WIDTH  # noqa: E402

DT = 1 / 60


def ev_move(pos):
    return pygame.event.Event(pygame.MOUSEMOTION, pos=pos, rel=(0, 0), buttons=(0, 0, 0))


def ev_down(pos, button=1):
    return pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=button)


def ev_up(pos, button=1):
    return pygame.event.Event(pygame.MOUSEBUTTONUP, pos=pos, button=button)


def ev_key(key):
    return pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode="", scancode=0)


class Driver:
    def __init__(self, out: Path, argb: bool = True) -> None:
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        if argb:
            self.screen = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            self.screen.fill((0, 0, 0, 0))
        self.app = App(self.screen)
        self.out = out
        out.mkdir(parents=True, exist_ok=True)

    def frames(self, n: int = 1, events=()) -> None:
        self.app.frame(list(events), DT)
        for _ in range(n - 1):
            self.app.frame([], DT)

    def click(self, pos, frames: int = 2) -> None:
        self.frames(1, [ev_move(pos)])
        self.frames(1, [ev_down(pos)])
        self.frames(frames, [ev_up(pos)])

    def drag(self, a, b) -> None:
        self.frames(1, [ev_move(a)])
        self.frames(1, [ev_down(a)])
        mid = ((a[0] + b[0]) // 2, (a[1] + b[1]) // 2)
        self.frames(2, [ev_move(mid)])
        self.frames(2, [ev_move(b)])
        self.frames(2, [ev_up(b)])

    def shot(self, name: str) -> Path:
        p = self.out / f"{name}.png"
        # как композитор окна: берём только RGB, альфу игнорируем
        raw = pygame.image.tobytes(self.screen, "RGBA")
        try:
            from PIL import Image

            Image.frombytes("RGBA", (WIDTH, HEIGHT), raw).convert("RGB").save(p)
        except Exception:
            pygame.image.save(self.screen, str(p))
        print("saved", p)
        return p


def run(out: Path, faction_index: int = 0, mode: str = "normal", argb: bool = True) -> dict:
    d = Driver(out, argb)
    app = d.app
    d.frames(30, [ev_move((WIDTH // 2, 300))])
    d.shot("01_menu")

    menu = app.scene
    d.click(menu.howto.rect.center)
    d.frames(10)
    d.shot("01b_howto")
    d.click(app.scene.go.rect.center)
    assert isinstance(app.scene, SetupScene), app.scene
    setup = app.scene
    d.click(setup.cards[faction_index].center)
    d.click(setup.next_enemy.rect.center)  # конкретный противник вместо «случайного»
    d.click(setup.next_enemy.rect.center)
    if mode == "turbo":
        d.click(setup.m_turbo.rect.center)
    d.frames(20, [ev_move(setup.cards[faction_index].center)])
    d.shot("02_faction_select")
    d.click(setup.start.rect.center)
    assert isinstance(app.scene, MatchScene), app.scene
    m: MatchScene = app.scene
    m.seed = 11
    player = m.player

    def wait_gold(cost: float, limit: float = 120.0) -> None:
        t0 = m.game.world.t
        while player.gold < cost and m.game.world.t - t0 < limit:
            d.frames(6)

    # 1) мечник/ближник в клетку 0 — клик по карточке, клик по клетке
    placed = []
    plan = [(Role.MELEE, 0), (Role.RANGED, 6), (Role.MELEE, 1), (Role.SUMMON, 7)]
    for role, slot in plan:
        bt = player.faction.building_by_role(role)
        wait_gold(bt.cost)
        d.click(m.panel.cards[role].center)
        assert m.placing == role, (m.placing, role)
        target = slot_rect(0, slot).center
        d.frames(3, [ev_move(target)])
        d.click(target)
        b = player.building_at(slot)
        assert b is not None and b.role == role, f"не поставилось {role} в {slot}"
        placed.append((role.value, slot))

    # 2) перетаскивание: из клетки 7 в клетку 9
    d.drag(slot_rect(0, 7).center, slot_rect(0, 9).center)
    assert player.building_at(9) is not None and player.building_at(7) is None, "drag не сработал"

    # 3) режим расстановки с призраком над свободной клеткой (клавиша 2)
    wait_gold(player.faction.building_by_role(Role.RANGED).cost)
    d.frames(1, [ev_key(pygame.K_2)])
    d.frames(1, [ev_move(slot_rect(0, 2).center)])
    d.frames(12)
    d.shot("03_placement_ghost")
    # ПКМ — отмена
    d.frames(2, [ev_down(slot_rect(0, 2).center, 3)])
    assert m.placing is None

    # 4) ускоряем (F, F → x4) и играем «как игрок»: покупаем по совету / по кругу
    d.frames(1, [ev_key(pygame.K_f)])
    d.frames(1, [ev_key(pygame.K_f)])
    order = [Role.RANGED, Role.MELEE, Role.ULT, Role.SUMMON, Role.MELEE, Role.RANGED, Role.ULT, Role.MELEE]
    k = 0
    res_v3: dict = {}
    mid_saved = False
    tooltip_saved = False
    while not m.over and m.game.world.t < 26 * 60:
        d.frames(4)
        free = player.free_slots()
        if free and k < len(order):
            role = order[k]
            idx = ROLE_ORDER.index(role)
            reason = player.buy_block_reason(idx)
            if reason is None:
                d.click(m.panel.cards[role].center, frames=1)
                d.click(slot_rect(0, free[0]).center, frames=1)
                k += 1
            elif reason != "не хватает золота":
                k += 1
        elif not free and player.lvl < 5 and player.gold >= 100 + 50 * player.lvl:
            d.frames(1, [ev_key(pygame.K_u)])
        n_units = len(player.units) + len(m.enemy.units)
        if not mid_saved and m.game.world.t > 150 and (n_units >= 34 or m.game.world.t > 600):
            d.frames(1, [ev_move((WIDTH // 2, 300))])
            d.shot("04_mid_battle")
            mid_saved = True
            d.frames(2, [ev_key(pygame.K_SPACE)])
            d.shot("04b_pause")
            d.frames(2, [ev_key(pygame.K_SPACE)])
            assert not m.paused
        if mid_saved and not tooltip_saved:
            d.frames(2, [ev_move(m.panel.cards[Role.ULT].center)])
            d.shot("05_card_tooltip")
            d.frames(2, [ev_move(slot_rect(0, 0).center)])
            d.shot("06_building_tooltip")
            d.frames(1, [ev_move((WIDTH // 2, 300))])
            tooltip_saved = True
            v3_features(d, m, res_v3)
        if m.game.world.t > 600 and not hasattr(m, "_late"):
            d.shot("07_late_battle")
            m._late = True
    if not mid_saved:
        d.shot("04_mid_battle")
    if not m.over:  # подстраховка, чтобы снять экран итогов
        m.game.world.finish_by_timeout()
    d.frames(90, [ev_move((WIDTH // 2, 200))])
    d.shot("08_game_over")
    w = m.game.world
    res = {
        "v3": res_v3,
        "winner": w.winner,
        "t": round(w.t, 1),
        "placed": placed,
        "player_buildings": len(player.buildings),
        "enemy_buildings": len(m.enemy.buildings),
        "castle_hp": (round(player.castle.hp), round(m.enemy.castle.hp)),
    }
    # пауза
    d.click(m.btn_menu.rect.center)
    print(res)
    return res


def v3_features(d: Driver, m: MatchScene, res: dict) -> None:
    """Удар героя, меч, зелье, бомба, продажа — мышью и клавишами, со скриншотами."""
    from castlefight.ui.layout import x_to_screen

    player = m.player
    w = m.game.world
    speed_i = m.speed_i
    m.speed_i = 0
    player.gold += 600  # чтобы точно хватило на всё (для скриншотов)
    # меч (T) и зелье ярости (Q)
    d.frames(1, [ev_key(pygame.K_t)])
    res["sword"] = player.sword
    d.frames(1, [ev_key(pygame.K_q)])
    res["rage"] = player.buff_active("rage", w.t)
    # удар героя по ближайшему врагу: наводим курсор и кликаем
    hits = 0
    for _ in range(12):
        d.frames(1)
        rects = [(r, u) for r, u in m.renderer.unit_rects if u.side == 1 and u.alive and 140 < r.centery < 560]
        if not rects:
            d.frames(10)
            continue
        r, u = min(rects, key=lambda t: t[0].centerx)
        before = player.strikes
        d.frames(1, [ev_move(r.center)])
        if hits == 0:
            d.shot("09_strike_hover")
        d.frames(1, [ev_down(r.center)])
        d.frames(1, [ev_up(r.center)])
        hits += player.strikes - before
        d.frames(int(0.45 * 60))
    res["strikes"] = player.strikes
    res["strike_dealt"] = round(player.strike_dealt)
    # подсказка лавки
    d.frames(2, [ev_move(m.panel.items["bomb"].center)])
    d.shot("10_shop_tooltip")
    # бомба: R → прицел над толпой врагов → клик
    d.frames(1, [ev_key(pygame.K_r)])
    res["bomb_armed"] = m.armed == "bomb"
    xs = [u.x for u in m.enemy.units if u.alive]
    if xs:
        from castlefight.ai.bots import best_bomb_x

        bx, _ = best_bomb_x(m.enemy.units, 80)
        target = (int(x_to_screen(bx)), 414)
    else:
        target = (WIDTH // 2, 414)
    d.frames(6, [ev_move(target)])
    d.shot("11_bomb_aim")
    kills0 = player.kills
    d.click(target, frames=1)
    res["bomb_dropped"] = len(w.bombs) == 1
    d.frames(int(0.6 * 60))
    d.shot("12_bomb_falling")
    n0 = sum(1 for e in m.renderer.events if e[0] == "bomb")
    for _ in range(240):
        d.frames(1)
        if sum(1 for e in m.renderer.events if e[0] == "bomb") > n0:
            break
    d.frames(5)
    d.shot("13_bomb_explosion")
    d.frames(30)
    res["bomb_kills"] = player.kills - kills0
    # продажа: ПКМ по зданию → «пузырь» → «Да»
    slot = next((b.slot for b in player.buildings), None)
    if slot is not None:
        c = slot_rect(0, slot).center
        d.frames(1, [ev_move(c)])
        d.frames(2, [ev_down(c, 3)])
        d.frames(1, [ev_up(c, 3)])
        res["sell_open"] = m.sell_slot == slot
        d.frames(1, [ev_move(m.sell_yes.rect.center)])
        d.shot("14_sell_confirm")
        gold0 = player.gold
        d.click(m.sell_yes.rect.center, frames=2)
        res["sold"] = player.building_at(slot) is None
        res["refund"] = round(player.gold - gold0)
    # пауза для скриншота лавки в работе
    d.frames(1, [ev_move((WIDTH // 2, 250))])
    d.shot("15_battle_shop")
    m.speed_i = speed_i


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    out = Path(args[0] if args else "screenshots")
    fi = int(args[1]) if len(args) > 1 else 0
    mode = args[2] if len(args) > 2 else "normal"
    run(out, fi, mode, argb="--native" not in sys.argv)
