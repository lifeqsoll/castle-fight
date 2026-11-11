"""Геометрия поля: перевод координат линии в экран и ячейки зон застройки."""

from __future__ import annotations

from typing import Optional

import pygame

from castlefight.data.balance import LANE, SLOTS
from castlefight.ui.theme import (
    LANE_X0,
    LANE_X1,
    SLOT_COLS,
    SLOT_GAP,
    SLOT_H,
    SLOT_W,
    WIDTH,
    ZONE_X_LEFT,
    ZONE_Y,
)


def x_to_screen(x: float) -> float:
    return LANE_X0 + x / LANE * (LANE_X1 - LANE_X0)


def zone_rect(side: int) -> pygame.Rect:
    """Прямоугольник всей зоны застройки стороны side (с полями)."""
    w = SLOT_COLS * SLOT_W + (SLOT_COLS - 1) * SLOT_GAP
    h = (SLOTS // SLOT_COLS) * SLOT_H + (SLOTS // SLOT_COLS - 1) * SLOT_GAP
    x = ZONE_X_LEFT if side == 0 else WIDTH - ZONE_X_LEFT - w
    return pygame.Rect(x, ZONE_Y, w, h).inflate(12, 12)


def slot_rect(side: int, slot: int) -> pygame.Rect:
    """Ячейка slot (0..11). Колонка 0 — ближе всего к своему замку."""
    row, col = divmod(slot, SLOT_COLS)
    y = ZONE_Y + row * (SLOT_H + SLOT_GAP)
    if side == 0:
        x = ZONE_X_LEFT + col * (SLOT_W + SLOT_GAP)
    else:
        x = WIDTH - ZONE_X_LEFT - (col + 1) * SLOT_W - col * SLOT_GAP
    return pygame.Rect(x, y, SLOT_W, SLOT_H)


def slot_at(side: int, pos: tuple[int, int]) -> Optional[int]:
    for i in range(SLOTS):
        if slot_rect(side, i).collidepoint(pos):
            return i
    return None


def screen_to_x(sx: float) -> float:
    """Обратный перевод: экранный x → координата линии (с ограничением)."""
    x = (sx - LANE_X0) / (LANE_X1 - LANE_X0) * LANE
    return max(0.0, min(float(LANE), x))


def lane_px(r: float) -> float:
    """Длина r на линии → пиксели экрана."""
    return r / LANE * (LANE_X1 - LANE_X0)
