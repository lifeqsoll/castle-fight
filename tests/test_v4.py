"""v4: H в меню (любая раскладка), бот-кликер, городок, сетевые экраны, повреждения замка."""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
import pytest

from castlefight.ai.bots import BotClicker, CounterBot
from castlefight.core.game import Game


@pytest.fixture(scope="module")
def app():
    pygame.init()
    import castlefight.ui.text as text

    text._FONTS.clear()  # другие тесты делали pygame.quit()
    from castlefight.ui.main import App

    return App(pygame.display.set_mode((1280, 720)))


def _key(key, scancode=0, uni=""):
    return pygame.event.Event(pygame.KEYDOWN, key=key, scancode=scancode, mod=0, unicode=uni)


def test_h_opens_howto_latin(app):
    from castlefight.ui.scenes import HowToScene, MenuScene

    app.set_scene(MenuScene(app))
    app.handle(_key(pygame.K_h, pygame.KSCAN_H, "h"))
    assert isinstance(app.scene, HowToScene)


def test_h_opens_howto_russian_layout(app):
    """С русской раскладкой keycode — 'р', но физическая клавиша (scancode) — H."""
    from castlefight.ui.scenes import HowToScene, MenuScene

    app.set_scene(MenuScene(app))
    app.handle(_key(ord("р"), pygame.KSCAN_H, "р"))
    assert isinstance(app.scene, HowToScene)
    app.set_scene(MenuScene(app))
    app.handle(_key(pygame.K_F1))
    assert isinstance(app.scene, HowToScene)


def test_howto_pages_flip_and_draw(app):
    from castlefight.ui.scenes import HowToScene

    s = HowToScene(app)
    app.set_scene(s)
    for _ in range(len(s.PAGES) + 2):
        s.draw(app.screen)
        app.handle(_key(pygame.K_RIGHT))
    assert s.page == len(s.PAGES) - 1
    app.handle(_key(pygame.K_LEFT))
    assert s.page == len(s.PAGES) - 2


def test_menu_net_button_and_scenes(app):
    from castlefight.ui.scenes import JoinScene, MenuScene, NetMenuScene

    app.set_scene(MenuScene(app))
    app.handle(_key(pygame.K_n, pygame.KSCAN_N, "n"))
    assert isinstance(app.scene, NetMenuScene)
    app.scene.draw(app.screen)
    app.handle(_key(pygame.K_2, pygame.KSCAN_2, "2"))
    assert isinstance(app.scene, JoinScene)
    js = app.scene
    js.ip.focus = True
    for ch in "127.0.0.1":
        js.handle(_key(ord(ch), 0, ch))
    assert js.ip.value == "127.0.0.1"
    js.update(0.1)
    js.draw(app.screen)
    js._leave()


def test_bot_clicker_rate_and_cooldown():
    g = Game("Королевство", "Орда", CounterBot(), CounterBot(), mode="normal", seed=5, bot_click=(False, True))
    w = g.world
    clicks = 0
    last = -1.0
    gaps = []
    for _ in range(int(240 / 0.2)):
        g.step()
        b = g.players[1]
        if b.strikes > clicks:
            clicks = b.strikes
            if last >= 0:
                gaps.append(w.t - last)
            last = w.t
        if w.winner is not None:
            break
    assert clicks > 50
    assert min(gaps) >= 0.4 - 1e-6  # те же правила перезарядки, что у человека
    rate = len(gaps) / sum(gaps)
    assert 0.7 < rate < 2.0


def test_bot_clicker_deterministic():
    def run():
        g = Game("Лес", "Некрополь", CounterBot(), CounterBot(), mode="turbo", seed=9)
        for _ in range(600):
            g.step()
        return [(p.strikes, round(p.castle.hp, 3), p.sword) for p in g.players]

    assert run() == run()


def test_bot_buys_sword_eventually():
    g = Game("Королевство", "Орда", CounterBot(), CounterBot(), mode="turbo", seed=3)
    for _ in range(int(600 / 0.2)):
        g.step()
        if g.world.winner is not None:
            break
    assert max(p.sword for p in g.players) >= 1


def test_town_positions_unique_and_mirrored():
    from castlefight.ui.theme import WIDTH
    from castlefight.ui.renderer import town_pos

    pts = {town_pos(0, i)[:2] for i in range(12)}
    assert len(pts) == 12
    for i in range(12):
        x0, y0, _ = town_pos(0, i)
        x1, y1, _ = town_pos(1, i)
        assert y0 == y1 and abs(x0 + x1 - WIDTH) < 1e-6


def test_castle_damage_stages_differ(app):
    a = app.assets
    s0, s1, s2 = (a.castle(0, 196, k) for k in range(3))
    assert s0.get_size() == s1.get_size() == s2.get_size()
    assert pygame.image.tobytes(s0, "RGBA") != pygame.image.tobytes(s1, "RGBA") != pygame.image.tobytes(s2, "RGBA")


def test_match_scene_client_side_draws(app):
    """MatchScene со стороной 1 (как у гостя сети) рисуется и ставит здание в правую зону."""
    from castlefight.ui.scenes import MatchScene

    class FakeNet:
        side = 1
        is_host = False
        acc = 0.0
        error = ""

        def __init__(self):
            self.game = Game("Королевство", "Орда", None, None, mode="normal", seed=1)
            self.sent = []

        def command(self, c):
            self.sent.append(c)

        def pump(self, dt, before=None, after=None):
            from castlefight.core import commands

            for c in self.sent:
                commands.apply(self.game, 1, c)
            self.sent = []
            self.game.step()
            return 1

        def close(self):
            pass

    net = FakeNet()
    s = MatchScene(app, "Королевство", "Орда", "normal", net=net)
    app.set_scene(s)
    from castlefight.data.enums import Role

    s._select(Role.MELEE)
    s._place(0, keep=False)
    s.update(0.2)
    s.draw(app.screen)
    assert net.game.players[1].building_at(0) is not None
    assert net.game.players[0].building_at(0) is None
