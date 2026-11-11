"""Виджеты в «ремесленном» стиле: деревянные кнопки-таблички, пергаментные подсказки,
пиксельные полоски. Палитра и процедурные текстуры — в ui/kit.py."""

from __future__ import annotations

from typing import Callable, Optional, Sequence

import pygame

from castlefight.ui import kit
from castlefight.ui.text import Font, make_font, outline_text, shadow_text, wrap
from castlefight.ui.theme import HEIGHT, WIDTH

_cache: dict[tuple, pygame.Surface] = {}


def _cached(key: tuple, make: Callable[[], pygame.Surface]) -> pygame.Surface:
    s = _cache.get(key)
    if s is None:
        if len(_cache) > 400:
            _cache.clear()
        s = make()
        _cache[key] = s
    return s


def lerp_color(a, b, t: float):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(len(a)))


shade = kit.shade


def gradient_rect(size: tuple[int, int], top, bottom, radius: int = 0, alpha: int = 255) -> pygame.Surface:
    """Вертикальный градиент (для мягких затемнений фона, не для панелей)."""

    def make() -> pygame.Surface:
        w, h = size
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        for y in range(h):
            c = lerp_color(top, bottom, y / max(1, h - 1))
            a = alpha if not isinstance(alpha, tuple) else int(alpha[0] + (alpha[1] - alpha[0]) * y / max(1, h - 1))
            pygame.draw.line(surf, (*c[:3], a), (0, y), (w, y))
        return surf

    return _cached(("grad", size, tuple(top), tuple(bottom), radius, alpha), make)


def hgradient(size: tuple[int, int], color, a0: int, a1: int) -> pygame.Surface:
    """Горизонтальное затемнение (alpha a0 слева → a1 справа)."""

    def make() -> pygame.Surface:
        w, h = size
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        for x in range(w):
            t = x / max(1, w - 1)
            pygame.draw.line(surf, (*color, int(a0 + (a1 - a0) * t)), (x, 0), (x, h))
        return surf

    return _cached(("hgrad", size, tuple(color), a0, a1), make)


def drop_shadow(screen: pygame.Surface, rect: pygame.Rect, off: int = 4, alpha: int = 90) -> None:
    """Жёсткая пиксельная тень (без размытия)."""
    s = _cached(("dsh", rect.size, alpha), lambda: _solid(rect.size, (*kit.INK, alpha)))
    screen.blit(s, (rect.x + off, rect.y + off))


def _solid(size, rgba) -> pygame.Surface:
    s = pygame.Surface(size, pygame.SRCALPHA)
    s.fill(rgba)
    return s


def draw_panel(screen: pygame.Surface, rect: pygame.Rect, kind: str = "paper", *, shadow: bool = True, seed: int = 0, **_ignored) -> None:
    """Панель: paper (пергамент), wood (доски), stone (каменная рамка с тёмным деревом)."""
    rect = pygame.Rect(rect)
    if shadow:
        drop_shadow(screen, rect)
    if kind == "wood":
        screen.blit(kit.wood_panel(rect.size, seed=seed), rect.topleft)
    elif kind == "darkwood":
        screen.blit(kit.wood_panel(rect.size, tone=kit.WOOD, seed=seed), rect.topleft)
    elif kind == "stone":
        screen.blit(kit.stone_frame(rect.size, seed=seed, fill=kit.WOOD_DARK), rect.topleft)
    else:
        screen.blit(kit.parchment(rect.size, seed=seed), rect.topleft)


def draw_bar(screen: pygame.Surface, rect: pygame.Rect, ratio: float, color, *, ghost: Optional[float] = None, **_ignored) -> None:
    kit.pixel_bar(screen, rect, ratio, color, ghost=ghost)


