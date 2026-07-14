"""Community layer: a shared, crowdsourced trust store.

Backed by SQLite so it is self-hostable with zero infrastructure. It records
per-paper trust reports (so scores can be pooled instead of recomputed by every
user), PubPeer-style annotations, and derives a leaderboard of the venues/authors
most often flagged for over-claiming.
"""

from .db import CommunityDB, Annotation

__all__ = ["CommunityDB", "Annotation"]
