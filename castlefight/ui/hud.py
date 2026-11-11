"""HUD: верхние «вывески» (замки, золото, таймер, скорость) и нижняя доска
(карточки зданий, апгрейд армии, лавка)."""

from __future__ import annotations

import math
from typing import Optional

import pygame

from castlefight.core import shop
from castlefight.core.economy import income_rate
from castlefight.data.balance import MULT, SELL_REFUND, SHOP, STRIKE_CD, STRIKE_DMG, SWORD_COST, UPG_BONUS, UPG_COST, UPG_MAX
from castlefight.data.enums import ArmorType, DamageType, Role
from castlefight.data.factions import BuildingType, UnitType
from castlefight.ui import kit
from castlefight.ui.assets import Assets
from castlefight.ui.text import fit_font, make_font, outline_text
from castlefight.ui.theme import (
    ARMOR_LABELS,
    DTYPE_LABELS,
    HEIGHT,
    MODE_LABELS,
    P_BAD,
    P_GOLD,
    P_GOOD,
    P_HEAL,
    P_HOT,
    P_MAGIC,
    P_MUTED,
    P_ROLE,
    P_TEXT,
    PANEL_Y,
    ROLE_LABELS,
    ROLE_ORDER,
    SHOP_KEYS,
    SHOP_NAMES,
    SHOP_ORDER,
    SHOP_SHORT,
    TEAM,
    WIDTH,
)
from castlefight.ui.widgets import drop_shadow, draw_tooltip


def fmt_time(t: float) -> str:
    t = max(0, int(t))
    return f"{t // 60:02d}:{t % 60:02d}"


def fmt_int(v: float) -> str:
    return f"{int(v):,}".replace(",", " ")


# --- описание юнита для подсказок -----------------------------------------


def _good_against(dtype: DamageType) -> list[str]:
    row = MULT[dtype]
    return [ARMOR_LABELS[a] for a in (ArmorType.L, ArmorType.M, ArmorType.H, ArmorType.S, ArmorType.R) if row[a] > 1.0]


def unit_lines(u: UnitType, upgrade_mult: float = 1.0) -> list[tuple[str, tuple]]:
    hp = u.hp * upgrade_mult
    dmg = u.dmg * upgrade_mult
    lines: list[tuple[str, tuple]] = [
        (f"HP {hp:.0f}  ·  броня: {ARMOR_LABELS[u.armor]}", P_TEXT),
        (f"Урон {dmg:.0f} ({DTYPE_LABELS[u.dtype]}) раз в {u.cd:g} с", P_TEXT),
        (f"Дальность {u.rng:g}  ·  скорость {u.spd:g}", P_MUTED),
    ]
    good = _good_against(u.dtype)
    if good:
        lines.append(("Силён против брони: " + ", ".join(good), P_GOOD))
    if u.minion is not None:
        m = u.minion
        lines.append(
            (
                f"Призывает «{m.name}» каждые {u.every:g} с (до {u.maxmin} сразу, {u.total} за жизнь): "
                f"HP {m.hp * upgrade_mult:.0f}, урон {m.dmg * upgrade_mult:.0f}",
                P_MAGIC,
            )
        )
    if u.aura_heal:
        lines.append((f"Аура: лечит союзников рядом на {u.aura_heal:g} HP/с", P_HEAL))
    if u.regen:
        lines.append((f"Регенерация {u.regen:g} HP/с", P_HEAL))
    if u.cleave:
        lines.append((f"Клив: {int(u.cleave * 100)}% урона соседям цели", P_HOT))
    if u.splash:
        lines.append((f"Сплеш: {int(u.splash * 100)}% урона по площади", P_HOT))
    if u.raise_dead:
        lines.append(("Поднимает убитых врагов (до 6)", P_HEAL))
    if u.siege:
        lines.append((f"Осада: x{u.siege:g} урона по замку", P_HOT))
    return lines


