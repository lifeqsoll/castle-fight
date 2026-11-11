"""Пиксельный «ремесленный» набор UI: дерево, пергамент, камень, ленты, полоски.

Всё рисуется процедурно в половинном разрешении и увеличивается ×2 без сглаживания —
получаются «крупные пиксели», как у спрайтов. Поверхности кэшируются по размеру.
Цвета — тёплая палитра из чернил, дерева и бумаги вместо тёмных прозрачных плашек.
"""

from __future__ import annotations

import random
from typing import Callable, Optional

import pygame

# --- палитра -------------------------------------------------------------
INK = (34, 22, 14)
INK_SOFT = (62, 40, 24)
WOOD_DARK = (74, 46, 28)
WOOD = (110, 70, 40)
WOOD_MID = (138, 90, 52)
WOOD_LIGHT = (170, 116, 68)
WOOD_HI = (200, 146, 88)
PAPER = (238, 220, 178)
PAPER_MID = (222, 198, 150)
PAPER_DARK = (196, 166, 116)
PAPER_EDGE = (160, 124, 80)
TEXT_INK = (60, 36, 20)
TEXT_INK_SOFT = (112, 80, 52)
CREAM = (248, 234, 204)
STONE_DARK = (70, 72, 80)
STONE = (112, 114, 122)
STONE_LIGHT = (150, 152, 158)
STONE_HI = (184, 186, 190)
RED = (180, 50, 38)
RED_DARK = (120, 30, 24)
BLUE = (52, 98, 170)
BLUE_DARK = (30, 56, 108)
GOLD = (236, 186, 58)
GOLD_DARK = (164, 112, 26)
GREEN = (92, 156, 58)
GREEN_DARK = (52, 100, 34)
IRON = (96, 92, 90)

_cache: dict[tuple, pygame.Surface] = {}


def _cached(key: tuple, make: Callable[[], pygame.Surface]) -> pygame.Surface:
    s = _cache.get(key)
    if s is None:
        if len(_cache) > 500:
            _cache.clear()
        s = make()
        _cache[key] = s
    return s


def _up(small: pygame.Surface, size: tuple[int, int]) -> pygame.Surface:
    """×2 без сглаживания, затем точная подгонка до size (нечётные размеры)."""
    big = pygame.transform.scale(small, (small.get_width() * 2, small.get_height() * 2))
    if big.get_size() != size:
        out = pygame.Surface(size, pygame.SRCALPHA)
        out.blit(big, (0, 0))
        return out
    return big


def shade(c, k: float):
    if k >= 1:
        return tuple(min(255, int(v + (255 - v) * (k - 1))) for v in c[:3])
    return tuple(int(v * k) for v in c[:3])


def _cut_corners(s: pygame.Surface, n: int = 1) -> None:
    w, h = s.get_size()
    for i in range(n):
        for j in range(n - i):
            for x, y in ((i, j), (w - 1 - i, j), (i, h - 1 - j), (w - 1 - i, h - 1 - j)):
                s.set_at((x, y), (0, 0, 0, 0))


def _outline_rect(s: pygame.Surface, color, cut: int = 1) -> None:
    """Контур 1px с «срезанными» углами (пиксельное скругление)."""
    w, h = s.get_size()
    pygame.draw.line(s, color, (cut, 0), (w - 1 - cut, 0))
    pygame.draw.line(s, color, (cut, h - 1), (w - 1 - cut, h - 1))
    pygame.draw.line(s, color, (0, cut), (0, h - 1 - cut))
    pygame.draw.line(s, color, (w - 1, cut), (w - 1, h - 1 - cut))
    if cut:
        s.set_at((1, 1), color)
        s.set_at((w - 2, 1), color)
        s.set_at((1, h - 2), color)
        s.set_at((w - 2, h - 2), color)


# --- дерево ----------------------------------------------------------------


