"""Перечисления типов урона, брони и ролей зданий/юнитов."""

from enum import Enum


class DamageType(str, Enum):
    """Тип урона атаки."""

    SLASH = "slash"
    PIERCE = "pierce"
    MAGIC = "magic"
    CASTLE = "castle"  # выстрел башни замка


class ArmorType(str, Enum):
    """Тип брони цели."""

    L = "L"  # лёгкая
    M = "M"  # средняя
    H = "H"  # тяжёлая
    S = "S"  # рой
    R = "R"  # камень
    C = "C"  # замок


class Role(str, Enum):
    """Роль здания или юнита."""

    MELEE = "melee"
    RANGED = "ranged"
    SUMMON = "summon"
    ULT = "ult"
    MINION = "minion"
