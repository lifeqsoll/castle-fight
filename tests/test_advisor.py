import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier

from castlefight.ai.advisor import Advisor, MLBot, eval_ml_vs_counter, train_advisor
from castlefight.core.game import Game
from castlefight.data.enums import Role


def test_training_saves_one_gradient_boosting_model(monkeypatch, tmp_path):
    features = np.zeros((20, 27), dtype=float)
    roles = np.array([0] * 10 + [1] * 10)
    monkeypatch.setattr(
        "castlefight.ai.advisor.collect_dataset",
        lambda n_matches, mode: (features, roles),
    )
    model_path = tmp_path / "advisor.joblib"

    result = train_advisor(model_path=model_path)
    advisor = Advisor(model_path)
    game = Game("Лес", "Аркана")

    assert result["model"] == "HistGradientBoostingClassifier"
    assert result["n_samples"] == len(roles)
    assert isinstance(advisor.model, HistGradientBoostingClassifier)
    assert advisor.suggest(game.players[0], game.world) in (
        game.players[0].defs[0].role,
        game.players[0].defs[1].role,
    )
    assert MLBot(advisor).choose(
        game.players[0],
        game.players[1],
        game.world.t,
        game.rng,
        game.world,
    ) in (0, 1)


def test_game_passes_world_to_ml_bot():
    calls = []

    class FixedAdvisor:
        def suggest(self, player, world):
            assert world.players[player.side] is player
            calls.append(player.side)
            return Role.MELEE

    game = Game(
        "Лес",
        "Аркана",
        MLBot(FixedAdvisor()),
        mode="normal",
        bot_shop=False,
        bot_click=False,
    )

    game.step()

    assert calls
    assert game.players[0].counts()[0] > 0


def test_evaluation_balances_factions_and_bot_sides(monkeypatch):
    import castlefight.ai.advisor as advisor_module

    games = []

    class FakeGame:
        def __init__(self, faction_a, faction_b, bot_a, bot_b, **kwargs):
            games.append((faction_a, faction_b, bot_a, bot_b))
            self.ml_side = 0 if isinstance(bot_a, MLBot) else 1

        def run(self):
            return {"winner": self.ml_side}

    monkeypatch.setattr(advisor_module, "Advisor", lambda model_path: object())
    monkeypatch.setattr(advisor_module, "Game", FakeGame)

    result = eval_ml_vs_counter(n=72)

    assert result == {"wins": 72, "games": 72, "winrate": 1.0}
    for first, second in zip(games[::2], games[1::2]):
        assert first[0] == second[1]
        assert first[1] == second[0]
        assert isinstance(first[2], MLBot)
        assert isinstance(second[3], MLBot)
