"""Official SDK entry point for the Wolf strategy.

Keep this module thin.  The real implementation lives in ``strategy_core`` so
the official connection runner stays isolated from policy changes.
"""

from strategy_core import WolfStrategy

STRATEGY_IMPLEMENTED = True

_strategy = WolfStrategy()


def on_game_start(start_data, context=None):
    """Cache the one-off map frame and reset per-match state."""
    _strategy.on_game_start(start_data, context)


def on_game_end(settlement=None, battle_data=None):
    """Lifecycle hook reserved for fast, non-blocking match finalisation."""
    _strategy.on_game_end(settlement, battle_data)


def reset_strategy_for_test():
    _strategy.reset_for_test()


def choose_command(game_state, bot_id):
    """Return exactly one legal command for the latest refresh frame."""
    return _strategy.choose_command(game_state, bot_id)
