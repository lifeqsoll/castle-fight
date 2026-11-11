import time

from castlefight.net.discovery import STALE, Beacon, Browser


def test_discovery_over_localhost_and_stale_drop():
    port = 47999
    br = Browser(port)
    bc = Beacon("Игра Мэлл", "mell", "Орда", 47821, port=port)
    try:
        bc.poll(0.0)
        bc.poll(0.5)  # раньше INTERVAL — не шлёт повторно
        deadline = time.monotonic() + 2
        while not br.games() and time.monotonic() < deadline:
            br.poll()
            time.sleep(0.02)
        g = br.games()
        assert len(g) == 1 and g[0].nick == "mell" and g[0].tcp == 47821 and g[0].faction == "Орда"
        br.poll(time.monotonic() + STALE + 1)  # маячок замолчал — игра пропала
        assert br.games() == []
    finally:
        bc.close()
        br.close()


def test_garbage_ignored():
    import socket

    port = 47998
    br = Browser(port)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.sendto(b"not json", ("127.0.0.1", port))
        s.sendto(b'{"magic":"other"}', ("127.0.0.1", port))
        time.sleep(0.1)
        br.poll()
        assert br.games() == []
    finally:
        s.close()
        br.close()
