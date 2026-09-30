"""Deterministic, simplified Pokémon team comparison engine.

Teams are compared by AGGREGATE power — every stat is summed across the team,
then a type-based modifier adjusts the score based on offensive coverage,
defensive resistances and exploitable weaknesses. There are no 1-v-1 duels.
"""
from app.type_chart import (TYPES, defensive_profile, offensive_coverage,
                            type_effectiveness, effectiveness_label)


# ----------------------------------------------------------------------
# Aggregation
# ----------------------------------------------------------------------
def compute_team_stats(team):
    """Sum every base stat across the team."""
    return {
        "hp": sum(int(p.get("hp", 0)) for p in team),
        "attack": sum(int(p.get("attack", 0)) for p in team),
        "defense": sum(int(p.get("defense", 0)) for p in team),
        "sp_attack": sum(int(p.get("sp_attack", 0)) for p in team),
        "sp_defense": sum(int(p.get("sp_defense", 0)) for p in team),
        "speed": sum(int(p.get("speed", 0)) for p in team),
        "bst": sum(int(p.get("bst", 0)) for p in team),
        "count": len(team),
    }


def team_synergy(team):
    """Single number describing type variety vs defensive holes."""
    if not team:
        return 0
    attacking = set()
    defending = []
    for p in team:
        types = list(p.get("types") or [])
        attacking.update(types)
        defending.extend(types)

    coverage = len(offensive_coverage(attacking))
    profile = defensive_profile(defending)
    weaknesses = sum(1 for v in profile.values() if v > 1)
    resistances = sum(1 for v in profile.values() if 0 < v < 1)
    immunities = sum(1 for v in profile.values() if v == 0)
    return coverage * 2 + resistances + immunities * 2 - weaknesses


def compute_team_power(team):
    """Full comparison profile for a team."""
    empty = {
        "stats": {"hp": 0, "attack": 0, "defense": 0, "sp_attack": 0,
                  "sp_defense": 0, "speed": 0, "bst": 0, "count": 0},
        "coverage": 0,
        "coverage_types": [],
        "weaknesses": 0,
        "weakness_types": [],
        "resistances": 0,
        "resistance_types": [],
        "immunities": 0,
        "immunity_types": [],
        "unique_types": 0,
        "synergy": 0,
        "type_modifier": 1.0,
        "power_score": 0.0,
    }
    if not team:
        return empty

    stats = compute_team_stats(team)

    attacking = set()
    defending = []
    for p in team:
        types = list(p.get("types") or [])
        attacking.update(types)
        defending.extend(types)

    coverage_set = offensive_coverage(attacking)
    profile = defensive_profile(defending)
    weakness_types = sorted([t for t, v in profile.items() if v > 1])
    resistance_types = sorted([t for t, v in profile.items() if 0 < v < 1])
    immunity_types = sorted([t for t, v in profile.items() if v == 0])

    coverage = len(coverage_set)
    weaknesses = len(weakness_types)
    resistances = len(resistance_types)
    immunities = len(immunity_types)
    unique_types = len(attacking)
    synergy = team_synergy(team)

    # ---- Final power score ---------------------------------------------
    # Start from raw BST, then apply a bounded type-based modifier.
    coverage_bonus = coverage * 0.020        # 18/18 → +36%
    resistance_bonus = resistances * 0.015   # 18 resists → +27%
    immunity_bonus = immunities * 0.035      # each immunity is meaningful
    weakness_penalty = weaknesses * 0.015    # 18 weaknesses → -27%
    diversity_bonus = unique_types * 0.005   # small reward for variety

    type_modifier = (
        1.0
        + coverage_bonus
        + resistance_bonus
        + immunity_bonus
        + diversity_bonus
        - weakness_penalty
    )
    # Clamp so modifiers stay reasonable
    type_modifier = max(0.5, min(2.5, type_modifier))

    power_score = round(stats["bst"] * type_modifier, 2)

    return {
        "stats": stats,
        "coverage": coverage,
        "coverage_types": sorted(coverage_set),
        "weaknesses": weaknesses,
        "weakness_types": weakness_types,
        "resistances": resistances,
        "resistance_types": resistance_types,
        "immunities": immunities,
        "immunity_types": immunity_types,
        "unique_types": unique_types,
        "synergy": synergy,
        "type_modifier": round(type_modifier, 3),
        "power_score": power_score,
    }


def analyse_team(team):
    """Human-readable breakdown used by the results page."""
    info = compute_team_power(team)
    return {
        "unique_types": sorted({t for p in team for t in (p.get("types") or [])}),
        "unique_type_count": info["unique_types"],
        "offensive_coverage": info["coverage_types"],
        "coverage_count": info["coverage"],
        "weaknesses": info["weakness_types"],
        "resistances": info["resistance_types"],
        "immunities": info["immunity_types"],
        "synergy": info["synergy"],
        "power_score": info["power_score"],
    }


# ----------------------------------------------------------------------
# Head-to-head comparison
# ----------------------------------------------------------------------
STAT_ORDER = ["hp", "attack", "defense", "sp_attack", "sp_defense", "speed"]
STAT_LABELS = {
    "hp": "HP",
    "attack": "Attack",
    "defense": "Defense",
    "sp_attack": "Sp. Atk",
    "sp_defense": "Sp. Def",
    "speed": "Speed",
}


