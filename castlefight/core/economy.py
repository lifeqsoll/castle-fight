"""Доход по времени и награды за убийства."""

from __future__ import annotations


def income_rate(t: float, econ: dict) -> float:
    """Золото в минуту в момент времени t (секунды)."""
    minute = int(t // econ["step"])
    return min(econ["cap"], econ["base"] + econ["inc"] * minute)


def income_for_tick(t: float, econ: dict, dt: float) -> float:
    """Золото за один тик dt."""
    return income_rate(t, econ) / 60.0 * dt
