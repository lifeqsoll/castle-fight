"""Отрисовка поля боя: фон, замки, зоны застройки, здания, юниты, эффекты.

Логика мира тикает дискретно (dt=0.2), а рисуем 60 FPS — поэтому позиции юнитов
интерполируются между двумя последними тиками, а события (удар, смерть, выстрел)
вычисляются сравнением снимков до/после тика. В core ничего не меняется.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Optional

import pygame

from castlefight.core.world import World
from castlefight.data.balance import SHOP, SLOTS
from castlefight.data.enums import DamageType, Role
from castlefight.ui.assets import Assets, make_vignette
from castlefight.ui.effects import Effects
from castlefight.ui.surf import opaque_surface
from castlefight.ui import kit
from castlefight.ui.layout import lane_px, slot_rect, x_to_screen, zone_rect
from castlefight.ui.text import make_font, outline_text
from castlefight.ui.theme import (
    BG_OFFSET_Y,
    CASTLE_BASE_Y,
    C_BAD,
    C_GOOD,
    C_GOLD,
    C_HINT,
    C_TEXT,
    FACTION_COLORS,
    LANE_Y,
    SLOT_H,
    SLOT_W,
    TEAM,
    WIDTH,
)
from castlefight.ui.widgets import draw_bar, drop_shadow, shade

CASTLE_W = 196
MAGIC_COLORS = {
    "Аркана": (90, 220, 255),
    "Некрополь": (140, 255, 120),
    "Кузня": (255, 160, 60),
    "Королевство": (255, 240, 160),
    "Орда": (255, 140, 80),
    "Лес": (170, 255, 140),
}


def _darken(surf: pygame.Surface) -> pygame.Surface:
    out = surf.copy()
    out.fill((88, 80, 76, 255), special_flags=pygame.BLEND_RGBA_MULT)
    return out


TOWN_W = 34  # ширина домика городка на поле (ближний ряд)


def town_pos(side: int, slot: int) -> tuple[float, float, float]:
    """Место здания городка на поле: (экранный x центра, y низа, масштаб).
    Стоят на траве между холмами и дорогой, сразу за замком. Ряд 0 — ближний (ниже, крупнее),
    ряд 1 — дальний (выше, мельче, со сдвигом «в шахматку»); колонка 0 — у замка."""
    row, col = divmod(slot, 6)
    y = 349 - row * 13 - (col % 2) * 2
    x = 216 + col * 38 + row * 19
    if side == 1:
        x = WIDTH - x
    return float(x), float(y), 1.0 - row * 0.15


def _ellipse_shadow(w: int) -> pygame.Surface:
    s = pygame.Surface((int(w * 1.1), max(6, w // 4)), pygame.SRCALPHA)
    pygame.draw.ellipse(s, (20, 30, 10, 60), s.get_rect())
    pygame.draw.ellipse(s, (20, 30, 10, 60), s.get_rect().inflate(-w // 3, -2))
    return s


@dataclass
class UnitVis:
    prev_x: float
    x: float
    depth: float
    flash: float = 0.0
    lunge: float = 0.0
    phase: float = 0.0
    moving: bool = False


@dataclass
class FieldUI:
    """Что UI хочет подсветить на поле в этом кадре."""

    mouse: tuple[int, int] = (0, 0)
    placing: Optional[Role] = None  # роль, которую ставим
    drag_slot: Optional[int] = None  # ячейка, из которой тащим здание
    hover_slot: Optional[int] = None  # ячейка своей зоны под курсором
    hover_enemy_slot: Optional[int] = None
    can_afford: bool = True
    show_zones: bool = True
    hover_unit: object = None  # вражеский юнит под курсором (для удара)
    bomb_x: Optional[float] = None  # экранный x прицела бомбы
    bomb_ok: bool = True
    sell_slot: Optional[int] = None  # ячейка, для которой открыт вопрос «продать?»
    strike_ready: float = 1.0  # 0..1 — готовность удара
    me: int = 0  # сторона этого игрока (в сетевой игре клиент — 1)


class BattleRenderer:
    def __init__(self, screen: pygame.Surface, assets: Assets) -> None:
        self.screen = screen
        self.assets = assets
        self.effects = Effects(assets.gold_src)
        # без .convert(): формат окна может быть ARGB, и альфа фона осталась бы 0 (см. ui/surf.py)
        self.field_bg = opaque_surface(screen.get_size())
        self.field_bg.fill((0, 0, 0))
        self.field_bg.blit(assets.bg, (0, BG_OFFSET_Y))
        if BG_OFFSET_Y < 0:  # низ, открывшийся из-за сдвига фона, — отражённая трава
            strip = assets.bg.subsurface(pygame.Rect(0, assets.bg.get_height() + BG_OFFSET_Y * 2, assets.bg.get_width(), -BG_OFFSET_Y)).copy()
            self.field_bg.blit(pygame.transform.flip(strip, False, True), (0, assets.bg.get_height() + BG_OFFSET_Y))
        self.field_bg.blit(make_vignette(), (0, 0))
        self._smoke_t = [0.0, 0.0]
        self.vis: dict[int, UnitVis] = {}
        self._snap: dict[int, tuple] = {}
        self._castle_snap: list[tuple[float, float]] = []
        self.castle_flash = [0.0, 0.0]
        self.castle_ghost_hp = [1.0, 1.0]
        self.rng = random.Random(3)
        self.time = 0.0
        self.small = make_font(13, "bold")
        self.unit_rects: list[tuple[pygame.Rect, object]] = []
        self.events: list[tuple] = []
        self.me = 0  # чья сторона «своя» (золото за убийства, вспышки удара)
        self.show_town = True

    def unit_at(self, pos, side: int):
        """Юнит стороны side под курсором (верхний по отрисовке, с небольшим допуском)."""
        best = None
        for rect, u in reversed(self.unit_rects):
            if u.side == side and u.alive and rect.inflate(10, 6).collidepoint(pos):
                best = u
                break
        return best

    # --- события тика --------------------------------------------------------

    def before_step(self, world: World) -> None:
        self._snap = {}
        for p in world.players:
            for u in p.units:
                self._snap[id(u)] = (u, u.x, u.hp, u.cd, p.side)
        self._castle_snap = [(p.castle.hp, p.castle.cd) for p in world.players]

    def after_step(self, world: World) -> None:
        alive_ids: set[int] = set()
        for p in world.players:
            faction = p.faction.name
            for u in p.units:
                uid = id(u)
                alive_ids.add(uid)
                snap = self._snap.get(uid)
                v = self.vis.get(uid)
                if v is None or snap is None:
                    v = UnitVis(u.x, u.x, self.rng.uniform(-9, 9), phase=self.rng.uniform(0, 6))
                    self.vis[uid] = v
                    continue
                _, sx, shp, scd, _ = snap
                v.prev_x, v.x = sx, u.x
                v.moving = abs(u.x - sx) > 0.05
                if u.hp < shp - 0.01:
                    v.flash = 0.12
                    if self.rng.random() < 0.5:
                        self.effects.hit(x_to_screen(u.x), LANE_Y + v.depth - 22, (255, 236, 190), 3)
                if u.cd > scd + 1e-6:  # атаковал на этом тике
                    self._on_attack(world, p, u, v, faction)
        # смерти
        for uid, (u, sx, shp, scd, side) in self._snap.items():
            if uid in alive_ids:
                continue
            v = self.vis.pop(uid, None)
            if u.alive:  # не умер, а просто исчез — не бывает, но на всякий
                continue
            depth = v.depth if v else 0.0
            faction = world.players[side].faction.name
            sx_scr = x_to_screen(u.x)
            spr = self.assets.unit(faction, u.role, side, self._variant(u))
            self.effects.death(spr, sx_scr, LANE_Y + depth, TEAM[side])
            if side != self.me and u.bounty > 0:
                self.effects.gold(sx_scr, LANE_Y + depth - spr.get_height() - 18, u.bounty)
        # события мира: взрывы бомб, проценты «Казны», покупки в лавке
        for e in world.events:
            if e[0] == "bomb":
                _, side, x, killed = e
                sx = x_to_screen(x)
                self.effects.explosion(sx, LANE_Y + 2, lane_px(SHOP["bomb"]["radius"]))
                if killed:
                    self.effects.text(sx, LANE_Y - 90, f"x{killed}", (255, 210, 120))
            elif e[0] == "strike":
                _, side, x, dealt = e
                tgt = next((u for u in world.players[1 - side].units if abs(u.x - x) < 0.01), None)
                v = self.vis.get(id(tgt)) if tgt is not None else None
                y = LANE_Y + (v.depth if v else 0) - 30
                sx = x_to_screen(x)
                self.effects.slash(sx, y)
                col = (255, 236, 190) if side == self.me else (255, 150, 130)
                self.effects.text(sx, y - 34, f"-{dealt:.0f}", col)
                if v is not None:
                    v.flash = 0.12
            elif e[0] == "shop" and e[2] == "repair":
                c = world.players[e[1]].castle
                cx = x_to_screen(c.x)
                for k in range(3):
                    self.effects.hit(cx + self.rng.uniform(-50, 50), CASTLE_BASE_Y - self.rng.uniform(40, 140), (190, 240, 150), 6)
                self.effects.text(cx, CASTLE_BASE_Y - 200, f"+{int(c.max_hp * SHOP['repair']['frac'])}", (170, 240, 140))
            elif e[0] == "shop" and e[2] in ("rage", "stone"):
                col = (255, 120, 90) if e[2] == "rage" else (190, 200, 220)
                for u in world.players[e[1]].units[:40]:
                    v = self.vis.get(id(u))
                    self.effects.hit(x_to_screen(u.x), LANE_Y + (v.depth if v else 0) - 30, col, 2)
            self.events.append(e)
        if len(self.events) > 50:
            del self.events[:-50]
        # замки
        for i, p in enumerate(world.players):
            hp0, cd0 = self._castle_snap[i] if self._castle_snap else (p.castle.hp, p.castle.cd)
            if p.castle.hp < hp0 - 0.01:
                self.castle_flash[i] = 0.12
            if p.castle.cd > cd0 + 1e-6:
                enemy = world.players[1 - i]
                cands = [u for u in enemy.units if u.alive]
                tx = None
                if cands:
                    t = min(cands, key=lambda u: abs(u.x - p.castle.x))
                    if abs(t.x - p.castle.x) <= p.castle.rng + 40:
                        tx = t
                for u0 in self._snap.values():
                    if tx is None and u0[4] != i and abs(u0[1] - p.castle.x) <= p.castle.rng + 40:
                        tx = u0[0]
                if tx is not None:
                    v = self.vis.get(id(tx))
                    d = v.depth if v else 0
                    cx = x_to_screen(p.castle.x)
                    self.effects.shoot(cx + (30 if i == 0 else -30), CASTLE_BASE_Y - 150, x_to_screen(tx.x), LANE_Y + d - 24, "bolt")

    def _variant(self, u) -> str:
        return "raised" if u.name == "Поднятый" else ""

    def _on_attack(self, world: World, p, u, v: UnitVis, faction: str) -> None:
        enemy = world.players[1 - p.side]
        if u.rng <= 60:
            v.lunge = 0.18
            return
        # дальний: снаряд к ближайшему врагу перед собой, иначе в замок
        best = None
        best_d = 1e9
        for e in enemy.units:
            d = (e.x - u.x) * u.dir
            if -5 <= d <= u.rng + 10 and d < best_d:
                best, best_d = e, d
        x0 = x_to_screen(u.x) + 12 * u.dir
        y0 = LANE_Y + v.depth - 34
        if best is not None:
            ev = self.vis.get(id(best))
            x1, y1 = x_to_screen(best.x), LANE_Y + (ev.depth if ev else 0) - 26
        else:
            x1, y1 = x_to_screen(enemy.castle.x), CASTLE_BASE_Y - 70
        if u.name == "Пушка":
            kind = "ball"
        elif u.dtype == DamageType.MAGIC:
            kind = "magic"
        else:
            kind = "arrow"
        self.effects.shoot(x0, y0, x1, y1, kind, MAGIC_COLORS.get(faction, (255, 255, 255)))

    def update(self, dt: float) -> None:
        self.time += dt
        self.effects.update(dt)
        for v in self.vis.values():
            v.flash = max(0.0, v.flash - dt)
            v.lunge = max(0.0, v.lunge - dt)
            if v.moving:
                v.phase += dt * 9
        for i in range(2):
            self.castle_flash[i] = max(0.0, self.castle_flash[i] - dt)

    # --- отрисовка -----------------------------------------------------------

    def draw(self, world: World, alpha: float, ui: FieldUI) -> None:
        sc = self.screen
        sc.blit(self.field_bg, (0, 0))
        self.effects.draw_ground(sc)
        if ui.bomb_x is not None:
            self._draw_bomb_aim(ui)

        if self.show_town:
            self._draw_town(world)
        for p in world.players:
            self._draw_castle(p, world)

        self.effects.draw_under(sc)
        self._draw_units(world, alpha, ui)
        if ui.show_zones:
            for p in world.players:
                self._draw_zone(p, ui)
        self._draw_bombs(world)
        self.effects.draw_over(sc)
        if ui.show_zones and (ui.placing is not None or ui.drag_slot is not None):
            self._draw_ghost(world.players[ui.me], ui)
        dx, dy = self.effects.shake_offset()
        if dx or dy:
            sc.scroll(dx, dy)

    def _draw_bomb_aim(self, ui: FieldUI) -> None:
        r = lane_px(SHOP["bomb"]["radius"])
        w, h = int(r * 2), int(r * 0.7)
        col = (255, 90, 60) if ui.bomb_ok else (150, 150, 150)
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        pulse = 0.5 + 0.5 * math.sin(self.time * 8)
        pygame.draw.ellipse(s, (*col, int(40 + 30 * pulse)), s.get_rect())
        pygame.draw.ellipse(s, (*kit.INK, 220), s.get_rect(), 4)
        pygame.draw.ellipse(s, (*col, 255), s.get_rect().inflate(-4, -4), 2)
        x = ui.bomb_x
        self.screen.blit(s, (x - w / 2, LANE_Y + 4 - h / 2))
        # перекрестие
        for a in range(4):
            ang = a * math.pi / 2
            x0, y0 = x + math.cos(ang) * 8, LANE_Y + 4 + math.sin(ang) * 5
            x1, y1 = x + math.cos(ang) * 20, LANE_Y + 4 + math.sin(ang) * 12
            pygame.draw.line(self.screen, kit.INK, (x0, y0), (x1, y1), 4)
            pygame.draw.line(self.screen, col, (x0, y0), (x1, y1), 2)

    def _draw_bombs(self, world: World) -> None:
        """Падающие бомбы: растущая тень на земле и сама бомба сверху."""
        sc = self.screen
        for b in world.bombs:
            k = 1 - max(0.0, b.t) / b.delay  # 0 → 1 к моменту падения
            x = x_to_screen(b.x)
            r = lane_px(SHOP["bomb"]["radius"])
            # круг-предупреждение
            w, h = int(r * 2), int(r * 0.7)
            s = pygame.Surface((w, h), pygame.SRCALPHA)
            pygame.draw.ellipse(s, (255, 80, 50, int(30 + 50 * k)), s.get_rect())
            pygame.draw.ellipse(s, (255, 120, 80, 200), s.get_rect(), 2)
            sc.blit(s, (x - w / 2, LANE_Y + 4 - h / 2))
            sw = int(16 + 30 * k)
            sh = pygame.Surface((sw, max(4, sw // 3)), pygame.SRCALPHA)
            pygame.draw.ellipse(sh, (0, 0, 0, int(60 + 100 * k)), sh.get_rect())
            sc.blit(sh, (x - sw / 2, LANE_Y + 4 - sh.get_height() / 2))
            y = -40 + (LANE_Y - 16 + 40) * (k ** 1.8)
            ic = self.assets.item_icon("bomb", 38)
            sc.blit(ic, ic.get_rect(center=(int(x), int(y))))

    def _draw_town(self, world: World) -> None:
        """Городок: каждое построенное здание стоит ещё и на поле, за своим замком.
        Ячейка зоны ↔ фиксированное место; порядок отрисовки — по глубине (дальние раньше)."""
        items = []
        for p in world.players:
            for b in p.buildings:
                x, y, scale = town_pos(p.side, b.slot)
                items.append((y, x, p, b, scale))
        items.sort(key=lambda t: (t[0], t[1]))
        sc = self.screen
        for y, x, p, b, scale in items:
            w = int(TOWN_W * scale)
            spr = self.assets.building(p.faction.name, b.role, w, int(w * 1.15), flip=p.side == 1)
            r = spr.get_rect(midbottom=(int(x), int(y)))
            sh = self.assets._get(("town_sh", w), lambda: _ellipse_shadow(w))
            sc.blit(sh, (r.centerx - sh.get_width() // 2, r.bottom - sh.get_height() + 2))
            sc.blit(spr, r)

    def _draw_castle(self, p, world: World) -> None:
        sc = self.screen
        ratio0 = max(0.0, p.castle.hp / p.castle.max_hp)
        stage = 0 if ratio0 >= 0.5 else (1 if ratio0 >= 0.25 else 2)
        spr = self.assets.castle(p.side, CASTLE_W, stage)
        cx = int(x_to_screen(p.castle.x))
        rect = spr.get_rect(midbottom=(cx, CASTLE_BASE_Y + 14))
        shadow = pygame.Surface((rect.w, 30), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (0, 0, 0, 80), shadow.get_rect())
        sc.blit(shadow, (rect.x, CASTLE_BASE_Y - 4))
        ratio = max(0.0, p.castle.hp / p.castle.max_hp)
        if ratio <= 0:
            spr = self.assets._get(("ruin", p.side), lambda: _darken(spr))
        sc.blit(spr, rect)
        # дым при низком HP, пожар при разрушении
        if ratio < 0.35:
            self._smoke_t[p.side] -= 1 / 60
            if self._smoke_t[p.side] <= 0:
                self._smoke_t[p.side] = 0.05 if ratio <= 0 else 0.25
                self.effects.smoke(rect.centerx, rect.y + rect.h * 0.45, fire=ratio <= 0.15)
        if self.castle_flash[p.side] > 0:
            fl = spr.copy()
            fl.fill((90, 70, 60, 0), special_flags=pygame.BLEND_RGB_ADD)
            fl.set_alpha(120)
            sc.blit(fl, rect)
        # полоска HP над замком
        g = self.castle_ghost_hp[p.side]
        g = max(ratio, g - 0.004) if g > ratio else ratio
        self.castle_ghost_hp[p.side] = g
        bar = pygame.Rect(0, 0, 120, 12)
        bar.midbottom = (cx, rect.top + 18)
        kit.pixel_bar(sc, bar, ratio, TEAM[p.side], ghost=g)
        txt = outline_text(self.small, f"{int(max(0, p.castle.hp)):,}".replace(",", " "), kit.CREAM, kit.INK, 2)
        sc.blit(txt, (bar.centerx - txt.get_width() // 2, bar.y - txt.get_height() + 2))

    def _draw_units(self, world: World, alpha: float, ui: Optional[FieldUI] = None) -> None:
        sc = self.screen
        self.unit_rects = []
        hover = ui.hover_unit if ui is not None else None
        items = []
        for p in world.players:
            faction = p.faction.name
            for u in p.units:
                if not u.alive:
                    continue
                v = self.vis.get(id(u))
                if v is None:
                    v = UnitVis(u.x, u.x, self.rng.uniform(-9, 9))
                    self.vis[id(u)] = v
                x = v.prev_x + (v.x - v.prev_x) * alpha
                items.append((LANE_Y + v.depth, x, u, v, p.side, faction))
        items.sort(key=lambda t: t[0])
        for y, x, u, v, side, faction in items:
            sx = x_to_screen(x)
            variant = "flash" if v.flash > 0 else self._variant(u)
            spr = self.assets.unit(faction, u.role, side, variant)
            bob = -abs(math.sin(v.phase)) * 3 if v.moving else 0
            lunge = math.sin((v.lunge / 0.18) * math.pi) * 8 * u.dir if v.lunge > 0 else 0
            w = spr.get_width()
            # тень и цветное кольцо команды
            sw = max(22, int(w * 0.62))
            sh = pygame.Surface((sw, 10), pygame.SRCALPHA)
            pygame.draw.ellipse(sh, (0, 0, 0, 95), sh.get_rect())
            pygame.draw.ellipse(sh, (*TEAM[side], 150), sh.get_rect(), 2)
            sc.blit(sh, (sx - sw // 2, y - 5))
            r = spr.get_rect(midbottom=(int(sx + lunge), int(y + bob)))
            sc.blit(spr, r)
            self.unit_rects.append((r, u))
            if u is hover:
                self._draw_target(r, ui.strike_ready if ui is not None else 1.0)
            # HP — только у раненых (и у цели под курсором), чтобы толпа не превращалась в «шум полосок»
            if 0 < u.hp < u.max_hp - 0.5 or u is hover:
                bw = 40 if u.role == Role.ULT else (24 if u.role == Role.MINION else 30)
                bar = pygame.Rect(int(sx) - bw // 2, r.top - 8, bw, 6)
                kit.pixel_bar(sc, bar, u.hp / u.max_hp, TEAM[side])

    def _draw_target(self, r: pygame.Rect, ready: float) -> None:
        """Уголки-скобки вокруг цели удара; красные, когда удар готов."""
        sc = self.screen
        col = (255, 80, 50) if ready >= 1.0 else (200, 170, 150)
        box = r.inflate(8, 4)
        L = 8
        for (x, y, dx, dy) in ((box.left, box.top, 1, 1), (box.right, box.top, -1, 1), (box.left, box.bottom, 1, -1), (box.right, box.bottom, -1, -1)):
            for c, wdt in ((kit.INK, 5), (col, 2)):
                pygame.draw.line(sc, c, (x, y), (x + L * dx, y), wdt)
                pygame.draw.line(sc, c, (x, y), (x, y + L * dy), wdt)

    def _draw_zone(self, p, ui: FieldUI) -> None:
        sc = self.screen
        side = p.side
        zr = zone_rect(side)
        team = TEAM[side]
        # ярлык зоны — маленькая деревянная табличка с цветной полосой команды
        used = len(p.buildings)
        text = f"твоя зона {used}/{SLOTS}" if side == ui.me else f"враг {used}/{SLOTS}"
        lab = outline_text(self.small, text, kit.CREAM, kit.INK, 2)
        tab = pygame.Rect(0, 0, lab.get_width() + 18, 22)
        tab.bottomleft = (zr.x + 6 if side == 0 else zr.right - 6 - tab.w, zr.y + 2)
        drop_shadow(sc, tab, 2, 70)
        sc.blit(kit.wood_panel(tab.size, nails=False, seed=side), tab.topleft)
        pygame.draw.rect(sc, team, (tab.x + 3, tab.bottom - 5, tab.w - 6, 2))
        sc.blit(lab, (tab.x + 9, tab.y + 2))

        active = side == ui.me and (ui.placing is not None or ui.drag_slot is not None)
        t = self.time
        for i in range(SLOTS):
            cr = slot_rect(side, i)
            b = p.building_at(i)
            hov = (side == ui.me and ui.hover_slot == i) or (side != ui.me and ui.hover_enemy_slot == i)
            if active:
                if ui.drag_slot == i:
                    state = "drag"
                elif b is None:
                    state = "free"
                else:
                    state = "busy"
            else:
                state = "hover" if hov else "idle"
            pl_h = 26
            plate_r = pygame.Rect(cr.x + 2, cr.bottom - pl_h, cr.w - 4, pl_h)
            sc.blit(kit.plinth(plate_r.size, state, seed=i + side * 12), plate_r.topleft)
            if active and b is None and ui.drag_slot != i:
                # мигающая рамка свободной клетки
                pulse = 0.5 + 0.5 * math.sin(t * 5)
                c = (200, 255, 150) if ui.hover_slot == i else kit.shade((150, 220, 110), 0.85 + 0.25 * pulse)
                pygame.draw.rect(sc, kit.INK, plate_r.inflate(4, 4), 2)
                pygame.draw.rect(sc, c, plate_r, 2)
            if ui.sell_slot == i and side == ui.me:
                pygame.draw.rect(sc, kit.INK, plate_r.inflate(4, 4), 2)
                pygame.draw.rect(sc, kit.GOLD, plate_r, 2)
            if b is None:
                continue
            if ui.drag_slot == i and side == ui.me:
                continue  # здание «в руке»
            spr = self.assets.building(p.faction.name, b.role, SLOT_W - 2, SLOT_H - 6, flip=side == 1)
            sc.blit(spr, spr.get_rect(midbottom=(cr.centerx, cr.bottom - 9)))
            if b.role == Role.ULT:
                pygame.draw.rect(sc, kit.INK, (cr.right - 11, cr.y + 2, 9, 9))
                pygame.draw.rect(sc, kit.GOLD, (cr.right - 9, cr.y + 4, 5, 5))
            if b.spawn_mult < 1.0:
                # «Соседство» — маленькая зелёная стрелка-ускорение
                pygame.draw.rect(sc, kit.INK, (cr.x + 1, cr.y + 2, 9, 9))
                pygame.draw.rect(sc, (130, 220, 90), (cr.x + 3, cr.y + 4, 5, 5))
            bar = pygame.Rect(cr.x + 5, cr.bottom - 7, cr.w - 10, 6)
            kit.pixel_bar(sc, bar, b.progress, shade(team, 1.2))

    def _draw_ghost(self, player, ui: FieldUI) -> None:
        sc = self.screen
        role = ui.placing
        if ui.drag_slot is not None:
            b = player.building_at(ui.drag_slot)
            if b is None:
                return
            role = b.role
        if role is None:
            return
        ok_slot = ui.hover_slot is not None and player.building_at(ui.hover_slot) is None
        ok = ok_slot and (ui.drag_slot is not None or ui.can_afford)
        g = self.assets.ghost(player.faction.name, role, SLOT_W + 6, SLOT_H + 2, ok)
        if ok_slot:
            cr = slot_rect(ui.me, ui.hover_slot)
            pos = g.get_rect(midbottom=(cr.centerx, cr.bottom - 7))
        else:
            pos = g.get_rect(center=ui.mouse)
        sc.blit(g, pos)
        c = (120, 210, 90) if ok else (220, 70, 50)
        badge = pygame.Rect(pos.right - 12, pos.top - 2, 16, 16)
        pygame.draw.rect(sc, kit.INK, badge)
        pygame.draw.rect(sc, c, badge.inflate(-4, -4))
        if ok:
            pygame.draw.lines(sc, kit.INK, False, [(badge.x + 4, badge.y + 8), (badge.x + 7, badge.y + 11), (badge.x + 12, badge.y + 4)], 2)
        else:
            pygame.draw.line(sc, kit.INK, (badge.x + 4, badge.y + 4), (badge.right - 5, badge.bottom - 5), 2)
            pygame.draw.line(sc, kit.INK, (badge.right - 5, badge.y + 4), (badge.x + 4, badge.bottom - 5), 2)