class Button:
    """Кнопка-табличка. kind: primary (красная краска), go (зелёная), secondary (дерево)."""

    ACCENTS = {"primary": kit.RED, "go": kit.GREEN, "blue": kit.BLUE, "secondary": None, "danger": kit.RED}

    def __init__(self, rect: pygame.Rect, label: str, *, kind: str = "secondary", font: Optional[Font] = None, sub: str = "", key: str = "") -> None:
        self.rect = pygame.Rect(rect)
        self.label = label
        self.kind = kind
        self.font = font or make_font(22, "title")
        self.sub = sub
        self.key = key
        self.enabled = True
        self.pressed = False
        self.selected = False

    def hit(self, pos) -> bool:
        return self.enabled and self.rect.collidepoint(pos)

    def draw(self, screen: pygame.Surface, mouse: tuple[int, int]) -> None:
        hover = self.enabled and self.rect.collidepoint(mouse)
        down = self.pressed and hover
        state = "disabled" if not self.enabled else ("pressed" if down else ("hover" if hover else "normal"))
        accent = self.ACCENTS.get(self.kind)
        if self.selected and accent is None:
            accent = kit.GOLD_DARK
        img = kit.wood_button(self.rect.size, state, accent)
        screen.blit(img, (self.rect.x, self.rect.y))
        dy = 4 if down else 0
        cy = self.rect.centery + dy
        light = accent is not None or True
        col = kit.CREAM if light else kit.TEXT_INK
        if not self.enabled:
            col = (196, 184, 168)
        t = outline_text(self.font, self.label, col, kit.INK, 2)
        if self.sub:
            s = make_font(14, "bold").render(self.sub, True, shade(col, 0.85))
            total = t.get_height() + s.get_height() - 4
            y = cy - total // 2
            screen.blit(t, (self.rect.centerx - t.get_width() // 2, y - 2))
            screen.blit(s, (self.rect.centerx - s.get_width() // 2, y + t.get_height() - 6))
        else:
            screen.blit(t, (self.rect.centerx - t.get_width() // 2, cy - t.get_height() // 2 - 1))
        if self.key:
            kf = make_font(8, "pixel").render(self.key, False, kit.TEXT_INK)
            cap = kit.key_cap(kf)
            screen.blit(cap, (self.rect.right - cap.get_width() - 6, self.rect.y + 6 + dy))


def draw_tooltip(
    screen: pygame.Surface,
    anchor: tuple[int, int],
    title: str,
    lines: Sequence[tuple[str, tuple]],
    *,
    width: int = 300,
    title_color=kit.TEXT_INK,
    above: bool = True,
) -> pygame.Rect:
    """Подсказка-записка на пергаменте: заголовок + строки (текст, цвет). Не вылезает за экран."""
    tf = make_font(19, "title")
    bf = make_font(15, "bold")
    wrapped: list[tuple[str, tuple]] = []
    for text, color in lines:
        if text == "-":
            wrapped.append(("-", color))
            continue
        for ln in wrap(bf, text, width - 28):
            wrapped.append((ln, color))
    lh = bf.height() + 1
    h = 14 + tf.height() + 4 + sum(10 if t == "-" else lh for t, _ in wrapped) + 12
    x = anchor[0] - width // 2
    y = anchor[1] - h - 8 if above else anchor[1] + 8
    x = max(6, min(WIDTH - width - 6, x))
    y = max(6, min(HEIGHT - h - 6, y))
    rect = pygame.Rect(x, y, width, h)
    drop_shadow(screen, rect, 4, 80)
    screen.blit(kit.parchment(rect.size, seed=3), rect.topleft)
    screen.blit(tf.render(title, True, title_color), (x + 14, y + 10))
    cy = y + 12 + tf.height() + 2
    for text, color in wrapped:
        if text == "-":
            for xx in range(x + 14, x + width - 14, 6):
                pygame.draw.line(screen, kit.PAPER_EDGE, (xx, cy + 4), (xx + 2, cy + 4), 2)
            cy += 10
            continue
        screen.blit(bf.render(text, True, color), (x + 14, cy))
        cy += lh
    return rect


def blit_center(screen: pygame.Surface, surf: pygame.Surface, cx: int, y: int) -> None:
    screen.blit(surf, (cx - surf.get_width() // 2, y))


def title_text(text: str, size: int, color=kit.CREAM) -> pygame.Surface:
    """Заголовок: брусковый шрифт, чернильная обводка, твёрдая тень вниз."""
    f = make_font(size, "title")
    return _cached(("title", text, size, tuple(color)), lambda: _hard_shadow(outline_text(f, text, color, kit.INK, 3), 3))


def pixel_title(text: str, size: int = 32, color=kit.CREAM, outline=kit.INK, depth: int = 4) -> pygame.Surface:
    """Пиксельный заголовок (Press Start 2P) с «объёмом» вниз."""
    f = make_font(size, "pixel")

    def make() -> pygame.Surface:
        base = f.render(text, False, color)
        ol = f.render(text, False, outline)
        dep = f.render(text, False, shade(outline, 1.0))
        px = max(2, size // 8)
        w, h = base.get_width() + px * 2, base.get_height() + px * 2 + depth
        out = pygame.Surface((w, h), pygame.SRCALPHA)
        for d in range(depth, 0, -1):
            out.blit(dep, (px, px + d))
        for dx in (-px, 0, px):
            for dy in (-px, 0, px):
                out.blit(ol, (px + dx, px + dy))
        out.blit(base, (px, px))
        return out

    return _cached(("ptitle", text, size, tuple(color), tuple(outline), depth), make)


def _hard_shadow(s: pygame.Surface, d: int) -> pygame.Surface:
    out = pygame.Surface((s.get_width(), s.get_height() + d), pygame.SRCALPHA)
    sh = s.copy()
    sh.fill((*kit.INK, 255), special_flags=pygame.BLEND_RGBA_MIN)
    sh.set_alpha(150)
    out.blit(sh, (0, d))
    out.blit(s, (0, 0))
    return out


def label(text: str, size: int = 16, color=kit.TEXT_INK, kind: str = "bold", shadow: bool = False) -> pygame.Surface:
    f = make_font(size, kind)
    return shadow_text(f, text, color) if shadow else f.render(text, True, color)
