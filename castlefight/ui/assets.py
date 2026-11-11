"""Загрузка спрайтов (через Pillow: pygame без SDL_image) с запасной процедурной графикой.

Если какого-то PNG нет — рисуем простую фигуру нужного цвета, игра не падает.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Optional

import pygame

from castlefight.data.enums import Role
from castlefight.ui.theme import FACTION_COLORS, FACTION_KEYS, HEIGHT, ROLE_ORDER, WIDTH

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"

# высота юнита на экране = высота PNG * UNIT_SCALE (PNG уже в относительном масштабе листа)
UNIT_SCALE = 0.42
MINION_SCALE = 0.66  # миньоны — уменьшенный «ближник» фракции


def _load(name: str) -> Optional[pygame.Surface]:
    path = ASSETS_DIR / name
    if not path.exists():
        return None
    try:
        from PIL import Image

        img = Image.open(path).convert("RGBA")
        return pygame.image.frombytes(img.tobytes(), img.size, "RGBA").convert_alpha()
    except Exception:
        return None


def scale_to(surf: pygame.Surface, size: tuple[int, int]) -> pygame.Surface:
    return pygame.transform.smoothscale(surf, (max(1, size[0]), max(1, size[1])))


def fit(surf: pygame.Surface, w: int, h: int) -> pygame.Surface:
    k = min(w / surf.get_width(), h / surf.get_height())
    return scale_to(surf, (round(surf.get_width() * k), round(surf.get_height() * k)))


def fit_height(surf: pygame.Surface, h: int) -> pygame.Surface:
    k = h / surf.get_height()
    return scale_to(surf, (round(surf.get_width() * k), h))


# --- запасная графика ------------------------------------------------------


def _fallback_bg() -> pygame.Surface:
    s = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    for y in range(HEIGHT):
        if y < 380:
            c = (110 + y // 6, 170 + y // 10, 225)
        elif y < 400:
            c = (96, 150, 80)
        elif y < 470:
            c = (196, 160, 104)
        else:
            c = (90, 150, 70)
        pygame.draw.line(s, c, (0, y), (WIDTH, y))
    return s


def _fallback_castle(color) -> pygame.Surface:
    s = pygame.Surface((220, 200), pygame.SRCALPHA)
    stone, dark = (150, 150, 156), (70, 70, 78)
    pygame.draw.rect(s, stone, (20, 80, 180, 110), border_radius=4)
    for x in (20, 150):
        pygame.draw.rect(s, stone, (x, 40, 50, 150))
        pygame.draw.polygon(s, color, [(x - 6, 42), (x + 25, 0), (x + 56, 42)])
    pygame.draw.rect(s, (90, 60, 36), (90, 130, 40, 60), border_top_left_radius=20, border_top_right_radius=20)
    pygame.draw.rect(s, dark, (20, 80, 180, 110), 3, border_radius=4)
    return s


def _fallback_building(color, role: Role) -> pygame.Surface:
    s = pygame.Surface((110, 120), pygame.SRCALPHA)
    pygame.draw.ellipse(s, (70, 110, 50), (4, 96, 102, 22))
    body = {Role.MELEE: (20, 50, 70, 50), Role.RANGED: (35, 20, 40, 80), Role.SUMMON: (25, 45, 60, 55), Role.ULT: (12, 30, 86, 70)}[role]
    pygame.draw.rect(s, (160, 156, 150), body)
    x, y, w, h = body
    pygame.draw.polygon(s, color, [(x - 8, y + 4), (x + w // 2, y - 30), (x + w + 8, y + 4)])
    pygame.draw.rect(s, (40, 36, 34), body, 2)
    return s


def _fallback_unit(color, role: Role) -> pygame.Surface:
    h = {Role.ULT: 170, Role.MINION: 90}.get(role, 120)
    s = pygame.Surface((80, h), pygame.SRCALPHA)
    pygame.draw.ellipse(s, color, (14, h * 0.3, 52, h * 0.66))
    pygame.draw.circle(s, (236, 206, 170), (40, int(h * 0.22)), int(h * 0.14))
    pygame.draw.ellipse(s, (20, 20, 20), (14, h * 0.3, 52, h * 0.66), 3)
    return s


def _fallback_gold() -> pygame.Surface:
    s = pygame.Surface((64, 64), pygame.SRCALPHA)
    pygame.draw.circle(s, (180, 120, 20), (32, 34), 26)
    pygame.draw.circle(s, (255, 210, 70), (32, 31), 24)
    pygame.draw.circle(s, (200, 140, 30), (32, 31), 16, 3)
    return s


def _fallback_item(item: str) -> pygame.Surface:
    s = pygame.Surface((64, 64), pygame.SRCALPHA)
    c = {"rage": (200, 40, 40), "stone": (140, 140, 150), "repair": (150, 100, 50), "bomb": (30, 30, 30), "sword": (200, 200, 210)}[item]
    if item == "sword":
        pygame.draw.rect(s, c, (28, 4, 8, 42))
        pygame.draw.rect(s, (200, 160, 50), (16, 44, 32, 6))
        pygame.draw.rect(s, (90, 60, 30), (28, 50, 8, 12))
    else:
        pygame.draw.circle(s, c, (32, 36), 24)
        pygame.draw.circle(s, (20, 20, 20), (32, 36), 24, 2)
    return s


def damaged(spr: pygame.Surface, stage: int, seed: int = 0) -> pygame.Surface:
    """Пиксельные трещины и копоть поверх замка (только по непрозрачным пикселям)."""
    import random as _r

    rng = _r.Random(seed)
    w, h = spr.get_size()
    out = spr.copy()
    k = 0.86 if stage == 1 else 0.7
    out.fill((int(255 * k), int(255 * k * 0.97), int(255 * k * 0.95), 255), special_flags=pygame.BLEND_RGBA_MULT)
    ov = pygame.Surface((w, h), pygame.SRCALPHA)
    px = max(2, w // 90)
    for _ in range(5 if stage == 1 else 11):
        x, y = rng.uniform(w * 0.15, w * 0.85), rng.uniform(h * 0.15, h * 0.8)
        for _ in range(rng.randint(5, 10)):
            pygame.draw.rect(ov, (34, 26, 24, 235), (int(x), int(y), px, px))
            x += rng.choice((-1, 0, 1)) * px
            y += px
    if stage >= 2:  # копоть и проломы
        for _ in range(7):
            cx, cy, r = rng.uniform(w * 0.2, w * 0.8), rng.uniform(h * 0.15, h * 0.7), rng.uniform(w * 0.05, w * 0.1)
            pygame.draw.ellipse(ov, (20, 16, 16, 120), (cx - r, cy - r * 0.7, 2 * r, 1.4 * r))
    m = pygame.mask.from_surface(spr, 40).to_surface(setcolor=(255, 255, 255, 255), unsetcolor=(0, 0, 0, 0))
    ov.blit(m, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    out.blit(ov, (0, 0))
    return out


class Assets:
    """Кэш спрайтов для UI и боя. Масштабированные версии кэшируются по размеру."""

    def __init__(self) -> None:
        bg = _load("bg_battlefield.jpg") or _load("bg_battlefield.png")
        from castlefight.ui.surf import to_opaque

        self.bg = to_opaque(scale_to(bg, (WIDTH, HEIGHT)) if bg else _fallback_bg())
        self.castle_blue = _load("castle_blue.png") or _fallback_castle((60, 110, 220))
        red = _load("castle_red.png") or _fallback_castle((210, 60, 50))
        self.castle_red = pygame.transform.flip(red, True, False)
        self.gold_src = _load("icon_gold.png") or _fallback_gold()
        self.gold = fit(self.gold_src, 30, 30)

        self.building_src: dict[tuple[str, Role], pygame.Surface] = {}
        self.unit_src: dict[tuple[str, Role], pygame.Surface] = {}
        for fname, key in FACTION_KEYS.items():
            color = FACTION_COLORS[fname]
            for role in ROLE_ORDER:
                b = _load(f"buildings/{key}_{role.value}.png")
                self.building_src[(fname, role)] = b or _fallback_building(color, role)
                u = _load(f"units/{key}_{role.value}.png")
                self.unit_src[(fname, role)] = u or _fallback_unit(color, role)

        self.shop_src: dict[str, pygame.Surface] = {}
        for item in ("rage", "stone", "repair", "bomb", "sword"):
            self.shop_src[item] = _load(f"shop/{item}.png") or _fallback_item(item)

        self._cache: dict[tuple, pygame.Surface] = {}

    def item_icon(self, item: str, size: int) -> pygame.Surface:
        return self._get(("item", item, size), lambda: fit(self.shop_src[item], size, size))

    # --- масштабированные версии -----------------------------------------

    def _get(self, key: tuple, make) -> pygame.Surface:
        s = self._cache.get(key)
        if s is None:
            s = make()
            self._cache[key] = s
        return s

    def gold_icon(self, size: int) -> pygame.Surface:
        return self._get(("gold", size), lambda: fit(self.gold_src, size, size))

    def castle(self, side: int, w: int = 210, stage: int = 0) -> pygame.Surface:
        """Замок; stage 0 — целый, 1 — трещины (<50% HP), 2 — сильно разбит (<25% HP)."""
        src = self.castle_blue if side == 0 else self.castle_red
        base = self._get(("castle", side, w, 0), lambda: fit(src, w, w))
        if stage <= 0:
            return base
        return self._get(("castle", side, w, stage), lambda: damaged(base, stage, seed=side * 31 + stage))

    def building(self, faction: str, role: Role, w: int, h: int, flip: bool = False) -> pygame.Surface:
        def make():
            s = fit(self.building_src[(faction, role)], w, h)
            return pygame.transform.flip(s, True, False) if flip else s

        return self._get(("bld", faction, role, w, h, flip), make)

    def unit(self, faction: str, role: Role, side: int, variant: str = "") -> pygame.Surface:
        """Спрайт юнита на поле. variant: '' | 'flash' (белая вспышка) | 'raised' (зелёный призрак)."""

        def make():
            src_role = Role.MELEE if role == Role.MINION else role
            src = self.unit_src[(faction, src_role)]
            h = src.get_height() * UNIT_SCALE
            if role == Role.MINION:
                h *= MINION_SCALE
            s = fit_height(src, max(26, int(h)))
            if side == 1:
                s = pygame.transform.flip(s, True, False)
            if variant == "flash":
                s = s.copy()
                s.fill((120, 110, 100, 0), special_flags=pygame.BLEND_RGB_ADD)
            elif variant == "raised":
                s = s.copy()
                s.fill((150, 255, 170, 255), special_flags=pygame.BLEND_RGBA_MULT)
            return s

        return self._get(("unit", faction, role, side, variant), make)

    def unit_icon(self, faction: str, role: Role, w: int, h: int) -> pygame.Surface:
        return self._get(("uicon", faction, role, w, h), lambda: fit(self.unit_src[(faction, role)], w, h))

    def ghost(self, faction: str, role: Role, w: int, h: int, ok: bool) -> pygame.Surface:
        def make():
            s = self.building(faction, role, w, h).copy()
            tint = (150, 255, 150, 255) if ok else (255, 120, 110, 255)
            s.fill(tint, special_flags=pygame.BLEND_RGBA_MULT)
            s.set_alpha(190)
            return s

        return self._get(("ghost", faction, role, w, h, ok), make)


def make_vignette() -> pygame.Surface:
    """Лёгкое затемнение краёв экрана."""
    small = pygame.Surface((64, 36), pygame.SRCALPHA)
    for y in range(36):
        for x in range(64):
            dx = (x - 31.5) / 32
            dy = (y - 17.5) / 18
            d = math.sqrt(dx * dx + dy * dy)
            a = max(0, min(255, int((d - 0.65) * 260)))
            small.set_at((x, y), (0, 0, 0, a))
    return pygame.transform.smoothscale(small, (WIDTH, HEIGHT))
