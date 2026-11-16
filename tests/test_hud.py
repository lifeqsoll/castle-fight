from types import SimpleNamespace

import pygame

from castlefight.ui.hud import TopBar
from castlefight.ui.scenes import MatchScene


def test_network_hud_shows_local_players_gold_and_labels():
    players = [object(), object()]
    world = SimpleNamespace(players=players)
    bar = TopBar(None)
    labels = []
    selected = []
    bar._side = lambda screen, player, side, who, world: labels.append((side, who))
    bar._center = lambda screen, world, player, mode, speed, paused, network: selected.append((player, network))

    bar.draw(None, world, "normal", 1, False, me_side=1, network=True)

    assert labels == [(0, "соперник"), (1, "ты")]
    assert selected == [(players[1], True)]


def test_escape_leaves_network_match_without_fake_pause(monkeypatch):
    import castlefight.ui.scenes as scenes

    next_scene = object()
    monkeypatch.setattr(scenes, "NetMenuScene", lambda app: next_scene)
    closed = []
    selected = []
    scene = object.__new__(MatchScene)
    scene.game = SimpleNamespace(world=SimpleNamespace(winner=None))
    scene.net = SimpleNamespace(close=lambda: closed.append(True))
    scene.paused = False
    scene._cancel = lambda: False
    scene.app = SimpleNamespace(set_scene=selected.append)

    scene.handle(SimpleNamespace(type=pygame.KEYDOWN, key=pygame.K_ESCAPE))

    assert not scene.paused
    assert closed == [True]
    assert selected == [next_scene]
