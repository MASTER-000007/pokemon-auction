"""Deterministic, simplified Pokémon battle & scoring engine.

This is an ORIGINAL scoring system *inspired* by Pokémon mechanics — it is not
a re-implementation of the official battle engine.
"""
from app.type_chart import (TYPES, defensive_profile, offensive_coverage,
                            type_effectiveness, effectiveness_label)
from config import Config

LEVEL = Config.BATTLE_LEVEL
MOVE_POWER = Config.BATTLE_MOVE_POWER
MAX_TURNS = Config.BATTLE_MAX_TURNS
STAB = Config.STAB_MULTIPLIER


# ----------------------------------------------------------------------
# Preparation
# ----------------------------------------------------------------------
def _max_hp(base_hp):
    return 2 * base_hp + 110


def prepare(pokemon):
    p = dict(pokemon)
    p["types"] = list(pokemon.get("types") or ["normal"])
    p["max_hp"] = _max_hp(int(pokemon.get("hp", 50)))
    p["hp_left"] = p["max_hp"]
    p["bst"] = int(pokemon.get("bst", 0))

    moves = []
    for t in p["types"]:
        moves.append({"type": t, "power": MOVE_POWER, "category": "physical"})
        moves.append({"type": t, "power": MOVE_POWER, "category": "special"})
    if not moves:
        moves = [{"type": "normal", "power": MOVE_POWER, "category": "physical"},
                 {"type": "normal", "power": MOVE_POWER, "category": "special"}]
    p["moves"] = moves
    return p


# ----------------------------------------------------------------------
# Damage
# ----------------------------------------------------------------------
def compute_damage(attacker, defender, move):
    if move["category"] == "physical":
        atk = max(1, int(attacker.get("attack", 1)))
        dfn = max(1, int(defender.get("defense", 1)))
    else:
        atk = max(1, int(attacker.get("sp_attack", 1)))
        dfn = max(1, int(defender.get("sp_defense", 1)))

    eff = type_effectiveness(move["type"], defender["types"])
    if eff <= 0:
        return 0

    base = ((2 * LEVEL / 5 + 2) * move["power"] * atk / dfn) / 50 + 2
    stab = STAB if move["type"] in attacker["types"] else 1.0
    return max(1, int(base * stab * eff))


def choose_move(attacker, defender):
    best_move, best_damage = attacker["moves"][0], -1
    for move in attacker["moves"]:
        dmg = compute_damage(attacker, defender, move)
        if dmg > best_damage:
            best_damage, best_move = dmg, move
    return best_move, best_damage


# ----------------------------------------------------------------------
# 1 v 1 duel
# ----------------------------------------------------------------------
def simulate_duel(pokemon_a, pokemon_b):
    a = prepare(pokemon_a)
    b = prepare(pokemon_b)
    log = []

    def key(p):
        return (p.get("speed", 0), p.get("bst", 0), p.get("id", 0))

    turn = 0
    while a["hp_left"] > 0 and b["hp_left"] > 0 and turn < MAX_TURNS:
        turn += 1
        order = [a, b] if key(a) >= key(b) else [b, a]

        for attacker, defender in ((order[0], order[1]), (order[1], order[0])):
            if a["hp_left"] <= 0 or b["hp_left"] <= 0:
                break
            move, dmg = choose_move(attacker, defender)
            eff = type_effectiveness(move["type"], defender["types"])

            if dmg <= 0:
                log.append(f"{attacker['name']} used a {move['type'].title()} move — "
                           f"it had no effect on {defender['name']}!")
                continue

            defender["hp_left"] = max(0, defender["hp_left"] - dmg)
            log.append(
                f"{attacker['name']} hit {defender['name']} with a "
                f"{move['type'].title()} {move['category']} move for {dmg} dmg "
                f"({effectiveness_label(eff)}) — "
                f"{defender['name']} {defender['hp_left']}/{defender['max_hp']} HP"
            )

    if a["hp_left"] <= 0 and b["hp_left"] <= 0:
        winner = "draw"
    elif b["hp_left"] <= 0:
        winner = "a"
    elif a["hp_left"] <= 0:
        winner = "b"
    else:
        pa = a["hp_left"] / a["max_hp"]
        pb = b["hp_left"] / b["max_hp"]
        winner = "a" if pa > pb else ("b" if pb > pa else "draw")
        log.append(f"Turn limit reached — decided on remaining HP "
                   f"({a['name']} {pa:.0%} vs {b['name']} {pb:.0%}).")

    return {
        "winner": winner,
        "turns": turn,
        "a": {"id": a.get("id"), "name": a["name"], "hp_left": a["hp_left"],
              "max_hp": a["max_hp"], "hp_pct": a["hp_left"] / a["max_hp"]},
        "b": {"id": b.get("id"), "name": b["name"], "hp_left": b["hp_left"],
              "max_hp": b["max_hp"], "hp_pct": b["hp_left"] / b["max_hp"]},
        "log": log,
    }


