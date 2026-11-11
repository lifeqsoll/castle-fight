"""Игрок: золото, здания, апгрейд, покупка."""

from __future__ import annotations

import random
from typing import Optional

from castlefight.core.building import Building
from castlefight.core.entity import Castle, Unit
from castlefight.data.balance import (
    ADJ_SPAWN_MULT,
    LANE,
    MAX_ULT,
    SELL_REFUND,
    SLOTS,
    STRIKE_CD,
    STRIKE_DMG,
    SWORD_COST,
    UPG_BONUS,
    UPG_COST,
    UPG_MAX,
)
from castlefight.data.enums import Role
from castlefight.data.factions import BuildingType, Faction


class Player:
    """Состояние одного игрока в матче."""

    def __init__(self, faction: Faction, side: int, econ: dict) -> None:
        self.faction = faction
        self.side = side
        self.gold = float(econ["start"])
        self.buildings: list[Building] = []
        self.units: list[Unit] = []
        castle_x = 0.0 if side == 0 else float(LANE)
        self.castle = Castle(side, castle_x, float(econ["castle_hp"]))
        self.lvl = 0
        self.earned = 0
        self.kills = 0
        self.ultspawned = 0
        self.first_ult: Optional[float] = None
        # v3: лавка, меч героя, баффы
        self.sword = 0  # уровень меча 0..len(STRIKE_DMG)-1
        self.next_strike_t = 0.0  # мировое время, когда можно ударить снова
        self.strikes = 0
        self.strike_dealt = 0.0
        self.cd_until: dict[str, float] = {}  # предмет лавки → время готовности
        self.buff_until: dict[str, float] = {}  # «rage» / «stone» → до какого времени действует
        self.repairs = 0
        self.shop_spent = 0
        self.sold = 0

    @property
    def upgrade_mult(self) -> float:
        return 1.0 + UPG_BONUS * self.lvl

    @property
    def defs(self) -> tuple[BuildingType, BuildingType, BuildingType, BuildingType]:
        """Здания фракции по индексам 0..3 (как у ботов)."""
        return self.faction.buildings

    def counts(self) -> list[int]:
        """Число зданий по ролям [melee, ranged, summon, ult]."""
        c = [0, 0, 0, 0]
        role_to_i = {Role.MELEE: 0, Role.RANGED: 1, Role.SUMMON: 2, Role.ULT: 3}
        for b in self.buildings:
            c[role_to_i[b.role]] += 1
        return c

    def ult_count(self) -> int:
        return sum(1 for b in self.buildings if b.role == Role.ULT)

    # --- слоты зоны застройки -------------------------------------------------

    def _sync_slots(self) -> None:
        """Зданиям без слота (добавленным напрямую) выдать первый свободный."""
        if all(b.slot is not None for b in self.buildings):
            return
        used = {b.slot for b in self.buildings if b.slot is not None}
        for b in self.buildings:
            if b.slot is None:
                for i in range(SLOTS):
                    if i not in used:
                        b.slot = i
                        used.add(i)
                        break
        self.refresh_adjacency()

    # --- «Соседство» ---------------------------------------------------------

    @staticmethod
    def neighbors(slot: int) -> list[int]:
        """Соседние по стороне ячейки сетки 2×6."""
        cols = SLOTS // 2
        row, col = divmod(slot, cols)
        out = []
        if col > 0:
            out.append(slot - 1)
        if col < cols - 1:
            out.append(slot + 1)
        other = (1 - row) * cols + col
        out.append(other)
        return out

    def refresh_adjacency(self) -> None:
        """Пересчитать бонус спавна: рядом стоит такое же здание → ADJ_SPAWN_MULT."""
        by_slot = {b.slot: b for b in self.buildings if b.slot is not None}
        for b in self.buildings:
            b.spawn_mult = 1.0
            if b.slot is None:
                continue
            for n in self.neighbors(b.slot):
                nb = by_slot.get(n)
                if nb is not None and nb.building_type is b.building_type:
                    b.spawn_mult = ADJ_SPAWN_MULT
                    break

    def best_slot(self, index: int) -> Optional[int]:
        """Свободная ячейка с максимумом таких же соседей (для ботов)."""
        free = self.free_slots()
        if not free:
            return None
        bt = self.defs[index]
        by_slot = {b.slot: b for b in self.buildings}

        def score(s: int) -> tuple[int, int]:
            same = sum(1 for n in self.neighbors(s) if n in by_slot and by_slot[n].building_type is bt)
            return (-same, s)

        return min(free, key=score)

    def building_at(self, slot: int) -> Optional[Building]:
        """Здание в ячейке slot или None."""
        self._sync_slots()
        for b in self.buildings:
            if b.slot == slot:
                return b
        return None

    def free_slots(self) -> list[int]:
        """Свободные ячейки по возрастанию."""
        self._sync_slots()
        used = {b.slot for b in self.buildings}
        return [i for i in range(SLOTS) if i not in used]

    def is_slot_free(self, slot: int) -> bool:
        return 0 <= slot < SLOTS and self.building_at(slot) is None

    def buy_block_reason(self, index: int) -> Optional[str]:
        """Почему нельзя купить здание index (None — можно)."""
        if index < 0 or index >= 4:
            return "нет такого здания"
        if len(self.buildings) >= SLOTS:
            return "все 12 мест заняты"
        bt = self.defs[index]
        if bt.role == Role.ULT and self.ult_count() >= MAX_ULT:
            return f"максимум {MAX_ULT} ульт-здания"
        if self.gold < bt.cost:
            return "не хватает золота"
        return None

    def can_buy(self, index: int, slot: Optional[int] = None) -> bool:
        if self.buy_block_reason(index) is not None:
            return False
        if slot is not None and not self.is_slot_free(slot):
            return False
        return True

    def buy(self, index: int, rng: random.Random, slot: Optional[int] = None) -> bool:
        """Купить здание по индексу роли 0..3 и поставить в ячейку slot.

        slot=None — первая свободная ячейка (так покупают боты).
        Вернуть True при успехе.
        """
        if not self.can_buy(index, slot):
            return False
        if slot is None:
            slot = self.free_slots()[0]
        bt = self.defs[index]
        self.gold -= bt.cost
        timer = bt.spawn * 0.5 * rng.uniform(0.8, 1.2)
        self.buildings.append(Building(bt, timer, slot=slot))
        self.refresh_adjacency()
        return True

    def sell_value(self, slot: int) -> int:
        b = self.building_at(slot)
        return 0 if b is None else int(b.cost * SELL_REFUND)

    def sell(self, slot: int) -> int:
        """Продать здание в ячейке slot. Вернуть возврат золота (0 — нечего продавать)."""
        b = self.building_at(slot)
        if b is None:
            return 0
        refund = int(b.cost * SELL_REFUND)
        self.buildings.remove(b)
        self.gold += refund
        self.sold += 1
        self.refresh_adjacency()
        return refund

    # --- меч героя (удар кликом) ----------------------------------------------

    @property
    def strike_damage(self) -> float:
        return float(STRIKE_DMG[self.sword])

    def sword_cost(self) -> Optional[int]:
        return SWORD_COST[self.sword] if self.sword < len(SWORD_COST) else None

    def upgrade_sword(self) -> bool:
        cost = self.sword_cost()
        if cost is None or self.gold < cost:
            return False
        self.gold -= cost
        self.shop_spent += cost
        self.sword += 1
        return True

    def strike_ready(self, t: float) -> bool:
        return t >= self.next_strike_t - 1e-9

    # --- баффы ----------------------------------------------------------------

    def buff_active(self, name: str, t: float) -> bool:
        return t < self.buff_until.get(name, -1.0)

    def dmg_mult(self, t: float) -> float:
        from castlefight.data.balance import SHOP

        return SHOP["rage"]["mult"] if self.buff_active("rage", t) else 1.0

    def taken_mult(self, t: float) -> float:
        from castlefight.data.balance import SHOP

        return SHOP["stone"]["mult"] if self.buff_active("stone", t) else 1.0

    def move_building(self, src: int, dst: int) -> bool:
        """Бесплатно перенести своё здание из ячейки src в свободную ячейку dst."""
        if src == dst:
            return False
        b = self.building_at(src)
        if b is None or not self.is_slot_free(dst):
            return False
        b.slot = dst
        self.refresh_adjacency()
        return True

    def try_upgrade(self) -> bool:
        """Купить следующий уровень апгрейда, если хватает золота."""
        if self.lvl >= UPG_MAX:
            return False
        cost = UPG_COST[self.lvl]
        if self.gold < cost:
            return False
        self.gold -= cost
        self.lvl += 1
        return True

    def spawn_x(self) -> float:
        return self.castle.x + (30.0 if self.side == 0 else -30.0)
