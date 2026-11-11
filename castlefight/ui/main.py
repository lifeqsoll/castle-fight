"""Pygame-клиент Castle Fight: окно, главный цикл и переключение экранов."""

from __future__ import annotations

import sys

import pygame

from castlefight.ui.assets import Assets
from castlefight.ui.surf import opaque_surface
from castlefight.ui.theme import HEIGHT, WIDTH


_LETTERS = "abcdefghijklmnopqrstuvwxyz"


def _scan_map() -> dict[int, int]:
    m = {}
    for ch in _LETTERS:
        sc, k = getattr(pygame, f"KSCAN_{ch.upper()}", None), getattr(pygame, f"K_{ch}", None)
        if sc is not None and k is not None:
            m[sc] = k
    return m


_SCAN = None


def layout_free_key(e: pygame.event.Event) -> pygame.event.Event:
    """Горячие клавиши-буквы по физической клавише (scancode), а не по символу.
    С русской раскладкой H даёт «р» — без этого H, Q, W, U… не работали."""
    global _SCAN
    if _SCAN is None:
        _SCAN = _scan_map()
    sc = getattr(e, "scancode", 0)
    k = _SCAN.get(sc) if sc else None
    if k is None or k == e.key:
        return e
    d = dict(e.dict)
    d["key"] = k
    return pygame.event.Event(e.type, d)


class App:
    """Держит окно, ассеты и текущий экран. Удобно гонять из скриптов (frame())."""

    def __init__(self, screen: pygame.Surface) -> None:
        from castlefight.ui.scenes import MenuScene

        # окно (может быть ARGB) и собственный непрозрачный холст кадра — см. ui/surf.py
        self.display = screen
        self.screen = opaque_surface(screen.get_size())
        self.assets = Assets()
        self.mouse = (WIDTH // 2, HEIGHT // 2)
        self.running = True
        self.scene = MenuScene(self)

    def set_scene(self, scene) -> None:
        self.scene = scene

    def handle(self, e: pygame.event.Event) -> None:
        if e.type == pygame.QUIT:
            self.running = False
            return
        if e.type == pygame.KEYDOWN:
            e = layout_free_key(e)
        if hasattr(e, "pos") and e.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
            self.mouse = e.pos
        self.scene.handle(e)

    def frame(self, events, dt: float) -> None:
        for e in events:
            self.handle(e)
        self.scene.update(dt)
        self.scene.draw(self.screen)
        self.present()

    def present(self) -> None:
        """Скопировать холст в окно. Блит непрозрачного холста ставит альфу окна в 255."""
        self.display.blit(self.screen, (0, 0))

    def run(self) -> None:
        clock = pygame.time.Clock()
        while self.running:
            dt = min(0.05, clock.tick(60) / 1000.0)
            self.frame(pygame.event.get(), dt)
            pygame.display.flip()


def main() -> None:
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Castle Fight")
    App(screen).run()
    pygame.quit()
    sys.exit(0)


if __name__ == "__main__":
    main()
