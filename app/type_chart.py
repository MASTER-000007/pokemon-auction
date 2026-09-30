"""The standard 18-type Pokémon effectiveness chart."""

TYPES = [
    "normal", "fire", "water", "electric", "grass", "ice",
    "fighting", "poison", "ground", "flying", "psychic", "bug",
    "rock", "ghost", "dragon", "dark", "steel", "fairy",
]

_RAW = {
    "normal":   {"rock": 0.5, "ghost": 0.0, "steel": 0.5},
    "fire":     {"fire": 0.5, "water": 0.5, "grass": 2.0, "ice": 2.0, "bug": 2.0,
                 "rock": 0.5, "dragon": 0.5, "steel": 2.0},
    "water":    {"fire": 2.0, "water": 0.5, "grass": 0.5, "ground": 2.0,
                 "rock": 2.0, "dragon": 0.5},
    "electric": {"water": 2.0, "electric": 0.5, "grass": 0.5, "ground": 0.0,
                 "flying": 2.0, "dragon": 0.5},
    "grass":    {"fire": 0.5, "water": 2.0, "grass": 0.5, "poison": 0.5,
                 "ground": 2.0, "flying": 0.5, "bug": 0.5, "rock": 2.0,
                 "dragon": 0.5, "steel": 0.5},
    "ice":      {"fire": 0.5, "water": 0.5, "grass": 2.0, "ice": 0.5,
                 "ground": 2.0, "flying": 2.0, "dragon": 2.0, "steel": 0.5},
    "fighting": {"normal": 2.0, "ice": 2.0, "poison": 0.5, "flying": 0.5,
                 "psychic": 0.5, "bug": 0.5, "rock": 2.0, "ghost": 0.0,
                 "dark": 2.0, "steel": 2.0, "fairy": 0.5},
    "poison":   {"grass": 2.0, "poison": 0.5, "ground": 0.5, "rock": 0.5,
                 "ghost": 0.5, "steel": 0.0, "fairy": 2.0},
    "ground":   {"fire": 2.0, "electric": 2.0, "grass": 0.5, "poison": 2.0,
                 "flying": 0.0, "bug": 0.5, "rock": 2.0, "steel": 2.0},
    "flying":   {"electric": 0.5, "grass": 2.0, "fighting": 2.0, "bug": 2.0,
                 "rock": 0.5, "steel": 0.5},
    "psychic":  {"fighting": 2.0, "poison": 2.0, "psychic": 0.5, "dark": 0.0,
                 "steel": 0.5},
    "bug":      {"fire": 0.5, "grass": 2.0, "fighting": 0.5, "poison": 0.5,
                 "flying": 0.5, "psychic": 2.0, "ghost": 0.5, "dark": 2.0,
                 "steel": 0.5, "fairy": 0.5},
    "rock":     {"fire": 2.0, "ice": 2.0, "fighting": 0.5, "ground": 0.5,
                 "flying": 2.0, "bug": 2.0, "steel": 0.5},
    "ghost":    {"normal": 0.0, "psychic": 2.0, "ghost": 2.0, "dark": 0.5},
    "dragon":   {"dragon": 2.0, "steel": 0.5, "fairy": 0.0},
    "dark":     {"fighting": 0.5, "psychic": 2.0, "ghost": 2.0, "dark": 0.5,
                 "fairy": 0.5},
    "steel":    {"fire": 0.5, "water": 0.5, "electric": 0.5, "ice": 2.0,
                 "rock": 2.0, "steel": 0.5, "fairy": 2.0},
    "fairy":    {"fire": 0.5, "fighting": 2.0, "poison": 0.5, "dragon": 2.0,
                 "dark": 2.0, "steel": 0.5},
}


def _build_chart():
    chart = {atk: {dfn: 1.0 for dfn in TYPES} for atk in TYPES}
    for atk, row in _RAW.items():
        for dfn, mult in row.items():
            chart[atk][dfn] = mult
    return chart


CHART = _build_chart()


def type_effectiveness(attack_type, defender_types):
    """Combined multiplier of one attacking type vs a (possibly dual) defender."""
    if attack_type not in CHART:
        return 1.0
    mult = 1.0
    for d in defender_types:
        if d in CHART[attack_type]:
            mult *= CHART[attack_type][d]
    return mult


def multiplier(attack_type, defender_types):
    """Alias for :func:`type_effectiveness` (kept for older callers)."""
    return type_effectiveness(attack_type, defender_types)


def effectiveness_label(mult):
    if mult == 0:
        return "no effect"
    if mult >= 4:
        return "extremely effective"
    if mult > 1:
        return "super effective"
    if mult < 1:
        return "not very effective"
    return "normally effective"


def defensive_profile(types):
    return {atk: type_effectiveness(atk, list(types)) for atk in TYPES}


def offensive_coverage(attacking_types):
    covered = set()
    for atk in attacking_types:
        if atk not in CHART:
            continue
        for dfn in TYPES:
            if CHART[atk][dfn] > 1.0:
                covered.add(dfn)
    return covered


def team_type_report(team_types):
    attacking = set()
    defending = []
    for types in team_types:
        attacking.update(types)
        defending.extend(types)

    profile = defensive_profile(defending) if defending else {t: 1.0 for t in TYPES}
    weaknesses = sorted([t for t, v in profile.items() if v > 1.0])
    resistances = sorted([t for t, v in profile.items() if 0.0 < v < 1.0])
    immunities = sorted([t for t, v in profile.items() if v == 0.0])

    return {
        "offensive_types": sorted(attacking),
        "offensive_coverage": sorted(offensive_coverage(attacking)),
        "coverage_count": len(offensive_coverage(attacking)),
        "weaknesses": weaknesses,
        "resistances": resistances,
        "immunities": immunities,
        "unique_types": sorted(attacking),
        "unique_type_count": len(attacking),
    }