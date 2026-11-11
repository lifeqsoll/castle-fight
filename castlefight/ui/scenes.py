"""Экраны игры: живое меню, «как играть», выбор фракции, матч (+пауза и итоги)."""

from __future__ import annotations

import math
import random
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import pygame

from castlefight.ai.bots import POOL, CounterBot
from castlefight.core import commands, shop
from castlefight.core.game import Game
from castlefight.data.balance import SELL_REFUND, SLOTS, STRIKE_CD
from castlefight.data.enums import Role
from castlefight.data.factions import FACTION_NAMES, FACTIONS
from castlefight.ui import kit
from castlefight.ui.hud import BuildPanel, TopBar, building_tooltip, fmt_int, fmt_time
from castlefight.ui.input import role_from_key, shop_from_key
from castlefight.ui.layout import screen_to_x, slot_at, slot_rect, x_to_screen
from castlefight.ui.renderer import BattleRenderer, FieldUI
from castlefight.ui.text import fit_font, make_font, outline_text, wrap
from castlefight.ui.theme import (
    FACTION_BLURBS,
    FACTION_COLORS,
    FACTION_LORE,
    HEIGHT,
    LANE_X0,
    LANE_X1,
    LANE_Y,
    MODE_HELP,
    MODE_LABELS,
    P_BAD,
    P_GOLD,
    P_GOOD,
    P_MUTED,
    P_ROLE,
    P_TEXT,
    PANEL_Y,
    ROLE_LABELS,
    ROLE_ORDER,
    SHOP_NAMES,
    TEAM,
    TOP_H,
    WIDTH,
)
from castlefight.ui.widgets import Button, blit_center, drop_shadow, hgradient, pixel_title, title_text

if TYPE_CHECKING:
    from castlefight.ui.main import App

LOGIC_DT = 0.2
ROLE_INDEX = {r: i for i, r in enumerate(ROLE_ORDER)}


class Scene:
    def __init__(self, app: "App") -> None:
        self.app = app

    def handle(self, e: pygame.event.Event) -> None: ...

    def update(self, dt: float) -> None: ...

    def draw(self, screen: pygame.Surface) -> None: ...


_DIM: dict[tuple, pygame.Surface] = {}


def dim(screen: pygame.Surface, alpha: int, color=(40, 26, 16)) -> None:
    """Лёгкое тёплое затемнение (не чёрное): кадр рисуется на непрозрачном холсте."""
    key = (alpha, color)
    s = _DIM.get(key)
    if s is None:
        s = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        s.fill((*color, alpha))
        _DIM[key] = s
    screen.blit(s, (0, 0))


def draw_backdrop(screen: pygame.Surface, assets, alpha: int = 70) -> None:
    screen.blit(assets.bg, (0, 0))
    dim(screen, alpha)


def _buttons_pressed(buttons, e) -> None:
    if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
        for b in buttons:
            b.pressed = b.rect.collidepoint(e.pos)
    elif e.type == pygame.MOUSEBUTTONUP and e.button == 1:
        for b in buttons:
            b.pressed = False


def ribbon_title(screen, text: str, cx: int, y: int, color=kit.RED, size: int = 30, min_w: int = 320) -> pygame.Rect:
    t = title_text(text, size)
    w = max(min_w, t.get_width() + 110)
    h = t.get_height() + 14
    r = pygame.Rect(0, 0, w, h)
    r.midtop = (cx, y)
    screen.blit(kit.ribbon(r.size, color), r.topleft)
    screen.blit(t, t.get_rect(center=(cx, r.centery - 2)))
    return r


# ---------------------------------------------------------------------------
# Главное меню — живое поле боя
# ---------------------------------------------------------------------------

MENU_TIPS = [
    "Кликай по вражеским воинам — герой бьёт вместе с армией. Меч в лавке усиливает удар.",
    "Бомба (R) накрывает толпу: выбери место на дороге и отойди от взрыва.",
    "Одинаковые здания рядом выпускают воинов на 8% чаще — «Соседство».",
    "Не трать всё сразу: каждые 30 с «Казна» платит 3% от запаса золота.",
    "Ненужное здание можно продать: ПКМ по нему или X — вернётся 60% цены.",
    "Тяжёлая броня боится магии, лёгкая — рубящего урона. Смотри подсказки карточек.",
]


class MenuScene(Scene):
    def __init__(self, app: "App") -> None:
        super().__init__(app)
        self.t = 0.0
        self.tip_i = random.randrange(len(MENU_TIPS))
        self.tip_t = 0.0
        post_x = 96
        f = make_font(26, "title")
        self.play = Button(pygame.Rect(post_x - 10, 398, 270, 58), "Играть", kind="primary", font=make_font(30, "title"), key="Enter")
        self.lan = Button(pygame.Rect(post_x + 2, 466, 250, 50), "По сети", font=f, key="N")
        self.howto = Button(pygame.Rect(post_x + 6, 526, 240, 50), "Как играть", font=f, key="H")
        self.quit = Button(pygame.Rect(post_x - 2, 586, 200, 50), "Выход", font=f, key="Esc")
        self.buttons = [self.play, self.lan, self.howto, self.quit]
        self.post_x = post_x
        self._new_demo()

    # демо-матч ботов на фоне
    def _new_demo(self) -> None:
        rnd = random.Random()
        a, b = rnd.sample(FACTION_NAMES, 2)
        self.demo = Game(a, b, rnd.choice(POOL)(), rnd.choice(POOL)(), mode="turbo", seed=rnd.randrange(1 << 20))
        for p in self.demo.players:
            p.gold += 420
        # прокрутить начало, чтобы армии уже сошлись
        for _ in range(int(48 / LOGIC_DT)):
            self.demo.step()
        self.renderer = BattleRenderer(self.app.screen, self.app.assets)
        self.renderer.after_step(self.demo.world)
        self.acc = 0.0

    def handle(self, e) -> None:
        _buttons_pressed(self.buttons, e)
        if e.type == pygame.KEYDOWN:
            if e.key in (pygame.K_RETURN, pygame.K_SPACE):
                self.app.set_scene(SetupScene(self.app))
            elif e.key in (pygame.K_h, pygame.K_F1):
                self.app.set_scene(HowToScene(self.app))
            elif e.key == pygame.K_n:
                self.app.set_scene(NetMenuScene(self.app))
            elif e.key == pygame.K_ESCAPE:
                self.app.running = False
        if e.type == pygame.MOUSEBUTTONUP and e.button == 1:
            if self.play.hit(e.pos):
                self.app.set_scene(SetupScene(self.app))
            elif self.lan.hit(e.pos):
                self.app.set_scene(NetMenuScene(self.app))
            elif self.howto.hit(e.pos):
                self.app.set_scene(HowToScene(self.app))
            elif self.quit.hit(e.pos):
                self.app.running = False
            elif self.tip_rect().collidepoint(e.pos):
                self.tip_i = (self.tip_i + 1) % len(MENU_TIPS)
                self.tip_t = 0.0

    def update(self, dt: float) -> None:
        self.t += dt
        self.tip_t += dt
        if self.tip_t > 7.0:
            self.tip_t = 0.0
            self.tip_i = (self.tip_i + 1) % len(MENU_TIPS)
        w = self.demo.world
        self.acc += dt * 1.5
        n = 0
        while self.acc >= LOGIC_DT and n < 5:
            self.acc -= LOGIC_DT
            self.renderer.before_step(w)
            alive = self.demo.step()
            self.renderer.after_step(w)
            n += 1
            if not alive or w.t > 300:
                self._new_demo()
                return
        self.renderer.update(dt * 1.5)

    def tip_rect(self) -> pygame.Rect:
        return pygame.Rect(WIDTH - 404, HEIGHT - 150, 380, 118)

    def draw(self, screen) -> None:
        alpha = max(0.0, min(1.0, self.acc / LOGIC_DT))
        self.renderer.draw(self.demo.world, alpha, FieldUI(show_zones=False))
        # затемняем только левую часть — под вывеску и логотип
        screen.blit(hgradient((560, HEIGHT), (36, 22, 12), 190, 0), (0, 0))
        self._logo(screen)
        self._post(screen)
        for b in self.buttons:
            b.draw(screen, self.app.mouse)
        self._tip(screen)
        # кто сражается на фоне
        a, b = self.demo.players
        cap = outline_text(make_font(14, "bold"), f"на фоне: {a.faction.name} против {b.faction.name} · {fmt_time(self.demo.world.t)}",
                           (236, 222, 190), kit.INK, 2)
        screen.blit(cap, (WIDTH - cap.get_width() - 20, 12))

    def _logo(self, screen) -> None:
        x, y = 44, 40
        bob = int(math.sin(self.t * 1.6) * 2)
        l1 = pixel_title("CASTLE", 48, kit.CREAM, kit.INK, 6)
        l2 = pixel_title("FIGHT", 48, (250, 196, 70), kit.INK, 6)
        screen.blit(l1, (x, y + bob))
        # скрещённые мечи между словами
        sx = x + l2.get_width() + 30
        sy = y + l1.get_height() + 8 + bob
        screen.blit(l2, (x, y + l1.get_height() - 2 + bob))
        sw = self.app.assets.item_icon("sword", 56)
        screen.blit(pygame.transform.rotate(sw, 35), (sx - 4, sy - 10))
        screen.blit(pygame.transform.rotate(pygame.transform.flip(sw, True, False), -35), (sx + 14, sy - 10))
        rib = pygame.Rect(x - 8, y + l1.get_height() + l2.get_height() + 2 + bob, 380, 40)
        screen.blit(kit.ribbon(rib.size, kit.RED), rib.topleft)
        sub = outline_text(make_font(18, "title"), "битва замков на одной дороге", kit.CREAM, kit.INK, 2)
        screen.blit(sub, sub.get_rect(center=(rib.centerx, rib.centery - 2)))

    def _post(self, screen) -> None:
        """Деревянный столб, к которому прибиты таблички-кнопки."""
        x = self.post_x + 90
        post = pygame.Rect(x, 386, 26, HEIGHT - 386)
        drop_shadow(screen, post, 5, 80)
        screen.blit(kit.wood_panel(post.size, tone=kit.WOOD, plank=40, nails=False, vertical=True, seed=3), post.topleft)
        cap = pygame.Rect(x - 6, 380, 38, 12)
        screen.blit(kit.wood_panel(cap.size, tone=kit.WOOD_DARK, nails=False), cap.topleft)
        # верёвки к табличкам
        for b in self.buttons:
            for dx in (24, b.rect.w - 24):
                pygame.draw.line(screen, kit.INK, (b.rect.x + dx, b.rect.y - 10), (b.rect.x + dx, b.rect.y + 2), 3)
        hint = outline_text(make_font(14, "bold"), "Enter — играть · N — по сети · H — правила · Esc — выход", (236, 222, 190), kit.INK, 2)
        screen.blit(hint, (x + 44, HEIGHT - 30))

    def _tip(self, screen) -> None:
        r = self.tip_rect()
        drop_shadow(screen, r, 5, 90)
        screen.blit(kit.parchment(r.size, seed=12), r.topleft)
        # гвоздь
        pygame.draw.rect(screen, kit.INK, (r.centerx - 4, r.y + 4, 8, 8))
        pygame.draw.rect(screen, (160, 156, 150), (r.centerx - 2, r.y + 6, 4, 4))
        head = make_font(8, "pixel").render("СОВЕТ ПОЛКОВОДЦУ", False, P_BAD)
        screen.blit(head, (r.x + 16, r.y + 16))
        bf = make_font(16, "bold")
        y = r.y + 34
        for ln in wrap(bf, MENU_TIPS[self.tip_i], r.w - 32)[:4]:
            screen.blit(bf.render(ln, True, P_TEXT), (r.x + 16, y))
            y += bf.height()
        # точки-страницы
        for i in range(len(MENU_TIPS)):
            c = P_TEXT if i == self.tip_i else kit.PAPER_EDGE
            pygame.draw.rect(screen, c, (r.right - 16 - (len(MENU_TIPS) - i) * 10, r.bottom - 14, 6, 6))


