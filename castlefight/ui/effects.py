"""Простые эффекты боя: искры, пыль смерти, снаряды, всплывающее золото."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

import pygame

from castlefight.ui.text import make_font, outline_text


@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    life: float
    max_life: float
    color: tuple
    size: float
    gravity: float = 0.0
    soft: bool = False  # дым: круглый и полупрозрачный


@dataclass
class Projectile:
    x0: float
    y0: float
    x1: float
    y1: float
    t: float
    dur: float
    kind: str  # arrow | magic | ball | bolt
    color: tuple


@dataclass
class Floater:
    x: float
    y: float
    surf: pygame.Surface
    life: float
    max_life: float


@dataclass
class Ring:
    """Ударная волна / след удара: расширяющийся эллипс."""

    x: float
    y: float
    r0: float
    r1: float
    life: float
    max_life: float
    color: tuple
    flat: float = 0.35  # сплюснутость (вид сбоку на землю)


@dataclass
class Slash:
    x: float
    y: float
    life: float
    max_life: float
    flip: bool


@dataclass
class Corpse:
    surf: pygame.Surface
    x: float
    y: float
    life: float
    max_life: float


class Effects:
    def __init__(self, gold_icon: pygame.Surface) -> None:
        self.parts: list[Particle] = []
        self.proj: list[Projectile] = []
        self.floats: list[Floater] = []
        self.corpses: list[Corpse] = []
        self.rings: list[Ring] = []
        self.slashes: list[Slash] = []
        self.scorch: list[Ring] = []  # подпалины на земле после бомбы
        self.shake = 0.0
        self.flashes: list[list[float]] = []
        self.gold_icon = gold_icon
        self.rng = random.Random(7)

    # --- спавн ------------------------------------------------------------

    def hit(self, x: float, y: float, color=(255, 230, 170), n: int = 5) -> None:
        r = self.rng
        for _ in range(n):
            a = r.uniform(0, math.tau)
            sp = r.uniform(40, 140)
            self.parts.append(Particle(x, y, math.cos(a) * sp, math.sin(a) * sp - 30, 0.25, 0.25, color, r.uniform(1.5, 3), 300))
        if len(self.parts) > 700:
            del self.parts[:200]

    def death(self, surf: pygame.Surface, x: float, y: float, team_color) -> None:
        r = self.rng
        self.corpses.append(Corpse(surf.copy(), x, y, 0.55, 0.55))
        for _ in range(12):
            a = r.uniform(math.pi, math.tau)
            sp = r.uniform(30, 110)
            c = r.choice([(200, 190, 170), (150, 140, 128), team_color])
            self.parts.append(Particle(x + r.uniform(-10, 10), y - r.uniform(0, 20), math.cos(a) * sp, math.sin(a) * sp, 0.6, 0.6, c, r.uniform(2, 4.5), 120))

    def smoke(self, x: float, y: float, fire: bool = False) -> None:
        r = self.rng
        c = r.choice([(70, 66, 64), (96, 90, 86), (54, 50, 50)])
        self.parts.append(Particle(x + r.uniform(-30, 30), y, r.uniform(-8, 8), r.uniform(-40, -20), 1.6, 1.6, c, r.uniform(5, 9), -4))
        if fire:
            self.parts.append(Particle(x + r.uniform(-25, 25), y + 10, r.uniform(-6, 6), r.uniform(-50, -30), 0.5, 0.5, r.choice([(255, 150, 40), (255, 200, 80)]), r.uniform(3, 5), 0))

    def gold(self, x: float, y: float, amount: int) -> None:
        f = make_font(18, "bold")
        txt = outline_text(f, f"+{amount}", (255, 214, 90), (40, 26, 6), 2)
        ic = pygame.transform.smoothscale(self.gold_icon, (18, 18))
        s = pygame.Surface((ic.get_width() + 2 + txt.get_width(), max(ic.get_height(), txt.get_height())), pygame.SRCALPHA)
        s.blit(ic, (0, (s.get_height() - ic.get_height()) // 2))
        s.blit(txt, (ic.get_width() + 2, 0))
        self.floats.append(Floater(x - s.get_width() / 2, y, s, 1.2, 1.2))

    def text(self, x: float, y: float, text: str, color) -> None:
        f = make_font(16, "bold")
        s = outline_text(f, text, color, (20, 10, 8), 2).copy()
        self.floats.append(Floater(x - s.get_width() / 2, y, s, 0.9, 0.9))

    def slash(self, x: float, y: float) -> None:
        """След удара мечом игрока."""
        self.slashes.append(Slash(x, y, 0.22, 0.22, self.rng.random() < 0.5))
        self.hit(x, y, (255, 244, 210), 6)

    def explosion(self, x: float, y: float, radius: float) -> None:
        """Взрыв бомбы: вспышка, огонь, дым, комья земли, ударная волна, тряска."""
        r = self.rng
        self.rings.append(Ring(x, y, 10, radius * 1.25, 0.5, 0.5, (255, 236, 170)))
        self.rings.append(Ring(x, y, 6, radius * 0.85, 0.35, 0.35, (255, 160, 60)))
        self.scorch.append(Ring(x, y, radius * 0.55, radius * 0.55, 6.0, 6.0, (40, 30, 22)))
        for _ in range(70):
            a = r.uniform(math.pi * 1.05, math.tau - 0.05)
            sp = r.uniform(90, 420)
            c = r.choice([(255, 220, 120), (255, 160, 50), (240, 100, 30), (255, 250, 210)])
            self.parts.append(Particle(x + r.uniform(-8, 8), y - 10, math.cos(a) * sp, math.sin(a) * sp * 1.2, 0.6, 0.6, c, r.uniform(3, 7), 520))
        for _ in range(18):
            a = r.uniform(math.pi * 1.1, math.tau - 0.1)
            sp = r.uniform(60, 220)
            self.parts.append(Particle(x + r.uniform(-20, 20), y, math.cos(a) * sp, math.sin(a) * sp, 0.8, 0.8, r.choice([(96, 70, 44), (70, 52, 34)]), r.uniform(2, 4), 700))
        for _ in range(16):
            self.parts.append(Particle(x + r.uniform(-radius * 0.5, radius * 0.5), y - r.uniform(0, 30), r.uniform(-20, 20), r.uniform(-60, -25), 1.4, 1.4, r.choice([(80, 74, 70), (110, 102, 96), (60, 56, 54)]), r.uniform(8, 14), -6, True))
        self.flashes.append([x, y - 26, 0.26, 0.26, max(56.0, radius * 1.1)])
        self.shake = max(self.shake, 0.35)

    def shoot(self, x0, y0, x1, y1, kind: str, color=(255, 255, 255)) -> None:
        dist = math.hypot(x1 - x0, y1 - y0)
        speed = {"arrow": 900, "magic": 650, "ball": 700, "bolt": 1100}.get(kind, 800)
        self.proj.append(Projectile(x0, y0, x1, y1, 0.0, max(0.06, dist / speed), kind, color))

    # --- шаг и отрисовка -------------------------------------------------

    def update(self, dt: float) -> None:
        for p in self.parts:
            p.life -= dt
            p.x += p.vx * dt
            p.y += p.vy * dt
            p.vy += p.gravity * dt
        self.parts = [p for p in self.parts if p.life > 0]
        done: list[Projectile] = []
        for pr in self.proj:
            pr.t += dt
            if pr.t >= pr.dur:
                done.append(pr)
        for pr in done:
            c = (140, 220, 255) if pr.kind == "magic" else (255, 220, 150)
            if pr.kind == "magic":
                c = pr.color
            self.hit(pr.x1, pr.y1, c, 6 if pr.kind != "arrow" else 3)
        self.proj = [p for p in self.proj if p.t < p.dur]
        for f in self.floats:
            f.life -= dt
            f.y -= 34 * dt
        self.floats = [f for f in self.floats if f.life > 0]
        for c in self.corpses:
            c.life -= dt
        self.corpses = [c for c in self.corpses if c.life > 0]
        for g in self.rings:
            g.life -= dt
        self.rings = [g for g in self.rings if g.life > 0]
        for g in self.scorch:
            g.life -= dt
        self.scorch = [g for g in self.scorch if g.life > 0]
        for sl in self.slashes:
            sl.life -= dt
        self.slashes = [sl for sl in self.slashes if sl.life > 0]
        self.shake = max(0.0, self.shake - dt)
        for f in self.flashes:
            f[2] -= dt
        self.flashes = [f for f in self.flashes if f[2] > 0]

    def shake_offset(self) -> tuple[int, int]:
        if self.shake <= 0:
            return (0, 0)
        k = self.shake / 0.35
        return (int(self.rng.uniform(-6, 6) * k), int(self.rng.uniform(-4, 4) * k))

    def draw_ground(self, screen: pygame.Surface) -> None:
        """Подпалины — под юнитами."""
        for g in self.scorch:
            k = min(1.0, g.life / 1.5)
            w, h = int(g.r1 * 2), int(g.r1 * 2 * g.flat)
            if w < 4 or h < 2:
                continue
            s = pygame.Surface((w, h), pygame.SRCALPHA)
            pygame.draw.ellipse(s, (*g.color, int(110 * k)), s.get_rect())
            pygame.draw.ellipse(s, (*g.color, int(70 * k)), s.get_rect().inflate(-w // 3, -h // 3))
            screen.blit(s, (g.x - w / 2, g.y - h / 2))

    def draw_under(self, screen: pygame.Surface) -> None:
        for c in self.corpses:
            k = c.life / c.max_life
            s = c.surf
            s.set_alpha(int(220 * k))
            sink = (1 - k) * 10
            screen.blit(s, s.get_rect(midbottom=(int(c.x), int(c.y + sink))))

    def draw_over(self, screen: pygame.Surface) -> None:
        for pr in self.proj:
            k = pr.t / pr.dur
            x = pr.x0 + (pr.x1 - pr.x0) * k
            arc = math.sin(k * math.pi) * (26 if pr.kind in ("arrow", "ball") else 8)
            y = pr.y0 + (pr.y1 - pr.y0) * k - arc
            if pr.kind == "arrow":
                k2 = min(1.0, k + 0.06)
                x2 = pr.x0 + (pr.x1 - pr.x0) * k2
                y2 = pr.y0 + (pr.y1 - pr.y0) * k2 - math.sin(k2 * math.pi) * 26
                dx, dy = x2 - x, y2 - y
                n = math.hypot(dx, dy) or 1
                dx, dy = dx / n * 12, dy / n * 12
                pygame.draw.line(screen, (60, 40, 24), (x - dx, y - dy), (x + dx, y + dy), 2)
                pygame.draw.circle(screen, (230, 230, 230), (int(x + dx), int(y + dy)), 2)
            elif pr.kind == "magic":
                glow = pygame.Surface((22, 22), pygame.SRCALPHA)
                pygame.draw.circle(glow, (*pr.color[:3], 70), (11, 11), 11)
                pygame.draw.circle(glow, (*pr.color[:3], 160), (11, 11), 7)
                pygame.draw.circle(glow, (255, 255, 255, 230), (11, 11), 3)
                screen.blit(glow, (x - 11, y - 11))
            elif pr.kind == "ball":
                pygame.draw.circle(screen, (30, 28, 26), (int(x), int(y)), 5)
                pygame.draw.circle(screen, (110, 104, 96), (int(x) - 1, int(y) - 1), 2)
            else:  # bolt — выстрел замка
                pygame.draw.line(screen, (255, 240, 180), (x - 8, y - 2), (x + 8, y + 2), 3)
                pygame.draw.circle(screen, (255, 255, 230), (int(x), int(y)), 3)
        for g in self.rings:
            k = 1 - g.life / g.max_life
            rr = g.r0 + (g.r1 - g.r0) * (1 - (1 - k) ** 2)
            w, h = int(rr * 2), max(4, int(rr * 2 * g.flat))
            pygame.draw.ellipse(screen, g.color[:3], (g.x - w / 2, g.y - h / 2, w, h), max(1, int(5 * (1 - k)) + 1))
        for sl in self.slashes:
            k = 1 - sl.life / sl.max_life
            d = -1 if sl.flip else 1
            pts = [(sl.x - 22 * d + 44 * d * t, sl.y - 26 + 52 * t - math.sin(t * math.pi) * 10) for t in (0.0, 0.25, 0.5, 0.75, 1.0)]
            n = max(2, int(len(pts) * min(1.0, k * 2.2)))
            if n >= 2:
                pygame.draw.lines(screen, (40, 26, 16), False, pts[:n], 6)
                pygame.draw.lines(screen, (255, 250, 230), False, pts[:n], 3)
        for f in self.flashes:
            k = f[2] / f[3]
            rr = int(f[4] * (1.2 - 0.5 * k))
            s = pygame.Surface((rr * 2, rr * 2), pygame.SRCALPHA)
            pygame.draw.circle(s, (255, 200, 90, int(150 * k)), (rr, rr), rr)
            pygame.draw.circle(s, (255, 250, 220, int(230 * k)), (rr, rr), int(rr * 0.6))
            screen.blit(s, (f[0] - rr, f[1] - rr))
        for p in self.parts:
            k = p.life / p.max_life
            if p.soft:
                r = max(2, int(p.size * (1.4 - 0.6 * k)))
                s = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
                pygame.draw.circle(s, (*p.color[:3], int(170 * min(1.0, k * 1.5))), (r, r), r)
                screen.blit(s, (int(p.x) - r, int(p.y) - r))
                continue
            r = max(1, int(p.size * (0.5 + 0.5 * k)))
            # квадратные «пиксельные» частицы — в стиле спрайтов
            pygame.draw.rect(screen, p.color[:3], (int(p.x) - r, int(p.y) - r, r * 2, r * 2))
        for f in self.floats:
            k = f.life / f.max_life
            s = f.surf
            s.set_alpha(int(255 * k / 0.4) if k < 0.4 else 255)
            screen.blit(s, (int(f.x), int(f.y)))
