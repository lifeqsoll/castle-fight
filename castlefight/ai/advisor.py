"""ML-советник: KNN и дерево решений по логам победных покупок."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import joblib
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.neighbors import KNeighborsClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier

from castlefight.ai.bots import POOL, Bot, CounterBot, MixedBot
from castlefight.core.game import Game, simulate
from castlefight.core.player import Player
from castlefight.core.world import World
from castlefight.data.enums import ArmorType, Role
from castlefight.data.factions import FACTION_NAMES, FACTIONS

ROLE_ORDER = (Role.MELEE, Role.RANGED, Role.SUMMON, Role.ULT)
ARMOR_ORDER = (ArmorType.L, ArmorType.M, ArmorType.H, ArmorType.S, ArmorType.R)
DEFAULT_MODEL_PATH = Path(__file__).resolve().parent / "advisor_model.joblib"


def faction_one_hot(name: str) -> list[float]:
    return [1.0 if n == name else 0.0 for n in FACTION_NAMES]


def armor_shares(player: Player) -> list[float]:
    mix = {a: 0.0 for a in ARMOR_ORDER}
    for b in player.buildings:
        u = b.building_type.unit
        w = u.hp / b.building_type.spawn
        if u.armor in mix:
            mix[u.armor] += w
        if u.minion is not None and u.every:
            m = u.minion
            if m.armor in mix:
                mix[m.armor] += m.hp / u.every * 0.7
    total = sum(mix.values()) or 1.0
    return [mix[a] / total for a in ARMOR_ORDER]


def extract_features(player: Player, enemy: Player, t: float) -> list[float]:
    """Признаки одной покупки."""
    my_roles = player.counts()
    en_roles = enemy.counts()
    feats: list[float] = [
        t / 60.0,
        float(player.gold),
        *my_roles,
        *en_roles,
        *armor_shares(enemy),
        *faction_one_hot(player.faction.name),
        *faction_one_hot(enemy.faction.name),
    ]
    return feats


class LoggingBot(Bot):
    """Обёртка: логирует успешные покупки."""

    def __init__(self, inner: Bot) -> None:
        super().__init__(jitter=inner.jitter)
        self.inner = inner
        self.logs: list[tuple[list[float], int]] = []
        self.name = f"log:{inner.name}"

    def choose(self, me: Player, en: Player, t: float, rng) -> Optional[int]:
        self.inner.plan = self.plan
        self.inner.done = self.done
        k = self.inner.choose(me, en, t, rng)
        self.plan = self.inner.plan
        self.done = self.inner.done
        if k is not None and me.can_buy(k):
            self.logs.append((extract_features(me, en, t), k))
        return k


def collect_dataset(n_matches: int = 2000, mode: str = "normal", seed0: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """Собрать (X, y) только из покупок победителей."""
    xs: list[list[float]] = []
    ys: list[int] = []
    rng_meta = np.random.default_rng(seed0)
    names = list(FACTION_NAMES)
    for i in range(n_matches):
        fa, fb = rng_meta.choice(names, size=2, replace=True)
        ba_cls = POOL[int(rng_meta.integers(0, len(POOL)))]
        bb_cls = POOL[int(rng_meta.integers(0, len(POOL)))]
        bot_a = LoggingBot(ba_cls())
        bot_b = LoggingBot(bb_cls())
        result = simulate(fa, fb, bot_a, bot_b, mode=mode, seed=seed0 + i + 1)
        winner_logs = bot_a.logs if result["winner"] == 0 else bot_b.logs
        for feats, label in winner_logs:
            xs.append(feats)
            ys.append(label)
    return np.asarray(xs, dtype=float), np.asarray(ys, dtype=int)


def _collect_chunk(args):
    n, mode, seed0 = args
    return collect_dataset(n_matches=n, mode=mode, seed0=seed0)


def collect_parallel(n_matches: int, mode: str = "normal", procs: int = 8) -> tuple[np.ndarray, np.ndarray]:
    from multiprocessing import Pool

    per = max(1, n_matches // procs)
    jobs = [(per, mode, 100_000 * (k + 1)) for k in range(procs)]
    with Pool(procs) as pool:
        parts = pool.map(_collect_chunk, jobs)
    return np.concatenate([p[0] for p in parts]), np.concatenate([p[1] for p in parts])


def train_advisor(
    n_matches: int = 2000,
    mode: str = "normal",
    model_path: Path | str = DEFAULT_MODEL_PATH,
) -> dict[str, Any]:
    """Обучить kNN (старый вариант), дерево, RandomForest и HistGradientBoosting;
    сравнить точность на отложенных 20% и сохранить лучшую модель."""
    from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier

    X, y = collect_parallel(n_matches, mode)
    try:
        X_train, X_val, y_train, y_val = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    except ValueError:
        X_train, X_val, y_train, y_val = train_test_split(X, y, test_size=0.2, random_state=42)
    models = {
        "knn": Pipeline([("scaler", StandardScaler()), ("clf", KNeighborsClassifier(n_neighbors=7))]),
        "tree": DecisionTreeClassifier(max_depth=6, random_state=42),
        "forest": RandomForestClassifier(n_estimators=150, max_depth=14, min_samples_leaf=3, n_jobs=-1, random_state=42),
        "hgb": HistGradientBoostingClassifier(max_iter=250, learning_rate=0.08, random_state=42),
    }
    accs: dict[str, float] = {}
    for name, m in models.items():
        m.fit(X_train, y_train)
        accs[name] = float(m.score(X_val, y_val))
    best_name = max(accs, key=accs.get)
    best = models[best_name]
    if best_name == "forest":
        best.set_params(n_jobs=1)  # в игре — один поток, быстрый отклик
    path = Path(model_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": best, "name": best_name, "accs": accs, "knn_acc": accs["knn"]}, path)
    return {"n_samples": len(y), "accs": accs, "best": best_name, "path": str(path)}


class Advisor:
    """Советник: suggest(player, world) -> Role."""

    def __init__(self, model_path: Path | str = DEFAULT_MODEL_PATH) -> None:
        payload = joblib.load(model_path)
        self.model = payload["model"]
        self.name = payload.get("name", "model")

    def suggest(self, player: Player, world: World) -> Role:
        enemy = world.players[1 - player.side]
        feats = np.asarray([extract_features(player, enemy, world.t)], dtype=float)
        idx = int(self.model.predict(feats)[0])
        return ROLE_ORDER[idx]


class MLBot(Bot):
    """Бот, покупающий роль из советника (с запасным Mixed)."""

    name = "ml"

    def __init__(self, advisor: Advisor, jitter: float = 0.05) -> None:
        super().__init__(jitter=jitter)
        self.advisor = advisor
        self._fallback = MixedBot(jitter=jitter)

    def pick(self, me: Player, en: Player, t: float, rng) -> int:
        # World передаётся через временный атрибут, если есть
        world = getattr(me, "_world_ref", None)
        if world is None:
            return self._fallback.pick(me, en, t, rng)
        role = self.advisor.suggest(me, world)
        return ROLE_ORDER.index(role)

    def want_ult(self, me: Player, counts: list[int], t: float) -> bool:
        return False  # роль выбирает модель целиком через plan

    def choose(self, me: Player, en: Player, t: float, rng) -> Optional[int]:
        world = getattr(me, "_world_ref", None)
        if world is None:
            return self._fallback.choose(me, en, t, rng)
        if len(me.buildings) >= 12:
            return None
        if self.plan is None:
            role = self.advisor.suggest(me, world)
            self.plan = ROLE_ORDER.index(role)
            # если ult недоступен — fallback на pick mixed
            if self.plan == 3 and not me.can_buy(3) and me.gold < me.defs[3].cost:
                pass
            if self.plan == 3 and me.ult_count() >= 2:
                self.plan = self._fallback.pick(me, en, t, rng)
        k = self.plan
        if me.gold >= me.defs[k].cost and me.can_buy(k):
            self.plan = None
            return k
        if not me.can_buy(k) and k == 3:
            self.plan = self._fallback.pick(me, en, t, rng)
        return None


def attach_world_refs(game: Game) -> None:
    """Чтобы MLBot видел World через игрока."""
    for p in game.players:
        p._world_ref = game.world  # noqa: SLF001


def eval_ml_vs_counter(n: int = 40, mode: str = "normal", model_path: Path | str = DEFAULT_MODEL_PATH) -> dict[str, float]:
    advisor = Advisor(model_path)
    wins = 0
    for i in range(n):
        fa = FACTION_NAMES[i % len(FACTION_NAMES)]
        fb = FACTION_NAMES[(i * 3) % len(FACTION_NAMES)]
        game = Game(fa, fb, MLBot(advisor), CounterBot(), mode=mode, seed=1000 + i)
        attach_world_refs(game)
        result = game.run()
        if result["winner"] == 0:
            wins += 1
    return {"wins": wins, "games": n, "winrate": wins / n}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--matches", type=int, default=2000)
    parser.add_argument("--mode", default="normal")
    parser.add_argument("--eval", type=int, default=40)
    args = parser.parse_args()
    info = train_advisor(n_matches=args.matches, mode=args.mode)
    print(info)
    print(eval_ml_vs_counter(n=args.eval, mode=args.mode, model_path=info["path"]))
