"""UI-расстановка мышью (pygame в headless-режиме)."""

import os

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
pygame = pytest.importorskip("pygame")

from castlefight.data.enums import Role  # noqa: E402
from castlefight.ui.layout import slot_at, slot_rect  # noqa: E402


@pytest.fixture(scope="module")
def app():
    pygame.init()
    screen = pygame.display.set_mode((1280, 720))
    from castlefight.ui.main import App

    a = App(screen)
    yield a
    pygame.quit()


def _match(app):
    from castlefight.ui.scenes import MatchScene

    m = MatchScene(app, "Королевство", "Орда", "normal", seed=1)
    app.set_scene(m)
    m.player.gold = 1000
    return m


def _click(app, pos, button=1):
    app.frame([pygame.event.Event(pygame.MOUSEMOTION, pos=pos, rel=(0, 0), buttons=(0, 0, 0))], 1 / 60)
    app.frame([pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=button)], 1 / 60)
    app.frame([pygame.event.Event(pygame.MOUSEBUTTONUP, pos=pos, button=button)], 1 / 60)


def test_slot_geometry_roundtrip():
    for side in (0, 1):
        rects = [slot_rect(side, i) for i in range(12)]
        for i, r in enumerate(rects):
            assert slot_at(side, r.center) == i
            for j in range(i + 1, 12):
                assert not r.colliderect(rects[j])


def test_card_then_slot_places_building(app):
    m = _match(app)
    _click(app, m.panel.cards[Role.RANGED].center)
    assert m.placing == Role.RANGED
    gold = m.player.gold
    _click(app, slot_rect(0, 4).center)
    b = m.player.building_at(4)
    assert b is not None and b.role == Role.RANGED
    assert abs(m.player.gold - (gold - b.cost)) < 1.0
    assert m.placing is None


def test_hotkey_and_right_click_cancel(app):
    m = _match(app)
    app.frame([pygame.event.Event(pygame.KEYDOWN, key=pygame.K_1, mod=0, unicode="1", scancode=0)], 1 / 60)
    assert m.placing == Role.MELEE
    _click(app, slot_rect(0, 0).center, button=3)
    assert m.placing is None
    assert m.player.buildings == []


def test_occupied_slot_rejected_and_drag_moves(app):
    m = _match(app)
    _click(app, m.panel.cards[Role.MELEE].center)
    _click(app, slot_rect(0, 0).center)
    _click(app, m.panel.cards[Role.MELEE].center)
    gold = m.player.gold
    _click(app, slot_rect(0, 0).center)  # занято
    assert m.player.gold >= gold and len(m.player.buildings) == 1
    app.frame([pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0, unicode="", scancode=0)], 1 / 60)
    assert m.placing is None and not m.paused
    a, b = slot_rect(0, 0).center, slot_rect(0, 11).center
    app.frame([pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=a, button=1)], 1 / 60)
    app.frame([pygame.event.Event(pygame.MOUSEMOTION, pos=b, rel=(0, 0), buttons=(1, 0, 0))], 1 / 60)
    app.frame([pygame.event.Event(pygame.MOUSEBUTTONUP, pos=b, button=1)], 1 / 60)
    assert m.player.building_at(0) is None
    assert m.player.building_at(11) is not None
    assert m.player.gold >= gold  # перенос бесплатный (золото только капает)


def test_bot_buildings_get_slots_and_screens_render(app):
    m = _match(app)
    m.enemy.gold = 500
    for _ in range(30):
        app.frame([], 0.2)
    assert len(m.enemy.buildings) > 0
    assert all(b.slot is not None for b in m.enemy.buildings)
    from castlefight.ui.scenes import HowToScene, MenuScene, SetupScene

    for sc in (MenuScene(app), HowToScene(app), SetupScene(app)):
        app.set_scene(sc)
        app.frame([], 1 / 60)


def test_assets_fallback_without_files(app, tmp_path, monkeypatch):
    """Если PNG нет — игра рисует процедурные фигуры и не падает."""
    import castlefight.ui.assets as assets_mod

    monkeypatch.setattr(assets_mod, "ASSETS_DIR", tmp_path)
    a = assets_mod.Assets()
    assert a.bg.get_size() == (1280, 720)
    s = a.unit("Орда", Role.ULT, 1)
    assert s.get_width() > 0 and s.get_height() > 0
    assert a.building("Лес", Role.SUMMON, 50, 50).get_width() <= 50
    assert a.castle(0).get_width() > 0