def simulate_team_battle(team_a, team_b, name_a="Team A", name_b="Team B"):
    """Compare two teams by aggregate power score. Fully deterministic."""
    info_a = compute_team_power(team_a)
    info_b = compute_team_power(team_b)

    stats_a = info_a["stats"]
    stats_b = info_b["stats"]
    score_a = info_a["power_score"]
    score_b = info_b["power_score"]

    # ---- per-stat category wins (used as a tiebreak & for the UI) -----
    wins_a = 0
    wins_b = 0
    draws = 0
    per_stat = []

    for key in STAT_ORDER:
        va = stats_a.get(key, 0)
        vb = stats_b.get(key, 0)
        if va > vb:
            wins_a += 1
            winner = "a"
        elif vb > va:
            wins_b += 1
            winner = "b"
        else:
            draws += 1
            winner = "draw"
        per_stat.append({
            "key": key,
            "label": STAT_LABELS[key],
            "a": va,
            "b": vb,
            "winner": winner,
            "diff": va - vb,
        })

    # ---- overall winner -------------------------------------------------
    tiebreak = ""
    if score_a > score_b:
        winner = "a"
    elif score_b > score_a:
        winner = "b"
    elif stats_a["bst"] > stats_b["bst"]:
        winner = "a"
        tiebreak = "total base stats"
    elif stats_b["bst"] > stats_a["bst"]:
        winner = "b"
        tiebreak = "total base stats"
    elif info_a["synergy"] > info_b["synergy"]:
        winner = "a"
        tiebreak = "team synergy"
    elif info_b["synergy"] > info_a["synergy"]:
        winner = "b"
        tiebreak = "team synergy"
    else:
        winner = "a" if name_a.lower() <= name_b.lower() else "b"
        tiebreak = "seed order"

    total_score = score_a + score_b
    hp_a_pct = round(100 * score_a / total_score, 2) if total_score else 0.0
    hp_b_pct = round(100 * score_b / total_score, 2) if total_score else 0.0

    return {
        "winner": winner,
        "score_a": score_a,
        "score_b": score_b,
        "wins_a": wins_a,          # stat categories won
        "wins_b": wins_b,
        "draws": draws,
        "hp_a_pct": hp_a_pct,
        "hp_b_pct": hp_b_pct,
        "synergy_a": info_a["synergy"],
        "synergy_b": info_b["synergy"],
        "stats_a": stats_a,
        "stats_b": stats_b,
        "power_a": info_a,
        "power_b": info_b,
        "per_stat": per_stat,
        "tiebreak": tiebreak,
        "name_a": name_a,
        "name_b": name_b,
    }


# ----------------------------------------------------------------------
# Round-robin tournament (interface unchanged)
# ----------------------------------------------------------------------
def run_tournament(participants):
    standings = {
        p["id"]: {
            "id": p["id"],
            "name": p["name"],
            "points": 0.0,
            "battles_won": 0,
            "battles_lost": 0,
            "matchup_wins": 0,
            "matchup_losses": 0,
            "matchup_draws": 0,
            "hp_left": 0.0,
            "synergy": team_synergy(p["team"]),
            "bst": sum(int(m.get("bst", 0)) for m in p["team"]),
            "team": p["team"],
        }
        for p in participants
    }

    battles = []
    for i in range(len(participants)):
        for j in range(i + 1, len(participants)):
            A, B = participants[i], participants[j]
            res = simulate_team_battle(A["team"], B["team"], A["name"], B["name"])

            if res["winner"] == "a":
                winner_id, loser_id = A["id"], B["id"]
            else:
                winner_id, loser_id = B["id"], A["id"]

            standings[winner_id]["points"] += 1
            standings[winner_id]["battles_won"] += 1
            standings[loser_id]["battles_lost"] += 1

            standings[A["id"]]["matchup_wins"] += res["wins_a"]
            standings[A["id"]]["matchup_losses"] += res["wins_b"]
            standings[A["id"]]["matchup_draws"] += res["draws"]
            standings[A["id"]]["hp_left"] += res["hp_a_pct"]

            standings[B["id"]]["matchup_wins"] += res["wins_b"]
            standings[B["id"]]["matchup_losses"] += res["wins_a"]
            standings[B["id"]]["matchup_draws"] += res["draws"]
            standings[B["id"]]["hp_left"] += res["hp_b_pct"]

            battles.append({
                "player_a": A["id"],
                "player_b": B["id"],
                "name_a": A["name"],
                "name_b": B["name"],
                "result": res,
                "winner_id": winner_id,
            })

    ranked = list(standings.values())
    ranked.sort(
        key=lambda s: (-s["points"], -s["matchup_wins"], -s["hp_left"],
                       -s["synergy"], -s["bst"], s["name"].lower())
    )
    for idx, row in enumerate(ranked, start=1):
        row["rank"] = idx
        row["hp_left"] = round(row["hp_left"], 1)

    return ranked, battles