def building_lines(bt: BuildingType, upgrade_mult: float, reason: Optional[str]) -> list[tuple[str, tuple]]:
    lines = [
        (f"Стоимость {bt.cost}  ·  юнит каждые {bt.spawn:g} с", P_GOLD),
        (f"Враг получит {bt.unit.bounty} зол. за убийство юнита", P_MUTED),
        ("-", P_MUTED),
    ]
    lines += unit_lines(bt.unit, upgrade_mult)
    lines.append(("-", P_MUTED))
    lines.append(("Соседство: такое же здание рядом — юниты выходят на 8% чаще", P_MUTED))
    if reason:
        lines.append((f"Нельзя: {reason}", P_BAD))
    else:
        lines.append(("Клик по карточке → клетка в своей зоне", P_MUTED))
    return lines


def shop_lines(player, world, item: str) -> list[tuple[str, tuple]]:
    s = SHOP.get(item, {})
    if item == "rage":
        lines = [(f"Вся твоя армия бьёт на +{int((s['mult'] - 1) * 100)}% сильнее {s['dur']:g} с.", P_TEXT)]
    elif item == "stone":
        lines = [(f"Твои воины получают на {int((1 - s['mult']) * 100)}% меньше урона {s['dur']:g} с.", P_TEXT)]
    elif item == "repair":
        left = s["uses"] - player.repairs
        lines = [
            (f"Замок восстанавливает {int(s['frac'] * 100)}% прочности ({fmt_int(player.castle.max_hp * s['frac'])} HP).", P_TEXT),
            (f"Осталось ремонтов: {left} из {s['uses']}", P_MUTED),
        ]
    elif item == "bomb":
        lines = [
            ("Выбери точку на дороге — через "
             f"{s['delay']:g} с бомба упадёт и нанесёт {s['dmg']:.0f} урона всем врагам в радиусе.", P_TEXT),
            ("Своих не задевает. Отлично против толпы и миньонов.", P_MUTED),
        ]
    else:
        lvl = player.sword
        nxt = f" → {STRIKE_DMG[lvl + 1]}" if lvl + 1 < len(STRIKE_DMG) else ""
        lines = [
            ("Кликай по вражеским воинам — герой бьёт сам.", P_TEXT),
            (f"Урон удара: {STRIKE_DMG[lvl]}{nxt}  ·  не чаще раза в {STRIKE_CD:g} с", P_TEXT),
            (f"Уровень меча: {lvl}/{len(SWORD_COST)}", P_MUTED),
        ]
    if item != "sword":
        lines.append((f"Перезарядка {s['cd']:g} с", P_MUTED))
    lines.append(("-", P_MUTED))
    reason = shop.block_reason(player, world, item)
    c = shop.cost(player, item)
    if reason:
        lines.append((f"Нельзя: {reason}", P_BAD))
    elif c is not None:
        lines.append((f"Цена {c} зол.  ·  клавиша {SHOP_KEYS[item]}", P_GOLD))
    return lines


# --- верхние вывески ----------------------------------------------------------


