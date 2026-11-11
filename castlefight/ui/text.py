"""Шрифты через pygame._freetype (работает без sdl2_ttf) + тени, обводка, перенос."""

from __future__ import annotations

from pathlib import Path

import pygame
import pygame._freetype as ft

FONTS_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
FONT_FILES = {
    # пиксельный шрифт для логотипа, цифр и коротких ярлыков (рисуется без сглаживания,
    # размеры кратны 8: 8 / 16 / 24 / 32)
    "pixel": "PressStart2P-Regular.ttf",
    # брусковый шрифт с хорошей кириллицей — заголовки, имена, основной текст
    "title": "Podkova-ExtraBold.ttf",
    "bold": "Podkova-SemiBold.ttf",
    "regular": "Podkova-Medium.ttf",
}
FALLBACK_FILES = {"title": "Philosopher-Bold.ttf", "bold": "PTSans-Bold.ttf", "regular": "PTSans-Regular.ttf"}

_inited = False


def _ensure() -> None:
    global _inited
    if not _inited:
        ft.init()
        _inited = True


class Font:
    """Обёртка с API как у pygame.font.Font.render(text, antialias, color) + кэш."""

    def __init__(self, size: int, kind: str = "regular") -> None:
        _ensure()
        self.size = size
        path = FONTS_DIR / FONT_FILES.get(kind, FONT_FILES["regular"])
        if not path.exists() and kind in FALLBACK_FILES:
            path = FONTS_DIR / FALLBACK_FILES[kind]
        try:
            self._font = ft.Font(str(path) if path.exists() else None, size)
        except Exception:  # битый файл — системный шрифт pygame
            self._font = ft.Font(None, size)
        self._font.antialiased = kind != "pixel"
        self._cache: dict[tuple, pygame.Surface] = {}

    def render(self, text: str, _antialias: bool = True, color=(255, 255, 255)) -> pygame.Surface:
        key = (text, tuple(color))
        surf = self._cache.get(key)
        if surf is None:
            if len(self._cache) > 600:
                self._cache.clear()
            if text:
                surf, _ = self._font.render(text, color)
            else:
                surf = pygame.Surface((1, self.height()), pygame.SRCALPHA)
            self._cache[key] = surf
        return surf

    def width(self, text: str) -> int:
        return self._font.get_rect(text).width if text else 0

    def height(self) -> int:
        return self._font.get_sized_height()


_FONTS: dict[tuple[int, str], Font] = {}


def make_font(size: int, kind: str = "regular") -> Font:
    key = (size, kind)
    if key not in _FONTS:
        _FONTS[key] = Font(size, kind)
    return _FONTS[key]


_FX_CACHE: dict[tuple, pygame.Surface] = {}


def _fx_cached(key: tuple, make) -> pygame.Surface:
    s = _FX_CACHE.get(key)
    if s is None:
        if len(_FX_CACHE) > 800:
            _FX_CACHE.clear()
        s = make()
        _FX_CACHE[key] = s
    return s


def shadow_text(font: Font, text: str, color, shadow=(0, 0, 0), offset: int = 2, alpha: int = 170) -> pygame.Surface:
    """Текст с мягкой тенью (кэшируется)."""
    return _fx_cached(("sh", id(font), text, tuple(color), tuple(shadow), offset, alpha), lambda: _shadow_text(font, text, color, shadow, offset, alpha))


def outline_text(font: Font, text: str, color, outline=(20, 14, 10), px: int = 2) -> pygame.Surface:
    """Текст с обводкой — для заголовков и цифр поверх арта (кэшируется)."""
    return _fx_cached(("ol", id(font), text, tuple(color), tuple(outline), px), lambda: _outline_text(font, text, color, outline, px))


def _shadow_text(font: Font, text: str, color, shadow, offset: int, alpha: int) -> pygame.Surface:
    fg = font.render(text, True, color)
    sh = font.render(text, True, shadow).copy()
    sh.set_alpha(alpha)
    out = pygame.Surface((fg.get_width() + offset, fg.get_height() + offset), pygame.SRCALPHA)
    out.blit(sh, (offset, offset))
    out.blit(fg, (0, 0))
    return out


def _outline_text(font: Font, text: str, color, outline, px: int) -> pygame.Surface:
    fg = font.render(text, True, color)
    ol = font.render(text, True, outline)
    w, h = fg.get_width() + px * 2, fg.get_height() + px * 2
    out = pygame.Surface((w, h + 2), pygame.SRCALPHA)
    for dx in range(-px, px + 1):
        for dy in range(-px, px + 1):
            if dx * dx + dy * dy <= px * px + 1:
                out.blit(ol, (px + dx, px + dy + 1))
    out.blit(fg, (px, px))
    return out


def fit_font(text: str, max_w: int, sizes: tuple[int, ...], kind: str = "bold") -> Font:
    """Самый крупный шрифт из sizes, в который влезает text."""
    for s in sizes:
        f = make_font(s, kind)
        if f.width(text) <= max_w:
            return f
    return make_font(sizes[-1], kind)


def wrap(font: Font, text: str, max_w: int) -> list[str]:
    """Перенос по словам."""
    lines: list[str] = []
    for para in text.split("\n"):
        cur = ""
        for word in para.split(" "):
            test = word if not cur else cur + " " + word
            if font.width(test) <= max_w:
                cur = test
            else:
                if cur:
                    lines.append(cur)
                cur = word
        lines.append(cur)
    return lines
