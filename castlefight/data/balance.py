"""Константы баланса: таблица урона, экономика, замок, слоты, апгрейды."""

from castlefight.data.enums import ArmorType, DamageType

# Множители урона: MULT[тип_урона][броня]
MULT: dict[DamageType, dict[ArmorType, float]] = {
    DamageType.SLASH: {
        ArmorType.L: 1.2,
        ArmorType.M: 1.0,
        ArmorType.H: 0.85,
        ArmorType.S: 1.3,
        ArmorType.C: 0.25,
        ArmorType.R: 0.8,
    },
    DamageType.PIERCE: {
        ArmorType.L: 1.25,
        ArmorType.M: 1.0,
        ArmorType.H: 0.8,
        ArmorType.S: 0.85,
        ArmorType.C: 0.25,
        ArmorType.R: 1.0,
    },
    DamageType.MAGIC: {
        ArmorType.L: 1.05,
        ArmorType.M: 1.1,
        ArmorType.H: 1.2,
        ArmorType.S: 0.85,
        ArmorType.C: 0.25,
        ArmorType.R: 1.1,
    },
    DamageType.CASTLE: {
        ArmorType.L: 1.0,
        ArmorType.M: 1.0,
        ArmorType.H: 1.0,
        ArmorType.S: 1.0,
        ArmorType.C: 1.0,
        ArmorType.R: 1.0,
    },
}

LANE = 2000  # длина линии в пикселях
BOUNTY = 0.02  # доля стоимости здания в награде за убийство
SLOTS = 12  # максимум зданий у игрока
MAX_ULT = 2  # максимум ult-зданий
UPG_BONUS = 0.1  # +10% HP и урона за уровень апгрейда
UPG_MAX = 5
UPG_COST = [100, 150, 200, 250, 300]
SD_RATE = 0.1  # ослабление замка на 10% за минуту после SD
SD_MIN_MULT = 0.2  # нижняя граница множителя урона замка

# Базовые параметры замка (HP переопределяется режимом в ECON)
CASTLE = dict(hp=6000, dmg=200, cd=0.35, rng=300, shots=1, armor=ArmorType.C)

# Экономика по режимам. castle_hp — HP замка в этом режиме.
ECON = {
    # v3: быстрее старт обычного режима (было start=60, base=15)
    "normal": dict(start=90, base=20, inc=5, step=60, cap=55, sd=20, castle_hp=15000),
    "turbo": dict(start=80, base=30, inc=10, step=60, cap=70, sd=10, castle_hp=6000),
}


# --- v3: удар игрока кликом (меч героя) ------------------------------------
# урон по уровням меча 0..4, перезарядка удара (кап частоты кликов), цены улучшений 0→1..3→4
STRIKE_DMG = (14, 22, 32, 44, 58)
STRIKE_CD = 0.4
SWORD_COST = (40, 70, 110, 160)

# --- v3: продажа зданий --------------------------------------------------
SELL_REFUND = 0.6  # 60% стоимости

# --- v3: лавка -----------------------------------------------------------
SHOP = {
    # +25% урона всей армии на 30 с
    "rage": dict(cost=60, cd=75.0, dur=30.0, mult=1.25),
    # -20% получаемого армией урона на 30 с
    "stone": dict(cost=60, cd=75.0, dur=30.0, mult=0.8),
    # ремонт замка: +8% от макс. HP, не больше 3 раз за матч
    "repair": dict(cost=80, cd=90.0, frac=0.08, uses=3),
    # бомба: падает через delay с, бьёт врагов в радиусе (единицы линии)
    "bomb": dict(cost=170, cd=100.0, delay=1.2, radius=100.0, dmg=500.0),
}

# --- v3: свои механики ---------------------------------------------------
ADJ_SPAWN_MULT = 0.92  # «Соседство»: такое же здание рядом (по стороне клетки) → спавн на 8% чаще
INTEREST = dict(every=30.0, rate=0.03, cap=6.0)  # «Казна»: каждые 30 с +3% от запаса, не больше 6


def damage_multiplier(dtype: DamageType, armor: ArmorType) -> float:
    """Вернуть множитель урона dtype по броне armor."""
    return MULT[dtype][armor]


def kill_bounty(cost: int) -> int:
    """Награда за убийство юнита здания стоимости cost (миньоны — 0 отдельно)."""
    return max(1, round(cost * BOUNTY))
