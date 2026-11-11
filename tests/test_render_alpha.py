"""Регрессия «чёрных прямоугольников»: окно в формате ARGB (как у pygame-ce на Linux).

Раньше поле рисовалось на `Surface().convert()` формата окна: альфа фона = 0, и
прозрачные края спрайтов / затемнение паузы становились чёрными. Теперь кадр
рисуется на собственном непрозрачном холсте (ui/surf.py).
"""

import os

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
pygame = pytest.importorskip("pygame")


@pytest.fixture(scope="module")
def argb_app():
    pygame.init()
    pygame.display.set_mode((1280, 720))
    display = pygame.Surface((1280, 720), pygame.SRCALPHA)  # «окно» с альфа-каналом
    display.fill((0, 0, 0, 0))
    from castlefight.ui.main import App

    app = App(display)
    yield app, display


def _match(app):
    from castlefight.ai.bots import CounterBot
    from castlefight.ui.scenes import MatchScene

    m = MatchScene(app, "Королевство", "Орда", "normal", seed=2)
    m.game.bot_a = CounterBot()
    m.game.clickers = [None, None]  # без вспышек ударов бота поверх фона
    app.set_scene(m)
    w = m.game.world
    for _ in range(int(120 / 0.2)):
        m.renderer.before_step(w)
        m.game.step()
        m.renderer.after_step(w)
    m.game.bot_a = None
    for _ in range(3):
        app.frame([], 1 / 60)
    return m


def _lum(c) -> float:
    return 0.3 * c[0] + 0.59 * c[1] + 0.11 * c[2]


def test_canvas_and_field_have_no_alpha(argb_app):
    app, display = argb_app
    m = _match(app)
    assert app.screen.get_masks()[3] == 0
    assert not app.screen.get_flags() & pygame.SRCALPHA
    assert m.renderer.field_bg.get_masks()[3] == 0


def test_transparent_sprite_pixels_are_not_black(argb_app):
    app, display = argb_app
    m = _match(app)
    from castlefight.ui.layout import x_to_screen
    from castlefight.ui.renderer import CASTLE_W
    from castlefight.ui.theme import CASTLE_BASE_Y

    # замок игрока: берём прозрачные пиксели спрайта и сравниваем окно с фоном
    p = m.player
    spr = app.assets.castle(0, CASTLE_W)
    rect = spr.get_rect(midbottom=(int(x_to_screen(p.castle.x)), CASTLE_BASE_Y + 14))
    checked = 0
    for yy in range(0, spr.get_height(), 7):
        for xx in range(0, spr.get_width(), 7):
            if spr.get_at((xx, yy)).a != 0:
                continue
            sx, sy = rect.x + xx, rect.y + yy
            if not (0 <= sx < 1280 and rect.y + 30 <= sy < 380):
                continue  # сверху — полоска HP замка
            if any(r.inflate(12, 12).collidepoint(sx, sy) for r, _ in m.renderer.unit_rects):
                continue
            got = display.get_at((sx, sy))
            want = m.renderer.field_bg.get_at((sx, sy))
            assert got.a == 255, (sx, sy, got)
            # фон (небо/холмы) не должен стать чёрным
            if _lum(want) > 60:
                assert _lum(got) > 0.5 * _lum(want), (sx, sy, got, want)
            checked += 1
    assert checked > 30


def test_pause_is_light_dim_not_black(argb_app):
    app, display = argb_app
    m = _match(app)
    area = [(x, y) for x in range(40, 1240, 37) for y in range(80, 380, 23)]
    before = sum(_lum(display.get_at(pt)) for pt in area) / len(area)
    m.paused = True
    app.frame([], 1 / 60)
    after = sum(_lum(display.get_at(pt)) for pt in area if not (430 <= pt[0] <= 850 and 200 <= pt[1] <= 500))
    n = sum(1 for pt in area if not (430 <= pt[0] <= 850 and 200 <= pt[1] <= 500))
    after /= n
    assert before > 80
    assert after > 0.6 * before, (before, after)
    m.paused = False


def test_menu_and_other_screens_render_on_argb(argb_app):
    app, display = argb_app
    from castlefight.ui.scenes import HowToScene, MenuScene, SetupScene

    for sc in (MenuScene(app), HowToScene(app), SetupScene(app)):
        app.set_scene(sc)
        app.frame([], 1 / 60)
        # нет чёрных провалов: средняя яркость кадра нормальная, альфа окна 255
        pts = [(x, y) for x in range(5, 1280, 61) for y in range(5, 720, 47)]
        assert all(display.get_at(pt).a == 255 for pt in pts)
        assert sum(_lum(display.get_at(pt)) for pt in pts) / len(pts) > 60
