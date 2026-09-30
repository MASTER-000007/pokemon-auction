"""Type chart + deterministic battle engine."""
from app.battle import (analyse_team, run_tournament, simulate_duel,
                        simulate_team_battle, team_synergy)
from app.type_chart import CHART, type_effectiveness


def _mon(dex_id, name, types, **stats):
    base = {"id": dex_id, "name": name, "types": list(types),
            "hp": 80, "attack": 100, "defense": 80,
            "sp_attack": 100, "sp_defense": 80, "speed": 100,
            "bst": 540, "is_legendary": False, "is_mythical": False}
    base.update(stats)
    return base


# ------------------------- type chart -------------------------
def test_type_chart_basics():
    assert type_effectiveness("water", ["fire"]) == 2.0
    assert type_effectiveness("electric", ["ground"]) == 0.0
    assert type_effectiveness("normal", ["ghost"]) == 0.0
    assert type_effectiveness("ice", ["dragon", "flying"]) == 4.0
    assert type_effectiveness("fire", ["water", "rock"]) == 0.25
    assert type_effectiveness("fire", ["normal"]) == 1.0


def test_type_chart_is_complete():
    for attacking, row in CHART.items():
        assert len(row) == 18, attacking


# ------------------------- duels -------------------------
def test_duel_is_deterministic():
    a = _mon(6, "Charizard", ["fire", "flying"], speed=100)
    b = _mon(3, "Venusaur", ["grass", "poison"], speed=80)
    first = simulate_duel(a, b)
    second = simulate_duel(a, b)
    assert first["winner"] == second["winner"]
    assert first["turns"] == second["turns"]
    assert first["a"]["hp_left"] == second["a"]["hp_left"]


def test_faster_pokemon_strikes_first():
    fast = _mon(1, "Fast", ["normal"], speed=200)
    slow = _mon(2, "Slow", ["normal"], speed=10)
    result = simulate_duel(fast, slow)
    assert result["winner"] == "a"


def test_type_advantage_matters():
    water = _mon(1, "Water", ["water"], speed=120)
    fire = _mon(2, "Fire", ["fire"], speed=100)
    result = simulate_duel(water, fire)
    assert result["winner"] == "a"


def test_immunity_is_respected():
    electric = _mon(1, "Zap", ["electric"], speed=200)
    ground = _mon(2, "Quake", ["ground"], speed=10)
    result = simulate_duel(electric, ground)
    # Ground is immune to electric; electric takes normal damage from ground moves
    assert result["winner"] == "b"


def test_duel_produces_battle_log():
    a = _mon(1, "A", ["fire"])
    b = _mon(2, "B", ["grass"])
    result = simulate_duel(a, b)
    assert result["log"]
    assert any("hit" in line or "no effect" in line for line in result["log"])


# ------------------------- team battles -------------------------
def test_team_battle_slot_by_slot():
    team_a = [_mon(i, f"A{i}", ["water"]) for i in range(1, 5)]
    team_b = [_mon(i + 10, f"B{i}", ["fire"]) for i in range(1, 5)]
    result = simulate_team_battle(team_a, team_b)
    assert result["wins_a"] == 4
    assert result["wins_b"] == 0
    assert result["winner"] == "a"
    assert len(result["slots"]) == 4


def test_team_battle_never_draws():
    team_a = [_mon(i, f"A{i}", ["normal"]) for i in range(1, 5)]
    team_b = [_mon(i, f"B{i}", ["normal"]) for i in range(1, 5)]
    result = simulate_team_battle(team_a, team_b)
    assert result["winner"] in ("a", "b")


def test_team_battle_tiebreak_by_hp():
    # Identical teams -> 2-2 with equal HP -> deterministic tiebreak path
    team_a = [_mon(i, f"A{i}", ["normal"]) for i in range(1, 5)]
    team_b = [_mon(i, f"B{i}", ["normal"]) for i in range(1, 5)]
    result = simulate_team_battle(team_a, team_b)
    assert result["wins_a"] == result["wins_b"] or result["tiebreak"]


# ------------------------- synergy / coverage -------------------------
def test_team_synergy_rewards_variety():
    diverse = [_mon(1, "A", ["fire"]), _mon(2, "B", ["water"]),
               _mon(3, "C", ["grass"]), _mon(4, "D", ["electric"])]
    mono = [_mon(1, "A", ["fire"]), _mon(2, "B", ["fire"]),
            _mon(3, "C", ["fire"]), _mon(4, "D", ["fire"])]
    assert team_synergy(diverse) > team_synergy(mono)


def test_analyse_team_reports_weaknesses():
    team = [_mon(1, "A", ["fire", "flying"]), _mon(2, "B", ["water"]),
            _mon(3, "C", ["grass"]), _mon(4, "D", ["electric"])]
    report = analyse_team(team)
    assert "rock" in report["weaknesses"] or "electric" in report["weaknesses"]
    assert report["coverage_count"] > 0


# ------------------------- tournament -------------------------
def test_tournament_is_deterministic_and_ranked():
    participants = [
        {"id": 1, "name": "Ash", "team": [_mon(i, f"A{i}", ["water"]) for i in range(1, 5)]},
        {"id": 2, "name": "Misty", "team": [_mon(i, f"B{i}", ["fire"]) for i in range(1, 5)]},
        {"id": 3, "name": "Brock", "team": [_mon(i, f"C{i}", ["grass"]) for i in range(1, 5)]},
    ]
    board1, battles1 = run_tournament(participants)
    board2, battles2 = run_tournament(participants)

    assert [r["id"] for r in board1] == [r["id"] for r in board2]
    assert len(battles1) == 3        # 3 players -> 3 pairings
    assert sum(r["points"] for r in board1) == 3
    assert board1[0]["rank"] == 1
    assert board1[-1]["rank"] == len(board1)


def test_tournament_points_match_wins():
    participants = [
        {"id": 1, "name": "A", "team": [_mon(i, f"A{i}", ["water"]) for i in range(1, 5)]},
        {"id": 2, "name": "B", "team": [_mon(i, f"B{i}", ["fire"]) for i in range(1, 5)]},
    ]
    board, battles = run_tournament(participants)
    assert len(battles) == 1
    assert board[0]["points"] == 1
    assert board[1]["points"] == 0