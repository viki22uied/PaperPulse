"""Persistent state: learned profiles (per user), seen papers.

Everything lives in a single JSON file so the tool is trivial to inspect, back
up, or delete. Multi-user support is a flat ``user -> profile`` map; single-user
setups just use the ``default`` user and never notice.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .profile import InterestProfile

DEFAULT_USER = "default"


@dataclass
class State:
    profiles: dict[str, InterestProfile] = field(default_factory=dict)
    seen_ids: set[str] = field(default_factory=set)
    # id -> {"title", "abstract"} for papers we've shown, so feedback by id can
    # be re-embedded later without another network round-trip.
    shown: dict[str, dict] = field(default_factory=dict)

    # --- convenience for the common single-user case ------------------------
    def get_profile(self, user: str = DEFAULT_USER) -> InterestProfile | None:
        return self.profiles.get(user)

    def set_profile(self, profile: InterestProfile, user: str = DEFAULT_USER) -> None:
        self.profiles[user] = profile

    @property
    def profile(self) -> InterestProfile | None:
        return self.profiles.get(DEFAULT_USER)

    @profile.setter
    def profile(self, value: InterestProfile | None) -> None:
        if value is None:
            self.profiles.pop(DEFAULT_USER, None)
        else:
            self.profiles[DEFAULT_USER] = value

    # --- persistence --------------------------------------------------------
    @classmethod
    def load(cls, path: str | Path) -> "State":
        path = Path(path)
        if not path.exists():
            return cls()
        data = json.loads(path.read_text())

        profiles: dict[str, InterestProfile] = {}
        # New format: {"profiles": {...}}. Old format: {"profile": {...}}.
        if data.get("profiles"):
            profiles = {
                user: InterestProfile.from_dict(p)
                for user, p in data["profiles"].items()
            }
        elif data.get("profile"):
            profiles[DEFAULT_USER] = InterestProfile.from_dict(data["profile"])

        return cls(
            profiles=profiles,
            seen_ids=set(data.get("seen_ids", [])),
            shown=data.get("shown", {}),
        )

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        data = {
            "profiles": {u: p.to_dict() for u, p in self.profiles.items()},
            "seen_ids": sorted(self.seen_ids),
            "shown": self.shown,
        }
        path.write_text(json.dumps(data, indent=2))
        return path