# ---------------------------------------------------------------------------
# Как играть
# ---------------------------------------------------------------------------


HOWTO_PAGES = [
    ("Основы", [
        "Цель — разрушить вражеский замок. Твой замок слева (синий), враг — справа (красный).",
        "Ты не водишь армию: строишь здания, а они сами по таймеру выпускают воинов.",
        "Воины идут по дороге и дерутся сами. Твоя работа — экономика, состав армии, лавка и удары героя.",
        "Золото: стартовый запас, доход каждую минуту (видно в верхней панели) и награда за каждого убитого врага.",
        "Режимы: «обычный» — спокойный темп; «турбо» — больше золота и всё быстрее.",
        "Если матч затянулся, начинается внезапная смерть: замки слабеют. По тайм-ауту побеждает замок с большим HP.",
    ]),
    ("Здания и армия", [
        "У каждой фракции 4 здания: ближний бой (1), дальний бой (2), призыв/магия (3), ульт (4).",
        "Выбери карточку внизу (клик или 1–4) и кликни по свободной клетке своей зоны. Shift — ставить ещё.",
        "12 мест в зоне, ульт-зданий — не больше двух. Каждая постройка появляется и на поле — городок у замка.",
        "Перетащи здание мышью на другую клетку, чтобы переставить (городок на поле тоже переедет).",
        "Полоска под зданием — время до следующего воина. Наведи на здание — увидишь его характеристики.",
        "U — апгрейд армии: +10% HP и урона всем воинам (до 5 уровней). Покупается за золото.",
    ]),
    ("Урон и броня", [
        "У каждого воина тип урона и тип брони. Множитель решает бой — подбирай контры к армии врага.",
        "Подсказки карточек показывают, против кого здание сильно. Значок «совет» — подсказка ИИ-советника.",
        "Совет обучен на тысячах матчей ботов (модель — градиентный бустинг по деревьям).",
        "Замки сами стреляют по ближайшему врагу в радиусе — не дай толпе дойти до стен.",
        "Ниже 50% HP по замку идут трещины, ниже 25% — копоть и дым.",
    ]),
    ("Лавка", [
        "Q — Зелье ярости: твои воины бьют сильнее на 30 с.",
        "W — Каменная кожа: твои воины получают меньше урона 30 с.",
        "E — Ремонт: чинит 8% HP замка, не больше 3 раз за матч.",
        "R — Бомба: выбери место на дороге кликом — через секунду взрыв по всем врагам в радиусе.",
        "T — Меч героя: повышает урон твоего клика (4 уровня).",
        "У каждого предмета своя перезарядка — она видна на кнопке. Бот тоже пользуется лавкой.",
    ]),
    ("Удар героя", [
        "Клик ЛКМ по вражескому воину — удар героя. Перезарядка 0,4 с (кольцо у курсора).",
        "Урон удара растёт с уровнем меча: 14 → 22 → 32 → 44 → 58.",
        "Бот бьёт по твоим воинам по тем же правилам: примерно 1–1,5 удара в секунду, и тоже покупает меч.",
        "Вражеские удары видны красными цифрами урона над твоими воинами.",
    ]),
    ("Механики", [
        "Соседство: одинаковые здания на соседних клетках выпускают воинов на 8% чаще (зелёный значок).",
        "Казна: каждые 30 с ты получаешь 3% от запаса золота (не больше 6) — копить иногда выгодно.",
        "Продажа: ПКМ по своему зданию или X под курсором — вернётся 60% цены. Подтверди «Да» или Enter.",
        "Внезапная смерть: после долгого матча замки получают всё больше урона.",
    ]),
    ("Управление", [
        "1–4 — выбрать здание · ЛКМ по клетке — поставить · Shift — ставить ещё · ПКМ / Esc — отмена.",
        "Перетаскивание — переставить · ПКМ или X — продать · Enter — подтвердить продажу.",
        "ЛКМ по врагу — удар героя · Q W E R T — лавка · U — апгрейд армии.",
        "F — скорость x1/x2/x4 · Пробел — пауза · Esc — меню паузы (в сетевой игре пауза и скорость отключены).",
        "В меню: Enter — играть, N — по сети, H или F1 — эти правила. Здесь: ← → — листать.",
    ]),
    ("Игра по сети", [
        "Оба компьютера — в одной сети (один Wi-Fi или роутер).",
        "Один жмёт «По сети» → «Создать игру», выбирает фракцию и ждёт. На экране его адрес и порт.",
        "Второй жмёт «Подключиться»: найденные игры появляются в списке сами — кликни по нужной.",
        "Не нашлась? Введи IP и порт хоста вручную (по умолчанию 47821) и нажми «Подключиться».",
        "Windows спросит про брандмауэр — разреши доступ в частных сетях. Порты: UDP 47820 (поиск), TCP 47821 (игра).",
        "Хост слева (синий), гость справа (красный). Если связь пропала — вернёшься в меню с сообщением.",
    ]),
]


DMG_RU = {"slash": "рубящий", "pierce": "колющий", "magic": "магия", "castle": "замок"}
ARMOR_RU = {"L": "лёгкая", "M": "средняя", "H": "тяжёлая", "S": "рой", "R": "камень", "C": "замок"}


