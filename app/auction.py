"""Auction-specific helpers (starting bids, validation, value display)."""
from app.pokemon_api import compute_auction_value
from config import Config


def starting_bid_for(pokemon):
    """Prefer the value stored at cache time; recompute if it is missing."""
    value = pokemon.get("auction_value")
    if value:
        return int(value)
    return compute_auction_value(
        int(pokemon.get("bst", 0)),
        bool(pokemon.get("is_legendary")),
        bool(pokemon.get("is_mythical")),
    )


def minimum_next_bid(current_bid, starting_bid, increment=None):
    increment = increment or Config.MIN_BID_INCREMENT
    if not current_bid or current_bid <= 0:
        return int(starting_bid)
    return int(current_bid) + int(increment)


def validate_bid(amount, player_coins, current_bid, starting_bid,
                 increment=None, max_amount=None):
    """Return ``(ok, error_message, normalised_amount)``."""
    max_amount = max_amount or Config.MAX_BID_AMOUNT
    try:
        if isinstance(amount, bool):
            raise ValueError
        if isinstance(amount, float):
            if not amount.is_integer():
                return False, "Bids must be whole numbers.", None
            amount = int(amount)
        amount = int(str(amount).strip())
    except (TypeError, ValueError):
        return False, "Enter a valid whole number.", None

    if amount <= 0:
        return False, "Bids must be greater than zero.", None
    if amount > max_amount:
        return False, f"Maximum bid is {max_amount} coins.", None
    if amount > player_coins:
        return False, f"You only have {player_coins} coins.", None

    floor = minimum_next_bid(current_bid, starting_bid, increment)
    if amount < floor:
        if current_bid:
            return False, f"Next valid bid is at least {floor} coins.", None
        return False, f"Opening bid is {floor} coins.", None

    return True, None, amount


def quick_bid_amounts(current_bid, starting_bid, coins, increment=None):
    """Return the +10 / +25 / +50 / MAX button values."""
    increment = increment or Config.MIN_BID_INCREMENT
    base = current_bid if current_bid else starting_bid - increment
    options = {}
    for step in (10, 25, 50):
        value = max(starting_bid, current_bid + step) if current_bid else starting_bid
        options[f"+{step}"] = min(value, coins)
    options["MAX"] = coins
    options["MIN"] = min(minimum_next_bid(current_bid, starting_bid, increment), coins)
    return options