class TopBar:
    def __init__(self, assets: Assets) -> None:
        self.assets = assets
        self.ghost = [1.0, 1.0]
        self.speed_rect = pygame.Rect(WIDTH // 2 + 126, 6, 178, 52)

    def draw(self, screen: pygame.Surface, world, mode: str, speed: int, paused: bool) -> None:
        a, b = world.players
        self._side(screen, a, 0, "ты", world)
        self._side(screen, b, 1, "бот", world)
        self._center(screen, world, a, mode, speed, paused)

    def _side(self, screen, p, side: int, who: str, world) -> None:
        crest = pygame.Rect(8 if side == 0 else WIDTH - 60, 6, 52, 52)
        drop_shadow(screen, crest, 3, 70)
        screen.blit(kit.stone_frame(crest.size, seed=side, fill=kit.shade(TEAM[side], 0.7)), crest.topleft)
        icon = self.assets.unit_icon(p.faction.name, Role.MELEE, 34, 38)
        if side == 1:
            icon = pygame.transform.flip(icon, True, False)
        screen.blit(icon, icon.get_rect(center=(crest.centerx, crest.centery + 1)))

        bw = 252
        bx = crest.right + 8 if side == 0 else crest.x - 8 - bw
        name = outline_text(make_font(18, "title"), p.faction.name, kit.CREAM, kit.INK, 2)
        tag = outline_text(make_font(13, "bold"), f"{who} · ур. армии {p.lvl}", (236, 222, 190), kit.INK, 2)
        if side == 0:
            screen.blit(name, (bx - 2, 2))
            screen.blit(tag, (bx + name.get_width() + 4, 6))
        else:
            screen.blit(name, (bx + bw - name.get_width() + 2, 2))
            screen.blit(tag, (bx + bw - name.get_width() - 4 - tag.get_width(), 6))
        ratio = max(0.0, p.castle.hp / p.castle.max_hp)
        g = self.ghost[side]
        g = max(ratio, g - 0.003) if g > ratio else ratio
        self.ghost[side] = g
        rect = pygame.Rect(bx, 30, bw, 22)
        drop_shadow(screen, rect, 3, 70)
        color = TEAM[side] if ratio > 0.3 else (220, 70, 50)
        kit.pixel_bar(screen, rect, ratio, color, ghost=g)
        txt = outline_text(make_font(14, "bold"), f"{fmt_int(max(0, p.castle.hp))} / {fmt_int(p.castle.max_hp)}", kit.CREAM, kit.INK, 2)
        screen.blit(txt, (rect.centerx - txt.get_width() // 2, rect.centery - txt.get_height() // 2))
        # активные зелья — маленькие значки под полоской
        x = bx if side == 0 else bx + bw - 22
        for item in ("rage", "stone"):
            if p.buff_active(item, world.t):
                ic = self.assets.item_icon(item, 20)
                screen.blit(ic, (x, 54))
                left = int(p.buff_until[item] - world.t)
                t = outline_text(make_font(12, "bold"), str(left), kit.CREAM, kit.INK, 2)
                screen.blit(t, (x + 16, 56))
                x += 40 if side == 0 else -40

    def _center(self, screen, world, me, mode: str, speed: int, paused: bool) -> None:
        cx = WIDTH // 2
        # кошель с золотом — деревянная табличка
        gold_r = pygame.Rect(cx - 284, 6, 156, 52)
        drop_shadow(screen, gold_r, 3, 70)
        screen.blit(kit.wood_panel(gold_r.size, seed=5), gold_r.topleft)
        screen.blit(self.assets.gold_icon(30), (gold_r.x + 8, gold_r.y + 10))
        gt = outline_text(make_font(16, "pixel"), f"{int(me.gold)}", (255, 220, 110), kit.INK, 2)
        screen.blit(gt, (gold_r.x + 44, gold_r.y + 8))
        inc = income_rate(world.t, world.econ)
        it = outline_text(make_font(13, "bold"), f"+{inc:g} в минуту", (230, 240, 190), kit.INK, 2)
        screen.blit(it, (gold_r.x + 43, gold_r.y + 28))

        # таймер — пергамент
        tr = pygame.Rect(cx - 112, 4, 224, 56)
        drop_shadow(screen, tr, 3, 70)
        screen.blit(kit.parchment(tr.size, seed=9), tr.topleft)
        t = make_font(24, "pixel").render(fmt_time(world.t), False, kit.TEXT_INK)
        screen.blit(t, (cx - t.get_width() // 2, tr.y + 8))
        sd_at = world.econ["sd"] * 60
        if world.t >= sd_at:
            sub = make_font(13, "bold").render(f"внезапная смерть · замки x{world.sudden_death_mult():.1f}", True, P_BAD)
        else:
            sub = make_font(13, "bold").render(f"внезапная смерть через {fmt_time(sd_at - world.t)}", True, P_MUTED)
        screen.blit(sub, (cx - sub.get_width() // 2, tr.y + 36))

        # скорость / пауза
        sp = self.speed_rect
        drop_shadow(screen, sp, 3, 70)
        screen.blit(kit.wood_panel(sp.size, seed=6), sp.topleft)
        if paused:
            top = outline_text(make_font(16, "pixel"), "ПАУЗА", (255, 200, 90), kit.INK, 2)
        else:
            top = outline_text(make_font(16, "pixel"), f"x{speed}", kit.CREAM, kit.INK, 2)
        screen.blit(top, (sp.x + 12, sp.y + 8))
        if not paused:
            m = outline_text(make_font(14, "bold"), MODE_LABELS.get(mode, mode).lower(), (236, 222, 190), kit.INK, 2)
            screen.blit(m, (sp.x + 12 + top.get_width() + 8, sp.y + 7))
        h = outline_text(make_font(12, "bold"), "F скорость · Пробел пауза", (220, 200, 170), kit.INK, 2)
        screen.blit(h, (sp.x + 10, sp.y + 30))


# --- нижняя доска ---------------------------------------------------------------

CARD_W = 178
CARD_H = 104
CARD_Y = PANEL_Y + 9
ITEM_W = 70
SHOP_X = 894


class BuildPanel:
    """4 карточки зданий + апгрейд армии + лавка из 5 предметов."""

    def __init__(self, assets: Assets) -> None:
        self.assets = assets
        self.cards: dict[Role, pygame.Rect] = {}
        x = 10
        for role in ROLE_ORDER:
            self.cards[role] = pygame.Rect(x, CARD_Y, CARD_W, CARD_H)
            x += CARD_W + 6
        self.upgrade_rect = pygame.Rect(x + 2, CARD_Y, 136, CARD_H)
        self.items: dict[str, pygame.Rect] = {}
        for i, item in enumerate(SHOP_ORDER):
            self.items[item] = pygame.Rect(SHOP_X + i * (ITEM_W + 6), CARD_Y, ITEM_W, CARD_H)
        self.time = 0.0
        self.flash: dict[str, float] = {}

    def hit(self, pos) -> Role | str | None:
        for role, rect in self.cards.items():
            if rect.collidepoint(pos):
                return role
        if self.upgrade_rect.collidepoint(pos):
            return "upgrade"
        for item, rect in self.items.items():
            if rect.collidepoint(pos):
                return "shop:" + item
        if pos[1] >= PANEL_Y:
            return "panel"
        return None

    def ping(self, key: str) -> None:
        self.flash[key] = 0.35

    def draw(self, screen: pygame.Surface, player, *, mouse, pressed: bool, placing: Optional[Role], hint_role: Optional[Role],
             dt: float, world=None, armed: Optional[str] = None) -> None:
        self.time += dt
        for k in list(self.flash):
            self.flash[k] -= dt
            if self.flash[k] <= 0:
                del self.flash[k]
        board = pygame.Rect(0, PANEL_Y - 4, WIDTH, HEIGHT - PANEL_Y + 4)
        screen.blit(kit.wood_panel(board.size, tone=kit.WOOD, plank=22, seed=1), board.topleft)
        # верхняя балка доски
        beam = pygame.Rect(0, PANEL_Y - 8, WIDTH, 8)
        pygame.draw.rect(screen, kit.INK, beam)
        pygame.draw.rect(screen, kit.WOOD_LIGHT, beam.inflate(0, -4))
        pygame.draw.line(screen, kit.WOOD_HI, (0, beam.y + 2), (WIDTH, beam.y + 2), 2)
        for i, role in enumerate(ROLE_ORDER):
            bt = player.faction.building_by_role(role)
            reason = player.buy_block_reason(i)
            self._card(screen, player, bt, role, i, self.cards[role], reason, mouse, pressed, placing == role, hint_role == role)
        self._upgrade(screen, player, mouse, pressed)
        # табличка «Лавка» над предметами
        lab = outline_text(make_font(13, "bold"), "лавка", kit.CREAM, kit.INK, 2)
        tab = pygame.Rect(SHOP_X + 150, PANEL_Y - 26, lab.get_width() + 20, 20)
        screen.blit(kit.wood_panel(tab.size, nails=False, seed=2), tab.topleft)
        screen.blit(lab, (tab.x + 10, tab.y + 1))
        if world is not None:
            for item in SHOP_ORDER:
                self._item(screen, player, world, item, self.items[item], mouse, pressed, armed == item)

    # карточка здания — пергамент
    def _card(self, screen, player, bt, role, idx, rect, reason, mouse, pressed, selected, hinted) -> None:
        hover = rect.collidepoint(mouse)
        enabled = reason is None
        r = rect.copy()
        if selected:
            r.y -= 6
        elif hover and pressed:
            r.y += 2
        elif hover:
            r.y -= 2
        drop_shadow(screen, r, 4, 110)
        screen.blit(kit.parchment(r.size, seed=idx + 20, tone=kit.PAPER if enabled else (206, 192, 164)), r.topleft)
        if selected:
            pygame.draw.rect(screen, kit.INK, r.inflate(6, 6), 2)
            pygame.draw.rect(screen, kit.GOLD, r.inflate(2, 2), 3)
        elif hinted:
            p = 0.5 + 0.5 * math.sin(self.time * 4)
            c = kit.shade(kit.GOLD, 0.8 + 0.3 * p)
            pygame.draw.rect(screen, c, r.inflate(2, 2), 2)
        # плинтус под иконкой
        ib = pygame.Rect(r.x + 6, r.y + 12, 64, 86)
        screen.blit(kit.plinth((60, 22), "idle", seed=idx), (ib.x + 2, ib.bottom - 22))
        ic = self.assets.building(player.faction.name, role, 64, 70)
        if not enabled:
            ic = self.assets._get(("bld_dim", player.faction.name, role), lambda: _dim_copy(ic))
        screen.blit(ic, ic.get_rect(midbottom=(ib.centerx, ib.bottom - 8)))
        # клавиша
        cap = kit.key_cap(make_font(8, "pixel").render(str(idx + 1), False, kit.TEXT_INK))
        screen.blit(cap, (r.x + 4, r.y + 4))

        tx = r.x + 72
        tw = r.right - tx - 5
        screen.blit(make_font(8, "pixel").render(ROLE_LABELS[role].upper()[:12], False, P_ROLE[role]), (tx, r.y + 9))
        nf = fit_font(bt.name, tw, (18, 17, 16, 15, 14, 13), "title")
        screen.blit(nf.render(bt.name, True, P_TEXT if enabled else P_MUTED), (tx, r.y + 21))
        screen.blit(self.assets.gold_icon(18), (tx, r.y + 47))
        afford = player.gold >= bt.cost
        screen.blit(make_font(16, "pixel").render(str(bt.cost), False, P_GOLD if afford else P_BAD), (tx + 21, r.y + 49))
        sp = make_font(13, "bold").render(f"{bt.spawn:g}с", True, P_MUTED)
        screen.blit(sp, (r.right - 7 - sp.get_width(), r.y + 50))
        if reason and reason != "не хватает золота":
            short = {"максимум 2 ульт-здания": "лимит: 2 ульта", "все 12 мест заняты": "нет мест"}.get(reason, reason)
            f = fit_font(short, tw - 6, (13, 12, 11), "bold")
            stamp = f.render(short, True, P_BAD)
            sr = pygame.Rect(tx - 3, r.y + 74, stamp.get_width() + 6, 20)
            pygame.draw.rect(screen, P_BAD, sr, 2)
            screen.blit(stamp, stamp.get_rect(center=sr.center))
        else:
            u = bt.unit
            st = f"HP {u.hp * player.upgrade_mult:.0f} · урон {u.dmg * player.upgrade_mult:.0f}"
            stats = fit_font(st, tw, (13, 12, 11), "bold").render(st, True, P_MUTED)
            screen.blit(stats, (tx, r.y + 76))
        if hinted:
            rib = kit.ribbon((76, 20), kit.GOLD_DARK)
            screen.blit(rib, (r.right - 70, r.y - 12))
            t = make_font(8, "pixel").render("СОВЕТ", False, kit.CREAM)
            screen.blit(t, (r.right - 70 + 38 - t.get_width() // 2, r.y - 6))

    def _upgrade(self, screen, player, mouse, pressed) -> None:
        r = self.upgrade_rect
        hover = r.collidepoint(mouse)
        maxed = player.lvl >= UPG_MAX
        cost = None if maxed else UPG_COST[player.lvl]
        can = cost is not None and player.gold >= cost
        state = "disabled" if not can else ("pressed" if hover and pressed else ("hover" if hover else "normal"))
        img = kit.wood_button((r.w, r.h - 4), state, kit.BLUE if can else None)
        screen.blit(img, r.topleft)
        dy = 4 if state == "pressed" else 0
        if self.flash.get("upgrade"):
            pygame.draw.rect(screen, kit.GOLD, r.inflate(4, 4), 3)
        t = outline_text(make_font(16, "title"), "Армия", kit.CREAM, kit.INK, 2)
        screen.blit(t, (r.x + 10, r.y + 6 + dy))
        cap = kit.key_cap(make_font(8, "pixel").render("U", False, kit.TEXT_INK))
        screen.blit(cap, (r.right - cap.get_width() - 6, r.y + 7 + dy))
        for i in range(UPG_MAX):
            box = pygame.Rect(r.x + 10 + i * 23, r.y + 34 + dy, 19, 14)
            pygame.draw.rect(screen, kit.INK, box)
            pygame.draw.rect(screen, kit.GOLD if i < player.lvl else (90, 70, 56), box.inflate(-4, -4))
        if cost is not None:
            screen.blit(self.assets.gold_icon(18), (r.x + 10, r.y + 56 + dy))
            ct = outline_text(make_font(16, "pixel"), str(cost), (255, 220, 110) if can else (240, 150, 130), kit.INK, 2)
            screen.blit(ct, (r.x + 32, r.y + 56 + dy))
            st = outline_text(make_font(12, "bold"), f"+{int(UPG_BONUS * 100)}% HP и урона", (230, 222, 200), kit.INK, 2)
            screen.blit(st, (r.x + 9, r.y + 78 + dy))
        else:
            st = outline_text(make_font(16, "title"), "максимум", (200, 240, 160), kit.INK, 2)
            screen.blit(st, (r.x + 12, r.y + 60))

    def _item(self, screen, player, world, item: str, r: pygame.Rect, mouse, pressed: bool, armed: bool) -> None:
        hover = r.collidepoint(mouse)
        reason = shop.block_reason(player, world, item)
        c = shop.cost(player, item)
        cd_left = shop.cooldown_left(player, world, item)
        active = item in ("rage", "stone") and player.buff_active(item, world.t)
        ok = reason is None
        state = "pressed" if (hover and pressed) or armed else ("hover" if hover else "normal")
        if not ok and not armed:
            state = "disabled" if cd_left <= 0 else "normal"
        sq = pygame.Rect(r.x, r.y, r.w, 66)
        accent = kit.GREEN_DARK if active else (kit.RED if armed else None)
        screen.blit(kit.wood_button((sq.w, sq.h - 4), state, accent), sq.topleft)
        dy = 4 if state == "pressed" else 0
        ic = self.assets.item_icon(item, 44)
        if not ok and cd_left <= 0:
            ic = self.assets._get(("item_dim", item), lambda: _dim_copy(ic))
        screen.blit(ic, ic.get_rect(center=(sq.centerx, sq.y + 30 + dy)))
        # перезарядка: тёмная «штора» сверху вниз и секунды
        total = SHOP.get(item, {}).get("cd", 0)
        if cd_left > 0 and total:
            k = cd_left / total
            h = int((sq.h - 10) * k)
            sh = pygame.Surface((sq.w - 8, max(1, h)), pygame.SRCALPHA)
            sh.fill((*kit.INK, 150))
            screen.blit(sh, (sq.x + 4, sq.y + 4 + (sq.h - 10 - h)))
            t = outline_text(make_font(16, "pixel"), f"{int(math.ceil(cd_left))}", kit.CREAM, kit.INK, 2)
            screen.blit(t, t.get_rect(center=(sq.centerx, sq.y + 30)))
        if item == "sword":
            lv = outline_text(make_font(8, "pixel"), f"{player.sword}/{len(SWORD_COST)}", kit.CREAM, kit.INK, 1)
            screen.blit(lv, (sq.right - lv.get_width() - 5, sq.y + 46 + dy))
        if item == "repair":
            left = SHOP["repair"]["uses"] - player.repairs
            lv = outline_text(make_font(8, "pixel"), f"x{left}", kit.CREAM, kit.INK, 1)
            screen.blit(lv, (sq.right - lv.get_width() - 5, sq.y + 46 + dy))
        cap = kit.key_cap(make_font(8, "pixel").render(SHOP_KEYS[item], False, kit.TEXT_INK))
        screen.blit(cap, (sq.x + 3, sq.y + 3 + dy))
        if self.flash.get(item):
            pygame.draw.rect(screen, kit.GOLD, sq.inflate(4, 4), 3)
        # ярлык с ценой
        tag = pygame.Rect(r.x + 2, r.y + 70, r.w - 4, 32)
        screen.blit(kit.parchment(tag.size, seed=hash(item) % 7), tag.topleft)
        name = make_font(12, "bold").render(SHOP_SHORT[item], True, P_TEXT)
        screen.blit(name, (tag.centerx - name.get_width() // 2, tag.y + 2))
        if c is None:
            v = make_font(8, "pixel").render("MAX", False, P_GOOD)
            screen.blit(v, (tag.centerx - v.get_width() // 2, tag.y + 19))
        else:
            v = make_font(8, "pixel").render(str(c), False, P_GOLD if player.gold >= c else P_BAD)
            coin = self.assets.gold_icon(11)
            w = coin.get_width() + 3 + v.get_width()
            x0 = tag.centerx - w // 2
            screen.blit(coin, (x0, tag.y + 17))
            screen.blit(v, (x0 + coin.get_width() + 3, tag.y + 19))

    def tooltip(self, screen, player, role: Role) -> None:
        idx = ROLE_ORDER.index(role)
        bt = player.faction.building_by_role(role)
        rect = self.cards[role]
        draw_tooltip(
            screen,
            (rect.centerx, PANEL_Y - 10),
            f"{bt.name} — {ROLE_LABELS[role].lower()}",
            building_lines(bt, player.upgrade_mult, player.buy_block_reason(idx)),
            width=350,
            title_color=P_ROLE[role],
        )

    def item_tooltip(self, screen, player, world, item: str) -> None:
        rect = self.items[item]
        draw_tooltip(screen, (rect.centerx, PANEL_Y - 10), SHOP_NAMES[item], shop_lines(player, world, item), width=320)

    def upgrade_tooltip(self, screen, player) -> None:
        r = self.upgrade_rect
        lines = [(f"Все твои воины получают +{int(UPG_BONUS * 100)}% HP и урона за уровень.", P_TEXT),
                 (f"Уровень {player.lvl}/{UPG_MAX}. Действует и на новых, и на уже живых.", P_MUTED)]
        draw_tooltip(screen, (r.centerx, PANEL_Y - 10), "Усиление армии", lines, width=300)


def _dim_copy(s: pygame.Surface) -> pygame.Surface:
    out = s.copy()
    out.fill((150, 140, 130, 255), special_flags=pygame.BLEND_RGBA_MULT)
    return out


def building_tooltip(screen, assets, player, building, anchor, own: bool) -> None:
    bt = building.building_type
    u = bt.unit
    pct = int(building.progress * 100)
    lines: list[tuple[str, tuple]] = [
        (f"{ROLE_LABELS[bt.role]}  ·  юнит каждые {bt.spawn * building.spawn_mult:g} с", P_ROLE[bt.role]),
        (f"Следующий юнит: {pct}%  (через {max(0.0, building.timer):.1f} с)", P_GOLD),
        (f"Выпущено юнитов: {building.spawned}", P_MUTED),
    ]
    if building.spawn_mult < 1.0:
        lines.append(("Соседство: рядом такое же здание, спавн на 8% быстрее", P_GOOD))
    lines.append(("-", P_MUTED))
    lines += unit_lines(u, player.upgrade_mult)
    if own:
        lines += [
            ("-", P_MUTED),
            ("Перетащи мышью — переставить бесплатно", P_MUTED),
            (f"ПКМ или X — продать за {int(bt.cost * SELL_REFUND)} зол.", P_GOLD),
        ]
    draw_tooltip(screen, anchor, f"{bt.name}" + ("" if own else "  (враг)"), lines, width=330, title_color=P_TEXT)