class HowToScene(Scene):
    PAGES = HOWTO_PAGES

    def __init__(self, app: "App", page: int = 0) -> None:
        super().__init__(app)
        self.page = page
        self.back = Button(pygame.Rect(40, 640, 200, 54), "В меню", key="Esc")
        self.prev = Button(pygame.Rect(WIDTH // 2 - 230, 640, 200, 54), "Назад", key="A")
        self.next = Button(pygame.Rect(WIDTH // 2 + 30, 640, 200, 54), "Дальше", kind="primary", key="D")
        self.go = Button(pygame.Rect(WIDTH - 300, 640, 260, 54), "К фракциям", kind="go", key="Enter")
        self.buttons = [self.back, self.prev, self.next, self.go]

    def flip(self, d: int) -> None:
        self.page = max(0, min(len(self.PAGES) - 1, self.page + d))

    def handle(self, e) -> None:
        _buttons_pressed(self.buttons, e)
        if e.type == pygame.KEYDOWN:
            if e.key == pygame.K_ESCAPE:
                self.app.set_scene(MenuScene(self.app))
            elif e.key in (pygame.K_RETURN,):
                self.app.set_scene(SetupScene(self.app))
            elif e.key in (pygame.K_RIGHT, pygame.K_d, pygame.K_SPACE, pygame.K_PAGEDOWN):
                self.flip(1)
            elif e.key in (pygame.K_LEFT, pygame.K_a, pygame.K_PAGEUP):
                self.flip(-1)
        if e.type == pygame.MOUSEBUTTONUP and e.button == 1:
            if self.back.hit(e.pos):
                self.app.set_scene(MenuScene(self.app))
            elif self.prev.hit(e.pos):
                self.flip(-1)
            elif self.next.hit(e.pos):
                self.flip(1)
            elif self.go.hit(e.pos):
                self.app.set_scene(SetupScene(self.app))
            for i, r in enumerate(self._dots()):
                if r.inflate(8, 8).collidepoint(e.pos):
                    self.page = i
        if e.type == pygame.MOUSEWHEEL:
            self.flip(-e.y)

    def _dots(self) -> list[pygame.Rect]:
        n = len(self.PAGES)
        x0 = WIDTH // 2 - n * 14
        return [pygame.Rect(x0 + i * 28, 604, 14, 14) for i in range(n)]

    def draw(self, screen) -> None:
        draw_backdrop(screen, self.app.assets, 60)
        sc = pygame.Rect(90, 70, WIDTH - 180, 560)
        drop_shadow(screen, sc, 6, 100)
        screen.blit(kit.scroll(sc.size, seed=4), sc.topleft)
        ribbon_title(screen, "Как играть", WIDTH // 2, 20)
        head, lines = self.PAGES[self.page]
        hf = make_font(28, "title")
        t = hf.render(f"{self.page + 1}. {head}", True, P_TEXT)
        screen.blit(t, (sc.x + 70, sc.y + 54))
        bf = make_font(18, "bold")
        y = sc.y + 104
        for i, text in enumerate(lines):
            badge = pygame.Rect(sc.x + 70, y + 3, 14, 14)
            pygame.draw.rect(screen, kit.INK, badge)
            pygame.draw.rect(screen, kit.RED if i % 2 == 0 else kit.BLUE, badge.inflate(-4, -4))
            for ln in wrap(bf, text, sc.w - 190):
                screen.blit(bf.render(ln, True, (86, 58, 36)), (sc.x + 96, y))
                y += bf.height() + 1
            y += 12
        if head == "Урон и броня":
            self._mult_table(screen, sc, y)
        for i, r in enumerate(self._dots()):
            pygame.draw.rect(screen, kit.INK, r)
            pygame.draw.rect(screen, kit.GOLD if i == self.page else kit.PAPER_EDGE, r.inflate(-4, -4))
        self.prev.enabled = self.page > 0
        self.next.enabled = self.page < len(self.PAGES) - 1
        for b in self.buttons:
            b.draw(screen, self.app.mouse)

    def _mult_table(self, screen, sc, y) -> None:
        from castlefight.data.balance import MULT

        dts = list(MULT)
        arms = list(next(iter(MULT.values())))
        f = make_font(14, "bold")
        cw = 96
        x0 = sc.x + 96
        screen.blit(f.render("урон \\ броня", True, P_MUTED), (x0, y))
        for j, a in enumerate(arms):
            screen.blit(f.render(ARMOR_RU.get(a.value, a.value), True, P_TEXT), (x0 + 130 + j * cw, y))
        for i, d in enumerate(dts):
            yy = y + 22 + i * 20
            screen.blit(f.render(DMG_RU.get(d.value, d.value), True, P_TEXT), (x0, yy))
            for j, a in enumerate(arms):
                v = MULT[d][a]
                col = P_GOOD if v > 1.0 else (P_BAD if v < 1.0 else P_TEXT)
                screen.blit(f.render(f"x{v:g}", True, col), (x0 + 130 + j * cw, yy))


# ---------------------------------------------------------------------------
# Выбор фракции и режима
# ---------------------------------------------------------------------------


class SetupScene(Scene):
    CARD_W = 262
    CARD_H = 226

    def __init__(self, app: "App", fi: int = 0, ei: int = -1, mode: str = "normal") -> None:
        super().__init__(app)
        self.fi = fi
        self.ei = ei  # -1 = случайный противник
        self.mode = mode
        self.cards: list[pygame.Rect] = []
        for i in range(len(FACTION_NAMES)):
            row, col = divmod(i, 3)
            self.cards.append(pygame.Rect(30 + col * (self.CARD_W + 14), 92 + row * (self.CARD_H + 16), self.CARD_W, self.CARD_H))
        px = 878
        self.side = pygame.Rect(px, 92, WIDTH - px - 26, 486)
        bf = make_font(20, "title")
        self.prev_enemy = Button(pygame.Rect(px + 18, 400, 46, 42), "<", font=bf, key="")
        self.next_enemy = Button(pygame.Rect(self.side.right - 64, 400, 46, 42), ">", font=bf)
        half = (self.side.w - 48) // 2
        self.m_normal = Button(pygame.Rect(px + 18, 482, half, 42), "Обычный", font=make_font(18, "title"))
        self.m_turbo = Button(pygame.Rect(px + 30 + half, 482, half, 42), "Турбо", font=make_font(18, "title"))
        self.start = Button(pygame.Rect(px, 600, self.side.w, 66), "В БОЙ!", kind="primary", font=make_font(32, "title"), key="Enter")
        self.back = Button(pygame.Rect(30, 610, 200, 56), "Назад", key="Esc")
        self.buttons = [self.prev_enemy, self.next_enemy, self.m_normal, self.m_turbo, self.start, self.back]
        self.t = 0.0

    def enemy_name(self) -> str:
        return "Случайный" if self.ei < 0 else FACTION_NAMES[self.ei]

    def choice(self) -> tuple[str, str, str]:
        if self.ei < 0:
            pool = [n for n in FACTION_NAMES if n != FACTION_NAMES[self.fi]]
            enemy = random.choice(pool)
        else:
            enemy = FACTION_NAMES[self.ei]
        return FACTION_NAMES[self.fi], enemy, self.mode

    def _cycle_enemy(self, d: int) -> None:
        n = len(FACTION_NAMES)
        self.ei = (self.ei + 1 + d) % (n + 1) - 1

    def _start(self) -> None:
        fa, fb, mode = self.choice()
        self.app.set_scene(MatchScene(self.app, fa, fb, mode))

    def handle(self, e) -> None:
        _buttons_pressed(self.buttons, e)
        n = len(FACTION_NAMES)
        if e.type == pygame.KEYDOWN:
            if e.key == pygame.K_ESCAPE:
                self.app.set_scene(MenuScene(self.app))
            elif e.key in (pygame.K_a, pygame.K_LEFT):
                self.fi = (self.fi - 1) % n
            elif e.key in (pygame.K_d, pygame.K_RIGHT):
                self.fi = (self.fi + 1) % n
            elif e.key in (pygame.K_w, pygame.K_UP, pygame.K_s, pygame.K_DOWN):
                self.fi = (self.fi + 3) % n
            elif e.key == pygame.K_q:
                self._cycle_enemy(-1)
            elif e.key == pygame.K_e:
                self._cycle_enemy(1)
            elif e.key == pygame.K_TAB:
                self.mode = "turbo" if self.mode == "normal" else "normal"
            elif e.key in (pygame.K_RETURN, pygame.K_SPACE):
                self._start()
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            for i, r in enumerate(self.cards):
                if r.collidepoint(e.pos):
                    self.fi = i
        if e.type == pygame.MOUSEBUTTONUP and e.button == 1:
            if self.prev_enemy.hit(e.pos):
                self._cycle_enemy(-1)
            elif self.next_enemy.hit(e.pos):
                self._cycle_enemy(1)
            elif self.m_normal.hit(e.pos):
                self.mode = "normal"
            elif self.m_turbo.hit(e.pos):
                self.mode = "turbo"
            elif self.start.hit(e.pos):
                self._start()
            elif self.back.hit(e.pos):
                self.app.set_scene(MenuScene(self.app))

    def update(self, dt: float) -> None:
        self.t += dt

    def _faction_card(self, screen, i: int, rect: pygame.Rect) -> None:
        a = self.app.assets
        name = FACTION_NAMES[i]
        color = FACTION_COLORS[name]
        sel = i == self.fi
        hover = rect.collidepoint(self.app.mouse)
        r = rect.move(0, -6 if sel else (-2 if hover else 0))
        drop_shadow(screen, r, 5, 110)
        screen.blit(kit.parchment(r.size, seed=i + 40), r.topleft)
        if sel:
            pygame.draw.rect(screen, kit.INK, r.inflate(8, 8), 2)
            pygame.draw.rect(screen, kit.GOLD, r.inflate(4, 4), 3)
        # цветная лента фракции сверху
        band = pygame.Rect(r.x + 10, r.y + 10, r.w - 20, 34)
        screen.blit(kit.ribbon(band.size, kit.shade(color, 0.85)), band.topleft)
        nt = outline_text(make_font(20, "title"), name, kit.CREAM, kit.INK, 2)
        screen.blit(nt, nt.get_rect(center=(band.centerx, band.centery - 2)))
        bl = make_font(14, "bold").render(FACTION_BLURBS[name], True, P_MUTED)
        screen.blit(bl, bl.get_rect(midtop=(r.centerx, r.y + 50)))
        # «сцена» с юнитами фракции на полоске травы
        stage = pygame.Rect(r.x + 12, r.y + 72, r.w - 24, 104)
        pygame.draw.rect(screen, (118, 150, 76), (stage.x, stage.bottom - 16, stage.w, 12))
        pygame.draw.rect(screen, (92, 122, 58), (stage.x, stage.bottom - 6, stage.w, 4))
        pygame.draw.rect(screen, kit.INK_SOFT, (stage.x, stage.bottom - 16, stage.w, 14), 2)
        xs = [stage.x + 30, stage.x + 90, stage.x + 150, stage.x + 208]
        for j, (x, role) in enumerate(zip(xs, ROLE_ORDER)):
            spr = a.unit_icon(name, role, 60, 94 if role == Role.ULT else 78)
            bob = int(math.sin(self.t * 4 + j) * 2) if sel else 0
            screen.blit(spr, spr.get_rect(midbottom=(x, stage.bottom - 8 + bob)))
        # цены зданий
        fac = FACTIONS[name]
        y = r.bottom - 38
        x = r.x + 16
        for role in ROLE_ORDER:
            bt = fac.building_by_role(role)
            pygame.draw.rect(screen, kit.INK, (x, y + 9, 10, 10))
            pygame.draw.rect(screen, P_ROLE[role], (x + 2, y + 11, 6, 6))
            t = make_font(8, "pixel").render(str(bt.cost), False, P_GOLD)
            screen.blit(t, (x + 15, y + 10))
            x += 60
        if sel:
            tag = pygame.Rect(r.right - 60, r.y - 14, 54, 26)
            screen.blit(kit.ribbon(tag.size, kit.RED), tag.topleft)
            t = make_font(8, "pixel").render("ТЫ", False, kit.CREAM)
            screen.blit(t, t.get_rect(center=(tag.centerx, tag.centery - 1)))

    def draw(self, screen) -> None:
        a = self.app.assets
        draw_backdrop(screen, a, 80)
        ribbon_title(screen, "Выбери фракцию", WIDTH // 2, 18, size=30)
        for i, r in enumerate(self.cards):
            self._faction_card(screen, i, r)

        # правая доска: описание, противник, режим
        s = self.side
        drop_shadow(screen, s, 6, 110)
        screen.blit(kit.wood_panel(s.size, seed=8), s.topleft)
        inner = s.inflate(-24, -24)
        paper = pygame.Rect(inner.x, inner.y, inner.w, 274)
        screen.blit(kit.parchment(paper.size, seed=2), paper.topleft)
        name = FACTION_NAMES[self.fi]
        fac = FACTIONS[name]
        screen.blit(make_font(26, "title").render(name, True, kit.shade(FACTION_COLORS[name], 0.6)), (paper.x + 14, paper.y + 8))
        bf = make_font(14, "bold")
        y = paper.y + 42
        for ln in wrap(bf, FACTION_LORE[name], paper.w - 28):
            screen.blit(bf.render(ln, True, (86, 58, 36)), (paper.x + 14, y))
            y += bf.height() + 1
        y += 8
        for role in ROLE_ORDER:
            bt = fac.building_by_role(role)
            pygame.draw.rect(screen, kit.INK, (paper.x + 14, y + 5, 10, 10))
            pygame.draw.rect(screen, P_ROLE[role], (paper.x + 16, y + 7, 6, 6))
            screen.blit(make_font(15, "title").render(bt.name, True, P_TEXT), (paper.x + 30, y))
            r = make_font(13, "bold").render(ROLE_LABELS[role].lower(), True, P_MUTED)
            screen.blit(r, (paper.right - 14 - r.get_width(), y + 2))
            y += 20
        # противник
        lab = outline_text(make_font(14, "bold"), "Противник (бот) · Q / E", (240, 226, 196), kit.INK, 2)
        screen.blit(lab, (s.x + 18, 374))
        en = self.enemy_name()
        plate = pygame.Rect(s.x + 72, 400, s.w - 144, 42)
        screen.blit(kit.parchment(plate.size, seed=5), plate.topleft)
        col = kit.shade(FACTION_COLORS.get(en, P_TEXT), 0.6) if en in FACTION_COLORS else P_TEXT
        t = make_font(20, "title").render(en, True, col)
        screen.blit(t, t.get_rect(center=plate.center))
        # режим
        lab = outline_text(make_font(14, "bold"), "Режим · Tab", (240, 226, 196), kit.INK, 2)
        screen.blit(lab, (s.x + 18, 458))
        self.m_normal.selected = self.mode == "normal"
        self.m_turbo.selected = self.mode == "turbo"
        hf = make_font(13, "bold")
        yy = 530
        for ln in wrap(hf, MODE_HELP[self.mode], s.w - 36)[:2]:
            screen.blit(outline_text(hf, ln, (236, 222, 190), kit.INK, 1), (s.x + 18, yy))
            yy += hf.height()
        for b in self.buttons:
            b.draw(screen, self.app.mouse)
        hint = outline_text(make_font(14, "bold"), "Клик или A / D — фракция · Enter — в бой · Esc — назад", (240, 226, 196), kit.INK, 2)
        blit_center(screen, hint, 560, 626)


# ---------------------------------------------------------------------------
# Матч
# ---------------------------------------------------------------------------


class MatchScene(Scene):
    SPEEDS = (1, 2, 4)

    def __init__(self, app: "App", faction_a: str, faction_b: str, mode: str, seed: Optional[int] = None, net=None) -> None:
        super().__init__(app)
        self.args = (faction_a, faction_b, mode)
        self.mode = mode
        self.net = net  # NetSession в сетевой игре
        if net is not None:
            self.game = net.game
            self.me = net.side
            self.seed = 0
        else:
            self.seed = random.randrange(1 << 30) if seed is None else seed
            self.game = Game(faction_a, faction_b, None, CounterBot(), mode=mode, seed=self.seed)
            self.me = 0
        self.foe = 1 - self.me
        self.player = self.game.players[self.me]
        self.enemy = self.game.players[self.foe]
        self.renderer = BattleRenderer(app.screen, app.assets)
        self.renderer.me = self.me
        self.top = TopBar(app.assets)
        self.panel = BuildPanel(app.assets)
        self.advisor = self._load_advisor()
        self.hint_role: Optional[Role] = None
        self._hint_at = -1.0
        self.acc = 0.0
        self.speed_i = 0
        self.paused = False
        self.placing: Optional[Role] = None
        self.armed: Optional[str] = None  # "bomb" — выбираем точку на дороге
        self.sell_slot: Optional[int] = None
        self.sell_t = 0.0
        self.drag_src: Optional[int] = None
        self.drag_start: Optional[tuple[int, int]] = None
        self.dragging = False
        self.mouse_down = False
        self.toast = ""
        self.toast_t = 0.0
        self.toast_bad = False
        self.over_t = 0.0
        self.frame_dt = 0.0
        cx, cy = WIDTH // 2, HEIGHT // 2
        self.btn_resume = Button(pygame.Rect(cx - 140, cy - 12, 280, 54), "Продолжить", kind="primary", key="Esc")
        self.btn_quit = Button(pygame.Rect(cx - 130, cy + 56, 260, 50), "Выйти в меню")
        self.btn_again = Button(pygame.Rect(cx - 250, cy + 168, 240, 56), "Реванш", kind="primary", key="R")
        self.btn_menu = Button(pygame.Rect(cx + 10, cy + 168, 240, 56), "К фракциям", key="Esc")
        self.sell_yes = Button(pygame.Rect(0, 0, 76, 34), "Да", kind="go", font=make_font(17, "title"))
        self.sell_no = Button(pygame.Rect(0, 0, 60, 34), "Нет", font=make_font(17, "title"))

    # --- служебное -----------------------------------------------------------

    def _load_advisor(self):
        path = Path(__file__).resolve().parent.parent / "ai" / "advisor_model.joblib"
        if not path.exists():
            return None
        try:
            from castlefight.ai.advisor import Advisor

            return Advisor(path)
        except Exception:
            return None

    @property
    def speed(self) -> int:
        return self.SPEEDS[self.speed_i]

    @property
    def over(self) -> bool:
        return self.game.world.winner is not None

    @property
    def world(self):
        return self.game.world

    def say(self, text: str, bad: bool = True) -> None:
        self.toast = text
        self.toast_t = 1.8
        self.toast_bad = bad

    def _cmd(self, cmd: dict):
        """Действие игрока: локально — сразу, по сети — отправка (применится в общем тике)."""
        if self.net is not None:
            self.net.command(cmd)
            return True
        return commands.apply(self.game, self.me, cmd)

    def _select(self, role: Role) -> None:
        self.armed = None
        self.sell_slot = None
        if self.placing == role:
            self.placing = None
            return
        reason = self.player.buy_block_reason(ROLE_INDEX[role])
        if reason:
            self.say(f"{self.player.faction.building_by_role(role).name}: {reason}")
            return
        self.placing = role

    def _place(self, slot: int, keep: bool) -> None:
        role = self.placing
        if role is None:
            return
        idx = ROLE_INDEX[role]
        if not self.player.is_slot_free(slot):
            self.say("Клетка занята — выбери свободную")
            return
        reason = self.player.buy_block_reason(idx)
        if reason:
            self.say(reason.capitalize())
            self.placing = None
            return
        bt = self.player.defs[idx]
        if self._cmd({"c": "buy", "i": idx, "s": slot}):
            r = slot_rect(self.me, slot)
            self.renderer.effects.hit(r.centerx, r.bottom - 10, (220, 200, 160), 14)
            self.renderer.effects.text(r.centerx, r.y - 4, f"-{bt.cost}", (255, 200, 90))
            if self.net is None and self.player.building_at(slot).spawn_mult < 1.0:
                self.renderer.effects.text(r.centerx, r.y - 22, "соседство!", (170, 240, 130))
            if not keep or self.player.buy_block_reason(idx):
                self.placing = None

    def _upgrade(self) -> None:
        if not self._cmd({"c": "upg"}):
            self.say("Апгрейд: максимум" if self.player.lvl >= 5 else "Апгрейд: не хватает золота")
        else:
            self.panel.ping("upgrade")
            self.say(f"Армия усилена: уровень {self.player.lvl}", bad=False)

    def _shop(self, item: str) -> None:
        """Клик по предмету лавки или горячая клавиша."""
        self.placing = None
        self.sell_slot = None
        if self.armed == item:
            self.armed = None
            return
        reason = shop.block_reason(self.player, self.world, item)
        if reason:
            self.say(f"{SHOP_NAMES[item]}: {reason}")
            return
        if item == "bomb":
            self.armed = "bomb"
            return
        if self._cmd({"c": "shop", "item": item, "x": None}):
            self.panel.ping(item)
            if item == "sword":
                self.say(f"Меч героя: уровень {self.player.sword}, удар {int(self.player.strike_damage)}", bad=False)
            else:
                self.say(f"{SHOP_NAMES[item]}!", bad=False)
            # эффект сразу (события лавки дойдут до рендера на следующем тике)

    def _drop_bomb(self, pos) -> None:
        x = screen_to_x(pos[0])
        if self._cmd({"c": "shop", "item": "bomb", "x": x}):
            self.panel.ping("bomb")
            self.armed = None
        else:
            self.say(f"Бомба: {shop.block_reason(self.player, self.world, 'bomb') or 'нельзя'}")
            self.armed = None

    def _strike(self, pos) -> bool:
        """Удар героя по вражескому юниту под курсором."""
        u = self.renderer.unit_at(pos, self.foe)
        if u is None:
            return False
        if u.uid and self.player.strike_ready(self.world.t):
            self._cmd({"c": "strike", "u": u.uid})  # вспышку и урон рисует рендер по событию
        return True

    def _open_sell(self, slot: int) -> None:
        if self.player.building_at(slot) is None:
            return
        self.placing = None
        self.armed = None
        self.sell_slot = slot
        self.sell_t = 5.0

    def _confirm_sell(self) -> None:
        slot = self.sell_slot
        self.sell_slot = None
        if slot is None:
            return
        refund = self._cmd({"c": "sell", "s": slot})
        if refund is True:
            refund = 0
        if refund:
            r = slot_rect(self.me, slot)
            self.renderer.effects.hit(r.centerx, r.bottom - 14, (200, 170, 120), 14)
            self.renderer.effects.gold(r.centerx, r.y - 6, refund)

    def _cancel(self) -> bool:
        if self.placing is not None or self.drag_src is not None or self.armed is not None or self.sell_slot is not None:
            self.placing = None
            self.drag_src = None
            self.dragging = False
            self.armed = None
            self.sell_slot = None
            return True
        return False

    def _sell_rects(self) -> tuple[pygame.Rect, pygame.Rect, pygame.Rect]:
        r = slot_rect(self.me, self.sell_slot if self.sell_slot is not None else 0)
        box = pygame.Rect(0, 0, 190, 84)
        box.midbottom = (r.centerx, r.y - 6)
        box.x = max(6, box.x)
        self.sell_yes.rect.topleft = (box.x + 14, box.y + 40)
        self.sell_no.rect.topleft = (box.right - 14 - self.sell_no.rect.w, box.y + 40)
        return box, self.sell_yes.rect, self.sell_no.rect

    # --- ввод --------------------------------------------------------------

    def handle(self, e) -> None:
        if self.over:
            self._handle_over(e)
            return
        if self.paused and not (e.type == pygame.KEYDOWN and e.key == pygame.K_SPACE):
            self._handle_pause(e)
            return
        if e.type == pygame.KEYDOWN:
            role = role_from_key(e.key)
            item = shop_from_key(e.key)
            if role is not None:
                self._select(role)
            elif item is not None:
                self._shop(item)
            elif e.key == pygame.K_u:
                self._upgrade()
            elif e.key == pygame.K_f and self.net is None:
                self.speed_i = (self.speed_i + 1) % len(self.SPEEDS)
            elif e.key == pygame.K_x:
                if self.sell_slot is not None:
                    self._confirm_sell()
                else:
                    slot = slot_at(self.me, self.app.mouse)
                    if slot is not None:
                        self._open_sell(slot)
            elif e.key == pygame.K_RETURN and self.sell_slot is not None:
                self._confirm_sell()
            elif e.key == pygame.K_SPACE and self.net is None:
                self.paused = not self.paused
            elif e.key == pygame.K_ESCAPE:
                if not self._cancel():
                    self.paused = True
        elif e.type == pygame.MOUSEBUTTONDOWN:
            if e.button == 3:
                if self._cancel():
                    return
                slot = slot_at(self.me, e.pos)
                if slot is not None and self.player.building_at(slot) is not None:
                    self._open_sell(slot)
                return
            if e.button != 1:
                return
            self.mouse_down = True
            if self.sell_slot is not None:
                _buttons_pressed([self.sell_yes, self.sell_no], e)
                box, yes, no = self._sell_rects()
                if box.collidepoint(e.pos):
                    return
                self.sell_slot = None
            hit = self.panel.hit(e.pos)
            if isinstance(hit, Role):
                self._select(hit)
                return
            if hit == "upgrade":
                self._upgrade()
                return
            if isinstance(hit, str) and hit.startswith("shop:"):
                self._shop(hit[5:])
                return
            if hit == "panel":
                return
            if self.top.speed_rect.collidepoint(e.pos) and self.net is None:
                self.speed_i = (self.speed_i + 1) % len(self.SPEEDS)
                return
            if self.armed == "bomb":
                if TOP_H <= e.pos[1] < PANEL_Y:
                    self._drop_bomb(e.pos)
                return
            slot = slot_at(self.me, e.pos)
            if self.placing is not None:
                if slot is not None:
                    mods = pygame.key.get_mods() if pygame.display.get_init() else 0
                    self._place(slot, keep=bool(mods & pygame.KMOD_SHIFT))
                return
            if slot is not None and self.player.building_at(slot) is not None:
                self.drag_src = slot
                self.drag_start = e.pos
                self.dragging = False
                return
            self._strike(e.pos)
        elif e.type == pygame.MOUSEMOTION:
            if self.drag_src is not None and self.drag_start is not None and not self.dragging:
                dx = e.pos[0] - self.drag_start[0]
                dy = e.pos[1] - self.drag_start[1]
                if dx * dx + dy * dy > 36:
                    self.dragging = True
        elif e.type == pygame.MOUSEBUTTONUP and e.button == 1:
            self.mouse_down = False
            if self.sell_slot is not None:
                yes, no = self.sell_yes.hit(e.pos), self.sell_no.hit(e.pos)
                _buttons_pressed([self.sell_yes, self.sell_no], e)
                if yes:
                    self._confirm_sell()
                elif no:
                    self.sell_slot = None
                return
            if self.drag_src is not None:
                if self.dragging:
                    dst = slot_at(self.me, e.pos)
                    if dst is not None and dst != self.drag_src:
                        if self._cmd({"c": "move", "a": self.drag_src, "b": dst}):
                            r = slot_rect(self.me, dst)
                            self.renderer.effects.hit(r.centerx, r.bottom - 10, (220, 200, 160), 10)
                        else:
                            self.say("Сюда нельзя — клетка занята")
                self.drag_src = None
                self.dragging = False

    def _handle_pause(self, e) -> None:
        _buttons_pressed([self.btn_resume, self.btn_quit], e)
        if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
            self.paused = False
        if e.type == pygame.MOUSEBUTTONUP and e.button == 1:
            if self.btn_resume.hit(e.pos):
                self.paused = False
            elif self.btn_quit.hit(e.pos):
                if self.net is not None:
                    self.net.close()
                    self.app.set_scene(NetMenuScene(self.app))
                else:
                    self.app.set_scene(MenuScene(self.app))

    def _handle_over(self, e) -> None:
        if self.over_t < 0.8:
            return
        if self.net is not None:  # по сети — только выход
            if (e.type == pygame.KEYDOWN and e.key in (pygame.K_ESCAPE, pygame.K_RETURN)) or (
                e.type == pygame.MOUSEBUTTONUP and e.button == 1 and (self.btn_menu.hit(e.pos) or self.btn_again.hit(e.pos))
            ):
                self.net.close()
                self.app.set_scene(NetMenuScene(self.app))
            return
        _buttons_pressed([self.btn_again, self.btn_menu], e)
        if e.type == pygame.KEYDOWN:
            if e.key in (pygame.K_RETURN, pygame.K_r):
                self.app.set_scene(MatchScene(self.app, *self.args))
            elif e.key == pygame.K_ESCAPE:
                self.app.set_scene(SetupScene(self.app, FACTION_NAMES.index(self.args[0]), mode=self.mode))
        if e.type == pygame.MOUSEBUTTONUP and e.button == 1:
            if self.btn_again.hit(e.pos):
                self.app.set_scene(MatchScene(self.app, *self.args))
            elif self.btn_menu.hit(e.pos):
                self.app.set_scene(SetupScene(self.app, FACTION_NAMES.index(self.args[0]), mode=self.mode))

    # --- шаг ---------------------------------------------------------------

    def _after_step(self, w) -> None:
        self.renderer.after_step(w)
        who = "Соперник" if self.net is not None else "Бот"
        for ev in w.events:
            if ev[0] == "interest" and ev[1] == self.me:
                self.renderer.effects.text(WIDTH // 2 - 215, 66, f"казна +{ev[2]:.0f}", (255, 214, 110))
            elif ev[0] == "shop" and ev[1] == self.foe:
                self.say(f"{who}: {SHOP_NAMES[ev[2]].lower()}", bad=True)

    def update(self, dt: float) -> None:
        self.frame_dt = dt
        w = self.game.world
        if self.net is not None and not self.over:
            self.net.pump(dt, self.renderer.before_step, self._after_step)
            self.acc = self.net.acc if self.net.is_host else 0.0
            if self.net.error:
                self.app.set_scene(NetMenuScene(self.app, msg=f"Сетевая игра прервана: {self.net.error}"))
                return
        elif not self.paused and not self.over:
            self.acc += dt * self.speed
            steps = 0
            while self.acc >= LOGIC_DT and steps < 20 and not self.over:
                self.acc -= LOGIC_DT
                self.renderer.before_step(w)
                self.game.step()
                self._after_step(w)
                steps += 1
        if True:
            if self.over:
                self.placing = None
                self.drag_src = None
                self.armed = None
                self.sell_slot = None
        if self.over:
            self.over_t += dt
        if not self.paused:
            self.renderer.update(dt * (self.speed if not self.over else 1))
        self.toast_t = max(0.0, self.toast_t - dt)
        if self.sell_slot is not None:
            self.sell_t -= dt
            if self.sell_t <= 0 or self.player.building_at(self.sell_slot) is None:
                self.sell_slot = None
        if self.advisor is not None and not self.over and w.t - self._hint_at >= 1.0:
            self._hint_at = w.t
            try:
                self.hint_role = self.advisor.suggest(self.player, w)
            except Exception:
                self.hint_role = None
        if self.placing is not None and self.player.buy_block_reason(ROLE_INDEX[self.placing]) == "все 12 мест заняты":
            self.placing = None
        if self.armed == "bomb" and shop.block_reason(self.player, w, "bomb") is not None:
            self.armed = None

    # --- отрисовка ---------------------------------------------------------

    def draw(self, screen) -> None:
        mouse = self.app.mouse
        hover_slot = slot_at(self.me, mouse)
        w = self.world
        in_field = TOP_H <= mouse[1] < PANEL_Y
        bomb_x = None
        if self.armed == "bomb" and in_field:
            bomb_x = max(LANE_X0, min(LANE_X1, mouse[0]))
        hover_unit = None
        if self.placing is None and self.armed is None and not self.dragging and in_field and not self.over and hover_slot is None:
            hover_unit = self.renderer.unit_at(mouse, self.foe)
        ready = 1.0 - max(0.0, self.player.next_strike_t - w.t) / STRIKE_CD
        ui = FieldUI(
            mouse=mouse,
            placing=self.placing,
            drag_slot=self.drag_src if self.dragging else None,
            hover_slot=hover_slot,
            hover_enemy_slot=slot_at(self.foe, mouse),
            can_afford=self.placing is None or self.player.buy_block_reason(ROLE_INDEX[self.placing]) is None,
            hover_unit=hover_unit,
            bomb_x=bomb_x,
            sell_slot=self.sell_slot,
            strike_ready=min(1.0, ready),
            me=self.me,
        )
        alpha = 0.0 if self.paused else max(0.0, min(1.0, self.acc / LOGIC_DT))
        if self.over:
            alpha = 1.0
        self.renderer.draw(w, alpha, ui)
        self.top.draw(screen, w, self.mode, self.speed, self.paused)
        self.panel.draw(
            screen,
            self.player,
            mouse=mouse,
            pressed=self.mouse_down,
            placing=self.placing,
            hint_role=self.hint_role if not self.over else None,
            dt=self.frame_dt,
            world=w,
            armed=self.armed,
        )
        if self.placing is not None:
            bt = self.player.faction.building_by_role(self.placing)
            self._banner(screen, f"Ставим «{bt.name}»: клик по свободной клетке · Shift — ещё · ПКМ / Esc — отмена")
        elif self.armed == "bomb":
            self._banner(screen, "Бомба: клик по дороге — сбросить · ПКМ / Esc — отмена", kit.RED)
        if hover_unit is not None:
            self._strike_cursor(screen, mouse, ready)
        # подсказки
        if not self.over and not self.paused and not self.dragging and self.sell_slot is None:
            hit = self.panel.hit(mouse)
            if isinstance(hit, Role):
                self.panel.tooltip(screen, self.player, hit)
            elif hit == "upgrade":
                self.panel.upgrade_tooltip(screen, self.player)
            elif isinstance(hit, str) and hit.startswith("shop:"):
                self.panel.item_tooltip(screen, self.player, w, hit[5:])
            elif self.placing is None and self.armed is None:
                for side, slot in ((self.me, hover_slot), (self.foe, ui.hover_enemy_slot)):
                    if slot is None:
                        continue
                    p = self.game.players[side]
                    b = p.building_at(slot)
                    if b is not None:
                        r = slot_rect(side, slot)
                        building_tooltip(screen, self.app.assets, p, b, (r.centerx, r.y - 2), own=side == self.me)
        if self.sell_slot is not None:
            self._sell_bubble(screen)
        if self.toast_t > 0:
            self._toast(screen)
        if self.paused and not self.over:
            self._pause_overlay(screen)
        if self.over and self.over_t > 0.6:
            self._over_overlay(screen)

    def _strike_cursor(self, screen, mouse, ready: float) -> None:
        """Маленький меч у курсора + кольцо перезарядки удара."""
        ic = self.app.assets.item_icon("sword", 26)
        ic = pygame.transform.rotate(ic, -35)
        screen.blit(ic, (mouse[0] + 8, mouse[1] - 4))
        if ready < 1.0:
            rect = pygame.Rect(mouse[0] + 6, mouse[1] - 6, 30, 30)
            pygame.draw.arc(screen, kit.INK, rect, math.pi / 2, math.pi / 2 + 2 * math.pi * ready, 5)
            pygame.draw.arc(screen, kit.CREAM, rect, math.pi / 2, math.pi / 2 + 2 * math.pi * ready, 2)

    def _banner(self, screen, text: str, color=None) -> None:
        f = make_font(15, "bold")
        t = f.render(text, True, P_TEXT)
        r = pygame.Rect(0, 0, t.get_width() + 36, 32)
        r.midtop = (WIDTH // 2, 70)
        drop_shadow(screen, r, 3, 80)
        screen.blit(kit.parchment(r.size, seed=7), r.topleft)
        if color is not None:
            pygame.draw.rect(screen, color, (r.x + 6, r.y + 6, 6, r.h - 12))
        screen.blit(t, t.get_rect(center=(r.centerx + 4, r.centery)))

    def _sell_bubble(self, screen) -> None:
        b = self.player.building_at(self.sell_slot)
        if b is None:
            return
        box, yes, no = self._sell_rects()
        drop_shadow(screen, box, 4, 90)
        screen.blit(kit.parchment(box.size, seed=11), box.topleft)
        # хвостик к клетке
        r = slot_rect(self.me, self.sell_slot)
        pts = [(r.centerx - 8, box.bottom - 2), (r.centerx + 8, box.bottom - 2), (r.centerx, box.bottom + 8)]
        pygame.draw.polygon(screen, kit.PAPER, pts)
        pygame.draw.lines(screen, kit.INK_SOFT, False, [pts[0], pts[2], pts[1]], 2)
        refund = int(b.cost * SELL_REFUND)
        t = make_font(16, "title").render(f"Продать «{b.building_type.name}»?", True, P_TEXT)
        if t.get_width() > box.w - 20:
            t = make_font(15, "title").render("Продать здание?", True, P_TEXT)
        screen.blit(t, (box.x + 12, box.y + 8))
        self.sell_yes.label = f"+{refund}"
        self.sell_yes.draw(screen, self.app.mouse)
        self.sell_no.draw(screen, self.app.mouse)

    def _toast(self, screen) -> None:
        f = make_font(17, "bold")
        t = f.render(self.toast, True, P_BAD if self.toast_bad else P_GOOD)
        r = pygame.Rect(0, 0, t.get_width() + 40, 38)
        r.midbottom = (WIDTH // 2, PANEL_Y - 18)
        k = min(1.0, self.toast_t / 0.3)
        surf = pygame.Surface((r.w + 4, r.h + 4), pygame.SRCALPHA)
        sh = pygame.Surface(r.size, pygame.SRCALPHA)
        sh.fill((*kit.INK, 90))
        surf.blit(sh, (4, 4))
        surf.blit(kit.parchment(r.size, seed=13), (0, 0))
        pygame.draw.rect(surf, P_BAD if self.toast_bad else P_GOOD, (6, 6, 6, r.h - 12))
        surf.blit(t, t.get_rect(center=(r.w // 2 + 4, r.h // 2)))
        surf.set_alpha(int(255 * k))
        screen.blit(surf, r)

    def _pause_overlay(self, screen) -> None:
        dim(screen, 70)
        cx, cy = WIDTH // 2, HEIGHT // 2
        r = pygame.Rect(cx - 210, cy - 132, 420, 264)
        drop_shadow(screen, r, 6, 110)
        screen.blit(kit.wood_panel(r.size, seed=4), r.topleft)
        # цепи-подвесы
        for x in (r.x + 60, r.right - 60):
            for y in range(r.y - 40, r.y, 8):
                pygame.draw.rect(screen, kit.INK, (x - 3, y, 6, 6), 2)
        t = pixel_title("ПАУЗА", 32, kit.CREAM, kit.INK, 4)
        screen.blit(t, t.get_rect(midtop=(cx, r.y + 26)))
        h = outline_text(make_font(15, "bold"), "Пробел / Esc — продолжить", (236, 222, 190), kit.INK, 2)
        screen.blit(h, h.get_rect(midtop=(cx, r.y + 84)))
        for b in (self.btn_resume, self.btn_quit):
            b.draw(screen, self.app.mouse)

    def _over_overlay(self, screen) -> None:
        k = min(1.0, (self.over_t - 0.6) / 0.4)
        dim(screen, int(90 * k))
        w = self.game.world
        win = w.winner == self.me
        cx, cy = WIDTH // 2, HEIGHT // 2
        r = pygame.Rect(cx - 320, cy - 262, 640, 500)
        drop_shadow(screen, r, 6, 110)
        screen.blit(kit.scroll(r.size, seed=6), r.topleft)
        title = "ПОБЕДА!" if win else "ПОРАЖЕНИЕ"
        color = (250, 196, 70) if win else (226, 90, 70)
        t = pixel_title(title, 32, color, kit.INK, 5)
        screen.blit(t, t.get_rect(midtop=(cx, r.y + 34)))
        if w.timeout:
            why = "Время вышло — победил тот, у кого замок крепче"
        else:
            why = "Вражеский замок разрушен" if win else "Твой замок пал"
        wt = make_font(17, "bold").render(why, True, P_MUTED)
        screen.blit(wt, wt.get_rect(midtop=(cx, r.y + 90)))
        a, b = self.game.players
        rows = [
            ("Время матча", fmt_time(w.t), ""),
            ("Замок, HP", fmt_int(max(0, a.castle.hp)), fmt_int(max(0, b.castle.hp))),
            ("Убито врагов", str(a.kills), str(b.kills)),
            ("Золото за убийства", fmt_int(a.earned), fmt_int(b.earned)),
            ("Ударов героя / урон", f"{a.strikes} / {fmt_int(a.strike_dealt)}", f"{b.strikes} / {fmt_int(b.strike_dealt)}"),
            ("Потрачено в лавке", fmt_int(a.shop_spent), fmt_int(b.shop_spent)),
            ("Зданий · апгрейд", f"{len(a.buildings)}/{SLOTS} · {a.lvl}", f"{len(b.buildings)}/{SLOTS} · {b.lvl}"),
        ]
        hf = make_font(16, "title")
        y = r.y + 126
        c1, c2 = r.x + 370, r.x + 520
        for c, p, side in ((c1, a, 0), (c2, b, 1)):
            t = hf.render(p.faction.name, True, kit.shade(TEAM[side], 0.7))
            screen.blit(t, (c - t.get_width() // 2, y))
        y += 28
        lf = make_font(16, "bold")
        vf = make_font(16, "title")
        for i, (name, va, vb) in enumerate(rows):
            if i % 2 == 0:
                pygame.draw.rect(screen, kit.shade(kit.PAPER, 0.93), (r.x + 50, y - 3, r.w - 100, 28))
            screen.blit(lf.render(name, True, P_TEXT), (r.x + 64, y))
            if vb:
                s1, s2 = vf.render(va, True, P_TEXT), vf.render(vb, True, P_TEXT)
                screen.blit(s1, (c1 - s1.get_width() // 2, y))
                screen.blit(s2, (c2 - s2.get_width() // 2, y))
            else:
                s1 = vf.render(va, True, P_TEXT)
                screen.blit(s1, ((c1 + c2) // 2 - s1.get_width() // 2, y))
            y += 30
        sl = kit.seal(30, kit.RED if win else (112, 46, 34))
        screen.blit(sl, (r.right - 96, r.y + 30))
        for btn in (self.btn_again, self.btn_menu):
            btn.draw(screen, self.app.mouse)


# ---------------------------------------------------------------------------
# Игра по локальной сети
# ---------------------------------------------------------------------------


def _nick() -> str:
    try:
        import getpass

        return getpass.getuser()[:16] or "игрок"
    except Exception:
        return "игрок"


def _panel(screen, title: str) -> pygame.Rect:
    draw_backdrop(screen, screen_assets(screen), 70)
    sc = pygame.Rect(120, 80, WIDTH - 240, 540)
    drop_shadow(screen, sc, 6, 100)
    screen.blit(kit.scroll(sc.size, seed=8), sc.topleft)
    ribbon_title(screen, title, WIDTH // 2, 24, color=kit.BLUE)
    return sc


_ASSETS = {}


def screen_assets(screen):
    return _ASSETS["a"]


def _text(screen, text, x, y, size=17, color=None, kind="bold"):
    t = make_font(size, kind).render(text, True, color or P_TEXT)
    screen.blit(t, (x, y))
    return t


class NetMenuScene(Scene):
    """«По сети»: создать игру или подключиться."""

    def __init__(self, app: "App", msg: str = "") -> None:
        super().__init__(app)
        _ASSETS["a"] = app.assets
        self.msg = msg
        cx = WIDTH // 2
        f = make_font(26, "title")
        self.host = Button(pygame.Rect(cx - 170, 300, 340, 62), "Создать игру", kind="primary", font=f, key="1")
        self.join = Button(pygame.Rect(cx - 170, 380, 340, 62), "Подключиться", kind="go", font=f, key="2")
        self.back = Button(pygame.Rect(cx - 120, 520, 240, 52), "В меню", key="Esc")
        self.buttons = [self.host, self.join, self.back]

    def handle(self, e) -> None:
        _buttons_pressed(self.buttons, e)
        if e.type == pygame.KEYDOWN:
            if e.key in (pygame.K_1, pygame.K_KP1):
                self.app.set_scene(HostScene(self.app))
            elif e.key in (pygame.K_2, pygame.K_KP2):
                self.app.set_scene(JoinScene(self.app))
            elif e.key == pygame.K_ESCAPE:
                self.app.set_scene(MenuScene(self.app))
        if e.type == pygame.MOUSEBUTTONUP and e.button == 1:
            if self.host.hit(e.pos):
                self.app.set_scene(HostScene(self.app))
            elif self.join.hit(e.pos):
                self.app.set_scene(JoinScene(self.app))
            elif self.back.hit(e.pos):
                self.app.set_scene(MenuScene(self.app))

    def draw(self, screen) -> None:
        sc = _panel(screen, "Игра по сети")
        bf = make_font(17, "bold")
        y = sc.y + 70
        for ln in ("Два компьютера в одной сети (один Wi-Fi или роутер).",
                   "Один создаёт игру, второй находит её в списке и подключается."):
            t = bf.render(ln, True, P_TEXT)
            screen.blit(t, t.get_rect(midtop=(WIDTH // 2, y)))
            y += 26
        if self.msg:
            for ln in wrap(bf, self.msg, sc.w - 120)[:2]:
                t = bf.render(ln, True, P_BAD)
                screen.blit(t, t.get_rect(midtop=(WIDTH // 2, 466 + (0 if ln == self.msg else 0))))
        for b in self.buttons:
            b.draw(screen, self.app.mouse)


class _FactionPick:
    """Выбор фракции стрелками / кликом (общий для хоста и гостя)."""

    def __init__(self, x: int, y: int, i: int = 0) -> None:
        self.i = i
        self.left = Button(pygame.Rect(x, y, 54, 48), "<", key="")
        self.right = Button(pygame.Rect(x + 326, y, 54, 48), ">", key="")
        self.rect = pygame.Rect(x + 60, y, 260, 48)

    @property
    def name(self) -> str:
        return FACTION_NAMES[self.i]

    def handle(self, e) -> None:
        _buttons_pressed([self.left, self.right], e)
        if e.type == pygame.MOUSEBUTTONUP and e.button == 1:
            if self.left.hit(e.pos):
                self.i = (self.i - 1) % len(FACTION_NAMES)
            elif self.right.hit(e.pos):
                self.i = (self.i + 1) % len(FACTION_NAMES)

    def draw(self, screen, mouse) -> None:
        screen.blit(kit.parchment(self.rect.size, seed=5), self.rect.topleft)
        col = kit.shade(FACTION_COLORS.get(self.name, P_TEXT), 0.6)
        t = make_font(22, "title").render(self.name, True, col)
        screen.blit(t, t.get_rect(center=self.rect.center))
        self.left.draw(screen, mouse)
        self.right.draw(screen, mouse)


class HostScene(Scene):
    """Хост: выбирает фракцию и режим, рассылает маяк и ждёт гостя."""

    def __init__(self, app: "App") -> None:
        super().__init__(app)
        from castlefight.net.lan import TCP_PORT, HostLobby, local_ips

        self.pick = _FactionPick(WIDTH // 2 - 190, 210)
        self.mode = "normal"
        self.error = ""
        self.lobby = None
        self.t = 0.0
        self.ips = local_ips()
        try:
            self.lobby = HostLobby(self.pick.name, self.mode, nick=_nick(), port=TCP_PORT)
        except OSError as e:
            self.error = f"Порт {TCP_PORT} занят или недоступен ({e.__class__.__name__}). Закрой другую копию игры."
        self.port = self.lobby.port if self.lobby else TCP_PORT
        self.mode_btn = Button(pygame.Rect(WIDTH // 2 - 150, 290, 300, 48), "", key="Tab")
        self.back = Button(pygame.Rect(WIDTH // 2 - 120, 548, 240, 52), "Отмена", key="Esc")

    def _leave(self) -> None:
        if self.lobby is not None:
            self.lobby.close()
        self.app.set_scene(NetMenuScene(self.app))

    def handle(self, e) -> None:
        self.pick.handle(e)
        _buttons_pressed([self.mode_btn, self.back], e)
        if e.type == pygame.KEYDOWN:
            if e.key == pygame.K_ESCAPE:
                self._leave()
            elif e.key in (pygame.K_a, pygame.K_LEFT):
                self.pick.i = (self.pick.i - 1) % len(FACTION_NAMES)
            elif e.key in (pygame.K_d, pygame.K_RIGHT):
                self.pick.i = (self.pick.i + 1) % len(FACTION_NAMES)
            elif e.key == pygame.K_TAB:
                self.mode = "turbo" if self.mode == "normal" else "normal"
        if e.type == pygame.MOUSEBUTTONUP and e.button == 1:
            if self.back.hit(e.pos):
                self._leave()
            elif self.mode_btn.hit(e.pos):
                self.mode = "turbo" if self.mode == "normal" else "normal"

    def update(self, dt: float) -> None:
        self.t += dt
        if self.lobby is None:
            return
        self.lobby.faction = self.pick.name
        self.lobby.mode = self.mode
        sess = self.lobby.poll()
        if sess is not None:
            fa, fb = (p.faction.name for p in sess.game.players)
            self.app.set_scene(MatchScene(self.app, fa, fb, sess.game.mode, net=sess))

    def draw(self, screen) -> None:
        sc = _panel(screen, "Создать игру")
        _text(screen, "Твоя фракция (A / D):", sc.x + 70, 180)
        self.pick.draw(screen, self.app.mouse)
        self.mode_btn.label = "Режим: обычный" if self.mode == "normal" else "Режим: турбо"
        self.mode_btn.draw(screen, self.app.mouse)
        y = 366
        if self.error:
            for ln in wrap(make_font(17, "bold"), self.error, sc.w - 140):
                _text(screen, ln, sc.x + 70, y, color=P_BAD)
                y += 24
        else:
            dots = "." * (1 + int(self.t * 2) % 3)
            _text(screen, f"Ждём второго игрока{dots}", sc.x + 70, y, 22, kind="title")
            y += 40
            _text(screen, "Адрес для ручного подключения:", sc.x + 70, y)
            y += 28
            for ip in self.ips[:3]:
                _text(screen, f"{ip} : {self.port}", sc.x + 90, y, 22, color=kit.shade(kit.BLUE, 0.8), kind="title")
                y += 32
            _text(screen, "Игра видна в списке «Подключиться» у всех в этой сети.", sc.x + 70, y + 4, 15, color=P_MUTED)
        self.back.draw(screen, self.app.mouse)


class _Field:
    def __init__(self, rect: pygame.Rect, value: str, label: str, maxlen: int) -> None:
        self.rect, self.value, self.label, self.maxlen = rect, value, label, maxlen
        self.focus = False

    def key(self, e) -> None:
        if e.key == pygame.K_BACKSPACE:
            self.value = self.value[:-1]
        elif e.unicode and (e.unicode.isdigit() or e.unicode == ".") and len(self.value) < self.maxlen:
            self.value += e.unicode

    def draw(self, screen, t: float) -> None:
        _text(screen, self.label, self.rect.x, self.rect.y - 22, 15, color=P_MUTED)
        pygame.draw.rect(screen, kit.INK, self.rect.inflate(4, 4))
        pygame.draw.rect(screen, (252, 244, 222) if self.focus else (232, 220, 192), self.rect)
        f = make_font(20, "title")
        txt = self.value + ("|" if self.focus and int(t * 2) % 2 == 0 else "")
        screen.blit(f.render(txt, True, P_TEXT), (self.rect.x + 8, self.rect.y + 6))


class JoinScene(Scene):
    """Гость: живой список найденных игр (UDP-маяки) + ручной ввод IP и порта."""

    def __init__(self, app: "App") -> None:
        super().__init__(app)
        from castlefight.net.discovery import Browser
        from castlefight.net.lan import TCP_PORT

        self.pick = _FactionPick(WIDTH // 2 - 190, 150, 1)
        try:
            self.browser = Browser()
        except OSError:
            self.browser = None
        self.ip = _Field(pygame.Rect(170, 476, 260, 38), "", "IP хоста", 15)
        self.port = _Field(pygame.Rect(450, 476, 110, 38), str(TCP_PORT), "Порт", 5)
        self.connect = Button(pygame.Rect(580, 468, 250, 52), "Подключиться", kind="go", key="Enter")
        self.back = Button(pygame.Rect(WIDTH // 2 - 120, 552, 240, 50), "Назад", key="Esc")
        self.join = None
        self.status = ""
        self.bad = False
        self.t = 0.0
        self.games = []

    def _rows(self):
        return [pygame.Rect(170, 252 + i * 46, WIDTH - 340, 40) for i in range(len(self.games[:4]))]

    def _leave(self) -> None:
        if self.browser is not None:
            self.browser.close()
        if self.join is not None:
            self.join.close()
        self.app.set_scene(NetMenuScene(self.app))

    def _go(self, host: str, port) -> None:
        from castlefight.net.lan import ClientJoin

        if not host:
            self.status, self.bad = "Введи IP хоста или выбери игру из списка", True
            return
        try:
            port = int(port)
        except ValueError:
            self.status, self.bad = "Порт — это число, например 47821", True
            return
        self.status, self.bad = f"Подключаемся к {host}:{port}…", False
        self.join = ClientJoin(host, port, self.pick.name, nick=_nick())
        if self.join.error:
            self.status, self.bad = self.join.error, True
            self.join = None

    def handle(self, e) -> None:
        self.pick.handle(e)
        _buttons_pressed([self.connect, self.back], e)
        if e.type == pygame.KEYDOWN:
            focused = self.ip if self.ip.focus else (self.port if self.port.focus else None)
            if e.key == pygame.K_ESCAPE:
                self._leave()
            elif e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self._go(self.ip.value, self.port.value)
            elif e.key == pygame.K_TAB:
                self.ip.focus, self.port.focus = not self.ip.focus, self.ip.focus
            elif focused is not None:
                focused.key(e)
            elif e.key in (pygame.K_a, pygame.K_LEFT):
                self.pick.i = (self.pick.i - 1) % len(FACTION_NAMES)
            elif e.key in (pygame.K_d, pygame.K_RIGHT):
                self.pick.i = (self.pick.i + 1) % len(FACTION_NAMES)
        if e.type == pygame.MOUSEBUTTONUP and e.button == 1:
            self.ip.focus = self.ip.rect.collidepoint(e.pos)
            self.port.focus = self.port.rect.collidepoint(e.pos)
            if self.back.hit(e.pos):
                self._leave()
            elif self.connect.hit(e.pos):
                self._go(self.ip.value, self.port.value)
            for r, g in zip(self._rows(), self.games):
                if r.collidepoint(e.pos):
                    self.ip.value, self.port.value = g.host, str(g.tcp)
                    self._go(g.host, g.tcp)

    def update(self, dt: float) -> None:
        self.t += dt
        if self.browser is not None:
            self.browser.poll()
            self.games = self.browser.games()
        if self.join is not None:
            sess = self.join.poll()
            if sess is not None:
                if self.browser is not None:
                    self.browser.close()
                fa, fb = (p.faction.name for p in sess.game.players)
                self.app.set_scene(MatchScene(self.app, fa, fb, sess.game.mode, net=sess))
            elif self.join.error:
                self.status, self.bad = self.join.error, True
                self.join = None

    def draw(self, screen) -> None:
        sc = _panel(screen, "Подключиться")
        _text(screen, "Твоя фракция:", sc.x + 50, 122, 15, color=P_MUTED)
        self.pick.draw(screen, self.app.mouse)
        dots = "." * (1 + int(self.t * 2) % 3)
        _text(screen, f"Игры в локальной сети{'' if self.games else ' — ищем' + dots}", 170, 222, 18, kind="title")
        mouse = self.app.mouse
        for r, g in zip(self._rows(), self.games):
            hov = r.collidepoint(mouse)
            screen.blit(kit.parchment(r.size, seed=3), r.topleft)
            pygame.draw.rect(screen, kit.GOLD if hov else kit.INK_SOFT, r, 2)
            _text(screen, f"{g.name}", r.x + 12, r.y + 9, 18, kind="title")
            _text(screen, f"{g.faction} · {g.host}:{g.tcp}", r.x + 330, r.y + 11, 15, color=P_MUTED)
            _text(screen, "клик — войти", r.right - 120, r.y + 11, 15, color=P_GOOD)
        if not self.games:
            _text(screen, "Пока никого. Попроси друга нажать «Создать игру» или введи адрес вручную.", 170, 262, 15, color=P_MUTED)
        _text(screen, "Не нашлась? Введи адрес вручную (Tab — переключить поле):", 170, 430, 15)
        self.ip.draw(screen, self.t)
        self.port.draw(screen, self.t)
        self.connect.draw(screen, mouse)
        if self.status:
            _text(screen, self.status[:90], 170, 526, 15, color=P_BAD if self.bad else P_GOOD)
        self.back.draw(screen, mouse)
