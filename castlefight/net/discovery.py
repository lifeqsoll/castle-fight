"""LAN-автопоиск игр (как «Открыть для сети» в Minecraft). Без pygame, неблокирующий.

Хост раз в секунду шлёт UDP-маячок (JSON) на 255.255.255.255, широковещательные адреса
подсетей и 127.0.0.1. Клиент слушает порт и держит список игр, удаляя молчащие > STALE с.
"""

from __future__ import annotations

import json
import os
import socket
import time
from dataclasses import dataclass
from typing import Optional

PORT = 47820
MAGIC = "castlefight"
VERSION = "4"
INTERVAL = 1.0
STALE = 4.0


def _broadcast_targets() -> list[str]:
    out = ["255.255.255.255", "127.0.0.1"]
    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            if not ip.startswith("127."):
                out.append(ip.rsplit(".", 1)[0] + ".255")  # /24 — самый частый случай
    except OSError:
        pass
    return list(dict.fromkeys(out))


class Beacon:
    """Хост: вызывать poll() каждый кадр — сам шлёт маячок раз в INTERVAL."""

    def __init__(self, name: str, nick: str, faction: str, tcp_port: int, port: int = PORT) -> None:
        self.info = {"magic": MAGIC, "v": VERSION, "name": name, "nick": nick, "faction": faction, "tcp": tcp_port, "id": os.urandom(4).hex()}
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.sock.setblocking(False)
        self.targets = _broadcast_targets()
        self._next = 0.0

    def poll(self, now: Optional[float] = None) -> None:
        now = time.monotonic() if now is None else now
        if now < self._next:
            return
        self._next = now + INTERVAL
        data = json.dumps(self.info).encode()
        for t in self.targets:
            try:
                self.sock.sendto(data, (t, self.port))
            except OSError:
                pass  # нет сети / адрес недоступен — не страшно

    def close(self) -> None:
        self.sock.close()


@dataclass
class Found:
    host: str
    tcp: int
    name: str
    nick: str
    faction: str
    seen: float


class Browser:
    """Клиент: poll() каждый кадр, games() — живой список (старые > STALE с убираются)."""

    def __init__(self, port: int = PORT) -> None:
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            try:
                self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except OSError:
                pass
        self.sock.bind(("", port))
        self.sock.setblocking(False)
        self.found: dict[str, Found] = {}

    def poll(self, now: Optional[float] = None) -> None:
        now = time.monotonic() if now is None else now
        while True:
            try:
                data, (addr, _) = self.sock.recvfrom(2048)
            except (BlockingIOError, InterruptedError):
                break
            except OSError:
                break
            try:
                d = json.loads(data.decode())
                if d.get("magic") != MAGIC or d.get("v") != VERSION:
                    continue
                key = str(d.get("id") or f"{addr}:{d['tcp']}")
                old = self.found.get(key)
                if old is not None and addr.startswith("127.") and not old.host.startswith("127."):
                    addr = old.host  # один хост виден по нескольким адресам — берём сетевой
                self.found[key] = Found(addr, int(d["tcp"]), str(d.get("name", "")), str(d.get("nick", "")),
                                        str(d.get("faction", "")), now)
            except (ValueError, KeyError, TypeError):
                continue  # мусор в сети игнорируем
        for k in [k for k, f in self.found.items() if now - f.seen > STALE]:
            del self.found[k]

    def games(self) -> list[Found]:
        return sorted(self.found.values(), key=lambda f: (f.name, f.host))

    def close(self) -> None:
        self.sock.close()