# ----------------------------------------------------------------------
# Team synergy / type coverage
# ----------------------------------------------------------------------
def team_synergy(team):
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


def analyse_team(team):
    if not team:
        return {"coverage_count": 0, "weaknesses": [], "resistances": [],
                "immunities": [], "unique_types": [], "offensive_coverage": []}

    attacking = set()
    defending = []
    for p in team:
        types = list(p.get("types") or [])
        attacking.update(types)
        defending.extend(types)

    profile = defensive_profile(defending)
    return {
        "unique_types": sorted(attacking),
        "unique_type_count": len(attacking),
        "offensive_coverage": sorted(offensive_coverage(attacking)),
        "coverage_count": len(offensive_coverage(attacking)),
        "weaknesses": sorted([t for t, v in profile.items() if v > 1]),
        "resistances": sorted([t for t, v in profile.items() if 0 < v < 1]),
        "immunities": sorted([t for t, v in profile.items() if v == 0]),
        "synergy": team_synergy(team),
    }


# ----------------------------------------------------------------------
# Team battle
# ----------------------------------------------------------------------
def simulate_team_battle(team_a, team_b, name_a="Team A", name_b="Team B"):
    slots = min(len(team_a), len(team_b))
    wins_a = wins_b = draws = 0
    hp_a_total = hp_b_total = 0.0
    details = []

    for i in range(slots):
        result = simulate_duel(team_a[i], team_b[i])
        hp_a_total += result["a"]["hp_pct"]
        hp_b_total += result["b"]["hp_pct"]

        if result["winner"] == "a":
            wins_a += 1
        elif result["winner"] == "b":
            wins_b += 1
        else:
            draws += 1

        details.append({
            "slot": i + 1,
            "a": {"id": result["a"]["id"], "name": result["a"]["name"],
                  "hp_pct": round(result["a"]["hp_pct"] * 100, 1)},
            "b": {"id": result["b"]["id"], "name": result["b"]["name"],
                  "hp_pct": round(result["b"]["hp_pct"] * 100, 1)},
            "winner": result["winner"],
            "turns": result["turns"],
            "log": result["log"],
        })

    hp_a_pct = (hp_a_total / slots * 100) if slots else 0.0
    hp_b_pct = (hp_b_total / slots * 100) if slots else 0.0

    tiebreak = ""
    if wins_a > wins_b:
        winner = "a"
    elif wins_b > wins_a:
        winner = "b"
    elif hp_a_pct > hp_b_pct + 0.001:
        winner, tiebreak = "a", "remaining HP"
    elif hp_b_pct > hp_a_pct + 0.001:
        winner, tiebreak = "b", "remaining HP"
    else:
        syn_a = team_synergy(team_a)
        syn_b = team_synergy(team_b)
        if syn_a > syn_b:
            winner, tiebreak = "a", "team synergy"
        elif syn_b > syn_a:
            winner, tiebreak = "b", "team synergy"
        else:
            bst_a = sum(int(p.get("bst", 0)) for p in team_a)
            bst_b = sum(int(p.get("bst", 0)) for p in team_b)
            if bst_a > bst_b:
                winner, tiebreak = "a", "total base stat"
            elif bst_b > bst_a:
                winner, tiebreak = "b", "total base stat"
            else:
                winner, tiebreak = "a", "seed order"

    return {
        "winner": winner,
        "wins_a": wins_a,
        "wins_b": wins_b,
        "draws": draws,
        "hp_a_pct": round(hp_a_pct, 2),
        "hp_b_pct": round(hp_b_pct, 2),
        "synergy_a": team_synergy(team_a),
        "synergy_b": team_synergy(team_b),
        "tiebreak": tiebreak,
        "slots": details,
        "name_a": name_a,
        "name_b": name_b,
    }


# ----------------------------------------------------------------------
# Round-robin tournament
# ----------------------------------------------------------------------
def run_tournament(participants):
    ids = [p["id"] for p in participants]
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