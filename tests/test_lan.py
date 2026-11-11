"""Хост и клиент по localhost: команды обеих сторон, одинаковое состояние, версия, отключение."""

import time

from castlefight.data.enums import Role
from castlefight.net.discovery import Browser
from castlefight.net.lan import ClientJoin, HostLobby, checksum


def _connect(port=0, faction_c="Орда", version=None):
    host = HostLobby("Королевство", "turbo", nick="мэлл", port=port, beacon=True, beacon_port=47997)
    client = ClientJoin("127.0.0.1", host.port, faction_c, nick="друг")
    if version is not None:
        pass
    hs = cs = None
    t0 = time.monotonic()
    while (hs is None or cs is None) and time.monotonic() - t0 < 3:
        hs = host.poll()
        cs = client.poll()
        time.sleep(0.005)
    return host, client, hs, cs


def test_handshake_and_lockstep_consistent_state():
    host, client, hs, cs = _connect()
    assert hs is not None and cs is not None
    assert hs.side == 0 and cs.side == 1
    assert [p.faction.name for p in hs.game.players] == [p.faction.name for p in cs.game.players] == ["Королевство", "Орда"]
    assert hs.game.mode == cs.game.mode == "turbo"
    # команды обеих сторон
    hs.command({"c": "buy", "i": 0, "s": 0})
    cs.command({"c": "buy", "i": 1, "s": 3})
    for i in range(400):  # 400 тиков = 80 с игры
        if i == 150:
            hs.command({"c": "shop", "item": "rage", "x": None})
            cs.command({"c": "buy", "i": 0, "s": 4})
        if i == 200:
            u = next((u for u in hs.game.players[1].units if u.alive), None)
            if u is not None:
                hs.command({"c": "strike", "u": u.uid})
            cs.command({"c": "sell", "s": 3})
        hs.pump(0.2)
        time.sleep(0.001)
        cs.pump(0)
    t0 = time.monotonic()
    while cs.n < hs.n and time.monotonic() - t0 < 2:
        cs.pump(0)
        time.sleep(0.005)
    assert cs.n == hs.n >= 400
    assert checksum(hs.game) == checksum(cs.game)
    assert not cs.desync
    a0, a1 = hs.game.players[0], cs.game.players[0]
    assert a0.building_at(0) is not None and a1.building_at(0) is not None
    b = cs.game.players[1]
    assert b.building_at(4) is not None and b.building_at(4).role == Role.MELEE
    assert b.building_at(3) is None  # продано
    assert hs.game.players[1].sold == cs.game.players[1].sold == 1
    assert len(a0.units) == len(a1.units)
    # клиент вышел — хост узнаёт
    cs.close()
    t0 = time.monotonic()
    while not hs.error and time.monotonic() - t0 < 2:
        hs.pump(0.0)
        time.sleep(0.01)
    assert hs.error
    host.close()


def test_version_mismatch_rejected(monkeypatch):
    import castlefight.net.discovery as disc
    import castlefight.net.lan as lan

    host = HostLobby("Лес", "normal", port=0, beacon=False)
    monkeypatch.setattr(lan, "VERSION", "999")
    client = ClientJoin("127.0.0.1", host.port, "Орда")
    monkeypatch.setattr(lan, "VERSION", disc.VERSION)
    t0 = time.monotonic()
    while not client.error and time.monotonic() - t0 < 3:
        host.poll()
        client.poll()
        time.sleep(0.01)
    assert "верси" in client.error
    host.close()


def test_connect_refused_gives_message():
    c = ClientJoin("127.0.0.1", 1, "Орда", timeout=0.5)
    assert c.error and c.poll() is None


def test_host_beacon_seen_by_browser():
    br = Browser(47997)
    host = HostLobby("Кузня", "normal", nick="мэлл", port=0, beacon=True, beacon_port=47997)
    try:
        t0 = time.monotonic()
        while not br.games() and time.monotonic() - t0 < 3:
            host.poll()
            br.poll()
            time.sleep(0.02)
        g = br.games()
        assert g and g[0].tcp == host.port and g[0].faction == "Кузня"
    finally:
        host.close()
        br.close()
