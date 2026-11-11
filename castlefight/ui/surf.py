"""Непрозрачные поверхности для кадра.

Почему это важно (баг «чёрных прямоугольников»): на многих Linux-системах окно
pygame / pygame-ce имеет формат ARGB (с альфа-каналом). Если поле рисовать на
поверхности `Surface(...).convert()` такого формата, альфа у пикселей остаётся 0,
и программный блиттер SDL при «прозрачном» назначении копирует исходный пиксель
как есть: прозрачные (0,0,0,0) края спрайтов становятся чёрными, а пауза — почти
чёрной. Поэтому весь кадр рисуется на собственном холсте без альфа-канала
(RGB, 32 бита, маска альфы = 0), и только в конце копируется в окно.
"""

from __future__ import annotations

import pygame

RGB_MASKS = (0x00FF0000, 0x0000FF00, 0x000000FF, 0)


def opaque_surface(size: tuple[int, int]) -> pygame.Surface:
    """Поверхность без альфа-канала, независимо от формата окна."""
    return pygame.Surface(size, 0, 32, RGB_MASKS)


def to_opaque(surf: pygame.Surface) -> pygame.Surface:
    out = opaque_surface(surf.get_size())
    out.fill((0, 0, 0))
    out.blit(surf, (0, 0))
    return out
