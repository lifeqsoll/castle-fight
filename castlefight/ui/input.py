"""Клавиатура: горячие клавиши зданий."""

from __future__ import annotations

import pygame

from castlefight.data.enums import Role

ROLE_KEYS = {
    pygame.K_1: Role.MELEE,
    pygame.K_2: Role.RANGED,
    pygame.K_3: Role.SUMMON,
    pygame.K_4: Role.ULT,
    pygame.K_KP1: Role.MELEE,
    pygame.K_KP2: Role.RANGED,
    pygame.K_KP3: Role.SUMMON,
    pygame.K_KP4: Role.ULT,
}


def role_from_key(key: int) -> Role | None:
    return ROLE_KEYS.get(key)


SHOP_KEYMAP = {
    pygame.K_q: "rage",
    pygame.K_w: "stone",
    pygame.K_e: "repair",
    pygame.K_r: "bomb",
    pygame.K_t: "sword",
}


def shop_from_key(key: int) -> str | None:
    return SHOP_KEYMAP.get(key)
