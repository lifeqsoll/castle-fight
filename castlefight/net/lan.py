"""Сетевая игра на двоих по локальной сети (stdlib socket, JSON-строки, неблокирующий).

Схема — «lockstep, ведёт хост»: обе стороны запускают одинаковую детерминированную
симуляцию (тот же seed). Хост — хозяин времени: каждый тик (0.2 с) он собирает команды
(свои и пришедшие от клиента), применяет их, делает шаг и шлёт клиенту
{"k":"tick","n":N,"cmds":[[side, cmd], ...]}. Клиент применяет те же команды в том же
порядке и делает тот же шаг. Каждые 25 тиков хост шлёт контрольную сумму — рассинхрон
виден сразу. TCP сам гарантирует порядок и доставку, поэтому схема устойчива на LAN.

Рукопожатие: клиент → {"k":"hello","v":ВЕРСИЯ,"nick","faction"};
хост → {"k":"welcome","seed","mode","factions":[хост, клиент]} или {"k":"reject","why"}.
"""

from __future__ import annotations

import json
import random
import socket
from typing import Callable, Optional

from castlefight.core import commands
from castlefight.core.game import Game
from castlefight.net.discovery import VERSION

TCP_PORT = 47821
LOGIC_DT = 0.2


def local_ips() -> list[str]:
    ips = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))  # пакет не уходит — просто узнаём свой адрес
        ips.append(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            if ip not in ips and not ip.startswith("127."):
                ips.append(ip)
    except OSError:
        pass
    return ips or ["127.0.0.1"]


class Conn:
    """Неблокирующее соединение с построчным JSON."""

    def __init__(self, sock: socket.socket) -> None:
        sock.setblocking(False)
        try:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            pass
        self.sock = sock
        self.inbuf = b""
        self.outbuf = b""
        self.closed = False
        self.why = ""

    def send(self, obj: dict) -> None:
        if self.closed:
            return
        self.outbuf += (json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
        self.flush()

    def flush(self) -> None:
        while self.outbuf and not self.closed:
            try:
                n = self.sock.send(self.outbuf)
                self.outbuf = self.outbuf[n:]
            except (BlockingIOError, InterruptedError):
                return
            except OSError as e:
                self._close(f"связь потеряна ({e.__class__.__name__})")

    def poll(self) -> list[dict]:
        out: list[dict] = []
        if self.closed:
            return out
        self.flush()
        while True:
            try:
                data = self.sock.recv(65536)
            except (BlockingIOError, InterruptedError):
                break
            except OSError as e:
                self._close(f"связь потеряна ({e.__class__.__name__})")
                break
            if not data:
                self._close("соперник отключился")
                break
            self.inbuf += data
        while b"\n" in self.inbuf:
            line, self.inbuf = self.inbuf.split(b"\n", 1)
            try:
                out.append(json.loads(line.decode()))
            except ValueError:
                continue
        return out

    def _close(self, why: str) -> None:
        if not self.closed:
            self.closed = True
            self.why = why
            try:
                self.sock.close()
            except OSError:
                pass

    def close(self, why: str = "отключено") -> None:
        try:
            self.send({"k": "bye"})
        except Exception:
            pass
        self._close(why)


class HostLobby:
    """Хост ждёт одного клиента. poll() — неблокирующий; когда пришёл hello → self.session."""

    def __init__(self, faction: str, mode: str, nick: str = "хост", port: int = TCP_PORT, beacon: bool = True,
                 beacon_port: Optional[int] = None) -> None:
        self.faction, self.mode, self.nick = faction, mode, nick
        self.srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.srv.bind(("", port))
        self.srv.listen(1)
        self.srv.setblocking(False)
        self.port = self.srv.getsockname()[1]
        self.conn: Optional[Conn] = None
        self.session: Optional[NetSession] = None
        self.error = ""
        self.beacon = None
        if beacon:
            from castlefight.net.discovery import PORT, Beacon

            try:
                self.beacon = Beacon(f"Игра {nick}", nick, faction, self.port, port=beacon_port or PORT)
            except OSError:
                self.beacon = None

    def poll(self) -> Optional["NetSession"]:
        if self.session is not None:
            return self.session
        if self.beacon is not None:
            self.beacon.info["faction"] = self.faction
            self.beacon.poll()
        if self.conn is None:
            try:
                s, _ = self.srv.accept()
                self.conn = Conn(s)
            except (BlockingIOError, InterruptedError):
                return None
            except OSError as e:
                self.error = str(e)
                return None
        for m in self.conn.poll():
            if m.get("k") != "hello":
                continue
            if str(m.get("v")) != VERSION:
                self.conn.send({"k": "reject", "why": f"разные версии игры: у хоста {VERSION}, у тебя {m.get('v')}"})
                self.conn.close()
                self.conn = None
                return None
            seed = random.randrange(1 << 30)
            cf = str(m.get("faction"))
            self.conn.send({"k": "welcome", "seed": seed, "mode": self.mode, "factions": [self.faction, cf], "nick": self.nick})
            game = Game(self.faction, cf, None, None, mode=self.mode, seed=seed)
            self.session = NetSession(self.conn, 0, game, peer_nick=str(m.get("nick", "игрок")))
            self.stop_listening()
            return self.session
        if self.conn is not None and self.conn.closed:
            self.conn = None
        return None

    def stop_listening(self) -> None:
        if self.beacon is not None:
            self.beacon.close()
            self.beacon = None
        try:
            self.srv.close()
        except OSError:
            pass

    def close(self) -> None:
        self.stop_listening()
        if self.conn is not None and self.session is None:
            self.conn.close()


class ClientJoin:
    """Клиент: connect (с таймаутом), hello, ждёт welcome. poll() → NetSession или None."""

    def __init__(self, host: str, port: int, faction: str, nick: str = "гость", timeout: float = 3.0) -> None:
        self.error = ""
        self.session: Optional[NetSession] = None
        self.conn: Optional[Conn] = None
        try:
            s = socket.create_connection((host, int(port)), timeout=timeout)
        except (OSError, ValueError) as e:
            self.error = f"не удалось подключиться к {host}:{port} ({e.__class__.__name__})"
            return
        self.conn = Conn(s)
        self.conn.send({"k": "hello", "v": VERSION, "nick": nick, "faction": faction})

    def poll(self) -> Optional["NetSession"]:
        if self.session is not None or self.conn is None:
            return self.session
        for m in self.conn.poll():
            if m.get("k") == "reject":
                self.error = str(m.get("why", "хост отказал"))
                self.conn.close()
                return None
            if m.get("k") == "welcome":
                fa, fb = m["factions"]
                game = Game(fa, fb, None, None, mode=m.get("mode", "normal"), seed=int(m["seed"]))
                self.session = NetSession(self.conn, 1, game, peer_nick=str(m.get("nick", "хост")))
                return self.session
        if self.conn.closed and not self.error:
            self.error = self.conn.why or "связь потеряна"
        return None

    def close(self) -> None:
        if self.conn is not None and self.session is None:
            self.conn.close()


def checksum(game: Game) -> list:
    w = game.world
    return [
        w.next_uid,
        [round(p.castle.hp, 2) for p in game.players],
        [round(sum(u.hp for u in p.units), 2) for p in game.players],
        [round(p.gold, 2) for p in game.players],
    ]


class NetSession:
    """Идущий сетевой матч. side — какой стороной управляет этот компьютер (0 хост, 1 клиент)."""

    def __init__(self, conn: Conn, side: int, game: Game, peer_nick: str = "") -> None:
        self.conn = conn
        self.side = side
        self.game = game
        self.peer_nick = peer_nick
        self.local: list[dict] = []
        self.remote: list[dict] = []
        self.ticks: list[dict] = []  # для клиента — пришедшие, но ещё не сыгранные тики
        self.n = 0
        self.acc = 0.0
        self.desync = False
        self.error = ""
        self.results: list[tuple[int, dict, object]] = []  # (side, cmd, результат) последнего шага

    @property
    def is_host(self) -> bool:
        return self.side == 0

    def command(self, cmd: dict) -> None:
        if self.is_host:
            self.local.append(cmd)
        else:
            self.conn.send({"k": "cmd", "c": cmd})

    def _receive(self) -> None:
        for m in self.conn.poll():
            k = m.get("k")
            if k == "cmd" and self.is_host:
                self.remote.append(m.get("c") or {})
            elif k == "tick" and not self.is_host:
                self.ticks.append(m)
            elif k == "sum" and not self.is_host:
                self.ticks.append(m)
            elif k == "bye":
                self.conn._close("соперник вышел из игры")
        if self.conn.closed and not self.error:
            self.error = self.conn.why or "связь потеряна"

    def _apply(self, cmds: list) -> None:
        self.results = []
        for side, cmd in cmds:
            self.results.append((side, cmd, commands.apply(self.game, int(side), cmd)))

    def pump(self, dt: float, before: Optional[Callable] = None, after: Optional[Callable] = None, max_steps: int = 20) -> int:
        """Принять сообщения и сделать столько тиков, сколько положено. Возвращает число тиков."""
        self._receive()
        steps = 0
        if self.is_host:
            self.acc += dt
            while self.acc >= LOGIC_DT and steps < max_steps and self.game.world.winner is None and not self.conn.closed:
                self.acc -= LOGIC_DT
                cmds = [[0, c] for c in self.local] + [[1, c] for c in self.remote]
                self.local, self.remote = [], []
                self.conn.send({"k": "tick", "n": self.n, "cmds": cmds})
                self._step(cmds, before, after)
                steps += 1
                if self.n % 25 == 0:
                    self.conn.send({"k": "sum", "n": self.n, "v": checksum(self.game)})
        else:
            while self.ticks and steps < max_steps:
                m = self.ticks.pop(0)
                if m["k"] == "sum":
                    if m["n"] == self.n and m["v"] != json.loads(json.dumps(checksum(self.game))):
                        self.desync = True
                    continue
                self._step(m.get("cmds", []), before, after)
                steps += 1
        return steps

    def _step(self, cmds, before, after) -> None:
        self._apply(cmds)
        w = self.game.world
        if before:
            before(w)
        self.game.step()
        if after:
            after(w)
        self.n += 1

    def close(self) -> None:
        self.conn.close("вышел")
