from __future__ import annotations

import random
from pathlib import Path
from typing import Any, Optional

import joblib
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.model_selection import train_test_split

from castlefight.ai.bots import Bot, CounterBot, MixedBot, POOL
from castlefight.core.game import Game
from castlefight.core.player import Player
from castlefight.core.world import World
from castlefight.data.balance import MAX_ULT, SLOTS
from castlefight.data.enums import ArmorType, Role
from castlefight.data.factions import FACTION_NAMES

ROLE_ORDER = (Role.MELEE, Role.RANGED, Role.SUMMON, Role.ULT)
ARMOR_ORDER = (ArmorType.L, ArmorType.M, ArmorType.H, ArmorType.S, ArmorType.R)
DEFAULT_MODEL_PATH = Path(__file__).resolve().parent / "advisor_model.joblib"


def extract_features(player: Player, enemy: Player, t: float) -> list[float]:
    armor = [0.0] * len(ARMOR_ORDER)
    for building in enemy.buildings:
        unit = building.building_type.unit
        if unit.armor in ARMOR_ORDER:
            armor[ARMOR_ORDER.index(unit.armor)] += unit.hp / building.building_type.spawn
        if unit.minion is not None and unit.every:
            if unit.minion.armor in ARMOR_ORDER:
                armor[ARMOR_ORDER.index(unit.minion.armor)] += unit.minion.hp / unit.every * 0.7
    armor_total = sum(armor) or 1.0
    armor = [value / armor_total for value in armor]

    return [
        t / 60.0,
        float(player.gold),
        *player.counts(),
        *enemy.counts(),
        *armor,
        *(float(name == player.faction.name) for name in FACTION_NAMES),
        *(float(name == enemy.faction.name) for name in FACTION_NAMES),
    ]


class LoggingBot(Bot):
    """Записывает покупки бота для обучающей выборки."""

    def __init__(self, bot: Bot) -> None:
        super().__init__(jitter=bot.jitter)
        self.bot = bot
        self.logs: list[tuple[list[float], int]] = []
        self.name = f"log:{bot.name}"

    def choose(
        self,
        me: Player,
        en: Player,
        t: float,
        rng: random.Random,
        world: World | None = None,
    ) -> Optional[int]:
        self.bot.plan = self.plan
        self.bot.done = self.done
        role = self.bot.choose(me, en, t, rng, world)
        self.plan = self.bot.plan
        self.done = self.bot.done
        if role is not None and me.can_buy(role) and world is not None:
            self.logs.append((extract_features(me, en, t), role))
        return role


def collect_dataset(
    n_matches: int = 2000,
    mode: str = "normal",
    seed: int = 0,
) -> tuple[np.ndarray, np.ndarray]:
    rng = random.Random(seed)
    features: list[list[float]] = []
    roles: list[int] = []

    for match in range(n_matches):
        faction_a = rng.choice(FACTION_NAMES)
        faction_b = rng.choice(FACTION_NAMES)
        bot_a = LoggingBot(rng.choice(POOL)())
        bot_b = LoggingBot(rng.choice(POOL)())
        game = Game(
            faction_a,
            faction_b,
            bot_a,
            bot_b,
            mode=mode,
            seed=seed + match + 1,
        )
        result = game.run()
        winner = result["winner"]
        if winner not in (0, 1):
            continue

        logs = (bot_a, bot_b)[winner].logs
        for sample, role in logs:
            features.append(sample)
            roles.append(role)

    return np.asarray(features, dtype=float), np.asarray(roles, dtype=int)


def train_advisor(
    n_matches: int = 2000,
    mode: str = "normal",
    model_path: Path | str = DEFAULT_MODEL_PATH,
) -> dict[str, Any]:
    features, roles = collect_dataset(n_matches, mode)
    if len(roles) < 10 or len(np.unique(roles)) < 2:
        raise ValueError("Для обучения нужны хотя бы 10 покупок и два разных типа зданий.")

    _, counts = np.unique(roles, return_counts=True)
    if counts.min() < 2:
        raise ValueError("Для каждого типа здания в обучающей выборке нужны минимум две покупки.")

    x_train, x_test, y_train, y_test = train_test_split(
        features,
        roles,
        test_size=0.2,
        random_state=42,
        stratify=roles,
    )
    model = HistGradientBoostingClassifier(
        max_iter=250,
        learning_rate=0.08,
        random_state=42,
    )
    model.fit(x_train, y_train)
    accuracy = float(model.score(x_test, y_test))
    model.fit(features, roles)

    path = Path(model_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, path)
    return {
        "n_samples": len(roles),
        "accuracy": accuracy,
        "model": "HistGradientBoostingClassifier",
        "path": str(path),
    }


class Advisor:
    def __init__(self, model_path: Path | str = DEFAULT_MODEL_PATH) -> None:
        self.model: HistGradientBoostingClassifier = joblib.load(model_path)

    def suggest(self, player: Player, world: World) -> Role:
        enemy = world.players[1 - player.side]
        features = np.asarray([extract_features(player, enemy, world.t)], dtype=float)
        role = int(self.model.predict(features)[0])
        return ROLE_ORDER[role]


class MLBot(Bot):
    name = "gradient_boosting"

    def __init__(self, advisor: Advisor) -> None:
        super().__init__(jitter=0)
        self.advisor = advisor
        self.fallback = MixedBot(jitter=0)

    def choose(
        self,
        me: Player,
        en: Player,
        t: float,
        rng: random.Random,
        world: World | None = None,
    ) -> Optional[int]:
        if world is None:
            return self.fallback.choose(me, en, t, rng)
        if len(me.buildings) >= SLOTS:
            return None

        if self.plan is None:
            self.plan = ROLE_ORDER.index(self.advisor.suggest(me, world))
        role = self.plan

        if me.can_buy(role):
            self.plan = None
            return role
        if role == 3 and me.ult_count() >= MAX_ULT:
            self.plan = self.fallback.pick(me, en, t, rng)
        return None


def eval_ml_vs_counter(
    n: int = 40,
    mode: str = "normal",
    model_path: Path | str = DEFAULT_MODEL_PATH,
) -> dict[str, float]:
    advisor = Advisor(model_path)
    wins = 0
    for match in range(n):
        pair = match // 2
        faction_a = FACTION_NAMES[pair % len(FACTION_NAMES)]
        faction_b = FACTION_NAMES[(pair // len(FACTION_NAMES)) % len(FACTION_NAMES)]
        ml_side = match % 2
        if ml_side:
            faction_a, faction_b = faction_b, faction_a
            bot_a, bot_b = CounterBot(), MLBot(advisor)
        else:
            bot_a, bot_b = MLBot(advisor), CounterBot()
        game = Game(
            faction_a,
            faction_b,
            bot_a,
            bot_b,
            mode=mode,
            seed=1000 + match,
        )
        if game.run()["winner"] == ml_side:
            wins += 1
    return {"wins": wins, "games": n, "winrate": wins / n}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--matches", type=int, default=2000)
    parser.add_argument("--mode", default="normal")
    parser.add_argument("--eval", type=int, default=40)
    args = parser.parse_args()
    result = train_advisor(n_matches=args.matches, mode=args.mode)
    print(result)
    print(eval_ml_vs_counter(n=args.eval, mode=args.mode, model_path=result["path"]))
