"""Analytics: derived measures computed from stored shots.

Pure functions only -- no Tkinter, no server imports -- so this package is
testable headless and portable to sibling repos.
"""

from .index import (
    IndexTier,
    bag_index_summary,
    evaluate_coverage,
    player_shanktuary_index,
    shanktuary_index,
)

__all__ = [
    "IndexTier",
    "bag_index_summary",
    "evaluate_coverage",
    "player_shanktuary_index",
    "shanktuary_index",
]