def _wood_small(w: int, h: int, base, plank_h: int, seed: int, vertical: bool = False, nails: bool = True) -> pygame.Surface:
    rnd = random.Random(seed)
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    s.fill((*base, 255))
    dark = shade(base, 0.72)
    light = shade(base, 1.18)
    # доски
    n = max(1, round((w if vertical else h) / plank_h))
    size = (w if vertical else h) / n
    for i in range(n):
        a = int(i * size)
        b = int((i + 1) * size)
        tone = shade(base, rnd.uniform(0.9, 1.08))
        if vertical:
            pygame.draw.rect(s, tone, (a, 0, b - a, h))
        else:
            pygame.draw.rect(s, tone, (0, a, w, b - a))
        # волокна
        for _ in range(max(2, (w if not vertical else h) // 9)):
            if vertical:
                x = rnd.randint(a + 1, max(a + 1, b - 2))
                y0 = rnd.randint(1, max(1, h - 4))
                pygame.draw.line(s, shade(tone, 0.84), (x, y0), (x, min(h - 2, y0 + rnd.randint(3, 10))))
            else:
                y = rnd.randint(a + 1, max(a + 1, b - 2))
                x0 = rnd.randint(1, max(1, w - 4))
                pygame.draw.line(s, shade(tone, 0.84), (x0, y), (min(w - 2, x0 + rnd.randint(4, 14)), y))
        # сучок
        if rnd.random() < 0.35 and (b - a) >= 5:
            if vertical:
                c = (rnd.randint(a + 2, max(a + 2, b - 3)), rnd.randint(3, max(3, h - 4)))
            else:
                c = (rnd.randint(3, max(3, w - 4)), rnd.randint(a + 2, max(a + 2, b - 3)))
            pygame.draw.ellipse(s, dark, (c[0] - 2, c[1] - 1, 4, 3))
        # шов и блик доски
        if i > 0:
            if vertical:
                pygame.draw.line(s, INK_SOFT, (a, 1), (a, h - 2))
                pygame.draw.line(s, light, (a + 1, 1), (a + 1, h - 2))
            else:
                pygame.draw.line(s, INK_SOFT, (1, a), (w - 2, a))
                pygame.draw.line(s, light, (1, a + 1), (w - 2, a + 1))
    # фаска: светлый верх/лево, тёмный низ/право
    pygame.draw.line(s, light, (1, 1), (w - 2, 1))
    pygame.draw.line(s, light, (1, 1), (1, h - 2))
    pygame.draw.line(s, dark, (1, h - 2), (w - 2, h - 2))
    pygame.draw.line(s, dark, (w - 2, 1), (w - 2, h - 2))
    _outline_rect(s, INK)
    _cut_corners(s, 1)
    if nails and w >= 14 and h >= 10:
        for x, y in ((3, 3), (w - 4, 3), (3, h - 4), (w - 4, h - 4)):
            s.set_at((x, y), (60, 58, 56))
            pygame.draw.rect(s, (52, 50, 50), (x - 1, y - 1, 2, 2))
            s.set_at((x - 1, y - 1), (150, 146, 140))
    return s


def wood_panel(size: tuple[int, int], tone=WOOD_MID, plank: int = 12, nails: bool = True, vertical: bool = False, seed: int = 0) -> pygame.Surface:
    """Деревянная панель из досок, с гвоздями по углам."""
    w, h = size

    def make():
        return _up(_wood_small(max(4, (w + 1) // 2), max(4, (h + 1) // 2), tone, plank, seed + w * 7 + h * 13, vertical, nails), size)

    return _cached(("wood", size, tone, plank, nails, vertical, seed), make)


def wood_button(size: tuple[int, int], state: str = "normal", accent: Optional[tuple] = None) -> pygame.Surface:
    """Табличка-кнопка. state: normal / hover / pressed / disabled. accent — цветная краска."""

    def make():
        w, h = (size[0] + 1) // 2, (size[1] + 1) // 2
        base = accent if accent is not None else WOOD_MID
        if state == "hover":
            base = shade(base, 1.12)
        elif state == "pressed":
            base = shade(base, 0.88)
        elif state == "disabled":
            base = (112, 100, 90)
        s = _wood_small(w, h, base, max(6, h // 2 + 1), 11 + w, False, nails=False)
        if accent is not None and state != "disabled":
            # «краска» поверх дерева: оставляем текстуру, сверху тонкая светлая полоса
            pygame.draw.line(s, shade(base, 1.35), (2, 2), (w - 3, 2))
        if state == "pressed":
            pygame.draw.line(s, shade(base, 0.6), (2, 2), (w - 3, 2))
        # тень-«ножка» снизу (видна, когда не нажата)
        out = pygame.Surface((w, h + 2), pygame.SRCALPHA)
        if state != "pressed":
            sh = pygame.Surface((w, h), pygame.SRCALPHA)
            sh.fill((*INK, 255))
            _cut_corners(sh, 1)
            out.blit(sh, (0, 2))
            out.blit(s, (0, 0))
        else:
            out.blit(s, (0, 2))
        return _up(out, (size[0], size[1] + 4))

    return _cached(("wbtn", size, state, accent), make)


# --- пергамент ---------------------------------------------------------------


def parchment(size: tuple[int, int], seed: int = 0, tone=PAPER, edge: bool = True) -> pygame.Surface:
    """Лист пергамента: тёплая бумага, неровный подкопчённый край, крапинки, чернильный контур."""
    w0, h0 = size

    def make():
        w, h = max(6, (w0 + 1) // 2), max(6, (h0 + 1) // 2)
        rnd = random.Random(seed * 31 + w * 3 + h)
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        s.fill((*tone, 255))
        mid = shade(tone, 0.93)
        dark = shade(tone, 0.82)
        # пятна и крапинки
        for _ in range(w * h // 60):
            x, y = rnd.randrange(w), rnd.randrange(h)
            s.set_at((x, y), mid if rnd.random() < 0.7 else dark)
        for _ in range(max(1, w * h // 900)):
            cx, cy = rnd.randrange(w), rnd.randrange(h)
            r = rnd.randint(3, 7)
            pygame.draw.ellipse(s, mid, (cx - r, cy - r // 2, r * 2, r))
        # подкопчённый край: 2 полосы
        if edge:
            for i, c in ((1, dark), (2, mid)):
                pygame.draw.rect(s, c, (i, i, w - 2 * i, h - 2 * i), 1)
            # неровности края
            for x in range(2, w - 2):
                if rnd.random() < 0.18:
                    s.set_at((x, 1 if rnd.random() < 0.5 else h - 2), PAPER_EDGE)
            for y in range(2, h - 2):
                if rnd.random() < 0.18:
                    s.set_at((1 if rnd.random() < 0.5 else w - 2, y), PAPER_EDGE)
        _outline_rect(s, INK_SOFT)
        _cut_corners(s, 1)
        return _up(s, size)

    return _cached(("paper", size, seed, tone, edge), make)


def scroll(size: tuple[int, int], seed: int = 0) -> pygame.Surface:
    """Свиток: пергамент с деревянными валиками сверху и снизу."""
    w0, h0 = size

    def make():
        out = pygame.Surface(size, pygame.SRCALPHA)
        roll = 16
        paper = parchment((w0 - 16, h0 - roll), seed)
        out.blit(paper, (8, roll // 2))
        for y in (0, h0 - roll):
            r = wood_panel((w0, roll), WOOD_LIGHT, plank=16, nails=False, seed=y)
            out.blit(r, (0, y))
            # ручки
            for x in (0, w0 - 8):
                pygame.draw.rect(out, INK, (x, y + 2, 8, roll - 4))
                pygame.draw.rect(out, WOOD_DARK, (x + 2, y + 4, 4, roll - 8))
        return out

    return _cached(("scroll", size, seed), make)


# --- камень ------------------------------------------------------------------


def stone_frame(size: tuple[int, int], seed: int = 0, fill=None) -> pygame.Surface:
    """Каменная рамка из блоков (внутри — fill или прозрачно)."""
    w0, h0 = size

    def make():
        w, h = max(6, (w0 + 1) // 2), max(6, (h0 + 1) // 2)
        rnd = random.Random(seed + w * 5 + h)
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        t = 4  # толщина рамки (в мелких пикселях)
        pygame.draw.rect(s, STONE, (0, 0, w, h))
        if fill is not None:
            pygame.draw.rect(s, fill, (t, t, w - 2 * t, h - 2 * t))
        else:
            pygame.draw.rect(s, (0, 0, 0, 0), (t, t, w - 2 * t, h - 2 * t))
        # блоки по периметру
        x = 0
        while x < w:
            bw = rnd.randint(6, 11)
            for y0 in (0, h - t):
                c = shade(STONE, rnd.uniform(0.9, 1.1))
                pygame.draw.rect(s, c, (x, y0, bw, t))
                pygame.draw.line(s, STONE_HI, (x, y0), (x + bw - 2, y0))
                pygame.draw.line(s, STONE_DARK, (x + bw - 1, y0), (x + bw - 1, y0 + t - 1))
            x += bw
        y = t
        while y < h - t:
            bh = rnd.randint(5, 9)
            for x0 in (0, w - t):
                c = shade(STONE, rnd.uniform(0.9, 1.1))
                pygame.draw.rect(s, c, (x0, y, t, min(bh, h - t - y)))
                pygame.draw.line(s, STONE_DARK, (x0, y + bh - 1), (x0 + t - 1, y + bh - 1))
            y += bh
        # внутренний тёмный кант
        pygame.draw.rect(s, STONE_DARK, (t - 1, t - 1, w - 2 * t + 2, h - 2 * t + 2), 1)
        _outline_rect(s, INK)
        _cut_corners(s, 1)
        return _up(s, size)

    return _cached(("stone", size, seed, fill), make)


def plinth(size: tuple[int, int], state: str = "idle", seed: int = 0) -> pygame.Surface:
    """Каменная площадка под здание (вид чуть сверху): idle / hover / free / busy / drag."""
    w0, h0 = size

    def make():
        w, h = max(6, (w0 + 1) // 2), max(6, (h0 + 1) // 2)
        rnd = random.Random(seed)
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        top_h = h - 4
        base = {"idle": (128, 120, 104), "hover": (150, 142, 122), "free": (126, 150, 96),
                "busy": (150, 104, 92), "drag": (176, 150, 92)}.get(state, (128, 120, 104))
        # боковина
        pygame.draw.rect(s, shade(base, 0.62), (0, 3, w, h - 3))
        # верх из плит
        pygame.draw.rect(s, base, (0, 0, w, top_h))
        for _ in range(4):
            x = rnd.randint(2, w - 4)
            pygame.draw.line(s, shade(base, 0.85), (x, 1), (x + rnd.choice((-1, 1)), top_h - 2))
        pygame.draw.line(s, shade(base, 0.85), (1, top_h // 2), (w - 2, top_h // 2 + rnd.choice((-1, 0, 1))))
        for _ in range(w * h // 40):
            s.set_at((rnd.randrange(1, w - 1), rnd.randrange(1, top_h - 1)), shade(base, rnd.choice((0.9, 1.1))))
        pygame.draw.line(s, shade(base, 1.2), (1, 1), (w - 2, 1))
        _outline_rect(s, INK)
        pygame.draw.line(s, INK, (1, top_h), (w - 2, top_h))
        _cut_corners(s, 1)
        out = _up(s, size)
        return out

    return _cached(("plinth", size, state, seed), make)


# --- ленты, печати, полоски ------------------------------------------------------


def ribbon(size: tuple[int, int], color=RED) -> pygame.Surface:
    """Лента-баннер с раздвоенными хвостами."""
    w0, h0 = size

    def make():
        w, h = max(10, (w0 + 1) // 2), max(6, (h0 + 1) // 2)
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        tail = max(4, h // 2)
        dark = shade(color, 0.6)
        # хвосты
        for side in (0, 1):
            pts = [(0, 2), (tail + 2, 2), (tail + 2, h - 1), (0, h - 1), (tail // 2 + 1, (h + 1) // 2)]
            if side:
                pts = [(w - 1 - x, y) for x, y in pts]
            pygame.draw.polygon(s, dark, pts)
            pygame.draw.polygon(s, INK, pts, 1)
        body = pygame.Rect(tail, 0, w - 2 * tail, h - 2)
        pygame.draw.rect(s, color, body)
        pygame.draw.line(s, shade(color, 1.3), (body.x + 1, 1), (body.right - 2, 1))
        pygame.draw.line(s, dark, (body.x + 1, body.bottom - 2), (body.right - 2, body.bottom - 2))
        pygame.draw.rect(s, INK, body, 1)
        return _up(s, size)

    return _cached(("ribbon", size, color), make)


def seal(radius: int, color=RED) -> pygame.Surface:
    """Сургучная печать."""

    def make():
        r = max(4, radius // 2)
        s = pygame.Surface((r * 2 + 2, r * 2 + 2), pygame.SRCALPHA)
        c = (r + 1, r + 1)
        rnd = random.Random(r)
        pts = []
        import math

        for i in range(16):
            a = i / 16 * 2 * math.pi
            rr = r + (1 if i % 2 else 0) - rnd.choice((0, 1))
            pts.append((c[0] + math.cos(a) * rr, c[1] + math.sin(a) * rr))
        pygame.draw.polygon(s, color, pts)
        pygame.draw.polygon(s, INK, pts, 1)
        pygame.draw.circle(s, shade(color, 0.75), c, max(2, r - 3), 1)
        # оттиск: башенка замка
        k = max(2, r // 3)
        dark = shade(color, 0.62)
        pygame.draw.rect(s, dark, (c[0] - k, c[1] - k // 2, 2 * k + 1, k + k // 2 + 1))
        for i in range(-k, k + 1, max(2, k // 2 + 1)):
            pygame.draw.rect(s, dark, (c[0] + i, c[1] - k, 1 + (k > 3), k // 2 + 1))
        pygame.draw.line(s, shade(color, 1.3), (c[0] - r + 3, c[1] - 2), (c[0] - r // 2, c[1] - r + 3))
        return pygame.transform.scale(s, (s.get_width() * 2, s.get_height() * 2))

    return _cached(("seal", radius, color), make)


def pixel_bar(screen: pygame.Surface, rect: pygame.Rect, ratio: float, color, *, ghost: Optional[float] = None,
              back=(52, 34, 24), segments: int = 0) -> None:
    """Пиксельная полоска: чернильный контур, блик сверху, тень снизу, «отставший» урон."""
    ratio = max(0.0, min(1.0, ratio))
    r = pygame.Rect(rect)
    pygame.draw.rect(screen, INK, r)
    inner = r.inflate(-4, -4)
    pygame.draw.rect(screen, back, inner)
    if ghost is not None and ghost > ratio:
        g = inner.copy()
        g.w = int(inner.w * min(1.0, ghost))
        pygame.draw.rect(screen, (246, 226, 180), g)
    if ratio > 0:
        f = inner.copy()
        f.w = max(2, int(inner.w * ratio))
        pygame.draw.rect(screen, color, f)
        if f.h >= 4:
            pygame.draw.rect(screen, shade(color, 1.35), (f.x, f.y, f.w, max(2, f.h // 4)))
            pygame.draw.rect(screen, shade(color, 0.7), (f.x, f.bottom - 2, f.w, 2))
    if segments > 1:
        for i in range(1, segments):
            x = inner.x + inner.w * i // segments
            pygame.draw.line(screen, (*INK, 255), (x, inner.y), (x, inner.bottom - 1))


def gold_coin(size: int) -> pygame.Surface:
    """Пиксельная монетка (если нет картинки)."""

    def make():
        r = max(3, size // 4)
        s = pygame.Surface((r * 2 + 1, r * 2 + 1), pygame.SRCALPHA)
        pygame.draw.circle(s, GOLD_DARK, (r, r), r)
        pygame.draw.circle(s, GOLD, (r, r - 0), r - 1)
        pygame.draw.circle(s, shade(GOLD, 1.3), (r - 1, r - 1), max(1, r - 3), 1)
        pygame.draw.circle(s, INK, (r, r), r, 1)
        return pygame.transform.scale(s, (size, size))

    return _cached(("coin", size), make)


def key_cap(label_surf: pygame.Surface, light: bool = True) -> pygame.Surface:
    """Маленькая «клавиша» с подписью (для горячих клавиш)."""
    w = max(18, label_surf.get_width() + 10)
    h = 18
    s = pygame.Surface((w, h + 2), pygame.SRCALPHA)
    pygame.draw.rect(s, INK, (0, 2, w, h))
    pygame.draw.rect(s, INK, (0, 0, w, h))
    pygame.draw.rect(s, PAPER if light else WOOD_LIGHT, (2, 2, w - 4, h - 4))
    pygame.draw.line(s, shade(PAPER if light else WOOD_LIGHT, 0.8), (2, h - 3), (w - 3, h - 3))
    s.blit(label_surf, label_surf.get_rect(center=(w // 2, h // 2)))
    return s
